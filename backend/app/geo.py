"""Region / country normalization to a public standard.

Every lead-creation path (Agent `add_leads`, real web search, seeds, demo,
manual) funnels through `insert_lead`, which calls `normalize_geo` so the
stored `region` / `country` always match the same taxonomy the frontend filters
and labels use:

- Regions: UN M49 macro/sub-regions, expressed as business-region names.
- Countries: ISO 3166-1 English short names.

The frontend counterpart (frontend/src/geo.ts) provides the display labels;
keep the region set and country→region mapping in sync between the two.
"""

from __future__ import annotations

# Canonical business regions (UN M49-aligned), west→east ordering.
STANDARD_REGIONS: list[str] = [
    "North America",
    "Latin America",
    "Europe",
    "Middle East",
    "Africa",
    "Central Asia",
    "South Asia",
    "Southeast Asia",
    "East Asia",
    "Oceania",
]

# ISO 3166-1 country (canonical) → standard region. Covers the major markets;
# unknown countries pass through unchanged and simply don't infer a region.
COUNTRY_TO_REGION: dict[str, str] = {
    # North America
    "United States": "North America",
    "Canada": "North America",
    # Latin America
    "Mexico": "Latin America",
    "Brazil": "Latin America",
    "Argentina": "Latin America",
    "Chile": "Latin America",
    "Colombia": "Latin America",
    "Peru": "Latin America",
    "Venezuela": "Latin America",
    "Ecuador": "Latin America",
    "Bolivia": "Latin America",
    "Uruguay": "Latin America",
    "Paraguay": "Latin America",
    "Guatemala": "Latin America",
    "Costa Rica": "Latin America",
    "Panama": "Latin America",
    "Dominican Republic": "Latin America",
    # Europe
    "Germany": "Europe",
    "France": "Europe",
    "United Kingdom": "Europe",
    "Italy": "Europe",
    "Spain": "Europe",
    "Netherlands": "Europe",
    "Switzerland": "Europe",
    "Belgium": "Europe",
    "Sweden": "Europe",
    "Poland": "Europe",
    "Austria": "Europe",
    "Portugal": "Europe",
    "Ireland": "Europe",
    "Denmark": "Europe",
    "Norway": "Europe",
    "Finland": "Europe",
    "Greece": "Europe",
    "Czech Republic": "Europe",
    "Hungary": "Europe",
    "Romania": "Europe",
    "Ukraine": "Europe",
    "Russia": "Europe",
    "Turkey": "Europe",
    # Middle East
    "United Arab Emirates": "Middle East",
    "Saudi Arabia": "Middle East",
    "Qatar": "Middle East",
    "Kuwait": "Middle East",
    "Bahrain": "Middle East",
    "Oman": "Middle East",
    "Israel": "Middle East",
    "Jordan": "Middle East",
    "Lebanon": "Middle East",
    "Iraq": "Middle East",
    "Iran": "Middle East",
    "Egypt": "Middle East",
    # Africa
    "South Africa": "Africa",
    "Nigeria": "Africa",
    "Kenya": "Africa",
    "Morocco": "Africa",
    "Algeria": "Africa",
    "Tunisia": "Africa",
    "Ghana": "Africa",
    "Ethiopia": "Africa",
    "Tanzania": "Africa",
    "Uganda": "Africa",
    # Central Asia
    "Kazakhstan": "Central Asia",
    "Uzbekistan": "Central Asia",
    "Turkmenistan": "Central Asia",
    "Kyrgyzstan": "Central Asia",
    "Tajikistan": "Central Asia",
    # South Asia
    "India": "South Asia",
    "Pakistan": "South Asia",
    "Bangladesh": "South Asia",
    "Sri Lanka": "South Asia",
    "Nepal": "South Asia",
    # Southeast Asia
    "Singapore": "Southeast Asia",
    "Malaysia": "Southeast Asia",
    "Thailand": "Southeast Asia",
    "Indonesia": "Southeast Asia",
    "Philippines": "Southeast Asia",
    "Vietnam": "Southeast Asia",
    "Myanmar": "Southeast Asia",
    "Cambodia": "Southeast Asia",
    "Laos": "Southeast Asia",
    "Brunei": "Southeast Asia",
    # East Asia
    "China": "East Asia",
    "Japan": "East Asia",
    "South Korea": "East Asia",
    "Taiwan": "East Asia",
    "Hong Kong": "East Asia",
    "Macau": "East Asia",
    "Mongolia": "East Asia",
    # Oceania
    "Australia": "Oceania",
    "New Zealand": "Oceania",
}

