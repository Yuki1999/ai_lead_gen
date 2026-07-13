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
    # "distributor" | "kol" | "" (auto-inferred when empty). Drives which approved
    # email template the system uses for outreach.
    lead_type: str = ""


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
    # True ONLY when the reply explicitly asks to stop / unsubscribe / be removed.
    # Auto-suppression keys off this — not off a general "rejected" intent — so a
    # merely-uninterested reply can't permanently block the address.
    opt_out: bool = False


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


# ── Approved outreach templates ──────────────────────────────────────────────
# Source: 客户提供的「MEDBOT NaviBot Skywalker 邮件模板文档 V2.0」(2026-06)。
# Two audiences (distributor / KOL), two languages (EN / CN), unified signature.

SIGNATURE_EN = "Skywalker Sales Team\nMEDBOT"
SIGNATURE_CN = "Skywalker 销售组\nMEDBOT"

# Four key product differentiators, kept verbatim per the approved copy.
DIFFERENTIATORS_EN = (
    "- A self-developed robotic arm that provides high dexterity alongside a lightweight design\n"
    "- An integrated cutting block designed specifically for efficient osteotomy\n"
    "- An open platform design – not only for MicroPort implants but also compatible with other brands\n"
    "- A patient safety profile that avoids opening the femoral canal, leading to less bleeding, "
    "faster patient recovery, and a low risk of infection"
)
DIFFERENTIATORS_CN = (
    "· 自主研发的机械臂，兼具高灵活性与轻量化设计\n"
    "· 专为高效截骨设计的一体化截骨导块\n"
    "· 开放平台设计——不仅适配微创植入物，也兼容其他品牌\n"
    "· 患者安全优势：无需打开股骨髓腔，出血更少、恢复更快、感染风险更低"
)

# Markets that should receive Chinese-language outreach. Everything else → English.
_CN_MARKETS = ("china", "中国", "中國", "taiwan", "台湾", "台灣", "hong kong", "香港", "macau", "澳门", "澳門")

_DISTRIBUTOR_KEYWORDS = (
    "distributor", "distribution", "dealer", "reseller", "channel", "channel partner",
    "trading", "import", "importer", "agent", "agency", "supply", "supplier",
    "medtech partners", "business development", "bd director", "bd manager",
    "经销", "代理", "渠道", "分销", "贸易", "供应",
)
_KOL_KEYWORDS = (
    "dr.", "dr ", "prof", "professor", "md,", " md", "surgeon", "orthopedic", "orthopaedic",
    "hospital", "clinic", "university", "chief", "head of", "department", "consultant",
    "procurement", "operating room", "or manager",
    "医生", "医师", "教授", "主任", "医院", "诊所", "骨科", "采购",
)


def infer_lead_type(lead: CandidateLead) -> str:
    """Return 'distributor' or 'kol'. Honors an explicit lead_type, else infers
    from category / contact / company text using the approved role-judgment rules."""
    explicit = (lead.lead_type or "").strip().lower()
    if explicit in ("distributor", "kol"):
        return explicit

    haystack = " ".join(
        [lead.category, lead.contact_name, lead.company_name, lead.match_reason, lead.notes]
    ).lower()

    if any(kw in haystack for kw in _KOL_KEYWORDS) and not any(
        kw in haystack for kw in _DISTRIBUTOR_KEYWORDS
    ):
        return "kol"
    if any(kw in haystack for kw in _DISTRIBUTOR_KEYWORDS):
        return "distributor"
    # Default to distributor — the historical and most common channel target.
    return "distributor"


def _email_language(lead: CandidateLead) -> str:
    """Pick outreach language by target market: Chinese for CN markets, else English."""
    market = f"{lead.country} {lead.region}".lower()
    return "cn" if any(m in market for m in _CN_MARKETS) else "en"


