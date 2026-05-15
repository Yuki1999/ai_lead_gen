<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  AlertTriangle,
  Bell,
  Bot,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Database,
  ExternalLink,
  FileText,
  Globe2,
  Home,
  MailCheck,
  Maximize2,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  UserCheck,
  X,
} from "lucide-vue-next";
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NConfigProvider,
  NEmpty,
  NGlobalStyle,
  NIcon,
  NInput,
  NInputNumber,
  NSelect,
  NTag,
  type SelectOption,
} from "naive-ui";
import {
  countAgentHistoryItems,
  splitAgentProcessHistory,
  type AgentProcessItem,
} from "./agentProcess";
import {
  activateAgentSession,
  createNextAgentSession,
  deleteAgentSession,
  loadAgentSessionState,
  renameAgentSession,
  saveAgentSessionId,
  type AgentSessionRecord,
  type AgentSessionState,
} from "./agentSession";
import MarkdownRenderer from "./components/MarkdownRenderer.vue";
import { parseMarkdown } from "./markdown";

interface Lead {
  id: number;
  company_name: string;
  region: string;
  country: string;
  website: string;
  contact_name: string;
  email: string;
  category: string;
  match_reason: string;
  source: string;
  score: number;
  status: string;
  notes: string;
}

interface Metrics {
  total_leads: number;
  interested_leads: number;
  sent_emails: number;
  human_review: number;
}

interface SearchResponse {
  created_count: number;
  leads: Lead[];
}

interface LeadListResponse {
  total: number;
  leads: Lead[];
}

interface EmailEvent {
  id: number;
  lead_id: number;
  subject: string;
  body: string;
  sent_to: string;
  region: string;
  status: string;
}

interface SendResponse {
  sent_count: number;
  events: EmailEvent[];
}

interface ReplyAnalysis {
  id: number;
  intent: string;
  confidence: number;
  summary: string;
  next_action: string;
  requires_human: boolean;
}

interface ProductProfile {
  product_name: string;
  procedure: string;
  summary: string;
  search_keywords: string[];
  value_points: string[];
  source_files: string[];
  video_assets: Array<{ filename: string; size_mb: number }>;
}

interface SourcePreview {
  url: string;
  title: string;
  text: string;
  email: string;
  emails: string[];
  email_found: boolean;
}

interface HighlightChunk {
  text: string;
  highlight: boolean;
}

interface AgentEvent {
  type?: string;
  toolName?: string;
  tool_name?: string;
  name?: string;
  [key: string]: unknown;
}

interface AgentChatResponse {
  message: string;
  session_id: string;
  events: AgentEvent[];
}

interface AgentConfigResponse {
  provider_name: string;
  has_api_key: boolean;
  api_key_preview: string | null;
  has_openai_api_key: boolean;
  openai_api_key_preview: string | null;
  model_name: string;
  backend_base_url: string;
  agent_env_path: string;
  restart_required: boolean;
}

const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const naiveThemeOverrides = {
  common: {
    primaryColor: "#2563EB",
    primaryColorHover: "#1D4ED8",
    primaryColorPressed: "#1E40AF",
    primaryColorSuppl: "#2563EB",
    borderRadius: "8px",
    borderRadiusSmall: "6px",
    fontFamily:
      'Inter, "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
};
const statusFilterOptions: SelectOption[] = [
  { label: "全部", value: "" },
  { label: "新线索", value: "new" },
  { label: "已邮件", value: "emailed" },
  { label: "有兴趣", value: "interested" },
  { label: "转人工", value: "human_review" },
  { label: "已确认", value: "qualified" },
  { label: "拒绝", value: "rejected" },
];
const providerOptions: SelectOption[] = [
  { label: "OpenAI", value: "openai" },
  { label: "DeepSeek", value: "deepseek" },
];

const leads = ref<Lead[]>([]);
const productProfile = ref<ProductProfile | null>(null);
const metrics = ref<Metrics>({
  total_leads: 0,
  interested_leads: 0,
  sent_emails: 0,
  human_review: 0,
});
const selectedLeadIds = ref<number[]>([]);
const targetRegions = ref("Germany, United Arab Emirates, Singapore, Saudi Arabia");
const productKeywords = ref(
  "orthopedic implant distributor, total knee arthroplasty distributor, joint replacement distributor"
);
const maxResults = ref(5);
const requireEmail = ref(true);
const filterRegion = ref("");
const filterStatus = ref("");
const query = ref("");
const replyLeadId = ref<number | "">("");
const replyText = ref(
  "We are interested. Please send product details, certificates, and partner requirements."
);
const lastEmail = ref<EmailEvent | null>(null);
const analysis = ref<ReplyAnalysis | null>(null);
const sourcePreview = ref<SourcePreview | null>(null);
const sourcePreviewLead = ref<Lead | null>(null);
const sourcePreviewLoading = ref(false);
const sourcePreviewError = ref("");
const sourcePreviewMode = ref<"page" | "text">("page");
const loading = ref(false);
const currentAction = ref<"dashboard" | "search" | "outreach" | "reply" | "qualify" | null>(null);
const notice = ref("");
const error = ref("");
const agentPrompt = ref(
  "帮我找 SkyWalker TKA 在印度的渠道商，优先找骨科植入物、关节置换、TKA 分销商，要求公开邮箱和来源证据。"
);
const agentResponse = ref("");
const agentSessionId = ref("default");
const agentSessions = ref<AgentSessionRecord[]>([]);
const agentEvents = ref<AgentEvent[]>([]);
const agentProcessItems = ref<AgentProcessItem[]>([]);
const agentLoading = ref(false);
const agentError = ref("");
const agentConfig = ref<AgentConfigResponse | null>(null);
const agentApiKeyInput = ref("");
const agentProviderName = ref("openai");
const agentModelName = ref("gpt-5-mini");
const agentBackendBaseUrl = ref("http://localhost:8000");
const agentConfigLoading = ref(false);
const agentConfigSaving = ref(false);
const agentConfigError = ref("");
const agentConfigNotice = ref("");
const activePage = ref<"workspace" | "agent">("workspace");
const editingSessionId = ref("");
const editingSessionTitle = ref("");
const agentConfigExpanded = ref(false);
const agentGuideOpen = ref(false);
const agentNotificationsOpen = ref(false);
const sidebarUserMenuOpen = ref(false);
const agentSettingsOpen = ref(false);
const agentSkillDetailsOpen = ref(false);
const agentLogsOpen = ref(false);
const agentReportFullscreen = ref(false);
const agentSessionSearch = ref("");
let agentProcessId = 0;
let agentGenerationStarted = false;

const selectedCount = computed(() => selectedLeadIds.value.length);
const topbarContent = computed(() =>
  activePage.value === "agent"
    ? {
        eyebrow: "Pi / pi-mono Agent",
        title: "渠道拓展 Agent",
        copy: "默认使用 overseas-distributor-prospecting skill，支持实时输出、联网搜索和线索入库。",
      }
    : {
        eyebrow: "微创畅行机器人 · 海外业务",
        title: "海外渠道拓展系统",
        copy: "面向 SkyWalker TKA 的代理商发现、邮箱证据审阅、触达记录和回复处理。",
      },
);
const agentProcessDisplay = computed(() => splitAgentProcessHistory(agentProcessItems.value));
const currentAgentProcessItem = computed(() => agentProcessDisplay.value.current);
const historicalAgentProcessItems = computed(() => agentProcessDisplay.value.history);
const historicalAgentStatusItems = computed(() =>
  historicalAgentProcessItems.value.filter((item) => item.kind !== "event")
);
const agentHistoryCount = computed(() =>
  countAgentHistoryItems(historicalAgentStatusItems.value, agentEvents.value)
);
const agentMarkdownBlocks = computed(() => parseMarkdown(agentResponse.value));
const activeAgentSession = computed(() =>
  agentSessions.value.find((session) => session.id === agentSessionId.value)
);
const filteredAgentSessions = computed(() => {
  const keyword = agentSessionSearch.value.trim().toLowerCase();
  if (!keyword) return agentSessions.value;

  return agentSessions.value.filter((session) =>
    [session.title, session.id, shortAgentSessionId(session.id)].some((value) =>
      value.toLowerCase().includes(keyword),
    ),
  );
});
const agentOutputText = computed(() => {
  const blocks = [
    agentError.value ? `Agent 请求失败\n${agentError.value}` : "",
    agentResponse.value,
  ].filter(Boolean);
  return blocks.join("\n\n").trim();
});
const agentNotificationItems = computed(() => [
  {
    label: "模型连接",
    detail: agentConfig.value?.has_api_key
      ? `${agentProviderName.value} · ${agentModelName.value}`
      : "API Key 未配置",
  },
  {
    label: "默认技能",
    detail: "overseas-distributor-prospecting 已启用",
  },
  {
    label: "会话持久化",
    detail: `${agentSessions.value.length} 个本地会话已保存`,
  },
]);
const agentLogRows = computed(() => {
  const processRows = agentProcessItems.value.map((item) => ({
    id: `process-${item.id}`,
    kind: item.kind,
    title: item.label,
    detail: item.detail || "流程状态",
  }));
  const eventRows = agentEvents.value.map((event, index) => ({
    id: `event-${index}`,
    kind: "event",
    title: formatAgentEvent(event),
    detail: String(event.type || event.toolName || event.tool_name || "tool event"),
  }));
  return [...processRows, ...eventRows].slice(-60).reverse();
});
const selectedLead = computed(() =>
  leads.value.find((lead) => lead.id === Number(replyLeadId.value))
);
const replyLeadOptions = computed<SelectOption[]>(() => [
  { label: "不关联", value: "" },
  ...leads.value.map((lead) => ({ label: lead.company_name, value: lead.id })),
]);
const highlightedSourceText = computed(() => {
  if (!sourcePreview.value) return [] as HighlightChunk[];
  return buildHighlightedChunks(sourcePreview.value.text, sourcePreview.value.email);
});
const highlightedEvidenceExcerpt = computed(() => {
  if (!sourcePreview.value) return [] as HighlightChunk[];
  const email = sourcePreview.value.email;
  const normalized = sourcePreview.value.text.replace(/\s+/g, " ").trim();
  if (!email || !normalized) return buildHighlightedChunks(normalized.slice(0, 420), email);

  const matchIndex = normalized.toLowerCase().indexOf(email.toLowerCase());
  if (matchIndex < 0) return buildHighlightedChunks(normalized.slice(0, 420), email);

  const start = Math.max(0, matchIndex - 170);
  const end = Math.min(normalized.length, matchIndex + email.length + 210);
  const excerpt = `${start > 0 ? "... " : ""}${normalized.slice(start, end)}${
    end < normalized.length ? " ..." : ""
  }`;
  return buildHighlightedChunks(excerpt, email);
});
const sourceHost = computed(() => {
  const source = sourcePreviewLead.value?.source;
  if (!source) return "";
  try {
    return new URL(source).hostname.replace(/^www\./, "");
  } catch {
    return source;
  }
});

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as T;
}

