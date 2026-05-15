# Pi Agent Sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real Pi agent sidecar to the Medbot web app, with `overseas-distributor-prospecting` loaded as the default skill and available from the existing Vue dashboard.

**Architecture:** Keep FastAPI as the business API and SQLite owner. Add a Node/TypeScript sidecar under `agent/` that creates Pi agent sessions, registers narrow backend-calling tools, and exposes `/agent/chat`. FastAPI proxies browser requests to the sidecar so the frontend keeps one API base URL.

**Tech Stack:** FastAPI, SQLite, Vue 3, Vite, TypeScript, Node HTTP server, `@earendil-works/pi-coding-agent`, `@earendil-works/pi-ai`, `typebox`, Node built-in test runner.

---

## File Structure

- Create `agent/package.json`: Node sidecar scripts and dependencies.
- Create `agent/tsconfig.json`: TypeScript build settings.
- Create `agent/.env.example`: sidecar runtime configuration.
- Create `agent/src/config.ts`: environment parsing, project paths, skill path validation.
- Create `agent/src/backendClient.ts`: typed wrapper around existing FastAPI endpoints.
- Create `agent/src/tools.ts`: Pi custom tools that call `backendClient`.
- Create `agent/src/piSession.ts`: Pi `createAgentSession()` setup, skill injection, system prompt override, and prompt execution.
- Create `agent/src/server.ts`: HTTP routes for `GET /health` and `POST /agent/chat`.
- Create `agent/src/index.ts`: sidecar entrypoint.
- Create `agent/tests/*.test.ts`: sidecar health, config, backend client, and missing-credential chat tests.
- Modify `backend/app/schemas.py`: add agent request/response schemas.
- Create `backend/app/agent_proxy.py`: FastAPI-to-sidecar proxy and error mapping.
- Modify `backend/app/main.py`: expose `POST /agent/chat`.
- Modify `backend/tests/test_api.py`: add proxy success and sidecar-unavailable tests.
- Modify `frontend/src/App.vue`: add Agent panel state, request handler, icons, and markup.
- Modify `frontend/src/styles.css`: style Agent panel using existing dashboard language.
- Modify `.env.example`: add `AGENT_BASE_URL`.
- Modify `README.md`: add sidecar setup and three-service run instructions.

## Task 1: Add FastAPI Agent Proxy Contract

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/agent_proxy.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing backend proxy tests**

Append to `backend/tests/test_api.py`:

```python
def test_agent_chat_proxy_forwards_to_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module

    def fake_forward_agent_chat(payload):
        assert payload["message"] == "Find India SkyWalker TKA distributors"
        assert payload["session_id"] is None
        return {
            "message": "Found 3 candidate distributors.",
            "session_id": "test-session",
            "events": [{"type": "tool", "name": "search_leads"}],
        }

    monkeypatch.setattr(main_module, "forward_agent_chat", fake_forward_agent_chat, raising=False)

    with TestClient(main_module.create_app()) as client:
        response = client.post(
            "/agent/chat",
            json={"message": "Find India SkyWalker TKA distributors"},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Found 3 candidate distributors."
    assert response.json()["session_id"] == "test-session"
    assert response.json()["events"][0]["name"] == "search_leads"


def test_agent_chat_proxy_reports_sidecar_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.agent_proxy import AgentProxyError

    def fake_forward_agent_chat(payload):
        raise AgentProxyError(status_code=503, detail="Agent sidecar unavailable at http://localhost:8011")

    monkeypatch.setattr(main_module, "forward_agent_chat", fake_forward_agent_chat, raising=False)

    with TestClient(main_module.create_app()) as client:
        response = client.post("/agent/chat", json={"message": "hello"})

    assert response.status_code == 503
    assert "Agent sidecar unavailable" in response.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
uv run pytest tests/test_api.py::test_agent_chat_proxy_forwards_to_sidecar tests/test_api.py::test_agent_chat_proxy_reports_sidecar_unavailable -v
```

Expected: FAIL because `/agent/chat` and `app.agent_proxy` do not exist.

- [ ] **Step 3: Add schemas**

Add to `backend/app/schemas.py`:

