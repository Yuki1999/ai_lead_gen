from pathlib import Path

import pytest
import requests

from app.product import extract_product_profile
from app.web_search import (
    SearchProviderError,
    SeedProspect,
    discover_real_prospects,
    extract_emails,
    extract_tavily,
    fetch_page_summary,
    search_tavily,
    search_web,
)


class FakeResponse:
    def __init__(
        self,
        text: str,
        status_code: int = 200,
        content_type: str = "text/html",
        json_data: object = None,
    ):
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("no json body")
        return self._json_data


class FakeHttp:
    def post(self, url: str, **kwargs):
        assert "api.tavily.com" in url
        return FakeResponse(
            "",
            json_data={
                "results": [
                    {
                        "title": "Demo Ortho Distribution - Orthopedic Implants",
                        "url": "https://demo-ortho.example/",
                        "content": "Orthopedic implant distributor for joint replacement and knee arthroplasty.",
                    }
                ]
            },
        )

    def get(self, url: str, **kwargs):
        return FakeResponse(
            """
            <html>
              <head><title>Demo Ortho Distribution</title></head>
              <body>
                We distribute orthopedic implants, knee arthroplasty products, and hospital robotics.
                Contact sales@demo-ortho.example for business development.
              </body>
            </html>
            """
        )


class SeedOnlyFakeHttp:
    def post(self, url: str, **kwargs):
        # No Tavily extract in this fake → force fetch_page_summary's direct
        # (BeautifulSoup) fallback, which is what this fixture exercises.
        raise requests.RequestException("extract unavailable in fixture")

    def get(self, url: str, **kwargs):
        return FakeResponse(
            """
            <html>
              <head><title>Seed Ortho</title></head>
              <body>
                Orthopedic implant distributor for knee arthroplasty.
                Contact bd@seed-ortho.example.
              </body>
            </html>
            """
        )


class ContactPageFakeHttp:
    def post(self, url: str, **kwargs):
        # Force the direct-fetch fallback so this test still verifies the
        # "which page did the email come from" logic against .get pages.
        raise requests.RequestException("extract unavailable in fixture")

    def get(self, url: str, **kwargs):
        if url.rstrip("/").endswith("contact"):
            return FakeResponse(
                """
                <html>
                  <head><title>Contact - Contact Page Ortho</title></head>
                  <body>Business development: bd@contact-page.example</body>
                </html>
                """
            )
        return FakeResponse(
            """
            <html>
              <head><title>Contact Page Ortho</title></head>
              <body>Orthopedic implant distributor with a separate contact page.</body>
            </html>
            """
        )


def test_product_profile_extracts_skywalker_tka_positioning():
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    assert "SkyWalker" in profile.product_name
    assert profile.procedure == "total knee arthroplasty (TKA)"
    assert "orthopedic implant distributor" in profile.ideal_customer_types
    assert any("arthroplasty" in keyword for keyword in profile.search_keywords)
    assert any(source.endswith(".pdf") for source in profile.source_files)
    assert any(asset.filename.endswith(".mp4") for asset in profile.video_assets)


def test_extract_emails_filters_image_like_matches():
    emails = extract_emails("info@example.com icon@2x.png sales@example.org %20bd@example.net")

    assert emails == ["bd@example.net", "info@example.com", "sales@example.org"]


def test_fetch_page_summary_records_where_email_was_found():
    page = fetch_page_summary("https://contact-page.example/", http=ContactPageFakeHttp())

    assert page.email_source_url == "https://contact-page.example/contact"
    assert "bd@contact-page.example" in extract_emails(page.html)


class TavilyExtractFakeHttp:
    """Serves Tavily /extract responses (raw_content) and blows up on any direct
    .get so a test can prove the extract path is used, not the fallback."""

    def post(self, url: str, **kwargs):
        assert "api.tavily.com/extract" in url
        target = kwargs["json"]["urls"][0]
        return FakeResponse(
            "",
            json_data={
                "results": [
                    {
                        "url": target,
                        "raw_content": (
                            "# Ortho Extract Co\n\n"
                            "Orthopedic implant distributor for knee arthroplasty.\n"
                            "Contact bd@ortho-extract.example for business development."
                        ),
                    }
                ],
                "failed_results": [],
            },
        )

    def get(self, url: str, **kwargs):
        raise AssertionError("direct .get must not run when Tavily extract succeeds")