async function loadDashboard(): Promise<void> {
  const params = new URLSearchParams();
  if (filterRegion.value) params.set("region", filterRegion.value);
  if (filterStatus.value) params.set("status", filterStatus.value);
  if (query.value) params.set("q", query.value);

  const [leadPayload, metricPayload] = await Promise.all([
    request<LeadListResponse>(`/leads?${params.toString()}`),
    request<Metrics>("/metrics"),
  ]);

  leads.value = leadPayload.leads;
  metrics.value = metricPayload;
  if (replyLeadId.value === "" && leads.value.length > 0) {
    replyLeadId.value = leads.value[0].id;
  }
}

async function loadProductProfile(): Promise<void> {
  productProfile.value = await request<ProductProfile>("/product/profile");
}

async function loadAgentConfig(): Promise<void> {
  agentConfigLoading.value = true;
  agentConfigError.value = "";
  try {
    applyAgentConfig(await request<AgentConfigResponse>("/agent/config"));
  } catch (caught) {
    agentConfigError.value = caught instanceof Error ? caught.message : "Agent 配置读取失败";
  } finally {
    agentConfigLoading.value = false;
  }
}

async function generateLeads(): Promise<void> {
  await runAction("search", async () => {
    const payload = await request<SearchResponse>("/leads/search", {
      method: "POST",
      body: JSON.stringify({
        target_regions: splitCsv(targetRegions.value),
        product_keywords: splitCsv(productKeywords.value),
        max_results: maxResults.value,
        real_search: true,
        require_email: requireEmail.value,
      }),
    });
    selectedLeadIds.value = payload.leads.map((lead) => lead.id);
    notice.value =
      payload.created_count > 0
        ? `新增 ${payload.created_count} 条真实网页线索`
        : "本轮未发现符合条件的公开邮箱线索";
    await loadDashboard();
  });
}

async function createOutreachRecords(): Promise<void> {
  if (selectedLeadIds.value.length === 0) return;

  await runAction("outreach", async () => {
    const payload = await request<SendResponse>("/campaigns/outreach-records", {
      method: "POST",
      body: JSON.stringify({ lead_ids: selectedLeadIds.value }),
    });
    lastEmail.value = payload.events[payload.events.length - 1] || null;
    notice.value = `已生成 ${payload.sent_count} 条触达记录`;
    await loadDashboard();
  });
}

async function analyzeCurrentReply(): Promise<void> {
  await runAction("reply", async () => {
    analysis.value = await request<ReplyAnalysis>("/replies/analyze", {
      method: "POST",
      body: JSON.stringify({
        lead_id: replyLeadId.value === "" ? null : Number(replyLeadId.value),
        reply_text: replyText.value,
      }),
    });
    notice.value = "回复已完成理解";
    await loadDashboard();
  });
}

async function sendAgentPrompt(): Promise<void> {
  const message = agentPrompt.value.trim();
  if (!message || agentLoading.value) return;

  agentLoading.value = true;
  clearAgentOutput();
  notice.value = "";
  appendAgentProcess("running", "连接 Agent", `Session ${agentSessionId.value || "default"}`);
  try {
    const response = await fetch(`${apiBase}/agent/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
    await loadDashboard();
  } catch (caught) {
    agentError.value = caught instanceof Error ? caught.message : "Agent 请求失败";
    appendAgentProcess("error", "Agent 请求失败", agentError.value);
  } finally {
    agentLoading.value = false;
  }
}

async function saveAgentConfig(): Promise<void> {
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
        backend_base_url: agentBackendBaseUrl.value.trim() || undefined,
      }),
    });
    applyAgentConfig(payload);
    agentApiKeyInput.value = "";
    agentConfigNotice.value = payload.restart_required
      ? "配置已保存，重启 Agent sidecar 后生效"
      : "配置已保存";
  } catch (caught) {
    agentConfigError.value = caught instanceof Error ? caught.message : "Agent 配置保存失败";
  } finally {
    agentConfigSaving.value = false;
  }
}

async function markQualified(leadId: number): Promise<void> {
  await runAction("qualify", async () => {
    await request<Lead>(`/leads/${leadId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "qualified", notes: "人工确认：渠道匹配，进入商务跟进。" }),
    });
    notice.value = "已标记为 qualified";
    await loadDashboard();
  });
}

async function openSourcePreview(lead: Lead): Promise<void> {
  sourcePreviewLead.value = lead;
  sourcePreview.value = null;
  sourcePreviewError.value = "";
  sourcePreviewMode.value = "page";
  sourcePreviewLoading.value = true;
  try {
    const params = new URLSearchParams({ url: lead.source, email: lead.email });
    sourcePreview.value = await request<SourcePreview>(`/sources/preview?${params.toString()}`);
  } catch (caught) {
    sourcePreviewError.value = caught instanceof Error ? caught.message : "来源页面读取失败";
  } finally {
    sourcePreviewLoading.value = false;
  }
}

