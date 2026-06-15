import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export interface AgentConfig {
  projectRoot: string;
  host: string;
  port: number;
  backendBaseUrl: string;
  modelProvider: string;
  modelName: string;
  skillName: string;
  skillPath: string;
  skillBaseDir: string;
  apiKey?: string;
  openaiApiKey?: string;
  agentToken?: string;
  hasModelCredentials: boolean;
  corsOrigin: string;
  maxBodyBytes: number;
  maxSessions: number;
  sessionIdleMs: number;
}

interface LoadConfigOptions {
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>;
  cwd?: string;
  projectRoot?: string;
}

const DEFAULT_SKILL_NAME = "overseas-distributor-prospecting";
const DEFAULT_MAX_BODY_BYTES = 64 * 1024;
const DEFAULT_MAX_SESSIONS = 20;
const DEFAULT_SESSION_IDLE_MS = 30 * 60 * 1000;
const DEFAULT_MODEL_BY_PROVIDER: Record<string, string> = {
  openai: "gpt-5-mini",
  deepseek: "deepseek-v4-pro",
};
const PROVIDER_API_KEY_ENV: Record<string, string> = {
  openai: "OPENAI_API_KEY",
  deepseek: "DEEPSEEK_API_KEY",
};

export function loadConfig(options: LoadConfigOptions = {}): AgentConfig {
  const processEnv = options.env ?? process.env;
  const projectRoot = resolveProjectRoot(options, processEnv);
  const env = mergeEnv(loadDotEnv(resolve(projectRoot, "agent", ".env")), processEnv);
  const skillBaseDir = resolve(projectRoot, "skills", DEFAULT_SKILL_NAME);
  const skillPath = resolve(skillBaseDir, "SKILL.md");
  const modelProvider = resolveModelProvider(env);
  const apiKey = env[apiKeyEnvName(modelProvider)] || undefined;
  const openaiApiKey = env.OPENAI_API_KEY || undefined;

  return {
    projectRoot,
    host: env.AGENT_HOST || "127.0.0.1",
    port: parsePort(env.AGENT_PORT),
    backendBaseUrl: (env.BACKEND_BASE_URL || "http://localhost:8000").replace(
      /\/$/,
      "",
    ),
    modelProvider,
    modelName: env.PI_MODEL || DEFAULT_MODEL_BY_PROVIDER[modelProvider] || "gpt-5-mini",
    skillName: DEFAULT_SKILL_NAME,
    skillPath,
    skillBaseDir,
    apiKey,
    openaiApiKey,
    agentToken: env.AGENT_TOKEN || undefined,
    hasModelCredentials: Boolean(apiKey),
    corsOrigin: env.AGENT_CORS_ORIGIN || "http://localhost:5173",
    maxBodyBytes: parsePositiveInt(
      env.AGENT_MAX_BODY_BYTES,
      DEFAULT_MAX_BODY_BYTES,
    ),
    maxSessions: parsePositiveInt(env.AGENT_MAX_SESSIONS, DEFAULT_MAX_SESSIONS),
    sessionIdleMs: parsePositiveInt(
      env.AGENT_SESSION_IDLE_MS,
      DEFAULT_SESSION_IDLE_MS,
    ),
  };
}

function resolveModelProvider(
  env: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string {
  const configured = env.PI_PROVIDER?.trim().toLowerCase();
  if (configured) {
    return configured;
  }

  if (env.PI_MODEL?.startsWith("deepseek") || env.DEEPSEEK_API_KEY) {
    return "deepseek";
  }

  return "openai";
}

export function apiKeyEnvName(providerName: string): string {
  return (
    PROVIDER_API_KEY_ENV[providerName] ??
    `${providerName.toUpperCase().replaceAll("-", "_")}_API_KEY`
  );
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

function parsePositiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function resolveProjectRoot(
  options: LoadConfigOptions,
  env: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string {
  if (options.projectRoot) {
    return resolve(options.projectRoot);
  }

  if (env.PROJECT_ROOT) {
    return resolve(env.PROJECT_ROOT);
  }

  if (options.cwd) {
    return findProjectRootFrom(resolve(options.cwd));
  }

  return findProjectRootFrom(dirname(fileURLToPath(import.meta.url)));
}

function findProjectRootFrom(startDir: string): string {
  let current = startDir;
  for (let depth = 0; depth < 6; depth += 1) {
    const candidate = resolve(current, "skills", DEFAULT_SKILL_NAME, "SKILL.md");
    if (existsSync(candidate)) {
      return current;
    }
    current = resolve(current, "..");
  }

  return resolve(startDir, "..");
}

function loadDotEnv(path: string): Record<string, string> {
  if (!existsSync(path)) {
    return {};
  }

  const values: Record<string, string> = {};
  const content = readFileSync(path, "utf8");
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const normalizedLine = line.startsWith("export ") ? line.slice(7).trim() : line;
    const separator = normalizedLine.indexOf("=");
    if (separator <= 0) {
      continue;
    }

    const key = normalizedLine.slice(0, separator).trim();
    const rawValue = normalizedLine.slice(separator + 1).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      continue;
    }

    values[key] = parseDotEnvValue(rawValue);
  }

  return values;
}

function parseDotEnvValue(value: string): string {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }

  const commentIndex = value.indexOf(" #");
  return commentIndex >= 0 ? value.slice(0, commentIndex).trimEnd() : value;
}

function mergeEnv(
  fileEnv: Record<string, string>,
  processEnv: NodeJS.ProcessEnv | Record<string, string | undefined>,
): Record<string, string | undefined> {
  const merged: Record<string, string | undefined> = { ...fileEnv };
  for (const [key, value] of Object.entries(processEnv)) {
    if (value !== undefined) {
      merged[key] = value;
    }
  }

  return merged;
}
