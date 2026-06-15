import {
  createServer as createHttpServer,
  type IncomingMessage,
  type ServerResponse,
} from "node:http";

import {
  apiKeyEnvName,
  assertSkillExists,
  loadConfig,
  type AgentConfig,
} from "./config.js";

interface ChatResult {
  message: string;
  events: object[];
}

type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "agent_event"; event: object };

type StreamEmit = (event: ChatStreamEvent) => void;

interface CreateServerOptions {
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>;
  cwd?: string;
  projectRoot?: string;
  runChat?: (
    message: string,
    sessionId: string,
    config: AgentConfig,
  ) => Promise<ChatResult> | ChatResult;
  runChatStream?: (
    message: string,
    sessionId: string,
    config: AgentConfig,
    emit: StreamEmit,
  ) => Promise<ChatResult> | ChatResult;
}

class RequestBodyError extends Error {
  constructor(
    message: string,
    readonly statusCode: number,
  ) {
    super(message);
  }
}

export function createServer(options: CreateServerOptions = {}) {
  const config = loadConfig({
    env: options.env,
    cwd: options.cwd,
    projectRoot: options.projectRoot,
  });

  return createHttpServer(async (request, response) => {
    try {
      if (request.method === "OPTIONS") {
        sendEmpty(response, 204, config);
        return;
      }

      if (request.method === "GET" && request.url === "/health") {
        sendJson(response, 200, { status: "ok" }, config);
        return;
      }

      if (
        request.method === "POST" &&
        (request.url === "/agent/chat" || request.url === "/agent/chat/stream")
      ) {
        const stream = request.url === "/agent/chat/stream";
        const authError = chatAuthorizationError(request, config);
        if (authError) {
          sendJson(response, 403, { detail: authError }, config);
          return;
        }

        const body = await readJson(request, config.maxBodyBytes);
        const message = typeof body.message === "string" ? body.message.trim() : "";
        const sessionId =
          typeof body.session_id === "string" && body.session_id
            ? body.session_id
            : "default";

        if (!message) {
          sendJson(response, 400, { detail: "message is required" }, config);
          return;
        }

        assertSkillExists(config);

        if (stream) {
          await handleStreamChat(response, {
            message,
            sessionId,
            config,
            runner: options.runChatStream,
          });
          return;
        }

        if (!config.hasModelCredentials) {
          const apiKeyEnv = apiKeyEnvName(config.modelProvider);
          sendJson(
            response,
            200,
            {
              message:
                `Pi agent is not configured. Set ${apiKeyEnv} in agent/.env or the sidecar environment, then restart the agent service.`,
              session_id: sessionId,
              events: [{ type: "setup_error", missing: apiKeyEnv }],
            },
            config,
          );
          return;
        }

        const runner = options.runChat ?? defaultMissingRunner;
        const result = await runner(message, sessionId, config);
        sendJson(
          response,
          200,
          {
            message: result.message,
            session_id: sessionId,
            events: [skillLoadedEvent(config), ...result.events],
          },
          config,
        );
        return;
      }

      sendJson(response, 404, { detail: "Not found" }, config);
    } catch (error) {
      const statusCode = error instanceof RequestBodyError ? error.statusCode : 500;
      sendJson(
        response,
        statusCode,
        {
          detail: error instanceof Error ? error.message : "Agent sidecar failed",
        },
        config,
      );
    }
  });
}

async function defaultMissingRunner(): Promise<ChatResult> {
  throw new Error("Pi chat runner has not been initialized");
}

