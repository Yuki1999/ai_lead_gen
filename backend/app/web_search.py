from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from html import unescape
from typing import Protocol
from urllib.parse import quote_plus, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.product import ProductProfile
from app.services import CandidateLead


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: object) -> requests.Response:
        ...

    def post(self, url: str, **kwargs: object) -> requests.Response:
        ...


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    query: str


@dataclass(frozen=True)
class SeedProspect:
    name: str
    url: str
    region: str
    country: str
    category: str
    hint: str


class SearchProviderError(RuntimeError):
    """Raised when the configured search provider is missing or fails.

    The system has no scraping fallback: if Tavily is not configured or its
    call fails, callers must surface the error rather than silently
    degrading to an unreliable substitute.
    """


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
USER_AGENT = "Mozilla/5.0 (compatible; MedbotProspectingDemo/0.1)"
PAGE_TIMEOUT_SECONDS = 3
TAVILY_TIMEOUT_SECONDS = 8
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
# Extract (esp. "advanced") fetches and renders pages server-side, so give it a
# more generous timeout than a plain search call.
TAVILY_EXTRACT_TIMEOUT_SECONDS = 30


def _search_depth() -> str:
    """Tavily search depth: 'basic' | 'advanced'. Default advanced for better
    result relevance (override with TAVILY_SEARCH_DEPTH)."""
    return (os.getenv("TAVILY_SEARCH_DEPTH", "advanced").strip() or "advanced")


def _extract_depth() -> str:
    """Tavily extract depth: 'basic' | 'advanced'. Default advanced for the most
    complete page content (override with TAVILY_EXTRACT_DEPTH)."""
    return (os.getenv("TAVILY_EXTRACT_DEPTH", "advanced").strip() or "advanced")
SEED_PROSPECTS = [
    SeedProspect(
        name="ITS Implant",
        url="https://www.its-implant.com/en/contact/",
        region="Europe",
        country="Germany",
        category="orthopedic implant company / distributor program",
        hint="Orthopedic implants with Germany office and distributor partnership page.",
    ),
    SeedProspect(
        name="United Orthopedic Europe",
        url="https://eu.unitedorthopedic.com/contact/",
        region="Europe",
        country="Switzerland",
        category="orthopedic hip and knee implants distribution branch",
        hint="European distribution and management branch for orthopedic hip and knee implants.",
    ),
    SeedProspect(
        name="SiS Medical GmbH",
        url="https://af-ortho.com/products/",
        region="Europe",
        country="Germany",
        category="orthopedic trauma company",
        hint="Germany-based orthopedic and trauma company with implant portfolio.",
    ),
    SeedProspect(
        name="Biotech Group",
        url="https://biotech-medical.com/bio/",
        region="Europe",
        country="Germany",
        category="orthopedic joint reconstruction manufacturer and distributor",
        hint="Germany-based medical product manufacturer and distributor with hip, knee, shoulder replacement.",
    ),
    SeedProspect(
        name="Orthopaedic Implant Co.",
        url="https://oicintl.com/contact/",
        region="Southeast Asia",
        country="Singapore",
        category="orthopedic implant company",
        hint="Singapore contact page for orthopedic implant company.",
    ),
    SeedProspect(
        name="Indola Pharma Link",
        url="https://www.indolapharmalink.com/",
        region="Southeast Asia",
        country="Singapore",
        category="orthopedic surgical equipment and implant distributor",
        hint="Singapore medical device distributor specializing in orthopedic surgical equipment and implants.",
    ),
    SeedProspect(
        name="Gen-Y Medical",
        url="https://www.genymedical.com/",
        region="Southeast Asia",
        country="Singapore",
        category="orthopedic medical device distributor",
        hint="Singapore distributor focused on orthopedic products and implants.",
    ),
    SeedProspect(
        name="Smithery Medwise",
        url="https://www.smitherymedwise.com/",
        region="Southeast Asia",
        country="Singapore",
        category="medical device distributor",
        hint="Singapore medical device distributor.",
    ),
    SeedProspect(
        name="ProtoMed Singapore",
        url="https://www.protomed.sg/products/",
        region="Southeast Asia",
        country="Singapore",
        category="surgical implant and medical device distributor",
        hint="Singapore medical device company with implant-related product lines.",
    ),
]