def render_email(lead: CandidateLead) -> RenderedEmail:
    """Generate outreach email using the approved templates.

    Role-aware (distributor vs KOL) and language-aware (by target market). Uses the
    configured LLM to personalize copy — and, for KOLs, to write a tailored intro
    paragraph like the gold-standard examples — falling back to the static template
    when no AI key is configured or the call fails.
    """
    ai_result = _try_ai_email(lead)
    if ai_result:
        return ai_result
    return _render_template_email(lead)


def _email_subject(lead_type: str, lang: str, market: str) -> str:
    if lead_type == "kol":
        if lang == "cn":
            return f"推动 {market} 机器人关节置换手术发展 – MEDBOT Skywalker 产品介绍"
        return f"Advancing Robotic Arthroplasty in {market} – Introduction from MEDBOT Skywalker"
    if lang == "cn":
        return f"分销合作机会 – MEDBOT NaviBot Skywalker 骨科机器人（{market} 市场）"
    return f"Distribution Partnership Opportunity – MEDBOT NaviBot Skywalker for {market}"


def _render_template_email(lead: CandidateLead) -> RenderedEmail:
    """Static fallback that fills the approved template variables without an LLM."""
    lead_type = infer_lead_type(lead)
    lang = _email_language(lead)
    market = lead.country or lead.region or ("目标市场" if lang == "cn" else "your market")
    name = lead.contact_name or ("Sir/Madam" if lang == "en" else "您好")
    subject = _email_subject(lead_type, lang, market)

    if lead_type == "distributor":
        if lang == "cn":
            body = (
                f"尊敬的 {name}：\n\n"
                f"我们了解到，您与 {market} 地区的高手术量骨科中心及关键意见领袖（KOL）有着深厚的合作关系——"
                "这正是我们联系您的原因。\n\n"
                f"我们正在寻找区域分销合作伙伴，将我们的旗舰手术机器人平台 MEDBOT NaviBot Skywalker 引入 "
                f"{market} 市场。该系统专为关节置换设计，为外科医生提供高兼容性、高效率的解决方案。\n\n"
                "我们系统的几个关键差异化优势包括：\n"
                f"{DIFFERENTIATORS_CN}\n\n"
                "我们致力于让手术更安全、更简单、更微创。\n\n"
                "如您有意向，麻烦回复本邮件，我们将有专人与您对接。\n\n"
                "感谢您的时间。\n\n"
                f"此致\n{SIGNATURE_CN}"
            )
        else:
            body = (
                f"Dear {name},\n\n"
                f"We understand you have strong relationships with high-volume orthopedic centers and "
                f"KOLs in {market} – which is exactly why we are reaching out.\n\n"
                f"We are seeking regional distribution partners to introduce our flagship surgical "
                f"robotics platform, the MEDBOT NaviBot Skywalker, into the {market} market. The system "
                "is designed for joint reconstruction and offers a highly compatible, efficient "
                "solution for surgeons.\n\n"
                "A few key differentiators of our system include:\n"
                f"{DIFFERENTIATORS_EN}\n\n"
                "We are committed to making surgery safer, easier, and less invasive.\n\n"
                "If you are interested, please reply to this email and a dedicated person will contact "
                "you.\n\n"
                "Thank you for your time.\n\n"
                f"Best regards,\n{SIGNATURE_EN}"
            )
    else:  # kol
        if lang == "cn":
            body = (
                f"尊敬的 {name}：\n\n"
                "我们联系您，是因为了解到您在骨科领域享有盛誉——作为高手术量的专科医生和数字化创新的先行者。"
                "我们非常尊重您的临床专业能力以及您在骨科领域作为重要学术验证者的角色。\n\n"
                "我们想向您介绍我们的 MEDBOT NaviBot 平台，特别是 Skywalker 全膝关节置换系统。"
                "我们相信，这项技术可以作为您现有临床工作的高兼容性、高效率补充。\n\n"
                "我们系统的几个关键差异化优势包括：\n"
                f"{DIFFERENTIATORS_CN}\n\n"
                "我们致力于让手术更安全、更简单、更微创。我们非常希望能与您沟通，探讨 Skywalker 系统的"
                "个性化术前规划和实时精度补偿如何与您当前的临床及学术目标相结合。\n\n"
                "如您有意向，麻烦回复本邮件，我们将有专人与您对接。\n\n"
                "感谢您的时间。\n\n"
                f"此致\n{SIGNATURE_CN}"
            )
        else:
            body = (
                f"Dear {name},\n\n"
                "We are reaching out to you because of your esteemed reputation as a high-volume "
                "specialist and digital innovator in the field of orthopedics. We deeply respect your "
                "clinical expertise and your role as a critical academic validator in the orthopedic "
                "community.\n\n"
                "We would like to introduce you to our MEDBOT NaviBot platform, featuring the Skywalker "
                "Total Knee System. We believe our technology can serve as a highly compatible and "
                "efficient addition to your practice.\n\n"
                "A few key differentiators of our system include:\n"
                f"{DIFFERENTIATORS_EN}\n\n"
                "We are committed to making surgery safer, easier, and less invasive. We would welcome "
                "the opportunity to discuss how the Skywalker system's personalized preoperative "
                "planning and real-time accuracy compensation might align with your ongoing clinical "
                "and academic objectives.\n\n"
                "If you are interested, please reply to this email and a dedicated person will contact "
                "you.\n\n"
                "Thank you for your time.\n\n"
                f"Sincerely,\n{SIGNATURE_EN}"
            )

    return RenderedEmail(sent_to=lead.email, subject=subject, body=body, region=lead.region)


