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
  reply_count?: number;
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
  created_at?: string;
  message_id?: string;
  source?: string;
  company_name?: string;
  country?: string;
}

interface DraftListResponse {
  total: number;
  drafts: EmailEvent[];
}

interface SendResponse {
  sent_count: number;
  events: EmailEvent[];
}

interface ReplyAnalysis {
  id: number;
  lead_id?: number;
  reply_text?: string;
  intent: string;
  confidence: number;
  summary: string;
  next_action: string;
  requires_human: boolean;
  created_at?: string;
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

interface SettingsResponse {
  sync_enabled: boolean;
  sync_interval_minutes: number;
  agent_provider: string;
  agent_model: string;
  has_agent_key: boolean;
  agent_key_preview: string;
  backend_base_url: string;
  email_server: string;
  email_user: string;
  has_email_password: boolean;
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
const sortField = ref("id");
const sortDir = ref<"asc" | "desc">("desc");
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
const currentAction = ref<"dashboard" | "search" | "outreach" | "reply" | "qualify" | "sync" | null>(null);

// Lead detail panel
const detailLeadId = ref<number | null>(null);
const detailStatus = ref("");
const detailNotes = ref("");
const detailOutreach = ref<EmailEvent[]>([]);
const detailReplies = ref<ReplyAnalysis[]>([]);
const detailLoading = ref(false);
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

// Settings page
const settings = ref<SettingsResponse>({
  sync_enabled: false,
  sync_interval_minutes: 0,
  agent_provider: "deepseek",
  agent_model: "deepseek-v4-pro",
  has_agent_key: false,
  agent_key_preview: "",
  backend_base_url: "http://localhost:8000",
  email_server: "mail.microport.com.cn",
  email_user: "",
  has_email_password: false,
});
const settingsAgentKeyInput = ref("");
const settingsEmailPasswordInput = ref("");
const settingsLoading = ref(false);
const settingsSaving = ref(false);
const settingsTab = ref<"email" | "sync" | "agent">("email");
const drafts = ref<EmailEvent[]>([]);
const draftCount = ref(0);
const showOutreachPreview = ref(false);
const outreachLoading = ref(false);
const outreachPreviews = ref<Array<{ lead_id: number; company_name: string; email: string; subject: string; body: string }>>([]);
const showCreateLead = ref(false);
const createError = ref("");
const newLead = ref({ company_name: "", region: "", country: "", website: "", contact_name: "", email: "", category: "medical device distributor" });
const activePage = ref<"workspace" | "agent" | "settings">("workspace");
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
const topbarContent = computed(() => {
  if (activePage.value === "agent") {
    return {
      eyebrow: "Pi / pi-mono Agent",
      title: "渠道拓展 Agent",
      copy: "默认使用 overseas-distributor-prospecting skill，支持实时输出、联网搜索和线索入库。",
    };
  }
  if (activePage.value === "settings") {
    return {
      eyebrow: "系统配置",
      title: "设置",
      copy: "邮件回复自动同步、Agent 模型与 API 配置。",
    };
  }
  return {
    eyebrow: "微创畅行机器人 · 海外业务",
    title: "海外渠道拓展系统",
    copy: "面向 SkyWalker TKA 的代理商发现、邮箱证据审阅、触达记录和回复处理。",
  };
});
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
  params.set("sort", sortField.value);
  params.set("order", sortDir.value);

  const [leadPayload, metricPayload] = await Promise.all([
    request<LeadListResponse>(`/leads?${params.toString()}`),
    request<Metrics>("/metrics"),
  ]);

