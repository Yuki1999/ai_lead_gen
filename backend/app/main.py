from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
import asyncio
import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import db
from app.auth import (
    require_auth, require_permission, verify_credentials, create_access_token,
    decode_access_token, check_password, hash_password, security_scheme,
    service_token,
)

_logger = logging.getLogger("medbot")
from app.agent_config import agent_config_status, test_agent_connection, update_agent_config
from app.agent_proxy import AgentProxyError, forward_agent_chat, forward_agent_chat_stream, get_agent_base_url, get_agent_headers
from app.email_service import (
    fetch_inbox_replies,
    is_configured as email_is_configured,
    list_attachments,
    send_batch,
    send_email,
    test_connection,
)
from app.product import extract_product_profile
from app.schemas import (
    AgentConfigResponse,
    AgentConfigUpdate,
    AgentChatRequest,
    AgentChatResponse,
    AgentTestConnectionRequest,
    AgentTestConnectionResponse,
    AuthVerifyResponse,
    EmailTestRequest,
    LeadCreateRequest,
    LeadUpdateRequest,
    LoginRequest,
    LoginResponse,
    OutreachRequest,
    ReplyAnalysisRequest,
    SearchRequest,
    WebFetchRequest,
    WebSearchRequest,
)
from app.services import (
    DEFAULT_EMAIL_TEMPLATE,
    DEFAULT_SCORING_RULES,
    CandidateLead,
    RenderedEmail,
    analyze_reply,
    generate_candidate_leads,
    generate_followup,
    render_email,
)
from app.web_search import discover_real_prospects, fetch_source_preview, search_web


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        from app.auth import validate_secrets
        validate_secrets()
        db.init_db()
        bg_task = asyncio.create_task(_auto_sync_loop())
        try:
            yield
        finally:
            bg_task.cancel()
            try:
                await bg_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(
        title="Medbot Overseas Distributor Pipeline",
        version="0.1.0",
        description="API for overseas distributor prospecting, outreach record generation, and reply triage.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Auth middleware ──────────────────────────────────

    _PUBLIC_PATHS = {"/health", "/auth/login", "/docs", "/redoc", "/openapi.json"}
    _AUTH_DISABLED = os.getenv("MEDBOT_AUTH_DISABLED", "").lower() in ("1", "true", "yes")

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        from fastapi.responses import JSONResponse  # local import for middleware

        # Skip auth if disabled (e.g., for tests)
        if _AUTH_DISABLED:
            return await call_next(request)

        # Allow CORS preflight requests without authentication
        if request.method == "OPTIONS":
            return await call_next(request)

        # Allow public paths without authentication
        path = request.url.path
        if path in _PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi"):
            return await call_next(request)

        # Perform auth check
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]  # strip "Bearer "

        # Check static service token (for agent-to-backend calls)
        if token == service_token():
            return await call_next(request)

        # Check JWT
        payload = decode_access_token(token)
        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics() -> dict[str, int]:
        return db.metrics()

    # ── Auth ────────────────────────────────────────────

    @app.post("/auth/login", response_model=LoginResponse)
    def login(request: LoginRequest) -> dict[str, object]:
        user = verify_credentials(request.username, request.password)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="用户名或密码错误",
            )
        token = create_access_token(
            user_id=int(user["user_id"]),
            username=str(user["username"]),
        )
        permissions = list(user["permissions"]) if isinstance(user["permissions"], list) else []
        return {
            "access_token": token,
            "token_type": "bearer",
            "username": str(user["username"]),
            "permissions": permissions,
        }

    @app.get("/auth/verify", response_model=AuthVerifyResponse)
    def verify_token(
        credentials=Depends(security_scheme),
    ) -> dict[str, object]:
        """Verify the current token and return the freshest permission list.

        Permissions are read from the DB on every call (subject to the 30s
        in-process cache) so the frontend always sees the post-edit state.
        """
        from app.auth import get_user_permissions
        if credentials is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        token = credentials.credentials
        if token == service_token():
            return {"username": "agent-service", "valid": True, "permissions": ["*"]}
        payload = decode_access_token(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        username = payload.get("sub")
        uid = payload.get("uid")
        if not isinstance(username, str) or not isinstance(uid, int):
            raise HTTPException(status_code=401, detail="Invalid token")
        perms = get_user_permissions(uid)
        if perms is None:
            raise HTTPException(status_code=401, detail="账号不存在或已被删除")
        return {"username": username, "valid": True, "permissions": perms}

    # ── Permission registry ─────────────────────────────

    @app.get("/permissions/registry")
    def permission_registry(_: str = Depends(require_auth)) -> dict[str, object]:
        """Return the canonical permission catalog (keys, groups, labels, presets).

        The frontend pulls this at boot to populate the role editor — there is
        no hard-coded permission list in the UI.
        """
        from app.permissions import registry_payload
        return registry_payload()

    # ── Product ─────────────────────────────────────────

    @app.get("/product/profile")
    def product_profile(_: str = Depends(require_permission("settings:read"))) -> dict[str, object]:
        return extract_product_profile().to_dict()

    @app.post("/agent/chat", response_model=AgentChatResponse)
    def agent_chat(request: AgentChatRequest,
                   username: str = Depends(require_permission("agent:chat"))) -> dict[str, object]:
        try:
            return forward_agent_chat(request.model_dump())
        except AgentProxyError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.post("/agent/chat/stream")
    def agent_chat_stream(request: AgentChatRequest,
                          username: str = Depends(require_permission("agent:chat"))) -> StreamingResponse:
        try:
            stream = forward_agent_chat_stream(request.model_dump())
        except AgentProxyError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.get("/agent/sessions")
    def list_agent_sessions(_: str = Depends(require_permission("agent:chat"))) -> dict[str, object]:
        """Proxy session list from the agent sidecar."""
        try:
            import requests as req
            base = get_agent_base_url()
            headers = get_agent_headers()
            resp = req.get(f"{base}/sessions", headers=headers, timeout=10)
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=resp.text)
            return resp.json()
        except req.RequestException as exc:
            raise HTTPException(status_code=503, detail=f"Agent sidecar unavailable: {exc}")

    @app.delete("/agent/sessions/{session_id}")
    def delete_agent_session(session_id: str,
                             _: str = Depends(require_permission("agent:chat"))) -> dict[str, object]:
        """Proxy session deletion to the agent sidecar."""
        try:
            import requests as req
            base = get_agent_base_url()
            headers = get_agent_headers()
            resp = req.delete(f"{base}/sessions/{session_id}", headers=headers, timeout=10)
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=resp.text)
            return resp.json()
        except req.RequestException as exc:
            raise HTTPException(status_code=503, detail=f"Agent sidecar unavailable: {exc}")

    @app.get("/agent/config", response_model=AgentConfigResponse)
    def agent_config(_: str = Depends(require_permission("settings:read"))) -> dict[str, object]:
        return agent_config_status()

    @app.put("/agent/config", response_model=AgentConfigResponse)
    def save_agent_config(request: AgentConfigUpdate,
                          _: str = Depends(require_permission("settings:write"))) -> dict[str, object]:
        return update_agent_config(
            provider_name=request.provider_name,
            api_key=request.api_key,
            openai_api_key=request.openai_api_key,
            model_name=request.model_name,
            api_base_url=request.api_base_url,
            backend_base_url=request.backend_base_url,
        )

    @app.post("/agent/test-connection", response_model=AgentTestConnectionResponse)
    def agent_test_connection(request: AgentTestConnectionRequest,
                              _: str = Depends(require_permission("settings:write"))) -> dict[str, object]:
        return test_agent_connection(
            provider_name=request.provider_name,
            api_key=request.api_key,
            model_name=request.model_name,
            api_base_url=request.api_base_url,
        )

    @app.post("/leads/search", status_code=201)
    def search_leads(request: SearchRequest,
                     username: str = Depends(require_permission("leads:write"))) -> dict[str, object]:
        if request.real_search:
            candidates = discover_real_prospects(
                target_regions=request.target_regions,
                product_profile=extract_product_profile(),
                extra_keywords=request.product_keywords,
                max_results=request.max_results,
                require_email=request.require_email,
            )
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

    @app.post("/leads/batch", status_code=201)
    def batch_create_leads(request: list[LeadCreateRequest],
                           username: str = Depends(require_permission("leads:write"))) -> dict[str, object]:
        """Batch create leads (used by Agent to save discovered leads)."""
        created = []
        for item in request:
            lead = CandidateLead(
                company_name=item.company_name,
                region=item.region,
                country=item.country,
                website=item.website,
                contact_name=item.contact_name,
                email=item.email,
                category=item.category,
                match_reason=item.match_reason,
                source=item.source,
                score=50,
                status="new",
                notes="Agent discovered",
            )
            created.append(db.insert_lead(lead))
        return {"created_count": len(created), "leads": created}

    @app.post("/leads", status_code=201)
    def create_lead(request: LeadCreateRequest,
                    username: str = Depends(require_permission("leads:write"))) -> dict[str, object]:
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
            score=50,
            status="new",
            notes="",
        )
        return db.insert_lead(lead)

    @app.delete("/leads/{lead_id}")
    def delete_lead(lead_id: int,
                    username: str = Depends(require_permission("leads:write"))) -> dict[str, object]:
        """Delete a lead and its associated outreach events and reply analyses."""
        if not db.delete_lead(lead_id):
            raise HTTPException(status_code=404, detail="Lead not found")
        return {"ok": True, "deleted": lead_id}

    @app.post("/leads/batch-delete")
    def batch_delete_leads(request: dict[str, object],
                           username: str = Depends(require_permission("leads:write"))) -> dict[str, object]:
        """Delete multiple leads at once."""
        lead_ids = request.get("lead_ids", [])
        if not isinstance(lead_ids, list) or not lead_ids:
            raise HTTPException(status_code=400, detail="lead_ids required")
        deleted = 0
        for lid in lead_ids:
            if isinstance(lid, (int, float)) and db.delete_lead(int(lid)):
                deleted += 1
        return {"ok": True, "deleted": deleted}

    @app.get("/leads")
    def list_leads(
        username: str = Depends(require_permission("leads:read")),
        region: str | None = Query(default=None),
        status: str | None = Query(default=None),
        q: str | None = Query(default=None),
        sort: str = Query(default="id"),
        order: str = Query(default="desc"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        total = db.count_leads(region=region, status=status, q=q)
        leads = db.list_leads(region=region, status=status, q=q, sort=sort, order=order, limit=limit, offset=offset)
        return {"total": total, "leads": leads}

    @app.get("/sources/preview")
    def source_preview(
        url: str = Query(min_length=8),
        email: str = Query(default=""),
        _: str = Depends(require_permission("leads:read")),
    ) -> dict[str, object]:
        try:
            return fetch_source_preview(url=url, email=email)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/web/search")
    def web_search(request: WebSearchRequest,
                   _: str = Depends(require_permission("agent:chat"))) -> dict[str, object]:
        results = search_web(request.query, limit=request.max_results)
        return {
            "query": request.query,
            "results": [asdict(result) for result in results],
        }

    @app.post("/web/fetch")
    def web_fetch(request: WebFetchRequest,
                  _: str = Depends(require_permission("agent:chat"))) -> dict[str, object]:
        try:
            return fetch_source_preview(url=request.url, email=request.email)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/leads/{lead_id}/history")
    def lead_history(lead_id: int,
                     _: str = Depends(require_permission("leads:read"))) -> dict[str, object]:
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

    @app.get("/leads/{lead_id}")
    def get_lead(lead_id: int,
                 _: str = Depends(require_permission("leads:read"))) -> dict[str, object]:
        lead = db.get_lead(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        return lead

    @app.patch("/leads/{lead_id}")
    def update_lead(lead_id: int, request: LeadUpdateRequest,
                    username: str = Depends(require_permission("leads:write"))) -> dict[str, object]:
        updated = db.update_lead(
            lead_id,
            company_name=request.company_name,
            region=request.region,
            country=request.country,
            website=request.website,
            contact_name=request.contact_name,
            email=request.email,
            category=request.category,
            match_reason=request.match_reason,
            source=request.source,
            score=request.score,
            status=request.status,
            notes=request.notes,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        return updated

    @app.post("/campaigns/custom-send", status_code=201)
    def custom_send(request: dict[str, object],
                    username: str = Depends(require_permission("outreach:send"))) -> dict[str, object]:
        """Send a single custom email (自拟定) to a lead — no template, user-written content."""
        lead_id = request.get("lead_id")
        subject = str(request.get("subject", "")).strip()
        body = str(request.get("body", "")).strip()
        attach_names = request.get("attachments") or []

        if not lead_id or not subject or not body:
            raise HTTPException(status_code=422, detail="lead_id, subject, body are required")

        lead = db.get_lead(int(lead_id))
        if lead is None:
            raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
        if not str(lead["email"]).strip():
            raise HTTPException(status_code=422, detail=f"Lead {lead_id} has no email")

        rendered = RenderedEmail(
            sent_to=str(lead["email"]),
            subject=subject,
            body=body,
            region=str(lead.get("region", "")),
        )

        send_enabled = email_is_configured()
        if send_enabled:
            send_result = send_email(
                to=rendered.sent_to, subject=rendered.subject, body=rendered.body,
                attachments=list(attach_names) if attach_names else None,
            )
            if send_result.success:
                event = db.insert_outreach_event(
                    int(lead_id), rendered, status="sent",
                    message_id=send_result.message_id, source="custom",
                )
            else:
                event = db.insert_outreach_event(
                    int(lead_id), rendered, status="send_failed", source="custom",
                )
        else:
            event = db.insert_outreach_event(int(lead_id), rendered, status="draft", source="custom")

        return {
            "ok": True,
            "sent_count": 1,
            "events": [event],
            "email_delivery": send_enabled,
            "source": "custom",
            "note": "Custom email sent" if send_enabled else "Custom email saved as draft",
        }

    @app.post("/campaigns/outreach-records", status_code=201)
    def create_outreach_records(request: OutreachRequest,
                                username: str = Depends(require_permission("outreach:send"))) -> dict[str, object]:
        return _create_outreach_records(request, source=request.source)

    @app.post("/campaigns/outreach-preview")
    def preview_outreach(request: OutreachRequest,
                         _: str = Depends(require_permission("outreach:send"))) -> dict[str, object]:
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

    @app.get("/campaigns/drafts")
    def list_drafts(_: str = Depends(require_permission("outreach:approve"))) -> dict[str, object]:
        """List all pending draft outreach events (created by Agent, awaiting approval)."""
        drafts = db.list_draft_events()
        return {"total": len(drafts), "drafts": drafts}

    @app.post("/campaigns/drafts/{event_id}/approve")
    def approve_draft(event_id: int,
                      username: str = Depends(require_permission("outreach:approve"))) -> dict[str, object]:
        """Approve a draft and send the email via EWS."""
        event = db.approve_outreach_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Actually send the email
        if email_is_configured():
            result = send_email(
                to=str(event["sent_to"]),
                subject=str(event["subject"]),
                body=str(event["body"]),
            )
            if result.success:
                db.approve_outreach_event(event_id)  # already approved, just re-read
                return {"ok": True, "event": event, "sent": True}
            else:
                # Mark as send_failed
                with db.connect() as conn:
                    conn.execute(
                        "UPDATE outreach_events SET status = 'send_failed' WHERE id = ?",
                        (event_id,),
                    )
                return {"ok": False, "event": event, "sent": False, "error": result.error}

        return {"ok": True, "event": event, "sent": False, "note": "Email not configured"}

    @app.post("/campaigns/drafts/{event_id}/reject")
    def reject_draft(event_id: int,
                     _: str = Depends(require_permission("outreach:approve"))) -> dict[str, object]:
        """Reject a draft without sending."""
        event = db.reject_outreach_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Draft not found")
        return {"ok": True, "event": event}

    @app.post("/campaigns/drafts/approve-all")
    def approve_all_drafts(_: str = Depends(require_permission("outreach:approve"))) -> dict[str, object]:
        """Approve all pending drafts and send them."""
        drafts = db.list_draft_events()
        results: list[dict[str, object]] = []
        for draft in drafts:
            event_id = int(draft["id"])
            db.approve_outreach_event(event_id)
            sent = False
            error = ""
            if email_is_configured():
                result = send_email(
                    to=str(draft["sent_to"]),
                    subject=str(draft["subject"]),
                    body=str(draft["body"]),
                )
                sent = result.success
                error = result.error
                if not sent:
                    with db.connect() as conn:
                        conn.execute(
                            "UPDATE outreach_events SET status = 'send_failed' WHERE id = ?",
                            (event_id,),
                        )
            results.append({
                "id": event_id,
                "company": draft.get("company_name", ""),
                "email": draft["sent_to"],
                "sent": sent,
                "error": error,
            })
        return {"ok": True, "total": len(results), "results": results}

    @app.post("/email/test")
    def email_test(request: EmailTestRequest,
                   _: str = Depends(require_permission("settings:write"))) -> dict[str, object]:
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

    @app.get("/attachments")
    def get_attachments(_: str = Depends(require_permission("outreach:send"))) -> dict[str, object]:
        """List available standard attachment files for follow-up emails."""
        from app.email_service import ATTACHMENTS_DIR
        return {"files": list_attachments(), "dir": str(ATTACHMENTS_DIR)}

    @app.get("/email/status")
    def email_status(_: str = Depends(require_permission("settings:read"))) -> dict[str, object]:
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

    @app.post("/campaigns/send-demo", status_code=201, include_in_schema=False)
    def send_legacy_demo(request: OutreachRequest,
                         _: str = Depends(require_permission("outreach:send"))) -> dict[str, object]:
        return _create_outreach_records(request, source="manual")

    def _create_outreach_records(
        request: OutreachRequest,
        *,
        source: str = "manual",
    ) -> dict[str, object]:
        events = []
        send_enabled = email_is_configured()
        send_errors: list[dict[str, object]] = []

        # Agent source: NEVER send, always draft
        should_send = send_enabled and source != "agent"

        for lead_id in request.lead_ids:
            lead = db.get_lead(lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
            if not str(lead["email"]).strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"Lead {lead_id} has no discovered email address",
                )
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
                send_result = send_email(
                    to=rendered.sent_to,
                    subject=rendered.subject,
                    body=rendered.body,
                )
                if send_result.success:
                    event = db.insert_outreach_event(
                        lead_id, rendered, status="sent",
                        message_id=send_result.message_id, source=source,
                    )
                else:
                    event = db.insert_outreach_event(
                        lead_id, rendered, status="send_failed", source=source,
                    )
                    send_errors.append({
                        "lead_id": lead_id,
                        "email": rendered.sent_to,
                        "error": send_result.error,
                    })
            else:
                status = "draft" if source == "agent" else "recorded"
                event = db.insert_outreach_event(lead_id, rendered, status=status, source=source)

            events.append(event)

        response: dict[str, object] = {
            "sent_count": len(events),
            "events": events,
            "email_delivery": should_send,
            "source": source,
        }
        if source == "agent":
            response["note"] = "Agent-created outreach saved as draft. Review and approve to send."
        if send_errors:
            response["send_errors"] = send_errors
        return response

    @app.post("/replies/sync", status_code=201)
    def sync_inbox_replies(username: str = Depends(require_permission("replies:sync"))) -> dict[str, object]:
        """Fetch real replies from Exchange inbox and match them to leads."""
        if not email_is_configured():
            raise HTTPException(
                status_code=503,
                detail="Email not configured.",
            )

        inbox_replies = fetch_inbox_replies(max_count=30)
        email_to_lead, domain_to_leads = _build_lead_index()

        synced: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []

        for reply in inbox_replies:
            result = _process_inbox_reply(reply, email_to_lead, domain_to_leads)
            if result is None:
                continue
            if result.pop("skipped", False):
                skipped.append(result)
            else:
                synced.append(result)

        return {
            "total_inbox": len(inbox_replies),
            "synced": len(synced),
            "skipped": len(skipped),
            "items": synced,
            "skipped_items": skipped[:10],
        }

    @app.post("/replies/analyze", status_code=201)
    def analyze_reply_endpoint(request: ReplyAnalysisRequest,
                               username: str = Depends(require_permission("replies:analyze"))) -> dict[str, object]:
        if request.lead_id is not None and db.get_lead(request.lead_id) is None:
            raise HTTPException(status_code=404, detail="Lead not found")

        analysis = analyze_reply(request.reply_text)
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

    @app.post("/replies/followup", status_code=201)
    def generate_followup_endpoint(request: ReplyAnalysisRequest,
                                   _: str = Depends(require_permission("replies:analyze"))) -> dict[str, object]:
        """Generate a follow-up email draft based on a customer reply."""
        lead_id = request.lead_id
        lead = db.get_lead(lead_id) if lead_id else None
        if lead_id is not None and lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")

        candidate = _lead_from_record(lead) if lead else CandidateLead(
            company_name="Unknown", region="", country="", website="",
            contact_name="", email="", category="", match_reason="",
            source="", score=0, status="new", notes="",
        )

        result = generate_followup(candidate, request.reply_text)
        if result is None:
            raise HTTPException(status_code=503, detail="AI follow-up generation unavailable")

        return {"subject": result.subject, "body": result.body, "sent_to": result.sent_to}

    @app.get("/settings")
    def get_settings(username: str = Depends(require_permission("settings:read"))) -> dict[str, object]:
        """Return all settings including sync frequency, agent config, and email."""
        settings = db.get_all_settings()
        return {
            "sync_enabled": settings.get("sync_enabled", "false") == "true",
            "sync_interval_minutes": int(settings.get("sync_interval_minutes", "0") or "0"),
            "agent_provider": settings.get("agent_provider", ""),
            "agent_model": settings.get("agent_model", ""),
            "has_agent_key": bool(settings.get("agent_key", "")),
            "agent_key_preview": _mask_key(settings.get("agent_key", "")),
            "api_base_url": settings.get("api_base_url", ""),
            "backend_base_url": settings.get("backend_base_url", "http://localhost:8000"),
            "email_server": settings.get("email_server", "mail.microport.com.cn"),
            "email_user": settings.get("email_user", ""),
            "has_email_password": bool(settings.get("email_password", "")),
            "email_template": settings.get("email_template", "") or DEFAULT_EMAIL_TEMPLATE,
            "scoring_rules": settings.get("scoring_rules", "") or DEFAULT_SCORING_RULES,
        }

    @app.put("/settings")
    def save_settings(request: dict[str, object],
                      username: str = Depends(require_permission("settings:write"))) -> dict[str, object]:
        """Save settings. Accepts partial updates. Applies email config immediately."""
        for key in (
            "sync_enabled", "sync_interval_minutes",
            "agent_provider", "agent_model", "agent_key", "api_base_url", "backend_base_url",
            "email_server", "email_user", "email_password", "email_template", "scoring_rules",
        ):
            if key in request:
                val = request[key]
                db.set_setting(key, str(val).lower() if isinstance(val, bool) else str(val))

        # Reload email config so changes take effect immediately
        from app.email_service import reload_config
        reload_config()

        # Sync scoring rules to skill file
        _sync_scoring_rules_to_skill()

        return get_settings()

    # ── User & Role Management ──────────────────────────

    @app.get("/users")
    def list_users(username: str = Depends(require_permission("users:manage"))) -> dict[str, object]:
        return {"users": db.list_users()}

    @app.post("/users", status_code=201)
    def create_user(request: dict[str, object],
                    username: str = Depends(require_permission("users:manage"))) -> dict[str, object]:
        uname = str(request.get("username", "")).strip()
        password = str(request.get("password", "")).strip()
        role_id = request.get("role_id")
        if not uname or not password or not role_id:
            raise HTTPException(status_code=422, detail="username, password, role_id are required")
        pw_hash = hash_password(password)
        user = db.create_user(uname, pw_hash, int(role_id))
        if user is None:
            raise HTTPException(status_code=409, detail="用户名已存在")
        return user

    @app.put("/users/{user_id}")
    def update_user(user_id: int, request: dict[str, object],
                    username: str = Depends(require_permission("users:manage"))) -> dict[str, object]:
        kwargs: dict = {}
        if "username" in request:
            kwargs["username"] = str(request["username"]).strip()
        if "password" in request and str(request["password"]).strip():
            kwargs["password_hash"] = hash_password(str(request["password"]).strip())
        if "role_id" in request:
            kwargs["role_id"] = int(request["role_id"])
        user = db.update_user(user_id, **kwargs)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    @app.delete("/users/{user_id}")
    def delete_user(user_id: int,
                    username: str = Depends(require_permission("users:manage"))) -> dict[str, object]:
        if not db.delete_user(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        return {"ok": True, "deleted": user_id}

    @app.get("/roles")
    def list_roles(username: str = Depends(require_permission("users:manage"))) -> dict[str, object]:
        return {"roles": db.list_roles()}

    @app.post("/roles", status_code=201)
    def create_role(request: dict[str, object],
                    username: str = Depends(require_permission("users:manage"))) -> dict[str, object]:
        name = str(request.get("name", "")).strip()
        permissions = request.get("permissions") or []
        if not name:
            raise HTTPException(status_code=422, detail="name is required")
        role = db.create_role(name, list(permissions))
        if role is None:
            raise HTTPException(status_code=409, detail="角色名已存在")
        return role

    @app.put("/roles/{role_id}")
    def update_role(role_id: int, request: dict[str, object],
                    username: str = Depends(require_permission("users:manage"))) -> dict[str, object]:
        kwargs: dict = {}
        if "name" in request:
            kwargs["name"] = str(request["name"]).strip()
        if "permissions" in request:
            kwargs["permissions"] = list(request["permissions"])
        role = db.update_role(role_id, **kwargs)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        return role

    @app.delete("/roles/{role_id}")
    def delete_role(role_id: int,
                    username: str = Depends(require_permission("users:manage"))) -> dict[str, object]:
        if not db.delete_role(role_id):
            raise HTTPException(status_code=404, detail="Role not found or cannot delete admin")
        return {"ok": True, "deleted": role_id}

    return app


def _skill_scoring_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "skills" / "overseas-distributor-prospecting" / "scoring-rules.md"


def _sync_scoring_rules_to_skill() -> None:
    """Write the current scoring_rules setting to the agent skill directory."""
    rules = db.get_setting("scoring_rules") or DEFAULT_SCORING_RULES
    path = _skill_scoring_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rules, encoding="utf-8")


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


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
                email_to_lead, domain_to_leads = _build_lead_index()
                synced = 0
                for reply in replies:
                    result = _process_inbox_reply(reply, email_to_lead, domain_to_leads)
                    if result is not None and not result.get("skipped"):
                        synced += 1
                if synced:
                    _logger.info("Auto-sync: synced %d new replies", synced)

            sleep_seconds = max(120, interval * 60) if interval > 0 else 300
            await asyncio.sleep(sleep_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("Auto-sync error, retrying in 5 min")
            await asyncio.sleep(300)


def _build_lead_index() -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, object]]]]:
    """Build email→lead and domain→leads lookup tables from all leads."""
    all_leads = db.list_leads()
    email_to_lead: dict[str, dict[str, object]] = {}
    domain_to_leads: dict[str, list[dict[str, object]]] = {}

    for lead in all_leads:
        lead_email = str(lead.get("email", "")).strip().lower()
        if not lead_email:
            continue
        email_to_lead[lead_email] = lead
        domain = lead_email.split("@")[-1] if "@" in lead_email else ""
        if domain:
            domain_to_leads.setdefault(domain, []).append(lead)

    return email_to_lead, domain_to_leads


def _match_sender_to_lead(
    sender_email: str,
    email_to_lead: dict[str, dict[str, object]],
    domain_to_leads: dict[str, list[dict[str, object]]],
) -> dict[str, object] | None:
    """Match a sender email to a lead by exact email, then domain fallback."""
    sender = sender_email.lower()
    matched = email_to_lead.get(sender)
    if matched is not None:
        return matched
    sender_domain = sender.split("@")[-1] if "@" in sender else ""
    if sender_domain:
        candidates = domain_to_leads.get(sender_domain, [])
        if len(candidates) >= 1:
            return candidates[0]
    return None


def _process_inbox_reply(
    reply: object,  # InboxReply from email_service
    email_to_lead: dict[str, dict[str, object]],
    domain_to_leads: dict[str, list[dict[str, object]]],
) -> dict[str, object] | None:
    """Process a single inbox reply: match, dedup, analyze, insert, update lead.

    Returns a synced-item dict on success, or a skipped-item dict (with 'skipped': True) if no match / already synced.
    """
    sender = reply.sender_email.lower()

    # 1. Match sender to a lead
    matched_lead = _match_sender_to_lead(sender, email_to_lead, domain_to_leads)
    if matched_lead is None:
        return {"sender": sender, "subject": reply.subject, "reason": "no matching lead", "skipped": True}

    lead_id = int(matched_lead["id"])

    # 2. Dedup: skip if already synced
    if _reply_already_synced(reply.message_id):
        return {"sender": sender, "subject": reply.subject, "reason": "already synced", "skipped": True}

    # 3. Analyze
    is_auto = _is_auto_reply(reply.subject, reply.body)
    analysis = analyze_reply(reply.body)

    # 4. Update lead status (skip for auto-replies)
    if not is_auto:
        db.update_lead(lead_id, status=_status_for_intent(analysis.intent, analysis.requires_human))

    # 5. Persist analysis
    record = db.insert_reply_analysis(
        lead_id=lead_id,
        reply_text=reply.body,
        analysis=analysis,
        message_id=reply.message_id,
    )

    return {
        "lead_id": lead_id,
        "company": matched_lead["company_name"],
        "sender": sender,
        "subject": reply.subject,
        "intent": analysis.intent,
        "confidence": analysis.confidence,
        "auto_reply": is_auto,
        "analysis_id": record["id"],
    }


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

    return filtered


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
