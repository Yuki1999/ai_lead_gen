import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import assert from "node:assert/strict";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { describe, it } from "node:test";

import { loadConfig } from "../src/config.js";

describe("loadConfig", () => {
  it("resolves the project skill path", () => {
    const config = loadConfig({
      env: emptyEnv(),
      cwd: process.cwd(),
    });

    assert.equal(config.port, 8011);
    assert.equal(config.host, "127.0.0.1");
    assert.equal(config.maxSessions, 20);
    assert.equal(config.sessionIdleMs, 30 * 60 * 1000);
    assert.equal(config.projectRoot, resolve(process.cwd(), ".."));
    assert.equal(config.skillName, "overseas-distributor-prospecting");
    assert.match(
      config.skillPath,
      /skills\/overseas-distributor-prospecting\/SKILL\.md$/,
    );
  });

  it("uses PROJECT_ROOT to resolve the default skill path", () => {
    const projectRoot = resolve(process.cwd(), "..");
    const config = loadConfig({
      env: emptyEnv({ PROJECT_ROOT: projectRoot }),
      cwd: "/tmp/not-the-project",
    });

    assert.equal(
      config.skillPath,
      resolve(
        projectRoot,
        "skills",
        "overseas-distributor-prospecting",
        "SKILL.md",
      ),
    );
  });

  it("points to the overseas distributor prospecting skill", () => {
    const config = loadConfig({ env: emptyEnv(), cwd: process.cwd() });
    const skill = readFileSync(config.skillPath, "utf8");

    assert.match(skill, /name:\s*overseas-distributor-prospecting/);
    assert.match(skill, /SkyWalker/);
  });

  it("loads sidecar settings from agent/.env under the project root", () => {
    const projectRoot = mkdtempSync(resolve(tmpdir(), "medbot-agent-config-"));
    mkdirSync(resolve(projectRoot, "agent"));
    writeFileSync(
      resolve(projectRoot, "agent", ".env"),
      [
        "OPENAI_API_KEY=file-key",
        "AGENT_PORT=9123",
        "AGENT_HOST=0.0.0.0",
        "BACKEND_BASE_URL=http://backend.example.test/",
        "AGENT_TOKEN=file-token",
        "AGENT_MAX_SESSIONS=7",
        "AGENT_SESSION_IDLE_MS=5000",
      ].join("\n"),
    );

    const config = loadConfig({ env: {}, projectRoot });

    assert.equal(config.modelProvider, "openai");
    assert.equal(config.apiKey, "file-key");
    assert.equal(config.openaiApiKey, "file-key");
    assert.equal(config.hasModelCredentials, true);
    assert.equal(config.port, 9123);
    assert.equal(config.host, "0.0.0.0");
    assert.equal(config.backendBaseUrl, "http://backend.example.test");
    assert.equal(config.agentToken, "file-token");
    assert.equal(config.maxSessions, 7);
    assert.equal(config.sessionIdleMs, 5000);
  });

  it("lets process environment values override agent/.env values", () => {
    const projectRoot = mkdtempSync(resolve(tmpdir(), "medbot-agent-config-"));
    mkdirSync(resolve(projectRoot, "agent"));
    writeFileSync(
      resolve(projectRoot, "agent", ".env"),
      ["OPENAI_API_KEY=file-key", "AGENT_PORT=9123"].join("\n"),
    );

    const config = loadConfig({
      env: emptyEnv({ OPENAI_API_KEY: "env-key", AGENT_PORT: "8123" }),
      projectRoot,
    });

    assert.equal(config.openaiApiKey, "env-key");
    assert.equal(config.port, 8123);
  });

  it("loads DeepSeek provider settings from agent/.env", () => {
    const projectRoot = mkdtempSync(resolve(tmpdir(), "medbot-agent-config-"));
    mkdirSync(resolve(projectRoot, "agent"));
    writeFileSync(
      resolve(projectRoot, "agent", ".env"),
      [
        "PI_PROVIDER=deepseek",
        "DEEPSEEK_API_KEY=deepseek-key",
        "PI_MODEL=deepseek-v4-pro",
      ].join("\n"),
    );

    const config = loadConfig({ env: {}, projectRoot });

    assert.equal(config.modelProvider, "deepseek");
    assert.equal(config.apiKey, "deepseek-key");
    assert.equal(config.openaiApiKey, undefined);
    assert.equal(config.modelName, "deepseek-v4-pro");
    assert.equal(config.hasModelCredentials, true);
  });
});

function emptyEnv(
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
