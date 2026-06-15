import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { AgentSessionEvent } from "@earendil-works/pi-coding-agent";

import { loadConfig } from "../src/config.js";
import {
  buildSystemPrompt,
  createDefaultSkill,
  evictCachedSessions,
  extractTextDelta,
  getOrCreateCachedSession,
  runWithSessionLock,
  summarizeEvent,
} from "../src/piSession.js";

describe("piSession helpers", () => {
  it("builds the Medbot system prompt and preserves an existing base prompt", () => {
    const prompt = buildSystemPrompt("Base Pi prompt.");

    assert.match(prompt, /^Base Pi prompt\./);
    assert.match(prompt, /overseas-distributor-prospecting/);
    assert.match(prompt, /Do not invent companies, contacts, emails, websites, or evidence/);
    assert.match(prompt, /Escalate .*pricing.*regulatory.*contract/i);
  });

  it("creates the default project skill with synthetic source metadata", () => {
    const config = loadConfig({ env: {}, cwd: process.cwd() });
    const skill = createDefaultSkill(config);

    assert.equal(skill.name, "overseas-distributor-prospecting");
    assert.equal(skill.filePath, config.skillPath);
    assert.equal(skill.baseDir, config.skillBaseDir);
    assert.equal(skill.disableModelInvocation, false);
    assert.equal(skill.sourceInfo.source, "medbot-sidecar");
    assert.equal(skill.sourceInfo.scope, "project");
    assert.equal(skill.sourceInfo.origin, "top-level");
    assert.equal(skill.sourceInfo.baseDir, config.skillBaseDir);
  });

  it("extracts assistant text deltas from message update events", () => {
    const event = {
      type: "message_update",
      assistantMessageEvent: { type: "text_delta", delta: "hello" },
    } as AgentSessionEvent;

    assert.equal(extractTextDelta(event), "hello");
    assert.equal(extractTextDelta({ type: "turn_start" } as AgentSessionEvent), "");
  });

  it("summarizes tool events without carrying raw payloads", () => {
    const summary = summarizeEvent({
      type: "tool_execution_start",
      toolName: "search_leads",
      toolCallId: "call-1",
      args: { target_regions: ["India"] },
    } as AgentSessionEvent);

    assert.deepEqual(summary, {
      type: "tool_execution_start",
      toolName: "search_leads",
    });
  });

  it("does not summarize high-frequency message update events", () => {
    const summary = summarizeEvent({
      type: "message_update",
      assistantMessageEvent: { type: "text_delta", delta: "hello" },
    } as AgentSessionEvent);

    assert.equal(summary, null);
  });

  it("reuses cached sessions by session ID and config key", async () => {
    let created = 0;
    const cache = new Map();
    const first = await getOrCreateCachedSession(
      "session-1",
      "test-config",
      async () => ({
        session: { id: ++created },
        configKey: "test-config",
      }),
      cache,
    );
    const second = await getOrCreateCachedSession(
      "session-1",
      "test-config",
      async () => ({
        session: { id: ++created },
        configKey: "test-config",
      }),
      cache,
    );
    const third = await getOrCreateCachedSession(
      "session-1",
      "other-config",
      async () => ({
        session: { id: ++created },
        configKey: "other-config",
      }),
      cache,
    );

    assert.equal(first.session, second.session);
    assert.notEqual(second.session, third.session);
    assert.equal(created, 2);
  });

  it("coalesces concurrent cached session creation for the same session ID and config", async () => {
    let created = 0;
    let releaseFactory: (() => void) | undefined;
    const cache = new Map();
    const factoryStarted = new Promise<void>((resolve) => {
      const factory = async () => {
        created += 1;
        resolve();
        await new Promise<void>((release) => {
          releaseFactory = release;
        });
        return {
          session: { id: created },
          configKey: "test-config",
        };
      };

      const first = getOrCreateCachedSession("session-1", "test-config", factory, cache);
      const second = getOrCreateCachedSession("session-1", "test-config", factory, cache);
      void Promise.all([first, second]).then(([firstResult, secondResult]) => {
        assert.equal(firstResult.session, secondResult.session);
      });
    });

    await factoryStarted;
    assert.equal(created, 1);
    releaseFactory?.();
    const [first, second] = await Promise.all([
      getOrCreateCachedSession("session-1", "test-config", async () => ({
        session: { id: ++created },
        configKey: "test-config",
      }), cache),
      getOrCreateCachedSession("session-1", "test-config", async () => ({
        session: { id: ++created },
        configKey: "test-config",
      }), cache),
    ]);

    assert.equal(first.session, second.session);
    assert.equal(created, 1);
  });

  it("serializes prompt work for the same session while allowing different sessions to overlap", async () => {
    const events: string[] = [];
    let releaseFirst: (() => void) | undefined;

    const first = runWithSessionLock("same", async () => {
      events.push("same-1-start");
      await new Promise<void>((resolve) => {
        releaseFirst = resolve;
      });
      events.push("same-1-end");
      return "same-1";
    });
    await waitFor(() => events.includes("same-1-start"));

    const second = runWithSessionLock("same", async () => {
      events.push("same-2-start");
      return "same-2";
    });
    const other = runWithSessionLock("other", async () => {
      events.push("other-start");
      return "other";
    });
    await waitFor(() => events.includes("other-start"));

    assert.deepEqual(events, ["same-1-start", "other-start"]);
    releaseFirst?.();
    assert.deepEqual(await Promise.all([first, second, other]), [
      "same-1",
      "same-2",
      "other",
    ]);
    assert.deepEqual(events, [
      "same-1-start",
      "other-start",
      "same-1-end",
      "same-2-start",
    ]);
  });

  it("evicts idle and oldest cached sessions and disposes live sessions", () => {
    const disposed: string[] = [];
    const cache = new Map([
      [
        "idle",
        {
          configKey: "config",
          session: { id: "idle", dispose: () => disposed.push("idle") },
          lastUsedAt: 1_000,
        },
      ],
      [
        "oldest",
        {
          configKey: "config",
          session: { id: "oldest", dispose: () => disposed.push("oldest") },
          lastUsedAt: 5_000,
        },
      ],
      [
        "newest",
        {
          configKey: "config",
          session: { id: "newest", dispose: () => disposed.push("newest") },
          lastUsedAt: 10_000,
        },
      ],
    ]);

    evictCachedSessions(cache, {
      now: 11_000,
      maxSessions: 1,
      idleMs: 6_000,
      disposeSession: (session) => session.dispose(),
    });

    assert.deepEqual([...cache.keys()], ["newest"]);
    assert.deepEqual(disposed, ["idle", "oldest"]);
  });
});

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.fail("condition was not met");
}