```python
class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str | None = Field(default=None, max_length=160)


class AgentChatResponse(BaseModel):
    message: str
    session_id: str
    events: list[dict[str, object]] = Field(default_factory=list)
```

- [ ] **Step 4: Add proxy module**

Create `backend/app/agent_proxy.py`:

```python
from __future__ import annotations

import os
from typing import Any

import requests


class AgentProxyError(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def get_agent_base_url() -> str:
    return os.getenv("AGENT_BASE_URL", "http://localhost:8011").rstrip("/")


def forward_agent_chat(
    payload: dict[str, Any],
    *,
    http: Any = requests,
    timeout: float = 90.0,
) -> dict[str, Any]:
    url = f"{get_agent_base_url()}/agent/chat"
    try:
        response = http.post(url, json=payload, timeout=timeout)
    except requests.Timeout as exc:
        raise AgentProxyError(status_code=504, detail=f"Agent sidecar timed out at {url}") from exc
    except requests.RequestException as exc:
        raise AgentProxyError(status_code=503, detail=f"Agent sidecar unavailable at {url}") from exc

    if response.status_code >= 500:
        raise AgentProxyError(status_code=502, detail=f"Agent sidecar failed with {response.status_code}")
    if response.status_code >= 400:
        raise AgentProxyError(status_code=response.status_code, detail=response.text)

    try:
        data = response.json()
    except ValueError as exc:
        raise AgentProxyError(status_code=502, detail="Agent sidecar returned invalid JSON") from exc

    if not isinstance(data, dict) or "message" not in data or "session_id" not in data:
        raise AgentProxyError(status_code=502, detail="Agent sidecar returned an invalid chat payload")
    data.setdefault("events", [])
    return data
```

- [ ] **Step 5: Wire FastAPI endpoint**

Modify imports in `backend/app/main.py`:

```python
from app.agent_proxy import AgentProxyError, forward_agent_chat
```

Import schemas:

```python
AgentChatRequest,
AgentChatResponse,
```

Add inside `create_app()`:

```python
    @app.post("/agent/chat", response_model=AgentChatResponse)
    def agent_chat(request: AgentChatRequest) -> dict[str, object]:
        try:
            return forward_agent_chat(request.model_dump())
        except AgentProxyError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
```

- [ ] **Step 6: Run backend proxy tests**

Run:

```bash
cd backend
uv run pytest tests/test_api.py::test_agent_chat_proxy_forwards_to_sidecar tests/test_api.py::test_agent_chat_proxy_reports_sidecar_unavailable -v
```

Expected: PASS.

- [ ] **Step 7: Git checkpoint**

Current workspace has no `.git`, so skip. If later inside a git repo:

```bash
git add backend/app/schemas.py backend/app/agent_proxy.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat: add agent sidecar proxy"
```

## Task 2: Scaffold the Pi Sidecar

**Files:**
- Create: `agent/package.json`
- Create: `agent/tsconfig.json`
- Create: `agent/.env.example`
- Create: `agent/src/config.ts`
- Create: `agent/src/server.ts`
- Create: `agent/src/index.ts`
- Test: `agent/tests/config.test.ts`
- Test: `agent/tests/server.test.ts`

- [ ] **Step 1: Create package files**

Create `agent/package.json`:

```json
{
  "name": "medbot-pi-agent-sidecar",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc -p tsconfig.json",
    "start": "node dist/index.js",
    "test": "node --import tsx --test tests/*.test.ts"
  },
  "dependencies": {
    "@earendil-works/pi-ai": "^0.74.0",
    "@earendil-works/pi-coding-agent": "^0.74.0",
    "typebox": "^1.1.24"
  },
  "devDependencies": {
    "@types/node": "^24.10.0",
    "tsx": "^4.21.0",
    "typescript": "^5.7.3"
  }
}
```

Create `agent/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": ".",
    "types": ["node"]
  },
  "include": ["src/**/*.ts", "tests/**/*.ts"]
}
```

Create `agent/.env.example`:

```env
OPENAI_API_KEY=
PI_MODEL=gpt-5-mini
BACKEND_BASE_URL=http://localhost:8000
AGENT_PORT=8011
```

