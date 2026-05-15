# Overseas Distributor Demo Design

## Goal

Build a local web demo for 微创畅行机器人海外业务 prospecting. The demo shows how an agent can collect distributor candidates, store them as structured leads, send outreach emails from the database, and classify replies for follow-up or human handoff.

## Scope

The demo is an MVP, not a production crawler or mail system. It uses deterministic sample data and rule-based classification so it can run locally without paid search APIs, SMTP credentials, or LLM keys. The implementation leaves clear extension points for real search APIs, CRM sync, SMTP providers, and LLM-based reply analysis.

## Architecture

- FastAPI backend under `backend/`.
- SQLite database for leads, outreach events, and reply analyses.
- Vue + Vite frontend under `frontend/`.
- A local Codex skill under `skills/overseas-distributor-prospecting/`.

## Backend

The backend exposes:

- `GET /health` for service checks.
- `POST /leads/search` to generate distributor leads from regions and product keywords.
- `GET /leads` to list and filter saved leads.
- `PATCH /leads/{lead_id}` to update status and notes.
- `POST /campaigns/send-demo` to render and record outreach emails.
- `POST /replies/analyze` to classify reply content and suggest the next action.

The backend uses small service functions for prospect scoring, email rendering, and reply classification. These functions are covered by unit tests before the API wiring is implemented.

## Data Model

Lead fields:

- `id`
- `company_name`
- `region`
- `country`
- `website`
- `contact_name`
- `email`
- `category`
- `match_reason`
- `source`
- `score`
- `status`
- `notes`
- `created_at`
- `updated_at`

Outreach event fields:

- `id`
- `lead_id`
- `subject`
- `body`
- `sent_to`
- `region`
- `status`
- `created_at`

Reply analysis fields:

- `id`
- `lead_id`
- `reply_text`
- `intent`
- `confidence`
- `summary`
- `next_action`
- `requires_human`
- `created_at`

## Frontend

The first screen is the operating demo itself, not a marketing page. It contains:

- Prospecting controls for target regions, product keywords, and result count.
- Lead database table with status, score, email, matching reason, and actions.
- Demo email panel showing region-aware outreach templates and send results.
- Reply analysis panel that classifies a pasted reply and recommends next steps.
- Compact summary metrics for total leads, interested leads, sent emails, and human handoff cases.

The visual style is a restrained operations dashboard: high contrast, predictable controls, dense tables, and no decorative hero section.

## Skill

The skill teaches an agent how to run overseas distributor prospecting for this business:

- Define target-market logic.
- Expand search terms and distributor categories.
- Capture required lead fields.
- Verify email/contact evidence.
- Generate region-aware outreach templates.
- Classify replies into next actions.
- Escalate ambiguous or complex conversations to a human.

## Testing

Backend tests cover:

- Lead scoring and candidate generation.
- Email template rendering by region.
- Reply intent classification.
- Core API flows with a temporary SQLite database.

Frontend verification covers:

- Type/build checks via `npm run build`.
- Manual local preview through the Vite dev server.

