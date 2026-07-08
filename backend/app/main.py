from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
import asyncio
import logging

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import db

_logger = logging.getLogger("medbot")
from app.agent_config import agent_config_status, update_agent_config
from app.auth import (
    PERMISSIONS,
    Principal,
    clear_login_failures,
    create_token,
    get_current_principal,
    login_locked_out,
    record_login_failure,
    require,
    verify_password,
)
from app.agent_proxy import AgentProxyError, forward_agent_chat, forward_agent_chat_stream
from app.email_service import (
    fetch_inbox_replies,
    is_configured as email_is_configured,
    send_batch,
    send_email,
    test_connection,
    verify_unsubscribe_token,
)
from fastapi.responses import HTMLResponse
from app.product import extract_product_profile
from app.schemas import (
    AgentConfigResponse,
    AgentConfigUpdate,
    AgentChatRequest,
    AgentChatResponse,
    ChangePasswordRequest,
    EmailTestRequest,
    LeadCreateRequest,
    LeadUpdateRequest,
    LoginRequest,
    OutreachRequest,
    ReplyAnalysisRequest,
    ResetPasswordRequest,
    RoleCreateRequest,
    RoleUpdateRequest,
    ScoringRulesResponse,
    ScoringRulesUpdateRequest,
    SearchRequest,
    SuppressionCreateRequest,
    TokenBudgetUpdateRequest,
    TokenUsageEventRequest,
    UserCreateRequest,
    UserUpdateRequest,
    WebFetchRequest,
    WebSearchRequest,
)
from app.services import (
    CandidateLead,
    RenderedEmail,
    ReplyAnalysisError,
    analyze_reply,
    auto_reply_analysis,
    bounce_reply_analysis,
    generate_candidate_leads,
    render_email,
)
from app.web_search import SearchProviderError, discover_real_prospects, fetch_source_preview, search_web


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        db.init_db()
        bg_task = asyncio.create_task(_auto_sync_loop())
        send_task = asyncio.create_task(_send_dispatch_loop())
        try:
            yield
        finally:
            for task in (bg_task, send_task):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(
        title="Medbot Overseas Distributor Pipeline",
        version="0.1.0",
        description="API for overseas distributor prospecting, outreach record generation, and reply triage.",
        lifespan=lifespan,
    )

    # Auth is via Bearer tokens (not cookies), so credentials are not needed and
    # origins can be locked down. Override with MEDBOT_CORS_ORIGINS (comma-separated)
    # in production; "*" is allowed only because no cookies ride these requests.
    import os as _os
    _cors = _os.getenv("MEDBOT_CORS_ORIGINS", "").strip()
    cors_origins = [o.strip() for o in _cors.split(",") if o.strip()] if _cors else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def _process_unsubscribe(token: str) -> str | None:
        """Suppress the token's email and stop contacting any matching lead.
        Returns the unsubscribed email, or None if the token is invalid."""
        email = verify_unsubscribe_token(token)
        if not email:
            return None
        db.add_suppression(email, reason="unsubscribe", source="email-link")
        db.add_audit(actor=email, action="unsubscribe", target_type="email", target_id=email)
        # If we know this lead, stop contacting it.
        for lead in db.list_leads():
            if str(lead.get("email", "")).strip().lower() == email.lower():
                db.update_lead(int(lead["id"]), status="rejected")
        return email

    @app.get("/unsubscribe", response_class=HTMLResponse, include_in_schema=False)
    def unsubscribe(token: str = Query(default="")) -> str:
        """Public unsubscribe landing page a human sees after clicking the link
        in an email, or the List-Unsubscribe header's URL in a mail client."""
        email = _process_unsubscribe(token)
        if not email:
            return _unsub_page("链接无效或已过期 / Invalid or expired link", ok=False)
        return _unsub_page(
            f"已退订：{email}<br>您将不会再收到我们的邮件。<br><br>"
            f"You have been unsubscribed.<br>You will no longer receive emails from us.",
            ok=True,
        )

    @app.post("/unsubscribe", include_in_schema=False)
    def unsubscribe_one_click(token: str = Query(default="")) -> Response:
        """RFC 8058 one-click unsubscribe target: mail clients (Gmail/Outlook/
        Yahoo) POST here directly from the List-Unsubscribe-Post header with no
        user interaction, so this must not render HTML — just process and
        return an empty success response."""
        email = _process_unsubscribe(token)
        return Response(status_code=200 if email else 400)

    # ── Auth ──────────────────────────────────────────────────────────────────

    @app.post("/auth/login")
    def login(request: LoginRequest, http_request: Request) -> dict[str, object]:
        client_ip = http_request.client.host if http_request.client else "unknown"
        lock_key = f"{client_ip}:{request.username.lower()}"

        retry_after = login_locked_out(lock_key)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail=f"登录失败次数过多，请 {retry_after // 60 + 1} 分钟后再试",
                headers={"Retry-After": str(retry_after)},
            )

        row = db.get_user_auth_row(request.username)
        if row is None or not verify_password(request.password, row["password_hash"]):
            record_login_failure(lock_key)
            db.add_audit(actor=request.username, action="login.failed", target_type="user", detail=client_ip)
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        if not row["is_active"]:
            raise HTTPException(status_code=403, detail="账号已被停用，请联系管理员")

        clear_login_failures(lock_key)
        token = create_token(user_id=int(row["id"]), username=str(row["username"]))
        db.add_audit(actor=str(row["username"]), action="login", target_type="user", target_id=row["id"])
        return {"token": token, "user": db.get_user(int(row["id"]))}

    @app.get("/auth/me")
    def whoami(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
        if principal.user_id is not None:
            user = db.get_user(principal.user_id)
            if user is not None:
                return user
        # Service principal (agent) — no user record.
        return {
            "username": principal.username,
            "is_superadmin": False,
            "is_service": principal.is_service,
            "permissions": sorted(principal.permissions),
            "roles": [],
        }

    @app.post("/auth/change-password")
    def change_password(
        request: ChangePasswordRequest,
        principal: Principal = Depends(get_current_principal),
    ) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=400, detail="服务账号无法修改密码")
        row = db.get_user_auth_row(principal.username)
        if row is None or not verify_password(request.old_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="原密码不正确")
        db.set_user_password(principal.user_id, request.new_password, must_change=False)
        db.add_audit(actor=principal.username, action="password.change", target_type="user", target_id=principal.user_id)
        return {"ok": True}

    # ── Admin: permissions, roles, users (require users.manage) ───────────────

    def _validate_permissions(perms: list[str]) -> list[str]:
        valid = {p["key"] for p in PERMISSIONS}
        unknown = [p for p in perms if p not in valid]
        if unknown:
            raise HTTPException(status_code=400, detail=f"未知权限：{', '.join(unknown)}")
        # De-dup, preserve a stable order.
        return [p["key"] for p in PERMISSIONS if p["key"] in set(perms)]

    @app.get("/admin/permissions", dependencies=[Depends(require("users.manage"))])
    def list_permissions() -> dict[str, object]:
        return {"permissions": PERMISSIONS}

    @app.get("/admin/roles", dependencies=[Depends(require("users.manage"))])
    def list_roles() -> dict[str, object]:
        return {"roles": db.list_roles()}

    @app.post("/admin/roles", status_code=201)
    def create_role(
        request: RoleCreateRequest,
        principal: Principal = Depends(require("users.manage")),
    ) -> dict[str, object]:
        if db.get_role_by_name(request.name) is not None:
            raise HTTPException(status_code=409, detail="角色名已存在")
        perms = _validate_permissions(request.permissions)
        role = db.create_role(name=request.name, description=request.description, permissions=perms)
        db.add_audit(actor=principal.username, action="role.create", target_type="role", target_id=role["id"], detail=request.name)
        return role

    @app.patch("/admin/roles/{role_id}")
    def update_role(
        role_id: int,
        request: RoleUpdateRequest,
        principal: Principal = Depends(require("users.manage")),
    ) -> dict[str, object]:
        role = db.get_role(role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="角色不存在")
        if request.name and request.name != role["name"]:
            existing = db.get_role_by_name(request.name)
            if existing is not None and existing["id"] != role_id:
                raise HTTPException(status_code=409, detail="角色名已存在")
        perms = _validate_permissions(request.permissions) if request.permissions is not None else None
        updated = db.update_role(
            role_id, name=request.name, description=request.description, permissions=perms
        )
        db.add_audit(actor=principal.username, action="role.update", target_type="role", target_id=role_id, detail=role["name"])
        return updated

    @app.delete("/admin/roles/{role_id}")
    def delete_role(
        role_id: int,
        principal: Principal = Depends(require("users.manage")),
    ) -> dict[str, object]:
        role = db.get_role(role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="角色不存在")
        if role["is_system"]:
            raise HTTPException(status_code=400, detail="系统内置角色不可删除")
        if role.get("user_count", 0) > 0:
            raise HTTPException(status_code=409, detail="该角色仍有用户在用，请先解除分配")
        db.delete_role(role_id)
        db.add_audit(actor=principal.username, action="role.delete", target_type="role", target_id=role_id, detail=role["name"])
        return {"ok": True, "deleted": role_id}

    @app.get("/admin/users", dependencies=[Depends(require("users.manage"))])
    def list_users() -> dict[str, object]:
        return {"users": db.list_users()}

    @app.post("/admin/users", status_code=201)
    def create_user(
        request: UserCreateRequest,
        principal: Principal = Depends(require("users.manage")),
    ) -> dict[str, object]:
        if db.get_user_auth_row(request.username) is not None:
            raise HTTPException(status_code=409, detail="用户名已存在")
        valid_role_ids = {r["id"] for r in db.list_roles()}
        bad = [rid for rid in request.role_ids if rid not in valid_role_ids]
        if bad:
            raise HTTPException(status_code=400, detail=f"角色不存在：{bad}")
        user = db.create_user(
            username=request.username,
            password=request.password,
            display_name=request.display_name,
            is_active=request.is_active,
            is_superadmin=request.is_superadmin,
            role_ids=request.role_ids,
        )
        db.add_audit(actor=principal.username, action="user.create", target_type="user", target_id=user["id"], detail=request.username)
        return user

    @app.patch("/admin/users/{user_id}")
    def update_user(
        user_id: int,
        request: UserUpdateRequest,
        principal: Principal = Depends(require("users.manage")),
    ) -> dict[str, object]:
        user = db.get_user(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        # Guard: never strip the last active superadmin of its powers.
        removing_super = (request.is_superadmin is False) and user["is_superadmin"]
        deactivating = (request.is_active is False) and user["is_active"]
        if (removing_super or deactivating) and user["is_superadmin"]:
            if db.count_active_superadmins(exclude_user_id=user_id) == 0:
                raise HTTPException(status_code=400, detail="必须至少保留一名启用的超级管理员")
        if request.role_ids is not None:
            valid_role_ids = {r["id"] for r in db.list_roles()}
            bad = [rid for rid in request.role_ids if rid not in valid_role_ids]
            if bad:
                raise HTTPException(status_code=400, detail=f"角色不存在：{bad}")
        updated = db.update_user(
            user_id,
            display_name=request.display_name,
            is_active=request.is_active,
            is_superadmin=request.is_superadmin,
            role_ids=request.role_ids,
        )
        db.add_audit(actor=principal.username, action="user.update", target_type="user", target_id=user_id, detail=user["username"])
        return updated

    @app.post("/admin/users/{user_id}/reset-password")
    def reset_password(
        user_id: int,
        request: ResetPasswordRequest,
        principal: Principal = Depends(require("users.manage")),
    ) -> dict[str, object]:
        if db.get_user(user_id) is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        # Force the user to set their own password on next login.
        db.set_user_password(user_id, request.new_password, must_change=True)
        db.add_audit(actor=principal.username, action="user.reset_password", target_type="user", target_id=user_id)
        return {"ok": True}

    @app.delete("/admin/users/{user_id}", dependencies=[Depends(require("users.manage"))])
    def delete_user(
        user_id: int,
        principal: Principal = Depends(require("users.manage")),
    ) -> dict[str, object]:
        user = db.get_user(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        if principal.user_id == user_id:
            raise HTTPException(status_code=400, detail="不能删除当前登录的自己")
        if user["is_superadmin"] and db.count_active_superadmins(exclude_user_id=user_id) == 0:
            raise HTTPException(status_code=400, detail="必须至少保留一名启用的超级管理员")
        db.delete_user(user_id)
        db.add_audit(actor=principal.username, action="user.delete", target_type="user", target_id=user_id, detail=user["username"])
        return {"ok": True, "deleted": user_id}

    # ── Compliance: suppression list + audit log (require users.manage) ───────

    @app.get("/admin/suppressions", dependencies=[Depends(require("users.manage"))])
    def list_suppressions(q: str | None = Query(default=None)) -> dict[str, object]:
        items = db.list_suppressions(q)
        return {"total": len(items), "suppressions": items}

    @app.post("/admin/suppressions", status_code=201)
    def add_suppression(
        request: SuppressionCreateRequest,
        principal: Principal = Depends(require("users.manage")),
    ) -> dict[str, object]:
        record = db.add_suppression(
            request.email, reason=request.reason or "manual", source="manual", notes=request.notes
        )
        db.add_audit(actor=principal.username, action="suppression.add", target_type="email", target_id=request.email, detail=request.reason)
        return record

    @app.delete("/admin/suppressions")
    def delete_suppression(
        email: str = Query(min_length=3),
        principal: Principal = Depends(require("users.manage")),
    ) -> dict[str, object]:
        removed = db.remove_suppression(email)
        if removed:
            db.add_audit(actor=principal.username, action="suppression.remove", target_type="email", target_id=email)
        return {"ok": removed, "email": email}

    @app.get("/admin/audit", dependencies=[Depends(require("users.manage"))])
    def list_audit(
        limit: int = Query(default=200, ge=1, le=1000),
        action: str | None = Query(default=None),
    ) -> dict[str, object]:
        items = db.list_audit(limit=limit, action=action)
        return {"total": len(items), "events": items}

    @app.get("/metrics", dependencies=[Depends(require("leads.view"))])
    def metrics() -> dict[str, int]:
        return db.metrics()

    @app.get("/product/profile", dependencies=[Depends(get_current_principal)])
    def product_profile() -> dict[str, object]:
        return extract_product_profile().to_dict()

    @app.get(
        "/scoring/rules",
        response_model=ScoringRulesResponse,
        dependencies=[Depends(get_current_principal)],
    )
    def scoring_rules(
        lead_type: str = Query(default="distributor", description="distributor 或 kol，两套规则独立配置。"),
    ) -> dict[str, object]:
        """Current lead-scoring weights/rules for the given lead type. Readable
        by any authenticated principal (including the Agent's delegated/service
        token) so the prospecting skill can fetch live values instead of
        hardcoded ones."""
        return db.get_scoring_rules(lead_type)

    @app.put(
        "/scoring/rules",
        response_model=ScoringRulesResponse,
        dependencies=[Depends(require("settings.manage"))],
    )
    def update_scoring_rules(
        request: ScoringRulesUpdateRequest,
        lead_type: str = Query(default="distributor", description="distributor 或 kol，两套规则独立配置。"),
        principal: Principal = Depends(require("settings.manage")),
    ) -> dict[str, object]:
        updated = db.set_scoring_rules(request.model_dump(), lead_type)
        db.add_audit(actor=principal.username, action="scoring_rules.update", detail=lead_type)
        return updated

    @app.post("/agent/chat", response_model=AgentChatResponse, dependencies=[Depends(require("agent.use"))])
    def agent_chat(
        request: AgentChatRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, object]:
        try:
            return forward_agent_chat(request.model_dump(), user_token=_bearer_token(authorization))
        except AgentProxyError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.post("/agent/chat/stream", dependencies=[Depends(require("agent.use"))])
    def agent_chat_stream(
        request: AgentChatRequest,
        authorization: str | None = Header(default=None),
    ) -> StreamingResponse:
        try:
            stream = forward_agent_chat_stream(request.model_dump(), user_token=_bearer_token(authorization))
        except AgentProxyError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.get("/agent/config", response_model=AgentConfigResponse, dependencies=[Depends(require("agent.config"))])
    def agent_config() -> dict[str, object]:
        return agent_config_status()

    @app.put("/agent/config", response_model=AgentConfigResponse, dependencies=[Depends(require("agent.config"))])
    def save_agent_config(request: AgentConfigUpdate) -> dict[str, object]:
        return update_agent_config(
            provider_name=request.provider_name,
            api_key=request.api_key,
            openai_api_key=request.openai_api_key,
            model_name=request.model_name,
            backend_base_url=request.backend_base_url,
        )

    @app.post("/leads/search", status_code=201, dependencies=[Depends(require("leads.search"))])
    def search_leads(request: SearchRequest) -> dict[str, object]:
        if request.real_search:
            try:
                candidates = discover_real_prospects(
                    target_regions=request.target_regions,
                    product_profile=extract_product_profile(),
                    extra_keywords=request.product_keywords,
                    max_results=request.max_results,
                    require_email=request.require_email,
                )
            except SearchProviderError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        else:
            candidates = generate_candidate_leads(
                target_regions=request.target_regions,
                product_keywords=request.product_keywords,
                max_results=request.max_results,
            )

        # Dedup against existing leads
        candidates = _filter_existing_leads(candidates)

        saved = [db.insert_lead(candidate) for candidate in candidates]
        return {"created_count": len(saved), "leads": saved}

    @app.post("/leads/batch", status_code=201, dependencies=[Depends(require("leads.edit"))])
    def batch_create_leads(request: list[LeadCreateRequest]) -> dict[str, object]:
        """Batch create leads (used by Agent to save discovered leads)."""
        candidates = [
            CandidateLead(
                company_name=item.company_name,
                region=item.region,
                country=item.country,
                website=item.website,
                contact_name=item.contact_name,
                email=item.email,
                category=item.category,
                match_reason=item.match_reason,
                source=item.source,
                score=item.score if item.score is not None else 50,
                status="new",
                notes="Agent discovered",
                lead_type=item.lead_type,
            )
            for item in request
        ]
        # Dedup against existing leads — do not rely solely on the Agent
        # remembering to call list_leads before add_leads.
        candidates = _filter_existing_leads(candidates)
        created = [db.insert_lead(candidate) for candidate in candidates]
        return {"created_count": len(created), "leads": created}

    @app.post("/leads", status_code=201, dependencies=[Depends(require("leads.edit"))])
    def create_lead(request: LeadCreateRequest) -> dict[str, object]:
        """Manually create a lead."""
        lead = CandidateLead(
            company_name=request.company_name,
            region=request.region,
            country=request.country,
            website=request.website,
            contact_name=request.contact_name,
            email=request.email,
            category=request.category,
            match_reason=request.match_reason,
            source=request.source,
            score=request.score if request.score is not None else 50,
            status="new",
            notes="",
            lead_type=request.lead_type,
        )
        return db.insert_lead(lead)

    @app.delete("/leads/{lead_id}")
    def delete_lead(
        lead_id: int,
        principal: Principal = Depends(require("leads.delete")),
    ) -> dict[str, object]:
        """Delete a lead and its associated outreach events and reply analyses."""
        if not db.delete_lead(lead_id):
            raise HTTPException(status_code=404, detail="Lead not found")
        db.add_audit(actor=principal.username, action="lead.delete", target_type="lead", target_id=lead_id)
        return {"ok": True, "deleted": lead_id}

    @app.post("/leads/batch-delete")
    def batch_delete_leads(
        request: dict[str, object],
        principal: Principal = Depends(require("leads.delete")),
    ) -> dict[str, object]:
        """Delete multiple leads at once."""
        lead_ids = request.get("lead_ids", [])
        if not isinstance(lead_ids, list) or not lead_ids:
            raise HTTPException(status_code=400, detail="lead_ids required")
        deleted = 0
        for lid in lead_ids:
            if isinstance(lid, (int, float)) and db.delete_lead(int(lid)):
                deleted += 1
        db.add_audit(actor=principal.username, action="lead.delete", target_type="lead", target_id=f"batch({deleted})")
        return {"ok": True, "deleted": deleted}

    @app.get("/leads", dependencies=[Depends(require("leads.view"))])
    def list_leads(
        region: str | None = Query(default=None),
        country: str | None = Query(default=None),
        status: str | None = Query(default=None),
        lead_type: str | None = Query(default=None, description="distributor 或 kol，留空为全部。"),
        q: str | None = Query(default=None),
        sort: str = Query(
            default="id",
            description=(
                "\u6392\u5e8f\u5b57\u6bb5\uff1aid, score, company_name, country, region, "
                "status, category, created_at, updated_at, reply_count\u3002"
                "\u672a\u77e5\u503c\u56de\u9000\u5230 id\u3002"
            ),
        ),
        order: str = Query(
            default="desc",
            description="\u6392\u5e8f\u65b9\u5411\uff1aasc \u6216 desc\uff0c\u9ed8\u8ba4 desc\u3002",
        ),
    ) -> dict[str, object]:
        leads = db.list_leads(
            region=region, country=country, status=status, lead_type=lead_type, q=q, sort=sort, order=order
        )
        return {"total": len(leads), "leads": leads}

    @app.get("/leads/facets", dependencies=[Depends(require("leads.view"))])
    def lead_facets() -> dict[str, object]:
        """Distinct region/country values (with counts) for the filter dropdowns."""
        return db.lead_facets()

    @app.get("/sources/preview", dependencies=[Depends(require("leads.search"))])
    def source_preview(
        url: str = Query(min_length=8),
        email: str = Query(default=""),
    ) -> dict[str, object]:
        try:
            return fetch_source_preview(url=url, email=email)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/web/search", dependencies=[Depends(require("leads.search"))])
    def web_search(request: WebSearchRequest) -> dict[str, object]:
        try:
            results = search_web(request.query, limit=request.max_results)
        except SearchProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "query": request.query,
            "results": [asdict(result) for result in results],
        }

    @app.post("/web/fetch", dependencies=[Depends(require("leads.search"))])
    def web_fetch(request: WebFetchRequest) -> dict[str, object]:
        try:
            return fetch_source_preview(url=request.url, email=request.email)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/leads/{lead_id}/history", dependencies=[Depends(require("leads.view"))])
    def lead_history(lead_id: int) -> dict[str, object]:
        lead = db.get_lead(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        outreach = db.list_outreach_events(lead_id)
        replies = db.list_reply_analyses(lead_id)
        return {
            "lead": lead,
            "outreach_events": outreach,
            "reply_analyses": replies,
        }

    @app.patch("/leads/{lead_id}", dependencies=[Depends(require("leads.edit"))])
    def update_lead(lead_id: int, request: LeadUpdateRequest) -> dict[str, object]:
        if request.lead_type is not None and request.lead_type not in ("distributor", "kol"):
            raise HTTPException(status_code=400, detail="lead_type must be 'distributor' or 'kol'")
        updated = db.update_lead(
            lead_id,
            status=request.status,
            notes=request.notes,
            lead_type=request.lead_type,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        return updated

    @app.post("/campaigns/outreach-records", status_code=201)
    def create_outreach_records(
        request: OutreachRequest,
        principal: Principal = Depends(require("outreach.create")),
    ) -> dict[str, object]:
        actor = "agent" if request.source == "agent" else principal.username
        return _create_outreach_records(request, source=request.source, actor=actor)

    @app.post("/campaigns/outreach-preview", dependencies=[Depends(require("outreach.view"))])
    def preview_outreach(request: OutreachRequest) -> dict[str, object]:
        """Generate email previews without sending."""
        previews: list[dict[str, object]] = []
        for lead_id in request.lead_ids:
            lead = db.get_lead(lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
            rendered = render_email(_lead_from_record(lead))
            previews.append({
                "lead_id": lead_id,
                "company_name": lead["company_name"],
                "email": lead["email"],
                "subject": rendered.subject,
                "body": rendered.body,
            })
        return {"previews": previews}

    @app.get("/campaigns/queue", dependencies=[Depends(require("outreach.view"))])
    def queue_status() -> dict[str, object]:
        """Outreach send-queue status and today's throttle usage."""
        cfg = _send_throttle()
        return {
            "queued": db.count_queued(),
            "sent_today": db.count_sent_since(_today_start_iso()),
            "daily_cap": cfg["daily_cap"],
            "min_interval_seconds": cfg["min_interval"],
            "per_domain_daily_cap": cfg["per_domain_cap"],
            "email_configured": email_is_configured(),
        }

    @app.get("/campaigns/drafts", dependencies=[Depends(require("outreach.view"))])
    def list_drafts() -> dict[str, object]:
        """List all pending draft outreach events (created by Agent, awaiting approval)."""
        drafts = db.list_draft_events()
        return {"total": len(drafts), "drafts": drafts}

    @app.post("/campaigns/drafts/{event_id}/approve")
    def approve_draft(
        event_id: int,
        principal: Principal = Depends(require("outreach.send")),
    ) -> dict[str, object]:
        """Approve a draft and send the email via EWS."""
        event = db.approve_outreach_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Refuse to send to a suppressed (unsubscribed/bounced) address.
        if db.is_suppressed(str(event["sent_to"])):
            db.mark_outreach_status(event_id, "suppressed")
            return {"ok": False, "event": event, "sent": False, "error": "收件人已退订/在抑制名单，未发送"}

        # Approving queues for throttled background delivery (not an inline send).
        db.mark_outreach_status(event_id, "queued")
        db.add_audit(actor=principal.username, action="draft.approve", target_type="lead", target_id=event["lead_id"], detail=str(event["sent_to"]))
        return {"ok": True, "event": event, "queued": True, "note": "已加入发送队列，将按节流速率发出。"}

    @app.post("/campaigns/drafts/{event_id}/reject", dependencies=[Depends(require("outreach.send"))])
    def reject_draft(event_id: int) -> dict[str, object]:
        """Reject a draft without sending."""
        event = db.reject_outreach_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Draft not found")
        return {"ok": True, "event": event}

    @app.post("/campaigns/drafts/approve-all")
    def approve_all_drafts(
        principal: Principal = Depends(require("outreach.send")),
    ) -> dict[str, object]:
        """Approve all pending drafts and send them (skipping suppressed addresses)."""
        drafts = db.list_draft_events()
        queued = 0
        skipped = 0
        for draft in drafts:
            event_id = int(draft["id"])
            if db.is_suppressed(str(draft["sent_to"])):
                db.mark_outreach_status(event_id, "suppressed")
                skipped += 1
                continue
            db.mark_outreach_status(event_id, "queued")
            queued += 1
        if queued:
            db.add_audit(actor=principal.username, action="draft.approve", target_type="batch", detail=f"queued {queued}")
        return {"ok": True, "queued": queued, "skipped_suppressed": skipped, "note": "已加入发送队列，将按节流速率发出。"}

    @app.post("/email/test", dependencies=[Depends(require("settings.manage"))])
    def email_test(request: EmailTestRequest) -> dict[str, object]:
        """Send a test email to verify EWS connectivity."""
        if not email_is_configured():
            raise HTTPException(
                status_code=503,
                detail="Email not configured. Set MEDBOT_EMAIL_SERVER, MEDBOT_EMAIL_USER, MEDBOT_EMAIL_PASSWORD.",
            )
        result = send_email(to=request.to, subject=request.subject, body=request.body)
        return {
            "ok": result.success,
            "sent_to": result.sent_to,
            "subject": result.subject,
            "message_id": result.message_id,
            "error": result.error,
        }

    @app.get("/email/status", dependencies=[Depends(require("settings.manage"))])
    def email_status() -> dict[str, object]:
        """Return email configuration status and Exchange connectivity."""
        configured = email_is_configured()
        status: dict[str, object] = {
            "configured": configured,
        }
        if configured:
            status.update(test_connection())
        else:
            status["message"] = (
                "Email not configured. Set MEDBOT_EMAIL_SERVER, MEDBOT_EMAIL_USER, MEDBOT_EMAIL_PASSWORD."
            )
        return status

    @app.post("/campaigns/send-demo", status_code=201, include_in_schema=False, dependencies=[Depends(require("outreach.create"))])
    def send_legacy_demo(request: OutreachRequest) -> dict[str, object]:
        return _create_outreach_records(request, source="manual")

    def _create_outreach_records(
        request: OutreachRequest,
        *,
        source: str = "manual",
        actor: str = "system",
    ) -> dict[str, object]:
        events = []
        send_enabled = email_is_configured()
        send_errors: list[dict[str, object]] = []

        # Agent source: draft by default. Only auto-send if the operator explicitly
        # enabled "AI 自动发送" in settings (default off). Manual/UI source still sends
        # when email is configured.
        if source == "agent":
            auto_send = db.get_setting("auto_send_enabled", "false") == "true"
            should_send = send_enabled and auto_send
        else:
            should_send = send_enabled

        for lead_id in request.lead_ids:
            lead = db.get_lead(lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
            if not str(lead["email"]).strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"Lead {lead_id} has no discovered email address",
                )

            # Never email a suppressed (unsubscribed / bounced) address.
            if db.is_suppressed(str(lead["email"])):
                rendered = render_email(_lead_from_record(lead))
                event = db.insert_outreach_event(lead_id, rendered, status="suppressed", source=source)
                events.append(event)
                continue

            rendered = render_email(_lead_from_record(lead))

            # Apply custom edits from preview
            custom_key = str(lead_id)
            if request.custom_emails and custom_key in request.custom_emails:
                custom = request.custom_emails[custom_key]
                rendered = RenderedEmail(
                    sent_to=rendered.sent_to,
                    subject=str(custom.get("subject", rendered.subject)),
                    body=str(custom.get("body", rendered.body)),
                    region=rendered.region,
                )

            if should_send:
                # Don't send inline — enqueue for throttled background delivery so a
                # burst of cold emails can't spike the domain's spam reputation.
                event = db.enqueue_outreach(lead_id, rendered, source=source)
            else:
                status = "draft" if source == "agent" else "recorded"
                event = db.insert_outreach_event(lead_id, rendered, status=status, source=source)

            events.append(event)

        queued_count = sum(1 for e in events if e.get("status") == "queued")
        response: dict[str, object] = {
            "sent_count": len(events),
            "queued_count": queued_count,
            "events": events,
            "email_delivery": should_send,
            "source": source,
        }
        if should_send and queued_count:
            response["note"] = f"已加入发送队列 {queued_count} 封，将按节流速率自动发出。"
        elif source == "agent" and not should_send:
            response["note"] = "Agent 生成的外联已存为草稿，审核批准后才会发送。"
        if send_errors:
            response["send_errors"] = send_errors
        return response

    @app.post("/replies/sync", status_code=201, dependencies=[Depends(require("replies.analyze"))])
    def sync_inbox_replies() -> dict[str, object]:
        """Fetch real replies from Exchange inbox and match them to leads."""
        if not email_is_configured():
            raise HTTPException(
                status_code=503,
                detail="Email not configured.",
            )

        # Fetch replies from inbox
        inbox_replies = fetch_inbox_replies(max_count=30)

        # Build lookup: exact email → lead, and domain → leads
        all_leads = db.list_leads()
        email_to_lead: dict[str, dict[str, object]] = {}
        domain_to_leads: dict[str, list[dict[str, object]]] = {}

        for lead in all_leads:
            lead_email = str(lead.get("email", "")).strip().lower()
            if not lead_email:
                continue
            email_to_lead[lead_email] = lead

            # Domain fallback
            domain = lead_email.split("@")[-1] if "@" in lead_email else ""
            if domain:
                domain_to_leads.setdefault(domain, []).append(lead)

        synced: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        bounced: list[str] = []
        analysis_failed = 0  # replies we couldn't analyze (LLM unavailable/failed)
        opted_out: list[str] = []  # addresses suppressed due to explicit opt-out

        for reply in inbox_replies:
            sender = reply.sender_email.lower()

            # Bounce / non-delivery report → suppress the failed recipient(s).
            if _is_bounce(sender, reply.subject):
                if _reply_already_synced(reply.message_id):
                    continue
                hit = _suppress_bounced_recipients(reply.body, email_to_lead)
                if hit:
                    bounced.extend(hit)
                    db.insert_reply_analysis(
                        lead_id=None, reply_text=reply.body[:2000],
                        analysis=bounce_reply_analysis(), message_id=reply.message_id,
                    )
                    continue

            # 1. Exact email match
            matched_lead = email_to_lead.get(sender)

            # 2. Domain match fallback
            if matched_lead is None:
                sender_domain = sender.split("@")[-1] if "@" in sender else ""
                candidates = domain_to_leads.get(sender_domain, [])
                if len(candidates) == 1:
                    matched_lead = candidates[0]
                elif len(candidates) > 1:
                    # Pick the most recently created/updated one
                    matched_lead = candidates[0]

            if matched_lead is None:
                skipped.append({
                    "sender": sender,
                    "subject": reply.subject,
                    "reason": "no matching lead",
                })
                continue

            lead_id = int(matched_lead["id"])

            # Dedup: skip if this exact reply was already synced
            if _reply_already_synced(reply.message_id):
                skipped.append({
                    "sender": sender,
                    "subject": reply.subject,
                    "reason": "already synced",
                })
                continue

            # Skip if this looks like an auto-reply
            is_auto = _is_auto_reply(reply.subject, reply.body)

            if is_auto:
                analysis = auto_reply_analysis()
                # Don't change lead status for auto-replies
            else:
                try:
                    analysis = analyze_reply(reply.body)
                except ReplyAnalysisError as exc:
                    # LLM-only reply analysis: don't guess with rules — skip this
                    # reply (leave it unanalyzed) and surface why in the result.
                    analysis_failed += 1
                    skipped.append({
                        "sender": sender,
                        "subject": reply.subject,
                        "reason": f"AI 分析失败：{exc}",
                    })
                    continue
                db.update_lead(
                    lead_id,
                    status=_status_for_intent(analysis.intent, analysis.requires_human),
                )
                # Only an EXPLICIT opt-out (unsubscribe / remove me) suppresses the
                # address — a merely "not interested" reply must stay recoverable.
                if analysis.opt_out and sender:
                    db.add_suppression(sender, reason="reply-optout", source="inbox")
                    db.add_audit(actor="system", action="suppression.add", target_type="email", target_id=sender, detail="reply-optout")
                    opted_out.append(sender)
            record = db.insert_reply_analysis(
                lead_id=lead_id,
                reply_text=reply.body,
                analysis=analysis,
                message_id=reply.message_id,
            )

            synced.append({
                "lead_id": lead_id,
                "company": matched_lead["company_name"],
                "sender": sender,
                "subject": reply.subject,
                "intent": analysis.intent,
                "confidence": analysis.confidence,
                "auto_reply": is_auto,
                "analysis_id": record["id"],
            })

        return {
            "total_inbox": len(inbox_replies),
            "synced": len(synced),
            "skipped": len(skipped),
            "bounced_suppressed": len(bounced),
            "analysis_failed": analysis_failed,
            "ai_ready": _content_ai_ready(),
            "opted_out": len(opted_out),
            "items": synced,
            "skipped_items": skipped[:10],
        }

    @app.post("/replies/analyze", status_code=201, dependencies=[Depends(require("replies.analyze"))])
    def analyze_reply_endpoint(request: ReplyAnalysisRequest) -> dict[str, object]:
        if request.lead_id is not None and db.get_lead(request.lead_id) is None:
            raise HTTPException(status_code=404, detail="Lead not found")

        try:
            analysis = analyze_reply(request.reply_text)
        except ReplyAnalysisError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if request.lead_id is not None:
            db.update_lead(
                request.lead_id,
                status=_status_for_intent(analysis.intent, analysis.requires_human),
            )
        return db.insert_reply_analysis(
            lead_id=request.lead_id,
            reply_text=request.reply_text,
            analysis=analysis,
        )

    @app.get("/settings", dependencies=[Depends(require("settings.manage"))])
    def get_settings() -> dict[str, object]:
        """Return all settings including sync frequency, agent config, and email."""
        settings = db.get_all_settings()
        return {
            "sync_enabled": settings.get("sync_enabled", "false") == "true",
            "sync_interval_minutes": int(settings.get("sync_interval_minutes", "0") or "0"),
            "auto_send_enabled": settings.get("auto_send_enabled", "false") == "true",
            "send_daily_cap": int(settings.get("send_daily_cap", "200") or "200"),
            "send_min_interval_seconds": int(settings.get("send_min_interval_seconds", "20") or "20"),
            "send_per_domain_daily_cap": int(settings.get("send_per_domain_daily_cap", "25") or "25"),
            # AI content generation (outreach emails + reply analysis). Default on:
            # LLM-generated with the template/keyword rules only as a fallback.
            "ai_content_generation": settings.get("ai_content_generation", "true") == "true",
            "ai_content_ready": _content_ai_ready(),
            "agent_provider": settings.get("agent_provider", ""),
            "agent_model": settings.get("agent_model", ""),
            "has_agent_key": bool(settings.get("agent_key", "")),
            "agent_key_preview": _mask_key(settings.get("agent_key", "")),
            "backend_base_url": settings.get("backend_base_url", "http://localhost:8000"),
            "email_server": settings.get("email_server", "mail.microport.com.cn"),
            "email_user": settings.get("email_user", ""),
            "has_email_password": bool(settings.get("email_password", "")),
        }

    @app.put("/settings")
    def save_settings(
        request: dict[str, object],
        principal: Principal = Depends(require("settings.manage")),
    ) -> dict[str, object]:
        """Save settings. Accepts partial updates. Applies email config immediately."""
        changed: list[str] = []
        for key in (
            "sync_enabled", "sync_interval_minutes", "auto_send_enabled",
            "ai_content_generation",
            "send_daily_cap", "send_min_interval_seconds", "send_per_domain_daily_cap",
            "agent_provider", "agent_model", "agent_key", "backend_base_url",
            "email_server", "email_user", "email_password",
        ):
            if key in request:
                val = request[key]
                db.set_setting(key, str(val).lower() if isinstance(val, bool) else str(val))
                # Audit which settings changed — never log secret values.
                changed.append(key if key not in ("agent_key", "email_password") else f"{key}=***")

        # Reload email config so changes take effect immediately
        from app.email_service import reload_config
        reload_config()

        if changed:
            db.add_audit(actor=principal.username, action="settings.update", detail=", ".join(changed))
        return get_settings()

    @app.get("/usage/token-report", dependencies=[Depends(require("settings.manage"))])
    def token_usage_report() -> dict[str, object]:
        """Monthly AI token usage vs. the configured budget, plus a daily trend series."""
        return _build_token_usage_report()

    @app.put("/usage/token-budget", dependencies=[Depends(require("settings.manage"))])
    def update_token_budget(
        request: TokenBudgetUpdateRequest,
        principal: Principal = Depends(require("settings.manage")),
    ) -> dict[str, object]:
        """Set the monthly token budget used to compute used/remaining in the report."""
        db.set_setting("monthly_token_budget", str(request.budget_tokens))
        db.add_audit(
            actor=principal.username,
            action="settings.update",
            detail=f"monthly_token_budget={request.budget_tokens}",
        )
        return _build_token_usage_report()

    @app.post("/usage/token-events", dependencies=[Depends(require("agent.use"))])
    def record_token_usage_event(request: TokenUsageEventRequest) -> dict[str, object]:
        """Agent sidecar reports token usage for a completed chat turn."""
        db.insert_token_usage_event(
            source="agent_chat",
            provider=request.provider,
            model=request.model,
            prompt_tokens=request.prompt_tokens,
            completion_tokens=request.completion_tokens,
            total_tokens=request.total_tokens,
            actor="agent",
        )
        return {"ok": True}

    return app


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _content_ai_ready() -> bool:
    """Whether an LLM is actually resolvable for email/reply generation.

    Ignores the on/off master switch — reflects only that a usable key exists
    (in backend settings or the Pi sidecar's agent/.env), so the UI can warn
    when AI generation is enabled but no key is configured anywhere.
    """
    from app.agent_config import resolve_sidecar_ai

    if db.get_setting("agent_key", "").strip() and db.get_setting("agent_provider", "").strip():
        return True
    return resolve_sidecar_ai() is not None


def _bearer_token(authorization: str | None) -> str | None:
    """Extract the raw bearer token from an Authorization header, if present.

    Used to delegate the calling human's own JWT to the Agent sidecar, so its
    outbound tool calls run with that user's real RBAC permissions instead of
    the sidecar's blanket-privileged service token.
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return token or None
    return None


def _unsub_page(message: str, *, ok: bool) -> str:
    color = "#047857" if ok else "#b91c1c"
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>退订 / Unsubscribe</title></head>
<body style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:#f7f8fb;margin:0;
display:flex;align-items:center;justify-content:center;min-height:100vh;">
<div style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:36px 40px;max-width:440px;
box-shadow:0 12px 28px rgba(15,23,42,.06);text-align:center;">
<div style="font-size:30px;color:{color};margin-bottom:12px;">{'✓' if ok else '✕'}</div>
<p style="font-size:15px;line-height:1.7;color:#334155;margin:0;">{message}</p>
</div></body></html>"""


def _today_start_iso() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _month_start_iso() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _days_ago_iso(days: int) -> str:
    from datetime import UTC, datetime, timedelta
    start = datetime.now(UTC) - timedelta(days=days)
    return start.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _build_token_usage_report() -> dict[str, object]:
    """Monthly-to-date token usage vs. the configured budget, plus a 30-day daily trend."""
    month_start = _month_start_iso()
    used = db.token_usage_total_since(month_start)
    budget = int(db.get_setting("monthly_token_budget", "0") or "0")
    return {
        "month_start": month_start,
        "used_tokens": used,
        "budget_tokens": budget,
        "remaining_tokens": max(budget - used, 0) if budget > 0 else None,
        "percent_used": round(used / budget * 100, 1) if budget > 0 else None,
        "by_source": db.token_usage_breakdown_since(month_start),
        "daily_series": db.token_usage_daily_series(since_iso=_days_ago_iso(29)),
    }


def _send_throttle() -> dict[str, int]:
    return {
        "daily_cap": int(db.get_setting("send_daily_cap", "200") or "200"),
        "min_interval": int(db.get_setting("send_min_interval_seconds", "20") or "20"),
        "per_domain_cap": int(db.get_setting("send_per_domain_daily_cap", "25") or "25"),
    }


def _dispatch_due_email() -> bool:
    """Send at most one queued email if throttle limits allow. Returns True if one was sent."""
    if not email_is_configured():
        return False
    cfg = _send_throttle()
    today = _today_start_iso()

    if db.count_sent_since(today) >= cfg["daily_cap"]:
        return False

    last = db.last_sent_at()
    if last:
        from datetime import UTC, datetime
        try:
            elapsed = (datetime.now(UTC) - datetime.fromisoformat(last)).total_seconds()
            if elapsed < cfg["min_interval"]:
                return False
        except (ValueError, TypeError):
            pass

    for event in db.list_queued_events(limit=50):
        to = str(event["sent_to"])
        # Re-check suppression at delivery time.
        if db.is_suppressed(to):
            db.mark_outreach_status(int(event["id"]), "suppressed")
            continue
        domain = to.split("@")[-1] if "@" in to else ""
        if domain and db.count_sent_since(today, domain=domain) >= cfg["per_domain_cap"]:
            continue  # this domain hit its daily cap; try another recipient

        result = send_email(to=to, subject=str(event["subject"]), body=str(event["body"]))
        if result.success:
            db.mark_outreach_sent(int(event["id"]), message_id=result.message_id)
            db.add_audit(actor="dispatch", action="email.sent", target_type="lead", target_id=event["lead_id"], detail=to)
        else:
            db.mark_outreach_status(int(event["id"]), "send_failed", error=result.error)
        return True  # one attempt per tick paces the send rate
    return False


async def _send_dispatch_loop() -> None:
    """Background worker: drains the outreach queue at the configured throttle rate."""
    while True:
        try:
            sent = await asyncio.to_thread(_dispatch_due_email)
            # Tick fast enough to honor short intervals, slow enough to idle cheaply.
            await asyncio.sleep(3 if sent else 5)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("Send dispatch error, retrying in 30s")
            await asyncio.sleep(30)


async def _auto_sync_loop() -> None:
    """Background task that periodically syncs inbox replies."""
    while True:
        try:
            enabled = db.get_setting("sync_enabled", "false") == "true"
            interval_str = db.get_setting("sync_interval_minutes", "0")
            interval = int(interval_str) if interval_str else 0

            if enabled and interval > 0 and email_is_configured():
                _logger.info("Auto-sync: checking inbox...")
                replies = fetch_inbox_replies(max_count=20)
                synced = 0
                for reply in replies:
                    if not _reply_already_synced(reply.message_id):
                        matched = _match_reply_to_lead(reply.sender_email)
                        if matched:
                            is_auto = _is_auto_reply(reply.subject, reply.body)
                            if is_auto:
                                analysis = auto_reply_analysis()
                            else:
                                try:
                                    analysis = analyze_reply(reply.body)
                                except ReplyAnalysisError as exc:
                                    # LLM-only: skip unanalyzable replies rather
                                    # than fall back to unreliable keyword rules.
                                    _logger.warning("Auto-sync: skipped reply (AI analysis failed): %s", exc)
                                    continue
                                db.update_lead(
                                    int(matched["id"]),
                                    status=_status_for_intent(analysis.intent, analysis.requires_human),
                                )
                            db.insert_reply_analysis(
                                lead_id=int(matched["id"]),
                                reply_text=reply.body,
                                analysis=analysis,
                                message_id=reply.message_id,
                            )
                            synced += 1
                if synced:
                    _logger.info("Auto-sync: synced %d new replies", synced)

            # Sleep for a check interval (every 2 min, or the sync interval, whichever is smaller)
            sleep_seconds = max(120, interval * 60) if interval > 0 else 300
            await asyncio.sleep(sleep_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("Auto-sync error, retrying in 5 min")
            await asyncio.sleep(300)


def _match_reply_to_lead(sender_email: str) -> dict[str, object] | None:
    """Match a sender email to a lead by exact or domain match."""
    sender = sender_email.lower()
    all_leads = db.list_leads()

    # Exact match
    for lead in all_leads:
        if str(lead.get("email", "")).strip().lower() == sender:
            return lead

    # Domain match
    sender_domain = sender.split("@")[-1] if "@" in sender else ""
    if sender_domain:
        candidates = [l for l in all_leads
                      if str(l.get("email", "")).strip().lower().endswith("@" + sender_domain)]
        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1:
            return candidates[0]

    return None


def _lead_from_record(record: dict[str, object]) -> CandidateLead:
    return CandidateLead(
        company_name=str(record["company_name"]),
        region=str(record["region"]),
        country=str(record["country"]),
        website=str(record["website"]),
        contact_name=str(record["contact_name"]),
        email=str(record["email"]),
        category=str(record["category"]),
        match_reason=str(record["match_reason"]),
        source=str(record["source"]),
        score=int(record["score"]),
        status=str(record["status"]),
        notes=str(record["notes"]),
        lead_type=str(record.get("lead_type", "") or ""),
    )


def _reply_already_synced(message_id: str) -> bool:
    """Check if a reply with this Exchange message_id was already stored."""
    if not message_id:
        return False
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM reply_analyses WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return bool(row and row[0] > 0)


def _filter_existing_leads(candidates: list[CandidateLead]) -> list[CandidateLead]:
    """Remove candidates that already exist in the database (by domain or email)."""
    existing = db.list_leads()
    existing_domains: set[str] = set()
    existing_emails: set[str] = set()
    existing_names: set[str] = set()

    for lead in existing:
        email = str(lead.get("email", "")).strip().lower()
        website = str(lead.get("website", "")).strip().lower()
        name = str(lead.get("company_name", "")).strip().lower()

        if email:
            existing_emails.add(email)
        if website:
            domain = website.split("://")[-1].split("/")[0].removeprefix("www.")
            if domain:
                existing_domains.add(domain)
        if name:
            existing_names.add(name)

    filtered: list[CandidateLead] = []
    for c in candidates:
        c_email = c.email.strip().lower()
        c_domain = c.website.split("://")[-1].split("/")[0].removeprefix("www.").lower() if c.website else ""
        c_name = c.company_name.strip().lower()

        if c_email and c_email in existing_emails:
            continue
        if c_domain and c_domain in existing_domains:
            continue
        if c_name and c_name in existing_names:
            continue

        filtered.append(c)
        # Also guard against duplicates within this same batch.
        if c_email:
            existing_emails.add(c_email)
        if c_domain:
            existing_domains.add(c_domain)
        if c_name:
            existing_names.add(c_name)

    return filtered


def _is_bounce(sender: str, subject: str) -> bool:
    """Detect non-delivery reports / bounce messages."""
    s = sender.lower()
    subj = subject.lower()
    if any(p in s for p in ("mailer-daemon", "postmaster", "mail delivery", "microsoftexchange")):
        return True
    return any(
        ind in subj
        for ind in (
            "undeliverable", "delivery has failed", "delivery failure",
            "mail delivery failed", "delivery status notification", "failure notice",
            "returned mail", "could not be delivered", "退信", "无法投递",
        )
    )


def _suppress_bounced_recipients(body: str, email_to_lead: dict[str, dict[str, object]]) -> list[str]:
    """Find any of our lead addresses inside a bounce body and suppress them."""
    lowered = body.lower()
    hits: list[str] = []
    for email in email_to_lead:
        if email and email in lowered:
            db.add_suppression(email, reason="bounce", source="ndr")
            db.add_audit(actor="system", action="suppression.add", target_type="email", target_id=email, detail="bounce")
            hits.append(email)
    return hits


def _is_auto_reply(subject: str, body: str) -> bool:
    """Detect auto-reply / out-of-office emails."""
    lowered = (subject + " " + body[:500]).lower()
    indicators = [
        "automatic reply",
        "out of office",
        "out of the office",
        "auto-reply",
        "auto reply",
        "vacation",
        "unavailable",
        "will not have access to email",
    ]
    return any(ind in lowered for ind in indicators)


def _status_for_intent(intent: str, requires_human: bool) -> str:
    if requires_human:
        return "human_review"
    if intent == "interested":
        return "interested"
    if intent == "rejected":
        return "rejected"
    return "needs_review"


app = create_app()
