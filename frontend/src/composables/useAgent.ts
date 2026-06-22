/**
 * Agent console state, streaming, session management, and SSE parsing.
 *
 * All refs are module-level for direct function access.
 * Circular import with useSettings is resolved lazily at call time.
 */
import { computed, ref } from "vue";
import { apiBase, request } from "@/api";
import { setNotice, confirmDanger } from "@/composables/useNotifications";
import { parseMarkdown } from "@/markdown";
import {
  splitAgentProcessHistory,
  countAgentHistoryItems,
  type AgentProcessItem,
} from "@/agentProcess";
import {
  loadAgentSessionState,
  createNextAgentSession,
  activateAgentSession,
  renameAgentSession,
  deleteAgentSession,
  saveAgentSessionId,
  type AgentSessionRecord,
  type AgentSessionState,
} from "@/agentSession";

// ── Interfaces ────────────────────────────────────────

export interface AgentEvent {
  type?: string;
  toolName?: string;
  tool_name?: string;
  name?: string;
  [key: string]: unknown;
}

export interface AgentChatResponse {
  message: string;
  session_id: string;
  events: AgentEvent[];
}

export interface AgentConfigResponse {
  provider_name: string;
  model_name: string;
  api_base_url: string;
  backend_base_url: string;
  api_key_preview: string;
  restart_required: boolean;
}

// ── Agent state ───────────────────────────────────────

export const agentPrompt = ref(
  "帮我找 SkyWalker TKA 在印度的渠道商，优先找骨科植入物、关节置换、TKA 分销商，要求公开邮箱和来源证据。",
);
export const agentResponse = ref("");
export const agentSessionId = ref("default");
export const agentSessions = ref<AgentSessionRecord[]>([]);
export const agentEvents = ref<AgentEvent[]>([]);
export const agentProcessItems = ref<AgentProcessItem[]>([]);
export const agentLoading = ref(false);
export const agentError = ref("");
export const agentConfig = ref<AgentConfigResponse | null>(null);
export const agentApiKeyInput = ref("");
export const agentProviderName = ref("deepseek");
export const agentModelName = ref("deepseek-v4-pro");
export const agentBackendBaseUrl = ref("http://localhost:8000");
export const agentApiBaseUrl = ref("");
export const agentConfigLoading = ref(false);
export const agentConfigSaving = ref(false);
export const agentConfigTesting = ref(false);
export const agentTestResult = ref<null | {
  ok: boolean;
  latency_ms: number;
  message: string;
  error?: string;
}>(null);
export const agentConfigError = ref("");
export const agentConfigNotice = ref("");

// Agent UI toggles
export const editingSessionId = ref("");
export const editingSessionTitle = ref("");
export const agentConfigExpanded = ref(false);
export const agentSettingsOpen = ref(false);
export const agentSkillDetailsOpen = ref(false);
export const agentLogsOpen = ref(false);
export const agentReportFullscreen = ref(false);
export const agentSessionSearch = ref("");
export let agentProcessId = 0;
export let agentGenerationStarted = false;

// ── Computed ──────────────────────────────────────────

