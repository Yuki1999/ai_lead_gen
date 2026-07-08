from app.geo import normalize_country, normalize_geo, normalize_region


def test_normalize_country_canonicalizes_aliases_and_case():
    assert normalize_country("usa") == "United States"
    assert normalize_country("U.K.") == "United Kingdom"
    assert normalize_country("UAE") == "United Arab Emirates"
    assert normalize_country("deutschland") == "Germany"
    assert normalize_country("germany") == "Germany"
    assert normalize_country("德国") == "Germany"


def test_normalize_country_drops_region_names_and_keeps_unknowns():
    # A region name mistakenly placed in the country field is not a country.
    assert normalize_country("Europe") == ""
    assert normalize_country("Southeast Asia") == ""
    # Unknown but plausible country passes through unchanged.
    assert normalize_country("Fictionland") == "Fictionland"
    assert normalize_country("") == ""


def test_normalize_region_matches_standard_and_aliases():
    assert normalize_region("europe") == "Europe"
    assert normalize_region("EU") == "Europe"
    assert normalize_region("ASEAN") == "Southeast Asia"
    assert normalize_region("Gulf") == "Middle East"
    assert normalize_region("拉美") == "Latin America"


def test_normalize_region_infers_from_country_when_non_standard():
    # Real-search path stores country == region; inference fixes the region.
    assert normalize_region("India", country="India") == "South Asia"
    assert normalize_region("", country="Germany") == "Europe"
    assert normalize_region("Deutschland", country="Germany") == "Europe"


def test_normalize_geo_fixes_country_equals_region_case():
    # discover_real_prospects sets country = region; normalization recovers both.
    region, country = normalize_geo("India", "India")
    assert (region, country) == ("South Asia", "India")

    region, country = normalize_geo("Europe", "Europe")
    assert region == "Europe"
    assert country == ""  # "Europe" is a region, not a country


def test_insert_lead_persists_normalized_geo(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "geo.db"))
    from app import db
    from app.services import CandidateLead

    db.init_db()
    lead = db.insert_lead(
        CandidateLead(
            company_name="Alias Co",
            region="EU",
            country="deutschland",
            website="",
            contact_name="",
            email="a@alias.example",
            category="distributor",
            match_reason="",
            source="test",
            score=80,
        )
    )
    assert lead["region"] == "Europe"
    assert lead["country"] == "Germany"