# Common variants / abbreviations / Chinese names → canonical ISO country name.
COUNTRY_ALIASES: dict[str, str] = {
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "america": "United States",
    "united states of america": "United States",
    "美国": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "英国": "United Kingdom",
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "阿联酋": "United Arab Emirates",
    "ksa": "Saudi Arabia",
    "沙特": "Saudi Arabia",
    "沙特阿拉伯": "Saudi Arabia",
    "korea": "South Korea",
    "republic of korea": "South Korea",
    "s. korea": "South Korea",
    "韩国": "South Korea",
    "deutschland": "Germany",
    "德国": "Germany",
    "法国": "France",
    "意大利": "Italy",
    "西班牙": "Spain",
    "holland": "Netherlands",
    "荷兰": "Netherlands",
    "瑞士": "Switzerland",
    "prc": "China",
    "mainland china": "China",
    "中国": "China",
    "日本": "Japan",
    "印度": "India",
    "巴基斯坦": "Pakistan",
    "新加坡": "Singapore",
    "马来西亚": "Malaysia",
    "泰国": "Thailand",
    "印度尼西亚": "Indonesia",
    "印尼": "Indonesia",
    "越南": "Vietnam",
    "菲律宾": "Philippines",
    "澳大利亚": "Australia",
    "澳洲": "Australia",
    "新西兰": "New Zealand",
    "巴西": "Brazil",
    "墨西哥": "Mexico",
    "加拿大": "Canada",
    "南非": "South Africa",
    "埃及": "Egypt",
    "土耳其": "Turkey",
    "俄罗斯": "Russia",
}

# Region variants / trade blocs / Chinese names → canonical standard region.
REGION_ALIASES: dict[str, str] = {
    "na": "North America",
    "n. america": "North America",
    "北美": "North America",
    "北美洲": "North America",
    "latam": "Latin America",
    "latin america and the caribbean": "Latin America",
    "south america": "Latin America",
    "central america": "Latin America",
    "拉美": "Latin America",
    "拉丁美洲": "Latin America",
    "南美": "Latin America",
    "eu": "Europe",
    "european union": "Europe",
    "emea europe": "Europe",
    "欧洲": "Europe",
    "欧盟": "Europe",
    "gcc": "Middle East",
    "gulf": "Middle East",
    "mena": "Middle East",
    "中东": "Middle East",
    "海湾": "Middle East",
    "非洲": "Africa",
    "sub-saharan africa": "Africa",
    "中亚": "Central Asia",
    "南亚": "South Asia",
    "asean": "Southeast Asia",
    "sea": "Southeast Asia",
    "s.e. asia": "Southeast Asia",
    "东南亚": "Southeast Asia",
    "东亚": "East Asia",
    "greater china": "East Asia",
    "oceania": "Oceania",
    "australasia": "Oceania",
    "大洋洲": "Oceania",
    "亚太": "",  # APAC is too broad to map to one region; leave for country inference
    "apac": "",
}

_COUNTRY_CANON_BY_LOWER = {name.lower(): name for name in COUNTRY_TO_REGION}
_REGION_CANON_BY_LOWER = {name.lower(): name for name in STANDARD_REGIONS}
_REGION_TOKENS = set(_REGION_CANON_BY_LOWER) | set(REGION_ALIASES)


def normalize_country(raw: str) -> str:
    """Canonicalize a country to its ISO 3166-1 English short name.

    Unknown countries pass through (stripped) unchanged. A value that is really
    a region name (e.g. "Europe") is treated as "no country".
    """
    value = (raw or "").strip()
    if not value:
        return ""
    key = value.lower()
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    if key in _COUNTRY_CANON_BY_LOWER:
        return _COUNTRY_CANON_BY_LOWER[key]
    # A region name mistakenly placed in the country field is not a country.
    if key in _REGION_TOKENS:
        return ""
    return value


def normalize_region(raw: str, country: str = "") -> str:
    """Canonicalize a region to the standard taxonomy.

    Prefers an explicit standard/aliased region; otherwise infers it from the
    (already-canonical) country; otherwise keeps the original value.
    """
    value = (raw or "").strip()
    key = value.lower()
    if key in _REGION_CANON_BY_LOWER:
        return _REGION_CANON_BY_LOWER[key]
    if key in REGION_ALIASES and REGION_ALIASES[key]:
        return REGION_ALIASES[key]
    inferred = COUNTRY_TO_REGION.get(country)
    if inferred:
        return inferred
    return value


def normalize_geo(region: str, country: str) -> tuple[str, str]:
    """Return `(region, country)` canonicalized to the public standard."""
    country_canon = normalize_country(country)
    region_canon = normalize_region(region, country_canon)
    return region_canon, country_canon