def render_followup_email(lead: CandidateLead, followup_number: int) -> RenderedEmail:
    """Render a short follow-up for an emailed lead that hasn't replied.

    followup_number 1 = gentle "did you receive it" nudge; 2+ = a value-add note
    with a clinical highlight. Keeps the approved CTA (reply → dedicated person,
    no call), unified signature, and no price/cert/exclusivity — consistent with
    the first-touch template."""
    lead_type = infer_lead_type(lead)
    lang = _email_language(lead)
    market = lead.country or lead.region or ("目标市场" if lang == "cn" else "your market")
    name = lead.contact_name or ("Sir/Madam" if lang == "en" else "您好")
    base_subject = _email_subject(lead_type, lang, market)
    subject = base_subject if base_subject.lower().startswith("re:") else f"Re: {base_subject}"
    topic_cn = "分销合作" if lead_type == "distributor" else "这项技术"
    topic_en = "a distribution partnership" if lead_type == "distributor" else "the technology"

    if lang == "cn":
        if followup_number <= 1:
            body = (
                f"尊敬的 {name}：\n\n"
                "前几日我们就 MEDBOT NaviBot Skywalker 骨科手术机器人向您发去了一封介绍邮件，"
                "不知是否已送达。\n\n"
                f"如您对{topic_cn}有任何疑问，欢迎随时回复本邮件，我们将安排专人与您对接。\n\n"
                "感谢您的时间。\n\n"
                f"此致\n{SIGNATURE_CN}"
            )
        else:
            body = (
                f"尊敬的 {name}：\n\n"
                "再次打扰。补充一点 Skywalker 系统的临床亮点供您参考："
                "个性化术前规划、实时精度补偿，且无需打开股骨髓腔——出血更少、恢复更快、感染风险更低。\n\n"
                "如有意向，欢迎回复本邮件，我们将有专人与您对接。\n\n"
                "感谢您的时间。\n\n"
                f"此致\n{SIGNATURE_CN}"
            )
    else:
        if followup_number <= 1:
            body = (
                f"Dear {name},\n\n"
                "I reached out a few days ago about the MEDBOT NaviBot Skywalker surgical robotics "
                "platform, and wanted to make sure my message reached you.\n\n"
                f"If you have any questions about {topic_en}, simply reply to this email and a "
                "dedicated person will be glad to follow up.\n\n"
                "Thank you for your time.\n\n"
                f"Best regards,\n{SIGNATURE_EN}"
            )
        else:
            body = (
                f"Dear {name},\n\n"
                "Following up once more with a quick clinical highlight of the Skywalker system: "
                "personalized preoperative planning, real-time accuracy compensation, and a design "
                "that avoids opening the femoral canal — for less bleeding, faster recovery, and low "
                "infection risk.\n\n"
                "If this is of interest, just reply to this email and a dedicated person will contact "
                "you.\n\n"
                "Thank you for your time.\n\n"
                f"Best regards,\n{SIGNATURE_EN}"
            )
    return RenderedEmail(sent_to=lead.email, subject=subject, body=body, region=lead.region)


