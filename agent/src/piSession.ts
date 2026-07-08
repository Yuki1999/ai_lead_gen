import { existsSync } from "node:fs";

import { getModel, type Model, type Usage } from "@earendil-works/pi-ai";
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
// Each cached session's BackendClient, keyed by the session object itself so
// entries are freed automatically (WeakMap) whenever a session is evicted —
// no manual cleanup needed. Looked up each turn to refresh the delegated
// user's token even on a reused, long-lived cached session.
const sessionBackends = new WeakMap<AgentSession, BackendClient>();

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

export function extractUsage(event: AgentSessionEvent): Usage | null {
  if (event.type === "message_end" && event.message.role === "assistant") {
    return event.message.usage;
  }

  return null;
}

export interface TurnUsageTotals {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export function sumUsage(usages: Usage[]): TurnUsageTotals {
  return usages.reduce<TurnUsageTotals>(
    (totals, usage) => ({
      promptTokens: totals.promptTokens + usage.input,
      completionTokens: totals.completionTokens + usage.output,
      totalTokens: totals.totalTokens + usage.totalTokens,
    }),
    { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
  );
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
  userToken?: string,
): Promise<{ message: string; events: object[] }> {
  return runPiChatPrompt(message, sessionId, config, undefined, userToken);
}

export async function runPiChatStream(
  message: string,
  sessionId: string,
  config: AgentConfig,
  emit: (event: ChatStreamEvent) => void,
  userToken?: string,
): Promise<{ message: string; events: object[] }> {
  return runPiChatPrompt(message, sessionId, config, emit, userToken);
}

async function runPiChatPrompt(
  message: string,
  sessionId: string,
  config: AgentConfig,
  emit?: (event: ChatStreamEvent) => void,
  userToken?: string,
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
      piSessionConfigKey(config, userToken),
      async () => {
        const { session, configKey, backend } = await createManagedPiSession(config, userToken);
        sessionBackends.set(session, backend);
        return { session, configKey };
      },
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

    // Refresh to THIS turn's delegated identity even on a reused, long-lived
    // cached session, so RBAC always reflects who is asking right now.
    sessionBackends.get(session)?.setUserToken(userToken);

    const chunks: string[] = [];
    const events: object[] = [];
    const usages: Usage[] = [];
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
      const usage = extractUsage(event);
      if (usage) {
        usages.push(usage);
      }
    });

    try {
      await session.prompt(`/skill:${config.skillName}\n\n${message}`);
      reportTokenUsage(sessionBackends.get(session), config, sumUsage(usages));
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

// Best-effort usage telemetry: a reporting failure must never surface to the
// user or affect the chat turn that already completed successfully.
function reportTokenUsage(
  backend: BackendClient | undefined,
  config: AgentConfig,
  totals: TurnUsageTotals,
): void {
  if (!backend || totals.totalTokens <= 0) {
    return;
  }
  backend
    .recordTokenUsage({
      provider: config.modelProvider,
      model: config.modelName,
      prompt_tokens: totals.promptTokens,
      completion_tokens: totals.completionTokens,
      total_tokens: totals.totalTokens,
    })
    .catch((error) => {
      console.error("Failed to record agent chat token usage", error);
    });
}

// OpenAI-compatible providers that pi-ai doesn't ship a model registry for, but
// expose an OpenAI-style /chat/completions endpoint we can target directly.
const OPENAI_COMPATIBLE_BASE_URLS: Record<string, string> = {
  bailian: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  dashscope: "https://dashscope.aliyuncs.com/compatible-mode/v1",
};

function buildOpenAiCompatibleModel(
  config: AgentConfig,
): Model<"openai-completions"> | null {
  const baseUrl = OPENAI_COMPATIBLE_BASE_URLS[config.modelProvider];
  if (!baseUrl) {
    return null;
  }
  // The openai-completions streamer reads model.baseUrl and resolves the API key
  // from AuthStorage by provider (set above via setRuntimeApiKey).
  // DashScope's OpenAI-compatible mode rejects `store`, the `developer` role, and
  // `max_completion_tokens` — auto-detected defaults assume real OpenAI, so pin
  // compat explicitly for these third-party endpoints.
  return {
    id: config.modelName,
    name: config.modelName,
    api: "openai-completions",
    provider: config.modelProvider as Model<"openai-completions">["provider"],
    baseUrl,
    reasoning: true,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 131072,
    maxTokens: 8192,
    compat: {
      supportsStore: false,
      supportsDeveloperRole: false,
      supportsReasoningEffort: false,
      maxTokensField: "max_tokens",
      supportsStrictMode: false,
    },
  };
}

async function createManagedPiSession(
  config: AgentConfig,
  userToken?: string,
): Promise<{ session: AgentSession; configKey: string; backend: BackendClient }> {
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
      : buildOpenAiCompatibleModel(config) ??
        modelRegistry.find(config.modelProvider, config.modelName);

  if (!model) {
    throw new Error(
      `Pi model not found for provider ${config.modelProvider} and model ${config.modelName}`,
    );
  }

  const backend = new BackendClient(config.backendBaseUrl, {
    serviceToken: config.backendServiceToken,
    userToken,
  });
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

  return { session, configKey: piSessionConfigKey(config, userToken), backend };
}

function piSessionConfigKey(config: AgentConfig, userToken?: string): string {
  return [
    config.projectRoot,
    config.backendBaseUrl,
    config.modelProvider,
    config.modelName,
    config.skillName,
    config.skillPath,
    config.apiKey ? "model-key" : "no-model-key",
    // Discriminate by delegated user identity (not the raw token, so a token
    // refresh/relogin for the SAME user doesn't needlessly drop the cached Pi
    // conversation). A different user reusing the same client session_id
    // gets a fresh session instead of continuing someone else's conversation.
    decodeJwtSubject(userToken),
  ].join("\0");
}

// Unverified decode — only used as a cache-key discriminator. The backend
// independently and authoritatively verifies the token's signature on every
// outbound call, so a forged/tampered value here can't grant any permission;
// at worst it would just miss a cache hit.
function decodeJwtSubject(token: string | undefined): string {
  if (!token) return "";
  try {
    const payloadB64 = token.split(".")[1] ?? "";
    const padded = payloadB64.replace(/-/g, "+").replace(/_/g, "/");
    const json = Buffer.from(padded, "base64").toString("utf8");
    const payload = JSON.parse(json) as { sub?: unknown; username?: unknown };
    return String(payload.sub ?? payload.username ?? "");
  } catch {
    return "";
  }
}

function isPendingSession<TSession>(
  entry: CachedSessionEntry<TSession>,
): entry is PendingCachedSession<TSession> {
  return "promise" in entry;
}
