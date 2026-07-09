import pytest

from app.services import (
    analyze_reply,
    generate_candidate_leads,
    render_email,
    resolve_content_ai,
)


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Point services at an empty DB so unit tests never read a real agent key /
    hit a live LLM. These tests assert the deterministic keyword/template paths."""
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "test.db"))
    # Also isolate the Pi sidecar env so the AI-content fallback can't resolve
    # a real key from the project's agent/.env during tests.
    monkeypatch.setenv("AGENT_ENV_PATH", str(tmp_path / "agent.env"))


def test_generate_candidate_leads_expands_regions_and_scores_matches():
    leads = generate_candidate_leads(
        target_regions=["Southeast Asia", "Europe"],
        product_keywords=["surgical robot", "hospital robotics"],
        max_results=5,
    )

    assert len(leads) == 5
    assert {lead.region for lead in leads} <= {"Southeast Asia", "Europe"}
    assert all(lead.email and "@" in lead.email for lead in leads)
    assert all(lead.score >= 70 for lead in leads)
    assert any("surgical robot" in lead.match_reason.lower() for lead in leads)


def test_render_email_uses_approved_template():
    lead = generate_candidate_leads(
        target_regions=["Middle East"],
        product_keywords=["minimally invasive robot"],
        max_results=1,
    )[0]

    email = render_email(lead)

    # Greeting + target market are personalized from the lead.
    assert lead.contact_name in email.body
    assert lead.country in email.body
    assert lead.country in email.subject
    assert lead.email == email.sent_to
    # Approved template markers: branded body, fixed CTA, unified signature.
    assert "MEDBOT NaviBot Skywalker" in email.body
    assert "reply to this email" in email.body.lower()
    assert "Skywalker Sales Team" in email.body


def test_render_email_kol_template_for_surgeon():
    from app.services import CandidateLead

    lead = CandidateLead(
        company_name="Netcare Linksfield Hospital",
        region="Africa",
        country="South Africa",
        website="https://example.org",
        contact_name="Dr. Chris McCready",
        email="dr.mccready@example.org",
        category="orthopedic surgeon / KOL",
        match_reason="First Mako TKA in Africa (2019); high-volume CT-based planning.",
        source="https://example.org",
        score=88,
    )

    email = render_email(lead)

    assert "Skywalker Total Knee System" in email.body
    assert "Dr. Chris McCready" in email.body
    assert "reply to this email" in email.body.lower()


def test_render_followup_email_nudge_then_value_add():
    from app.services import CandidateLead, render_followup_email

    lead = CandidateLead(
        company_name="Ortho Dist", region="Europe", country="Germany", website="",
        contact_name="Dr. Weber", email="w@ortho.example", category="distributor",
        match_reason="", source="", score=80, lead_type="distributor",
    )
    f1 = render_followup_email(lead, followup_number=1)
    assert f1.subject.startswith("Re:")
    assert "reply to this email" in f1.body.lower()
    assert "Skywalker Sales Team" in f1.body
    # A follow-up promises nothing commercial, same as the first touch.
    assert not any(w in f1.body.lower() for w in ("price", "exclusiv", "fda", "contract"))

    f2 = render_followup_email(lead, followup_number=2)
    assert "femoral canal" in f2.body.lower()  # value-add clinical highlight


# ── Reply analysis is LLM-only: no keyword fallback, error when unavailable ───

def test_analyze_reply_raises_without_llm():
    from app import db
    from app.services import ReplyAnalysisError

    db.init_db()  # no DB key; AGENT_ENV_PATH isolated by the autouse fixture
    with pytest.raises(ReplyAnalysisError):
        analyze_reply("We are interested, please send more info.")


def test_analyze_reply_raises_when_llm_call_fails(monkeypatch):
    import requests
    from app import db
    from app.services import ReplyAnalysisError

    db.init_db()
    db.set_setting("agent_provider", "deepseek")
    db.set_setting("agent_key", "test-key")

    class _Resp:
        status_code = 500
        text = "server error"

        def json(self):
            return {}

    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp())
    with pytest.raises(ReplyAnalysisError):
        analyze_reply("We are interested, please send more info.")


def test_analyze_reply_uses_llm_result_when_configured(monkeypatch):
    import requests
    from app import db

    db.init_db()
    db.set_setting("agent_provider", "deepseek")
    db.set_setting("agent_key", "test-key")

    fake = _FakeChatCompletion(
        '{"intent": "complex", "confidence": 0.9, "summary": "涉及价格与注册证", '
        '"next_action": "转人工", "requires_human": true}',
        {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
    )
    monkeypatch.setattr(requests, "post", lambda *a, **k: fake)

    result = analyze_reply("We are interested. Please send pricing and your registration certificate.")
    assert result.intent == "complex"
    assert result.requires_human is True


# ── AI token usage monitoring ─────────────────────────────────────────────────

class _FakeChatCompletion:
    def __init__(self, content: str, usage: dict):
        self.status_code = 200
        self._content = content
        self._usage = usage

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": self._usage,
        }


def test_try_ai_email_records_token_usage(monkeypatch):
    import requests
    from app import db

    db.init_db()
    db.set_setting("agent_provider", "deepseek")
    db.set_setting("agent_key", "test-key")

    fake = _FakeChatCompletion(
        '{"subject": "S", "body": "B"}',
        {"prompt_tokens": 500, "completion_tokens": 100, "total_tokens": 600},
    )
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: fake)

    lead = generate_candidate_leads(
        target_regions=["Europe"], product_keywords=["surgical robot"], max_results=1,
    )[0]

    email = render_email(lead)

    assert email.subject == "S"
    assert db.token_usage_total_since("1970-01-01T00:00:00+00:00") == 600
    assert db.token_usage_breakdown_since("1970-01-01T00:00:00+00:00") == {"email_generation": 600}


def test_try_ai_reply_analysis_records_token_usage(monkeypatch):
    import requests
    from app import db

    db.init_db()
    db.set_setting("agent_provider", "deepseek")
    db.set_setting("agent_key", "test-key")

    fake = _FakeChatCompletion(
        '{"intent": "interested", "confidence": 0.9, "summary": "s", '
        '"next_action": "n", "requires_human": false}',
        {"prompt_tokens": 200, "completion_tokens": 50, "total_tokens": 250},
    )
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: fake)

    result = analyze_reply("We are interested, please send more info.")

    assert result.intent == "interested"
    assert db.token_usage_total_since("1970-01-01T00:00:00+00:00") == 250
    assert db.token_usage_breakdown_since("1970-01-01T00:00:00+00:00") == {"reply_analysis": 250}



# ── resolve_content_ai: LLM primary, rules fallback, single-config reuse ──────

def test_resolve_content_ai_prefers_backend_settings():
    from app import db

    db.init_db()
    db.set_setting("agent_provider", "deepseek")
    db.set_setting("agent_key", "db-key")
    db.set_setting("agent_model", "deepseek-v4-pro")

    assert resolve_content_ai() == ("deepseek", "db-key", "deepseek-v4-pro")


def test_resolve_content_ai_falls_back_to_sidecar_env(tmp_path, monkeypatch):
    from app import db

    db.init_db()  # no backend agent_key set
    env = tmp_path / "agent.env"
    env.write_text("PI_PROVIDER=deepseek\nDEEPSEEK_API_KEY=sidecar-key\nPI_MODEL=deepseek-v4-pro\n")
    monkeypatch.setenv("AGENT_ENV_PATH", str(env))

    assert resolve_content_ai() == ("deepseek", "sidecar-key", "deepseek-v4-pro")


def test_resolve_content_ai_returns_none_when_disabled():
    from app import db

    db.init_db()
    db.set_setting("agent_provider", "deepseek")
    db.set_setting("agent_key", "db-key")
    db.set_setting("ai_content_generation", "false")

    assert resolve_content_ai() is None


def test_resolve_content_ai_returns_none_without_any_key():
    from app import db

    db.init_db()  # no DB key; AGENT_ENV_PATH isolated to an empty file by fixture
    assert resolve_content_ai() is None


# ── opt_out drives suppression (not a general "rejected" intent) ──────────────

def test_analyze_reply_parses_explicit_opt_out(monkeypatch):
    import requests
    from app import db

    db.init_db()
    db.set_setting("agent_provider", "deepseek")
    db.set_setting("agent_key", "test-key")
    fake = _FakeChatCompletion(
        '{"intent": "rejected", "confidence": 0.95, "summary": "对方要求退订", '
        '"next_action": "停止发送", "requires_human": false, "opt_out": true}',
        {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
    )
    monkeypatch.setattr(requests, "post", lambda *a, **k: fake)
    result = analyze_reply("Please unsubscribe me and do not contact us again.")
    assert result.intent == "rejected"
    assert result.opt_out is True


def test_analyze_reply_rejected_without_opt_out_defaults_false(monkeypatch):
    import requests
    from app import db

    db.init_db()
    db.set_setting("agent_provider", "deepseek")
    db.set_setting("agent_key", "test-key")
    # "not interested" but NO explicit unsubscribe → opt_out must default False,
    # so the address is not permanently suppressed.
    fake = _FakeChatCompletion(
        '{"intent": "rejected", "confidence": 0.8, "summary": "暂不感兴趣", '
        '"next_action": "季度后再联系", "requires_human": false}',
        {"prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 50},
    )
    monkeypatch.setattr(requests, "post", lambda *a, **k: fake)
    result = analyze_reply("Not interested right now, maybe next quarter.")
    assert result.intent == "rejected"
    assert result.opt_out is False
