from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient


def _authenticate(client: TestClient, username: str = "admin", password: str = "admin123") -> None:
    """Log in and attach the bearer token to the client for subsequent requests."""
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    client.headers["Authorization"] = f"Bearer {resp.json()['token']}"


def _mock_reply_llm(monkeypatch, *, intent: str, requires_human: bool) -> None:
    """Configure a backend LLM key and stub the chat call so reply analysis (now
    LLM-only, no keyword fallback) returns a deterministic intent in tests."""
    import requests

    from app import db

    db.set_setting("agent_provider", "deepseek")
    db.set_setting("agent_key", "test-key")
    content = (
        '{"intent": "%s", "confidence": 0.9, "summary": "s", '
        '"next_action": "n", "requires_human": %s}'
        % (intent, "true" if requires_human else "false")
    )

    class _Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 12}}

    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp())


@contextmanager
def _client(tmp_path, monkeypatch, *, authenticate: bool = True):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    # Isolate the Pi sidecar env so the AI-content fallback can't resolve a real
    # key from the project's agent/.env during tests (keeps email/reply on the
    # deterministic template/keyword path unless a test sets a DB key itself).
    monkeypatch.setenv("AGENT_ENV_PATH", str(tmp_path / "agent.env"))
    from app.main import create_app

    with TestClient(create_app()) as client:
        if authenticate:
            _authenticate(client)
        yield client


def test_health_check(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_prospecting_persists_and_lists_leads(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Europe"],
                "product_keywords": ["surgical robot"],
                "max_results": 3,
                "real_search": False,
            },
        )
        listed = client.get("/leads", params={"region": "Europe"})

    assert created.status_code == 201
    assert created.json()["created_count"] == 3
    assert len(created.json()["leads"]) == 3
    assert listed.status_code == 200
    assert listed.json()["total"] == 3
    assert listed.json()["leads"][0]["region"] == "Europe"


def test_batch_create_leads_persists_agent_computed_score(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Agent Found Ortho",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@agent-found-ortho.example",
                    "score": 87,
                },
                {
                    "company_name": "Agent Found Ortho No Score",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@no-score.example",
                },
            ],
        )

    assert created.status_code == 201
    leads = created.json()["leads"]
    assert leads[0]["score"] == 87
    assert leads[1]["score"] == 50


def test_batch_create_leads_rejects_out_of_range_score(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Bad Score Co",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@bad-score.example",
                    "score": 150,
                }
            ],
        )

    assert response.status_code == 422


def test_batch_create_leads_derives_status_from_score_thresholds(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Strong Fit Co",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@strong-fit.example",
                    "score": 90,
                },
                {
                    "company_name": "Needs Review Co",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@needs-review.example",
                    "score": 45,
                },
                {
                    "company_name": "Weak Fit Co",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@weak-fit.example",
                    "score": 10,
                },
            ],
        )

    leads = created.json()["leads"]
    # Match level is decoupled from pipeline status: strong & weak both land in the
    # single "pending" (待确认) queue; only the reject band is auto-rejected. The
    # score's strength is surfaced via match_level, not the status.
    assert leads[0]["status"] == "pending"
    assert leads[0]["match_level"] == "strong"
    assert leads[1]["status"] == "pending"
    assert leads[1]["match_level"] == "weak"
    assert leads[2]["status"] == "rejected"
    assert leads[2]["match_level"] == "reject"


def test_auto_confirm_strong_promotes_strong_matches(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.put("/settings", json={"auto_confirm_strong": True})
        created = client.post(
            "/leads/batch",
            json=[
                {"company_name": "Strong Co", "region": "Europe", "country": "Germany",
                 "email": "s@strong.example", "score": 90},
                {"company_name": "Mid Co", "region": "Europe", "country": "Germany",
                 "email": "m@mid.example", "score": 65},
            ],
        )
    leads = created.json()["leads"]
    # With the toggle on, a strong match skips 待确认 and is auto-confirmed;
    # a medium match still waits for a human.
    assert leads[0]["status"] == "qualified"
    assert leads[1]["status"] == "pending"


def test_delete_lead_with_history_succeeds(tmp_path, monkeypatch):
    """Deleting a lead that has outreach history must remove the FK children
    first — PostgreSQL enforces the foreign keys, unlike the old SQLite."""
    with _client(tmp_path, monkeypatch) as client:
        lead = client.post("/leads", json={
            "company_name": "Del Co", "region": "Europe", "country": "Germany",
            "email": "del@co.example", "score": 85,
        }).json()
        lid = lead["id"]
        # Give the lead a child row (outreach event references leads.id).
        client.post("/campaigns/outreach-records", json={"lead_ids": [lid]})
        resp = client.delete(f"/leads/{lid}")
        assert resp.status_code == 200, resp.text
        assert all(l["id"] != lid for l in client.get("/leads").json()["leads"])


def test_leads_pagination_and_page_clamp(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post(
            "/leads/batch",
            json=[
                {"company_name": f"Page Co {i}", "region": "Europe", "country": "Germany",
                 "email": f"p{i}@page.example", "score": 70}
                for i in range(3)
            ],
        )
        # 3 leads, page_size 2 → 2 pages.
        p1 = client.get("/leads", params={"page_size": 2, "page": 1}).json()
        assert p1["total"] == 3
        assert p1["total_pages"] == 2
        assert p1["page"] == 1
        assert len(p1["leads"]) == 2

        p2 = client.get("/leads", params={"page_size": 2, "page": 2}).json()
        assert p2["page"] == 2
        assert len(p2["leads"]) == 1

        # Pages don't overlap (deterministic ordering).
        assert {l["id"] for l in p1["leads"]}.isdisjoint({l["id"] for l in p2["leads"]})

        # A stale / out-of-range page clamps back to the last valid page instead
        # of returning an empty page.
        p99 = client.get("/leads", params={"page_size": 2, "page": 99}).json()
        assert p99["page"] == 2
        assert len(p99["leads"]) == 1

        # page_size / page bounds are validated by the endpoint.
        assert client.get("/leads", params={"page_size": 0}).status_code == 422
        assert client.get("/leads", params={"page_size": 1000}).status_code == 422
        assert client.get("/leads", params={"page": 0}).status_code == 422


def test_followup_creates_draft_after_interval(tmp_path, monkeypatch):
    from app import db
    from app.main import _process_followups
    from app.services import RenderedEmail

    with _client(tmp_path, monkeypatch) as client:
        lead = client.post("/leads", json={
            "company_name": "Followup Co", "region": "Europe", "country": "Germany",
            "email": "f@followup.example", "score": 80,
        }).json()
        lid = lead["id"]
        # Simulate an initial email delivered long ago (status → emailed).
        ev = db.insert_outreach_event(
            lid,
            RenderedEmail(sent_to="f@followup.example", subject="s", body="b", region="Europe"),
            status="sent",
        )
        with db.connect() as conn:
            conn.execute(
                "UPDATE outreach_events SET sent_at = %s WHERE id = %s",
                ("2000-01-01T00:00:00+00:00", ev["id"]),
            )
        db.set_setting("followup_enabled", "true")
        db.set_setting("followup_interval_days", "5")
        db.set_setting("followup_max", "2")

        # Auto-send off → the follow-up is created as a draft for manual approval.
        assert _process_followups() == 1
        followups = [e for e in db.list_outreach_events(lid) if e.get("source") == "followup"]
        assert len(followups) == 1
        assert followups[0]["status"] == "draft"

        # A pending draft blocks stacking another follow-up.
        assert _process_followups() == 0


def test_batch_create_leads_dedups_against_existing_leads(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        first = client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Existing Ortho",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@existing-ortho.example",
                    "score": 80,
                }
            ],
        )
        second = client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Existing Ortho",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@existing-ortho.example",
                    "score": 80,
                },
                {
                    "company_name": "New Ortho",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@new-ortho.example",
                    "score": 80,
                },
            ],
        )

    assert first.json()["created_count"] == 1
    assert second.json()["created_count"] == 1
    assert second.json()["leads"][0]["company_name"] == "New Ortho"


