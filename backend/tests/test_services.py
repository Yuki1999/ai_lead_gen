from app.services import (
    analyze_reply,
    generate_candidate_leads,
    render_email,
)


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


def test_render_email_uses_region_and_contact_context():
    lead = generate_candidate_leads(
        target_regions=["Middle East"],
        product_keywords=["minimally invasive robot"],
        max_results=1,
    )[0]

    email = render_email(lead)

    assert lead.contact_name in email.body
    assert lead.country in email.body
    assert "Middle East" in email.subject
    assert lead.email == email.sent_to
    assert "introductory product brief" in email.body.lower()


def test_analyze_reply_marks_interest_and_product_brief_next_action():
    result = analyze_reply(
        "Thanks for reaching out. We are interested and would like more product details, pricing, and certificates."
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
    assert "human" in result.next_action.lower()


def test_analyze_reply_detects_rejection():
    result = analyze_reply("Not interested. Please remove us from your list.")

    assert result.intent == "rejected"
    assert result.requires_human is False
    assert "do not contact" in result.next_action.lower()

