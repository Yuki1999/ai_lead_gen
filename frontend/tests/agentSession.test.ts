import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  AGENT_SESSIONS_STORAGE_KEY,
  AGENT_SESSION_STORAGE_KEY,
  activateAgentSession,
  createAgentSessionId,
  createNextAgentSession,
  deleteAgentSession,
  deriveSessionTitle,
  isAgentSessionId,
  isDefaultSessionTitle,
  loadAgentSessionState,
  loadAgentSessionId,
  renameAgentSession,
  resetAgentSessionId,
  saveAgentSessionId,
} from "../src/agentSession.ts";

function createMemoryStorage(initial?: string): Storage {
  const values = new Map<string, string>();
  if (initial) values.set(AGENT_SESSION_STORAGE_KEY, initial);

  return {
    get length() {
      return values.size;
    },
    clear() {
      values.clear();
    },
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(values.keys())[index] ?? null;
    },
    removeItem(key: string) {
      values.delete(key);
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    },
  };
}

describe("agent session persistence", () => {
  it("creates bounded agent session ids", () => {
    const id = createAgentSessionId(1_714_000_000_000, () => 0.42);

    assert.match(id, /^agent-[a-z0-9]+-[a-z0-9]+$/);
    assert.equal(isAgentSessionId(id), true);
    assert.equal(id.length <= 160, true);
  });

  it("loads an existing persisted session id", () => {
    const storage = createMemoryStorage("agent-existing-123abc");

    assert.equal(loadAgentSessionId(storage), "agent-existing-123abc");
  });

  it("persists a new session id when storage is empty", () => {
    const storage = createMemoryStorage();
    const id = loadAgentSessionId(storage, () => "agent-new-session");

    assert.equal(id, "agent-new-session");
    assert.equal(storage.getItem(AGENT_SESSION_STORAGE_KEY), "agent-new-session");
  });

  it("resets and persists a replacement session id", () => {
    const storage = createMemoryStorage("agent-old-session");
    const id = resetAgentSessionId(storage, () => "agent-next-session");

    assert.equal(id, "agent-next-session");
    assert.equal(storage.getItem(AGENT_SESSION_STORAGE_KEY), "agent-next-session");
  });

  it("saves only valid agent session ids", () => {
    const storage = createMemoryStorage("agent-old-session");

    saveAgentSessionId(storage, "default");
    assert.equal(storage.getItem(AGENT_SESSION_STORAGE_KEY), "agent-old-session");

    saveAgentSessionId(storage, "agent-valid-session");
    assert.equal(storage.getItem(AGENT_SESSION_STORAGE_KEY), "agent-valid-session");
  });

  it("creates and persists a first managed session when storage is empty", () => {
    const storage = createMemoryStorage();
    const state = loadAgentSessionState(storage, () => ({
      id: "agent-first-session",
      title: "会话 1",
      createdAt: 100,
      updatedAt: 100,
    }));

    assert.equal(state.activeId, "agent-first-session");
    assert.deepEqual(state.sessions, [
      {
        id: "agent-first-session",
        title: "会话 1",
        createdAt: 100,
        updatedAt: 100,
      },
    ]);
    assert.equal(storage.getItem(AGENT_SESSION_STORAGE_KEY), "agent-first-session");
    assert.match(storage.getItem(AGENT_SESSIONS_STORAGE_KEY) || "", /agent-first-session/);
  });

  it("migrates a legacy single session id into the managed session list", () => {
    const storage = createMemoryStorage("agent-legacy-session");
    const state = loadAgentSessionState(storage, () => ({
      id: "agent-unused-session",
      title: "unused",
      createdAt: 1,
      updatedAt: 1,
    }));

    assert.equal(state.activeId, "agent-legacy-session");
    assert.equal(state.sessions[0].id, "agent-legacy-session");
  });

  it("creates, activates, renames, and deletes managed sessions", () => {
    const storage = createMemoryStorage();
    let counter = 0;
    const create = () => {
      counter += 1;
      return {
        id: `agent-session-${counter}`,
        title: `会话 ${counter}`,
        createdAt: counter,
        updatedAt: counter,
      };
    };

    let state = loadAgentSessionState(storage, create);
    state = createNextAgentSession(storage, state, create);
    assert.equal(state.activeId, "agent-session-2");
    assert.deepEqual(
      state.sessions.map((session) => session.id),
      ["agent-session-2", "agent-session-1"],
    );

    state = activateAgentSession(storage, state, "agent-session-1");
    assert.equal(state.activeId, "agent-session-1");
    assert.equal(storage.getItem(AGENT_SESSION_STORAGE_KEY), "agent-session-1");

    state = renameAgentSession(storage, state, "agent-session-1", "  India 渠道  ", 99);
    assert.equal(state.sessions.find((session) => session.id === "agent-session-1")?.title, "India 渠道");

    state = deleteAgentSession(storage, state, "agent-session-1", create);
    assert.equal(state.activeId, "agent-session-2");
    assert.deepEqual(state.sessions.map((session) => session.id), ["agent-session-2"]);

    state = deleteAgentSession(storage, state, "agent-session-2", create);
    assert.equal(state.activeId, "agent-session-3");
    assert.deepEqual(state.sessions.map((session) => session.id), ["agent-session-3"]);
  });
});

describe("auto session titling", () => {
  it("recognizes only the auto-generated placeholder titles", () => {
    assert.equal(isDefaultSessionTitle("新会话"), true);
    assert.equal(isDefaultSessionTitle("会话 2"), true);
    assert.equal(isDefaultSessionTitle("会话12"), true);
    assert.equal(isDefaultSessionTitle("当前会话"), true);
    assert.equal(isDefaultSessionTitle("未命名会话"), true);
    // A real / user-given title must not be treated as a placeholder.
    assert.equal(isDefaultSessionTitle("找印度 TKA 渠道商"), false);
    assert.equal(isDefaultSessionTitle("会话记录整理"), false);
  });

  it("derives a concise title from the first message", () => {
    assert.equal(deriveSessionTitle("帮我找印度的 TKA 渠道商"), "帮我找印度的 TKA 渠道商");
    assert.equal(deriveSessionTitle("  多个   空格   合并  "), "多个 空格 合并");
    assert.equal(deriveSessionTitle("   "), "新会话");
    // Long messages are truncated to maxLength + an ellipsis.
    const long = deriveSessionTitle("请详细列举拓展印度 TKA 渠道商的十个步骤并逐一展开说明每一步");
    assert.ok(long.endsWith("…"));
    assert.equal(long.length, 25);
  });
});
