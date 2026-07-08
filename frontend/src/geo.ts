// Region / country display labels for the lead-management filters.
//
// Regions follow the UN M49 "Standard Country or Area Codes for Statistical
// Use" macro/sub-region taxonomy (unstats.un.org/unsd/methodology/m49),
// expressed with the business-region names this app stores. Countries follow
// ISO 3166-1 English short names.
//
// These maps only provide friendly 中文 + English labels and ordering; the
// actual filter options come from the values present in the database
// (GET /leads/facets), so a value without a label just displays verbatim.

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

// ISO 3166-1 major markets across every region (English name → 中文 · English).
export const COUNTRY_LABELS: Record<string, string> = {
  // North America
  "United States": "美国 · United States",
  Canada: "加拿大 · Canada",
  Mexico: "墨西哥 · Mexico",
  // Latin America
  Brazil: "巴西 · Brazil",
  Argentina: "阿根廷 · Argentina",
  Chile: "智利 · Chile",
  Colombia: "哥伦比亚 · Colombia",
  Peru: "秘鲁 · Peru",
  // Europe
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
  Turkey: "土耳其 · Turkey",
  Russia: "俄罗斯 · Russia",
  // Middle East
  "United Arab Emirates": "阿联酋 · United Arab Emirates",
  "Saudi Arabia": "沙特阿拉伯 · Saudi Arabia",
  Qatar: "卡塔尔 · Qatar",
  Kuwait: "科威特 · Kuwait",
  Israel: "以色列 · Israel",
  Jordan: "约旦 · Jordan",
  Egypt: "埃及 · Egypt",
  // Africa
  "South Africa": "南非 · South Africa",
  Nigeria: "尼日利亚 · Nigeria",
  Kenya: "肯尼亚 · Kenya",
  Morocco: "摩洛哥 · Morocco",
  // South / Central Asia
  India: "印度 · India",
  Pakistan: "巴基斯坦 · Pakistan",
  Bangladesh: "孟加拉国 · Bangladesh",
  "Sri Lanka": "斯里兰卡 · Sri Lanka",
  Kazakhstan: "哈萨克斯坦 · Kazakhstan",
  // Southeast Asia
  Singapore: "新加坡 · Singapore",
  Malaysia: "马来西亚 · Malaysia",
  Thailand: "泰国 · Thailand",
  Indonesia: "印度尼西亚 · Indonesia",
  Philippines: "菲律宾 · Philippines",
  Vietnam: "越南 · Vietnam",
  Myanmar: "缅甸 · Myanmar",
  Cambodia: "柬埔寨 · Cambodia",
  // East Asia
  China: "中国 · China",
  Japan: "日本 · Japan",
  "South Korea": "韩国 · South Korea",
  Taiwan: "中国台湾 · Taiwan",
  "Hong Kong": "中国香港 · Hong Kong",
  // Oceania
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
