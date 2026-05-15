from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import db
from app.agent_config import agent_config_status, update_agent_config
from app.agent_proxy import AgentProxyError, forward_agent_chat, forward_agent_chat_stream
from app.product import extract_product_profile
from app.schemas import (
    AgentConfigResponse,
    AgentConfigUpdate,
    AgentChatRequest,
    AgentChatResponse,
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
        yield

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

    @app.patch("/leads/{lead_id}")
    def update_lead(lead_id: int, request: LeadUpdateRequest) -> dict[str, object]:
        updated = db.update_lead(lead_id, status=request.status, notes=request.notes)
        if updated is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        return updated

    @app.post("/campaigns/outreach-records", status_code=201)
    def create_outreach_records(request: OutreachRequest) -> dict[str, object]:
        return _create_outreach_records(request)

    @app.post("/campaigns/send-demo", status_code=201, include_in_schema=False)
    def send_legacy_demo(request: OutreachRequest) -> dict[str, object]:
        return _create_outreach_records(request)

    def _create_outreach_records(request: OutreachRequest) -> dict[str, object]:
        events = []
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
            events.append(db.insert_outreach_event(lead_id, rendered))
        return {"sent_count": len(events), "events": events}

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

    return app


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


def _status_for_intent(intent: str, requires_human: bool) -> str:
    if requires_human:
        return "human_review"
    if intent == "interested":
        return "interested"
    if intent == "rejected":
        return "rejected"
    return "needs_review"


app = create_app()