export const agentProcessDisplay = computed(() =>
  splitAgentProcessHistory(agentProcessItems.value),
);
export const currentAgentProcessItem = computed(
  () => agentProcessDisplay.value.current,
);
export const historicalAgentProcessItems = computed(
  () => agentProcessDisplay.value.history,
);
export const historicalAgentStatusItems = computed(() =>
  historicalAgentProcessItems.value.filter((item) => item.kind !== "event"),
);
export const agentHistoryCount = computed(() =>
  countAgentHistoryItems(historicalAgentStatusItems.value, agentEvents.value),
);
export const agentMarkdownBlocks = computed(() =>
  parseMarkdown(agentResponse.value),
);
export const activeAgentSession = computed(() =>
  agentSessions.value.find((s) => s.id === agentSessionId.value),
);
export const filteredAgentSessions = computed(() => {
  const keyword = agentSessionSearch.value.trim().toLowerCase();
  if (!keyword) return agentSessions.value;
  return agentSessions.value.filter((s) =>
    [s.title, s.id, shortAgentSessionId(s.id)].some((v) =>
      v.toLowerCase().includes(keyword),
    ),
  );
});
export const agentOutputText = computed(() => {
  const blocks = [
    agentError.value ? `Agent 请求失败\n${agentError.value}` : "",
    agentResponse.value,
  ].filter(Boolean);
  return blocks.join("\n\n").trim();
});
export const agentLogRows = computed(() => {
  const items: Array<{
    kind: string;
    time: string;
    label: string;
    detail: string;
  }> = [];
  for (const pi of agentProcessItems.value) {
    items.push({
      kind: "process",
      time: pi.time || "",
      label: pi.label || pi.kind || "",
      detail: pi.detail || "",
    });
  }
  for (const ev of agentEvents.value) {
    const name = ev.type || ev.toolName || ev.tool_name || ev.name || "事件";
    items.push({
      kind: "event",
      time: "",
      label: formatAgentEvent(ev),
      detail: "",
    });
  }
  return items.slice(-60).reverse();
});
export const agentNotificationItems = computed(() => [
  {
    label: "模型连接",
    detail: `${agentProviderName.value} / ${agentModelName.value}`,
  },
  {
    label: "Skill",
    detail: "overseas-distributor-prospecting",
  },
  {
    label: "会话持久化",
    detail: agentSessions.value.length
      ? `${agentSessions.value.length} 个会话`
      : "无持久化会话",
  },
]);

// ── Agent config ──────────────────────────────────────

export function applyAgentConfig(config: AgentConfigResponse): void {
  agentConfig.value = config;
  agentProviderName.value = config.provider_name;
  agentModelName.value = config.model_name;
  agentApiBaseUrl.value = config.api_base_url || "";
  agentBackendBaseUrl.value = config.backend_base_url;
}

export async function loadAgentConfig(): Promise<void> {
  agentConfigLoading.value = true;
  agentConfigError.value = "";
  try {
    applyAgentConfig(await request<AgentConfigResponse>("/agent/config"));
  } catch (caught) {
    agentConfigError.value =
      caught instanceof Error ? caught.message : "Agent 配置读取失败";
  } finally {
    agentConfigLoading.value = false;
  }
}

export async function saveAgentConfig(): Promise<void> {
  if (agentConfigSaving.value) return;
  agentConfigSaving.value = true;
  agentConfigError.value = "";
  agentConfigNotice.value = "";
  try {
    const payload = await request<AgentConfigResponse>("/agent/config", {
      method: "PUT",
      body: JSON.stringify({
        provider_name: agentProviderName.value.trim() || undefined,
        api_key: agentApiKeyInput.value.trim() || undefined,
        model_name: agentModelName.value.trim() || undefined,
        api_base_url: agentApiBaseUrl.value.trim() || undefined,
        backend_base_url: agentBackendBaseUrl.value.trim() || undefined,
      }),
    });
    applyAgentConfig(payload);
    agentApiKeyInput.value = "";
    agentConfigNotice.value = payload.restart_required
      ? "配置已保存，重启 Agent sidecar 后生效"
      : "配置已保存";
  } catch (caught) {
    agentConfigError.value =
      caught instanceof Error ? caught.message : "Agent 配置保存失败";
  } finally {
    agentConfigSaving.value = false;
  }
}

