import { existsSync } from "node:fs";

import { getModel } from "@earendil-works/pi-ai";
import {
  AuthStorage,
  createAgentSession,
  createSyntheticSourceInfo,
  DefaultResourceLoader,
  getAgentDir,
  ModelRegistry,
  SessionManager,
  type AgentSession,
  type AgentSessionEvent,
  type Skill,
} from "@earendil-works/pi-coding-agent";

import { BackendClient } from "./backendClient.js";
import type { AgentConfig } from "./config.js";
import { createBusinessTools } from "./tools.js";

export const DEFAULT_SYSTEM_PROMPT = `
You are the Medbot overseas distributor prospecting agent.
Default to the overseas-distributor-prospecting skill unless the user explicitly asks for another workflow.
Do not invent companies, contacts, emails, websites, or evidence.
Prefer official sources, including official company websites, regulatory directories, exhibitor lists, distributor pages, and hospital-equipment channel evidence.
Use the registered tools for product profile lookup, lead search, lead listing, outreach records, and reply analysis.
Escalate legal, exclusivity, pricing, regulatory, tender, contract, liability, warranty, clinical, and adverse-event topics to human review.
`.trim();

type JsonSafeObject = Record<string, string | number | boolean | null>;
type CachedSessionFactory<TSession> = () => Promise<{
  session: TSession;
  configKey: string;
}>;

export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "agent_event"; event: JsonSafeObject };

export interface CachedSession<TSession> {
  session: TSession;
  configKey: string;
  lastUsedAt: number;
}

interface PendingCachedSession<TSession> {
  configKey: string;
  promise: Promise<CachedSession<TSession>>;
}

type CachedSessionEntry<TSession> =
  | CachedSession<TSession>
  | PendingCachedSession<TSession>;

// Session objects are cached by client session_id so follow-up requests keep
// Pi conversation context. Each prompt attaches one listener and removes it in
// finally; cached sessions are disposed when their runtime config changes.
const sessionCache = new Map<string, CachedSessionEntry<AgentSession>>();
const promptLocks = new Map<string, Promise<void>>();

export function buildSystemPrompt(base?: string): string {
  return base ? `${base}\n\n${DEFAULT_SYSTEM_PROMPT}` : DEFAULT_SYSTEM_PROMPT;
}

export function createDefaultSkill(config: AgentConfig): Skill {
  return {
    name: config.skillName,
    description:
      "Overseas distributor prospecting for Medbot, SkyWalker TKA, orthopedic surgical robotics, and medical device channels.",
    filePath: config.skillPath,
    baseDir: config.skillBaseDir,
    sourceInfo: createSyntheticSourceInfo(config.skillPath, {
      source: "medbot-sidecar",
      scope: "project",
      origin: "top-level",
      baseDir: config.skillBaseDir,
    }),
    disableModelInvocation: false,
  };
}

export function extractTextDelta(event: AgentSessionEvent): string {
  if (
    event.type === "message_update" &&
    event.assistantMessageEvent.type === "text_delta"
  ) {
    return event.assistantMessageEvent.delta;
  }

  return "";
}

export function summarizeEvent(event: AgentSessionEvent): JsonSafeObject | null {
  if (event.type === "message_update") {
    return null;
  }

  const summary: JsonSafeObject = { type: event.type };

  if (
    (event.type === "tool_execution_start" ||
      event.type === "tool_execution_update" ||
      event.type === "tool_execution_end") &&
    typeof event.toolName === "string"
  ) {
    summary.toolName = event.toolName;
  }

  return summary;
}

export async function getOrCreateCachedSession<TSession>(
  sessionId: string,
  configKey: string,
  factory: CachedSessionFactory<TSession>,
  cache: Map<string, CachedSessionEntry<TSession>> = new Map(),
  disposeSession?: (session: TSession) => void,
  now = Date.now(),
): Promise<CachedSession<TSession>> {
  const cached = cache.get(sessionId);
  if (cached && isPendingSession(cached)) {
    await cached.promise;
    return getOrCreateCachedSession(
      sessionId,
      configKey,
      factory,
      cache,
      disposeSession,
      now,
    );
  } else if (cached?.configKey === configKey) {
    cached.lastUsedAt = now;
    return cached;
  } else if (cached) {
    disposeSession?.(cached.session);
  }

  const pending: PendingCachedSession<TSession> = {
    configKey,
    promise: factory().then((created) => ({
      ...created,
      lastUsedAt: now,
    })),
  };
  cache.set(sessionId, pending);

  try {
    const created = await pending.promise;
    if (cache.get(sessionId) === pending) {
      cache.set(sessionId, created);
    }
    return created;
  } catch (error) {
    if (cache.get(sessionId) === pending) {
      cache.delete(sessionId);
    }
    throw error;
  }
}

export async function runWithSessionLock<T>(
  sessionId: string,
  operation: () => Promise<T>,
  locks: Map<string, Promise<void>> = promptLocks,
): Promise<T> {
  const previous = locks.get(sessionId) ?? Promise.resolve();
  const run = previous.catch(() => undefined).then(operation);
  const current = run.then(
    () => undefined,
    () => undefined,
  );
  locks.set(sessionId, current);

  try {
    return await run;
  } finally {
    if (locks.get(sessionId) === current) {
      locks.delete(sessionId);
    }
  }
}

