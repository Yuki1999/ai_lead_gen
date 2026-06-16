from dataclasses import dataclass
from itertools import cycle

DEFAULT_EMAIL_TEMPLATE = """\
Subject: [Role] Introduction – MEDBOT NaviBot Skywalker Orthopedic Robot for [Target Market]

Dear [Name],

[IfDistributor]We understand you have strong relationships with high-volume orthopedic centers and KOLs in [Target Market]. MEDBOT is seeking regional distribution partners to introduce the NaviBot Skywalker into the [Target Market] market.[/IfDistributor]

[IfBuyer]We understand your center is committed to improving joint replacement outcomes. MEDBOT's NaviBot Skywalker is a surgical robotics platform designed for high-compatibility joint reconstruction.[/IfBuyer]

Common product description (for both):
The system offers:
- Sub-millimeter accuracy
- Personalized preoperative planning (CT-based)
- Integrated cutting block for efficient osteotomy

If you are interested, please reply to this email and a dedicated person will contact you. We can then learn about the current joint replacement landscape in [Target Market], your clinical training workflows and KOL networks, and explore potential distribution or collaboration models.

Thank you for your time.
Best regards,
SkyWalker Sales Team
MEDBOT"""


DEFAULT_SCORING_RULES = """\
Start from 0 and apply the rules below.

Positive scoring:
- +25 if the official site confirms medical device distribution, importation, or channel sales.
- +20 if the company has clear orthopedic implants, joint replacement, knee arthroplasty, surgical equipment, robotics, navigation, or OR capital equipment relevance.
- +15 if a visible business email or official contact form is available.
- +15 if the company's country or regional coverage matches the target market.
- +10 if a named business development, sales, product, or distributor contact is available.
- +10 if the company appears in a manufacturer partner page, official exhibitor list, regulatory/importer directory, or medical device association directory.
- +5 if the company has multi-country coverage that is relevant to the target region.

Negative scoring:
- -20 if source evidence is weak or incomplete.
- -20 if only LinkedIn/social/trade-directory evidence is available and no official site confirmation exists.
- -30 if the company is unrelated to healthcare robotics, orthopedic devices, medical distribution, surgical equipment, or hospital equipment.
- -30 if the company appears to be hospital-only, media-only, consultant-only, job-board-only, consumer-only, or unrelated industrial robotics.
- -40 if the lead is a confirmed duplicate.

Clamp score to 0–100.

Recommended interpretation:
| Score  | Meaning                          | Usual Status   |
| ------ | -------------------------------- | -------------- |
| 80–100 | Strong fit                        | qualified      |
| 60–79  | Good / medium fit                 | new or human_review |
| 40–59  | Possible fit, needs verification  | human_review   |
| Below 40 | Weak fit or reject              | rejected       |

Do not force a high score. A company with broad medical device distribution but no orthopedic evidence should normally be medium-fit or human-review."""


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
    """Generate outreach email using template + LLM variable filling."""
    from app.db import get_all_settings
    settings = get_all_settings()
    template = settings.get("email_template", "").strip() or DEFAULT_EMAIL_TEMPLATE

    ai_result = _fill_template_with_llm(lead, template)
    if ai_result:
        return ai_result
    return _fill_template_simple(lead, template)


def _fill_template_simple(lead: CandidateLead, template: str) -> RenderedEmail:
    """Fill template variables without LLM (fallback when AI unavailable)."""
    import re

    category_lower = lead.category.lower() if lead.category else ""
    is_distributor = any(kw in category_lower for kw in ["distributor", "dealer", "reseller", "distribution", "代理"])

    role = "Distributor" if is_distributor else "Buyer"

    # Remove condition blocks for the irrelevant role
    if is_distributor:
        template = re.sub(r"\[IfBuyer\].*?\[/IfBuyer\]", "", template, flags=re.DOTALL)
        template = re.sub(r"\[/IfDistributor\]", "", template)
        template = re.sub(r"\[IfDistributor\]", "", template)
    else:
        template = re.sub(r"\[IfDistributor\].*?\[/IfDistributor\]", "", template, flags=re.DOTALL)
        template = re.sub(r"\[/IfBuyer\]", "", template)
        template = re.sub(r"\[IfBuyer\]", "", template)

    name = lead.contact_name.strip() if lead.contact_name else "Sir/Madam"
    country = lead.country or lead.region
    company = lead.company_name

    template = template.replace("[Name]", name)
    template = template.replace("[Role]", role)
    template = template.replace("[Target Market]", country)
    template = template.replace("[Company]", company)

    subject = ""
    body = template
    if template.lower().startswith("subject:"):
        lines = template.split("\n", 1)
        subject = lines[0][8:].strip()
        body = lines[1].strip() if len(lines) > 1 else ""

    return RenderedEmail(sent_to=lead.email, subject=subject, body=body, region=lead.region)


