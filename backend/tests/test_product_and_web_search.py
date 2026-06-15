from pathlib import Path

from app.product import extract_product_profile
from app.web_search import (
    SeedProspect,
    discover_real_prospects,
    extract_emails,
    fetch_page_summary,
    search_duckduckgo,
    search_web,
)


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, content_type: str = "text/html"):
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": content_type}


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
