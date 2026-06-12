from dataclasses import dataclass
from itertools import cycle


@dataclass(frozen=True)
class CandidateLead:
    company_name: str
    region: str
    country: str
    website: str
    contact_name: str
    email: str
    category: str
    match_reason: str
    source: str
    score: int
    status: str = "new"
    notes: str = ""


@dataclass(frozen=True)
class RenderedEmail:
    sent_to: str
    subject: str
    body: str
    region: str


@dataclass(frozen=True)
class ReplyAnalysis:
    intent: str
    confidence: float
    summary: str
    next_action: str
    requires_human: bool


def generate_candidate_leads(
    target_regions: list[str],
    product_keywords: list[str],
    max_results: int = 8,
) -> list[CandidateLead]:
    regions = [region.strip() for region in target_regions if region.strip()]
    keywords = [keyword.strip() for keyword in product_keywords if keyword.strip()]
    if not regions:
        regions = ["Southeast Asia"]
    if not keywords:
        keywords = ["surgical robotics"]

    results: list[CandidateLead] = []
    region_cycle = cycle(regions)
    keyword_cycle = cycle(keywords)

    for index in range(max(0, max_results)):
        region = next(region_cycle)
        keyword = next(keyword_cycle)
        profile = _region_profile(region)
        company_suffix = index + 1
        category = _category_for_keyword(keyword)
        score = min(98, 72 + (index % 5) * 4 + profile["score_bonus"])
        company_slug = f"{profile['code']}-medtech-{company_suffix}"
        contact_name = profile["contacts"][index % len(profile["contacts"])]

        results.append(
            CandidateLead(
                company_name=f"{profile['market_name']} MedTech Partners {company_suffix}",
                region=region,
                country=profile["countries"][index % len(profile["countries"])],
                website=f"https://www.{company_slug}.example.com",
                contact_name=contact_name,
                email=f"{contact_name.lower().replace(' ', '.')}@{company_slug}.example.com",
                category=category,
                match_reason=(
                    f"Matches {keyword} through {category}; has hospital channel coverage "
                    f"in {region} and likely experience with capital equipment sales."
                ),
                source=f"demo::{region.lower().replace(' ', '-')}",
                score=score,
            )
        )

    return results


def render_email(lead: CandidateLead) -> RenderedEmail:
    """Generate outreach email. Uses AI if agent is configured, otherwise falls back to template."""
    ai_result = _try_ai_email(lead)
    if ai_result:
        return ai_result
    return _render_template_email(lead)


def _render_template_email(lead: CandidateLead) -> RenderedEmail:
    subject = f"{lead.region} partnership discussion for SkyWalker TKA robotics"
    body = (
        f"Hi {lead.contact_name},\n\n"
        f"I am reaching out because {lead.company_name} appears active in {lead.country}'s "
        f"{lead.category} channel. We are mapping overseas partners for the SkyWalker Robotic "
        "Platform Total Knee Application, a CT-based orthopedic robotics system for TKA workflows, "
        "patient-specific planning, intra-op adjustment, and robotically located cutting planes.\n\n"
        "If this is relevant, we can share an introductory product brief, product video, regulatory "
        "status overview, and a short partner qualification form.\n\n"
        "Best regards,\n"
        "Overseas Business Development Team"
    )
    return RenderedEmail(sent_to=lead.email, subject=subject, body=body, region=lead.region)


