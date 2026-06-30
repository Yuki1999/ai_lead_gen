import pytest

from app.services import (
    analyze_reply,
    generate_candidate_leads,
    render_email,
)


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Point services at an empty DB so unit tests never read a real agent key /
    hit a live LLM. These tests assert the deterministic keyword/template paths."""
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "test.db"))


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


def test_analyze_reply_marks_interest_without_trigger_topics():
    result = analyze_reply(
        "Thanks for reaching out. We are interested in the Skywalker system and would like to learn more. Who can we talk to?"
    )

    assert result.intent == "interested"
    assert result.requires_human is False
    assert "product brief" in result.next_action.lower()
    assert result.confidence >= 0.7


def test_analyze_reply_escalates_complex_regulatory_requests():
    result = analyze_reply(
        "We need exclusive distribution terms, tender commitments, regulatory registration ownership, and legal contract review."
    )

    assert result.intent == "complex"
    assert result.requires_human is True


def test_analyze_reply_escalates_pricing_and_certificate_requests():
    # Approved rules: price / 注册证 are human-review triggers even with interest.
    result = analyze_reply(
        "We are interested. Please send pricing and your registration certificate."
    )

    assert result.intent == "complex"
    assert result.requires_human is True


def test_analyze_reply_detects_rejection():
    result = analyze_reply("Not interested. Please remove us from your list.")

    assert result.intent == "rejected"
    assert result.requires_human is False
    assert "do not contact" in result.next_action.lower()