def discover_real_prospects(
    *,
    target_regions: list[str],
    product_profile: ProductProfile,
    extra_keywords: list[str] | None = None,
    max_results: int = 8,
    require_email: bool = True,
    http: HttpClient | None = None,
) -> list[CandidateLead]:
    http = http or requests.Session()
    regions = [region.strip() for region in target_regions if region.strip()] or ["Europe"]
    queries = build_search_queries(regions, product_profile, extra_keywords=extra_keywords)
    max_queries = int(os.getenv("MEDBOT_SEARCH_MAX_QUERIES", str(max(1, min(2, max_results)))))
    queries = queries[:max_queries]
    deadline = time.monotonic() + float(os.getenv("MEDBOT_SEARCH_DEADLINE_SECONDS", "25"))
    leads: list[CandidateLead] = []
    seen_domains: set[str] = set()

    _append_seed_prospects(
        leads=leads,
        seen_domains=seen_domains,
        target_regions=regions,
        product_profile=product_profile,
        max_results=max_results,
        require_email=require_email,
        http=http,
        deadline=deadline,
    )
    if len(leads) >= max_results:
        return leads

    for query in queries:
        if time.monotonic() > deadline:
            break
        for result in search_web(query, http=http, limit=max(3, max_results * 2)):
            if time.monotonic() > deadline:
                return leads
            domain = _domain(result.url)
            if not domain or domain in seen_domains or _is_low_value_domain(domain):
                continue

            page = fetch_page_summary(result.url, http=http)
            emails = extract_emails(page.html) or extract_emails(result.snippet)
            if require_email and not emails:
                continue

            seen_domains.add(domain)
            lead = _candidate_from_result(
                result=result,
                page=page,
                email=_choose_email(emails, result.url),
                product_profile=product_profile,
                region=_region_from_query(query, regions),
            )
            if lead is None:
                continue
            leads.append(lead)
            if len(leads) >= max_results:
                return leads

    return leads


def _append_seed_prospects(
    *,
    leads: list[CandidateLead],
    seen_domains: set[str],
    target_regions: list[str],
    product_profile: ProductProfile,
    max_results: int,
    require_email: bool,
    http: HttpClient,
    deadline: float,
) -> None:
    for seed in SEED_PROSPECTS:
        if len(leads) >= max_results or time.monotonic() > deadline:
            return
        if not _seed_matches_targets(seed, target_regions):
            continue
        domain = _domain(seed.url)
        if not domain or domain in seen_domains:
            continue

        page = fetch_page_summary(seed.url, http=http)
        emails = extract_emails(page.html)
        if require_email and not emails:
            continue

        seen_domains.add(domain)
        seed_lead = _candidate_from_result(
            result=SearchResult(
                title=seed.name,
                url=seed.url,
                snippet=seed.hint,
                query="verified seed source",
            ),
            page=page,
            email=_choose_email(emails, seed.url),
            product_profile=product_profile,
            region=seed.country,
        )
        if seed_lead is not None:
            leads.append(seed_lead)


def _seed_matches_targets(seed: SeedProspect, targets: list[str]) -> bool:
    target_text = " ".join(targets).lower()
    seed_values = f"{seed.region} {seed.country}".lower()
    if any(target.lower() in seed_values for target in targets):
        return True
    if "europe" in target_text and seed.region.lower() == "europe":
        return True
    if any(term in target_text for term in ["southeast asia", "asean", "singapore"]):
        return seed.region.lower() == "southeast asia"
    return False


def build_search_queries(
    regions: list[str],
    product_profile: ProductProfile,
    *,
    extra_keywords: list[str] | None = None,
) -> list[str]:
    query_templates = [
        '"{keyword}" "{region}" contact email',
        '"{keyword}" "{region}" distributor orthopedics',
        '"{keyword}" "{region}" joint replacement',
    ]
    keywords = [
        keyword.strip()
        for keyword in [*(extra_keywords or []), *product_profile.search_keywords]
        if keyword.strip()
    ][:6]
    queries: list[str] = []
    for region in regions:
        for keyword in keywords:
            for template in query_templates:
                queries.append(template.format(keyword=keyword, region=region))
    return queries


