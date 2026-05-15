import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { describe, it } from "node:test";

import { createServer } from "../src/server.js";

async function request(
  server: ReturnType<typeof createServer>,
  path: string,
  init: RequestInit = {},
) {
  const listener = server.listen(0);
  await new Promise<void>((resolve) => listener.once("listening", resolve));
  const address = listener.address();
  assert.equal(typeof address, "object");
  assert.ok(address);
  const port = (address as AddressInfo).port;
  try {
    return await fetch(`http://127.0.0.1:${port}${path}`, init);
  } finally {
    await new Promise<void>((resolve) => listener.close(() => resolve()));
  }
}

function parseSse(text: string): Array<{ event: string; data: Record<string, unknown> }> {
  return text
    .trim()
    .split(/\n\n+/)
    .map((frame) => {
      const eventLine = frame.split("\n").find((line) => line.startsWith("event: "));
      const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
      assert.ok(eventLine);
      assert.ok(dataLine);
      return {
        event: eventLine.slice("event: ".length),
        data: JSON.parse(dataLine.slice("data: ".length)) as Record<string, unknown>,
      };
    });
}

describe("agent server", () => {
  it("serves health checks", async () => {
    const response = await request(createServer(), "/health");

    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { status: "ok" });
  });

  it("returns setup guidance when no model credentials are configured", async () => {
    const response = await request(createServer({ env: testEnv() }), "/agent/chat", {
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

  it("calls the chat runner when model credentials are configured", async () => {
    const calls: object[] = [];
    const response = await request(
      createServer({
        env: testEnv({ OPENAI_API_KEY: "test-key" }),
        runChat: async (message, sessionId, config) => {
          calls.push({
            message,
            sessionId,
            skillName: config.skillName,
            projectRoot: config.projectRoot,
          });
          return {
            message: "runner response",
            events: [{ type: "tool_execution_start", toolName: "search_leads" }],
          };
        },
      }),
      "/agent/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "Find India distributors",
          session_id: "session-123",
        }),
      },
    );

    assert.equal(response.status, 200);
    assert.deepEqual(calls, [
      {
        message: "Find India distributors",
        sessionId: "session-123",
        skillName: "overseas-distributor-prospecting",
        projectRoot: resolveProjectRootForTest(),
      },
    ]);
    assert.deepEqual(await response.json(), {
      message: "runner response",
      session_id: "session-123",
      events: [
        {
          type: "skill_loaded",
          skillName: "overseas-distributor-prospecting",
          skillPath: `${resolveProjectRootForTest()}/skills/overseas-distributor-prospecting/SKILL.md`,
        },
        { type: "tool_execution_start", toolName: "search_leads" },
      ],
    });
  });

  it("streams chat runner progress as server-sent events", async () => {
    const response = await request(
      createServer({
        env: testEnv({ OPENAI_API_KEY: "test-key" }),
        runChatStream: async (message, sessionId, config, emit) => {
          assert.equal(message, "Find India distributors");
          assert.equal(sessionId, "session-123");
          assert.equal(config.skillName, "overseas-distributor-prospecting");
          emit({ type: "delta", text: "First " });
          emit({
            type: "agent_event",
            event: { type: "tool_execution_start", toolName: "search_leads" },
          });
          emit({ type: "delta", text: "second." });
          return {
            message: "First second.",
            events: [{ type: "tool_execution_start", toolName: "search_leads" }],
          };
        },
      }),
      "/agent/chat/stream",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "Find India distributors",
          session_id: "session-123",
        }),
      },
    );

    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /text\/event-stream/);
    const frames = parseSse(await response.text());
    assert.deepEqual(frames, [
      { event: "start", data: { session_id: "session-123" } },
      {
        event: "agent_event",
        data: {
          event: {
            type: "skill_loaded",
            skillName: "overseas-distributor-prospecting",
            skillPath: `${resolveProjectRootForTest()}/skills/overseas-distributor-prospecting/SKILL.md`,
          },
        },
      },
      { event: "delta", data: { text: "First " } },
      {
        event: "agent_event",
        data: { event: { type: "tool_execution_start", toolName: "search_leads" } },
      },
      { event: "delta", data: { text: "second." } },
      {
        event: "done",
        data: {
          message: "First second.",
          session_id: "session-123",
          events: [
            {
              type: "skill_loaded",
              skillName: "overseas-distributor-prospecting",
              skillPath: `${resolveProjectRootForTest()}/skills/overseas-distributor-prospecting/SKILL.md`,
            },
            { type: "tool_execution_start", toolName: "search_leads" },
          ],
        },
      },
    ]);
  });

  it("rejects chat requests on non-local hosts when AGENT_TOKEN is not configured", async () => {
    const response = await request(
      createServer({ env: testEnv({ AGENT_HOST: "0.0.0.0" }) }),
      "/agent/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "Find India distributors" }),
      },
    );

    assert.equal(response.status, 403);
    const payload = await response.json();
    assert.match(payload.detail, /AGENT_TOKEN/);
  });

  it("requires a bearer token for chat requests when AGENT_TOKEN is configured", async () => {
    const response = await request(
      createServer({ env: testEnv({ AGENT_TOKEN: "secret" }) }),
      "/agent/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "Find India distributors" }),
      },
    );

    assert.equal(response.status, 403);
    const payload = await response.json();
    assert.match(payload.detail, /Authorization/);
  });

  it("allows authorized chat requests with AGENT_TOKEN and missing model credentials still returns setup guidance", async () => {
    const response = await request(
      createServer({ env: testEnv({ AGENT_TOKEN: "secret" }) }),
      "/agent/chat",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer secret",
        },
        body: JSON.stringify({ message: "Find India distributors" }),
      },
    );

    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.match(payload.message, /OPENAI_API_KEY/);
  });

  it("returns 400 for malformed JSON", async () => {
    const response = await request(createServer({ env: testEnv() }), "/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{not-json",
    });

    assert.equal(response.status, 400);
    const payload = await response.json();
    assert.match(payload.detail, /invalid json/i);
  });

  for (const [name, body] of [
    ["null", "null"],
    ["array", "[]"],
    ["string", JSON.stringify("hello")],
  ]) {
    it(`returns 400 when JSON body is ${name}`, async () => {
      const response = await request(createServer({ env: testEnv() }), "/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });

      assert.equal(response.status, 400);
      const payload = await response.json();
      assert.match(payload.detail, /json object/i);
    });
  }

  it("returns a useful error for oversized request bodies", async () => {
    const response = await request(createServer({ env: testEnv() }), "/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "x".repeat(70 * 1024) }),
    });

    assert.ok(response.status === 400 || response.status === 413);
    const payload = await response.json();
    assert.match(payload.detail, /too large|body size/i);
  });

  it("handles CORS preflight for chat requests", async () => {
    const response = await request(createServer({ env: testEnv() }), "/agent/chat", {
      method: "OPTIONS",
      headers: { Origin: "http://localhost:5173" },
    });

    assert.ok(response.status === 200 || response.status === 204);
    assert.match(
      response.headers.get("access-control-allow-methods") ?? "",
      /POST/,
    );
    assert.match(
      response.headers.get("access-control-allow-headers") ?? "",
      /Content-Type/i,
    );
  });
});

function resolveProjectRootForTest(): string {
  return new URL("../..", import.meta.url).pathname.replace(/\/$/, "");
}

function testEnv(
  overrides: Record<string, string | undefined> = {},
): Record<string, string | undefined> {
  return {
    AGENT_CORS_ORIGIN: "",
    AGENT_HOST: "",
    AGENT_MAX_BODY_BYTES: "",
    AGENT_MAX_SESSIONS: "",
    AGENT_PORT: "",
    AGENT_SESSION_IDLE_MS: "",
    AGENT_TOKEN: "",
    BACKEND_BASE_URL: "",
    DEEPSEEK_API_KEY: "",
    OPENAI_API_KEY: "",
    PI_MODEL: "",
    PI_PROVIDER: "",
    PROJECT_ROOT: "",
    ...overrides,
  };
}