export async function testAgentConnection(): Promise<void> {
  if (agentConfigTesting.value) return;
  agentConfigTesting.value = true;
  agentTestResult.value = null;
  agentConfigError.value = "";
  try {
    // Lazy import to avoid circular dependency with useSettings
    const { settingsAgentKeyInput } = await import(
      "@/composables/useSettings"
    );
    const apiKey =
      agentApiKeyInput.value.trim() || settingsAgentKeyInput.value.trim();
    if (!apiKey) {
      agentTestResult.value = {
        ok: false,
        latency_ms: 0,
        message: "请先输入 API Key",
        error: "未提供 API Key",
      };
      return;
    }
    const start = performance.now();
    const resp = await fetch(`${apiBase}/agent/test-connection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const latency = Math.round(performance.now() - start);
    const body = (await resp.json()) as {
      ok: boolean;
      message: string;
      error?: string;
    };
    agentTestResult.value = { ...body, latency_ms: latency };
  } catch (caught) {
    agentTestResult.value = {
      ok: false,
      latency_ms: 0,
      message: "连接测试失败",
      error: caught instanceof Error ? caught.message : "未知错误",
    };
  } finally {
    agentConfigTesting.value = false;
  }
}

// ── Streaming ─────────────────────────────────────────

export function clearAgentOutput(): void {
  agentError.value = "";
  agentResponse.value = "";
  agentEvents.value = [];
  agentProcessItems.value = [];
  agentReportFullscreen.value = false;
  agentGenerationStarted = false;
}

export function appendAgentProcess(
  kind: string,
  label: string,
  detail?: string,
): void {
  agentProcessItems.value = [
    ...agentProcessItems.value.slice(-39),
    {
      kind,
      label,
      detail: detail || "",
      time: new Date().toISOString(),
    } as AgentProcessItem,
  ];
}

export function consumeAgentStreamBuffer(buffer: string): string {
  const frames = buffer.split("\n\n");
  if (frames.length <= 1) return buffer;
  for (let i = 0; i < frames.length - 1; i++) {
    const frame = frames[i].trim();
    if (frame) handleAgentSseFrame(frame);
  }
  return frames[frames.length - 1];
}

export function handleAgentSseFrame(frame: string): void {
  const lines = frame.split("\n");
  let eventName = "message";
  let data = "";
  for (const line of lines) {
    if (line.startsWith("event: ")) {
      eventName = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      data = line.slice(6);
    }
  }
  if (data) handleAgentStreamEvent(eventName, data);
}

export function handleAgentStreamEvent(
  eventName: string,
  rawPayload: string,
): void {
  let payload: Record<string, unknown> = {};
  try {
    payload = JSON.parse(rawPayload) as Record<string, unknown>;
  } catch {
    payload = { text: rawPayload };
  }

  switch (eventName) {
    case "start": {
      const sid =
        (payload.session_id as string) || agentSessionId.value || "default";
      if (sid !== agentSessionId.value) {
        applyIncomingAgentSession(sid);
      }
      appendAgentProcess("running", "Agent 开始", `Session ${sid}`);
      break;
    }
    case "delta": {
      if (!agentGenerationStarted) {
        agentGenerationStarted = true;
        appendAgentProcess("running", "模型输出", "开始接收增量输出");
      }
      const text = (payload.text || payload.content || "") as string;
      agentResponse.value += text;
      break;
    }
    case "agent_event": {
      const ev = asAgentEvent(payload);
      agentEvents.value = [...agentEvents.value.slice(-99), ev];
      appendAgentProcess("event", formatAgentEvent(ev));
      break;
    }
    case "done": {
      appendAgentProcess("done", "Agent 完成", (payload.message as string) || "任务完成");
      if (payload.session_id) {
        applyIncomingAgentSession(payload.session_id as string);
      }
      break;
    }
    case "error": {
      agentError.value = (payload.message || payload.error || "未知错误") as string;
      appendAgentProcess("error", "Agent 错误", agentError.value);
      break;
    }
  }
}

export function asAgentEvent(value: Record<string, unknown>): AgentEvent {
  return {
    type: value.type as string | undefined,
    toolName: value.toolName as string | undefined,
    tool_name: value.tool_name as string | undefined,
    name: value.name as string | undefined,
    ...value,
  };
}

export function formatAgentEvent(event: AgentEvent): string {
  const name =
    event.type || event.toolName || event.tool_name || event.name || "事件";
  return `${name}`;
}

export async function sendAgentPrompt(): Promise<void> {
  const message = agentPrompt.value.trim();
  if (!message || agentLoading.value) return;
  agentLoading.value = true;
  clearAgentOutput();
  setNotice("");
  appendAgentProcess(
    "running",
    "连接 Agent",
    `Session ${agentSessionId.value || "default"}`,
  );
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    // Auth token is handled by @/api request wrapper, but streaming
    // uses raw fetch so we read from useAuth lazily
    const { useAuth } = await import("@/composables/useAuth");
    const { authToken } = useAuth();
    if (authToken.value) {
      headers["Authorization"] = `Bearer ${authToken.value}`;
    }
    const response = await fetch(`${apiBase}/agent/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        message,
        session_id: agentSessionId.value || undefined,
      }),
    });

    if (!response.ok) {
      throw new Error(await response.text());
    }
    if (!response.body) {
      throw new Error("当前浏览器不支持流式响应");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer = consumeAgentStreamBuffer(
        buffer + decoder.decode(value, { stream: true }),
      );
    }
    buffer = consumeAgentStreamBuffer(buffer + decoder.decode());
    if (buffer.trim()) {
      handleAgentSseFrame(buffer);
    }
    // Reload dashboard data after agent completes
    const { loadDashboard } = await import("@/composables/useLeads");
    await loadDashboard();
  } catch (caught) {
    agentError.value =
      caught instanceof Error ? caught.message : "Agent 请求失败";
    appendAgentProcess("error", "Agent 请求失败", agentError.value);
  } finally {
    agentLoading.value = false;
  }
}

