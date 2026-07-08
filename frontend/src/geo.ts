// Region / country taxonomy for lead management (filters + the add-lead form).
//
// Regions follow the UN M49 "Standard Country or Area Codes for Statistical
// Use" macro/sub-region taxonomy (unstats.un.org/unsd/methodology/m49),
// expressed with the business-region names this app stores. Countries follow
// ISO 3166-1 English short names.
//
// This is the frontend mirror of backend/app/geo.py — keep the region set and
// the country→region mapping in sync between the two. The backend re-normalizes
// region/country on write (normalize_geo), so these values are the canonical
// ones it stores; picking them here means every option round-trips cleanly.

// UN M49-aligned regions, ordered roughly west→east / by prominence for this
// business. `value` matches what the backend stores.
export const STANDARD_REGIONS: { value: string; label: string }[] = [
  { value: "North America", label: "北美 · North America" },
  { value: "Latin America", label: "拉丁美洲 · Latin America" },
  { value: "Europe", label: "欧洲 · Europe" },
  { value: "Middle East", label: "中东 · Middle East" },
  { value: "Africa", label: "非洲 · Africa" },
  { value: "Central Asia", label: "中亚 · Central Asia" },
  { value: "South Asia", label: "南亚 · South Asia" },
  { value: "Southeast Asia", label: "东南亚 · Southeast Asia" },
  { value: "East Asia", label: "东亚 · East Asia" },
  { value: "Oceania", label: "大洋洲 · Oceania" },
];

// ISO 3166-1 country (canonical) → standard region. Mirrors
// backend/app/geo.py COUNTRY_TO_REGION. Ordered by region so the grouped
// dropdown options come out in a sensible order.
export const COUNTRY_TO_REGION: Record<string, string> = {
  // North America
  "United States": "North America",
  Canada: "North America",
  // Latin America
  Mexico: "Latin America",
  Brazil: "Latin America",
  Argentina: "Latin America",
  Chile: "Latin America",
  Colombia: "Latin America",
  Peru: "Latin America",
  Venezuela: "Latin America",
  Ecuador: "Latin America",
  Bolivia: "Latin America",
  Uruguay: "Latin America",
  Paraguay: "Latin America",
  Guatemala: "Latin America",
  "Costa Rica": "Latin America",
  Panama: "Latin America",
  "Dominican Republic": "Latin America",
  // Europe
  Germany: "Europe",
  France: "Europe",
  "United Kingdom": "Europe",
  Italy: "Europe",
  Spain: "Europe",
  Netherlands: "Europe",
  Switzerland: "Europe",
  Belgium: "Europe",
  Sweden: "Europe",
  Poland: "Europe",
  Austria: "Europe",
  Portugal: "Europe",
  Ireland: "Europe",
  Denmark: "Europe",
  Norway: "Europe",
  Finland: "Europe",
  Greece: "Europe",
  "Czech Republic": "Europe",
  Hungary: "Europe",
  Romania: "Europe",
  Ukraine: "Europe",
  Russia: "Europe",
  Turkey: "Europe",
  // Middle East
  "United Arab Emirates": "Middle East",
  "Saudi Arabia": "Middle East",
  Qatar: "Middle East",
  Kuwait: "Middle East",
  Bahrain: "Middle East",
  Oman: "Middle East",
  Israel: "Middle East",
  Jordan: "Middle East",
  Lebanon: "Middle East",
  Iraq: "Middle East",
  Iran: "Middle East",
  Egypt: "Middle East",
  // Africa
  "South Africa": "Africa",
  Nigeria: "Africa",
  Kenya: "Africa",
  Morocco: "Africa",
  Algeria: "Africa",
  Tunisia: "Africa",
  Ghana: "Africa",
  Ethiopia: "Africa",
  Tanzania: "Africa",
  Uganda: "Africa",
  // Central Asia
  Kazakhstan: "Central Asia",
  Uzbekistan: "Central Asia",
  Turkmenistan: "Central Asia",
  Kyrgyzstan: "Central Asia",
  Tajikistan: "Central Asia",
  // South Asia
  India: "South Asia",
  Pakistan: "South Asia",
  Bangladesh: "South Asia",
  "Sri Lanka": "South Asia",
  Nepal: "South Asia",
  // Southeast Asia
  Singapore: "Southeast Asia",
  Malaysia: "Southeast Asia",
  Thailand: "Southeast Asia",
  Indonesia: "Southeast Asia",
  Philippines: "Southeast Asia",
  Vietnam: "Southeast Asia",
  Myanmar: "Southeast Asia",
  Cambodia: "Southeast Asia",
  Laos: "Southeast Asia",
  Brunei: "Southeast Asia",
  // East Asia
  China: "East Asia",
  Japan: "East Asia",
  "South Korea": "East Asia",
  Taiwan: "East Asia",
  "Hong Kong": "East Asia",
  Macau: "East Asia",
  Mongolia: "East Asia",
  // Oceania
  Australia: "Oceania",
  "New Zealand": "Oceania",
};