  leads.value = leadPayload.leads;
  metrics.value = metricPayload;
  if (replyLeadId.value === "" && leads.value.length > 0) {
    replyLeadId.value = leads.value[0].id;
  }
  loadDrafts();
}

async function loadDrafts(): Promise<void> {
  try {
    const payload = await request<DraftListResponse>("/campaigns/drafts");
    drafts.value = payload.drafts;
    draftCount.value = payload.total;
  } catch {
    drafts.value = [];
    draftCount.value = 0;
  }
}

async function approveDraft(eventId: number): Promise<void> {
  await runAction("outreach", async () => {
    const result = await request<{ ok: boolean; sent: boolean; error?: string }>(
      `/campaigns/drafts/${eventId}/approve`,
      { method: "POST" }
    );
    notice.value = result.sent ? "已批准并发送" : result.ok ? "已批准" : "批准失败";
    await loadDrafts();
    await loadDashboard();
  });
}

async function rejectDraft(eventId: number): Promise<void> {
  await runAction("outreach", async () => {
    await request(`/campaigns/drafts/${eventId}/reject`, { method: "POST" });
    notice.value = "已拒绝";
    await loadDrafts();
  });
}

function openCreateLead(): void {
  createError.value = "";
  newLead.value = { company_name: "", region: "", country: "", website: "", contact_name: "", email: "", category: "medical device distributor" };
  showCreateLead.value = true;
}

async function createLead(): Promise<void> {
  createError.value = "";
  if (!newLead.value.company_name.trim()) {
    createError.value = "请填写公司名称";
    return;
  }
  if (!newLead.value.region.trim()) {
    createError.value = "请填写地区";
    return;
  }
  if (!newLead.value.country.trim()) {
    createError.value = "请填写国家";
    return;
  }
  if (!newLead.value.email.trim()) {
    createError.value = "请填写邮箱";
    return;
  }
  try {
    await request("/leads", {
      method: "POST",
      body: JSON.stringify(newLead.value),
    });
    showCreateLead.value = false;
    notice.value = "线索已添加";
    await loadDashboard();
  } catch (caught) {
    const msg = caught instanceof Error ? caught.message : "创建失败";
    // Parse FastAPI validation errors into readable text
    try {
      const parsed = JSON.parse(msg);
      if (parsed.detail && Array.isArray(parsed.detail)) {
        createError.value = parsed.detail.map((e: { loc: string[]; msg: string }) => `${e.loc.slice(-1)[0]}: ${e.msg}`).join("; ");
        return;
      }
    } catch {}
    createError.value = msg;
  }
}

async function batchDeleteLeads(): Promise<void> {
  if (selectedLeadIds.value.length === 0) return;
  const confirmed = globalThis.confirm?.(`确定删除选中的 ${selectedLeadIds.value.length} 条线索及其关联数据？`) ?? true;
  if (!confirmed) return;
  await runAction("qualify", async () => {
    await request("/leads/batch-delete", {
      method: "POST",
      body: JSON.stringify({ lead_ids: selectedLeadIds.value }),
    });
    selectedLeadIds.value = [];
    notice.value = "已批量删除";
    await loadDashboard();
  });
}

async function deleteLead(leadId: number): Promise<void> {
  const confirmed = globalThis.confirm?.("确定删除这条线索及其关联的外联记录和回复分析？") ?? true;
  if (!confirmed) return;
  await runAction("qualify", async () => {
    await request(`/leads/${leadId}`, { method: "DELETE" });
    closeLeadDetail();
    notice.value = "线索已删除";
    await loadDashboard();
  });
}

async function approveAllDrafts(): Promise<void> {
  if (draftCount.value === 0) return;
  await runAction("outreach", async () => {
    const result = await request<{ total: number; results: Array<{ sent: boolean }> }>(
      "/campaigns/drafts/approve-all",
      { method: "POST" }
    );
    const sentCount = result.results.filter((r) => r.sent).length;
    notice.value = `已批准 ${result.total} 条，成功发送 ${sentCount} 条`;
    await loadDrafts();
    await loadDashboard();
  });
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

async function syncReplies(): Promise<void> {
  await runAction("sync", async () => {
    const payload = await request<{
      total_inbox: number;
      synced: number;
      skipped: number;
      items: Array<{ lead_id: number; company: string; intent: string; auto_reply: boolean }>;
    }>("/replies/sync", { method: "POST" });
    if (payload.synced > 0) {
      const companies = [...new Set(payload.items.map((i) => i.company))].join("、");
      notice.value = `同步了 ${payload.synced} 条回复（${companies}），跳过 ${payload.skipped} 条`;
    } else {
      notice.value = `未发现新回复（扫描 ${payload.total_inbox} 封邮件）`;
    }
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

async function sendOutreachSingle(leadId: number): Promise<void> {
  await fetchOutreachPreview([leadId]);
}

async function sendOutreachBatch(): Promise<void> {
  await fetchOutreachPreview(selectedLeadIds.value);
}

async function fetchOutreachPreview(leadIds: number[]): Promise<void> {
  if (leadIds.length === 0) return;
  outreachPreviews.value = [];
  outreachLoading.value = true;
  showOutreachPreview.value = true;
  try {
    const payload = await request<{ previews: typeof outreachPreviews.value }>("/campaigns/outreach-preview", {
      method: "POST",
      body: JSON.stringify({ lead_ids: leadIds }),
    });
    outreachPreviews.value = payload.previews;
  } catch (caught) {
    error.value = "生成邮件失败";
    showOutreachPreview.value = false;
  } finally {
    outreachLoading.value = false;
  }
}

async function confirmSendOutreach(): Promise<void> {
  const leadIds = outreachPreviews.value.map((p) => p.lead_id);
  const customEmails: Record<string, { subject: string; body: string }> = {};
  for (const p of outreachPreviews.value) {
    customEmails[String(p.lead_id)] = { subject: p.subject, body: p.body };
  }
  await runAction("outreach", async () => {
    const payload = await request<SendResponse>("/campaigns/outreach-records", {
      method: "POST",
      body: JSON.stringify({ lead_ids: leadIds, custom_emails: customEmails }),
    });
    showOutreachPreview.value = false;
    notice.value = `已发送 ${payload.sent_count} 封外联`;
    await loadDashboard();
  });
}

function goToReplyForLead(leadId: number): void {
  openLeadDetail(leadId);
}

async function reactivateLead(leadId: number): Promise<void> {
  await runAction("qualify", async () => {
    await request<Lead>(`/leads/${leadId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "new", notes: "重新激活" }),
    });
    notice.value = "线索已重新激活";
    await loadDashboard();
  });
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

const detailLead = computed(() =>
  detailLeadId.value ? leads.value.find((l) => l.id === detailLeadId.value) ?? null : null
);

async function openLeadDetail(leadId: number): Promise<void> {
  detailLeadId.value = leadId;
  detailLoading.value = true;
  const lead = leads.value.find((l) => l.id === leadId);
  detailStatus.value = lead?.status ?? "";
  detailNotes.value = lead?.notes ?? "";
  try {
    const history = await request<{
      lead: Lead;
      outreach_events: EmailEvent[];
      reply_analyses: ReplyAnalysis[];
    }>(`/leads/${leadId}/history`);
    detailOutreach.value = history.outreach_events;
    detailReplies.value = history.reply_analyses;
  } catch {
    detailOutreach.value = [];
    detailReplies.value = [];
  } finally {
    detailLoading.value = false;
  }
}

function closeLeadDetail(): void {
  detailLeadId.value = null;
  detailOutreach.value = [];
  detailReplies.value = [];
}

function goToReply(): void {
  notice.value = "回复已自动同步和分析，点击行查看详情";
}

async function saveLeadDetail(): Promise<void> {
  if (detailLeadId.value === null) return;
  const lead = leads.value.find((l) => l.id === detailLeadId.value);
  if (lead && lead.status === detailStatus.value && (lead.notes || "") === (detailNotes.value || "")) {
    return; // no change
  }
  await request<Lead>(`/leads/${detailLeadId.value!}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: detailStatus.value || undefined,
      notes: detailNotes.value || undefined,
    }),
  });
  await loadDashboard();
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

function toggleSelectAll(checked: boolean): void {
  if (checked) {
    selectedLeadIds.value = leads.value.map((l) => l.id);
  } else {
    selectedLeadIds.value = [];
  }
}

function toggleSort(field: string): void {
  if (sortField.value === field) {
    sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  } else {
    sortField.value = field;
    sortDir.value = "asc";
  }
  runAction("dashboard", loadDashboard);
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

function showPage(page: "workspace" | "agent" | "settings", sectionId?: string): void {
  activePage.value = page;
  agentGuideOpen.value = false;
  agentNotificationsOpen.value = false;
  sidebarUserMenuOpen.value = false;
  const hash = page === "agent" ? "agent" : page === "settings" ? "settings" : sectionId || "overview";
  globalThis.history?.replaceState(null, "", `#${hash}`);

  if (page === "settings") {
    loadSettings();
    return;
  }
  const targetId = sectionId || (page === "agent" ? "overview" : "");
  if (!targetId) return;
  globalThis.requestAnimationFrame?.(() => {
    globalThis.document?.getElementById(targetId)?.scrollIntoView({ block: "start" });
  });
}

async function loadSettings(): Promise<void> {
  settingsLoading.value = true;
  try {
    settings.value = await request<SettingsResponse>("/settings");
  } catch {
    // use defaults
  } finally {
    settingsLoading.value = false;
  }
}

async function saveSettings(): Promise<void> {
  if (settingsSaving.value) return;
  settingsSaving.value = true;
  try {
    const body: Record<string, unknown> = {
      sync_enabled: settings.value.sync_enabled,
      sync_interval_minutes: settings.value.sync_interval_minutes,
      agent_provider: agentProviderName.value,
      agent_model: agentModelName.value,
      backend_base_url: agentBackendBaseUrl.value,
      email_server: settings.value.email_server,
      email_user: settings.value.email_user,
    };
    if (settingsAgentKeyInput.value.trim()) {
      body.agent_key = settingsAgentKeyInput.value.trim();
    }
    if (settingsEmailPasswordInput.value.trim()) {
      body.email_password = settingsEmailPasswordInput.value.trim();
    }
    settings.value = await request<SettingsResponse>("/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    settingsAgentKeyInput.value = "";
    settingsEmailPasswordInput.value = "";
    // Also sync agent config
    await saveAgentConfig();
    notice.value = "设置已保存";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "设置保存失败";
  } finally {
    settingsSaving.value = false;
  }
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

function formatTime(iso?: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return iso.slice(0, 16);
  }
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
        <button
          type="button"
          :class="{ active: activePage === 'agent' }"
          @click="showPage('agent')"
        >
          <span class="nav-icon"><Bot :size="18" aria-hidden="true" /></span>
          渠道拓展Agent
        </button>
        <button
          type="button"
          :class="{ active: activePage === 'workspace' }"
          @click="showPage('workspace', 'overview')"
        >
          <span class="nav-icon"><Home :size="18" aria-hidden="true" /></span>
          线索管理
          <span v-if="draftCount > 0" class="nav-badge">{{ draftCount }}</span>
        </button>
        <button
          type="button"
          :class="{ active: activePage === 'settings' }"
          @click="showPage('settings')"
        >
          <span class="nav-icon"><SlidersHorizontal :size="18" aria-hidden="true" /></span>
          设置
        </button>
      </nav>
      <div class="sidebar-footer">
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
            <n-button
              class="ghost-button"
              secondary
              :loading="currentAction === 'sync'"
              :disabled="loading"
              @click="syncReplies"
            >
              <template #icon>
                <n-icon><MailCheck /></n-icon>
              </template>
              同步回复
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
        v-if="activePage === 'agent' && agentNotificationsOpen"
        class="agent-topbar-panels"
        aria-live="polite"
      >
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
          v-if="false"
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

        <section
          v-if="activePage === 'workspace' && draftCount > 0"
          class="draft-queue"
          aria-label="待审核外联"
        >
          <div class="draft-queue-head">
            <div>
              <p class="panel-label">待审核</p>
              <strong>Agent 生成了 {{ draftCount }} 条外联草稿</strong>
              <span>审核后才会真实发送</span>
            </div>
            <n-button class="primary-button" type="primary" size="small" @click="approveAllDrafts">
              <template #icon><n-icon><Check /></n-icon></template>
              全部批准发送
            </n-button>
          </div>
          <article v-for="draft in drafts" :key="draft.id" class="draft-card">
            <div class="draft-card-body">
              <div class="draft-meta">
                <strong>{{ draft.company_name || 'Unknown' }}</strong>
                <span>{{ draft.country }} · {{ draft.sent_to }}</span>
              </div>
              <p class="draft-subject">{{ draft.subject }}</p>
              <p class="draft-preview">{{ draft.body.slice(0, 250) }}{{ draft.body.length > 250 ? '...' : '' }}</p>
            </div>
            <div class="draft-actions">
              <n-button class="ghost-button" type="primary" size="small" @click="approveDraft(draft.id)">
                <template #icon><n-icon><Check /></n-icon></template>
                批准
              </n-button>
              <n-button class="ghost-button danger-action" size="small" @click="rejectDraft(draft.id)">
                <template #icon><n-icon><X /></n-icon></template>
                拒绝
              </n-button>
            </div>
          </article>
        </section>

        <div v-if="activePage === 'workspace'" class="toolbar" aria-label="筛选线索">
          <div class="toolbar-search">
            <Search :size="15" class="toolbar-search-icon" aria-hidden="true" />
            <input
              v-model="query"
              placeholder="搜索公司、邮箱、国家..."
              class="toolbar-search-input"
              @keyup.enter="runAction('dashboard', loadDashboard)"
            />
            <button
              v-if="query"
              class="toolbar-search-clear"
              type="button"
              aria-label="清除搜索"
              @click="query = ''; runAction('dashboard', loadDashboard)"
            >
              <X :size="13" />
            </button>
          </div>

          <div class="status-chips">
            <button
              v-for="opt in statusFilterOptions"
              :key="String(opt.value)"
              :class="['status-chip', { active: filterStatus === opt.value }]"
              @click="filterStatus = filterStatus === opt.value ? '' : String(opt.value); runAction('dashboard', loadDashboard)"
            >
              {{ opt.label }}
            </button>
          </div>

          <input
            v-model="filterRegion"
            placeholder="地区..."
            class="toolbar-region-input"
            @keyup.enter="runAction('dashboard', loadDashboard)"
          />
        </div>

        <section
          v-if="activePage === 'workspace'"
          class="lead-list modern-data-table lead-intelligence-panel"
          aria-labelledby="lead-list-title"
        >
          <div class="list-head">
            <div class="list-head-left">
              <label class="select-cell" @click.stop>
                <n-checkbox
                  :checked="selectedLeadIds.length === leads.length && leads.length > 0"
                  :indeterminate="selectedLeadIds.length > 0 && selectedLeadIds.length < leads.length"
                  @update:checked="toggleSelectAll"
                />
              </label>
              <div>
                <h2 id="lead-list-title">线索数据库</h2>
                <p>公司、邮箱、公开来源证据、评分和管线状态</p>
              </div>
            </div>
            <div class="list-head-right">
              <n-button class="ghost-button" secondary size="small" @click="openCreateLead">
                <template #icon><n-icon><Plus /></n-icon></template>
                添加线索
              </n-button>
              <template v-if="selectedLeadIds.length > 0">
                <span class="selection-count">已选 {{ selectedLeadIds.length }} 条</span>
                <n-button
                  class="primary-button"
                  type="primary"
                  size="small"
                  :loading="currentAction === 'outreach'"
                  :disabled="loading"
                  @click.stop="sendOutreachBatch"
                >
                  <template #icon><n-icon><Send /></n-icon></template>
                  发送外联
                </n-button>
                <n-button class="ghost-button danger-action" secondary size="small" @click.stop="batchDeleteLeads">
                  <template #icon><n-icon><Trash2 /></n-icon></template>
                  删除
                </n-button>
                <n-button class="ghost-button" secondary size="small" @click.stop="selectedLeadIds = []">
                  取消
                </n-button>
              </template>
              <span v-else>{{ leads.length }} 条</span>
            </div>
          </div>

          <n-empty
            v-if="leads.length === 0"
            class="empty-state"
            description="点击左侧'实时搜索并入库'后，结果会显示在这里。"
          >
            <template #icon>
              <n-icon><Globe2 /></n-icon>
            </template>
            <template #extra>
              <strong>暂无线索</strong>
            </template>
          </n-empty>

          <article
            v-for="lead in leads"
            :key="lead.id"
            :class="['lead-row', { 'lead-row-selected': detailLeadId === lead.id }]"
            @click="openLeadDetail(lead.id)"
          >
            <label class="select-cell" :aria-label="`选择 ${lead.company_name}`" @click.stop>
              <n-checkbox
                :checked="selectedLeadIds.includes(lead.id)"
                @update:checked="(checked) => setLeadSelection(lead.id, checked)"
              />
            </label>

            <div class="lead-body">
              <div class="lead-top">
                <strong class="lead-name">{{ lead.company_name }}</strong>
                <n-tag :type="statusTagType(lead.status)" size="small" round :bordered="false">
                  {{ formatStatus(lead.status) }}
                </n-tag>
                <span class="lead-region">{{ lead.country === lead.region ? lead.country : `${lead.country} · ${lead.region}` }}</span>
                <span class="lead-category">{{ lead.category }}</span>
              </div>
              <div class="lead-bottom">
                <a v-if="lead.email" :href="`mailto:${lead.email}`" class="lead-email" @click.stop>{{ lead.email }}</a>
                <span v-else class="muted">—</span>
                <span class="lead-score-badge">{{ lead.score }}</span>
                <button class="source-link" type="button" @click.stop="openSourcePreview(lead)">{{ lead.source }}</button>
                <span class="lead-reason-inline">{{ lead.match_reason }}</span>
              </div>
            </div>

            <div class="lead-tools" @click.stop>
              <button v-if="lead.status === 'new'" class="lead-action-btn primary" @click="sendOutreachSingle(lead.id)"><Send :size="13" />外联</button>
              <button v-if="lead.status === 'emailed' && (lead.reply_count || 0) > 0" class="lead-action-btn" @click="goToReplyForLead(lead.id)"><MailCheck :size="13" />回复</button>
              <button v-if="['new', 'emailed', 'interested', 'human_review', 'needs_review'].includes(lead.status)" class="lead-action-btn" @click="markQualified(lead.id)"><UserCheck :size="13" />确认</button>
              <button v-if="lead.status === 'rejected'" class="lead-action-btn" @click="reactivateLead(lead.id)"><RefreshCw :size="13" />激活</button>
              <button class="lead-action-btn danger" @click="deleteLead(lead.id)"><Trash2 :size="13" /></button>
            </div>
          </article>
        </section>

        <div
          v-if="activePage === 'workspace' && detailLeadId !== null"
          class="modal-backdrop"
          role="presentation"
          @click.self="closeLeadDetail"
        >
          <section
            class="lead-detail-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="lead-detail-title"
          >
            <header class="modal-header">
              <div>
                <p class="panel-label">线索管理</p>
                <h2 id="lead-detail-title">{{ detailLead?.company_name }}</h2>
                <span class="detail-meta">{{ detailLead?.country === detailLead?.region ? detailLead?.country : `${detailLead?.country} · ${detailLead?.region}` }} · {{ detailLead?.email }}</span>
              </div>
              <button class="icon-only-button" type="button" aria-label="关闭详情" @click="closeLeadDetail">
                <X :size="20" aria-hidden="true" />
              </button>
            </header>

            <div class="detail-summary">
              <div class="detail-summary-row">
                <span class="detail-summary-label">匹配理由</span>
                <span>{{ detailLead?.match_reason }}</span>
              </div>
              <div class="detail-summary-row">
                <span class="detail-summary-label">来源</span>
                <a :href="detailLead?.source" target="_blank" rel="noreferrer">{{ detailLead?.source }}</a>
              </div>
              <div class="detail-summary-row">
                <span class="detail-summary-label">网站</span>
                <a :href="detailLead?.website" target="_blank" rel="noreferrer">{{ detailLead?.website }}</a>
              </div>
              <div class="detail-summary-row">
                <span class="detail-summary-label">类别</span>
                <span>{{ detailLead?.category }}</span>
              </div>
            </div>

            <div class="detail-grid">
              <div class="detail-form">
                <label class="field">
                  <span>状态</span>
                  <n-select v-model:value="detailStatus" :options="statusFilterOptions.filter(o => o.value !== '')" @update:value="saveLeadDetail" />
                </label>
                <label class="field">
                  <span>备注</span>
                  <n-input
                    v-model:value="detailNotes"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 5 }"
                    placeholder="添加跟进备注..."
                    @blur="saveLeadDetail"
                  />
                </label>
                <div class="detail-actions">
                  <n-button class="ghost-button danger-action" secondary @click="deleteLead(detailLeadId!)">
                    <template #icon><n-icon><Trash2 /></n-icon></template>
                    删除
                  </n-button>
                  <n-button class="ghost-button" secondary @click="goToReply">
                    <template #icon><n-icon><MailCheck /></n-icon></template>
                    回复处理
                  </n-button>
                </div>
              </div>

              <div class="detail-history">
                <div v-if="detailOutreach.length > 0">
                  <p class="panel-label">外联记录</p>
                  <article v-for="ev in detailOutreach" :key="ev.id" class="history-card">
                    <div class="history-head">
                      <n-tag :type="ev.status === 'sent' ? 'success' : ev.status === 'send_failed' ? 'error' : 'info'" size="small" round :bordered="false">
                        {{ ev.status === 'sent' ? '已发送' : ev.status === 'send_failed' ? '发送失败' : '已记录' }}
                      </n-tag>
                      <small>{{ formatTime(ev.created_at) }}</small>
                    </div>
                    <strong>{{ ev.subject }}</strong>
                    <span>收件人：{{ ev.sent_to }}</span>
                    <p>{{ ev.body.slice(0, 200) }}{{ ev.body.length > 200 ? '...' : '' }}</p>
                  </article>
                </div>

                <div v-if="detailReplies.length > 0">
                  <p class="panel-label">回复记录</p>
                  <article v-for="r in detailReplies" :key="r.id" class="history-card">
                    <div class="history-head">
                      <n-tag :type="statusTagType(r.requires_human ? 'human_review' : r.intent)" size="small" round :bordered="false">
                        {{ r.requires_human ? '转人工' : formatStatus(r.intent) }}
                      </n-tag>
                      <small>{{ Math.round(r.confidence * 100) }}% · {{ formatTime(r.created_at) }}</small>
                    </div>
                    <blockquote v-if="r.reply_text" class="reply-quote">{{ r.reply_text }}</blockquote>
                    <p>{{ r.summary }}</p>
                    <p class="history-next">{{ r.next_action }}</p>
                  </article>
                </div>

                <div v-if="detailOutreach.length === 0 && detailReplies.length === 0 && !detailLoading" class="history-empty">
                  暂无外联或回复记录
                </div>
                <div v-if="detailLoading" class="history-empty">加载中...</div>
              </div>
            </div>
          </section>
        </div>

        <div class="feedback" aria-live="polite">
          <n-alert v-if="notice" class="notice" type="success" :show-icon="false">
            {{ notice }}
          </n-alert>
          <n-alert v-if="error" class="error" type="error" :show-icon="false">
            {{ error }}
          </n-alert>
        </div>
      </section>

        <section
          v-if="activePage === 'settings'"
          class="settings-page"
          aria-labelledby="settings-title"
        >
          <div class="settings-tabs">
            <button :class="['settings-tab', { active: settingsTab === 'email' }]" @click="settingsTab = 'email'">邮箱</button>
            <button :class="['settings-tab', { active: settingsTab === 'sync' }]" @click="settingsTab = 'sync'">同步</button>
            <button :class="['settings-tab', { active: settingsTab === 'agent' }]" @click="settingsTab = 'agent'">Agent</button>
          </div>

          <section v-if="settingsTab === 'email'" class="settings-card">
            <div class="settings-card-head">
              <div>
                <p class="panel-label">邮箱配置</p>
                <h3>Exchange 邮件服务</h3>
                <p>配置 EWS 连接信息，用于发送外联和同步回复。</p>
              </div>
              <n-tag :type="settings.email_user ? 'success' : 'default'" size="small" round :bordered="false">
                {{ settings.email_user ? '已配置' : '未配置' }}
              </n-tag>
            </div>
            <div class="settings-agent-grid">
              <label class="field"><span>SMTP 服务器</span><n-input v-model:value="settings.email_server" placeholder="mail.microport.com.cn" /></label>
              <label class="field"><span>邮箱账号</span><n-input v-model:value="settings.email_user" placeholder="OB_OSD@microport.com" /></label>
              <label class="field"><span>邮箱密码</span><n-input v-model:value="settingsEmailPasswordInput" autocomplete="off" :placeholder="settings.has_email_password ? '已设置 (不显示)' : '输入密码'" type="password" show-password-on="click" /></label>
            </div>
          </section>

          <section v-if="settingsTab === 'sync'" class="settings-card">
            <div class="settings-card-head">
              <div>
                <p class="panel-label">邮件同步</p>
                <h3>自动同步回复</h3>
                <p>定期从 Exchange 收件箱拉取回复，匹配到对应线索并自动分析意向。</p>
              </div>
              <n-tag :type="settings.sync_enabled ? 'success' : 'default'" size="small" round :bordered="false">
                {{ settings.sync_enabled ? '已开启' : '已关闭' }}
              </n-tag>
            </div>
            <label class="toggle-field"><n-checkbox v-model:checked="settings.sync_enabled">启用自动同步</n-checkbox></label>
            <label class="field" v-if="settings.sync_enabled"><span>同步间隔（分钟）</span><n-input-number v-model:value="settings.sync_interval_minutes" :min="5" :max="1440" /></label>
            <p class="setting-hint" v-if="settings.sync_enabled && settings.sync_interval_minutes > 0">每 {{ settings.sync_interval_minutes }} 分钟自动扫描收件箱，仅同步新回复。</p>
          </section>

          <section v-if="settingsTab === 'agent'" class="settings-card">
            <div class="settings-card-head">
              <div>
                <p class="panel-label">AI Agent</p>
                <h3>模型与 API 配置</h3>
                <p>配置 Agent 使用的 AI 模型、API Key 和后端地址。</p>
              </div>
            </div>
            <div class="settings-agent-grid">
              <label class="field"><span>Provider</span><n-select v-model:value="agentProviderName" :options="providerOptions" /></label>
              <label class="field"><span>API Key</span><n-input v-model:value="settingsAgentKeyInput" autocomplete="off" :placeholder="settings.has_agent_key ? settings.agent_key_preview : 'sk-...'" type="password" show-password-on="click" /></label>
              <label class="field"><span>模型</span><n-input v-model:value="agentModelName" placeholder="deepseek-v4-pro" /></label>
              <label class="field"><span>Backend URL</span><n-input v-model:value="agentBackendBaseUrl" /></label>
            </div>
          </section>

          <div class="settings-actions">
            <n-button
              class="primary-button"
              type="primary"
              size="large"
              :loading="settingsSaving"
              :disabled="settingsLoading || settingsSaving"
              @click="saveSettings"
            >
              <template #icon><n-icon><Save /></n-icon></template>
              {{ settingsSaving ? '保存中...' : '保存设置' }}
            </n-button>
          </div>
        </section>
      </main>
    </section>

    <!-- Outreach Preview Modal -->
    <div
      v-if="showOutreachPreview"
      class="modal-backdrop"
      role="presentation"
      @click.self="showOutreachPreview = false"
    >
      <section class="create-lead-modal" role="dialog" aria-modal="true" aria-label="外联预览">
        <header class="modal-header">
          <div>
            <p class="panel-label">确认发送</p>
            <h2>外联邮件预览</h2>
          </div>
          <button class="icon-only-button" type="button" aria-label="关闭" @click="showOutreachPreview = false">
            <X :size="20" aria-hidden="true" />
          </button>
        </header>
        <div class="create-lead-body">
          <div v-if="outreachLoading" class="outreach-loading">
            <RefreshCw :size="28" class="spin" />
            <span>AI 正在生成邮件...</span>
          </div>
          <article v-for="(p, idx) in outreachPreviews" :key="p.lead_id" class="outreach-preview-card">
            <div class="outreach-preview-meta">
              <strong>{{ p.company_name }}</strong>
              <span>收件人：{{ p.email }}</span>
            </div>
            <label class="field"><span>主题</span><n-input v-model:value="outreachPreviews[idx].subject" /></label>
            <label class="field"><span>正文</span><n-input v-model:value="outreachPreviews[idx].body" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" /></label>
          </article>
        </div>
        <footer class="create-lead-footer">
          <n-button class="ghost-button" secondary @click="showOutreachPreview = false">取消</n-button>
          <n-button class="primary-button" type="primary" :disabled="outreachLoading" :loading="currentAction === 'outreach'" @click="confirmSendOutreach">
            <template #icon><n-icon><Send /></n-icon></template>
            确认发送
          </n-button>
        </footer>
      </section>
    </div>

    <!-- Create Lead Modal -->
    <div
      v-if="showCreateLead"
      class="modal-backdrop"
      role="presentation"
      @click.self="showCreateLead = false"
    >
      <section class="create-lead-modal" role="dialog" aria-modal="true" aria-label="添加线索">
        <header class="modal-header">
          <div>
            <p class="panel-label">线索管理</p>
            <h2>添加线索</h2>
          </div>
          <button class="icon-only-button" type="button" aria-label="关闭" @click="showCreateLead = false">
            <X :size="20" aria-hidden="true" />
          </button>
        </header>
        <div class="create-lead-body">
          <div class="create-lead-row">
            <label class="field"><span>公司名称 *</span><n-input v-model:value="newLead.company_name" /></label>
            <label class="field"><span>国家 *</span><n-input v-model:value="newLead.country" /></label>
          </div>
          <div class="create-lead-row">
            <label class="field"><span>地区 *</span><n-input v-model:value="newLead.region" placeholder="如 Southeast Asia" /></label>
            <label class="field"><span>网站</span><n-input v-model:value="newLead.website" placeholder="https://" /></label>
          </div>
          <div class="create-lead-row">
            <label class="field"><span>邮箱 *</span><n-input v-model:value="newLead.email" /></label>
            <label class="field"><span>联系人</span><n-input v-model:value="newLead.contact_name" /></label>
          </div>
          <label class="field"><span>类别</span><n-input v-model:value="newLead.category" /></label>
        </div>
        <p v-if="createError" class="create-error">{{ createError }}</p>
        <footer class="create-lead-footer">
          <n-button class="ghost-button" secondary @click="showCreateLead = false">取消</n-button>
          <n-button class="primary-button" type="primary" :loading="currentAction === 'search'" @click="createLead">
            <template #icon><n-icon><Plus /></n-icon></template>
            创建
          </n-button>
        </footer>
      </section>
    </div>

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

    <!-- Agent Guide Modal -->
    <div
      v-if="agentGuideOpen"
      class="modal-backdrop"
      role="presentation"
      @click.self="agentGuideOpen = false"
    >
      <section class="guide-modal" role="dialog" aria-modal="true" aria-label="使用指南">
        <header class="modal-header">
          <div>
            <p class="panel-label">使用指南</p>
            <h2>渠道拓展 Agent 工作流</h2>
          </div>
          <button class="icon-only-button" type="button" aria-label="关闭" @click="agentGuideOpen = false">
            <X :size="20" aria-hidden="true" />
          </button>
        </header>
        <div class="guide-body">
          <div class="guide-section">
            <h3>Step 1 — 建立线索库</h3>
            <p>在任务框描述目标：产品、国家、渠道类型。Agent 会自动扩展搜索词、调用搜索引擎、提取公开邮箱，并去重入库。</p>
            <p>示例：<code>帮我在德国和新加坡找骨科植入物经销商，要求有公开邮箱和官网证据</code></p>
          </div>
          <div class="guide-section">
            <h3>Step 2 — 发送外联</h3>
            <p>Agent 生成的邮件会进入<strong>线索管理 → 待审核队列</strong>，需人工预览和批准后才会真实发送。</p>
            <p>也可手动勾选线索，点击「发送外联」预览 AI 生成的邮件模板，编辑后确认发送。</p>
          </div>
          <div class="guide-section">
            <h3>Step 3 — 分析回复</h3>
            <p>点击「同步回复」从收件箱拉取真实回复，AI 自动分析意图（感兴趣 / 拒绝 / 复杂 / 待审核）。</p>
            <p>点击线索行查看完整沟通历史、回复原文和分析结果，可在详情中修改状态和备注。</p>
          </div>
          <div class="guide-section">
            <h3>设置</h3>
            <p>在「设置」页面配置邮箱连接、自动同步频率和 AI 模型参数。启用自动同步后，系统定期扫描收件箱。</p>
          </div>
        </div>
      </section>
    </div>
  </div>
  </n-config-provider>
</template>