// ── Session management ────────────────────────────────

export function getAgentStorage(): Storage | undefined {
  try {
    return globalThis.localStorage || undefined;
  } catch {
    return undefined;
  }
}

export function shortAgentSessionId(sessionId: string): string {
  return sessionId.slice(0, 8);
}

export function formatTime(iso?: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return iso;
  }
}

export function formatAgentSessionTime(timestamp: string | number): string {
  try {
    return new Date(timestamp).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(timestamp);
  }
}

export function applyAgentSessionState(state: AgentSessionState): void {
  agentSessionId.value = state.activeId;
  agentSessions.value = state.sessions;
}

export function currentAgentSessionState(): AgentSessionState {
  return { activeId: agentSessionId.value, sessions: agentSessions.value };
}

export function applyIncomingAgentSession(sessionId: string): void {
  const storage = getAgentStorage();
  saveAgentSessionId(storage, sessionId);
  applyAgentSessionState(loadAgentSessionState(storage));
}

export function startNewAgentSession(): void {
  if (agentLoading.value) return;
  applyAgentSessionState(
    createNextAgentSession(getAgentStorage(), currentAgentSessionState()),
  );
  clearAgentOutput();
  setNotice("已创建新的 Agent 会话");
}

export function switchAgentSession(sessionId: string): void {
  if (agentLoading.value || sessionId === agentSessionId.value) return;
  applyAgentSessionState(
    activateAgentSession(
      getAgentStorage(),
      currentAgentSessionState(),
      sessionId,
    ),
  );
  clearAgentOutput();
  setNotice("已切换 Agent 会话");
}

export function beginEditAgentSession(session: AgentSessionRecord): void {
  editingSessionId.value = session.id;
  editingSessionTitle.value = session.title;
}

export function cancelEditAgentSession(): void {
  editingSessionId.value = "";
  editingSessionTitle.value = "";
}

export function saveAgentSessionTitle(sessionId: string): void {
  applyAgentSessionState(
    renameAgentSession(
      getAgentStorage(),
      currentAgentSessionState(),
      sessionId,
      editingSessionTitle.value,
    ),
  );
  cancelEditAgentSession();
}

export async function removeAgentSession(sessionId: string): Promise<void> {
  if (agentLoading.value) return;
  const session = agentSessions.value.find((s) => s.id === sessionId);
  const title = session?.title || "当前会话";
  const confirmed = await confirmDanger({
    title: `删除会话「${title}」？`,
    content: "本地保存的会话历史和过程记录会一并清除，发送给 Agent 的请求不受影响。",
    positiveText: "删除",
  });
  if (!confirmed) return;
  const wasActive = agentSessionId.value === sessionId;
  applyAgentSessionState(
    deleteAgentSession(getAgentStorage(), currentAgentSessionState(), sessionId),
  );
  if (wasActive) clearAgentOutput();
  setNotice("已删除 Agent 会话");
}

// ── Toggle helpers ────────────────────────────────────

export function toggleAgentSettings(): void {
  agentSettingsOpen.value = !agentSettingsOpen.value;
  if (agentSettingsOpen.value) agentConfigExpanded.value = true;
}

export function toggleAgentSkillDetails(): void {
  agentSkillDetailsOpen.value = !agentSkillDetailsOpen.value;
}

export function toggleAgentLogs(): void {
  agentLogsOpen.value = !agentLogsOpen.value;
}