def test_batch_create_leads_dedups_within_the_same_batch(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Same Company Twice",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@same-company.example",
                    "score": 80,
                },
                {
                    "company_name": "Same Company Twice",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@same-company.example",
                    "score": 80,
                },
            ],
        )

    assert created.json()["created_count"] == 1


def test_product_profile_endpoint_reads_root_assets(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/product/profile")

    payload = response.json()
    assert response.status_code == 200
    assert "SkyWalker" in payload["product_name"]
    assert payload["procedure"] == "total knee arthroplasty (TKA)"
    assert any(source.endswith(".pdf") for source in payload["source_files"])


def test_real_search_mode_uses_product_profile_and_web_search(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.services import CandidateLead

    def fake_discover_real_prospects(**kwargs):
        assert kwargs["product_profile"].procedure == "total knee arthroplasty (TKA)"
        assert kwargs["require_email"] is True
        return [
            CandidateLead(
                company_name="Real Ortho Distribution",
                region="Europe",
                country="Europe",
                website="https://real-ortho.example",
                contact_name="Sales / Business Development",
                email="bd@real-ortho.example",
                category="orthopedic / medical device distributor",
                match_reason="Live web match for total knee arthroplasty distributor.",
                source="https://real-ortho.example",
                score=91,
            )
        ]

    monkeypatch.setattr(
        main_module,
        "discover_real_prospects",
        fake_discover_real_prospects,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        _authenticate(client)
        response = client.post(
            "/leads/search",
            json={
                "target_regions": ["Europe"],
                "product_keywords": [],
                "max_results": 1,
                "real_search": True,
                "require_email": True,
            },
        )

    payload = response.json()
    assert response.status_code == 201
    assert payload["created_count"] == 1
    assert payload["leads"][0]["company_name"] == "Real Ortho Distribution"
    assert payload["leads"][0]["email"] == "bd@real-ortho.example"
    assert payload["leads"][0]["source"] == "https://real-ortho.example"


def test_demo_email_send_records_events(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Middle East"],
                "product_keywords": ["minimally invasive robot"],
                "max_results": 1,
                "real_search": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        sent = client.post("/campaigns/send-demo", json={"lead_ids": [lead_id]})

    payload = sent.json()
    assert sent.status_code == 201
    assert payload["sent_count"] == 1
    assert payload["events"][0]["lead_id"] == lead_id
    # Approved template: subject carries the target market, body is brand-consistent.
    assert "MEDBOT NaviBot Skywalker" in payload["events"][0]["subject"]
    assert "reply to this email" in payload["events"][0]["body"].lower()


def test_demo_email_send_requires_discovered_email(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.services import CandidateLead

    def fake_discover_real_prospects(**kwargs):
        return [
            CandidateLead(
                company_name="No Email Ortho",
                region="Europe",
                country="Europe",
                website="https://no-email.example",
                contact_name="Sales / Business Development",
                email="",
                category="orthopedic distributor",
                match_reason="Live web match without visible email.",
                source="https://no-email.example",
                score=71,
            )
        ]

    monkeypatch.setattr(
        main_module,
        "discover_real_prospects",
        fake_discover_real_prospects,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        _authenticate(client)
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Europe"],
                "max_results": 1,
                "real_search": True,
                "require_email": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        sent = client.post("/campaigns/send-demo", json={"lead_ids": [lead_id]})

    assert sent.status_code == 422
    assert "no discovered email" in sent.json()["detail"]


def test_reply_analysis_updates_lead_status(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        _mock_reply_llm(monkeypatch, intent="interested", requires_human=False)
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Southeast Asia"],
                "product_keywords": ["hospital robotics"],
                "max_results": 1,
                "real_search": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        analysis = client.post(
            "/replies/analyze",
            json={
                "lead_id": lead_id,
                "reply_text": "We are interested in the Skywalker system and would like to learn more. Who can we talk to?",
            },
        )
        listed = client.get("/leads")

    assert analysis.status_code == 201
    assert analysis.json()["intent"] == "interested"
    assert analysis.json()["requires_human"] is False
    assert listed.json()["leads"][0]["status"] == "interested"


def test_complex_reply_sets_human_review_status(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        _mock_reply_llm(monkeypatch, intent="complex", requires_human=True)
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Latin America"],
                "product_keywords": ["surgical robot"],
                "max_results": 1,
                "real_search": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        analysis = client.post(
            "/replies/analyze",
            json={
                "lead_id": lead_id,
                "reply_text": "We need exclusive distribution, regulatory ownership, and contract review.",
            },
        )
        lead = client.get("/leads").json()["leads"][0]

    assert analysis.status_code == 201
    assert analysis.json()["requires_human"] is True
    assert lead["status"] == "human_review"


def _make_lead(client, **overrides) -> int:
    payload = {
        "company_name": "Reply Co", "region": "Europe", "country": "Germany",
        "email": "r@reply.example", "score": 80,
    }
    payload.update(overrides)
    return client.post("/leads", json=payload).json()["id"]


def test_interested_reply_auto_drafts_reply_with_brochure(tmp_path, monkeypatch):
    from app import db
    from app.main import _generate_pending_reply_drafts

    with _client(tmp_path, monkeypatch) as client:
        _mock_reply_llm(monkeypatch, intent="interested", requires_human=False)
        lid = _make_lead(client)
        client.post("/replies/analyze", json={"lead_id": lid, "reply_text": "We are interested, who can we talk to?"})

        # Generation is async: the reply is flagged now, the draft is produced
        # off the request path by the background worker.
        assert bool(db.list_reply_analyses(lid)[0]["draft_pending"]) is True
        assert [e for e in db.list_outreach_events(lid) if e["source"] == "reply_draft"] == []

        assert _generate_pending_reply_drafts() == 1
        drafts = [e for e in db.list_outreach_events(lid) if e["source"] == "reply_draft"]
        assert len(drafts) == 1
        assert drafts[0]["status"] == "draft"
        assert bool(drafts[0]["attach_brochure"]) is True
        # Auto-drafting must not change the reply-derived status; flag now cleared.
        assert db.get_lead(lid)["status"] == "interested"
        assert bool(db.list_reply_analyses(lid)[0]["draft_pending"]) is False


def test_human_review_reply_auto_drafts_holding_no_brochure(tmp_path, monkeypatch):
    from app import db
    from app.main import _generate_pending_reply_drafts

    with _client(tmp_path, monkeypatch) as client:
        _mock_reply_llm(monkeypatch, intent="complex", requires_human=True)
        lid = _make_lead(client)
        client.post("/replies/analyze", json={"lead_id": lid, "reply_text": "What is the price and exclusivity?"})
        _generate_pending_reply_drafts()

        drafts = [e for e in db.list_outreach_events(lid) if e["source"] == "reply_draft"]
        assert len(drafts) == 1
        assert bool(drafts[0]["attach_brochure"]) is False
        assert db.get_lead(lid)["status"] == "human_review"


def test_rejected_and_needs_review_replies_create_no_draft(tmp_path, monkeypatch):
    from app import db
    from app.main import _generate_pending_reply_drafts

    with _client(tmp_path, monkeypatch) as client:
        _mock_reply_llm(monkeypatch, intent="rejected", requires_human=False)
        lid = _make_lead(client)
        client.post("/replies/analyze", json={"lead_id": lid, "reply_text": "Not interested, no fit."})
        # Not flagged, and the worker produces nothing.
        assert bool(db.list_reply_analyses(lid)[0]["draft_pending"]) is False
        assert _generate_pending_reply_drafts() == 0
        assert [e for e in db.list_outreach_events(lid) if e["source"] == "reply_draft"] == []


def test_reply_draft_not_duplicated_on_repeated_analysis(tmp_path, monkeypatch):
    from app import db
    from app.main import _generate_pending_reply_drafts

    with _client(tmp_path, monkeypatch) as client:
        _mock_reply_llm(monkeypatch, intent="interested", requires_human=False)
        lid = _make_lead(client)
        client.post("/replies/analyze", json={"lead_id": lid, "reply_text": "Interested!"})
        _generate_pending_reply_drafts()
        # A second reply while a draft is already pending must not flag another.
        client.post("/replies/analyze", json={"lead_id": lid, "reply_text": "Still interested!"})
        assert bool(db.list_reply_analyses(lid)[0]["draft_pending"]) is False
        _generate_pending_reply_drafts()
        drafts = [e for e in db.list_outreach_events(lid) if e["source"] == "reply_draft"]
        assert len(drafts) == 1


def test_manual_reply_endpoint_drafts_and_sends(tmp_path, monkeypatch):
    from app import db

    with _client(tmp_path, monkeypatch) as client:
        lid = _make_lead(client)
        # Save a manual reply draft.
        r1 = client.post(f"/leads/{lid}/reply", json={"subject": "Re: Hello", "body": "Manual reply body.", "action": "draft"})
        assert r1.status_code == 201 and r1.json()["queued"] is False
        drafts = [e for e in db.list_outreach_events(lid) if e["source"] == "reply_manual"]
        assert len(drafts) == 1 and drafts[0]["status"] == "draft"

        # Queue one for delivery.
        r2 = client.post(f"/leads/{lid}/reply", json={"subject": "Re: Hello 2", "body": "Send this now.", "action": "send"})
        assert r2.json()["queued"] is True
        queued = [e for e in db.list_outreach_events(lid) if e["source"] == "reply_manual" and e["status"] == "queued"]
        assert len(queued) == 1


def test_edit_draft_updates_content(tmp_path, monkeypatch):
    from app import db
    from app.main import _generate_pending_reply_drafts

    with _client(tmp_path, monkeypatch) as client:
        _mock_reply_llm(monkeypatch, intent="interested", requires_human=False)
        lid = _make_lead(client)
        client.post("/replies/analyze", json={"lead_id": lid, "reply_text": "Interested!"})
        _generate_pending_reply_drafts()
        draft = [e for e in db.list_outreach_events(lid) if e["source"] == "reply_draft"][0]

        resp = client.put(f"/campaigns/drafts/{draft['id']}", json={"subject": "Re: edited", "body": "Edited body.", "attach_brochure": False})
        assert resp.status_code == 200
        updated = db.list_outreach_events(lid)[0]
        assert updated["subject"] == "Re: edited"
        assert updated["body"] == "Edited body."
        assert bool(updated["attach_brochure"]) is False


def test_reply_draft_worker_generates_flagged_drafts(tmp_path, monkeypatch):
    """The background worker turns draft-flagged replies into drafts and is
    idempotent (a second run with nothing pending is a no-op)."""
    from app import db
    from app.main import _generate_pending_reply_drafts

    with _client(tmp_path, monkeypatch) as client:
        _mock_reply_llm(monkeypatch, intent="interested", requires_human=False)
        lid = _make_lead(client)
        client.post("/replies/analyze", json={"lead_id": lid, "reply_text": "Interested!"})
        assert _generate_pending_reply_drafts() == 1
        assert _generate_pending_reply_drafts() == 0  # nothing left pending
        assert len([e for e in db.list_outreach_events(lid) if e["source"] == "reply_draft"]) == 1


def test_delivered_reply_keeps_lead_status(tmp_path, monkeypatch):
    """A reply's delivery must NOT reset an interested/human_review lead to emailed."""
    from app import db
    from app.services import RenderedEmail

    with _client(tmp_path, monkeypatch) as client:
        lid = _make_lead(client)
        db.update_lead(lid, status="interested")
        ev = db.insert_outreach_event(
            lid, RenderedEmail(sent_to="r@reply.example", subject="Re: x", body="b", region="Europe"),
            status="queued", source="reply_draft",
        )
        db.mark_outreach_sent(int(ev["id"]))
        assert db.get_lead(lid)["status"] == "interested"


def test_lead_search_is_case_insensitive(tmp_path, monkeypatch):
    """Postgres LIKE is case-sensitive (SQLite's wasn't), which silently broke the
    search box after the migration: "Dach" found nothing for "DACH Medical".
    Search must match regardless of the caller's capitalization — and the paged
    `total` (count_leads) must agree with the rows returned (list_leads)."""
    with _client(tmp_path, monkeypatch) as client:
        _make_lead(client, company_name="DACH Medical Group", email="office@dach-medical.example")
        _make_lead(client, company_name="metamorphosis GmbH", email="info@meta.example")

        for keyword in ("DACH", "dach", "Dach", "dAcH"):
            payload = client.get(f"/leads?q={keyword}").json()
            assert payload["total"] == 1, keyword
            assert len(payload["leads"]) == 1, keyword
            assert payload["leads"][0]["company_name"] == "DACH Medical Group", keyword

        # Matching on other searchable columns is case-insensitive too.
        for keyword in ("METAMORPHOSIS", "Metamorphosis"):
            assert client.get(f"/leads?q={keyword}").json()["total"] == 1, keyword
        # email column
        assert client.get("/leads?q=OFFICE@DACH-MEDICAL.EXAMPLE").json()["total"] == 1
        # a non-match still returns nothing
        assert client.get("/leads?q=zzz-nothing").json()["total"] == 0


def test_agent_history_is_team_shared_across_users(tmp_path, monkeypatch):
    """Agent chat history lives server-side, so a DIFFERENT user on a DIFFERENT
    browser sees the same sessions and turns (the client's actual complaint)."""
    from fastapi.testclient import TestClient

    from app import db
    from app.main import create_app

    with _client(tmp_path, monkeypatch) as client:
        # admin records a turn
        r = client.post("/agent/sessions/agent-abc/turns", json={
            "payload": {"role": "user", "text": "找德国的代理商"},
            "title": "德国代理商",
        })
        assert r.status_code == 201
        assert r.json()["author"] == "admin"
        client.post("/agent/sessions/agent-abc/turns", json={
            "payload": {"role": "assistant", "text": "好的，正在搜索…"},
        })

        # a second user, fresh client (i.e. another machine/browser, no localStorage)
        db.create_user(
            username="colleague", password="Str0ngPass!", display_name="同事",
            is_superadmin=True, must_change_password=False,
        )

    with TestClient(create_app()) as c2:
        _authenticate(c2, username="colleague", password="Str0ngPass!")
        listed = c2.get("/agent/sessions").json()
        assert listed["total"] == 1
        assert listed["sessions"][0]["session_id"] == "agent-abc"
        assert listed["sessions"][0]["title"] == "德国代理商"
        assert listed["sessions"][0]["created_by"] == "admin"
        assert listed["sessions"][0]["turn_count"] == 2

        detail = c2.get("/agent/sessions/agent-abc").json()
        assert [t["payload"]["text"] for t in detail["turns"]] == ["找德国的代理商", "好的，正在搜索…"]
        assert detail["turns"][0]["author"] == "admin"


def test_agent_session_rename_and_delete(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/agent/sessions/agent-x/turns", json={"payload": {"role": "user", "text": "hi"}})

        renamed = client.put("/agent/sessions/agent-x", json={"title": "新标题"})
        assert renamed.status_code == 200
        assert client.get("/agent/sessions").json()["sessions"][0]["title"] == "新标题"

        assert client.delete("/agent/sessions/agent-x").json()["ok"] is True
        assert client.get("/agent/sessions").json()["total"] == 0
        # turns are removed with the session
        assert client.get("/agent/sessions/agent-x").status_code == 404


def test_agent_session_ordering_and_unknown_session(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/agent/sessions/agent-old/turns", json={"payload": {"text": "a"}})
        client.post("/agent/sessions/agent-new/turns", json={"payload": {"text": "b"}})
        # most recently active first
        assert client.get("/agent/sessions").json()["sessions"][0]["session_id"] == "agent-new"
        assert client.get("/agent/sessions/nope").status_code == 404
        assert client.put("/agent/sessions/nope", json={"title": "x"}).status_code == 404
        assert client.delete("/agent/sessions/nope").status_code == 404


def test_reply_analysis_errors_without_llm(tmp_path, monkeypatch):
    # No LLM configured (AGENT_ENV_PATH isolated by fixture): the endpoint must
    # error rather than fall back to keyword rules.
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={"target_regions": ["Europe"], "max_results": 1, "real_search": False},
        )
        lead_id = created.json()["leads"][0]["id"]
        resp = client.post(
            "/replies/analyze",
            json={"lead_id": lead_id, "reply_text": "We are interested, tell us more."},
        )

    assert resp.status_code == 502
    assert "AI" in resp.json()["detail"]


def test_update_lead_status_and_notes(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Europe"],
                "product_keywords": ["surgical robot"],
                "max_results": 1,
                "real_search": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        updated = client.patch(
            f"/leads/{lead_id}",
            json={"status": "qualified", "notes": "Owner confirmed channel fit."},
        )

    assert updated.status_code == 200
    assert updated.json()["status"] == "qualified"
    assert updated.json()["notes"] == "Owner confirmed channel fit."


def test_update_lead_reclassifies_lead_type(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Misclassified Co",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@misclassified.example",
                    "lead_type": "distributor",
                    "score": 70,
                }
            ],
        )
        lead_id = created.json()["leads"][0]["id"]

        updated = client.patch(f"/leads/{lead_id}", json={"lead_type": "kol"})
        rejected = client.patch(f"/leads/{lead_id}", json={"lead_type": "not-a-real-type"})

    assert updated.status_code == 200
    assert updated.json()["lead_type"] == "kol"
    assert rejected.status_code == 400


def test_source_preview_endpoint_returns_page_text_and_email_match(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module

    def fake_fetch_source_preview(url: str, email: str):
        assert url == "https://source.example/contact"
        assert email == "sales@source.example"
        return {
            "url": url,
            "title": "Source Contact",
            "text": "Contact our sales team at sales@source.example for distribution inquiries.",
            "email": email,
            "emails": ["sales@source.example"],
            "email_found": True,
        }

    monkeypatch.setattr(
        main_module,
        "fetch_source_preview",
        fake_fetch_source_preview,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        _authenticate(client)
        response = client.get(
            "/sources/preview",
            params={"url": "https://source.example/contact", "email": "sales@source.example"},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["title"] == "Source Contact"
    assert payload["email_found"] is True
    assert "sales@source.example" in payload["text"]


def test_web_search_endpoint_returns_search_results(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.web_search import SearchResult

    def fake_search_web(query: str, *, limit: int = 8):
        assert query == "orthopedic implant distributor India"
        assert limit == 2
        return [
            SearchResult(
                title="Ortho Distributor India",
                url="https://ortho.example",
                snippet="Orthopedic implant distributor in India.",
                query=query,
            )
        ]

    monkeypatch.setattr(main_module, "search_web", fake_search_web, raising=False)

    with TestClient(main_module.create_app()) as client:
        _authenticate(client)
        response = client.post(
            "/web/search",
            json={"query": "orthopedic implant distributor India", "max_results": 2},
        )

    assert response.status_code == 200
    assert response.json() == {
        "query": "orthopedic implant distributor India",
        "results": [
            {
                "title": "Ortho Distributor India",
                "url": "https://ortho.example",
                "snippet": "Orthopedic implant distributor in India.",
                "query": "orthopedic implant distributor India",
            }
        ],
    }


def test_web_fetch_endpoint_returns_page_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module

    def fake_fetch_source_preview(url: str, email: str):
        assert url == "https://ortho.example/contact"
        assert email == "sales@ortho.example"
        return {
            "url": url,
            "title": "Contact Ortho",
            "text": "Contact sales@ortho.example for distribution.",
            "email": email,
            "emails": [email],
            "email_found": True,
        }

    monkeypatch.setattr(
        main_module,
        "fetch_source_preview",
        fake_fetch_source_preview,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        _authenticate(client)
        response = client.post(
            "/web/fetch",
            json={"url": "https://ortho.example/contact", "email": "sales@ortho.example"},
        )

    assert response.status_code == 200
    assert response.json()["title"] == "Contact Ortho"
    assert response.json()["email_found"] is True


def test_agent_chat_delegates_the_calling_users_own_token(tmp_path, monkeypatch):
    """The sidecar must receive THIS specific user's JWT (not the admin's, not
    the service token), so its tool calls run under that user's real RBAC
    permissions rather than a blanket-privileged identity."""
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.auth import decode_token

    captured = {}

    def fake_forward_agent_chat(payload, user_token=None):
        captured["user_token"] = user_token
        return {"message": "ok", "session_id": "s", "events": []}

    monkeypatch.setattr(main_module, "forward_agent_chat", fake_forward_agent_chat, raising=False)

    with _client(tmp_path, monkeypatch) as client:
        role = client.post(
            "/admin/roles", json={"name": "chat-only", "permissions": ["agent.use"]}
        ).json()
        client.post(
            "/admin/users",
            json={"username": "chatter", "password": "chatter123", "role_ids": [role["id"]]},
        )

    with TestClient(main_module.create_app()) as c2:
        _authenticate(c2, "chatter", "chatter123")
        c2.post("/agent/chat", json={"message": "hi"})

    payload = decode_token(captured["user_token"])
    assert payload is not None
    assert payload["username"] == "chatter"


def test_agent_chat_proxy_forwards_to_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module

    def fake_forward_agent_chat(payload, user_token=None):
        assert payload["message"] == "Find India SkyWalker TKA distributors"
        assert payload["session_id"] is None
        # The signed-in admin's own JWT must be delegated to the sidecar so its
        # tool calls run under the real caller's RBAC permissions.
        assert user_token
        return {
            "message": "Found 3 candidate distributors.",
            "session_id": "test-session",
            "events": [{"type": "tool", "name": "search_leads"}],
        }

    monkeypatch.setattr(main_module, "forward_agent_chat", fake_forward_agent_chat, raising=False)

    with TestClient(main_module.create_app()) as client:
        _authenticate(client)
        response = client.post(
            "/agent/chat",
            json={"message": "Find India SkyWalker TKA distributors"},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Found 3 candidate distributors."
    assert response.json()["session_id"] == "test-session"
    assert response.json()["events"][0]["name"] == "search_leads"


def test_agent_chat_stream_proxy_forwards_sse(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module

    def fake_forward_agent_chat_stream(payload, user_token=None):
        assert payload["message"] == "Find India SkyWalker TKA distributors"
        assert user_token
        yield b'event: start\ndata: {"session_id":"test-session"}\n\n'
        yield b'event: delta\ndata: {"text":"Found "}\n\n'
        yield b'event: done\ndata: {"message":"Found 3","session_id":"test-session","events":[]}\n\n'

    monkeypatch.setattr(
        main_module,
        "forward_agent_chat_stream",
        fake_forward_agent_chat_stream,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        _authenticate(client)
        with client.stream(
            "POST",
            "/agent/chat/stream",
            json={"message": "Find India SkyWalker TKA distributors"},
        ) as response:
            body = response.read().decode("utf8")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: start' in body
    assert '{"text":"Found "}' in body
    assert 'event: done' in body


def test_agent_chat_proxy_reports_sidecar_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.agent_proxy import AgentProxyError

    def fake_forward_agent_chat(payload, user_token=None):
        raise AgentProxyError(status_code=503, detail="Agent sidecar unavailable at http://localhost:8011")

    monkeypatch.setattr(main_module, "forward_agent_chat", fake_forward_agent_chat, raising=False)

    with TestClient(main_module.create_app()) as client:
        _authenticate(client)
        response = client.post("/agent/chat", json={"message": "hello"})

    assert response.status_code == 503
    assert "Agent sidecar unavailable" in response.json()["detail"]


def test_agent_config_status_masks_key_and_reads_agent_env(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=sk-test-secret-123456",
                "PI_MODEL=gpt-5-mini",
                "BACKEND_BASE_URL=http://localhost:8020",
            ]
        ),
        encoding="utf8",
    )
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/agent/config")

    payload = response.json()
    assert response.status_code == 200
    assert payload["has_openai_api_key"] is True
    assert payload["openai_api_key_preview"] == "sk-...3456"
    assert payload["provider_name"] == "openai"
    assert payload["has_api_key"] is True
    assert payload["api_key_preview"] == "sk-...3456"
    assert "secret" not in str(payload)
    assert payload["model_name"] == "gpt-5-mini"
    assert payload["backend_base_url"] == "http://localhost:8020"
    assert payload["restart_required"] is False


def test_agent_config_status_reads_deepseek_key_without_leaking_secret(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text(
        "\n".join(
            [
                "PI_PROVIDER=deepseek",
                "DEEPSEEK_API_KEY=sk-deepseek-secret-123456",
                "PI_MODEL=deepseek-v4-pro",
            ]
        ),
        encoding="utf8",
    )
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/agent/config")

    payload = response.json()
    assert response.status_code == 200
    assert payload["provider_name"] == "deepseek"
    assert payload["has_api_key"] is True
    assert payload["api_key_preview"] == "sk-...3456"
    assert "secret" not in str(payload)
    assert payload["has_openai_api_key"] is False
    assert payload["model_name"] == "deepseek-v4-pro"


def test_agent_config_update_writes_agent_env_and_preserves_other_values(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text(
        "\n".join(
            [
                "# existing sidecar settings",
                "AGENT_PORT=8011",
                "OPENAI_API_KEY=old-key",
                "PI_MODEL=gpt-5-mini",
            ]
        )
        + "\n",
        encoding="utf8",
    )
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.put(
            "/agent/config",
            json={
                "openai_api_key": "sk-new-secret-abcdef",
                "model_name": "gpt-5.5",
                "backend_base_url": "http://localhost:8020/",
            },
        )

    payload = response.json()
    content = agent_env_path.read_text(encoding="utf8")
    assert response.status_code == 200
    assert payload["has_openai_api_key"] is True
    assert payload["openai_api_key_preview"] == "sk-...cdef"
    assert payload["model_name"] == "gpt-5.5"
    assert payload["backend_base_url"] == "http://localhost:8020"
    assert payload["restart_required"] is True
    assert "# existing sidecar settings" in content
    assert "AGENT_PORT=8011" in content
    assert "OPENAI_API_KEY=sk-new-secret-abcdef" in content
    assert "PI_MODEL=gpt-5.5" in content
    assert "BACKEND_BASE_URL=http://localhost:8020" in content


def test_agent_config_update_writes_deepseek_provider_key_and_model(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text("AGENT_PORT=8011\nOPENAI_API_KEY=old-openai-key\n", encoding="utf8")
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.put(
            "/agent/config",
            json={
                "provider_name": "deepseek",
                "api_key": "sk-deepseek-new-abcdef",
                "model_name": "deepseek-v4-pro",
                "backend_base_url": "http://localhost:8020/",
            },
        )

    payload = response.json()
    content = agent_env_path.read_text(encoding="utf8")
    assert response.status_code == 200
    assert payload["provider_name"] == "deepseek"
    assert payload["has_api_key"] is True
    assert payload["api_key_preview"] == "sk-...cdef"
    assert payload["model_name"] == "deepseek-v4-pro"
    assert payload["backend_base_url"] == "http://localhost:8020"
    assert "AGENT_PORT=8011" in content
    assert "OPENAI_API_KEY=old-openai-key" in content
    assert "PI_PROVIDER=deepseek" in content
    assert "DEEPSEEK_API_KEY=sk-deepseek-new-abcdef" in content
    assert "PI_MODEL=deepseek-v4-pro" in content
    assert "BACKEND_BASE_URL=http://localhost:8020" in content


def test_agent_config_update_can_change_model_without_resending_key(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text(
        "OPENAI_API_KEY=sk-existing-secret-0000\nPI_MODEL=gpt-5-mini\n",
        encoding="utf8",
    )
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.put("/agent/config", json={"model_name": "gpt-5.4"})

    content = agent_env_path.read_text(encoding="utf8")
    assert response.status_code == 200
    assert "OPENAI_API_KEY=sk-existing-secret-0000" in content
    assert "PI_MODEL=gpt-5.4" in content


@pytest.mark.parametrize(
    "payload",
    [
        {"message": None, "session_id": "s"},
        {"message": "ok", "session_id": "s", "events": "bad"},
    ],
)
def test_forward_agent_chat_rejects_malformed_sidecar_payload(payload, monkeypatch):
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    from app.agent_proxy import AgentProxyError, forward_agent_chat

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return payload

    class FakeHttp:
        def post(self, url, json, timeout):
            return FakeResponse()

    with pytest.raises(AgentProxyError) as exc_info:
        forward_agent_chat({"message": "hello"}, http=FakeHttp())

    assert exc_info.value.status_code == 502
    assert "invalid chat payload" in exc_info.value.detail


def test_forward_agent_chat_uses_default_url_and_defaults_events(monkeypatch):
    monkeypatch.delenv("AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    from app.agent_proxy import forward_agent_chat

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {"message": "ok", "session_id": "s"}

    class FakeHttp:
        def __init__(self):
            self.calls = []

        def post(self, url, json, timeout):
            self.calls.append((url, json, timeout))
            return FakeResponse()

    fake_http = FakeHttp()
    result = forward_agent_chat({"message": "hello", "session_id": None}, http=fake_http, timeout=12.5)

    assert fake_http.calls == [
        ("http://localhost:8011/agent/chat", {"message": "hello", "session_id": None}, 12.5)
    ]
    assert result == {"message": "ok", "session_id": "s", "events": []}


def test_forward_agent_chat_sends_authorization_header_when_token_is_configured(monkeypatch):
    monkeypatch.setenv("AGENT_TOKEN", "sidecar-secret")
    from app.agent_proxy import forward_agent_chat

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {"message": "ok", "session_id": "s", "events": []}

    class FakeHttp:
        def __init__(self):
            self.headers = None

        def post(self, url, json, timeout, headers=None):
            self.headers = headers
            return FakeResponse()

    fake_http = FakeHttp()
    forward_agent_chat({"message": "hello"}, http=fake_http)

    assert fake_http.headers == {"Authorization": "Bearer sidecar-secret"}


def test_forward_agent_chat_stream_uses_stream_endpoint_and_yields_chunks(monkeypatch):
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    from app.agent_proxy import forward_agent_chat_stream

    class FakeResponse:
        status_code = 200
        text = "ok"

        def iter_content(self, chunk_size=None):
            yield b"event: delta\n"
            yield b'data: {"text":"hi"}\n\n'

        def close(self):
            self.closed = True

    class FakeHttp:
        def __init__(self):
            self.calls = []
            self.response = FakeResponse()

        def post(self, url, json, timeout, stream=False):
            self.calls.append((url, json, timeout, stream))
            return self.response

    fake_http = FakeHttp()
    chunks = list(forward_agent_chat_stream({"message": "hello"}, http=fake_http, timeout=12.5))

    assert fake_http.calls == [
        ("http://localhost:8011/agent/chat/stream", {"message": "hello"}, 12.5, True)
    ]
    assert chunks == [b"event: delta\n", b'data: {"text":"hi"}\n\n']
    assert fake_http.response.closed is True


def test_forward_agent_chat_stream_stops_cleanly_when_upstream_disconnects(monkeypatch):
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    import requests

    from app.agent_proxy import forward_agent_chat_stream

    class FakeResponse:
        status_code = 200
        text = "ok"
        closed = False

        def iter_content(self, chunk_size=None):
            yield b"event: start\n\n"
            raise requests.exceptions.ChunkedEncodingError("broken stream")

        def close(self):
            self.closed = True

    class FakeHttp:
        def __init__(self):
            self.response = FakeResponse()

        def post(self, url, json, timeout, stream=False):
            return self.response

    fake_http = FakeHttp()
    chunks = list(forward_agent_chat_stream({"message": "hello"}, http=fake_http))

    assert chunks == [b"event: start\n\n"]
    assert fake_http.response.closed is True


# ── Auth & RBAC ───────────────────────────────────────────────────────────────

def test_protected_endpoint_requires_auth(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, authenticate=False) as client:
        # No token → 401
        assert client.get("/leads").status_code == 401
        # Health stays public
        assert client.get("/health").status_code == 200


def test_login_rejects_bad_credentials(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, authenticate=False) as client:
        resp = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401


def test_seeded_admin_has_all_permissions(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        me = client.get("/auth/me").json()
        assert me["username"] == "admin"
        assert me["is_superadmin"] is True
        perms = client.get("/admin/permissions").json()["permissions"]
        assert set(me["permissions"]) == {p["key"] for p in perms}


def test_custom_role_limits_permissions(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        # Admin creates a read-only role + a user with only that role.
        role = client.post(
            "/admin/roles",
            json={"name": "仅查看线索", "description": "", "permissions": ["leads.view"]},
        ).json()
        assert role["permissions"] == ["leads.view"]

        client.post(
            "/admin/users",
            json={
                "username": "viewer1",
                "password": "viewer123",
                "display_name": "Viewer",
                "role_ids": [role["id"]],
            },
        )

        # Log in as the limited user on a fresh client (no inherited admin header).
        from fastapi.testclient import TestClient
        from app.main import create_app

        with TestClient(create_app()) as c2:
            _authenticate(c2, "viewer1", "viewer123")
            assert c2.get("/leads").status_code == 200  # has leads.view
            # Lacks leads.search / outreach / users.manage → 403
            assert c2.post("/leads/search", json={"target_regions": ["Europe"], "real_search": False}).status_code == 403
            assert c2.get("/admin/users").status_code == 403


def test_non_admin_cannot_manage_users(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        role = client.post(
            "/admin/roles", json={"name": "操作", "permissions": ["leads.view", "leads.search"]}
        ).json()
        client.post(
            "/admin/users",
            json={"username": "op1", "password": "oppass1", "role_ids": [role["id"]]},
        )

    from fastapi.testclient import TestClient
    from app.main import create_app

    with TestClient(create_app()) as c2:
        _authenticate(c2, "op1", "oppass1")
        assert c2.post("/admin/roles", json={"name": "x", "permissions": []}).status_code == 403


def test_cannot_delete_last_superadmin(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        me = client.get("/auth/me").json()
        # Deleting self is blocked, and it's the only superadmin anyway.
        resp = client.request("DELETE", f"/admin/users/{me['id']}")
        assert resp.status_code == 400


# ── Compliance: unsubscribe, suppression, audit ───────────────────────────────

def test_unsubscribe_link_suppresses_recipient(tmp_path, monkeypatch):
    from app.email_service import make_unsubscribe_token

    with _client(tmp_path, monkeypatch) as client:
        token = make_unsubscribe_token("doc@hospital.example")
        # Public endpoint, no auth needed
        page = client.get("/unsubscribe", params={"token": token})
        assert page.status_code == 200
        assert "退订" in page.text or "unsubscribed" in page.text.lower()

        supp = client.get("/admin/suppressions").json()
        emails = [s["email"] for s in supp["suppressions"]]
        assert "doc@hospital.example" in emails

        # Tampered token is rejected
        bad = client.get("/unsubscribe", params={"token": "garbage.deadbeef"})
        assert bad.status_code == 200
        assert "无效" in bad.text or "Invalid" in bad.text


def test_unsubscribe_one_click_post_suppresses_without_html(tmp_path, monkeypatch):
    """RFC 8058 target: mail clients POST here directly (no user interaction),
    so it must not render an HTML page — just suppress and return empty 200."""
    from app.email_service import make_unsubscribe_token

    with _client(tmp_path, monkeypatch) as client:
        token = make_unsubscribe_token("one-click@hospital.example")
        response = client.post("/unsubscribe", params={"token": token})
        assert response.status_code == 200
        assert response.text == ""

        supp = client.get("/admin/suppressions").json()
        emails = [s["email"] for s in supp["suppressions"]]
        assert "one-click@hospital.example" in emails

        bad = client.post("/unsubscribe", params={"token": "garbage.deadbeef"})
        assert bad.status_code == 400


def test_suppressed_address_is_not_emailed(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={"target_regions": ["Europe"], "product_keywords": ["surgical robot"],
                  "max_results": 1, "real_search": False},
        )
        lead = created.json()["leads"][0]
        # Suppress this lead's email
        client.post("/admin/suppressions", json={"email": lead["email"], "reason": "manual"})

        sent = client.post("/campaigns/send-demo", json={"lead_ids": [lead["id"]]})
        assert sent.status_code == 201
        # The outreach event is recorded as suppressed, not sent/recorded
        assert sent.json()["events"][0]["status"] == "suppressed"


def test_manual_suppression_add_and_remove(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/admin/suppressions", json={"email": "x@y.com", "reason": "bounce"})
        assert any(s["email"] == "x@y.com" for s in client.get("/admin/suppressions").json()["suppressions"])
        client.request("DELETE", "/admin/suppressions", params={"email": "x@y.com"})
        assert not any(s["email"] == "x@y.com" for s in client.get("/admin/suppressions").json()["suppressions"])


def test_audit_log_records_login_and_actions(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        # The fixture already logged in → a login event should exist
        client.post("/admin/suppressions", json={"email": "z@z.com"})
        audit = client.get("/admin/audit").json()["events"]
        actions = {e["action"] for e in audit}
        assert "login" in actions
        assert "suppression.add" in actions
        # actor is recorded
        assert all(e["actor"] for e in audit)


def test_audit_requires_admin(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        role = client.post("/admin/roles", json={"name": "noaudit", "permissions": ["leads.view"]}).json()
        client.post("/admin/users", json={"username": "nau", "password": "nau123x", "role_ids": [role["id"]]})

    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as c2:
        _authenticate(c2, "nau", "nau123x")
        assert c2.get("/admin/audit").status_code == 403
        assert c2.get("/admin/suppressions").status_code == 403


# ── #3 Auth hardening ─────────────────────────────────────────────────────────

def test_login_rate_limited_after_failures(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, authenticate=False) as client:
        for _ in range(5):
            r = client.post("/auth/login", json={"username": "ratelimitee", "password": "bad"})
            assert r.status_code == 401
        # 6th attempt is locked out
        r = client.post("/auth/login", json={"username": "ratelimitee", "password": "bad"})
        assert r.status_code == 429
        assert "Retry-After" in r.headers


def test_default_admin_must_change_password_then_cleared(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        me = client.get("/auth/me").json()
        assert me["must_change_password"] is True
        client.post("/auth/change-password", json={"old_password": "admin123", "new_password": "newpass123"})
        assert client.get("/auth/me").json()["must_change_password"] is False


def test_admin_reset_forces_user_change(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        role = client.post("/admin/roles", json={"name": "r1", "permissions": ["leads.view"]}).json()
        u = client.post("/admin/users", json={"username": "u1", "password": "init123", "role_ids": [role["id"]]}).json()
        # New users must change on first login
        assert u["must_change_password"] is True


def test_secret_settings_encrypted_at_rest(tmp_path, monkeypatch):
    from app import db as dbmod
    with _client(tmp_path, monkeypatch) as client:
        client.put("/settings", json={"agent_provider": "bailian", "agent_key": "sk-secret-123456"})
        # Raw DB value is ciphertext, not the plaintext key
        with dbmod.connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = %s", ("agent_key",)
            ).fetchone()
        raw = row["value"]
        assert raw.startswith("enc:v1:")
        assert "sk-secret-123456" not in raw
        # And it decrypts back transparently
        assert dbmod.get_setting("agent_key") == "sk-secret-123456"


# ── #2 Send queue, throttle, bounce ───────────────────────────────────────────

def test_send_enqueues_and_dispatch_delivers(tmp_path, monkeypatch):
    from app import main as m
    from app.email_service import SendResult
    sent: list[str] = []
    monkeypatch.setattr(m, "email_is_configured", lambda: True)
    monkeypatch.setattr(m, "send_email", lambda *, to, subject, body, **k: (sent.append(to), SendResult(sent_to=to, subject=subject, success=True, message_id="mid"))[1])

    with _client(tmp_path, monkeypatch) as client:
        lead = client.post("/leads", json={
            "company_name": "Q Co", "region": "Europe", "country": "Germany",
            "email": "buyer@qco.example", "category": "distributor",
        }).json()
        resp = client.post("/campaigns/send-demo", json={"lead_ids": [lead["id"]]})
        # Email configured → queued, not sent inline
        assert resp.json()["events"][0]["status"] == "queued"
        assert resp.json()["queued_count"] == 1
        assert client.get("/campaigns/queue").json()["queued"] == 1

        # Drain one from the queue
        assert m._dispatch_due_email() is True
        assert sent == ["buyer@qco.example"]
        q = client.get("/campaigns/queue").json()
        assert q["queued"] == 0 and q["sent_today"] == 1


def test_dispatch_skips_suppressed_in_queue(tmp_path, monkeypatch):
    from app import main as m
    from app.email_service import SendResult
    monkeypatch.setattr(m, "email_is_configured", lambda: True)
    monkeypatch.setattr(m, "send_email", lambda **k: SendResult(sent_to="x", subject="s", success=True))

    with _client(tmp_path, monkeypatch) as client:
        lead = client.post("/leads", json={
            "company_name": "S Co", "region": "Europe", "country": "France",
            "email": "no@sco.example", "category": "distributor",
        }).json()
        client.post("/campaigns/send-demo", json={"lead_ids": [lead["id"]]})  # queued
        client.post("/admin/suppressions", json={"email": "no@sco.example"})  # then suppressed
        m._dispatch_due_email()
        # The queued item should be marked suppressed, not sent
        assert client.get("/campaigns/queue").json()["queued"] == 0
        hist = client.get(f"/leads/{lead['id']}/history").json()
        assert hist["outreach_events"][0]["status"] == "suppressed"


def test_bounce_message_suppresses_recipient(tmp_path, monkeypatch):
    from app import main as m
    from app.email_service import InboxReply
    monkeypatch.setattr(m, "email_is_configured", lambda: True)

    with _client(tmp_path, monkeypatch) as client:
        lead = client.post("/leads", json={
            "company_name": "B Co", "region": "Europe", "country": "Spain",
            "email": "deadbox@bco.example", "category": "distributor",
        }).json()
        bounce = InboxReply(
            sender_email="MAILER-DAEMON@exchange.local", sender_name="Mail Delivery System",
            subject="Undeliverable: Distribution Partnership",
            body="Your message to deadbox@bco.example could not be delivered. 550 5.1.1 user unknown.",
            received_at="", message_id="bounce-1",
        )
        monkeypatch.setattr(m, "fetch_inbox_replies", lambda **k: [bounce])
        result = client.post("/replies/sync").json()
        assert result["bounced_suppressed"] == 1
        assert any(s["email"] == "deadbox@bco.example" for s in client.get("/admin/suppressions").json()["suppressions"])


# ── Configurable lead scoring rules ────────────────────────────────────────────

def test_scoring_rules_defaults_match_skill_md(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        rules = client.get("/scoring/rules").json()

    weight_total = sum(w["percent"] for w in rules["weights"])
    assert weight_total == 100
    assert rules["positive_rules"][0] == {"points": 25, "description": "官网确认从事医疗器械分销、进口或渠道销售"}
    assert rules["thresholds"][0]["level"] == "strong"
    assert rules["updated_at"] == ""


def test_scoring_rules_readable_via_service_token(tmp_path, monkeypatch):
    """The Agent's tool call authenticates with the service token, not a user
    JWT — it must still be able to read the current rules."""
    import os as _os
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    monkeypatch.setenv("MEDBOT_SERVICE_TOKEN", "svc-secret")
    from app.main import create_app

    with TestClient(create_app()) as client:
        resp = client.get("/scoring/rules", headers={"X-Service-Token": "svc-secret"})
        assert resp.status_code == 200
        assert len(resp.json()["weights"]) > 0


def test_update_scoring_rules_persists_and_requires_settings_manage(tmp_path, monkeypatch):
    custom = {
        "weights": [{"key": "channel_fit", "label": "渠道匹配度", "percent": 100}],
        "positive_rules": [{"points": 50, "description": "自定义规则"}],
        "negative_rules": [{"points": -50, "description": "自定义扣分"}],
        "thresholds": [{"min": 0, "max": 100, "level": "medium", "label": "全部待核验"}],
    }
    with _client(tmp_path, monkeypatch) as client:
        updated = client.put("/scoring/rules", json=custom).json()
        assert updated["weights"][0]["percent"] == 100
        assert updated["updated_at"] != ""

        # Persisted: a fresh GET reflects the change, not the defaults.
        fetched = client.get("/scoring/rules").json()
        assert fetched["positive_rules"][0]["description"] == "自定义规则"

        # A limited role without settings.manage cannot edit, but can still read.
        role = client.post("/admin/roles", json={"name": "score-reader", "permissions": ["leads.view"]}).json()
        client.post("/admin/users", json={"username": "score_reader", "password": "reader123x", "role_ids": [role["id"]]})

    from app.main import create_app as _create_app

    with TestClient(_create_app()) as c2:
        _authenticate(c2, "score_reader", "reader123x")
        assert c2.get("/scoring/rules").status_code == 200
        assert c2.put("/scoring/rules", json=custom).status_code == 403


def test_scoring_rules_kol_and_distributor_are_independent(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        distributor_defaults = client.get("/scoring/rules").json()
        kol_defaults = client.get("/scoring/rules", params={"lead_type": "kol"}).json()

        # Defaults differ — KOL rules are not just the distributor rules relabeled.
        assert distributor_defaults["weights"][0]["key"] == "channel_fit"
        assert kol_defaults["weights"][0]["key"] == "clinical_volume_fit"
        assert distributor_defaults["positive_rules"] != kol_defaults["positive_rules"]

        # Updating one set never touches the other.
        kol_custom = {
            "weights": [{"key": "clinical_volume_fit", "label": "临床匹配度", "percent": 100}],
            "positive_rules": [{"points": 50, "description": "自定义KOL规则"}],
            "negative_rules": [{"points": -50, "description": "自定义KOL扣分"}],
            "thresholds": [{"min": 0, "max": 100, "level": "medium", "label": "全部待核验"}],
        }
        client.put("/scoring/rules", params={"lead_type": "kol"}, json=kol_custom)

        distributor_after = client.get("/scoring/rules").json()
        kol_after = client.get("/scoring/rules", params={"lead_type": "kol"}).json()
        assert distributor_after == distributor_defaults
        assert kol_after["positive_rules"][0]["description"] == "自定义KOL规则"


def test_leads_filter_by_lead_type(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Dr. Filter Test",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "surgeon@filter-test.example",
                    "lead_type": "kol",
                    "score": 80,
                },
                {
                    "company_name": "Filter Test Distribution",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@filter-test-distribution.example",
                    "lead_type": "distributor",
                    "score": 80,
                },
            ],
        )

        kol_only = client.get("/leads", params={"lead_type": "kol"}).json()
        distributor_only = client.get("/leads", params={"lead_type": "distributor"}).json()

    assert kol_only["total"] == 1
    assert kol_only["leads"][0]["company_name"] == "Dr. Filter Test"
    assert distributor_only["total"] == 1
    assert distributor_only["leads"][0]["company_name"] == "Filter Test Distribution"


def test_batch_create_leads_infers_and_persists_lead_type_when_unset(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Auto Infer Distribution Co",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@auto-infer-distribution.example",
                    "category": "orthopedic implant distributor",
                    "score": 70,
                }
            ],
        )

    # lead_type wasn't supplied — insert_lead must resolve and persist it,
    # not leave it blank for every downstream query/dashboard to re-infer.
    assert created.json()["leads"][0]["lead_type"] == "distributor"


def test_dashboard_metrics_break_down_leads_by_type(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        # "已确认" now means human-confirmed; turn on auto-confirm so strong-match
        # leads land in 'qualified' and the qualified counters are exercised.
        client.put("/settings", json={"auto_confirm_strong": True})
        client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Metrics KOL",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "kol@metrics-test.example",
                    "lead_type": "kol",
                    "score": 90,
                },
                {
                    "company_name": "Metrics Distributor",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "dist@metrics-test.example",
                    "lead_type": "distributor",
                    "score": 90,
                },
            ],
        )
        metrics = client.get("/metrics").json()

    assert metrics["kol_leads"] >= 1
    assert metrics["distributor_leads"] >= 1
    assert metrics["kol_qualified"] >= 1
    assert metrics["distributor_qualified"] >= 1


def test_leads_sort_multiple_fields(tmp_path, monkeypatch):
    """
    /leads should honour ?sort=&order= for every whitelisted column, fall back
    to id on unknown fields, and apply created_at DESC as a stable tiebreaker
    within score/status/… ties.
    """
    with _client(tmp_path, monkeypatch) as client:
        # Insert leads in a known order. Batch keeps insertion sequential so
        # created_at strictly increases along the array, letting us reason about
        # tiebreakers by id order.
        payload = [
            {"company_name": "Alpha Ortho",  "region": "Europe", "country": "Germany",
             "email": "a@alpha.example", "score": 60},
            {"company_name": "Bravo Med",    "region": "Europe", "country": "France",
             "email": "b@bravo.example",   "score": 90},
            {"company_name": "Charlie Bio",  "region": "Asia",   "country": "Japan",
             "email": "c@charlie.example", "score": 90},   # ties with Bravo on score
            {"company_name": "Delta Robotics","region": "Asia",  "country": "India",
             "email": "d@delta.example",   "score": 75},
        ]
        created = client.post("/leads/batch", json=payload)
        assert created.status_code == 201
        ids = [lead["id"] for lead in created.json()["leads"]]
        assert len(ids) == 4

        # 1) score DESC with tie: 90 (Charlie, newer) → 90 (Bravo) → 75 → 60
        resp = client.get("/leads", params={"sort": "score", "order": "desc"})
        assert resp.status_code == 200
        names = [lead["company_name"] for lead in resp.json()["leads"]]
        assert names == ["Charlie Bio", "Bravo Med", "Delta Robotics", "Alpha Ortho"]

        # 2) created_at ASC: oldest first, matches insertion order
        resp = client.get("/leads", params={"sort": "created_at", "order": "asc"})
        assert resp.status_code == 200
        names_asc = [lead["company_name"] for lead in resp.json()["leads"]]
        assert names_asc == ["Alpha Ortho", "Bravo Med", "Charlie Bio", "Delta Robotics"]

        # 3) company_name ASC — SQLite BINARY sort on the leading ASCII letter.
        resp = client.get("/leads", params={"sort": "company_name", "order": "asc"})
        names_alpha = [lead["company_name"] for lead in resp.json()["leads"]]
        assert names_alpha == sorted(names_alpha)

        # 4) Unknown sort key falls back to id DESC (default behaviour preserved).
        resp = client.get("/leads", params={"sort": "email", "order": "desc"})
        ids_returned = [lead["id"] for lead in resp.json()["leads"]]
        assert ids_returned == sorted(ids, reverse=True)

        # 5) Invalid order value falls back to DESC (case-insensitive comparison).
        resp = client.get("/leads", params={"sort": "score", "order": "GIBBERISH"})
        scores = [lead["score"] for lead in resp.json()["leads"]]
        assert scores == sorted(scores, reverse=True)

        # 6) reply_count DESC — insert two replies against Alpha Ortho, one
        # against Delta, none for the rest. Alpha should sort first.
        from app.db import insert_reply_analysis
        from app.services import ReplyAnalysis
        stub = ReplyAnalysis(
            intent="interested", confidence=0.9, summary="", next_action="",
            requires_human=False,
        )
        alpha_id = created.json()["leads"][0]["id"]
        delta_id = created.json()["leads"][3]["id"]
        insert_reply_analysis(lead_id=alpha_id, reply_text="reply 1", analysis=stub)
        insert_reply_analysis(lead_id=alpha_id, reply_text="reply 2", analysis=stub)
        insert_reply_analysis(lead_id=delta_id, reply_text="reply 3", analysis=stub)

        resp = client.get("/leads", params={"sort": "reply_count", "order": "desc"})
        rows = resp.json()["leads"]
        assert rows[0]["company_name"] == "Alpha Ortho"
        assert rows[0]["reply_count"] == 2
        assert rows[1]["company_name"] == "Delta Robotics"
        assert rows[1]["reply_count"] == 1
        assert rows[2]["reply_count"] == 0 and rows[3]["reply_count"] == 0


def test_leads_filter_by_country(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post(
            "/leads/batch",
            json=[
                {
                    "company_name": "Germany Country Filter Co",
                    "region": "Europe",
                    "country": "Germany",
                    "email": "sales@germany-country-filter.example",
                    "score": 80,
                },
                {
                    "company_name": "Singapore Country Filter Co",
                    "region": "Southeast Asia",
                    "country": "Singapore",
                    "email": "sales@singapore-country-filter.example",
                    "score": 80,
                },
            ],
        )

        germany_only = client.get("/leads", params={"country": "Germany"}).json()
        singapore_only = client.get("/leads", params={"country": "Singapore"}).json()
        no_filter = client.get("/leads").json()

    assert germany_only["total"] == 1
    assert germany_only["leads"][0]["company_name"] == "Germany Country Filter Co"
    assert singapore_only["total"] == 1
    assert singapore_only["leads"][0]["company_name"] == "Singapore Country Filter Co"
    assert no_filter["total"] == 2


# ── AI token usage monitoring ─────────────────────────────────────────────────

def test_token_usage_report_defaults_to_no_budget(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/usage/token-report")

    assert resp.status_code == 200
    body = resp.json()
    assert body["used_tokens"] == 0
    assert body["budget_tokens"] == 0
    assert body["remaining_tokens"] is None
    assert body["percent_used"] is None
    assert body["by_source"] == {}
    assert body["daily_series"] == []


def test_agent_reports_token_usage_and_report_aggregates_it(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        recorded = client.post(
            "/usage/token-events",
            json={
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
            },
        )
        assert recorded.status_code == 200

        report = client.get("/usage/token-report").json()

    assert report["used_tokens"] == 150
    assert report["by_source"] == {"agent_chat": 150}


def test_token_budget_update_computes_remaining_and_percent(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post(
            "/usage/token-events",
            json={
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "prompt_tokens": 8000,
                "completion_tokens": 2000,
                "total_tokens": 10000,
            },
        )

        updated = client.put("/usage/token-budget", json={"budget_tokens": 100000}).json()

    assert updated["budget_tokens"] == 100000
    assert updated["used_tokens"] == 10000
    assert updated["remaining_tokens"] == 90000
    assert updated["percent_used"] == 10.0


def test_token_usage_requires_settings_manage_for_report_and_budget(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        role = client.post(
            "/admin/roles", json={"name": "usage-blind", "permissions": ["leads.view"]}
        ).json()
        client.post(
            "/admin/users",
            json={"username": "usage_blind", "password": "blind1234", "role_ids": [role["id"]]},
        )

    from app.main import create_app as _create_app

    with TestClient(_create_app()) as c2:
        _authenticate(c2, "usage_blind", "blind1234")
        assert c2.get("/usage/token-report").status_code == 403
        assert c2.put("/usage/token-budget", json={"budget_tokens": 1000}).status_code == 403


def test_token_usage_event_requires_agent_use_permission(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        role = client.post(
            "/admin/roles", json={"name": "no-agent-use", "permissions": ["leads.view"]}
        ).json()
        client.post(
            "/admin/users",
            json={"username": "no_agent_use", "password": "noagent123", "role_ids": [role["id"]]},
        )

    from app.main import create_app as _create_app

    with TestClient(_create_app()) as c2:
        _authenticate(c2, "no_agent_use", "noagent123")
        resp = c2.post(
            "/usage/token-events",
            json={
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        )
        assert resp.status_code == 403
