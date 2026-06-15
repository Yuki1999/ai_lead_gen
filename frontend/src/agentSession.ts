export const AGENT_SESSION_STORAGE_KEY = "medbot.agent.session_id";
export const AGENT_SESSIONS_STORAGE_KEY = "medbot.agent.sessions";

interface AgentSessionStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface AgentSessionRecord {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
}

export interface AgentSessionState {
  activeId: string;
  sessions: AgentSessionRecord[];
}

export function createAgentSessionId(
  now = Date.now(),
  random = Math.random,
): string {
  const timestamp = Math.max(0, Math.floor(now)).toString(36);
  const entropy = Math.floor(random() * 1_000_000_000)
    .toString(36)
    .padStart(6, "0");
  return `agent-${timestamp}-${entropy}`;
}

export function createAgentSessionRecord(
  title = "新会话",
  now = Date.now(),
  random = Math.random,
): AgentSessionRecord {
  return {
    id: createAgentSessionId(now, random),
    title,
    createdAt: now,
    updatedAt: now,
  };
}

export function isAgentSessionId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^agent-[a-z0-9]+-[a-z0-9]+$/i.test(value) &&
    value.length <= 160
  );
}

export function loadAgentSessionState(
  storage: AgentSessionStorage | undefined,
  create = () => createAgentSessionRecord(),
): AgentSessionState {
  const storedSessions = readAgentSessions(storage);
  const legacyActiveId = safeGet(storage, AGENT_SESSION_STORAGE_KEY);
  let sessions = storedSessions;

  if (isAgentSessionId(legacyActiveId) && !sessions.some((session) => session.id === legacyActiveId)) {
    const now = Date.now();
    sessions = [
      {
        id: legacyActiveId,
        title: "当前会话",
        createdAt: now,
        updatedAt: now,
      },
      ...sessions,
    ];
  }

  if (sessions.length === 0) {
    sessions = [create()];
  }

  const activeId = sessions.some((session) => session.id === legacyActiveId)
    ? (legacyActiveId as string)
    : sessions[0].id;
  const state = { activeId, sessions };
  persistAgentSessionState(storage, state);
  return state;
}

export function createNextAgentSession(
  storage: AgentSessionStorage | undefined,
  state: AgentSessionState,
  create = () => createAgentSessionRecord(`会话 ${state.sessions.length + 1}`),
): AgentSessionState {
  const session = create();
  const next = {
    activeId: session.id,
    sessions: [session, ...state.sessions.filter((item) => item.id !== session.id)].slice(0, 30),
  };
  persistAgentSessionState(storage, next);
  return next;
}

export function activateAgentSession(
  storage: AgentSessionStorage | undefined,
  state: AgentSessionState,
  sessionId: string,
): AgentSessionState {
  if (!state.sessions.some((session) => session.id === sessionId)) return state;
  const next = { ...state, activeId: sessionId };
  persistAgentSessionState(storage, next);
  return next;
}

export function renameAgentSession(
  storage: AgentSessionStorage | undefined,
  state: AgentSessionState,
  sessionId: string,
  title: string,
  now = Date.now(),
): AgentSessionState {
  const normalized = title.trim();
  if (!normalized) return state;

  const next = {
    ...state,
    sessions: state.sessions.map((session) =>
      session.id === sessionId
        ? { ...session, title: normalized.slice(0, 80), updatedAt: now }
        : session,
    ),
  };
  persistAgentSessionState(storage, next);
  return next;
}

export function deleteAgentSession(
  storage: AgentSessionStorage | undefined,
  state: AgentSessionState,
  sessionId: string,
  create = () => createAgentSessionRecord("新会话"),
): AgentSessionState {
  let sessions = state.sessions.filter((session) => session.id !== sessionId);

  if (sessions.length === 0) {
    sessions = [create()];
  }

  const activeId =
    state.activeId === sessionId || !sessions.some((session) => session.id === state.activeId)
      ? sessions[0].id
      : state.activeId;
  const next = { activeId, sessions };
  persistAgentSessionState(storage, next);
  return next;
}

export function loadAgentSessionId(
  storage: AgentSessionStorage | undefined,
  create = createAgentSessionId,
): string {
  const existing = safeGet(storage, AGENT_SESSION_STORAGE_KEY);
  if (isAgentSessionId(existing)) return existing;

  const next = create();
  safeSet(storage, AGENT_SESSION_STORAGE_KEY, next);
  return next;
}

export function resetAgentSessionId(
  storage: AgentSessionStorage | undefined,
  create = createAgentSessionId,
): string {
  const next = create();
  safeSet(storage, AGENT_SESSION_STORAGE_KEY, next);
  return next;
}

export function saveAgentSessionId(
  storage: AgentSessionStorage | undefined,
  value: string,
): void {
  if (isAgentSessionId(value)) {
    safeSet(storage, AGENT_SESSION_STORAGE_KEY, value);
  }
}

function readAgentSessions(storage: AgentSessionStorage | undefined): AgentSessionRecord[] {
  const raw = safeGet(storage, AGENT_SESSIONS_STORAGE_KEY);
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const seen = new Set<string>();
    return parsed
      .map((value) => normalizeAgentSessionRecord(value))
      .filter((session): session is AgentSessionRecord => {
        if (!session || seen.has(session.id)) return false;
        seen.add(session.id);
        return true;
      });
  } catch {
    return [];
  }
}

function normalizeAgentSessionRecord(value: unknown): AgentSessionRecord | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const candidate = value as Partial<AgentSessionRecord>;
  if (!isAgentSessionId(candidate.id)) return null;

  const title = typeof candidate.title === "string" ? candidate.title.trim() : "";
  return {
    id: candidate.id,
    title: title ? title.slice(0, 80) : "未命名会话",
    createdAt: finiteTimestamp(candidate.createdAt),
    updatedAt: finiteTimestamp(candidate.updatedAt),
  };
}

function finiteTimestamp(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : Date.now();
}

function persistAgentSessionState(
  storage: AgentSessionStorage | undefined,
  state: AgentSessionState,
): void {
  safeSet(storage, AGENT_SESSION_STORAGE_KEY, state.activeId);
  safeSet(storage, AGENT_SESSIONS_STORAGE_KEY, JSON.stringify(state.sessions));
}

function safeGet(storage: AgentSessionStorage | undefined, key: string): string | null {
  if (!storage) return null;
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(storage: AgentSessionStorage | undefined, key: string, value: string): void {
  if (!storage) return;
  try {
    storage.setItem(key, value);
  } catch {
    // Browsers can block localStorage in private or hardened contexts.
  }
}
