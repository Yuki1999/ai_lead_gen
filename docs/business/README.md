# Skywalker 业务配置与邮件模板（客户批准版 V2.0 / 2026-06）

本目录是客户（微创畅行 / MEDBOT Skywalker）提供的业务输入，系统的邮件生成、回复转人工、线索筛选规则均以此为准。源文件保留原始 docx/xlsx，本文件是要点摘要，供团队与 Agent 快速参考。

## 源文件

| 文件 | 用途 |
| --- | --- |
| `邮件模板-V2.docx` | 批准版邮件模板（代理商 / KOL，中英文）、变量、角色判断、发送策略、人工审核触发词 |
| `Skywalker_Distributor_Selection_Criteria.docx` | 代理商筛选标准 |
| `Skywalker_KOL_Selection_Criteria.docx` | KOL 筛选标准 |
| `获客Agent_业务信息.xlsx` | 渠道开发信息表：目标市场、客户类型、关键词、匹配标准、排除项、评分权重、触达策略、人工审核项 |
| `KOL邮件样例-领导版.txt` | 领导手写的 16 封 KOL 个性化邮件样例（个性化引语的黄金标准） |

## 两类收件人与模板

系统按收件人角色（`lead_type`）选择模板，按目标市场选择语言（中文市场→中文，其余→英文）。

- **代理商 / 渠道商（distributor）**：商业合作、渠道网络、分销能力。主题 `Distribution Partnership Opportunity – MEDBOT NaviBot Skywalker for {市场}`。
- **KOL / 采购者（kol）**：临床价值、学术合作、技术创新、患者获益。主题 `Advancing Robotic Arthroplasty in {市场} – Introduction from MEDBOT Skywalker`。KOL 版会由 AI 写一段 `[Personalized Intro]`，引用该医生的公开成就（如「2019 非洲首例 Mako TKA」），数据来自线索的 `match_reason` / `notes`。

### 角色判断规则（邮件模板文档 4.1）

| | 判为代理商 | 判为 KOL/采购者 |
| --- | --- | --- |
| 职位关键词 | Distribution Manager, Channel Partner, BD Director, Reseller, Distributor | Chief Surgeon, Head of Orthopedics, Procurement Director, Professor, Dr. |
| 公司类型 | 器械贸易/代理/渠道公司 | 医院、骨科中心、手术中心、大学医学院 |

## 固定要素（所有模板）

- 4 条差异化卖点（自研机械臂、一体化截骨导块、开放平台、无需打开股骨髓腔）逐字保留。
- 统一署名：`Skywalker Sales Team, MEDBOT` / `Skywalker 销售组，MEDBOT`。
- 行动号召：**回复邮件，专人对接**（不主动要求安排通话）。
- 首封只发介绍，不承诺价格、注册证、独家、合同等。

## 人工审核触发词（回复命中即转人工，AI 不自动回复）

价格 / 报价 / 预算、独家代理 / 排他性、注册证 / 认证 / FDA / CE、招投标 / 招标、合同 / 协议 / 条款、付款 / 保证金、临床声明 / 适应症 / 疗效承诺、样机 / 试用 / 演示。

实现见 `backend/app/services.py` 的 `_HUMAN_REVIEW_TRIGGERS` 与 `analyze_reply` 的 AI 提示。

## 评分权重（业务信息表）

渠道匹配度 40% · 目标市场战略优先级 25% · 学术/品牌公开资历 20% · 联系方式可用性 10% · 公开 KOL/医院合作记录 5%（加分）。

## 排除对象（已放宽）

不发：终端医院（转当地经销商）、媒体、咨询公司、工业机器人公司（非医疗）、纯科研机构。
**变更：** 代理竞品（Mako / ROSA / Cori）者**不再一刀切排除**，改为个案评估、评分中酌情降级。

## AI 自动发送

后端设置 `auto_send_enabled`（默认 `false`）。
- `false`（默认）：Agent 生成的外联一律存草稿，需人工在前端逐封批准后发送。
- `true`：Agent 生成首封冷邮件后直接通过 Exchange 发出。回复仍按上方触发词转人工。

前端「设置 → 同步」页有开关。