def _resolve_llm_api_url(settings: dict[str, str]) -> str | None:
    """Resolve the chat completions endpoint. Uses api_base_url if configured, otherwise provider default."""
    provider = settings.get("agent_provider", "").lower()
    custom_base = settings.get("api_base_url", "").strip().rstrip("/")
    if custom_base:
        return f"{custom_base}/chat/completions"

    if provider == "openai":
        return "https://api.openai.com/v1/chat/completions"
    if provider == "deepseek" or provider:
        return "https://api.deepseek.com/chat/completions"
    return None


def _fill_template_with_llm(lead: CandidateLead, template: str) -> RenderedEmail | None:
    """Use LLM to fill template variables (including [Role] determination). Returns None on failure."""
    try:
        from app.db import get_all_settings
        settings = get_all_settings()
        provider = settings.get("agent_provider", "").lower()
        api_key = settings.get("agent_key", "")
        model = settings.get("agent_model", "deepseek-v4-pro")

        if not api_key or not provider:
            return None

        api_url = _resolve_llm_api_url(settings)
        if not api_url:
            return None

        if provider == "deepseek" and ("v4" in model or "pro" in model):
            model = "deepseek-chat"

        import requests, json as json_mod, re as re_mod

        system_prompt = (
            "You are an overseas BD email assistant for MEDBOT. "
            "Given a lead profile and an email template with placeholders, fill in the template to produce a complete, ready-to-send cold outreach email.\n\n"
            "RULES:\n"
            "1. Replace [Name] with the contact name. If empty, use 'Sir/Madam'.\n"
            "2. Replace [Target Market] with the lead's country.\n"
            "3. Replace [Company] with the lead's company name.\n"
            "4. Determine [Role] from the lead's 'category' field:\n"
            "   - If category suggests a distributor/dealer/reseller -> use 'Distributor'\n"
            "   - Otherwise -> use 'Buyer' (hospital, clinic, procurement)\n"
            "5. Remove the irrelevant [IfDistributor]...[/IfDistributor] or [IfBuyer]...[/IfBuyer] block based on the determined role.\n"
            "   - If role is Distributor, keep the [IfDistributor] block content and remove the [IfBuyer] tags and content entirely.\n"
            "   - If role is Buyer, keep the [IfBuyer] block content and remove the [IfDistributor] tags and content entirely.\n"
            "6. Keep all other text exactly as-is. NEVER add content not in the template.\n\n"
            "Return ONLY a JSON object: {\"subject\": \"...\", \"body\": \"...\"}, no other text."
        )

        user_prompt = (
            f"LEAD PROFILE:\n"
            f"company_name: {lead.company_name}\n"
            f"contact_name: {lead.contact_name or 'N/A'}\n"
            f"country: {lead.country}\n"
            f"region: {lead.region}\n"
            f"category: {lead.category}\n"
            f"website: {lead.website}\n\n"
            f"TEMPLATE:\n{template}"
        )

        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 800,
            },
            timeout=25,
        )

        if resp.status_code != 200:
            return None

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        content = re_mod.sub(r"^```(?:json)?\s*", "", content)
        content = re_mod.sub(r"\s*```$", "", content)
        parsed = json_mod.loads(content)

        subject = str(parsed.get("subject", "")).strip()
        body = str(parsed.get("body", "")).strip()
        if not subject or not body:
            return None

        return RenderedEmail(sent_to=lead.email, subject=subject, body=body, region=lead.region)

    except Exception:
        return None