function closeSourcePreview(): void {
  sourcePreview.value = null;
  sourcePreviewLead.value = null;
  sourcePreviewError.value = "";
  sourcePreviewLoading.value = false;
}

function toggleLead(leadId: number, event: Event): void {
  setLeadSelection(leadId, (event.target as HTMLInputElement).checked);
}

function setLeadSelection(leadId: number, checked: boolean): void {
  if (checked) {
    selectedLeadIds.value = [...new Set([...selectedLeadIds.value, leadId])];
  } else {
    selectedLeadIds.value = selectedLeadIds.value.filter((id) => id !== leadId);
  }
}

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildHighlightedChunks(text: string, email: string): HighlightChunk[] {
  if (!email) return [{ text, highlight: false }];
  const chunks = text.split(new RegExp(`(${escapeRegex(email)})`, "gi"));
  return chunks
    .filter((chunk) => chunk.length > 0)
    .map((chunk) => ({
      text: chunk,
      highlight: chunk.toLowerCase() === email.toLowerCase(),
    }));
}

async function runAction(
  actionName: NonNullable<typeof currentAction.value>,
  action: () => Promise<void>,
): Promise<void> {
  loading.value = true;
  currentAction.value = actionName;
  error.value = "";
  notice.value = "";
  try {
    await action();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "请求失败";
  } finally {
    loading.value = false;
    currentAction.value = null;
  }
}

function formatStatus(status: string): string {
  const labels: Record<string, string> = {
    new: "新线索",
    emailed: "已邮件",
    interested: "有兴趣",
    human_review: "转人工",
    rejected: "拒绝",
    needs_review: "待复核",
    qualified: "已确认",
  };
  return labels[status] || status;
}

function statusClass(status: string): string {
  return `status status-${status.replace("_", "-")}`;
}

function statusTagType(status: string): "default" | "info" | "success" | "warning" | "error" {
  if (["interested", "qualified"].includes(status)) return "success";
  if (["human_review", "needs_review"].includes(status)) return "warning";
  if (status === "rejected") return "error";
  if (status === "emailed") return "info";
  return "default";
}

function applyAgentConfig(config: AgentConfigResponse): void {
  agentConfig.value = config;
  agentProviderName.value = config.provider_name;
  agentModelName.value = config.model_name;
  agentBackendBaseUrl.value = config.backend_base_url;
}

function showPage(page: "workspace" | "agent", sectionId?: string): void {
  activePage.value = page;
  agentGuideOpen.value = false;
  agentNotificationsOpen.value = false;
  sidebarUserMenuOpen.value = false;
  const hash = page === "agent" ? "agent" : sectionId || "overview";
  globalThis.history?.replaceState(null, "", `#${hash}`);
  const targetId = sectionId || (page === "agent" ? "overview" : "");
  if (!targetId) return;
  globalThis.requestAnimationFrame?.(() => {
    globalThis.document?.getElementById(targetId)?.scrollIntoView({ block: "start" });
  });
}

function toggleAgentGuide(): void {
  agentGuideOpen.value = !agentGuideOpen.value;
  if (agentGuideOpen.value) agentNotificationsOpen.value = false;
}

function toggleAgentNotifications(): void {
  agentNotificationsOpen.value = !agentNotificationsOpen.value;
  if (agentNotificationsOpen.value) agentGuideOpen.value = false;
}

function toggleSidebarUserMenu(): void {
  sidebarUserMenuOpen.value = !sidebarUserMenuOpen.value;
}

function toggleAgentSettings(): void {
  agentSettingsOpen.value = !agentSettingsOpen.value;
  if (agentSettingsOpen.value) agentConfigExpanded.value = true;
}

function toggleAgentSkillDetails(): void {
  agentSkillDetailsOpen.value = !agentSkillDetailsOpen.value;
}

function toggleAgentLogs(): void {
  agentLogsOpen.value = !agentLogsOpen.value;
}

function toggleAgentReportFullscreen(): void {
  if (!agentOutputText.value) {
    notice.value = "暂无 Agent 输出可全屏查看";
    return;
  }
  agentReportFullscreen.value = !agentReportFullscreen.value;
}

async function copyAgentOutput(): Promise<void> {
  if (!agentOutputText.value) {
    notice.value = "暂无 Agent 输出可复制";
    return;
  }
  await copyTextToClipboard(agentOutputText.value, "Agent 输出已复制");
}

function downloadAgentOutput(): void {
  if (!agentOutputText.value) {
    notice.value = "暂无 Agent 输出可导出";
    return;
  }

  const documentRef = globalThis.document;
  const urlApi = globalThis.URL;
  if (!documentRef || !urlApi?.createObjectURL) {
    notice.value = "当前环境不支持文件导出";
    return;
  }

  const filenameDate = new Date().toISOString().slice(0, 10);
  const blob = new Blob([agentOutputText.value], { type: "text/markdown;charset=utf-8" });
  const objectUrl = urlApi.createObjectURL(blob);
  const anchor = documentRef.createElement("a");
  anchor.href = objectUrl;
  anchor.download = `agent-output-${shortAgentSessionId(agentSessionId.value)}-${filenameDate}.md`;
  documentRef.body.append(anchor);
  anchor.click();
  anchor.remove();
  urlApi.revokeObjectURL(objectUrl);
  notice.value = "Agent 输出已导出为 Markdown";
}

async function copyAgentSessionId(): Promise<void> {
  await copyTextToClipboard(agentSessionId.value, "会话 ID 已复制");
}

async function copyCurrentPageLink(): Promise<void> {
  const href = globalThis.location?.href || "#agent";
  sidebarUserMenuOpen.value = false;
  await copyTextToClipboard(href, "当前页面链接已复制");
}

function openAgentFromUserMenu(): void {
  sidebarUserMenuOpen.value = false;
  showPage("agent");
}

function refreshDashboardFromUserMenu(): void {
  sidebarUserMenuOpen.value = false;
  void runAction("dashboard", loadDashboard);
}

async function copyTextToClipboard(text: string, successMessage: string): Promise<void> {
  try {
    const clipboard = globalThis.navigator?.clipboard;
    if (clipboard?.writeText) {
      await clipboard.writeText(text);
      notice.value = successMessage;
      return;
    }
  } catch {
    // Fall through to the textarea fallback below.
  }

  notice.value = fallbackCopyText(text) ? successMessage : "复制失败，请手动选择内容";
}