def _try_ai_email(lead: CandidateLead) -> RenderedEmail | None:
    """Generate email using the configured AI agent. Returns None on failure."""
    try:
        from app.db import get_all_settings
        settings = get_all_settings()
        provider = settings.get("agent_provider", "").lower()
        api_key = settings.get("agent_key", "")
        model = settings.get("agent_model", "deepseek-v4-pro")

        if not api_key or not provider:
            return None

        if provider == "deepseek":
            api_url = "https://api.deepseek.com/v1/chat/completions"
            # deepseek-chat is more reliable for structured JSON output
            if "v4" in model or "pro" in model:
                model = "deepseek-chat"
        elif provider == "openai":
            api_url = "https://api.openai.com/v1/chat/completions"
        else:
            api_url = f"https://api.deepseek.com/v1/chat/completions"
            model = "deepseek-chat"

        import requests
        prompt = _build_email_prompt(lead)
        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an overseas BD assistant. Write concise, professional cold outreach emails in English. Return ONLY a JSON object with 'subject' and 'body' fields, no other text."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 600,
            },
            timeout=20,
        )

        if resp.status_code != 200:
            return None

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON from response
        import json, re
        # Strip markdown code fences if present
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        parsed = json.loads(content)

        subject = str(parsed.get("subject", "")).strip()
        body = str(parsed.get("body", "")).strip()
        if not subject or not body:
            return None

        return RenderedEmail(sent_to=lead.email, subject=subject, body=body, region=lead.region)

    except Exception:
        return None


def _build_email_prompt(lead: CandidateLead) -> str:
    return f"""Write a brief cold outreach email for:

Company: {lead.company_name}
Contact: {lead.contact_name}
Country: {lead.country}
Region: {lead.region}
Category: {lead.category}
Match reason: {lead.match_reason}

Product: SkyWalker Robotic Platform Total Knee Application — CT-based orthopedic robotics system for TKA workflows, patient-specific planning, intra-op adjustment, and robotically located cutting planes.

Requirements:
- Short greeting with contact name
- One sentence why they were selected
- Brief product intro
- Call to action: offer product brief and qualification call
- Professional, not salesy
- Return JSON: {{"subject": "...", "body": "..."}}"""


def analyze_reply(reply_text: str) -> ReplyAnalysis:
    ai_result = _try_ai_reply_analysis(reply_text)
    if ai_result:
        return ai_result
    return _keyword_analyze_reply(reply_text)


def _try_ai_reply_analysis(reply_text: str) -> ReplyAnalysis | None:
    """Use the configured LLM to analyze reply intent. Returns None on failure."""
    try:
        from app.db import get_all_settings
        settings = get_all_settings()
        provider = settings.get("agent_provider", "").lower()
        api_key = settings.get("agent_key", "")
        model = settings.get("agent_model", "deepseek-v4-pro")

        if not api_key or not provider:
            return None

        if provider == "deepseek":
            api_url = "https://api.deepseek.com/v1/chat/completions"
        elif provider == "openai":
            api_url = "https://api.openai.com/v1/chat/completions"
        else:
            return None

        import requests, json, re

        prompt = f"""Analyze this prospect reply email and classify the intent. Reply text:

\"\"\"
{reply_text[:2000]}
\"\"\"

Return ONLY a JSON object with these fields:
- intent: one of "interested", "rejected", "complex", "needs_review"
- confidence: number between 0 and 1
- summary: one short sentence in Chinese summarizing what the reply means
- next_action: one short sentence in Chinese about what to do next
- requires_human: boolean, true if the reply involves legal/contract/exclusivity/tender matters that need human review

Rules:
- "interested": asks for product details, pricing, catalog, certificates, meeting, call, or shows clear interest
- "rejected": not interested, unsubscribe, remove, no fit
- "complex": involves legal, exclusivity, tender, contract, liability, payment terms, regulatory ownership
- "needs_review": ambiguous, unclear, or doesn't fit the above categories

Important: The reply may be in Chinese, English, or any language. Judge by meaning, not by keyword matching."""

        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a business reply classifier. Return ONLY valid JSON, no other text."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 300,
            },
            timeout=20,
        )

        if resp.status_code != 200:
            return None

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        parsed = json.loads(content)

        intent = str(parsed.get("intent", "")).lower()
        if intent not in ("interested", "rejected", "complex", "needs_review"):
            return None

        return ReplyAnalysis(
            intent=intent,
            confidence=float(parsed.get("confidence", 0.7)),
            summary=str(parsed.get("summary", ""))[:500],
            next_action=str(parsed.get("next_action", ""))[:500],
            requires_human=bool(parsed.get("requires_human", False)),
        )

    except Exception:
        return None