def search_web(query: str, *, http: HttpClient | None = None, limit: int = 8) -> list[SearchResult]:
    # Tavily is the only search provider. There is no scraping fallback: if
    # it isn't configured or the call fails, callers get a SearchProviderError
    # instead of a silently degraded (and often unreliable) substitute.
    return search_tavily(query, http=http, limit=limit)


def _tavily_api_key() -> str:
    return os.getenv("TAVILY_API_KEY", "").strip()


def search_tavily(query: str, *, http: HttpClient | None = None, limit: int = 8) -> list[SearchResult]:
    api_key = _tavily_api_key()
    if not api_key:
        raise SearchProviderError("TAVILY_API_KEY is not configured")
    http = http or requests.Session()
    try:
        response = http.post(
            TAVILY_SEARCH_URL,
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": _search_depth(),
                "max_results": limit,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=TAVILY_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise SearchProviderError(f"Tavily request failed: {exc}") from exc
    if response.status_code >= 400:
        raise SearchProviderError(f"Tavily returned HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise SearchProviderError("Tavily returned a non-JSON response") from exc

    results: list[SearchResult] = []
    for item in data.get("results", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if not _is_http_url(url):
            continue
        results.append(
            SearchResult(
                title=str(item.get("title", "")).strip(),
                url=url,
                snippet=str(item.get("content", "")).strip(),
                query=query,
            )
        )
        if len(results) >= limit:
            break
    return results


def extract_tavily(
    urls: list[str], *, http: HttpClient | None = None, extract_depth: str | None = None
) -> dict[str, str]:
    """Fetch page content via Tavily's /extract service, returning {url: content}.

    Tavily fetches and renders the pages on its own infrastructure, so this works
    from hosts that can't reach arbitrary foreign sites directly (e.g. behind the
    GFW) as long as api.tavily.com is reachable. Only the api.tavily.com hop is
    needed. Raises SearchProviderError on a transport/HTTP failure so callers can
    decide whether to fall back or surface the error.
    """
    api_key = _tavily_api_key()
    if not api_key:
        raise SearchProviderError("TAVILY_API_KEY is not configured")
    clean_urls = [u for u in urls if _is_http_url(u)]
    if not clean_urls:
        return {}
    http = http or requests.Session()
    try:
        response = http.post(
            TAVILY_EXTRACT_URL,
            json={
                "api_key": api_key,
                "urls": clean_urls,
                "extract_depth": extract_depth or _extract_depth(),
                "format": "markdown",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=TAVILY_EXTRACT_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise SearchProviderError(f"Tavily extract failed: {exc}") from exc
    if response.status_code >= 400:
        raise SearchProviderError(f"Tavily extract returned HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise SearchProviderError("Tavily extract returned a non-JSON response") from exc

    out: dict[str, str] = {}
    for item in data.get("results", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        content = str(item.get("raw_content", "") or "")
        if url and content.strip():
            out[url] = content
    return out


_NAV_TITLE_JUNK = {
    "skip to content",
    "skip to main content",
    "menu",
    "toggle navigation",
    "search",
}


def _title_from_markdown(md: str) -> str:
    """Best-effort page title from extracted markdown: the first meaningful line,
    skipping heading markers, pure-image lines (![alt](url)), navigation links
    ("Skip to content"), and unwrapping markdown links to their visible text."""
    for raw in md.splitlines():
        line = raw.strip().lstrip("#").strip()
        if not line or line.startswith("!["):
            continue
        # Unwrap markdown links/images: [text](url) / ![alt](url) → text/alt.
        line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line).strip()
        if not line or line.lower() in _NAV_TITLE_JUNK:
            continue
        return line[:200]
    return ""


@dataclass(frozen=True)
class PageSummary:
    url: str
    title: str
    text: str
    html: str
    email_source_url: str = ""


def fetch_page_summary(url: str, *, http: HttpClient | None = None) -> PageSummary:
    """Read a page's content + emails, preferring Tavily Extract (server-side
    fetch, GFW-resilient) and falling back to a direct fetch only if extract is
    unavailable or returns nothing usable."""
    http = http or requests.Session()
    candidates = _candidate_contact_urls(url)[:2]
    try:
        extracted = extract_tavily(candidates, http=http)
    except SearchProviderError:
        extracted = {}

    if extracted:
        title = ""
        text = ""
        html = ""
        email_source_url = ""
        for candidate_url in candidates:
            content = extracted.get(candidate_url, "")
            if not content:
                continue
            html += "\n" + content
            text += "\n" + content[:80_000]
            if not title:
                title = _title_from_markdown(content)
            if not email_source_url and extract_emails(content):
                email_source_url = candidate_url
        if text.strip():
            return PageSummary(url=url, title=title, text=text, html=html, email_source_url=email_source_url)

    return _fetch_page_summary_direct(url, http=http)


def _fetch_page_summary_direct(url: str, *, http: HttpClient | None = None) -> PageSummary:
    """Legacy direct fetch (requests + BeautifulSoup). Best-effort fallback for
    when Tavily Extract is unavailable; unreliable from GFW-restricted hosts."""
    http = http or requests.Session()
    html = ""
    title = ""
    text = ""
    email_source_url = ""
    for candidate_url in _candidate_contact_urls(url)[:2]:
        try:
            response = http.get(
                candidate_url,
                timeout=PAGE_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            )
        except requests.RequestException:
            continue
        content_type = response.headers.get("content-type", "")
        if response.status_code >= 400 or "text/html" not in content_type:
            continue

        html += "\n" + response.text[:500_000]
        soup = BeautifulSoup(response.text, "html.parser")
        if not title and soup.title:
            title = soup.title.get_text(" ", strip=True)
        text += "\n" + soup.get_text(" ", strip=True)[:80_000]
        if extract_emails(response.text):
            email_source_url = candidate_url
            break
    return PageSummary(url=url, title=title, text=text, html=html, email_source_url=email_source_url)


def fetch_source_preview(url: str, email: str = "") -> dict[str, object]:
    if not _is_http_url(url):
        raise ValueError("Only http and https source URLs are supported")

    page = fetch_page_summary(url)
    emails = extract_emails(page.html)
    normalized_email = email.strip().lower()
    page_text = _normalize_preview_text(page.text)
    return {
        "url": url,
        "title": page.title or url,
        "text": page_text,
        "email": normalized_email,
        "emails": emails,
        "email_found": bool(normalized_email and normalized_email in emails),
    }


def extract_emails(text: str) -> list[str]:
    text = unquote(text)
    emails = {
        email.strip(".,;:()[]{}<>").lower()
        for email in EMAIL_RE.findall(text)
        if not email.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
    }
    return sorted(emails)


def _normalize_preview_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:30_000]


def _candidate_from_result(
    *,
    result: SearchResult,
    page: PageSummary,
    email: str,
    product_profile: ProductProfile,
    region: str,
) -> CandidateLead | None:
    evidence = f"{result.title} {result.snippet} {page.text[:3000]}".lower()
    category = _category_from_evidence(evidence)
    score = _score(evidence=evidence, email=email, product_profile=product_profile)
    # Prefer the search engine's page title for the company name: it's a clean
    # <title>, whereas Tavily's markdown often starts with a "Skip to content"
    # nav link or a logo image. Fall back to the extracted title only if the
    # search title is empty/generic.
    company_name = _clean_company_name(result.title, fallback=page.title)

    # The mechanical name is often an SEO phrase ("No.1 ... Manufacturer in
    # India"), a page-section label ("Product By Category"), or leaked markdown.
    # When it looks weak, ask the LLM to infer the real name from multiple
    # signals (domain + title + snippet + page text + email); fall back to a
    # domain-derived name if no LLM is configured.
    if _name_looks_weak(company_name):
        from app.services import ai_company_name

        ai_name = ai_company_name(
            title=result.title,
            snippet=result.snippet,
            page_text=page.text,
            domain=_domain(result.url),
            email=email,
        )
        if ai_name and not _name_looks_weak(ai_name):
            company_name = ai_name
        else:
            domain_name = _company_name_from_domain(result.url)
            if domain_name:
                company_name = domain_name

    # Reject dictionary/encyclopedia/wiki/journal/error-page style titles.
    if _is_low_value_title(company_name) or _is_low_value_title(result.title):
        return None

    # Reject soft-404 / error / "page not found" pages that returned HTTP 200
    # but clearly aren't a company page (status-code checks alone miss these).
    if _looks_like_error_page(title=page.title, text=page.text):
        return None

    # Require at least one topical signal (orthopedics / medical device /
    # distribution). Without this, ANY page with a scraped email — a journal's
    # editorial contact, a forum's support address — would still pass, since
    # having an email is otherwise the only real filter.
    if not _has_topical_relevance(evidence):
        return None

    # Reject directory / listicle / ranking pages and market-research /
    # consultancy pages — they're about companies, not a channel to sell to.
    if _looks_like_aggregator(title=result.title, page_title=page.title, evidence=evidence):
        return None

    country = region
    match_reason = (
        f"Live web match for {product_profile.procedure}: {result.snippet or result.title}. "
        f"Detected category: {category}."
    )
    source_url = page.email_source_url or page.url or result.url
    notes = (
        f"Real search query: {result.query}. "
        f"Email {'found' if email else 'not found'}"
        f"{f' at {source_url}' if email else ''}."
    )

    return CandidateLead(
        company_name=company_name,
        region=region,
        country=country,
        website=result.url,
        contact_name="Sales / Business Development",
        email=email,
        category=category,
        match_reason=match_reason[:900],
        source=source_url,
        score=score,
        notes=notes,
    )


def _score(*, evidence: str, email: str, product_profile: ProductProfile) -> int:
    score = 45
    if email:
        score += 20
    for term in ["orthopedic", "orthopaedic", "implant", "joint", "knee", "arthroplasty"]:
        if term in evidence:
            score += 5
    for term in ["distributor", "distribution", "sales", "medical device"]:
        if term in evidence:
            score += 4
    for term in product_profile.specialties:
        if term.lower() in evidence:
            score += 3
    return max(0, min(score, 98))


def _category_from_evidence(evidence: str) -> str:
    if "distributor" in evidence or "distribution" in evidence:
        return "orthopedic / medical device distributor"
    if "hospital" in evidence or "clinic" in evidence:
        return "orthopedic hospital or joint replacement center"
    if "implant" in evidence or "arthroplasty" in evidence:
        return "orthopedic implant company"
    if "robot" in evidence:
        return "surgical robotics company"
    return "medical device prospect"


def _candidate_contact_urls(url: str) -> list[str]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return [url]
    root = f"{parsed.scheme}://{parsed.netloc}/"
    candidates = [url, root]
    for path in ["contact", "contact-us", "contacts", "en/contact", "about/contact"]:
        candidates.append(urljoin(root, path))
    return list(dict.fromkeys(candidates))


_FREE_EMAIL_PROVIDERS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com",
    "aol.com", "163.com", "126.com", "qq.com", "sina.com", "hongkong.com",
    "yandex.com", "gmx.com", "mail.com", "protonmail.com", "rediffmail.com",
}


def _choose_email(emails: list[str], url: str) -> str:
    if not emails:
        return ""
    domain = _domain(url)
    if domain:
        domain_parts = domain.split(".")
        root_domain = ".".join(domain_parts[-2:]) if len(domain_parts) >= 2 else domain
        for email in emails:
            if email.endswith(root_domain):  # same-domain corporate email wins
                return email
    # No same-domain match: prefer a corporate address over a free-provider one
    # (directory pages often expose a scraped gmail/hongkong.com etc.).
    for email in emails:
        if email.rsplit("@", 1)[-1] not in _FREE_EMAIL_PROVIDERS:
            return email
    return emails[0]


def _is_low_value_title(name: str) -> bool:
    """Reject titles that look like dictionary/wiki/journal/forum/error-page entries."""
    lowered = name.lower()
    patterns = [
        "是什么意思", "的翻译", "的读音", "的用法", "的例句",
        "definition", "meaning of", "what is", "what are",
        "how to", "how do", "why do", "why is",
        " - wikipedia", "wikipedia, the free",
        "dictionary", "encyclopedia", "thesaurus",
        "翻译", "词典", "字典", "词霸", "爱词霸",
        # Academic journals / papers / literature
        "杂志", "期刊", "学报", "论文", "文献",
        "journal of", "proceedings of", "conference on",
        # Q&A / forum / column content (not a company)
        "专栏", "问答", "讨论区", "论坛",
        # Soft-404 / error / unavailable pages that often return HTTP 200
        "404", "page not found", "not found", "页面不存在", "页面未找到",
        "无法访问", "访问出错", "出错了", "服务器错误", "维护中",
        "under maintenance", "access denied", "forbidden",
    ]
    return any(p in lowered for p in patterns)


# Domain-agnostic backstop for soft-404 pages: many sites render an "error" or
# "not found" page with HTTP 200. Combine a phrase match with very short body
# text — a real company page almost never has both.
_ERROR_PAGE_PHRASES = (
    "404", "page not found", "not found", "页面不存在", "页面未找到",
    "无法访问", "访问出错", "出错了", "该页面", "链接已失效",
    "under maintenance", "access denied", "内容不存在", "内容已删除",
)


def _looks_like_error_page(*, title: str, text: str) -> bool:
    haystack = f"{title} {text[:400]}".lower()
    has_error_phrase = any(phrase in haystack for phrase in _ERROR_PAGE_PHRASES)
    is_very_short = len(re.sub(r"\s+", "", text)) < 120
    return has_error_phrase and is_very_short


_TOPICAL_TERMS = (
    "orthopedic", "orthopaedic", "implant", "joint replacement", "arthroplasty",
    "knee", "hip", "distributor", "distribution", "medical device",
    "surgical", "surgery", "robotics", "navigation", "prosthesis", "prosthetic",
    "骨科", "关节", "植入物", "经销", "代理", "分销", "手术机器人", "医疗器械",
)


def _has_topical_relevance(evidence: str) -> bool:
    """Require at least one orthopedics/medical-device/distribution signal.

    Without this, any page with a scraped email — an academic journal's
    editorial contact, a forum's support address — would still pass, since
    having an email was otherwise the only real acceptance criterion.
    """
    return any(term in evidence for term in _TOPICAL_TERMS)


# Directory / listicle / ranking pages ("Top 10 Orthopedic Companies in India",
# "Orthopedic Implant Manufacturers in India", supplier directories) announce
# themselves in the title. These are pages ABOUT companies, not a company's own
# site, and were polluting the lead list with scraped listing emails.
_LISTICLE_TITLE_RE = re.compile(
    r"top\s*\d+"
    r"|\d+\s+(?:best|leading|largest|top)\b"
    r"|best\s+[\w\s/&-]{0,40}\b(?:companies|manufacturers|suppliers|distributors)\b"
    r"|list of\b"
    r"|companies list"
    r"|\b(?:companies|manufacturers|suppliers|distributors|exporters|vendors)\s+(?:list|directory)\b"
    r"|\b(?:companies|manufacturers|suppliers|distributors|exporters)\s+in\s+\w"
    r"|directory of\b"
    r"|十大|排行|排名|名录",
    re.IGNORECASE,
)
# Market-research / consultancy / advisory pages (e.g. a "market entry advisory
# firm" publishing a report about distributors) — topical but not a channel.
_CONSULTANCY_TERMS = (
    "market entry", "advisory firm", "consulting firm", "consultancy",
    "market report", "market research", "market analysis", "market size",
    "research report", "industry report", "industry analysis",
    "市场分析", "市场研究", "研究报告", "行业分析", "市场报告", "咨询公司",
)


def _looks_like_aggregator(*, title: str, page_title: str, evidence: str) -> bool:
    """True for directory/listicle/ranking pages and market-research/consultancy
    pages — content that reads as being *about* companies rather than a single
    company's own site."""
    for candidate_title in (title, page_title):
        if candidate_title and _LISTICLE_TITLE_RE.search(candidate_title):
            return True
    return any(term in evidence for term in _CONSULTANCY_TERMS)


def _clean_company_name(title: str, *, fallback: str = "") -> str:
    cleaned = re.split(r"\s[-|–—]\s", title, maxsplit=1)[0].strip()
    if cleaned.lower() in {"", "contact", "contact us", "products", "home", "about us"}:
        cleaned = fallback.strip()
    return cleaned[:120] or "Unknown Prospect"


_WEAK_NAME_LABELS = {
    "unknown prospect", "products", "product", "product by category", "categories",
    "contact", "contact us", "contact-us", "home", "about", "about us", "services",
    "welcome", "index",
}
_WEAK_NAME_SEO_RE = re.compile(
    r"\b(no\.?\s*1|#\s*1|top|best|leading|largest)\b.*"
    r"\b(manufacturer|manufacturers|supplier|suppliers|company|companies|distributor|distributors|implants?)\b"
    r"|\bmanufacturers?\s+in\s+\w",
    re.IGNORECASE,
)


def _name_looks_weak(name: str) -> bool:
    """True when a mechanically-derived company name is an SEO phrase, a
    page-section label, leaked markdown, or generic — worth re-deriving via the
    LLM from richer signals."""
    if not name:
        return True
    lowered = name.strip().lower()
    if lowered in _WEAK_NAME_LABELS:
        return True
    if "![" in name or "](" in name:  # markdown image/link leaked into the title
        return True
    return bool(_WEAK_NAME_SEO_RE.search(name))


def _company_name_from_domain(url: str) -> str:
    """Last-resort name from the domain root (e.g. xlo.in -> 'Xlo'). Crude for
    concatenated domains; only used when the LLM is unavailable."""
    domain = _domain(url)
    if not domain:
        return ""
    root = domain.split(".")[0]
    cleaned = re.sub(r"[^a-z0-9]+", " ", root, flags=re.IGNORECASE).strip()
    return cleaned.title()[:120] if cleaned else ""


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_low_value_domain(domain: str) -> bool:
    blocked = {
        "facebook.com",
        "linkedin.com",
        "youtube.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "duckduckgo.com",
        # Dictionary / encyclopedia / wiki / Q&A
        "iciba.com",
        "wikipedia.org",
        "wiktionary.org",
        "merriam-webster.com",
        "dictionary.com",
        "thefreedictionary.com",
        "collinsdictionary.com",
        "cambridge.org",
        "oxfordlearnersdictionaries.com",
        "macmillandictionary.com",
        "ldoceonline.com",
        "wordreference.com",
        "quora.com",
        "answers.com",
        "britannica.com",
        "encyclopedia.com",
        "baidu.com",
        "baike.baidu.com",
        "zhidao.baidu.com",
        # Translation / language
        "translate.google",
        "deepl.com",
        "reverso.net",
        "linguee.com",
        "dict.cc",
        "bab.la",
        "glosbe.com",
        # Chinese Q&A / content / social platforms
        "zhihu.com",
        "douban.com",
        "weibo.com",
        "xiaohongshu.com",
        "bilibili.com",
        "toutiao.com",
        "sohu.com",
        "163.com",
        "qq.com",
        "sina.com.cn",
        "csdn.net",
        "jianshu.com",
        # Academic journals / literature databases / paper repositories
        "cnki.net",
        "wanfangdata.com.cn",
        "cqvip.com",
        "oversea.cnki.net",
        "pubmed.ncbi.nlm.nih.gov",
        "ncbi.nlm.nih.gov",
        "researchgate.net",
        "sciencedirect.com",
        "springer.com",
        "springerlink.com",
        "wiley.com",
        "nature.com",
        "jamanetwork.com",
        "nejm.org",
        "thelancet.com",
        "tandfonline.com",
        "academic.oup.com",
        "semanticscholar.org",
        "jstor.org",
        "scholar.google.com",
        # News / media aggregators
        "reddit.com",
        "medium.com",
        "pinterest.com",
        "tiktok.com",
        # Code / dev
        "github.com",
        "stackoverflow.com",
        "gitlab.com",
        "bitbucket.org",
        # Job / recruitment
        "indeed.com",
        "glassdoor.com",
        "ziprecruiter.com",
        "monster.com",
    }
    return any(domain == blocked_domain or domain.endswith(f".{blocked_domain}") for blocked_domain in blocked)


def _region_from_query(query: str, regions: list[str]) -> str:
    lowered = query.lower()
    for region in regions:
        if quote_plus(region).lower() in lowered or region.lower() in lowered:
            return region
    return regions[0]
