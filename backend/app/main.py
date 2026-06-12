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
    LeadCreateRequest,
    LeadUpdateRequest,
    OutreachRequest,
    ReplyAnalysisRequest,
    SearchRequest,
    WebFetchRequest,
    WebSearchRequest,
)
from app.services import (
    CandidateLead,
    RenderedEmail,
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

        # Dedup against existing leads
        candidates = _filter_existing_leads(candidates)

        saved = [db.insert_lead(candidate) for candidate in candidates]
        return {"created_count": len(saved), "leads": saved}

    @app.post("/leads/batch", status_code=201)
    def batch_create_leads(request: list[LeadCreateRequest]) -> dict[str, object]:
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
            score=50,
            status="new",
            notes="",
        )
        return db.insert_lead(lead)

    @app.delete("/leads/{lead_id}")
    def delete_lead(lead_id: int) -> dict[str, object]:
        """Delete a lead and its associated outreach events and reply analyses."""
        if not db.delete_lead(lead_id):
            raise HTTPException(status_code=404, detail="Lead not found")
        return {"ok": True, "deleted": lead_id}

    @app.post("/leads/batch-delete")
    def batch_delete_leads(request: dict[str, object]) -> dict[str, object]:
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
        region: str | None = Query(default=None),
        status: str | None = Query(default=None),
        q: str | None = Query(default=None),
        sort: str = Query(default="id"),
        order: str = Query(default="desc"),
    ) -> dict[str, object]:
        leads = db.list_leads(region=region, status=status, q=q, sort=sort, order=order)
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
        return _create_outreach_records(request, source=request.source)

    @app.post("/campaigns/outreach-preview")
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

    @app.get("/campaigns/drafts")
    def list_drafts() -> dict[str, object]:
        """List all pending draft outreach events (created by Agent, awaiting approval)."""
        drafts = db.list_draft_events()
        return {"total": len(drafts), "drafts": drafts}

    @app.post("/campaigns/drafts/{event_id}/approve")
    def approve_draft(event_id: int) -> dict[str, object]:
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
    def reject_draft(event_id: int) -> dict[str, object]:
        """Reject a draft without sending."""
        event = db.reject_outreach_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Draft not found")
        return {"ok": True, "event": event}

    @app.post("/campaigns/drafts/approve-all")
    def approve_all_drafts() -> dict[str, object]:
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
        """Return all settings including sync frequency, agent config, and email."""
        settings = db.get_all_settings()
        return {
            "sync_enabled": settings.get("sync_enabled", "false") == "true",
            "sync_interval_minutes": int(settings.get("sync_interval_minutes", "0") or "0"),
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
    def save_settings(request: dict[str, object]) -> dict[str, object]:
        """Save settings. Accepts partial updates. Applies email config immediately."""
        for key in (
            "sync_enabled", "sync_interval_minutes",
            "agent_provider", "agent_model", "agent_key", "backend_base_url",
            "email_server", "email_user", "email_password",
        ):
            if key in request:
                val = request[key]
                db.set_setting(key, str(val).lower() if isinstance(val, bool) else str(val))

        # Reload email config so changes take effect immediately
        from app.email_service import reload_config
        reload_config()

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