def test_title_from_markdown_skips_nav_and_images():
    from app.web_search import _title_from_markdown

    md = (
        "[Skip to content](https://x.example/#content)\n\n"
        "![ITS logo](https://x.example/logo.png)\n\n"
        "# ITS Implant\n\nOrthopedic implants for knee arthroplasty."
    )
    assert _title_from_markdown(md) == "ITS Implant"


def test_extract_tavily_parses_raw_content(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    out = extract_tavily(["https://ortho-extract.example/"], http=TavilyExtractFakeHttp())

    assert out == {
        "https://ortho-extract.example/": (
            "# Ortho Extract Co\n\n"
            "Orthopedic implant distributor for knee arthroplasty.\n"
            "Contact bd@ortho-extract.example for business development."
        )
    }


def test_extract_tavily_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(SearchProviderError):
        extract_tavily(["https://ortho-extract.example/"], http=TavilyExtractFakeHttp())


def test_fetch_page_summary_prefers_tavily_extract(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    # .get raises if called → this only passes via the Tavily extract path.
    page = fetch_page_summary("https://ortho-extract.example/", http=TavilyExtractFakeHttp())

    assert page.title == "Ortho Extract Co"  # derived from the markdown H1
    assert "knee arthroplasty" in page.text
    assert "bd@ortho-extract.example" in extract_emails(page.html)
    assert page.email_source_url == "https://ortho-extract.example/"


def test_discover_real_prospects_uses_search_result_and_page_email(monkeypatch):
    import app.web_search as web_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(web_search, "SEED_PROSPECTS", [])
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    leads = discover_real_prospects(
        target_regions=["Europe"],
        product_profile=profile,
        max_results=1,
        require_email=True,
        http=FakeHttp(),
    )

    assert len(leads) == 1
    assert leads[0].company_name == "Demo Ortho Distribution"
    assert leads[0].email == "sales@demo-ortho.example"
    assert leads[0].website == "https://demo-ortho.example/"
    assert leads[0].source == "https://demo-ortho.example/"
    assert "Email found at https://demo-ortho.example/" in leads[0].notes
    assert leads[0].score >= 70
    assert "total knee arthroplasty" in leads[0].match_reason.lower()


def test_discover_real_prospects_scans_verified_seed_sources_when_they_match_region(monkeypatch):
    import app.web_search as web_search

    monkeypatch.setattr(
        web_search,
        "SEED_PROSPECTS",
        [
            SeedProspect(
                name="Seed Ortho",
                url="https://seed-ortho.example/contact",
                region="Europe",
                country="Germany",
                category="orthopedic implant distributor",
                hint="Verified seed source for orthopedic implant distribution.",
            )
        ],
    )
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    leads = discover_real_prospects(
        target_regions=["Germany"],
        product_profile=profile,
        max_results=1,
        require_email=True,
        http=SeedOnlyFakeHttp(),
    )

    assert len(leads) == 1
    assert leads[0].company_name == "Seed Ortho"
    assert leads[0].email == "bd@seed-ortho.example"
    assert leads[0].source == "https://seed-ortho.example/contact"
    assert "Email found at https://seed-ortho.example/contact" in leads[0].notes


# ── Regression tests: real search must not save non-company junk as leads ────
# (reported: 知乎专栏 / academic journal pages / soft-404 error pages slipping
# into the lead list because they happened to expose a scraped email.)

class ZhihuColumnFakeHttp:
    """A Zhihu column ranks in search results; the domain itself must be
    rejected before any page is even fetched."""

    def post(self, url: str, **kwargs):
        return FakeResponse(
            "",
            json_data={
                "results": [
                    {
                        "title": "骨科机器人行业观察 - 知乎专栏",
                        "url": "https://www.zhihu.com/column/c_123",
                        "content": "分享骨科手术机器人、关节置换行业动态。联系邮箱 columnist@zhihu.com",
                    }
                ]
            },
        )

    def get(self, url: str, **kwargs):
        raise AssertionError("Zhihu domain should be filtered before any page fetch")


def test_discover_real_prospects_rejects_zhihu_column(monkeypatch):
    import app.web_search as web_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(web_search, "SEED_PROSPECTS", [])
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    leads = discover_real_prospects(
        target_regions=["China"],
        product_profile=profile,
        max_results=1,
        require_email=True,
        http=ZhihuColumnFakeHttp(),
    )

    assert leads == []


class AcademicJournalFakeHttp:
    """An academic journal page — on a domain not in any blocklist — with a
    real editorial-office email and even topical (orthopedic) keywords. Must
    still be rejected by the title pattern, not just the domain blocklist."""

    def post(self, url: str, **kwargs):
        return FakeResponse(
            "",
            json_data={
                "results": [
                    {
                        "title": "中国协和医学杂志 - 骨科机器人关节置换研究论文",
                        "url": "https://www.example-pumc-journal.cn/",
                        "content": "本文报道了机器人辅助全膝关节置换手术的临床研究。",
                    }
                ]
            },
        )

    def get(self, url: str, **kwargs):
        return FakeResponse(
            """
            <html>
              <head><title>中国协和医学杂志</title></head>
              <body>
                本刊为骨科与关节置换领域学术期刊，刊登机器人辅助手术相关论文。
                编辑部联系邮箱：editor@example-pumc-journal.cn
              </body>
            </html>
            """
        )


def test_discover_real_prospects_rejects_academic_journal_title(monkeypatch):
    import app.web_search as web_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(web_search, "SEED_PROSPECTS", [])
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    leads = discover_real_prospects(
        target_regions=["China"],
        product_profile=profile,
        max_results=1,
        require_email=True,
        http=AcademicJournalFakeHttp(),
    )

    assert leads == []


class SoftErrorPageFakeHttp:
    """The page returns HTTP 200 but is actually a 'not found' page (common
    for sites that don't set a real 404 status). A stray contact-form email
    template fragment happens to be present in the boilerplate."""

    def post(self, url: str, **kwargs):
        return FakeResponse(
            "",
            json_data={
                "results": [
                    {
                        "title": "Ortho Distributors Directory",
                        "url": "https://broken-ortho.example/old-page",
                        "content": "Orthopedic implant distributor directory listing.",
                    }
                ]
            },
        )

    def get(self, url: str, **kwargs):
        return FakeResponse(
            """
            <html>
              <head><title>404 - Page Not Found</title></head>
              <body>Sorry, this page could not be found. webmaster@broken-ortho.example</body>
            </html>
            """,
            status_code=200,
        )


def test_discover_real_prospects_rejects_soft_404_page(monkeypatch):
    import app.web_search as web_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(web_search, "SEED_PROSPECTS", [])
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    leads = discover_real_prospects(
        target_regions=["Europe"],
        product_profile=profile,
        max_results=1,
        require_email=True,
        http=SoftErrorPageFakeHttp(),
    )

    assert leads == []


class UnrelatedBusinessFakeHttp:
    """A real, legitimate business page with a real email — but nothing to do
    with orthopedics/medical devices/distribution. Must be rejected by the
    topical-relevance gate, not saved just because it has *an* email."""

    def post(self, url: str, **kwargs):
        return FakeResponse(
            "",
            json_data={
                "results": [
                    {
                        "title": "Coffee Roasters Co",
                        "url": "https://coffee-roasters.example/",
                        "content": "Specialty coffee roaster and wholesale supplier.",
                    }
                ]
            },
        )

    def get(self, url: str, **kwargs):
        return FakeResponse(
            """
            <html>
              <head><title>Coffee Roasters Co</title></head>
              <body>We roast and sell specialty coffee beans wholesale. Contact sales@coffee-roasters.example.</body>
            </html>
            """
        )


def test_discover_real_prospects_rejects_topically_unrelated_business(monkeypatch):
    import app.web_search as web_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(web_search, "SEED_PROSPECTS", [])
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    leads = discover_real_prospects(
        target_regions=["Europe"],
        product_profile=profile,
        max_results=1,
        require_email=True,
        http=UnrelatedBusinessFakeHttp(),
    )

    assert leads == []


class DirectoryListicleFakeHttp:
    """A 'Top N companies' listicle: topical and has an email, but it's a page
    ABOUT companies, not a distributor's own site — must be rejected."""

    def post(self, url: str, **kwargs):
        return FakeResponse(
            "",
            json_data={
                "results": [
                    {
                        "title": "Top 10 Orthopedic Implant Companies in India (2026)",
                        "url": "https://blog.example/top-10-orthopedic-implant-companies",
                        "content": "Ranking the best orthopedic implant manufacturers for joint replacement and TKA.",
                    }
                ]
            },
        )

    def get(self, url: str, **kwargs):
        return FakeResponse(
            """
            <html><head><title>Top 10 Orthopedic Implant Companies in India</title></head>
            <body>1. Ortho A — knee arthroplasty implants. Contact info@listco.example.
            2. Ortho B — surgical robotics.</body></html>
            """
        )


def test_discover_real_prospects_rejects_directory_listicle(monkeypatch):
    import app.web_search as web_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(web_search, "SEED_PROSPECTS", [])
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    leads = discover_real_prospects(
        target_regions=["South Asia"],
        product_profile=profile,
        max_results=1,
        require_email=True,
        http=DirectoryListicleFakeHttp(),
    )

    assert leads == []


class MarketConsultancyFakeHttp:
    """A market-entry advisory firm's report about distributors — topical but a
    consultancy, not a channel."""

    def post(self, url: str, **kwargs):
        return FakeResponse(
            "",
            json_data={
                "results": [
                    {
                        "title": "Romania Orthopaedic Implants Importer-Distributors — FRD Center",
                        "url": "https://frdcenter.example/report",
                        "content": "As one of the pioneer market entry advisory firms, our analysis of orthopedic distributors.",
                    }
                ]
            },
        )

    def get(self, url: str, **kwargs):
        return FakeResponse(
            """
            <html><head><title>FRD Center — Market Entry Advisory</title></head>
            <body>Orthopedic implants distributor market research report. Contact europa@frdcenter.example.
            As one of the pioneer market entry advisory firms, we help with market entry.</body></html>
            """
        )


def test_discover_real_prospects_rejects_market_consultancy(monkeypatch):
    import app.web_search as web_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(web_search, "SEED_PROSPECTS", [])
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    leads = discover_real_prospects(
        target_regions=["Europe"],
        product_profile=profile,
        max_results=1,
        require_email=True,
        http=MarketConsultancyFakeHttp(),
    )

    assert leads == []


# ── Tavily is the only search provider. There is no scraping fallback: a ────
# missing key or a failed call must raise, not silently degrade. ────────────

class TavilyFakeHttp:
    def post(self, url: str, **kwargs):
        assert "api.tavily.com" in url
        assert kwargs["json"]["api_key"] == "tvly-test-key"
        return FakeResponse(
            "",
            json_data={
                "results": [
                    {
                        "title": "Demo Ortho Distribution - Orthopedic Implants",
                        "url": "https://demo-ortho.example/",
                        "content": "Orthopedic implant distributor for joint replacement and knee arthroplasty.",
                    }
                ]
            },
        )

    def get(self, url: str, **kwargs):
        return FakeResponse(
            """
            <html>
              <head><title>Demo Ortho Distribution</title></head>
              <body>
                We distribute orthopedic implants, knee arthroplasty products, and hospital robotics.
                Contact sales@demo-ortho.example for business development.
              </body>
            </html>
            """
        )


def test_search_tavily_used_when_api_key_configured(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")

    results = search_tavily("orthopedic distributor Europe", http=TavilyFakeHttp())

    assert len(results) == 1
    assert results[0].title == "Demo Ortho Distribution - Orthopedic Implants"
    assert results[0].url == "https://demo-ortho.example/"


def test_search_tavily_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    class UnusedHttp:
        def post(self, url: str, **kwargs):
            raise AssertionError("should not call Tavily when no API key is configured")

    with pytest.raises(SearchProviderError):
        search_tavily("orthopedic distributor Europe", http=UnusedHttp())


def test_search_web_raises_when_tavily_call_fails(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")

    class FailingHttp:
        def post(self, url: str, **kwargs):
            return FakeResponse("server error", status_code=500)

    with pytest.raises(SearchProviderError):
        search_web("orthopedic distributor Europe", http=FailingHttp())


def test_discover_real_prospects_raises_when_tavily_not_configured(monkeypatch):
    import app.web_search as web_search

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(web_search, "SEED_PROSPECTS", [])
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    class UnusedHttp:
        def post(self, url: str, **kwargs):
            raise AssertionError("should not call Tavily when no API key is configured")

        def get(self, url: str, **kwargs):
            raise AssertionError("should not fetch pages before search succeeds")

    with pytest.raises(SearchProviderError):
        discover_real_prospects(
            target_regions=["Europe"],
            product_profile=profile,
            max_results=1,
            require_email=True,
            http=UnusedHttp(),
        )


def test_discover_real_prospects_uses_tavily_when_configured(monkeypatch):
    import app.web_search as web_search

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(web_search, "SEED_PROSPECTS", [])
    profile = extract_product_profile(Path(__file__).resolve().parents[2])

    leads = discover_real_prospects(
        target_regions=["Europe"],
        product_profile=profile,
        max_results=1,
        require_email=True,
        http=TavilyFakeHttp(),
    )

    assert len(leads) == 1
    assert leads[0].company_name == "Demo Ortho Distribution"
    assert leads[0].email == "sales@demo-ortho.example"
