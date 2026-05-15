# Pi Agent Sidecar Design

## Goal

Embed a real Pi agent runtime into the existing Medbot overseas distributor web app. The agent should support project skills and default to `overseas-distributor-prospecting` so a user can ask natural-language business development questions such as "find SkyWalker TKA distributors in India" and have the app run the existing prospecting workflow.

## Current System

The project currently has three main pieces:

- `backend/`: FastAPI + SQLite API for product profile extraction, real prospect search, lead storage, outreach record generation, and reply analysis.
- `frontend/`: Vue + Vite operations dashboard.
- `skills/overseas-distributor-prospecting/`: Agent skill describing the overseas distributor prospecting workflow for Medbot, SkyWalker TKA, orthopedic surgical robotics, and medical device channel development.

The current app already has deterministic business functions. The new work should add an agent layer without replacing those functions.

## Chosen Approach

Add a Node/TypeScript Pi sidecar under `agent/`.

The sidecar will use the current Pi package scope:

- `@earendil-works/pi-coding-agent`
- `@earendil-works/pi-agent-core`
- `@earendil-works/pi-ai`
- `@earendil-works/pi-tui`

The older `@mariozechner/*` packages still exist on npm, but Pi documentation now points to `@earendil-works/*`. The implementation should lock the actual package versions in `agent/package-lock.json`.

## Architecture

Runtime services:

- FastAPI backend on `:8000`.
- Pi agent sidecar on `:8011`.
- Vue frontend on the Vite port.

Preferred request path:

```text
frontend -> FastAPI backend -> Pi agent sidecar -> FastAPI backend tools
```

The frontend should keep one configured API base URL. FastAPI will expose an `/agent/chat` proxy endpoint that forwards agent requests to the sidecar. This keeps browser CORS and deployment shape simple.

The sidecar will call existing FastAPI endpoints through custom Pi tools. It will not write directly to SQLite.

## Agent Session

The sidecar creates an agent session with `createAgentSession()`.

The resource loader must inject the project skill:

```text
skills/overseas-distributor-prospecting/SKILL.md
```

The sidecar should bias the system prompt toward this default behavior:

- Use `overseas-distributor-prospecting` unless the user asks for a different workflow.
- Do not invent companies, contacts, emails, websites, or evidence.
- Prefer official websites, regulatory directories, exhibitor lists, distributor pages, and hospital-equipment channel evidence.
- Use the registered business tools for product profile, search, lead listing, outreach records, and reply analysis.
- Escalate legal, exclusivity, pricing, regulatory ownership, tender, contract, liability, warranty, clinical-claim, and adverse-event issues to human review.

The first implementation can use one in-memory session per sidecar process. Persistent session trees can be added later if needed.

## Custom Tools

Register narrowly scoped Pi tools that call the backend API:

- `get_product_profile`: calls `GET /product/profile`.
- `search_leads`: calls `POST /leads/search`.
- `list_leads`: calls `GET /leads`.
- `create_outreach_records`: calls `POST /campaigns/outreach-records`.
- `analyze_reply`: calls `POST /replies/analyze`.

Tool inputs should mirror existing backend schemas where possible. Tool outputs should return backend JSON plus a concise text summary suitable for the agent transcript.

The agent must not get general-purpose database credentials or direct write access. Business state changes go through the existing FastAPI API.

## API Contract

Agent sidecar:

- `GET /health`
  - Returns `{ "status": "ok" }`.
- `POST /agent/chat`
  - Input: `{ "message": string, "session_id"?: string }`.
  - Output: `{ "message": string, "session_id": string, "events"?: object[] }`.

FastAPI proxy:

- `POST /agent/chat`
  - Accepts the same request shape.
  - Forwards to `AGENT_BASE_URL`.
  - Returns the sidecar response.
  - If the sidecar is unavailable, returns a clear `503` with a useful error message.

## Frontend

Add a compact Agent panel to the existing operations dashboard.

The panel should include:

- A default skill label: `overseas-distributor-prospecting`.
- A textarea or chat input for natural-language instructions.
- A submit button with loading state.
- A response area that displays the latest agent message.
- Error handling for missing API keys, sidecar downtime, and backend proxy failures.

Generated or updated leads should remain visible in the existing lead table after dashboard refresh. The first version does not need multi-turn transcript persistence in the browser.

## Configuration

Add `agent/.env.example`:

```env
OPENAI_API_KEY=
PI_MODEL=gpt-5-mini
BACKEND_BASE_URL=http://localhost:8000
AGENT_PORT=8011
```

Add backend configuration:

```env
AGENT_BASE_URL=http://localhost:8011
```

Update the root README with three-service startup instructions.

## Error Handling

The sidecar should report:

- Missing LLM credentials with a clear setup message.
- Backend connection failures with the backend URL.
- Tool validation errors with the tool name and input issue.
- Model/runtime errors without exposing secrets.

The FastAPI proxy should report:

- Agent sidecar unavailable as `503`.
- Agent timeout as `504`.
- Invalid agent response as `502`.

The frontend should show these errors in the existing dashboard style and should not blank the page.

## Testing

Backend tests:

- `/agent/chat` proxy forwards valid requests.
- Proxy returns `503` when the agent sidecar is unavailable.

Agent tests:

- `GET /health` returns ok.
- Skill path is configured and readable.
- Custom tools call a mock backend base URL.
- `/agent/chat` returns a structured setup error when credentials are missing.

Frontend verification:

- `npm run build`.
- Manual local check that the Agent panel can submit a prompt and display either an agent response or a clear setup error.

## Out of Scope

- Real SMTP sending.
- CRM sync.
- Browser automation.
- Persistent Pi session tree UI.
- User accounts and permission management.
- Replacing the existing FastAPI lead search logic.

## Rollout

1. Add the Node/TypeScript sidecar and package lock.
2. Add custom backend-calling Pi tools.
3. Load the default skill into Pi.
4. Add FastAPI proxy endpoint and tests.
5. Add the frontend Agent panel.
6. Update README and `.env.example`.
7. Run backend tests and frontend build.

## Local Constraints

This project directory is not currently a git repository, so the design document cannot be committed from this workspace. The spec review subagent step from the brainstorming workflow is also skipped because this environment only allows subagent spawning when the user explicitly requests delegated agent work.
