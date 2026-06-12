from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
import asyncio
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import db

_logger = logging.getLogger("medbot")
from app.agent_config import agent_config_status, update_agent_config
from app.agent_proxy import AgentProxyError, forward_agent_chat, forward_agent_chat_stream
from app.email_service import (
    fetch_inbox_replies,
    is_configured as email_is_configured,
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
    EmailTestRequest,
    LeadUpdateRequest,
    OutreachRequest,
    ReplyAnalysisRequest,
    SearchRequest,
    WebFetchRequest,
    WebSearchRequest,
)
from app.services import (
    CandidateLead,
    analyze_reply,
    generate_candidate_leads,
    render_email,
)
from app.web_search import discover_real_prospects, fetch_source_preview, search_web


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics() -> dict[str, int]:
        return db.metrics()

    @app.get("/product/profile")
    def product_profile() -> dict[str, object]:
        return extract_product_profile().to_dict()

    @app.post("/agent/chat", response_model=AgentChatResponse)
    def agent_chat(request: AgentChatRequest) -> dict[str, object]:
        try:
            return forward_agent_chat(request.model_dump())
        except AgentProxyError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.post("/agent/chat/stream")
    def agent_chat_stream(request: AgentChatRequest) -> StreamingResponse:
        try:
            stream = forward_agent_chat_stream(request.model_dump())
        except AgentProxyError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.get("/agent/config", response_model=AgentConfigResponse)
    def agent_config() -> dict[str, object]:
        return agent_config_status()

    @app.put("/agent/config", response_model=AgentConfigResponse)
    def save_agent_config(request: AgentConfigUpdate) -> dict[str, object]:
        return update_agent_config(
            provider_name=request.provider_name,
            api_key=request.api_key,
            openai_api_key=request.openai_api_key,
            model_name=request.model_name,
            backend_base_url=request.backend_base_url,
        )

    @app.post("/leads/search", status_code=201)
    def search_leads(request: SearchRequest) -> dict[str, object]:
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
        saved = [db.insert_lead(candidate) for candidate in candidates]
        return {"created_count": len(saved), "leads": saved}

    @app.get("/leads")
    def list_leads(
        region: str | None = Query(default=None),
        status: str | None = Query(default=None),
        q: str | None = Query(default=None),
    ) -> dict[str, object]:
        leads = db.list_leads(region=region, status=status, q=q)
        return {"total": len(leads), "leads": leads}

    @app.get("/sources/preview")
    def source_preview(
        url: str = Query(min_length=8),
        email: str = Query(default=""),
    ) -> dict[str, object]:
        try:
            return fetch_source_preview(url=url, email=email)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/web/search")
    def web_search(request: WebSearchRequest) -> dict[str, object]:
        results = search_web(request.query, limit=request.max_results)
        return {
            "query": request.query,
            "results": [asdict(result) for result in results],
        }

    @app.post("/web/fetch")
    def web_fetch(request: WebFetchRequest) -> dict[str, object]:
        try:
            return fetch_source_preview(url=request.url, email=request.email)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/leads/{lead_id}/history")
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

    @app.patch("/leads/{lead_id}")
    def update_lead(lead_id: int, request: LeadUpdateRequest) -> dict[str, object]:
        updated = db.update_lead(lead_id, status=request.status, notes=request.notes)
        if updated is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        return updated

    @app.post("/campaigns/outreach-records", status_code=201)
    def create_outreach_records(request: OutreachRequest) -> dict[str, object]:
        return _create_outreach_records(request)

    @app.post("/email/test")
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

    @app.get("/email/status")
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

    @app.post("/campaigns/send-demo", status_code=201, include_in_schema=False)
    def send_legacy_demo(request: OutreachRequest) -> dict[str, object]:
        return _create_outreach_records(request)

    def _create_outreach_records(request: OutreachRequest) -> dict[str, object]:
        events = []
        send_enabled = email_is_configured()
        send_errors: list[dict[str, object]] = []

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

            # Record the outreach event
            if send_enabled:
                send_result = send_email(
                    to=rendered.sent_to,
                    subject=rendered.subject,
                    body=rendered.body,
                )
                if send_result.success:
                    event = db.insert_outreach_event(
                        lead_id, rendered, status="sent", message_id=send_result.message_id
                    )
                else:
                    event = db.insert_outreach_event(
                        lead_id, rendered, status="send_failed"
                    )
                    send_errors.append({
                        "lead_id": lead_id,
                        "email": rendered.sent_to,
                        "error": send_result.error,
                    })
            else:
                event = db.insert_outreach_event(lead_id, rendered)

            events.append(event)

        response: dict[str, object] = {
            "sent_count": len(events),
            "events": events,
            "email_delivery": send_enabled,
        }
        if send_errors:
            response["send_errors"] = send_errors
        return response

    @app.post("/replies/sync", status_code=201)
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

        for reply in inbox_replies:
            sender = reply.sender_email.lower()

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
                analysis = analyze_reply("Auto-reply received")
                # Don't change lead status for auto-replies
            else:
                analysis = analyze_reply(reply.body)
                db.update_lead(
                    lead_id,
                    status=_status_for_intent(analysis.intent, analysis.requires_human),
                )
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
            "items": synced,
            "skipped_items": skipped[:10],
        }

    @app.post("/replies/analyze", status_code=201)
    def analyze_reply_endpoint(request: ReplyAnalysisRequest) -> dict[str, object]:
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

    @app.get("/settings")
    def get_settings() -> dict[str, object]:
        """Return all settings including sync frequency and agent config."""
        settings = db.get_all_settings()
        return {
            "sync_enabled": settings.get("sync_enabled", "false") == "true",
            "sync_interval_minutes": int(settings.get("sync_interval_minutes", "0") or "0"),
            "agent_provider": settings.get("agent_provider", ""),
            "agent_model": settings.get("agent_model", ""),
            "has_agent_key": bool(settings.get("agent_key", "")),
            "agent_key_preview": _mask_key(settings.get("agent_key", "")),
            "backend_base_url": settings.get("backend_base_url", "http://localhost:8000"),
        }

    @app.put("/settings")
    def save_settings(request: dict[str, object]) -> dict[str, object]:
        """Save settings. Accepts partial updates."""
        for key in (
            "sync_enabled", "sync_interval_minutes",
            "agent_provider", "agent_model", "agent_key", "backend_base_url",
        ):
            if key in request:
                val = request[key]
                db.set_setting(key, str(val).lower() if isinstance(val, bool) else str(val))

        return get_settings()

    return app


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
                synced = 0
                for reply in replies:
                    if not _reply_already_synced(reply.message_id):
                        matched = _match_reply_to_lead(reply.sender_email)
                        if matched:
                            is_auto = _is_auto_reply(reply.subject, reply.body)
                            analysis = analyze_reply(reply.body)
                            db.insert_reply_analysis(
                                lead_id=int(matched["id"]),
                                reply_text=reply.body,
                                analysis=analysis,
                                message_id=reply.message_id,
                            )
                            if not is_auto:
                                db.update_lead(
                                    int(matched["id"]),
                                    status=_status_for_intent(analysis.intent, analysis.requires_human),
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
