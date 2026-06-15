---
name: overseas-distributor-prospecting
description: Use when conducting overseas distributor prospecting for Medbot, 微创畅行机器人, SkyWalker TKA, orthopedic surgical robotics, orthopedic navigation, joint replacement, TKA, or medical device channel development.
---

# Overseas Distributor Prospecting

## 1. Skill Purpose

Use this skill when the user wants to discover, qualify, score, deduplicate, and organize overseas distributor leads for Medbot / 微创畅行机器人 / SkyWalker® TKA or adjacent orthopedic surgical robotics products.

The skill is designed for overseas BD, channel development, sales operations, and market-entry research.  
The final output should normally be a Chinese structured research report with traceable public evidence.

This skill focuses on:

- Distributor lead discovery
- Existing lead deduplication
- Public evidence collection
- Lead qualification
- Fit scoring
- Priority ranking
- Chinese structured research report generation

This skill does **not** handle:

- Email outreach writing
- Email sending
- Outreach sequence management
- Reply triage
- Pricing discussion
- Contract negotiation
- Distributor authorization commitment
- Regulatory ownership commitment
- Clinical claims or adverse-event handling

If the user asks for any excluded activity, stop and explain that this skill only covers distributor research and qualification. Escalate commercial, legal, regulatory, clinical, warranty, liability, tender, exclusivity, or contract matters to a human.

---

## 2. Product Context

The target product context is SkyWalker® Robotic Platform Total Knee Application.

Core positioning:

- CT-based robotic platform for total knee arthroplasty, also known as TKA.
- Supports patient-specific preoperative planning.
- Supports intraoperative plan adjustment.
- Provides real-time gap balancing and intraoperative data insights.
- Uses robotically located cutting planes and motion-follow cutting block capability.
- Compatible with Evolution® Medial-Pivot Knee implant workflows.

Prioritize distributor candidates connected to:

- Orthopedic implants
- Joint replacement
- Knee arthroplasty
- Total knee arthroplasty / TKA
- Surgical robotics
- Orthopedic navigation
- Operating-room capital equipment
- Surgical instruments
- Hospital robotics distribution
- Medical device channel distribution
- Importation or distribution of Class II / Class III medical devices, where applicable

Do not require a company to already sell surgical robots.  
A company can still be relevant if it has strong orthopedic implant, joint replacement, hospital capital equipment, OR equipment, or surgical navigation channels.

---

## 3. Trigger Conditions

Use this skill when the user asks for any of the following:

- Find overseas distributors for SkyWalker TKA.
- Search medical device distributors in a target country.
- Build a lead list for orthopedic surgical robot channels.
- Qualify distributor candidates.
- Score distributor leads.
- Deduplicate distributor leads.
- Generate a distributor prospecting report.
- Research potential partners for orthopedic implants, joint replacement, TKA, surgical navigation, or hospital robotics.

Do not use this skill for:

- Writing outreach emails.
- Reply classification.
- CRM follow-up automation.
- Contract or pricing advice.
- Regulatory filing advice.
- Hospital end-user sales unless the hospital also operates a distribution or reseller business.

---

## 4. Required Inputs

Before detailed prospecting, identify these inputs:

| Input | Required | Notes |
| --- | --- | --- |
| Product | Optional | Default to SkyWalker TKA if not specified. |
| Target market | Required | Country, region, trade zone, or sales territory. |
| Ideal channel type | Optional | Default to orthopedic implant / joint replacement / surgical equipment distributor. |
| Lead count | Optional | Default to 10 retained leads if user does not specify. |
| Existing lead database | Optional | Use if available for deduplication. |
| Output format | Optional | Default to Chinese structured report. |

If the user does not specify a target country or region, ask one concise clarification question before conducting detailed prospecting.

Example:

> 请先指定目标市场，例如“沙特”“巴西”“东南亚”“德国/奥地利/瑞士”等。这个 skill 需要目标区域才能避免泛泛搜索。

If the user gives a broad region such as “Europe” or “Middle East,” proceed by grouping results by country and state that coverage is regional, not exhaustive.

---

## 5. Non-Negotiable Rules

The agent must follow these rules:

1. Do not invent companies, contacts, emails, websites, URLs, source evidence, scores, or locations.
2. Every retained lead must have at least one public source.
3. Prefer official company websites and official source evidence.
4. If no public email is found, record the official contact page instead of fabricating an email.
5. Do not include hospitals as end users unless they also operate a distribution, reseller, importer, or channel business.
6. Exclude media sites, job boards, pure consultants, generic import-export firms without medical device evidence, consumer product sellers, unrelated industrial robotics companies, and unsupported entities.
7. Deduplicate before reporting.
8. Do not include duplicate companies.
9. Keep match reasons evidence-based and concise.
10. If evidence is incomplete, state the gap clearly.
11. Use only these status values: `new`, `qualified`, `human_review`, `rejected`.
12. Rejected leads should normally be excluded from the final report unless the user explicitly asks to see rejected leads.
13. Do not generate outreach email content.
14. Do not include send status.
15. Escalate legal, exclusivity, regulatory ownership, tender, contract, warranty, liability, clinical-claim, or adverse-event topics to a human.

---

## 6. Execution Workflow

### Step 0: Interpret the Request

Extract:

- Product or product family
- Target country / region
- Desired number of leads
- Any exclusions
- Whether the user provided an existing lead list or database
- Whether the user wants a standard or compact report

If product is not specified, use:

> SkyWalker TKA orthopedic surgical robot / orthopedic robotic platform for total knee arthroplasty.

If target market is missing, ask for it before deep research.

---

### Step 1: Deduplicate Existing Leads

Before adding or reporting any lead, check against existing leads when available.

If the environment provides a `list_leads` tool, call it before searching or adding new leads.

Extract and normalize:

- Company names, lowercase
- Website domains
- Email domains
- Exact emails
- Known aliases or local-language names

Reject a candidate as duplicate if it matches existing leads by:

- Company name, case-insensitive
- Website domain
- Email domain
- Exact email
- Clear alias / subsidiary identity

If no database or `list_leads` tool is available, state in the report:

> 本轮去重仅基于当前调研会话内已发现线索，未接入历史 lead database。

Do not over-report dedup details unless they affect the final lead list.

---

### Step 2: Build a Search Plan

Create search batches before searching.

Use at least three search angles when possible:

#### A. Orthopedic Channel Search

Use terms such as:

- `orthopedic implant distributor {country}`
- `orthopedic implants distributor {country}`
- `joint replacement distributor {country}`
- `knee implant distributor {country}`
- `total knee arthroplasty distributor {country}`
- `TKA distributor {country}`
- `arthroplasty products distributor {country}`

#### B. Surgical Equipment / Capital Equipment Search

Use terms such as:

- `surgical equipment distributor {country}`
- `operating room equipment distributor {country}`
- `hospital capital equipment distributor {country}`
- `medical device distributor orthopedics {country}`
- `surgical instruments distributor orthopedics {country}`

#### C. Robotics / Navigation / Advanced Surgery Search

Use terms such as:

- `surgical robotics distributor {country}`
- `orthopedic navigation distributor {country}`
- `robotic surgery distributor {country}`
- `computer assisted orthopedic surgery distributor {country}`
- `navigation system medical distributor {country}`

#### D. Evidence-Source Search

Use source-oriented terms such as:

- `{country} medical device distributor orthopedic`
- `{country} medical device importer orthopedic`
- `{country} medical device association distributor`
- `{country} orthopedic congress exhibitor distributor`
- `{country} hospital equipment distributor`
- `site:{company_domain} orthopedics`
- `site:{company_domain} joint replacement`
- `site:{company_domain} distributor`

For non-English markets, add local-language equivalents where possible.

Examples:

- Spanish: `distribuidor de implantes ortopédicos`, `distribuidor de dispositivos médicos`, `artroplastia de rodilla`
- Portuguese: `distribuidor de implantes ortopédicos`, `dispositivos médicos`, `artroplastia do joelho`
- French: `distributeur implants orthopédiques`, `dispositifs médicaux`, `arthroplastie du genou`
- German: `Orthopädie Implantate Vertrieb`, `Medizintechnik Distributor`, `Knieendoprothetik`
- Arabic: use English plus local market terms when reliable local-language search is difficult

---

### Step 3: Collect Candidate Leads

For each candidate, collect only verifiable facts.

Preferred evidence hierarchy:

| Evidence Level | Source Type | Use |
| --- | --- | --- |
| Level 1 | Official company website, official product/portfolio page, official contact page | Strong primary evidence |
| Level 2 | Manufacturer distributor page, regulatory/importer directory, official exhibitor list, association directory | Strong supporting evidence |
| Level 3 | Public catalog, brochure, press release, credible trade directory | Supporting evidence |
| Level 4 | LinkedIn company page or social page | Supporting evidence only; avoid as sole source when possible |

Do not retain a lead if no credible source confirms medical device, orthopedic, surgical equipment, hospital equipment, importer, distributor, or channel activity.

---

### Step 4: Extract Required Fields

For every retained lead, capture:

| Field | Requirement |
| --- | --- |
| `company_name` | Legal or trading name. |
| `local_name` | Local-language name if available. |
| `region` | Region, such as Europe, Middle East, Southeast Asia. |
| `country` | Country or primary market. |
| `city` | City or headquarters location if available. |
| `website` | Official website URL. |
| `contact_name` | Named BD / sales / product / distributor contact if public; otherwise department. |
| `email` | Public business email if available. Prioritize sales, BD, distributor, info, or medical-device business emails. |
| `contact_page` | Official contact page if email is unavailable. |
| `category` | Distributor or channel type. |
| `portfolio_fit` | Orthopedics / implants / joint replacement / surgical equipment / robotics / navigation / hospital capital equipment. |
| `match_reason` | Evidence-based explanation of why this company fits. |
| `source` | URLs and short source notes. |
| `evidence_level` | Level 1 / Level 2 / Level 3 / Level 4. |
| `score` | 0–100 fit score. |
| `status` | `new`, `qualified`, `human_review`, or `rejected`. |
| `notes` | Evidence gaps, verification notes, dedup notes, owner assignment if any. |

---

### Step 5: Score Each Lead

Start from 0 and apply the rules below.

Positive scoring:

- +25 if the official site confirms medical device distribution, importation, or channel sales.
- +20 if the company has clear orthopedic implants, joint replacement, knee arthroplasty, surgical equipment, robotics, navigation, or OR capital equipment relevance.
- +15 if a visible business email or official contact form is available.
- +15 if the company’s country or regional coverage matches the target market.
- +10 if a named business development, sales, product, or distributor contact is available.
- +10 if the company appears in a manufacturer partner page, official exhibitor list, regulatory/importer directory, or medical device association directory.
- +5 if the company has multi-country coverage that is relevant to the target region.

Negative scoring:

- -20 if source evidence is weak or incomplete.
- -20 if only LinkedIn/social/trade-directory evidence is available and no official site confirmation exists.
- -30 if the company is unrelated to healthcare robotics, orthopedic devices, medical distribution, surgical equipment, or hospital equipment.
- -30 if the company appears to be hospital-only, media-only, consultant-only, job-board-only, consumer-only, or unrelated industrial robotics.
- -40 if the lead is a confirmed duplicate.

Clamp score to 0–100.

Recommended interpretation:

| Score | Meaning | Usual Status |
| ---: | --- | --- |
| 80–100 | Strong fit | `qualified` |
| 60–79 | Good / medium fit | `new` or `human_review` |
| 40–59 | Possible fit, needs manual verification | `human_review` |
| Below 40 | Weak fit or reject | `rejected` |

Do not force a high score.  
A company with broad medical device distribution but no orthopedic evidence should normally be medium-fit or human-review.

---

### Step 6: Assign Status

Use only the following statuses.

#### `qualified`

Use when:

- Strong public evidence confirms relevant distribution fit.
- The company clearly serves medical device, orthopedic, joint replacement, surgical equipment, hospital capital equipment, navigation, or surgical robotics channels.
- Contact route is available through public email or official contact page.

#### `new`

Use when:

- The company is a new non-duplicate lead.
- Evidence is sufficient to retain it.
- Fit is good but not yet manually verified.

#### `human_review`

Use when:

- Evidence is promising but incomplete.
- The company may be a distributor but source evidence is indirect.
- The company has broad medical device coverage but orthopedic fit is unclear.
- The company may require regulatory, exclusivity, authorization, or territory review.
- The lead has only a contact form and no email, but otherwise looks relevant.

#### `rejected`

Use when:

- The company is clearly unrelated.
- The company is a duplicate.
- The company is hospital-only.
- The company is media-only, consultant-only, job-board-only, consumer-only, or unsupported by evidence.
- The company has no credible medical device or hospital equipment channel evidence.

Rejected leads should normally be excluded from the final report unless explicitly requested.

---

### Step 7: Quality Control Before Final Output

Before returning the report, verify:

- Each retained lead has at least one source URL.
- Each source actually supports the match reason.
- No company appears twice under aliases.
- No hospital-only end users are included.
- No fabricated emails or contact names are included.
- Missing emails are replaced with official contact pages.
- Scores match the scoring rules.
- Status values are valid.
- Strong, medium, and human-review leads are separated.
- The report is written in Chinese.
- Company names, product names, URLs, and emails retain original language.

---

## 7. Output Requirements

The default final output must be a Chinese structured research report.

Do not only return raw JSON unless the user explicitly requests JSON.

Every included lead must have source evidence.

If no qualified leads are found, explain:

- What search angles were attempted.
- Why candidates were rejected or insufficient.
- What next search direction is recommended.

---

## 8. Standard Report Format

Use this format unless the user asks for a shorter output.

# 🔍 {Product / Market} 潜在渠道商搜索报告

**产品：** {product_name}  
**目标市场：** {target_country_or_region}  
**调研时间：** {date}  
**调研范围：** {search_scope_summary}  
**去重说明：** {dedup_summary}

---

## 一、市场背景与搜索口径

简要说明：

- 本次搜索围绕哪个国家 / 区域。
- 为什么该市场适合寻找骨科机器人 / TKA / 关节置换相关渠道。
- 本次重点筛选了哪些类型的公司。
- 共发现多少候选公司、保留多少家、强匹配多少家、中度匹配多少家、人工核验多少家。
- 如果公开信息不足，需要说明不足之处。

示例：

SkyWalker TKA 属于骨科机器人和全膝关节置换应用，适合优先寻找具备骨科植入物、关节置换产品、手术室设备、医院资本设备或医疗机器人渠道经验的经销商。本次围绕 {target_country_or_region} 市场进行公开信息检索，重点筛选具备医疗器械分销、骨科产品组合、医院客户网络或手术设备销售能力的公司。

---

## 二、第一梯队：强匹配渠道商

适用标准：

- 有较强官方证据。
- 明确从事医疗器械分销、进口、代理或渠道销售。
- 与骨科植入物、关节置换、手术设备、导航、机器人或 OR 资本设备高度相关。
- 有公开邮箱或官方联系页。
- 分数通常为 80–100。

### {index}. {company_name} {optional_tag}

| 字段 | 内容 |
| --- | --- |
| 国家/地区 | {country_or_city} |
| 官网 | {website} |
| 邮箱/联系页 | {email_or_contact_page} |
| 联系人/部门 | {contact_name_or_department} |
| 渠道类型 | {category} |
| 产品/业务匹配 | {portfolio_fit} |
| 证据等级 | {evidence_level} |
| 匹配度 | {score}/100 |
| 状态 | {status} |

**为什么匹配：**  
{match_reason}

**证据来源：**  
{source_url_or_source_note}

**备注：**  
{notes}

---

## 三、第二梯队：中度匹配渠道商

适用标准：

- 证据显示可能具备医疗器械、医院设备或手术设备渠道。
- 骨科 / 机器人 / 关节置换相关性可能是间接证据。
- 需要人工确认是否适合 BD 跟进。
- 分数通常为 60–79。

### {index}. {company_name} {optional_tag}

| 字段 | 内容 |
| --- | --- |
| 国家/地区 | {country_or_city} |
| 官网 | {website} |
| 邮箱/联系页 | {email_or_contact_page} |
| 联系人/部门 | {contact_name_or_department} |
| 渠道类型 | {category} |
| 产品/业务匹配 | {portfolio_fit} |
| 证据等级 | {evidence_level} |
| 匹配度 | {score}/100 |
| 状态 | {status} |

**为什么匹配：**  
{match_reason}

**证据来源：**  
{source_url_or_source_note}

**备注：**  
{notes}

---

## 四、第三梯队：值得跟进 / 需要人工核验

适用标准：

- 存在一定相关证据。
- 公开信息不完整。
- 可能是经销商、进口商、资本设备服务商或骨科相关公司。
- 需要人工确认。
- 分数通常为 40–59，或状态为 `human_review`。

### {index}. {company_name}

| 字段 | 内容 |
| --- | --- |
| 国家/地区 | {country_or_city} |
| 官网 | {website} |
| 邮箱/联系页 | {email_or_contact_page} |
| 联系人/部门 | {contact_name_or_department} |
| 渠道类型 | {category} |
| 产品/业务匹配 | {portfolio_fit} |
| 证据等级 | {evidence_level} |
| 匹配度 | {score}/100 |
| 状态 | human_review |

**为什么值得跟进：**  
{match_reason}

**证据来源：**  
{source_url_or_source_note}

**需要人工核验：**  
{verification_gap}

---

## 五、优先级排序

| 优先级 | 公司 | 国家/地区 | 推荐原因 | 邮箱/联系页 |
| --- | --- | --- | --- | --- |
| 🥇 | {company_name} | {country_or_city} | {brief_reason} | {email_or_contact_page} |
| 🥈 | {company_name} | {country_or_city} | {brief_reason} | {email_or_contact_page} |
| 🥉 | {company_name} | {country_or_city} | {brief_reason} | {email_or_contact_page} |
| 4 | {company_name} | {country_or_city} | {brief_reason} | {email_or_contact_page} |