def resolve_content_ai(*, respect_toggle: bool = True) -> tuple[str, str, str] | None:
    """Resolve the LLM used to generate outreach emails and analyze replies.

    Priority:
    1. Master switch `ai_content_generation` (default on) — only when
       `respect_toggle` is set. Email generation respects it (falls back to a
       template when off); reply analysis passes `respect_toggle=False` because
       it is LLM-only and simply needs a key.
    2. Explicit backend AI settings (`agent_provider` / `agent_key` / `agent_model`).
    3. Fall back to the Pi sidecar's config (agent/.env) so a single agent setup
       also powers email/reply generation without re-entering the key.

    Returns `(provider, api_key, model)`, or None when no LLM is available.
    """
    try:
        from app.db import get_all_settings, get_setting

        if respect_toggle and get_setting("ai_content_generation", "true") != "true":
            return None
        settings = get_all_settings()
        provider = settings.get("agent_provider", "").strip().lower()
        api_key = settings.get("agent_key", "").strip()
        model = settings.get("agent_model", "").strip()
        if api_key and provider:
            return provider, api_key, model or "deepseek-v4-pro"

        from app.agent_config import resolve_sidecar_ai

        sidecar = resolve_sidecar_ai()
        if sidecar and sidecar[1]:
            provider, api_key, model = sidecar
            return provider.lower(), api_key, model or "deepseek-v4-pro"
    except Exception:
        pass
    return None


def _record_llm_usage(*, source: str, provider: str, model: str, data: object) -> None:
    """Persist token usage from an OpenAI-compatible chat-completions response.

    Best-effort and self-contained: a bug here must never take down email
    generation or reply analysis, so all failures are swallowed.
    """
    try:
        usage = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            return
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        if total_tokens <= 0:
            return
        from app.db import insert_token_usage_event
        insert_token_usage_event(
            source=source,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            actor="backend",
        )
    except Exception:
        pass


def _llm_endpoint(provider: str, model: str) -> tuple[str, str]:
    """Resolve the OpenAI-compatible chat endpoint + effective model name."""
    if provider == "deepseek":
        if "v4" in model or "pro" in model:
            model = "deepseek-chat"
        return "https://api.deepseek.com/v1/chat/completions", model
    if provider == "openai":
        return "https://api.openai.com/v1/chat/completions", model
    if provider in ("bailian", "dashscope", "qwen"):
        return "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", model
    return "https://api.deepseek.com/v1/chat/completions", "deepseek-chat"