function fallbackCopyText(text: string): boolean {
  const documentRef = globalThis.document;
  if (!documentRef?.body) return false;

  const textarea = documentRef.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  documentRef.body.append(textarea);
  textarea.select();
  try {
    return documentRef.execCommand("copy");
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}

function clearAgentOutput(): void {
  agentError.value = "";
  agentResponse.value = "";
  agentEvents.value = [];
  agentProcessItems.value = [];
  agentReportFullscreen.value = false;
  agentGenerationStarted = false;
}

function startNewAgentSession(): void {
  if (agentLoading.value) return;
  applyAgentSessionState(
    createNextAgentSession(getAgentStorage(), currentAgentSessionState()),
  );
  clearAgentOutput();
  notice.value = "已创建新的 Agent 会话";
}

function switchAgentSession(sessionId: string): void {
  if (agentLoading.value || sessionId === agentSessionId.value) return;
  applyAgentSessionState(
    activateAgentSession(getAgentStorage(), currentAgentSessionState(), sessionId),
  );
  clearAgentOutput();
  notice.value = "已切换 Agent 会话";
}

function beginEditAgentSession(session: AgentSessionRecord): void {
  editingSessionId.value = session.id;
  editingSessionTitle.value = session.title;
}

function cancelEditAgentSession(): void {
  editingSessionId.value = "";
  editingSessionTitle.value = "";
}

function saveAgentSessionTitle(sessionId: string): void {
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

function removeAgentSession(sessionId: string): void {
  if (agentLoading.value) return;
  const session = agentSessions.value.find((item) => item.id === sessionId);
  const title = session?.title || "当前会话";
  const confirmed = globalThis.confirm?.(`删除会话“${title}”？`) ?? true;
  if (!confirmed) return;

  const wasActive = agentSessionId.value === sessionId;
  applyAgentSessionState(
    deleteAgentSession(getAgentStorage(), currentAgentSessionState(), sessionId),
  );
  if (wasActive) clearAgentOutput();
  notice.value = "已删除 Agent 会话";
}

function applyAgentSessionState(state: AgentSessionState): void {
  agentSessionId.value = state.activeId;
  agentSessions.value = state.sessions;
}

function currentAgentSessionState(): AgentSessionState {
  return {
    activeId: agentSessionId.value,
    sessions: agentSessions.value,
  };
}

function applyIncomingAgentSession(sessionId: string): void {
  const storage = getAgentStorage();
  saveAgentSessionId(storage, sessionId);
  applyAgentSessionState(loadAgentSessionState(storage));
}

function shortAgentSessionId(sessionId: string): string {
  return sessionId.replace(/^agent-/, "").slice(0, 18);
}

function formatAgentSessionTime(timestamp: number): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function getAgentStorage(): Storage | undefined {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}

function appendAgentProcess(
  kind: AgentProcessItem["kind"],
  label: string,
  detail?: string,
): void {
  agentProcessItems.value = [
    ...agentProcessItems.value,
    { id: ++agentProcessId, kind, label, detail },
  ].slice(-40);
}

function consumeAgentStreamBuffer(buffer: string): string {
  let remaining = buffer;
  let boundary = remaining.indexOf("\n\n");
  while (boundary >= 0) {
    const frame = remaining.slice(0, boundary);
    if (frame.trim()) {
      handleAgentSseFrame(frame);
    }
    remaining = remaining.slice(boundary + 2);
    boundary = remaining.indexOf("\n\n");
  }
  return remaining;
}

function handleAgentSseFrame(frame: string): void {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) return;

  try {
    handleAgentStreamEvent(eventName, JSON.parse(dataLines.join("\n")));
  } catch (caught) {
    appendAgentProcess(
      "error",
      "流式事件解析失败",
      caught instanceof Error ? caught.message : "Invalid stream frame",
    );
  }
}

function handleAgentStreamEvent(eventName: string, payload: Record<string, unknown>): void {
  if (eventName === "start") {
    if (typeof payload.session_id === "string") {
      applyIncomingAgentSession(payload.session_id);
    }
    appendAgentProcess("running", "会话已开始", `Session ${agentSessionId.value}`);
    return;
  }

  if (eventName === "delta") {
    const text = typeof payload.text === "string" ? payload.text : "";
    if (!agentGenerationStarted) {
      agentGenerationStarted = true;
      appendAgentProcess("running", "模型开始输出");
    }
    agentResponse.value += text;
    return;
  }

  if (eventName === "agent_event") {
    const event = asAgentEvent(payload.event);
    if (!event) return;
    agentEvents.value = [...agentEvents.value, event].slice(-50);
    appendAgentProcess("event", formatAgentEvent(event));
    return;
  }

  if (eventName === "done") {
    if (typeof payload.message === "string" && payload.message) {
      agentResponse.value = payload.message;
    }
    if (typeof payload.session_id === "string") {
      applyIncomingAgentSession(payload.session_id);
    }
    if (Array.isArray(payload.events)) {
      agentEvents.value = payload.events.map((event) => event as AgentEvent).slice(-50);
    }
    appendAgentProcess("done", "Agent 已完成");
    notice.value = "Agent 已返回渠道拓展建议";
    return;
  }

  if (eventName === "error") {
    agentError.value = typeof payload.detail === "string" ? payload.detail : "Agent 流式请求失败";
    appendAgentProcess("error", "Agent 请求失败", agentError.value);
  }
}

function asAgentEvent(value: unknown): AgentEvent | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as AgentEvent)
    : null;
}

function formatAgentEvent(event: AgentEvent): string {
  const type = String(event.type || "event");
  const tool = event.toolName || event.tool_name || event.name;
  const skill = event.skillName || event.skill_name;
  const labels: Record<string, string> = {
    assistant_message_delta: "回复生成",
    setup_error: "配置提示",
    skill_loaded: "Skill 已加载",
    tool_call: "工具调用",
    tool_execution_start: "工具开始",
    tool_execution_update: "工具更新",
    tool_execution_end: "工具完成",
    tool_execution_done: "工具完成",
    tool_execution_error: "工具失败",
  };
  if (skill) {
    return `${labels[type] || type}: ${String(skill)}`;
  }
  return tool ? `${labels[type] || type}: ${String(tool)}` : labels[type] || type;
}

onMounted(() => {
  applyAgentSessionState(loadAgentSessionState(getAgentStorage()));
  if (globalThis.location?.hash === "#agent") {
    activePage.value = "agent";
  }
  void runAction("dashboard", async () => {
    await Promise.all([loadProductProfile(), loadDashboard()]);
  });
  void loadAgentConfig();
});
</script>

