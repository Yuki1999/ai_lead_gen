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


def analyze_reply(reply_text: str) -> ReplyAnalysis:
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