def ai_company_name(
    *, title: str, snippet: str, page_text: str, domain: str, email: str
) -> str | None:
    """Infer a clean company name from multiple page signals via the LLM.

    Given the domain, page title, search snippet, a page-text excerpt, and the
    contact email, return the real company/brand name — not an SEO phrase
    ("No.1 / Top ... Manufacturer in India"), a page-section label
    ("Product By Category"), or leaked markdown. Returns None when no LLM is
    configured or the call fails, so callers can fall back to a heuristic."""
    try:
        resolved = resolve_content_ai(respect_toggle=False)
        if resolved is None:
            return None
        provider, api_key, model = resolved
        api_url, model = _llm_endpoint(provider, model)

        import requests

        system = (
            "You extract the proper company or organization name from web-page signals. "
            "Return ONLY the real name (brand or legal name) — never an SEO/marketing phrase "
            "like 'No.1/Top/Best/Leading ... Manufacturer/Company in <country>', never a tagline, "
            "never a page-section label ('Products', 'Contact', 'Product By Category', 'Home'), "
            "never a person's name, never markdown. If the title is generic or unhelpful, infer the "
            "name from the domain and page text (e.g. sharmaortho.com -> 'Sharma Ortho'). "
            'Respond with JSON only: {"company_name": "..."}.'
        )
        user = (
            f"domain: {domain}\n"
            f"contact email: {email}\n"
            f"page title: {title}\n"
            f"search snippet: {snippet}\n"
            f"page text (excerpt): {page_text[:1500]}"
        )
        resp = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": 60,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        _record_llm_usage(source="company_name", provider=provider, model=model, data=data)
        import json as _json
        import re as _re

        content = data["choices"][0]["message"]["content"].strip()
        content = _re.sub(r"^```(?:json)?\s*", "", content)
        content = _re.sub(r"\s*```$", "", content)
        name = str(_json.loads(content).get("company_name", "")).strip()
        return name[:120] or None
    except Exception:
        return None


def _try_ai_email(lead: CandidateLead) -> RenderedEmail | None:
    """Generate email using the configured AI agent. Returns None on failure."""
    try:
        resolved = resolve_content_ai()
        if resolved is None:
            return None
        provider, api_key, model = resolved

        if provider == "deepseek":
            api_url = "https://api.deepseek.com/v1/chat/completions"
            # deepseek-chat is more reliable for structured JSON output
            if "v4" in model or "pro" in model:
                model = "deepseek-chat"
        elif provider == "openai":
            api_url = "https://api.openai.com/v1/chat/completions"
        elif provider in ("bailian", "dashscope", "qwen"):
            # 阿里云百炼 / 通义千问 — OpenAI 兼容端点
            api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        else:
            api_url = f"https://api.deepseek.com/v1/chat/completions"
            model = "deepseek-chat"

        import requests
        lead_type = infer_lead_type(lead)
        lang = _email_language(lead)
        prompt = _build_email_prompt(lead, lead_type, lang)
        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _email_system_prompt(lang)},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.6,
                "max_tokens": 900,
            },
            # Reasoning/"thinking" models (e.g. Bailian qwen3.7-max) can take 30–90s.
            timeout=120,
        )

        if resp.status_code != 200:
            return None

        data = resp.json()
        _record_llm_usage(source="email_generation", provider=provider, model=model, data=data)
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


def _email_system_prompt(lang: str) -> str:
    lang_clause = (
        "Write the email in fluent professional Chinese."
        if lang == "cn"
        else "Write the email in fluent professional English."
    )
    return (
        "You are the MEDBOT Skywalker overseas sales assistant. You write personalized cold "
        "outreach emails that strictly follow an approved template: a brand-consistent body, the "
        "four fixed product differentiators, and the unified team signature. "
        f"{lang_clause} "
        "Never invent clinical claims, pricing, regulatory status, or facts about the recipient "
        "beyond what is provided. Return ONLY a JSON object with 'subject' and 'body' fields."
    )