export function evictCachedSessions<TSession>(
  cache: Map<string, CachedSessionEntry<TSession>>,
  options: {
    now: number;
    maxSessions: number;
    idleMs: number;
    disposeSession: (session: TSession) => void;
    protectedSessionIds?: Set<string>;
  },
): void {
  const protectedSessionIds = options.protectedSessionIds ?? new Set<string>();

  for (const [sessionId, entry] of cache) {
    if (protectedSessionIds.has(sessionId) || isPendingSession(entry)) {
      continue;
    }

    if (options.now - entry.lastUsedAt > options.idleMs) {
      options.disposeSession(entry.session);
      cache.delete(sessionId);
    }
  }

  const liveEntries = [...cache.entries()]
    .filter(
      (entry): entry is [string, CachedSession<TSession>] =>
        !protectedSessionIds.has(entry[0]) && !isPendingSession(entry[1]),
    )
    .sort((left, right) => left[1].lastUsedAt - right[1].lastUsedAt);

  let liveCount = [...cache.values()].filter(
    (entry) => !isPendingSession(entry),
  ).length;
  for (const [sessionId, entry] of liveEntries) {
    if (liveCount <= options.maxSessions) {
      break;
    }
    options.disposeSession(entry.session);
    cache.delete(sessionId);
    liveCount -= 1;
  }
}

export async function runPiChat(
  message: string,
  sessionId: string,
  config: AgentConfig,
): Promise<{ message: string; events: object[] }> {
  return runPiChatPrompt(message, sessionId, config);
}

export async function runPiChatStream(
  message: string,
  sessionId: string,
  config: AgentConfig,
  emit: (event: ChatStreamEvent) => void,
): Promise<{ message: string; events: object[] }> {
  return runPiChatPrompt(message, sessionId, config, emit);
}

async function runPiChatPrompt(
  message: string,
  sessionId: string,
  config: AgentConfig,
  emit?: (event: ChatStreamEvent) => void,
): Promise<{ message: string; events: object[] }> {
  return runWithSessionLock(sessionId, async () => {
    evictCachedSessions(sessionCache, {
      now: Date.now(),
      maxSessions: config.maxSessions,
      idleMs: config.sessionIdleMs,
      disposeSession: (session) => session.dispose(),
      protectedSessionIds: new Set(promptLocks.keys()),
    });

    const managedSession = await getOrCreateCachedSession(
      sessionId,
      piSessionConfigKey(config),
      () => createManagedPiSession(config),
      sessionCache,
      (session) => session.dispose(),
    );
    const { session } = managedSession;
    managedSession.lastUsedAt = Date.now();
    evictCachedSessions(sessionCache, {
      now: managedSession.lastUsedAt,
      maxSessions: config.maxSessions,
      idleMs: config.sessionIdleMs,
      disposeSession: (cachedSession) => cachedSession.dispose(),
      protectedSessionIds: new Set(promptLocks.keys()),
    });

    const chunks: string[] = [];
    const events: object[] = [];
    const unsubscribe = session.subscribe((event) => {
      const summary = summarizeEvent(event);
      if (summary) {
        events.push(summary);
        emit?.({ type: "agent_event", event: summary });
      }
      const delta = extractTextDelta(event);
      if (delta) {
        chunks.push(delta);
        emit?.({ type: "delta", text: delta });
      }
    });

    try {
      await session.prompt(`/skill:${config.skillName}\n\n${message}`);
      return {
        message:
          chunks.join("").trim() || "Agent completed without a text response.",
        events: events.slice(-50),
      };
    } finally {
      managedSession.lastUsedAt = Date.now();
      unsubscribe();
    }
  });
}

async function createManagedPiSession(
  config: AgentConfig,
): Promise<{ session: AgentSession; configKey: string }> {
  if (!existsSync(config.skillPath)) {
    throw new Error(`Default skill not found at ${config.skillPath}`);
  }

  const projectRoot = config.projectRoot || process.cwd();
  const agentDir = getAgentDir();
  const authStorage = AuthStorage.inMemory();
  if (config.apiKey) {
    authStorage.setRuntimeApiKey(config.modelProvider, config.apiKey);
  }

  const modelRegistry = ModelRegistry.inMemory(authStorage);
  const model =
    config.modelProvider === "openai" && config.modelName === "gpt-5-mini"
      ? getModel("openai", "gpt-5-mini")
      : modelRegistry.find(config.modelProvider, config.modelName);

  if (!model) {
    throw new Error(
      `Pi model not found for provider ${config.modelProvider} and model ${config.modelName}`,
    );
  }

  const backend = new BackendClient(config.backendBaseUrl);
  const businessTools = createBusinessTools(backend);
  const resourceLoader = new DefaultResourceLoader({
    cwd: projectRoot,
    agentDir,
    systemPromptOverride: buildSystemPrompt,
    skillsOverride: (current) => ({
      skills: [...current.skills, createDefaultSkill(config)],
      diagnostics: current.diagnostics,
    }),
  });
  await resourceLoader.reload();

  const { session } = await createAgentSession({
    cwd: projectRoot,
    agentDir,
    model,
    authStorage,
    modelRegistry,
    resourceLoader,
    sessionManager: SessionManager.inMemory(projectRoot),
    customTools: businessTools,
    tools: businessTools.map((tool) => tool.name),
  });

  return { session, configKey: piSessionConfigKey(config) };
}

function piSessionConfigKey(config: AgentConfig): string {
  return [
    config.projectRoot,
    config.backendBaseUrl,
    config.modelProvider,
    config.modelName,
    config.skillName,
    config.skillPath,
    config.apiKey ? "model-key" : "no-model-key",
  ].join("\0");
}

function isPendingSession<TSession>(
  entry: CachedSessionEntry<TSession>,
): entry is PendingCachedSession<TSession> {
  return "promise" in entry;
}