// ISO 3166-1 name → 中文 · English display label. Covers every country in
// COUNTRY_TO_REGION; unknown countries fall back to their verbatim value.
export const COUNTRY_LABELS: Record<string, string> = {
  "United States": "美国 · United States",
  Canada: "加拿大 · Canada",
  Mexico: "墨西哥 · Mexico",
  Brazil: "巴西 · Brazil",
  Argentina: "阿根廷 · Argentina",
  Chile: "智利 · Chile",
  Colombia: "哥伦比亚 · Colombia",
  Peru: "秘鲁 · Peru",
  Venezuela: "委内瑞拉 · Venezuela",
  Ecuador: "厄瓜多尔 · Ecuador",
  Bolivia: "玻利维亚 · Bolivia",
  Uruguay: "乌拉圭 · Uruguay",
  Paraguay: "巴拉圭 · Paraguay",
  Guatemala: "危地马拉 · Guatemala",
  "Costa Rica": "哥斯达黎加 · Costa Rica",
  Panama: "巴拿马 · Panama",
  "Dominican Republic": "多米尼加 · Dominican Republic",
  Germany: "德国 · Germany",
  France: "法国 · France",
  "United Kingdom": "英国 · United Kingdom",
  Italy: "意大利 · Italy",
  Spain: "西班牙 · Spain",
  Netherlands: "荷兰 · Netherlands",
  Switzerland: "瑞士 · Switzerland",
  Belgium: "比利时 · Belgium",
  Sweden: "瑞典 · Sweden",
  Poland: "波兰 · Poland",
  Austria: "奥地利 · Austria",
  Portugal: "葡萄牙 · Portugal",
  Ireland: "爱尔兰 · Ireland",
  Denmark: "丹麦 · Denmark",
  Norway: "挪威 · Norway",
  Finland: "芬兰 · Finland",
  Greece: "希腊 · Greece",
  "Czech Republic": "捷克 · Czech Republic",
  Hungary: "匈牙利 · Hungary",
  Romania: "罗马尼亚 · Romania",
  Ukraine: "乌克兰 · Ukraine",
  Russia: "俄罗斯 · Russia",
  Turkey: "土耳其 · Turkey",
  "United Arab Emirates": "阿联酋 · United Arab Emirates",
  "Saudi Arabia": "沙特阿拉伯 · Saudi Arabia",
  Qatar: "卡塔尔 · Qatar",
  Kuwait: "科威特 · Kuwait",
  Bahrain: "巴林 · Bahrain",
  Oman: "阿曼 · Oman",
  Israel: "以色列 · Israel",
  Jordan: "约旦 · Jordan",
  Lebanon: "黎巴嫩 · Lebanon",
  Iraq: "伊拉克 · Iraq",
  Iran: "伊朗 · Iran",
  Egypt: "埃及 · Egypt",
  "South Africa": "南非 · South Africa",
  Nigeria: "尼日利亚 · Nigeria",
  Kenya: "肯尼亚 · Kenya",
  Morocco: "摩洛哥 · Morocco",
  Algeria: "阿尔及利亚 · Algeria",
  Tunisia: "突尼斯 · Tunisia",
  Ghana: "加纳 · Ghana",
  Ethiopia: "埃塞俄比亚 · Ethiopia",
  Tanzania: "坦桑尼亚 · Tanzania",
  Uganda: "乌干达 · Uganda",
  Kazakhstan: "哈萨克斯坦 · Kazakhstan",
  Uzbekistan: "乌兹别克斯坦 · Uzbekistan",
  Turkmenistan: "土库曼斯坦 · Turkmenistan",
  Kyrgyzstan: "吉尔吉斯斯坦 · Kyrgyzstan",
  Tajikistan: "塔吉克斯坦 · Tajikistan",
  India: "印度 · India",
  Pakistan: "巴基斯坦 · Pakistan",
  Bangladesh: "孟加拉国 · Bangladesh",
  "Sri Lanka": "斯里兰卡 · Sri Lanka",
  Nepal: "尼泊尔 · Nepal",
  Singapore: "新加坡 · Singapore",
  Malaysia: "马来西亚 · Malaysia",
  Thailand: "泰国 · Thailand",
  Indonesia: "印度尼西亚 · Indonesia",
  Philippines: "菲律宾 · Philippines",
  Vietnam: "越南 · Vietnam",
  Myanmar: "缅甸 · Myanmar",
  Cambodia: "柬埔寨 · Cambodia",
  Laos: "老挝 · Laos",
  Brunei: "文莱 · Brunei",
  China: "中国 · China",
  Japan: "日本 · Japan",
  "South Korea": "韩国 · South Korea",
  Taiwan: "中国台湾 · Taiwan",
  "Hong Kong": "中国香港 · Hong Kong",
  Macau: "中国澳门 · Macau",
  Mongolia: "蒙古 · Mongolia",
  Australia: "澳大利亚 · Australia",
  "New Zealand": "新西兰 · New Zealand",
};

const REGION_LABEL_MAP: Record<string, string> = Object.fromEntries(
  STANDARD_REGIONS.map((r) => [r.value, r.label]),
);

export function labelForRegion(value: string): string {
  return REGION_LABEL_MAP[value] || value;
}

export function labelForCountry(value: string): string {
  return COUNTRY_LABELS[value] || value;
}

// Standard region → its member countries (as `{ label, value }`), in the region
// order above and alphabetized within each region by English name.
export function countryGroupsByRegion(): {
  region: string;
  label: string;
  countries: { value: string; label: string }[];
}[] {
  return STANDARD_REGIONS.map((region) => ({
    region: region.value,
    label: region.label,
    countries: Object.keys(COUNTRY_TO_REGION)
      .filter((c) => COUNTRY_TO_REGION[c] === region.value)
      .sort()
      .map((c) => ({ value: c, label: labelForCountry(c) })),
  })).filter((g) => g.countries.length > 0);
}