def _build_email_prompt(lead: CandidateLead, lead_type: str, lang: str) -> str:
    market = lead.country or lead.region
    differentiators = DIFFERENTIATORS_CN if lang == "cn" else DIFFERENTIATORS_EN
    signature = SIGNATURE_CN if lang == "cn" else SIGNATURE_EN
    subject = _email_subject(lead_type, lang, market)

    lead_facts = (
        f"Recipient name: {lead.contact_name or '(unknown — use a polite generic greeting)'}\n"
        f"Organization: {lead.company_name}\n"
        f"Target market: {market}\n"
        f"Category: {lead.category}\n"
        f"Why selected / public evidence: {lead.match_reason}\n"
        f"Extra notes: {lead.notes or '(none)'}"
    )

    if lead_type == "kol":
        role_instructions = (
            "Audience: KEY OPINION LEADER / surgeon / hospital procurement decision-maker.\n"
            "Write a [Personalized Intro] sentence following this structure (style distilled from "
            "approved gold-standard examples — do not copy their wording, just the pattern):\n"
            "  1. A short 2-4 word reputation label grounded in the evidence (e.g. 'an efficiency "
            "champion and digital innovator', 'a rapid-recovery advocate and safety expert') plus "
            "their institution by name.\n"
            "  2. One or two concrete, verifiable achievements from the evidence/notes above — a "
            "'first' milestone (first in their country/region to perform a robotic or navigated "
            "procedure), a case-volume figure, or a leadership/academic title. Never invent a "
            "figure or milestone that isn't in the evidence.\n"
            "  3. Pick ONE specific clinical/technical theme from that achievement (e.g. 3D "
            "planning, rapid recovery, sensor-based balancing, high-volume efficiency) and echo "
            "that SAME theme later when explaining why Skywalker fits their practice, and again in "
            "the closing line — this creates one connected thread instead of generic flattery "
            "bolted onto boilerplate.\n"
            "If the evidence is thin, skip steps 1-2 and write a brief, honest, non-fabricated "
            "compliment instead — do not force a fake achievement. Then introduce the MEDBOT "
            "NaviBot platform featuring the Skywalker Total Knee System, frame it as a compatible "
            "addition to their practice, and close by offering to discuss how its personalized "
            "preoperative planning and real-time accuracy compensation align with their clinical/"
            "academic objectives (tied back to the theme from step 3 when there is one).\n"
        )
    else:
        role_instructions = (
            "Audience: medical-device DISTRIBUTOR / orthopedic implant agent / channel partner.\n"
            "Open by acknowledging their relationships with high-volume orthopedic centers and KOLs "
            "in the target market, then propose a regional distribution partnership for the MEDBOT "
            "NaviBot Skywalker. Keep it commercial and channel-focused. A [Personalized Intro] is "
            "optional for distributors — keep the opening simple.\n"
        )

    return f"""Compose ONE outreach email using the approved MEDBOT Skywalker template.

{lead_facts}

{role_instructions}
Hard requirements:
- Subject line MUST be exactly: {subject}
- Greeting addresses the recipient by name when available.
- Include these four differentiators verbatim as a bullet list:
{differentiators}
- Include the line about being committed to making surgery safer, easier, and less invasive.
- Call to action MUST be: invite them to reply and a dedicated person will contact them. Do NOT ask to schedule a call and do NOT request a meeting time.
- End with exactly this signature:
{signature}
- Do not add prices, certifications, FDA/CE claims, exclusivity, or contract terms.

Return JSON: {{"subject": "{subject}", "body": "..."}}"""


class ReplyAnalysisError(RuntimeError):
    """Raised when a reply can't be analyzed by the LLM.

    Reply intent classification is LLM-only — there is NO keyword fallback, so
    callers get a clear error (no LLM configured, or the LLM call failed)
    instead of an unreliable rule-based guess.
    """


def bounce_reply_analysis() -> ReplyAnalysis:
    """Deterministic analysis for a bounce / non-delivery report (no LLM needed)."""
    return ReplyAnalysis(
        intent="rejected",
        confidence=1.0,
        summary="退信 / 无法送达；已将该地址加入抑制名单。",
        next_action="停止向该地址发送外联。",
        requires_human=False,
    )