export function toggleAgentReportFullscreen(): void {
  if (!agentOutputText.value) {
    setNotice("暂无 Agent 输出可全屏查看");
    return;
  }
  agentReportFullscreen.value = !agentReportFullscreen.value;
}

// ── Clipboard helpers (agent-specific) ────────────────

export async function copyAgentOutput(): Promise<void> {
  if (!agentOutputText.value) {
    setNotice("暂无 Agent 输出可复制");
    return;
  }
  const { copyTextToClipboard } = await import("@/composables/useAuth");
  await copyTextToClipboard(agentOutputText.value, "Agent 输出已复制");
}

export function downloadAgentOutput(): void {
  if (!agentOutputText.value) {
    setNotice("暂无 Agent 输出可导出");
    return;
  }
  const documentRef = globalThis.document;
  const urlApi = globalThis.URL;
  if (!documentRef || !urlApi?.createObjectURL) {
    setNotice("当前环境不支持文件导出");
    return;
  }
  const filenameDate = new Date().toISOString().slice(0, 10);
  const blob = new Blob([agentOutputText.value], {
    type: "text/markdown;charset=utf-8",
  });
  const objectUrl = urlApi.createObjectURL(blob);
  const anchor = documentRef.createElement("a");
  anchor.href = objectUrl;
  anchor.download = `agent-output-${shortAgentSessionId(agentSessionId.value)}-${filenameDate}.md`;
  documentRef.body.append(anchor);
  anchor.click();
  anchor.remove();
  urlApi.revokeObjectURL(objectUrl);
  setNotice("Agent 输出已导出为 Markdown");
}

export async function copyAgentSessionId(): Promise<void> {
  const { copyTextToClipboard } = await import("@/composables/useAuth");
  await copyTextToClipboard(agentSessionId.value, "会话 ID 已复制");
}

// Re-export for App.vue onMounted
export { loadAgentSessionState } from "@/agentSession";

// ── Aggregator ────────────────────────────────────────

export function useAgent() {
  return {
    // Re-export from agentSession for convenience
    loadAgentSessionState,
    // State
    agentPrompt,
    agentResponse,
    agentSessionId,
    agentSessions,
    agentEvents,
    agentProcessItems,
    agentLoading,
    agentError,
    agentConfig,
    agentApiKeyInput,
    agentProviderName,
    agentModelName,
    agentBackendBaseUrl,
    agentApiBaseUrl,
    agentConfigLoading,
    agentConfigSaving,
    agentConfigTesting,
    agentTestResult,
    agentConfigError,
    agentConfigNotice,
    editingSessionId,
    editingSessionTitle,
    agentConfigExpanded,
    agentSettingsOpen,
    agentSkillDetailsOpen,
    agentLogsOpen,
    agentReportFullscreen,
    agentSessionSearch,
    agentProcessId,
    agentGenerationStarted,
    // Computed
    agentProcessDisplay,
    currentAgentProcessItem,
    historicalAgentProcessItems,
    historicalAgentStatusItems,
    agentHistoryCount,
    agentMarkdownBlocks,
    activeAgentSession,
    filteredAgentSessions,
    agentOutputText,
    agentLogRows,
    agentNotificationItems,
    // Functions
    applyAgentConfig,
    loadAgentConfig,
    saveAgentConfig,
    testAgentConnection,
    clearAgentOutput,
    appendAgentProcess,
    consumeAgentStreamBuffer,
    handleAgentSseFrame,
    handleAgentStreamEvent,
    asAgentEvent,
    formatAgentEvent,
    sendAgentPrompt,
    getAgentStorage,
    shortAgentSessionId,
    formatTime,
    formatAgentSessionTime,
    applyAgentSessionState,
    currentAgentSessionState,
    applyIncomingAgentSession,
    startNewAgentSession,
    switchAgentSession,
    beginEditAgentSession,
    cancelEditAgentSession,
    saveAgentSessionTitle,
    removeAgentSession,
    toggleAgentSettings,
    toggleAgentSkillDetails,
    toggleAgentLogs,
    toggleAgentReportFullscreen,
    copyAgentOutput,
    downloadAgentOutput,
    copyAgentSessionId,
  };
}