Ranking rules:

1. Rank by score first.
2. If scores are similar, prioritize orthopedic implant / joint replacement / TKA evidence.
3. Then prioritize official company evidence.
4. Then prioritize visible email or official contact page.
5. Then prioritize target-market coverage.
6. Do not include rejected or duplicate leads.

---

## 六、需人工处理事项

Use concise bullets.

Examples:

- **{company_name}**：官网显示医疗设备业务，但未找到明确骨科或关节置换产品线，需要人工确认。
- **{company_name}**：只找到官方联系表单，未找到公开邮箱，需要人工决定是否纳入外联名单。
- **{company_name}**：可能涉及独家代理、监管注册或授权资质问题，需要业务负责人判断。
- **{company_name}**：疑似重复线索，需要与历史 lead database 再次核对。

---

## 七、结论与建议

Summarize:

- Most recommended companies.
- Which companies need manual verification before BD action.
- Main evidence gaps.
- Whether the current market deserves deeper search.
- Suggested next research directions, such as neighboring countries, exhibition lists, orthopedic congress exhibitor lists, medical device associations, importer databases, or regulatory directories.

Example:

本轮搜索中，{top_company_1}、{top_company_2} 和 {top_company_3} 的匹配度最高，建议优先进入人工核验。{review_company_1} 和 {review_company_2} 具备一定渠道相关性，但公开证据不足，建议由 BD 人员进一步确认其是否覆盖骨科植入物、关节置换或手术室资本设备渠道。下一步建议继续从骨科大会参展商名录、医疗器械进口商目录和周边国家渠道商名录扩展线索。

---

## 9. Compact Report Format

Use this format if the user asks for a shorter report.

# 🔍 {Product / Market} 潜在渠道商搜索报告

**产品：** {product_name}  
**目标市场：** {target_country_or_region}  
**调研时间：** {date}  
**去重说明：** {dedup_summary}

## 强匹配渠道商

| 公司 | 国家/地区 | 官网 | 邮箱/联系页 | 匹配原因 | 证据等级 | 分数 | 状态 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| {company_name} | {country} | {website} | {email_or_contact_page} | {brief_match_reason} | {evidence_level} | {score} | {status} |

## 中度匹配 / 待核验

| 公司 | 国家/地区 | 官网 | 邮箱/联系页 | 待核验点 | 证据等级 | 分数 | 状态 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| {company_name} | {country} | {website} | {email_or_contact_page} | {verification_gap} | {evidence_level} | {score} | human_review |

## 优先级建议

1. **{company_name}**：{reason}
2. **{company_name}**：{reason}
3. **{company_name}**：{reason}

## 人工核验事项

- {manual_review_item}
- {manual_review_item}

---

## 10. JSON Output Format

Only use this if the user explicitly requests JSON.

```json
{
  "product": "{product_name}",
  "target_market": "{target_country_or_region}",
  "research_date": "{date}",
  "dedup_summary": "{dedup_summary}",
  "leads": [
    {
      "company_name": "",
      "local_name": "",
      "region": "",
      "country": "",
      "city": "",
      "website": "",
      "contact_name": "",
      "email": "",
      "contact_page": "",
      "category": "",
      "portfolio_fit": "",
      "match_reason": "",
      "source": [
        {
          "url": "",
          "evidence_note": "",
          "evidence_level": "Level 1"
        }
      ],
      "score": 0,
      "status": "new",
      "notes": ""
    }
  ],
  "manual_review_items": [],
  "recommended_next_steps": []
}
```

---

## 11. Final Output Rules

The agent must follow these rules when generating the final answer:

1. Write the report in Chinese.
2. Keep company names, product names, URLs, and emails in their original language.
3. Include source evidence for every retained lead.
4. Do not fabricate missing emails, contacts, websites, or source evidence.
5. Use official contact pages when emails are unavailable.
6. Deduplicate before reporting.
7. Do not include duplicate companies.
8. Do not include hospital-only end users.
9. Do not include media, job boards, pure consultants, unrelated industrial robotics companies, consumer sellers, or unsupported companies.
10. Do not generate outreach email content.
11. Do not classify replies.
12. Do not include email send status.
13. Use only `new`, `qualified`, `human_review`, or `rejected` as status values.
14. Exclude rejected leads unless the user explicitly asks to see them.
15. Keep match reasons concise and evidence-based.
16. State evidence gaps clearly instead of guessing.
17. If no qualified leads are found, explain the searches performed and recommend next search directions.
18. If the target market is too broad, state that the result is a first-pass scan, not an exhaustive distributor database.