- [ ] **Step 2: Install dependencies**

Run:

```bash
cd agent
npm install
```

Expected: creates `agent/package-lock.json`.

- [ ] **Step 3: Write failing config and health tests**

Create `agent/tests/config.test.ts`:

```typescript
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { loadConfig } from "../src/config.ts";

describe("loadConfig", () => {
  it("resolves the project skill path", () => {
    const config = loadConfig({ env: {}, cwd: process.cwd() });

    assert.equal(config.port, 8011);
    assert.equal(config.skillName, "overseas-distributor-prospecting");
    assert.match(config.skillPath, /skills\/overseas-distributor-prospecting\/SKILL\.md$/);
  });
});
```

Create `agent/tests/server.test.ts`:

```typescript
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createServer } from "../src/server.ts";

async function request(server: ReturnType<typeof createServer>, path: string, init: RequestInit = {}) {
  const listener = server.listen(0);
  await new Promise<void>((resolve) => listener.once("listening", resolve));
  const address = listener.address();
  assert.equal(typeof address, "object");
  assert.ok(address);
  try {
    return await fetch(`http://127.0.0.1:${address.port}${path}`, init);
  } finally {
    await new Promise<void>((resolve) => listener.close(() => resolve()));
  }
}

describe("agent server", () => {
  it("serves health checks", async () => {
    const response = await request(createServer(), "/health");

    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { status: "ok" });
  });

  it("returns setup guidance when no model credentials are configured", async () => {
    const response = await request(createServer({ env: {} }), "/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Find India distributors" }),
    });

    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.session_id, "default");
    assert.match(payload.message, /OPENAI_API_KEY/);
    assert.equal(payload.events[0].type, "setup_error");
  });
});
```

- [ ] **Step 4: Run tests to verify they fail**

Run:

```bash
cd agent
npm test
```

Expected: FAIL because `src/config.ts` and `src/server.ts` do not exist.

- [ ] **Step 5: Implement config**

Create `agent/src/config.ts`:

```typescript
import { existsSync } from "node:fs";
import { resolve } from "node:path";

export interface AgentConfig {
  port: number;
  backendBaseUrl: string;
  modelName: string;
  skillName: string;
  skillPath: string;
  skillBaseDir: string;
  hasModelCredentials: boolean;
}

interface LoadConfigOptions {
  env?: NodeJS.ProcessEnv;
  cwd?: string;
}

export function loadConfig(options: LoadConfigOptions = {}): AgentConfig {
  const env = options.env ?? process.env;
  const projectRoot = resolve(options.cwd ?? process.cwd(), "..");
  const skillBaseDir = resolve(projectRoot, "skills", "overseas-distributor-prospecting");
  const skillPath = resolve(skillBaseDir, "SKILL.md");

  return {
    port: parsePort(env.AGENT_PORT),
    backendBaseUrl: (env.BACKEND_BASE_URL || "http://localhost:8000").replace(/\/$/, ""),
    modelName: env.PI_MODEL || "gpt-5-mini",
    skillName: "overseas-distributor-prospecting",
    skillPath,
    skillBaseDir,
    hasModelCredentials: Boolean(env.OPENAI_API_KEY),
  };
}

export function assertSkillExists(config: AgentConfig): void {
  if (!existsSync(config.skillPath)) {
    throw new Error(`Default skill not found at ${config.skillPath}`);
  }
}

function parsePort(value: string | undefined): number {
  const parsed = Number(value || "8011");
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 8011;
}
```

- [ ] **Step 6: Implement minimal server**

Create `agent/src/server.ts`:

```typescript
import { createServer as createHttpServer, type IncomingMessage, type ServerResponse } from "node:http";
import { randomUUID } from "node:crypto";

import { assertSkillExists, loadConfig, type AgentConfig } from "./config.js";

interface CreateServerOptions {
  env?: NodeJS.ProcessEnv;
  runChat?: (message: string, sessionId: string, config: AgentConfig) => Promise<{ message: string; events: object[] }>;
}