def auto_reply_analysis() -> ReplyAnalysis:
    """Deterministic analysis for an auto-reply (out-of-office etc.; no LLM needed)."""
    return ReplyAnalysis(
        intent="needs_review",
        confidence=0.5,
        summary="自动回复（如离开办公室），非真实意向。",
        next_action="等待对方的真实回复后再处理。",
        requires_human=False,
    )


def analyze_reply(reply_text: str) -> ReplyAnalysis:
    """Classify a prospect reply's intent using the LLM.

    LLM-only by design: raises ``ReplyAnalysisError`` when no LLM is configured
    or the call fails, rather than falling back to unreliable keyword rules.
    """
    resolved = resolve_content_ai(respect_toggle=False)
    if resolved is None:
        raise ReplyAnalysisError(
            "未配置 AI 模型（Provider / API Key），无法分析回复。请在「设置 → Agent」中配置 LLM。"
        )
    return _ai_reply_analysis(reply_text, resolved)


def _ai_reply_analysis(reply_text: str, resolved: tuple[str, str, str]) -> ReplyAnalysis:
    """Call the LLM to classify a reply. Raises ReplyAnalysisError on any failure."""
    provider, api_key, model = resolved

    if provider == "deepseek":
        api_url = "https://api.deepseek.com/v1/chat/completions"
    elif provider == "openai":
        api_url = "https://api.openai.com/v1/chat/completions"
    elif provider in ("bailian", "dashscope", "qwen"):
        # 阿里云百炼 / 通义千问 — OpenAI 兼容端点
        api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    else:
        raise ReplyAnalysisError(f"不支持的 AI provider：{provider}")

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
- opt_out: boolean, true ONLY if the reply EXPLICITLY asks to stop contact / unsubscribe / be removed from the list (e.g. "unsubscribe", "remove me", "do not contact us", "stop emailing", "退订", "别再发了"). A merely uninterested or "no fit" reply is NOT an opt_out.

Rules:
- "interested": general interest, asks for the brochure/product brief, asks who to talk to, or wants to keep the conversation going — WITHOUT yet raising any of the human-review topics below
- "rejected": not interested, unsubscribe, remove, no fit
- "complex": the reply touches ANY of these human-review topics → set requires_human=true. Topics: price / quote / budget; exclusive distribution / exclusivity; product registration / certification / FDA / CE; tender / bidding; contract / agreement / terms; payment / deposit; clinical claims / indications / efficacy promises; demo unit / trial / live demonstration / sample machine
- "needs_review": ambiguous, unclear, or doesn't fit the above categories

Important: The reply may be in Chinese, English, or any language. Judge by meaning, not by keyword matching. Whenever a human-review topic appears, prefer "complex" with requires_human=true even if the prospect also sounds interested."""

    try:
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
            # Reasoning/"thinking" models (e.g. Bailian qwen3.7-max) can be slow.
            timeout=90,
        )
    except requests.RequestException as exc:
        raise ReplyAnalysisError(f"AI 回复分析请求失败：{exc}") from exc

    if resp.status_code != 200:
        raise ReplyAnalysisError(f"AI 回复分析返回 HTTP {resp.status_code}")

    data = resp.json()
    _record_llm_usage(source="reply_analysis", provider=provider, model=model, data=data)
    try:
        content = data["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        parsed = json.loads(content)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise ReplyAnalysisError("AI 回复分析返回了无法解析的内容") from exc

    intent = str(parsed.get("intent", "")).lower()
    if intent not in ("interested", "rejected", "complex", "needs_review"):
        raise ReplyAnalysisError(f"AI 回复分析返回了无效的 intent：{intent!r}")

    return ReplyAnalysis(
        intent=intent,
        confidence=float(parsed.get("confidence", 0.7)),
        summary=str(parsed.get("summary", ""))[:500],
        next_action=str(parsed.get("next_action", ""))[:500],
        requires_human=bool(parsed.get("requires_human", False)),
        opt_out=bool(parsed.get("opt_out", False)),
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