def _strip_quoted_reply(text: str) -> str:
    """Extract only the new reply content, removing quoted original email and signatures.

    Handles common reply delimiters in Chinese and English:
    - ---原始邮件--- / ---Original Message---
    - On ... wrote: / 发件人: ... 发送时间:
    - -----Original Message-----
    """
    # Split on common reply markers — keep only the part above them
    markers = [
        "\n---原始邮件---",
        "\n---Original Message---",
        "\n-----Original Message-----",
        "\n> ",  # inline quote prefix
        "\n发件人:",  # Chinese email client header
        "\nFrom:",
        "\nOn ",  # "On ... wrote:"
    ]
    for marker in markers:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]
    return text.strip()


# High-risk terms that MUST escalate to human regardless of LLM judgment.
# This is NOT keyword classification — it's a safety net for cases the LLM
# might miss (e.g., exclusive agency demands buried in a friendly reply).
_MUST_ESCALATE_TERMS = [
    "独家代理", "独家经销", "排他", "exclusive distribution", "exclusive agency",
    "招标", "投标", "tender", "rfp", "rfq",
    "注册转移", "registration transfer",
    "合资", "joint venture",
]


def _has_escalation_signal(text: str) -> bool:
    """Check for high-risk terms that must escalate to human."""
    lowered = text.lower()
    return any(term in lowered for term in _MUST_ESCALATE_TERMS)


def analyze_reply(reply_text: str) -> ReplyAnalysis:
    # Strip quoted original email
    clean_text = _strip_quoted_reply(reply_text)
    if not clean_text:
        clean_text = reply_text.strip()

    ai_result = _try_ai_reply_analysis(clean_text)
    if ai_result:
        # Safety net: high-risk terms always escalate
        if _has_escalation_signal(clean_text):
            return ReplyAnalysis(
                intent=ai_result.intent,
                confidence=ai_result.confidence,
                summary=ai_result.summary,
                next_action="Escalate to human: contains exclusivity/tender/regulatory transfer demands.",
                requires_human=True,
            )
        return ai_result

    # LLM unavailable — safety net still applies
    if _has_escalation_signal(clean_text):
        return ReplyAnalysis(
            intent="needs_review",
            confidence=0.85,
            summary="Reply contains high-risk commercial/legal terms (exclusivity, tender, regulatory transfer).",
            next_action="Escalate to human overseas business owner immediately.",
            requires_human=True,
        )

    return ReplyAnalysis(
        intent="needs_review",
        confidence=0.5,
        summary="AI reply analysis unavailable — unable to classify automatically.",
        next_action="Check agent_key in settings and re-analyze, or review manually.",
        requires_human=False,
    )


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

        api_url = _resolve_llm_api_url(settings)
        if not api_url:
            return None

        import requests, json, re

        system_prompt = """You are a reply classifier for an overseas medical device business (MicroPort SkyWalker TKA surgical robot). You analyze prospect replies to cold outreach emails.

CONTEXT:
- We contact potential overseas distributors
- AI handles: sending brochures, certificates, pricing, scheduling calls
- Human salespeople handle ONLY: legal/commercial complexity that AI cannot resolve
- "转人工" is expensive — only escalate when absolutely necessary

CRITICAL RULE — requires_human:
Set requires_human = true ONLY when the reply explicitly demands:
- Exclusive distribution rights / 独家代理 / 排他
- Formal tender / RFP / 招标 / 投标
- Regulatory ownership transfer / 注册转移
- Contract negotiation / 合同条款
- Complex payment terms / 信用证 / 付款条件
- Joint venture / 合资 / 当地生产

Even if the prospect also shows interest, the presence of these triggers means requires_human = true.
When a prospect says both "有兴趣" AND "独家代理" → requires_human = true."""

        prompt = f"""Classify this prospect reply. Reply text:

\"\"\"
{reply_text[:2000]}
\"\"\"

Return ONLY a JSON object:
{{"intent": "<interested|rejected|needs_review>", "confidence": <0-1>, "summary": "<1 Chinese sentence>", "next_action": "<1 Chinese sentence>", "requires_human": <bool>}}

INTENT:
- "interested": shows interest, asks for info, pricing, catalog, demo, meeting. Including: 有兴趣, 发资料, 请发, 想了解, 好的, 看看, 了解一下, send details, interested
- "rejected": clearly declines: 不感兴趣, 不需要, not interested, unsubscribe, 别再发
- "needs_review": ambiguous, auto-reply, out-of-office, or doesn't clearly fit above

REQUIRES_HUMAN (be strict):
- true ONLY when reply demands: 独家代理, exclusive distribution, 招标, tender, 注册转移, registration transfer, 合同, contract, 合资, joint venture, 付款条件, payment terms
- false for ALL other cases — including simple interest, asking for info, auto-replies, vague replies
- When in doubt, default to false"""

        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
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

        # Map legacy "complex" intent to "needs_review" with requires_human
        requires_human = bool(parsed.get("requires_human", False))
        if intent == "complex":
            intent = "needs_review"
            requires_human = True

        # SAFEGUARD: interested replies never require human — even if LLM hallucinates
        if intent == "interested":
            requires_human = False

        return ReplyAnalysis(
            intent=intent,
            confidence=float(parsed.get("confidence", 0.7)),
            summary=str(parsed.get("summary", ""))[:500],
            next_action=str(parsed.get("next_action", ""))[:500],
            requires_human=requires_human,
        )

    except Exception:
        return None


