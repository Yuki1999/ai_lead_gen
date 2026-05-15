---
name: overseas-distributor-prospecting
description: Use when conducting overseas distributor prospecting for Medbot, 微创畅行机器人, SkyWalker TKA, orthopedic surgical robotics, or similar medical device channel business.
---

# Overseas Distributor Prospecting

Use this skill for overseas business development workflows where the agent needs to find, qualify, contact, and triage medical device or surgical robotics distributors.

## Product Context

For this project, the root assets describe SkyWalker® Robotic Platform Total Knee Application:

- CT-based system for total knee arthroplasty (TKA).
- Patient-specific preoperative planning and intraoperative plan adjustment.
- Real-time gap balancing and intra-op data insights.
- Robotically located cutting planes and motion-follow cutting block capability.
- Compatible with Evolution® Medial-Pivot Knee implant workflows.

Prioritize prospects connected to orthopedic implants, joint replacement, knee arthroplasty, surgical robotics, OR capital equipment, or hospital robotics distribution.

## Operating Rules

- Do not invent companies, contacts, emails, websites, or evidence.
- Prefer official company websites, regulatory directories, exhibition exhibitor lists, distributor pages, and hospital-equipment channel evidence.
- Capture source URLs and matching evidence for every lead.
- If no public email is found, record the official contact page instead of fabricating an email.
- Treat email as business outreach: keep messages concise, include opt-out language when sending real email, and obey local anti-spam rules.
- Escalate legal, exclusivity, pricing commitment, regulatory ownership, tender, contract, or adverse-event topics to a human.

## Step 1: Build the Lead Database

Clarify the search target:

- Product: SkyWalker TKA orthopedic surgical robot, hospital robotics, orthopedic navigation, joint replacement, operating-room capital equipment.
- Target regions: country, region, language, regulatory market, or trade zone.
- Ideal channel: orthopedic implant distributor, joint replacement distributor, surgical equipment distributor, hospital capital equipment reseller, robotics integrator.
- Exclusions: hospitals as end users, media sites, pure consultants, unrelated industrial robotics companies.

Expand search terms:

- English: `orthopedic implant distributor`, `total knee arthroplasty distributor`, `joint replacement distributor`, `surgical robotics distributor`, `hospital capital equipment distributor`, `CT based orthopedic navigation distributor`.
- Add country and city terms.
- Add local-language equivalents when searching non-English markets.
- Add competitor/channel terms only when relevant: orthopedic robotics, knee implants, arthroplasty, navigation, surgical systems, medtech distributor.

Capture fields:

| Field | Requirement |
| --- | --- |
| `company_name` | Legal or trading name |
| `region` | Sales region such as Europe, Middle East, Southeast Asia |
| `country` | Country or primary market |
| `website` | Official website URL |
| `contact_name` | Named owner if available; otherwise department |
| `email` | Public business email; prioritize sales, BD, distributor, info |
| `category` | Distributor/channel type |
| `match_reason` | Why this lead is relevant |
| `source` | URL or source note |
| `score` | 0-100 fit score |
| `status` | `new`, `emailed`, `interested`, `human_review`, `qualified`, `rejected` |
| `notes` | Evidence gaps, verification notes, owner assignment |

Score leads:

- +25 official site confirms medical device distribution.
- +20 orthopedic implants, joint replacement, knee arthroplasty, OR, robotics, or capital-equipment fit.
- +15 visible business email or contact form.
- +15 country coverage matches target.
- +10 named business development, sales, or distributor contact.
- -20 no source evidence.
- -30 unrelated robotics, consumer product, hospital-only, or media entity.

## Step 2: Send Outreach

Select email owner by region:

- Southeast Asia: regional BD or APAC owner.
- Middle East: GCC/MENA owner.
- Europe: EU/CE/regulatory-aware owner.
- Latin America: LatAm channel owner.
- Unknown: overseas BD mailbox.

First-touch email structure:

1. Short greeting with company/contact name.
2. One sentence explaining why the recipient matched the distributor profile.
3. One sentence introducing the product category.
4. Ask whether they handle orthopedic implants, joint replacement, hospital robotics, or operating-room capital equipment channels.
5. Offer an introductory product brief and qualification call.
6. Keep attachments out of the first email unless the user explicitly asks to send them.

Example:

```text
Subject: {region} partnership discussion for SkyWalker TKA robotics

Hi {contact_name},

I am reaching out because {company_name} appears active in {country}'s {category} channel. We are mapping overseas partners for the SkyWalker Robotic Platform Total Knee Application, a CT-based orthopedic robotics system for TKA workflows, patient-specific planning, intra-op adjustment, and robotically located cutting planes.

If relevant, we can share an introductory product brief, product video, regulatory status overview, and a short partner qualification form.

Best regards,
{sender_name}
```

## Step 3: Analyze Replies

Classify replies:

- `interested`: asks for product details, catalog, pricing range, certificates, call, meeting, distribution requirements.
- `needs_review`: ambiguous, asks who the sender is, asks for clarification, or contains weak interest.
- `rejected`: not interested, unsubscribe, remove us, no fit.
- `complex`: exclusivity, tender commitment, regulatory registration ownership, legal contract, liability, payment terms, warranty commitment, clinical claims, or adverse-event content.

Next actions:

- `interested`: send preliminary product brief and request a qualification call.
- `needs_review`: ask one clarifying question or route to owner.
- `rejected`: mark do-not-contact and stop the sequence.
- `complex`: route to human business owner before answering.

## Output Format

When asked to return leads, use a structured table or JSON with the captured fields. When asked to send email, show the selected recipients, subject, body, and send status. When asked to triage replies, return intent, confidence, summary, next action, and whether human handoff is required.