def _keyword_analyze_reply(reply_text: str) -> ReplyAnalysis:
    text = reply_text.strip()
    lowered = text.lower()

    if _contains_any(lowered, ["not interested", "remove us", "unsubscribe", "do not contact"]):
        return ReplyAnalysis(
            intent="rejected",
            confidence=0.9,
            summary="The recipient declined further outreach.",
            next_action="Mark as do not contact and stop outreach.",
            requires_human=False,
        )

    if _contains_any(
        lowered,
        [
            "exclusive",
            "tender",
            "legal",
            "contract",
            "registration ownership",
            "regulatory registration",
            "liability",
            "payment terms",
        ],
    ):
        return ReplyAnalysis(
            intent="complex",
            confidence=0.84,
            summary="The reply includes commercial, regulatory, or legal terms that need review.",
            next_action="Escalate to a human overseas business owner before responding.",
            requires_human=True,
        )

    if _contains_any(
        lowered,
        ["interested", "send", "share", "details", "pricing", "certificate", "catalog", "product"],
    ):
        return ReplyAnalysis(
            intent="interested",
            confidence=0.78,
            summary="The recipient asked for more information or showed interest.",
            next_action="Send the introductory product brief and ask to schedule a qualification call.",
            requires_human=False,
        )

    return ReplyAnalysis(
        intent="needs_review",
        confidence=0.58,
        summary="The reply is ambiguous and does not clearly accept or reject the outreach.",
        next_action="Route to a human for quick review or request clarification.",
        requires_human=True,
    )


def _region_profile(region: str) -> dict[str, object]:
    profiles: dict[str, dict[str, object]] = {
        "southeast asia": {
            "market_name": "ASEAN",
            "code": "asean",
            "countries": ["Singapore", "Thailand", "Malaysia", "Indonesia"],
            "contacts": ["Maya Tan", "Arun Lim", "Nina Rahman"],
            "score_bonus": 6,
        },
        "europe": {
            "market_name": "Euro",
            "code": "euro",
            "countries": ["Germany", "France", "Spain", "Italy"],
            "contacts": ["Anna Keller", "Marc Dubois", "Elena Rossi"],
            "score_bonus": 4,
        },
        "middle east": {
            "market_name": "Gulf",
            "code": "gulf",
            "countries": ["United Arab Emirates", "Saudi Arabia", "Qatar"],
            "contacts": ["Omar Haddad", "Leila Mansour", "Samir Nasser"],
            "score_bonus": 5,
        },
        "latin america": {
            "market_name": "LatAm",
            "code": "latam",
            "countries": ["Brazil", "Mexico", "Chile", "Colombia"],
            "contacts": ["Ana Silva", "Diego Torres", "Lucia Perez"],
            "score_bonus": 3,
        },
        "north america": {
            "market_name": "NorthAm",
            "code": "northam",
            "countries": ["United States", "Canada"],
            "contacts": ["Jordan Miller", "Casey Wilson", "Morgan Lee"],
            "score_bonus": 2,
        },
    }
    default_profile = {
        "market_name": "Global",
        "code": "global",
        "countries": [region],
        "contacts": ["Alex Chen", "Jamie Park", "Taylor Lin"],
        "score_bonus": 1,
    }
    return profiles.get(region.lower(), default_profile)


def _category_for_keyword(keyword: str) -> str:
    lowered = keyword.lower()
    if "robot" in lowered:
        return "surgical robotics distributor"
    if "hospital" in lowered:
        return "hospital equipment distributor"
    if "laparoscopic" in lowered or "minimally invasive" in lowered:
        return "minimally invasive surgery channel"
    return "medical device distributor"


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)