async function handleStreamChat(
  response: ServerResponse,
  options: {
    message: string;
    sessionId: string;
    config: AgentConfig;
    runner?: CreateServerOptions["runChatStream"];
  },
): Promise<void> {
  sendStreamHeaders(response, options.config);
  const skillEvent = skillLoadedEvent(options.config);
  writeSse(response, "start", { session_id: options.sessionId });
  writeSse(response, "agent_event", { event: skillEvent });

  if (!options.config.hasModelCredentials) {
    const apiKeyEnv = apiKeyEnvName(options.config.modelProvider);
    const message = `Pi agent is not configured. Set ${apiKeyEnv} in agent/.env or the sidecar environment, then restart the agent service.`;
    const events = [skillEvent, { type: "setup_error", missing: apiKeyEnv }];
    writeSse(response, "agent_event", { event: events[1] });
    writeSse(response, "done", {
      message,
      session_id: options.sessionId,
      events,
    });
    response.end();
    return;
  }

  try {
    const runner = options.runner ?? defaultMissingStreamRunner;
    const result = await runner(
      options.message,
      options.sessionId,
      options.config,
      (event) => {
        writeSse(response, event.type, event.type === "delta" ? { text: event.text } : { event: event.event });
      },
    );
    writeSse(response, "done", {
      message: result.message,
      session_id: options.sessionId,
      events: [skillEvent, ...result.events],
    });
  } catch (error) {
    writeSse(response, "error", {
      detail: error instanceof Error ? error.message : "Agent sidecar failed",
    });
  } finally {
    response.end();
  }
}

function skillLoadedEvent(config: AgentConfig): object {
  return {
    type: "skill_loaded",
    skillName: config.skillName,
    skillPath: config.skillPath,
  };
}

async function defaultMissingStreamRunner(): Promise<ChatResult> {
  throw new Error("Pi chat stream runner has not been initialized");
}

async function readJson(
  request: IncomingMessage,
  maxBodyBytes: number,
): Promise<Record<string, unknown>> {
  const contentLength = Number(request.headers["content-length"] || 0);
  if (contentLength > maxBodyBytes) {
    throw new RequestBodyError(
      `Request body is too large. Limit is ${maxBodyBytes} bytes.`,
      413,
    );
  }

  const chunks: Buffer[] = [];
  let receivedBytes = 0;
  for await (const chunk of request) {
    const buffer = Buffer.from(chunk);
    receivedBytes += buffer.byteLength;
    if (receivedBytes > maxBodyBytes) {
      throw new RequestBodyError(
        `Request body is too large. Limit is ${maxBodyBytes} bytes.`,
        413,
      );
    }
    chunks.push(buffer);
  }

  if (chunks.length === 0) {
    return {};
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new RequestBodyError("Invalid JSON request body", 400);
  }

  if (!isJsonObject(parsed)) {
    throw new RequestBodyError("JSON object request body is required", 400);
  }

  return parsed;
}

function isJsonObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sendJson(
  response: ServerResponse,
  statusCode: number,
  payload: object,
  config: AgentConfig,
): void {
  response.writeHead(statusCode, {
    "Content-Type": "application/json",
    ...corsHeaders(config),
  });
  response.end(JSON.stringify(payload));
}

function sendEmpty(
  response: ServerResponse,
  statusCode: number,
  config: AgentConfig,
): void {
  response.writeHead(statusCode, corsHeaders(config));
  response.end();
}

function sendStreamHeaders(response: ServerResponse, config: AgentConfig): void {
  response.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    ...corsHeaders(config),
  });
}

function writeSse(response: ServerResponse, event: string, payload: object): void {
  response.write(`event: ${event}\n`);
  response.write(`data: ${JSON.stringify(payload)}\n\n`);
}

function corsHeaders(config: AgentConfig): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": config.corsOrigin,
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
  };
}

function chatAuthorizationError(
  request: IncomingMessage,
  config: AgentConfig,
): string | undefined {
  if (!isLocalHost(config.host) && !config.agentToken) {
    return "AGENT_TOKEN is required when AGENT_HOST is not local.";
  }

  if (!config.agentToken) {
    return undefined;
  }

  const authorization = request.headers.authorization;
  if (authorization !== `Bearer ${config.agentToken}`) {
    return "Authorization: Bearer token is required for /agent/chat.";
  }

  return undefined;
}

function isLocalHost(host: string): boolean {
  const normalized = host.toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
}
