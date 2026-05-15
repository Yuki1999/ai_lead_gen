from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from html import unescape
from typing import Protocol
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.product import ProductProfile
from app.services import CandidateLead


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: object) -> requests.Response:
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


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
USER_AGENT = "Mozilla/5.0 (compatible; MedbotProspectingDemo/0.1)"
SEARCH_TIMEOUT_SECONDS = 5
PAGE_TIMEOUT_SECONDS = 3
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
        leads.append(
            _candidate_from_result(
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
        )


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
    http = http or requests.Session()
    results = search_duckduckgo(query, http=http, limit=limit)
    return results or search_jina_reader(query, http=http, limit=limit) or search_bing(query, http=http, limit=limit)


def search_duckduckgo(query: str, *, http: HttpClient | None = None, limit: int = 8) -> list[SearchResult]:
    http = http or requests.Session()
    try:
        response = http.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            timeout=SEARCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException:
        return []
    if response.status_code >= 400:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[SearchResult] = []
    for row in soup.select(".result"):
        link = row.select_one("a.result__a")
        if not link:
            continue
        raw_url = link.get("href") or ""
        url = _unwrap_duckduckgo_url(raw_url)
        title = link.get_text(" ", strip=True)
        snippet = row.select_one(".result__snippet")
        results.append(
            SearchResult(
                title=unescape(title),
                url=url,
                snippet=snippet.get_text(" ", strip=True) if snippet else "",
                query=query,
            )
        )
        if len(results) >= limit:
            break
    return results


def search_bing(query: str, *, http: HttpClient | None = None, limit: int = 8) -> list[SearchResult]:
    http = http or requests.Session()
    try:
        response = http.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "en-US"},
            timeout=SEARCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException:
        return []
    if response.status_code >= 400:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[SearchResult] = []
    for row in soup.select("li.b_algo"):
        link = row.select_one("h2 a[href]")
        if not link:
            continue
        url = _unwrap_bing_url(link.get("href") or "")
        if not _is_http_url(url):
            continue
        title = link.get_text(" ", strip=True)
        snippet = row.select_one(".b_caption p") or row.select_one("p")
        results.append(
            SearchResult(
                title=unescape(title),
                url=url,
                snippet=snippet.get_text(" ", strip=True) if snippet else "",
                query=query,
            )
        )
        if len(results) >= limit:
            break
    return results


def search_jina_reader(query: str, *, http: HttpClient | None = None, limit: int = 8) -> list[SearchResult]:
    http = http or requests.Session()
    target_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        response = http.get(
            f"https://r.jina.ai/http://r.jina.ai/http://{target_url}",
            timeout=SEARCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException:
        return []
    if response.status_code >= 400:
        return []

    results: list[SearchResult] = []
    matches = list(
        re.finditer(
            r"^\s*(?:\d+\.\s+)?## \[(?P<title>.+?)\]\((?P<url>https?://[^\s)]+)\)",
            response.text,
            re.MULTILINE,
        )
    )
    for index, match in enumerate(matches):
        raw_url = unescape(match.group("url"))
        url = _unwrap_duckduckgo_url(raw_url)
        if not _is_http_url(url) or _is_low_value_domain(_domain(url)):
            continue
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(response.text)
        snippet = _markdown_snippet(response.text[match.end():block_end])
        results.append(
            SearchResult(
                title=_clean_markdown(match.group("title")),
                url=url,
                snippet=snippet,
                query=query,
            )
        )
        if len(results) >= limit:
            break
    return results


@dataclass(frozen=True)
class PageSummary:
    url: str
    title: str
    text: str
    html: str
    email_source_url: str = ""


def fetch_page_summary(url: str, *, http: HttpClient | None = None) -> PageSummary:
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
) -> CandidateLead:
    evidence = f"{result.title} {result.snippet} {page.text[:3000]}".lower()
    category = _category_from_evidence(evidence)
    score = _score(evidence=evidence, email=email, product_profile=product_profile)
    company_name = _clean_company_name(page.title, fallback=result.title)
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


def _unwrap_duckduckgo_url(raw_url: str) -> str:
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    parsed = urlparse(raw_url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return target or raw_url
    if raw_url.startswith("/"):
        return f"https://duckduckgo.com{raw_url}"
    return raw_url


def _unwrap_bing_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if "bing.com" in parsed.netloc and parsed.path.startswith("/ck/"):
        target = parse_qs(parsed.query).get("u", [""])[0]
        if target.startswith("a1"):
            target = target[2:]
        try:
            import base64

            padded = target + "=" * (-len(target) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode("utf8")
            if _is_http_url(decoded):
                return decoded
        except (ValueError, UnicodeDecodeError):
            return raw_url
    return raw_url


def _markdown_snippet(block: str) -> str:
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[![") or line.startswith("!["):
            continue
        link_match = re.fullmatch(r"\[([^\]]+)\]\([^)]+\)", line)
        if link_match:
            label = link_match.group(1)
            if "." in label and " " not in label:
                continue
            return _clean_markdown(label)[:500]
        return _clean_markdown(line)[:500]
    return ""


def _clean_markdown(value: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("**", " ").replace("__", " ")
    return unescape(re.sub(r"\s+", " ", value)).strip()


def _choose_email(emails: list[str], url: str) -> str:
    if not emails:
        return ""
    domain = _domain(url)
    if domain:
        domain_parts = domain.split(".")
        root_domain = ".".join(domain_parts[-2:]) if len(domain_parts) >= 2 else domain
        for email in emails:
            if email.endswith(root_domain):
                return email
    return emails[0]


def _clean_company_name(title: str, *, fallback: str = "") -> str:
    cleaned = re.split(r"\s[-|–—]\s", title, maxsplit=1)[0].strip()
    if cleaned.lower() in {"", "contact", "contact us", "products", "home", "about us"}:
        cleaned = fallback.strip()
    return cleaned[:120] or "Unknown Prospect"


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
    }
    return any(domain == blocked_domain or domain.endswith(f".{blocked_domain}") for blocked_domain in blocked)


def _region_from_query(query: str, regions: list[str]) -> str:
    lowered = query.lower()
    for region in regions:
        if quote_plus(region).lower() in lowered or region.lower() in lowered:
            return region
    return regions[0]