export function createServer(options: CreateServerOptions = {}) {
  const config = loadConfig({ env: options.env, cwd: process.cwd() });

  return createHttpServer(async (request, response) => {
    try {
      if (request.method === "GET" && request.url === "/health") {
        sendJson(response, 200, { status: "ok" });
        return;
      }

      if (request.method === "POST" && request.url === "/agent/chat") {
        const body = await readJson(request);
        const message = typeof body.message === "string" ? body.message.trim() : "";
        const sessionId = typeof body.session_id === "string" && body.session_id ? body.session_id : "default";

        if (!message) {
          sendJson(response, 400, { detail: "message is required" });
          return;
        }

        assertSkillExists(config);

        if (!config.hasModelCredentials) {
          sendJson(response, 200, {
            message: "Pi agent is not configured. Set OPENAI_API_KEY in agent/.env or the sidecar environment, then restart the agent service.",
            session_id: sessionId,
            events: [{ type: "setup_error", missing: "OPENAI_API_KEY" }],
          });
          return;
        }

        const runner = options.runChat ?? defaultMissingRunner;
        const result = await runner(message, sessionId, config);
        sendJson(response, 200, {
          message: result.message,
          session_id: sessionId || randomUUID(),
          events: result.events,
        });
        return;
      }

      sendJson(response, 404, { detail: "Not found" });
    } catch (error) {
      sendJson(response, 500, {
        detail: error instanceof Error ? error.message : "Agent sidecar failed",
      });
    }
  });
}

async function defaultMissingRunner(): Promise<{ message: string; events: object[] }> {
  throw new Error("Pi chat runner has not been initialized");
}

async function readJson(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  if (chunks.length === 0) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>;
}

function sendJson(response: ServerResponse, statusCode: number, payload: object): void {
  response.writeHead(statusCode, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
  });
  response.end(JSON.stringify(payload));
}
```

Create `agent/src/index.ts`:

```typescript
import { createServer } from "./server.js";
import { loadConfig } from "./config.js";

const config = loadConfig();
const server = createServer();

server.listen(config.port, () => {
  console.log(`Medbot Pi agent sidecar listening on http://localhost:${config.port}`);
});
```

- [ ] **Step 7: Run tests and build**

Run:

```bash
cd agent
npm test
npm run build
```

Expected: PASS.

- [ ] **Step 8: Git checkpoint**

Current workspace has no `.git`, so skip. If later inside a git repo:

```bash
git add agent/package.json agent/package-lock.json agent/tsconfig.json agent/.env.example agent/src agent/tests
git commit -m "feat: scaffold pi agent sidecar"
```

## Task 3: Add Backend Client and Pi Tools

**Files:**
- Create: `agent/src/backendClient.ts`
- Create: `agent/src/tools.ts`
- Modify: `agent/src/server.ts`
- Test: `agent/tests/backendClient.test.ts`
- Test: `agent/tests/tools.test.ts`

- [ ] **Step 1: Write failing backend client test**

Create `agent/tests/backendClient.test.ts` with a local Node HTTP server that verifies paths and payloads:

```typescript
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { describe, it } from "node:test";

import { BackendClient } from "../src/backendClient.ts";

