from pathlib import Path

from app.product import extract_product_profile
from app.web_search import (
    SeedProspect,
    discover_real_prospects,
    extract_emails,
    fetch_page_summary,
    search_duckduckgo,
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
    def get(self, url: str, **kwargs):
        if "duckduckgo" in url:
            return FakeResponse(
                """
                <div class="result">
                  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdemo-ortho.example%2F">
                    Demo Ortho Distribution - Orthopedic Implants
                  </a>
                  <a class="result__snippet">
                    Orthopedic implant distributor for joint replacement and knee arthroplasty.
                  </a>
                </div>
                """
            )
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
    def get(self, url: str, **kwargs):
        if "duckduckgo" in url:
            return FakeResponse("")
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


class BingFallbackFakeHttp:
    def get(self, url: str, **kwargs):
        if "duckduckgo" in url:
            return FakeResponse("<html><title>DuckDuckGo challenge</title></html>")
        if "bing.com" in url:
            return FakeResponse(
                """
                <ol id="b_results">
                  <li class="b_algo">
                    <h2><a href="https://bing-ortho.example/contact">
                      Bing Ortho India
                    </a></h2>
                    <div class="b_caption">
                      <p>Orthopedic implant distributor serving India.</p>
                    </div>
                  </li>
                </ol>
                """
            )
        return FakeResponse("")


class JinaFallbackFakeHttp:
    def get(self, url: str, **kwargs):
        if "duckduckgo.com/html" in url and "r.jina.ai" not in url:
            return FakeResponse("<html><title>DuckDuckGo challenge</title></html>")
        if "r.jina.ai" in url:
            return FakeResponse(
                """
                Title: orthopedic implant distributor India at DuckDuckGo

                URL Source: https://duckduckgo.com/html/?q=orthopedic%20implant%20distributor%20India

                Markdown Content:
                ## [Smit MediMed Pvt Ltd - Certified Orthopedic Implants Producer](https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.smitmedimed.com%2F)

                [Established in the year 1990, Smit Medimed Pvt Ltd specializes as CDSCO certified Orthopedic Implants Producer.](https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.smitmedimed.com%2F)
                """
            )
        return FakeResponse("")


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


def test_search_duckduckgo_unwraps_real_result_urls():
    results = search_duckduckgo("orthopedic distributor", http=FakeHttp(), limit=1)

    assert results[0].url == "https://demo-ortho.example/"
    assert "Orthopedic Implants" in results[0].title


def test_search_web_falls_back_to_bing_results_when_duckduckgo_is_blocked():
    results = search_web("orthopedic distributor India", http=BingFallbackFakeHttp(), limit=1)

    assert len(results) == 1
    assert results[0].url == "https://bing-ortho.example/contact"
    assert results[0].title == "Bing Ortho India"
    assert results[0].snippet == "Orthopedic implant distributor serving India."
    assert results[0].query == "orthopedic distributor India"


def test_search_web_uses_jina_reader_when_duckduckgo_is_blocked():
    results = search_web("orthopedic implant distributor India", http=JinaFallbackFakeHttp(), limit=1)

    assert len(results) == 1
    assert results[0].url == "https://www.smitmedimed.com/"
    assert results[0].title == "Smit MediMed Pvt Ltd - Certified Orthopedic Implants Producer"
    assert "CDSCO certified Orthopedic Implants Producer" in results[0].snippet


def test_fetch_page_summary_records_where_email_was_found():
    page = fetch_page_summary("https://contact-page.example/", http=ContactPageFakeHttp())

    assert page.email_source_url == "https://contact-page.example/contact"
    assert "bd@contact-page.example" in extract_emails(page.html)


def test_discover_real_prospects_uses_search_result_and_page_email(monkeypatch):
    import app.web_search as web_search

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

    def get(self, url: str, **kwargs):
        if "duckduckgo" in url:
            return FakeResponse(
                """
                <div class="result">
                  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.zhihu.com%2Fcolumn%2Fc_123">
                    骨科机器人行业观察 - 知乎专栏
                  </a>
                  <a class="result__snippet">
                    分享骨科手术机器人、关节置换行业动态。联系邮箱 columnist@zhihu.com
                  </a>
                </div>
                """
            )
        raise AssertionError("Zhihu domain should be filtered before any page fetch")


def test_discover_real_prospects_rejects_zhihu_column(monkeypatch):
    import app.web_search as web_search

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

    def get(self, url: str, **kwargs):
        if "duckduckgo" in url:
            return FakeResponse(
                """
                <div class="result">
                  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example-pumc-journal.cn%2F">
                    中国协和医学杂志 - 骨科机器人关节置换研究论文
                  </a>
                  <a class="result__snippet">
                    本文报道了机器人辅助全膝关节置换手术的临床研究。
                  </a>
                </div>
                """
            )
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

    def get(self, url: str, **kwargs):
        if "duckduckgo" in url:
            return FakeResponse(
                """
                <div class="result">
                  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fbroken-ortho.example%2Fold-page">
                    Ortho Distributors Directory
                  </a>
                  <a class="result__snippet">
                    Orthopedic implant distributor directory listing.
                  </a>
                </div>
                """
            )
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

    def get(self, url: str, **kwargs):
        if "duckduckgo" in url:
            return FakeResponse(
                """
                <div class="result">
                  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fcoffee-roasters.example%2F">
                    Coffee Roasters Co
                  </a>
                  <a class="result__snippet">
                    Specialty coffee roaster and wholesale supplier.
                  </a>
                </div>
                """
            )
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


# ── Tavily as the primary search provider (DuckDuckGo/Bing are unreliable ───
# from mainland China networks) ──────────────────────────────────────────────

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


def test_search_tavily_returns_empty_without_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    class UnusedHttp:
        def post(self, url: str, **kwargs):
            raise AssertionError("should not call Tavily when no API key is configured")

    assert search_tavily("orthopedic distributor Europe", http=UnusedHttp()) == []


def test_search_web_prefers_tavily_over_duckduckgo(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")

    class DuckDuckGoShouldNotBeCalled(TavilyFakeHttp):
        def get(self, url: str, **kwargs):
            if "duckduckgo" in url:
                raise AssertionError("should not fall back to DuckDuckGo when Tavily succeeds")
            return super().get(url, **kwargs)

    results = search_web("orthopedic distributor Europe", http=DuckDuckGoShouldNotBeCalled())

    assert len(results) == 1
    assert results[0].url == "https://demo-ortho.example/"


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