def generate_followup(lead: CandidateLead, reply_text: str) -> RenderedEmail | None:
    """Generate a follow-up email based on a customer reply. Returns None on failure."""
    try:
        from app.db import get_all_settings
        settings = get_all_settings()
        provider = settings.get("agent_provider", "").lower()
        api_key = settings.get("agent_key", "")
        model = settings.get("agent_model", "deepseek-v4-pro")

        if not api_key or not provider:
            return None

        api_url = _resolve_llm_api_url(settings)
        if not api_url:
            return None

        if provider == "deepseek" and ("v4" in model or "pro" in model):
            model = "deepseek-chat"

        import requests, json as json_mod, re as re_mod

        system_prompt = (
            "You are an overseas BD assistant for MEDBOT (SkyWalker TKA surgical robot). "
            "A prospect has replied to our cold outreach email. Based on their reply, write a professional follow-up email.\n\n"
            "RULES:\n"
            "- If they show interest: thank them, provide the requested info (brochure, certificates, pricing, demo), and suggest a call.\n"
            "- If they ask questions: answer concisely and offer to connect them with a specialist.\n"
            "- If they say no / not interested: politely thank them and leave the door open.\n"
            "- If ambiguous / auto-reply: keep it short, ask if they'd like more information.\n"
            "- Sign as 'SkyWalker Sales Team / MEDBOT'.\n"
            "- Keep it under 200 words, professional and warm.\n\n"
            "Return ONLY a JSON object: {\"subject\": \"...\", \"body\": \"...\"}, no other text."
        )

        user_prompt = (
            f"LEAD:\n"
            f"Company: {lead.company_name}\n"
            f"Contact: {lead.contact_name or 'N/A'}\n"
            f"Country: {lead.country}\n"
            f"Category: {lead.category}\n\n"
            f"CUSTOMER REPLY:\n{reply_text[:2000]}"
        )

        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 600,
            },
            timeout=25,
        )

        if resp.status_code != 200:
            return None

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        content = re_mod.sub(r"^```(?:json)?\s*", "", content)
        content = re_mod.sub(r"\s*```$", "", content)
        parsed = json_mod.loads(content)

        subject = str(parsed.get("subject", "")).strip()
        body = str(parsed.get("body", "")).strip()
        if not subject or not body:
            return None

        return RenderedEmail(sent_to=lead.email, subject=subject, body=body, region=lead.region)

    except Exception:
        return None


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