async function withMockBackend(handler: Parameters<typeof createServer>[0]) {
  const server = createServer(handler);
  server.listen(0);
  await new Promise<void>((resolve) => server.once("listening", resolve));
  const address = server.address();
  assert.equal(typeof address, "object");
  assert.ok(address);
  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

describe("BackendClient", () => {
  it("calls product profile and lead search endpoints", async () => {
    const backend = await withMockBackend((request, response) => {
      response.setHeader("Content-Type", "application/json");
      if (request.method === "GET" && request.url === "/product/profile") {
        response.end(JSON.stringify({ product_name: "SkyWalker", search_keywords: [] }));
        return;
      }
      if (request.method === "POST" && request.url === "/leads/search") {
        response.statusCode = 201;
        response.end(JSON.stringify({ created_count: 1, leads: [{ company_name: "Demo Ortho" }] }));
        return;
      }
      response.statusCode = 404;
      response.end(JSON.stringify({ detail: "not found" }));
    });

    try {
      const client = new BackendClient(backend.baseUrl);
      assert.equal((await client.getProductProfile()).product_name, "SkyWalker");
      assert.equal(
        (await client.searchLeads({ target_regions: ["India"], product_keywords: [], max_results: 1, real_search: true, require_email: true })).created_count,
        1,
      );
    } finally {
      await backend.close();
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd agent
npm test
```

Expected: FAIL because `backendClient.ts` does not exist.

- [ ] **Step 3: Implement backend client**

Create `agent/src/backendClient.ts`:

```typescript
export interface SearchLeadsInput {
  target_regions: string[];
  product_keywords?: string[];
  max_results?: number;
  real_search?: boolean;
  require_email?: boolean;
}

export class BackendClient {
  constructor(private readonly baseUrl: string) {}

  getProductProfile(): Promise<Record<string, unknown>> {
    return this.request("/product/profile");
  }

  searchLeads(input: SearchLeadsInput): Promise<Record<string, unknown>> {
    return this.request("/leads/search", {
      method: "POST",
      body: JSON.stringify({
        product_keywords: [],
        max_results: 8,
        real_search: true,
        require_email: true,
        ...input,
      }),
    });
  }

  listLeads(params: { region?: string; status?: string; q?: string } = {}): Promise<Record<string, unknown>> {
    const query = new URLSearchParams();
    if (params.region) query.set("region", params.region);
    if (params.status) query.set("status", params.status);
    if (params.q) query.set("q", params.q);
    return this.request(`/leads?${query.toString()}`);
  }

  createOutreachRecords(input: { lead_ids: number[] }): Promise<Record<string, unknown>> {
    return this.request("/campaigns/outreach-records", {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  analyzeReply(input: { reply_text: string; lead_id?: number | null }): Promise<Record<string, unknown>> {
    return this.request("/replies/analyze", {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  private async request(path: string, init: RequestInit = {}): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers || {}),
      },
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`Backend ${response.status} for ${path}: ${text}`);
    }
    return text ? (JSON.parse(text) as Record<string, unknown>) : {};
  }
}
```

- [ ] **Step 4: Write Pi tool tests**

Create `agent/tests/tools.test.ts`:

```typescript
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createBusinessTools } from "../src/tools.ts";

describe("createBusinessTools", () => {
  it("creates named Medbot business tools", () => {
    const tools = createBusinessTools({
      getProductProfile: async () => ({}),
      searchLeads: async () => ({ created_count: 0, leads: [] }),
      listLeads: async () => ({ total: 0, leads: [] }),
      createOutreachRecords: async () => ({ sent_count: 0, events: [] }),
      analyzeReply: async () => ({ intent: "needs_review" }),
    });

    assert.deepEqual(
      tools.map((tool) => tool.name),
      ["get_product_profile", "search_leads", "list_leads", "create_outreach_records", "analyze_reply"],
    );
  });
});
```

- [ ] **Step 5: Implement tools**

Create `agent/src/tools.ts` using `defineTool` and `Type`:

```typescript
import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

import type { BackendClient } from "./backendClient.js";

export function createBusinessTools(client: Pick<BackendClient, "getProductProfile" | "searchLeads" | "listLeads" | "createOutreachRecords" | "analyzeReply">) {
  return [
    defineTool({
      name: "get_product_profile",
      label: "Get product profile",
      description: "Fetch the SkyWalker TKA product profile and search positioning from the Medbot backend.",
      parameters: Type.Object({}),
      execute: async () => toolResult(await client.getProductProfile()),
    }),
    defineTool({
      name: "search_leads",
      label: "Search distributor leads",
      description: "Search and persist overseas distributor leads through the Medbot backend.",
      parameters: Type.Object({
        target_regions: Type.Array(Type.String()),
        product_keywords: Type.Optional(Type.Array(Type.String())),
        max_results: Type.Optional(Type.Number()),
        real_search: Type.Optional(Type.Boolean()),
        require_email: Type.Optional(Type.Boolean()),
      }),
      execute: async (_toolCallId, params) => toolResult(await client.searchLeads(params)),
    }),
    defineTool({
      name: "list_leads",
      label: "List leads",
      description: "List saved distributor leads from the Medbot backend.",
      parameters: Type.Object({
        region: Type.Optional(Type.String()),
        status: Type.Optional(Type.String()),
        q: Type.Optional(Type.String()),
      }),
      execute: async (_toolCallId, params) => toolResult(await client.listLeads(params)),
    }),
    defineTool({
      name: "create_outreach_records",
      label: "Create outreach records",
      description: "Render and record outreach email drafts for saved lead IDs.",
      parameters: Type.Object({
        lead_ids: Type.Array(Type.Number()),
      }),
      execute: async (_toolCallId, params) => toolResult(await client.createOutreachRecords(params)),
    }),
    defineTool({
      name: "analyze_reply",
      label: "Analyze reply",
      description: "Classify a distributor reply and update lead status when a lead ID is provided.",
      parameters: Type.Object({
        reply_text: Type.String(),
        lead_id: Type.Optional(Type.Union([Type.Number(), Type.Null()])),
      }),
      execute: async (_toolCallId, params) => toolResult(await client.analyzeReply(params)),
    }),
  ];
}

function toolResult(payload: Record<string, unknown>) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}
```

- [ ] **Step 6: Run sidecar tests and build**

Run:

```bash
cd agent
npm test
npm run build
```

Expected: PASS.

- [ ] **Step 7: Git checkpoint**

Current workspace has no `.git`, so skip. If later inside a git repo:

```bash
git add agent/src/backendClient.ts agent/src/tools.ts agent/tests
git commit -m "feat: add medbot agent tools"
```

## Task 4: Create Real Pi Chat Runner

**Files:**
- Create: `agent/src/piSession.ts`
- Modify: `agent/src/server.ts`
- Modify: `agent/src/index.ts`
- Test: `agent/tests/config.test.ts`
- Manual verify: `agent` sidecar startup with missing and present credentials

- [ ] **Step 1: Add skill validation test**

Extend `agent/tests/config.test.ts`:

```typescript
import { readFileSync } from "node:fs";

it("points to the overseas distributor prospecting skill", () => {
  const config = loadConfig({ env: {}, cwd: process.cwd() });
  const skill = readFileSync(config.skillPath, "utf8");

  assert.match(skill, /name:\s*overseas-distributor-prospecting/);
  assert.match(skill, /SkyWalker TKA/);
});
```

- [ ] **Step 2: Implement Pi session runner**

Create `agent/src/piSession.ts`.

Use the SDK imports documented by Pi:

```typescript
import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
  type Skill,
} from "@earendil-works/pi-coding-agent";
```

Implement:

```typescript
import { BackendClient } from "./backendClient.js";
import type { AgentConfig } from "./config.js";
import { createBusinessTools } from "./tools.js";

const DEFAULT_SYSTEM_PROMPT = `
You are the Medbot overseas distributor prospecting agent.
Default to the overseas-distributor-prospecting skill unless the user explicitly asks for another workflow.
Do not invent companies, contacts, emails, websites, or evidence.
Use official websites, regulatory directories, exhibitor lists, distributor pages, and hospital-equipment channel evidence.
Use the registered tools for product profile lookup, lead search, lead listing, outreach records, and reply analysis.
Escalate exclusivity, pricing, regulatory ownership, tender, contract, liability, warranty, clinical-claim, and adverse-event topics to human review.
`;

export async function runPiChat(
  message: string,
  _sessionId: string,
  config: AgentConfig,
): Promise<{ message: string; events: object[] }> {
  const skill: Skill = {
    name: config.skillName,
    description: "Overseas distributor prospecting for Medbot, SkyWalker TKA, orthopedic surgical robotics, and medical device channels.",
    filePath: config.skillPath,
    baseDir: config.skillBaseDir,
    source: "custom",
  };

  const loader = new DefaultResourceLoader({
    cwd: process.cwd(),
    systemPromptOverride: () => DEFAULT_SYSTEM_PROMPT,
    skillsOverride: (current) => ({
      skills: [...current.skills, skill],
      diagnostics: current.diagnostics,
    }),
  });
  await loader.reload();

  const backend = new BackendClient(config.backendBaseUrl);
  const customTools = createBusinessTools(backend);
  const { session } = await createAgentSession({
    resourceLoader: loader,
    sessionManager: SessionManager.inMemory(process.cwd()),
    customTools,
    tools: customTools.map((tool) => tool.name),
  });

  const chunks: string[] = [];
  const events: object[] = [];
  session.subscribe((event) => {
    events.push(summarizeEvent(event));
    if (event.type === "message_update" && event.assistantMessageEvent?.type === "text_delta") {
      chunks.push(event.assistantMessageEvent.delta);
    }
  });

  await session.prompt(`/skill:${config.skillName}\n\n${message}`);
  return {
    message: chunks.join("").trim() || "Agent completed without a text response.",
    events: events.slice(-50),
  };
}

function summarizeEvent(event: unknown): object {
  if (typeof event === "object" && event !== null && "type" in event) {
    const typed = event as { type: string };
    return { type: typed.type };
  }
  return { type: "unknown" };
}
```

If TypeScript reports SDK type drift, inspect `agent/node_modules/@earendil-works/pi-coding-agent/dist/index.d.ts` and adjust imports only enough to match the installed `0.74.x` API.

- [ ] **Step 3: Wire runner into server entrypoint**

Modify `agent/src/index.ts`:

```typescript
import { createServer } from "./server.js";
import { loadConfig } from "./config.js";
import { runPiChat } from "./piSession.js";

const config = loadConfig();
const server = createServer({ runChat: runPiChat });

server.listen(config.port, () => {
  console.log(`Medbot Pi agent sidecar listening on http://localhost:${config.port}`);
});
```

- [ ] **Step 4: Run sidecar tests and build**

Run:

```bash
cd agent
npm test
npm run build
```

Expected: PASS. If build fails on Pi SDK type details, fix by reading installed `.d.ts` files rather than guessing.

- [ ] **Step 5: Manual sidecar check without credentials**

Run:

```bash
cd agent
npm run dev
```

In another terminal:

```bash
curl -s http://localhost:8011/health
curl -s -X POST http://localhost:8011/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"帮我找印度 SkyWalker TKA 渠道商"}'
```

Expected: `/health` returns ok; `/agent/chat` returns setup guidance mentioning `OPENAI_API_KEY`.

- [ ] **Step 6: Git checkpoint**

Current workspace has no `.git`, so skip. If later inside a git repo:

```bash
git add agent/src/piSession.ts agent/src/server.ts agent/src/index.ts agent/tests
git commit -m "feat: run pi agent chat sessions"
```

## Task 5: Add Frontend Agent Panel

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add TypeScript state and API handler**

Modify `frontend/src/App.vue`:

Add icons:

```typescript
Bot,
Send,
```

Add interface:

```typescript
interface AgentChatResponse {
  message: string;
  session_id: string;
  events: Array<Record<string, unknown>>;
}
```

Add refs:

```typescript
const agentPrompt = ref("帮我找印度 SkyWalker TKA 渠道商，输出候选清单、评分和下一步建议。");
const agentResponse = ref<AgentChatResponse | null>(null);
const agentSessionId = ref("");
```

Add handler:

```typescript
async function sendAgentPrompt(): Promise<void> {
  if (!agentPrompt.value.trim()) return;

  await runAction(async () => {
    const payload = await request<AgentChatResponse>("/agent/chat", {
      method: "POST",
      body: JSON.stringify({
        message: agentPrompt.value,
        session_id: agentSessionId.value || null,
      }),
    });
    agentResponse.value = payload;
    agentSessionId.value = payload.session_id;
    notice.value = "Agent 已完成处理";
    await loadDashboard();
  });
}
```

- [ ] **Step 2: Add sidebar navigation link**

Add in `.side-nav`:

```vue
<a href="#agent-title">Agent</a>
```

- [ ] **Step 3: Add Agent panel markup**

Place this inside `<section class="content-area">`, after `pipeline-strip` and before `toolbar`:

```vue
<section class="agent-panel" aria-labelledby="agent-title">
  <div class="section-title step-title">
    <span class="step-index">AI</span>
    <div>
      <h2 id="agent-title">Pi Agent</h2>
      <p>默认使用 overseas-distributor-prospecting skill 执行渠道拓展任务</p>
    </div>
  </div>

  <div class="agent-skill-row">
    <span>
      <Bot :size="16" aria-hidden="true" />
      overseas-distributor-prospecting
    </span>
    <small v-if="agentSessionId">Session {{ agentSessionId }}</small>
  </div>

  <label class="field agent-prompt">
    <span>Agent 指令</span>
    <textarea v-model="agentPrompt" rows="4" />
  </label>

  <button class="primary-button agent-submit" type="button" :disabled="loading || !agentPrompt.trim()" @click="sendAgentPrompt">
    <LoaderCircle v-if="loading" class="spin" :size="18" aria-hidden="true" />
    <Send v-else :size="18" aria-hidden="true" />
    {{ loading ? "Agent 处理中..." : "运行 Agent" }}
  </button>

  <article v-if="agentResponse" class="agent-response" aria-live="polite">
    <strong>Agent 输出</strong>
    <p>{{ agentResponse.message }}</p>
    <small>{{ agentResponse.events.length }} 个运行事件</small>
  </article>
</section>
```

- [ ] **Step 4: Add CSS**

Append focused styles to `frontend/src/styles.css`:

```css
.agent-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 16px;
}

.agent-skill-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.agent-skill-row span {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid #bcdad4;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary-strong);
  padding: 6px 10px;
  font-size: 13px;
  font-weight: 900;
}

.agent-skill-row small {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

.agent-prompt textarea {
  min-height: 108px;
}

.agent-submit {
  max-width: 220px;
}

.agent-response {
  margin-top: 14px;
  border: 1px solid #cfe0de;
  border-radius: 8px;
  background: var(--surface-subtle);
  padding: 14px;
}

.agent-response strong,
.agent-response small {
  display: block;
}

.agent-response p {
  margin: 10px 0;
  white-space: pre-line;
  color: #344151;
  line-height: 1.55;
}
```

If mobile layout needs adjustment, add this to the existing responsive section rather than creating a separate design language.

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 6: Git checkpoint**

Current workspace has no `.git`, so skip. If later inside a git repo:

```bash
git add frontend/src/App.vue frontend/src/styles.css
git commit -m "feat: add pi agent panel"
```

## Task 6: Update Docs and Root Environment Example

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update `.env.example`**

Add:

```env
# Agent sidecar
AGENT_BASE_URL=http://localhost:8011
BACKEND_BASE_URL=http://localhost:8000
AGENT_PORT=8011
PI_MODEL=gpt-5-mini
OPENAI_API_KEY=
```

- [ ] **Step 2: Update README structure section**

Add:

```markdown
- `agent/`: Node/TypeScript Pi sidecar that loads the overseas distributor prospecting skill and calls the FastAPI business API through custom tools.
```

- [ ] **Step 3: Update README run instructions**

Add:

```markdown
## Agent sidecar

```bash
cd agent
npm install
npm run build
npm run dev
```

The sidecar defaults to `http://localhost:8011` and calls the backend at `http://localhost:8000`.
Set `OPENAI_API_KEY` before running real agent chat. Without it, `/agent/chat` returns setup guidance instead of failing silently.
```

Update the full local flow to start backend, agent, then frontend.

- [ ] **Step 4: Git checkpoint**

Current workspace has no `.git`, so skip. If later inside a git repo:

```bash
git add .env.example README.md
git commit -m "docs: document pi agent sidecar"
```

## Task 7: Full Verification

**Files:**
- No new files unless fixes are required.

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd backend
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run agent tests and build**

Run:

```bash
cd agent
npm test
npm run build
```

Expected: all tests PASS and TypeScript build succeeds.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Manual local smoke test**

Start backend:

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

Start agent:

```bash
cd agent
npm run dev
```

Start frontend:

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

Open the Vite URL. Submit the default Agent prompt. With no `OPENAI_API_KEY`, the Agent panel should show setup guidance. With `OPENAI_API_KEY` set, it should run the Pi session and use the Medbot tools to create or list leads.

- [ ] **Step 5: Final status**

Record:

- Backend test result.
- Agent test/build result.
- Frontend build result.
- Local server URLs.
- Any missing credential limitation.