<template>
  <n-config-provider :theme-overrides="naiveThemeOverrides">
  <n-global-style />
  <div class="app-shell app-frame">
    <aside class="sidebar" aria-label="系统导航">
      <div class="brand-lockup">
        <div class="brand-mark">SW</div>
        <div>
          <strong>SkyWalker</strong>
          <span>Overseas Prospecting</span>
        </div>
      </div>
      <nav class="side-nav" aria-label="主导航">
        <a
          href="#overview"
          :class="{ active: activePage === 'workspace' }"
          @click.prevent="showPage('workspace', 'overview')"
        >
          <span class="nav-icon"><Home :size="18" aria-hidden="true" /></span>
          概览
        </a>
        <a href="#prospecting-title" @click.prevent="showPage('workspace', 'prospecting-title')">
          <span class="nav-icon"><Search :size="18" aria-hidden="true" /></span>
          获客搜索
        </a>
        <a href="#lead-list-title" @click.prevent="showPage('workspace', 'lead-list-title')">
          <span class="nav-icon"><Database :size="18" aria-hidden="true" /></span>
          线索库
        </a>
        <button type="button" :class="{ active: activePage === 'agent' }" @click="showPage('agent')">
          <span class="nav-icon"><Bot :size="18" aria-hidden="true" /></span>
          Agent
        </button>
        <a href="#reply-title" @click.prevent="showPage('workspace', 'reply-title')">
          <span class="nav-icon"><MailCheck :size="18" aria-hidden="true" /></span>
          外联跟进
        </a>
      </nav>
      <div class="sidebar-footer">
        <div class="sidebar-usage-card">
          <div>
            <strong>本月使用</strong>
            <a href="#overview" @click.prevent="showPage('workspace', 'overview')">查看详情</a>
          </div>
          <span>额度</span>
          <div class="usage-bar"><i></i></div>
          <small>1,250 / 3,000 Credits</small>
          <small>重置于 2026-06-01</small>
        </div>
        <button
          class="sidebar-user-card"
          type="button"
          :aria-expanded="sidebarUserMenuOpen"
          aria-controls="sidebar-user-menu"
          @click="toggleSidebarUserMenu"
        >
          <span class="user-avatar">张</span>
          <div>
            <strong>张明</strong>
            <small>医疗器械 · 管理员</small>
          </div>
          <ChevronDown :size="16" aria-hidden="true" />
        </button>
        <div
          v-if="sidebarUserMenuOpen"
          id="sidebar-user-menu"
          class="sidebar-user-menu"
          role="menu"
          aria-label="用户快捷操作"
        >
          <button type="button" role="menuitem" @click="openAgentFromUserMenu">打开 Agent</button>
          <button type="button" role="menuitem" @click="copyCurrentPageLink">复制当前链接</button>
          <button type="button" role="menuitem" @click="refreshDashboardFromUserMenu">刷新数据</button>
        </div>
      </div>
    </aside>

    <section class="main-workspace workspace-shell">
      <header id="overview" class="topbar workspace-command">
        <div>
          <p :class="['eyebrow', { 'agent-crumb': activePage === 'agent' }]">
            <ChevronDown v-if="activePage === 'agent'" :size="14" aria-hidden="true" />
            <span>{{ topbarContent.eyebrow }}</span>
          </p>
          <h1>{{ topbarContent.title }}</h1>
          <p class="topbar-copy">{{ topbarContent.copy }}</p>
        </div>
        <div class="topbar-actions" :class="{ 'agent-hero-actions': activePage === 'agent' }">
          <template v-if="activePage === 'workspace'">
            <span class="live-badge">
              <ShieldCheck :size="16" aria-hidden="true" />
              生产数据视图
            </span>
            <n-button
              class="ghost-button"
              secondary
              :loading="currentAction === 'dashboard'"
              :disabled="loading"
              @click="runAction('dashboard', loadDashboard)"
            >
              <template #icon>
                <n-icon><RefreshCw /></n-icon>
              </template>
              {{ currentAction === "dashboard" ? "刷新中..." : "刷新数据" }}
            </n-button>
          </template>
          <template v-else>
            <n-button
              class="ghost-button agent-guide-button"
              secondary
              :aria-expanded="agentGuideOpen"
              @click="toggleAgentGuide"
            >
              <template #icon>
                <n-icon><BookOpen /></n-icon>
              </template>
              使用指南
            </n-button>
            <button
              class="notification-button"
              type="button"
              aria-label="通知"
              :aria-expanded="agentNotificationsOpen"
              @click="toggleAgentNotifications"
            >
              <Bell :size="18" aria-hidden="true" />
              <span>{{ agentNotificationItems.length }}</span>
            </button>
            <span class="agent-online-badge">
              <i></i>
              在线
            </span>
          </template>
        </div>
      </header>

      <section
        v-if="activePage === 'agent' && (agentGuideOpen || agentNotificationsOpen)"
        class="agent-topbar-panels"
        aria-live="polite"
      >
        <article v-if="agentGuideOpen" class="agent-guide-panel" aria-label="Agent 使用指南">
          <div class="agent-panel-head">
            <div>
              <p class="panel-label">使用指南</p>
              <strong>渠道拓展任务流</strong>
            </div>
            <button class="icon-only-button" type="button" aria-label="关闭使用指南" @click="toggleAgentGuide">
              <X :size="16" aria-hidden="true" />
            </button>
          </div>
          <ol class="agent-guide-steps">
            <li>在任务框写清产品、国家、渠道类型和证据要求。</li>
            <li>发送后右侧只显示最新执行步骤，历史记录默认折叠。</li>
            <li>输出完成后可复制、导出 Markdown 或全屏审阅。</li>
          </ol>
        </article>

        <article
          v-if="agentNotificationsOpen"
          class="agent-notification-panel"
          aria-label="Agent 通知"
        >
          <div class="agent-panel-head">
            <div>
              <p class="panel-label">通知</p>
              <strong>Agent 状态</strong>
            </div>
            <button class="icon-only-button" type="button" aria-label="关闭通知" @click="toggleAgentNotifications">
              <X :size="16" aria-hidden="true" />
            </button>
          </div>
          <div class="agent-notification-list">
            <article v-for="item in agentNotificationItems" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.detail }}</strong>
            </article>
          </div>
        </article>
      </section>

      <main class="dashboard-grid" :class="{ 'agent-route': activePage === 'agent' }">
        <section
          v-if="activePage === 'workspace'"
          class="tool-panel workspace-ops-panel"
          aria-labelledby="prospecting-title"
        >
          <n-card
            v-if="productProfile"
            class="product-panel product-summary-card"
            aria-label="产品画像"
            :bordered="false"
          >
            <div class="product-heading">
              <span class="product-icon">
                <FileText :size="20" aria-hidden="true" />
              </span>
              <div class="product-title-copy">
                <p class="panel-label">产品画像</p>
                <strong>{{ productProfile.product_name }}</strong>
                <span class="product-procedure">{{ productProfile.procedure }}</span>
              </div>
            </div>
            <p>{{ productProfile.summary }}</p>
            <div class="chip-row">
              <span v-for="point in productProfile.value_points.slice(0, 2)" :key="point">
                {{ point }}
              </span>
            </div>
            <small>
              资料：{{ productProfile.source_files.length }} PDF ·
              {{ productProfile.video_assets.length }} 视频
            </small>
          </n-card>

          <div class="section-title step-title">
            <span class="step-index">1</span>
            <div>
              <h2 id="prospecting-title">获客搜索</h2>
              <p>按地区和关键词扫描公开网页邮箱</p>
            </div>
          </div>

          <label class="field">
            <span>目标地区</span>
            <n-input v-model:value="targetRegions" clearable />
          </label>

          <label class="field">
            <span>搜索关键词</span>
            <n-input v-model:value="productKeywords" clearable />
          </label>

          <div class="field-row">
            <label class="field compact">
              <span>返回数量</span>
              <n-input-number v-model:value="maxResults" :min="1" :max="50" />
            </label>

            <label class="toggle-field">
              <n-checkbox v-model:checked="requireEmail">仅保存已发现邮箱</n-checkbox>
            </label>
          </div>

          <n-button
            class="primary-button"
            type="primary"
            size="large"
            block
            :loading="currentAction === 'search'"
            :disabled="loading"
            @click="generateLeads"
          >
            <template #icon>
              <n-icon><Search /></n-icon>
            </template>
            {{ currentAction === "search" ? "搜索中..." : "实时搜索并入库" }}
          </n-button>

          <div class="section-title step-title offset">
            <span class="step-index">2</span>
            <div>
              <h2>触达记录</h2>
              <p>生成邮件草稿并记录触达动作</p>
            </div>
          </div>

          <n-button
            class="primary-button secondary"
            type="info"
            size="large"
            block
            :loading="currentAction === 'outreach'"
            :disabled="loading || selectedCount === 0"
            @click="createOutreachRecords"
          >
            <template #icon>
              <n-icon><MailCheck /></n-icon>
            </template>
            {{ currentAction === "outreach" ? "生成中..." : "生成触达记录" }}
          </n-button>
          <p class="selection-copy">已选择 {{ selectedCount }} 个邮箱</p>

          <n-card v-if="lastEmail" class="email-preview" aria-label="触达内容预览" :bordered="false">
            <strong>{{ lastEmail.subject }}</strong>
            <span>{{ lastEmail.sent_to }}</span>
            <p>{{ lastEmail.body }}</p>
          </n-card>
        </section>

        <section class="content-area" aria-label="线索和回复工作区">
          <div v-if="activePage === 'workspace'" class="metrics-row summary-strip">
            <article class="metric-card">
              <span class="metric-icon"><Database :size="19" aria-hidden="true" /></span>
              <div>
                <span>线索总数</span>
                <strong>{{ metrics.total_leads }}</strong>
              </div>
            </article>
            <article class="metric-card">
              <span class="metric-icon success"><UserCheck :size="19" aria-hidden="true" /></span>
              <div>
                <span>有兴趣</span>
                <strong>{{ metrics.interested_leads }}</strong>
              </div>
            </article>
            <article class="metric-card">
              <span class="metric-icon blue"><MailCheck :size="19" aria-hidden="true" /></span>
              <div>
                <span>已触达</span>
                <strong>{{ metrics.sent_emails }}</strong>
              </div>
            </article>
            <article class="metric-card warning">
              <span class="metric-icon warning-icon"><AlertTriangle :size="19" aria-hidden="true" /></span>
              <div>
                <span>转人工</span>
                <strong>{{ metrics.human_review }}</strong>
              </div>
            </article>
          </div>

          <div v-if="activePage === 'workspace'" class="pipeline-strip" aria-label="渠道工作流状态">
            <article>
              <span>01</span>
              <div>
                <strong>发现线索</strong>
                <small>公开网页搜索</small>
              </div>
            </article>
            <article>
              <span>02</span>
              <div>
                <strong>审阅证据</strong>
                <small>来源与邮箱位置</small>
              </div>
            </article>
            <article>
              <span>03</span>
              <div>
                <strong>渠道触达</strong>
                <small>邮件草稿与记录</small>
              </div>
            </article>
            <article>
              <span>04</span>
              <div>
                <strong>回复分流</strong>
                <small>意向与转人工</small>
              </div>
            </article>
          </div>

          <section
            v-if="activePage === 'agent'"
            class="agent-panel agent-page-panel agent-console-layout agent-chat-shell agent-design-shell"
            aria-labelledby="agent-title"
          >
            <header class="agent-head">
              <div class="agent-title">
                <span class="agent-icon">
                  <Bot :size="21" aria-hidden="true" />
                </span>
                <div>
                  <p class="panel-label">Pi / pi-mono</p>
                  <h2 id="agent-title">渠道拓展 Agent</h2>
                  <p>默认使用 overseas-distributor-prospecting skill，并通过后台工具写入线索库。</p>
                </div>
              </div>
              <span class="agent-session">
                {{ activeAgentSession?.title || "当前会话" }} · {{ shortAgentSessionId(agentSessionId) }}
              </span>
            </header>

            <section class="agent-session-manager agent-sidebar-panel" aria-label="会话管理">
              <div class="session-manager-head">
                <div>
                  <p class="panel-label">会话管理</p>
                  <strong>{{ agentSessions.length }} 个会话</strong>
                </div>
                <n-button class="ghost-button" secondary :disabled="agentLoading" @click="startNewAgentSession">
                  <template #icon>
                    <n-icon><Plus /></n-icon>
                  </template>
                  新建会话
                </n-button>
              </div>
              <n-input
                v-model:value="agentSessionSearch"
                class="agent-session-search"
                placeholder="搜索会话..."
                clearable
              >
                <template #prefix>
                  <n-icon><Search /></n-icon>
                </template>
              </n-input>

              <div class="session-list" role="list">
                <article
                  v-for="session in filteredAgentSessions"
                  :key="session.id"
                  :class="['session-row', { active: session.id === agentSessionId }]"
                  role="listitem"
                >
                  <form
                    v-if="editingSessionId === session.id"
                    class="session-rename"
                    @submit.prevent="saveAgentSessionTitle(session.id)"
                  >
                    <n-input
                      v-model="editingSessionTitle"
                      aria-label="会话名称"
                      maxlength="80"
                    />
                    <n-button class="icon-only-button" type="primary" circle attr-type="submit" aria-label="保存会话名称">
                      <template #icon>
                        <n-icon><Check /></n-icon>
                      </template>
                    </n-button>
                    <n-button
                      class="icon-only-button"
                      circle
                      aria-label="取消重命名"
                      @click="cancelEditAgentSession"
                    >
                      <template #icon>
                        <n-icon><X /></n-icon>
                      </template>
                    </n-button>
                  </form>

                  <template v-else>
                    <button
                      class="session-select-button"
                      type="button"
                      :disabled="agentLoading"
                      @click="switchAgentSession(session.id)"
                    >
                      <strong>{{ session.title }}</strong>
                      <small>
                        {{ formatAgentSessionTime(session.updatedAt) }} ·
                        {{ shortAgentSessionId(session.id) }}
                      </small>
                    </button>
                    <div class="session-row-actions">
                      <n-button
                        class="icon-only-button"
                        circle
                        :disabled="agentLoading"
                        :aria-label="`重命名 ${session.title}`"
                        @click="beginEditAgentSession(session)"
                      >
                        <template #icon>
                          <n-icon><Pencil /></n-icon>
                        </template>
                      </n-button>
                      <n-button
                        class="icon-only-button danger-action"
                        circle
                        :disabled="agentLoading"
                        :aria-label="`删除 ${session.title}`"
                        @click="removeAgentSession(session.id)"
                      >
                        <template #icon>
                          <n-icon><Trash2 /></n-icon>
                        </template>
                      </n-button>
                    </div>
                  </template>
                </article>
                <div v-if="filteredAgentSessions.length === 0" class="session-empty-state">
                  没有匹配的会话
                </div>
              </div>
              <div class="session-manager-foot">
                共 {{ filteredAgentSessions.length }} / {{ agentSessions.length }} 个会话
              </div>
            </section>

            <section class="agent-main-panel agent-conversation-panel" aria-label="Agent 任务和输出">
              <div class="agent-composer-card agent-compose-surface">
                <div class="agent-composer-heading">
                  <strong>向 Agent 发起任务</strong>
                  <span>{{ agentPrompt.length }} / 2000</span>
                </div>
                <label class="field agent-field">
                  <span>任务指令</span>
                  <n-input
                    v-model:value="agentPrompt"
                    type="textarea"
                    :autosize="{ minRows: 5, maxRows: 10 }"
                  />
                </label>

                <div class="agent-actions">
                  <span class="agent-skill-pill">overseas-distributor-prospecting</span>
                  <div class="agent-action-buttons">
                    <n-button
                      class="icon-only-button agent-tune-button"
                      circle
                      secondary
                      aria-label="高级设置"
                      :aria-expanded="agentSettingsOpen"
                      @click="toggleAgentSettings"
                    >
                      <template #icon>
                        <n-icon><SlidersHorizontal /></n-icon>
                      </template>
                    </n-button>
                    <n-button
                      class="ghost-button"
                      secondary
                      :disabled="agentLoading"
                      @click="startNewAgentSession"
                    >
                      <template #icon>
                        <n-icon><RefreshCw /></n-icon>
                      </template>
                      新建会话
                    </n-button>
                    <n-button
                      class="primary-button"
                      type="primary"
                      size="large"
                      :loading="agentLoading"
                      :disabled="agentLoading || !agentPrompt.trim()"
                      @click="sendAgentPrompt"
                    >
                      <template #icon>
                        <n-icon><Send /></n-icon>
                      </template>
                      {{ agentLoading ? "处理中..." : "发送任务" }}
                    </n-button>
                  </div>
                </div>

                <section
                  v-if="agentSettingsOpen"
                  class="agent-settings-panel"
                  aria-label="Agent 高级设置"
                >
                  <div>
                    <span>Provider</span>
                    <strong>{{ agentProviderName }}</strong>
                  </div>
                  <div>
                    <span>Model</span>
                    <strong>{{ agentModelName }}</strong>
                  </div>
                  <div>
                    <span>Session</span>
                    <strong>{{ shortAgentSessionId(agentSessionId) }}</strong>
                  </div>
                  <n-button class="ghost-button" secondary @click="agentConfigExpanded = true">
                    打开配置管理
                  </n-button>
                  <n-button class="ghost-button" secondary @click="copyAgentSessionId">
                    复制会话 ID
                  </n-button>
                </section>
              </div>

              <div
                v-if="agentResponse || agentError"
                :class="[
                  'agent-output',
                  'agent-report-card',
                  { 'agent-report-fullscreen': agentReportFullscreen },
                ]"
                aria-live="polite"
              >
                <div class="agent-report-head">
                  <div>
                    <strong>Agent 输出</strong>
                    <n-tag
                      :type="agentError ? 'error' : agentLoading ? 'info' : 'success'"
                      size="small"
                      round
                      :bordered="false"
                    >
                      {{ agentError ? "失败" : agentLoading ? "生成中" : "已完成" }}
                    </n-tag>
                  </div>
                  <span>
                    <CheckCircle2 :size="15" aria-hidden="true" />
                    完成于 2026-05-15
                  </span>
                  <div class="report-actions">
                    <button
                      type="button"
                      aria-label="复制"
                      :disabled="!agentOutputText"
                      @click="copyAgentOutput"
                    >
                      <Check :size="15" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      aria-label="导出"
                      :disabled="!agentOutputText"
                      @click="downloadAgentOutput"
                    >
                      <ExternalLink :size="15" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      :aria-label="agentReportFullscreen ? '退出全屏' : '全屏'"
                      :disabled="!agentOutputText"
                      @click="toggleAgentReportFullscreen"
                    >
                      <Maximize2 :size="15" aria-hidden="true" />
                    </button>
                  </div>
                </div>
                <p v-if="agentError" class="error">{{ agentError }}</p>
                <MarkdownRenderer
                  v-if="agentResponse"
                  class="agent-message"
                  :blocks="agentMarkdownBlocks"
                />
              </div>
              <div v-else class="agent-empty-state agent-report-card" aria-live="polite">
                <Bot :size="22" aria-hidden="true" />
                <div>
                  <strong>输入任务后，Agent 会在这里持续输出。</strong>
                  <span>工具调用过程会固定显示在右侧执行轨道中，历史默认折叠。</span>
                </div>
              </div>
            </section>

            <aside class="agent-context-rail agent-side-panel" aria-label="Agent 上下文">
              <section class="agent-config" aria-label="Agent 配置">
                <div class="agent-config-header">
                  <strong>Agent 配置</strong>
                  <span
                    :class="[
                      'status',
                      agentConfig?.has_api_key ? 'status-qualified' : 'status-needs-review',
                    ]"
                  >
                    <i></i>
                    {{ agentConfig?.has_api_key ? "已连接" : "未连接" }}
                  </span>
                </div>

                <dl class="agent-config-summary">
                  <div>
                    <dt>Provider</dt>
                    <dd>{{ agentProviderName }}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>{{ agentModelName }}</dd>
                  </div>
                  <div>
                    <dt>API 状态</dt>
                    <dd>{{ agentConfig?.has_api_key ? "200 OK" : "未配置" }}</dd>
                  </div>
                  <div>
                    <dt>API Key</dt>
                    <dd>{{ agentConfig?.api_key_preview || "未配置" }}</dd>
                  </div>
                </dl>

                <n-button
                  class="ghost-button agent-config-manage-button"
                  secondary
                  :aria-expanded="agentConfigExpanded"
                  @click="agentConfigExpanded = !agentConfigExpanded"
                >
                  <template #icon>
                    <n-icon><SlidersHorizontal /></n-icon>
                  </template>
                  配置管理
                </n-button>

                <div v-if="agentConfigExpanded" class="agent-config-grid">
                  <label class="field">
                    <span>Provider</span>
                    <n-select v-model:value="agentProviderName" :options="providerOptions" />
                  </label>
                  <label class="field">
                    <span>API Key</span>
                    <n-input
                      v-model:value="agentApiKeyInput"
                      autocomplete="off"
                      placeholder="sk-..."
                      type="password"
                      show-password-on="click"
                    />
                  </label>
                  <label class="field">
                    <span>模型</span>
                    <n-input v-model:value="agentModelName" />
                  </label>
                  <label class="field">
                    <span>Backend URL</span>
                    <n-input v-model:value="agentBackendBaseUrl" />
                  </label>
                  <n-button
                    class="ghost-button"
                    secondary
                    :loading="agentConfigSaving"
                    :disabled="agentConfigLoading || agentConfigSaving"
                    @click="saveAgentConfig"
                  >
                    <template #icon>
                      <n-icon><Save /></n-icon>
                    </template>
                    {{ agentConfigSaving ? "保存中..." : "保存配置" }}
                  </n-button>
                </div>

                <p v-if="agentConfigNotice" class="notice">{{ agentConfigNotice }}</p>
                <p v-if="agentConfigError" class="error">{{ agentConfigError }}</p>
              </section>

              <section class="agent-capability-card" aria-label="当前技能">
                <div>
                  <p class="panel-label">当前技能</p>
                  <n-tag type="success" round :bordered="false">
                    overseas-distributor-prospecting
                  </n-tag>
                  <small>海外经销商线索挖掘与分析</small>
                </div>
                <a
                  href="#agent-title"
                  :aria-expanded="agentSkillDetailsOpen"
                  @click.prevent="toggleAgentSkillDetails"
                >
                  详情
                </a>
              </section>

              <section
                v-if="agentSkillDetailsOpen"
                class="agent-skill-detail-panel"
                aria-label="技能详情"
              >
                <div>
                  <span>适用产品</span>
                  <strong>SkyWalker TKA / 骨科手术机器人 / 医疗器械渠道</strong>
                </div>
                <div>
                  <span>默认流程</span>
                  <strong>产品画像、国家市场搜索、线索评分、公开证据汇总</strong>
                </div>
                <div>
                  <span>输出格式</span>
                  <strong>Markdown 报告 + 可入库线索</strong>
                </div>
              </section>

              <section class="agent-execution-rail" aria-label="Agent 实时过程">
                <div class="execution-rail-head">
                  <div>
                    <p class="panel-label">执行过程</p>
                    <strong>{{ currentAgentProcessItem ? "正在执行" : "等待任务" }}</strong>
                  </div>
                  <span>{{ agentHistoryCount }} 历史</span>
                </div>

                <div v-if="currentAgentProcessItem" class="agent-process">
                  <div
                    :class="[
                      'agent-process-item',
                      'agent-process-current',
                      `process-${currentAgentProcessItem.kind}`,
                    ]"
                  >
                    <span aria-hidden="true"></span>
                    <div>
                      <strong>{{ currentAgentProcessItem.label }}</strong>
                      <small v-if="currentAgentProcessItem.detail">{{ currentAgentProcessItem.detail }}</small>
                    </div>
                  </div>
                </div>
                <div v-else class="agent-process-idle">
                  <span aria-hidden="true"></span>
                  <div>
                    <strong>暂无运行中的工具</strong>
                    <small>发送任务后，这里只展示最新一步。</small>
                  </div>
                </div>

                <details v-if="agentHistoryCount > 0" class="agent-history">
                  <summary>
                    <span>历史记录</span>
                    <small>{{ agentHistoryCount }} 条</small>
                  </summary>
                  <div v-if="historicalAgentStatusItems.length > 0" class="agent-history-process">
                    <div
                      v-for="item in historicalAgentStatusItems"
                      :key="item.id"
                      :class="['agent-process-item', `process-${item.kind}`]"
                    >
                      <span aria-hidden="true"></span>
                      <div>
                        <strong>{{ item.label }}</strong>
                        <small v-if="item.detail">{{ item.detail }}</small>
                      </div>
                    </div>
                  </div>
                  <div v-if="agentEvents.length > 0" class="agent-events" aria-label="Agent 工具事件历史">
                    <span v-for="(event, index) in agentEvents" :key="index">
                      {{ formatAgentEvent(event) }}
                    </span>
                  </div>
                </details>
              </section>
              <n-button
                class="agent-log-button"
                secondary
                block
                :aria-expanded="agentLogsOpen"
                @click="toggleAgentLogs"
              >
                <template #icon>
                  <n-icon><Clock3 /></n-icon>
                </template>
                查看完整执行日志
              </n-button>
              <section v-if="agentLogsOpen" class="agent-log-panel" aria-label="完整执行日志">
                <article v-for="row in agentLogRows" :key="row.id" class="agent-log-row">
                  <span>{{ row.title }}</span>
                  <small>{{ row.detail }}</small>
                </article>
                <div v-if="agentLogRows.length === 0" class="agent-log-empty">
                  暂无执行日志
                </div>
              </section>
            </aside>
          </section>

        <div v-if="activePage === 'workspace'" class="toolbar" aria-label="筛选线索">
          <label>
            <span>地区</span>
            <n-input v-model:value="filterRegion" clearable placeholder="Europe" />
          </label>
          <label>
            <span>状态</span>
            <n-select v-model:value="filterStatus" :options="statusFilterOptions" />
          </label>
          <label class="wide">
            <span>关键词</span>
            <n-input v-model:value="query" clearable placeholder="company / email / country" />
          </label>
          <n-button
            class="ghost-button"
            secondary
            :loading="currentAction === 'dashboard'"
            :disabled="loading"
            @click="runAction('dashboard', loadDashboard)"
          >
            <template #icon>
              <n-icon><Search /></n-icon>
            </template>
            {{ currentAction === "dashboard" ? "筛选中..." : "筛选" }}
          </n-button>
        </div>

        <section
          v-if="activePage === 'workspace'"
          class="lead-list modern-data-table lead-intelligence-panel"
          aria-labelledby="lead-list-title"
        >
          <div class="list-head">
            <div>
              <h2 id="lead-list-title">线索数据库</h2>
              <p>公司、邮箱、公开来源证据、评分和管线状态</p>
            </div>
            <span>{{ leads.length }} 条</span>
          </div>

          <n-empty
            v-if="leads.length === 0"
            class="empty-state"
            description="点击左侧“实时搜索并入库”后，结果会显示在这里。"
          >
            <template #icon>
              <n-icon><Globe2 /></n-icon>
            </template>
            <template #extra>
              <strong>暂无线索</strong>
            </template>
          </n-empty>

          <article v-for="lead in leads" :key="lead.id" class="lead-row">
            <label class="select-cell" :aria-label="`选择 ${lead.company_name}`">
              <n-checkbox
                :checked="selectedLeadIds.includes(lead.id)"
                @update:checked="(checked) => setLeadSelection(lead.id, checked)"
              />
            </label>

            <div class="lead-main">
              <div class="lead-title-line">
                <strong>{{ lead.company_name }}</strong>
                <n-tag :type="statusTagType(lead.status)" size="small" round :bordered="false">
                  {{ formatStatus(lead.status) }}
                </n-tag>
              </div>
              <span>{{ lead.country }} · {{ lead.region }} · {{ lead.category }}</span>
              <a :href="lead.website" target="_blank" rel="noreferrer">{{ lead.website }}</a>
            </div>

            <div class="lead-contact">
              <span>公开邮箱</span>
              <a v-if="lead.email" :href="`mailto:${lead.email}`">{{ lead.email }}</a>
              <span v-else class="muted">未发现公开邮箱</span>
            </div>

            <p class="lead-reason">{{ lead.match_reason }}</p>

            <div class="lead-source">
              <span>来源 / 邮箱位置</span>
              <button class="source-link" type="button" @click="openSourcePreview(lead)">
                {{ lead.source }}
              </button>
              <small v-if="lead.notes">{{ lead.notes }}</small>
            </div>

            <div class="lead-meta">
              <span class="score">{{ lead.score }}</span>
              <n-button class="icon-text-button" secondary size="small" @click="markQualified(lead.id)">
                <template #icon>
                  <n-icon><UserCheck /></n-icon>
                </template>
                确认
              </n-button>
            </div>
          </article>
        </section>

        <section v-if="activePage === 'workspace'" class="reply-panel" aria-labelledby="reply-title">
          <div class="section-title step-title">
            <span class="step-index">3</span>
            <div>
              <h2 id="reply-title">回复理解</h2>
              <p>判断意向、资料需求和转人工风险</p>
            </div>
          </div>

          <div class="reply-grid">
            <label class="field">
              <span>关联线索</span>
              <n-select v-model:value="replyLeadId" :options="replyLeadOptions" filterable />
            </label>

            <label class="field reply-text">
              <span>邮件回复</span>
              <n-input
                v-model:value="replyText"
                type="textarea"
                :autosize="{ minRows: 5, maxRows: 9 }"
              />
            </label>
          </div>

          <n-button
            class="primary-button"
            type="primary"
            size="large"
            :loading="currentAction === 'reply'"
            :disabled="loading"
            @click="analyzeCurrentReply"
          >
            <template #icon>
              <n-icon><MailCheck /></n-icon>
            </template>
            {{ currentAction === "reply" ? "理解中..." : "理解回复" }}
          </n-button>

          <article v-if="analysis" class="analysis-result">
            <div>
              <n-tag
                :type="statusTagType(analysis.requires_human ? 'human_review' : analysis.intent)"
                round
                :bordered="false"
              >
                {{ analysis.requires_human ? "转人工" : formatStatus(analysis.intent) }}
              </n-tag>
              <strong>{{ Math.round(analysis.confidence * 100) }}%</strong>
            </div>
            <p>{{ analysis.summary }}</p>
            <p>{{ analysis.next_action }}</p>
            <small v-if="selectedLead">关联：{{ selectedLead.company_name }}</small>
          </article>
        </section>

        <div class="feedback" aria-live="polite">
          <n-alert v-if="notice" class="notice" type="success" :show-icon="false">
            {{ notice }}
          </n-alert>
          <n-alert v-if="error" class="error" type="error" :show-icon="false">
            {{ error }}
          </n-alert>
        </div>
      </section>
      </main>
    </section>

    <div
      v-if="sourcePreviewLead"
      class="modal-backdrop"
      role="presentation"
      @click.self="closeSourcePreview"
    >
      <section
        class="source-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-modal-title"
      >
        <header class="modal-header">
          <div>
            <p class="panel-label">来源页面</p>
            <h2 id="source-modal-title">{{ sourcePreviewLead.company_name }}</h2>
          </div>
          <button class="icon-only-button" type="button" aria-label="关闭来源预览" @click="closeSourcePreview">
            <X :size="20" aria-hidden="true" />
          </button>
        </header>

        <div class="source-summary">
          <div>
            <span class="summary-label">原文地址</span>
            <a :href="sourcePreviewLead.source" target="_blank" rel="noreferrer">
              <ExternalLink :size="16" aria-hidden="true" />
              {{ sourcePreviewLead.source }}
            </a>
          </div>
          <div>
            <span class="summary-label">联系人邮箱</span>
            <strong>{{ sourcePreviewLead.email }}</strong>
          </div>
        </div>

        <div v-if="sourcePreviewLoading" class="modal-state">正在读取来源页面...</div>
        <div v-else-if="sourcePreviewError" class="modal-state error-state">
          {{ sourcePreviewError }}
        </div>
        <template v-else-if="sourcePreview">
          <div class="source-evidence">
            <span :class="sourcePreview.email_found ? 'status status-interested' : 'status status-needs-review'">
              {{ sourcePreview.email_found ? "邮箱已在原文中匹配" : "未在原文中直接匹配" }}
            </span>
            <span>{{ sourcePreview.emails.length }} 个公开邮箱</span>
            <div class="view-toggle" role="tablist" aria-label="来源视图">
              <button
                type="button"
                :class="{ active: sourcePreviewMode === 'page' }"
                @click="sourcePreviewMode = 'page'"
              >
                网页原文
              </button>
              <button
                type="button"
                :class="{ active: sourcePreviewMode === 'text' }"
                @click="sourcePreviewMode = 'text'"
              >
                文本证据
              </button>
            </div>
          </div>

          <div v-if="sourcePreviewMode === 'page'" class="source-web-layout">
            <div class="source-page-frame">
              <iframe
                :src="sourcePreview.url"
                title="来源网页原文"
                sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
                referrerpolicy="no-referrer"
              />
            </div>
            <aside class="evidence-panel" aria-label="联系人证据">
              <p class="panel-label">联系人高亮</p>
              <strong>{{ sourcePreview.email }}</strong>
              <span>{{ sourceHost }}</span>
              <div class="evidence-snippet">
                <template v-for="(chunk, index) in highlightedEvidenceExcerpt" :key="index">
                  <mark v-if="chunk.highlight">{{ chunk.text }}</mark>
                  <span v-else>{{ chunk.text }}</span>
                </template>
              </div>
              <a class="open-source-button" :href="sourcePreview.url" target="_blank" rel="noreferrer">
                <ExternalLink :size="16" aria-hidden="true" />
                打开原站
              </a>
            </aside>
          </div>

          <div v-else class="source-text" aria-label="来源页面文本证据">
            <template v-for="(chunk, index) in highlightedSourceText" :key="index">
              <mark v-if="chunk.highlight">{{ chunk.text }}</mark>
              <span v-else>{{ chunk.text }}</span>
            </template>
          </div>
        </template>
      </section>
    </div>
  </div>
  </n-config-provider>
</template>
