<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bell,
  Bot,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Database,
  Gauge,
  ExternalLink,
  FileText,
  Globe2,
  Home,
  Inbox,
  Link2,
  Loader2,
  Mail,
  MailCheck,
  MapPin,
  Tag,
  Maximize2,
  MessageSquare,
  Pencil,
  Sparkles,
  Star,
  User,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Square,
  Trash2,
  UserCheck,
  Wrench,
  X,
} from "lucide-vue-next";
import {
  createDiscreteApi,
  NButton,
  NCard,
  NCheckbox,
  NConfigProvider,
  NEmpty,
  NGlobalStyle,
  NIcon,
  NInput,
  NInputNumber,
  NPagination,
  NSelect,
  NTag,
  type ConfigProviderProps,
  type SelectOption,
} from "naive-ui";
import AdminPanel from "./components/AdminPanel.vue";
import FilterSelect from "./components/FilterSelect.vue";
import ScoringRulesSettings from "./components/ScoringRulesSettings.vue";
import UsageReport from "./components/UsageReport.vue";
import {
  STANDARD_REGIONS,
  COUNTRY_TO_REGION,
  countryGroupsByRegion,
  labelForCountry,
  labelForRegion,
} from "./geo";
import {
  activateAgentSession,
  createNextAgentSession,
  deleteAgentSession,
  deriveSessionTitle,
  isDefaultSessionTitle,
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
  match_level?: string; // AI 匹配度徽章：strong | medium | weak | reject
  notes: string;
  lead_type?: string;
  reply_count?: number;
  last_outreach_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

interface Metrics {
  total_leads: number;
  interested_leads: number;
  sent_emails: number;
  human_review: number;
  distributor_leads?: number;
  kol_leads?: number;
  distributor_qualified?: number;
  kol_qualified?: number;
}

interface SearchResponse {
  created_count: number;
  leads: Lead[];
}

interface LeadListResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
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
  queued_count?: number;
  note?: string;
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

interface AgentToolCall {
  id: number;
  toolName: string;
  status: "running" | "done" | "error";
  detail?: string;
}

interface AgentTurn {
  id: number;
  role: "user" | "assistant";
  text: string;
  toolCalls: AgentToolCall[];
  pending: boolean;
  error: string;
  stopped: boolean;
  startedAt: number;
  resultSummary?: { leadsAdded: number; draftsAdded: number };
  /** Tool-call timeline starts expanded while running, then auto-collapses to
   * a one-line summary once the turn finishes; the user can still toggle it. */
  toolTimelineExpanded?: boolean;
}

interface AgentChatResponse {
  message: string;
  session_id: string;
  events: AgentEvent[];
}

interface SettingsResponse {
  sync_enabled: boolean;
  sync_interval_minutes: number;
  auto_send_enabled: boolean;
  send_daily_cap: number;
  send_min_interval_seconds: number;
  send_per_domain_daily_cap: number;
  ai_content_generation: boolean;
  ai_content_ready: boolean;
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

// ── Auth state ───────────────────────────────────────────────────────────────
interface MeUser {
  id?: number;
  username: string;
  display_name?: string;
  is_superadmin: boolean;
  is_service?: boolean;
  must_change_password?: boolean;
  permissions: string[];
  roles: { id: number; name: string }[];
}

const TOKEN_KEY = "medbot_token";
const authToken = ref<string | null>(localStorage.getItem(TOKEN_KEY));
const me = ref<MeUser | null>(null);
const isAuthenticated = computed(() => !!authToken.value && !!me.value);

const loginUsername = ref("");
const loginPassword = ref("");
const loginError = ref("");
const loginLoading = ref(false);

const changePwdOpen = ref(false);
const forcePwdChange = ref(false);
const oldPassword = ref("");
const newPassword = ref("");
const changePwdMsg = ref("");

function maybeForcePasswordChange(): void {
  if (me.value?.must_change_password) {
    forcePwdChange.value = true;
    changePwdOpen.value = true;
  }
}

function can(permission: string): boolean {
  if (!me.value) return false;
  if (me.value.is_superadmin) return true;
  return me.value.permissions.includes(permission);
}

function setToken(token: string | null): void {
  authToken.value = token;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function doLogin(): Promise<void> {
  loginError.value = "";
  if (!loginUsername.value.trim() || !loginPassword.value) {
    loginError.value = "请输入用户名和密码";
    return;
  }
  loginLoading.value = true;
  try {
    const resp = await fetch(`${apiBase}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: loginUsername.value.trim(),
        password: loginPassword.value,
      }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      loginError.value = (detail as { detail?: string }).detail || "登录失败";
      return;
    }
    const data = (await resp.json()) as { token: string; user: MeUser };
    setToken(data.token);
    me.value = data.user;
    loginPassword.value = "";
    await bootstrapAfterLogin();
    maybeForcePasswordChange();
  } catch (error) {
    loginError.value = error instanceof Error ? error.message : "登录失败";
  } finally {
    loginLoading.value = false;
  }
}

function logout(): void {
  setToken(null);
  me.value = null;
  sidebarUserMenuOpen.value = false;
  activePage.value = "workspace";
}

async function fetchMe(): Promise<boolean> {
  if (!authToken.value) return false;
  try {
    const resp = await fetch(`${apiBase}/auth/me`, {
      headers: { Authorization: `Bearer ${authToken.value}` },
    });
    if (!resp.ok) {
      setToken(null);
      me.value = null;
      return false;
    }
    me.value = (await resp.json()) as MeUser;
    return true;
  } catch {
    return false;
  }
}

async function submitChangePassword(): Promise<void> {
  changePwdMsg.value = "";
  if (newPassword.value.length < 6) {
    changePwdMsg.value = "新密码至少 6 位";
    return;
  }
  try {
    await request("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        old_password: oldPassword.value,
        new_password: newPassword.value,
      }),
    });
    changePwdMsg.value = "密码已修改";
    oldPassword.value = "";
    newPassword.value = "";
    if (me.value) me.value.must_change_password = false;
    forcePwdChange.value = false;
    setTimeout(() => {
      changePwdOpen.value = false;
      changePwdMsg.value = "";
    }, 1200);
  } catch (error) {
    changePwdMsg.value = error instanceof Error ? error.message : "修改失败";
  }
}

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

// Floating, auto-dismissing toasts instead of a static inline banner. Uses
// naive-ui's discrete API (not useMessage()) because this is a single root
// component, so there's no separate child component to host the provider.
const configProviderPropsRef = computed<ConfigProviderProps>(() => ({
  themeOverrides: naiveThemeOverrides,
}));
const { message } = createDiscreteApi(["message"], {
  configProviderProps: configProviderPropsRef,
  messageProviderProps: { placement: "top", duration: 3200, keepAliveOnHover: true },
});
const statusFilterOptions: SelectOption[] = [
  { label: "全部", value: "" },
  { label: "待确认", value: "pending" },
  { label: "已确认", value: "qualified" },
  { label: "已邮件", value: "emailed" },
  { label: "有兴趣", value: "interested" },
  { label: "转人工", value: "human_review" },
  { label: "已拒绝", value: "rejected" },
];
const leadTypeFilterOptions: SelectOption[] = [
  { label: "全部类型", value: "" },
  { label: "代理商", value: "distributor" },
  { label: "KOL", value: "kol" },
];
// Filter-dropdown options exclude the "全部" entry — FilterSelect renders its own
// reset row from the placeholder.
const statusSelectOptions = computed(() =>
  statusFilterOptions
    .filter((o) => o.value !== "")
    .map((o) => ({ value: String(o.value), label: String(o.label) })),
);
const leadTypeSelectOptions = computed(() =>
  leadTypeFilterOptions
    .filter((o) => o.value !== "")
    .map((o) => ({ value: String(o.value), label: String(o.label) })),
);

// Region/country options come from the DB facets (so every option returns
// results), ordered by the standard region taxonomy, then labeled 中文·English.
const regionSelectOptions = computed(() => {
  const counts = new Map(leadFacets.value.regions.map((r) => [r.value, r.count]));
  const order = STANDARD_REGIONS.map((r) => r.value);
  return leadFacets.value.regions
    .map((r) => ({ value: r.value, label: labelForRegion(r.value), count: r.count }))
    .sort((a, b) => {
      const ia = order.indexOf(a.value);
      const ib = order.indexOf(b.value);
      if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
      return b.count - a.count;
    })
    .map((o) => ({ ...o, count: counts.get(o.value) }));
});
const countrySelectOptions = computed(() =>
  leadFacets.value.countries.map((c) => ({
    value: c.value,
    label: labelForCountry(c.value),
    count: c.count,
  })),
);

const leadTypeLabels: Record<string, string> = {
  distributor: "代理商",
  kol: "KOL",
};
function leadTypeLabel(leadType: string | undefined): string {
  return leadTypeLabels[leadType || ""] || "未分类";
}
// Whitelist mirrors backend `_SORT_EXPRS` in backend/app/db.py — keep in sync.
const sortFieldOptions: SelectOption[] = [
  { label: "最新入库", value: "id" },
  { label: "评分", value: "score" },
  { label: "最近更新", value: "updated_at" },
  { label: "回复数", value: "reply_count" },
  { label: "公司名", value: "company_name" },
  { label: "国家", value: "country" },
  { label: "地区", value: "region" },
  { label: "类别", value: "category" },
  { label: "状态", value: "status" },
];
const providerOptions: SelectOption[] = [
  { label: "OpenAI", value: "openai" },
  { label: "DeepSeek", value: "deepseek" },
  { label: "百炼 (通义千问)", value: "bailian" },
];

// Friendly label + icon per business tool the Agent can call (agent/src/tools.ts).
// Unknown/future tool names fall back to the raw name + a generic wrench icon.
const AGENT_TOOL_META: Record<string, { label: string; icon: typeof FileText }> = {
  get_product_profile: { label: "读取产品画像", icon: FileText },
  get_scoring_rules: { label: "读取评分规则", icon: SlidersHorizontal },
  web_search: { label: "网页搜索", icon: Globe2 },
  fetch_url: { label: "抓取网页", icon: Link2 },
  search_leads: { label: "搜索线索", icon: Search },
  list_leads: { label: "查看线索库", icon: Database },
  add_leads: { label: "保存线索", icon: UserCheck },
  create_outreach_records: { label: "生成外联记录", icon: MailCheck },
  analyze_reply: { label: "分析回复", icon: MessageSquare },
  __skill__: { label: "技能加载", icon: BookOpen },
};
function toolMeta(name: string): { label: string; icon: typeof FileText } {
  return AGENT_TOOL_META[name] || { label: name, icon: Wrench };
}
function toggleToolTimeline(turn: AgentTurn): void {
  turn.toolTimelineExpanded = !turn.toolTimelineExpanded;
}
function toolsHaveRunning(turn: AgentTurn): boolean {
  return turn.toolCalls.some((c) => c.status === "running");
}
function toolsHaveError(turn: AgentTurn): boolean {
  return Boolean(turn.error) || turn.toolCalls.some((c) => c.status === "error");
}
// The tool currently executing — shown as a single live line ("正在搜索线索…")
// so the collapsed summary reads calmly instead of a growing list of rows.
function runningToolLabel(turn: AgentTurn): string {
  const running = [...turn.toolCalls].reverse().find((c) => c.status === "running");
  return running ? toolMeta(running.toolName).label : "调用工具";
}
function collapseToolTimelineIfClean(turn: AgentTurn): void {
  // Auto-expand only to surface a failure; otherwise stay collapsed as a
  // quiet one-line summary the user can open on demand.
  turn.toolTimelineExpanded = toolsHaveError(turn);
}
function renderTurnBlocks(text: string) {
  return parseMarkdown(text);
}
function applySuggestion(text: string): void {
  agentPrompt.value = text;
  nextTick(() => {
    autoGrowComposer();
    agentComposerRef.value?.focus();
  });
}
function focusComposer(): void {
  nextTick(() => agentComposerRef.value?.focus());
}
function autoGrowComposer(): void {
  const el = agentComposerRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 180) + "px";
}
// Track how close the user is to the bottom so streaming only auto-follows when
// they haven't scrolled up, and the "back to bottom" affordance appears when they have.
function onAgentChatScroll(): void {
  const el = agentChatScrollRef.value;
  if (!el) return;
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  agentPinnedToBottom.value = distanceFromBottom < 80;
  agentShowScrollDown.value = distanceFromBottom > 220;
}
function scrollAgentChatToBottom(opts: { force?: boolean; smooth?: boolean } = {}): void {
  const { force = false, smooth = false } = opts;
  // While streaming, respect a user who scrolled up to read earlier content.
  if (!force && !agentPinnedToBottom.value) return;
  nextTick(() => {
    const el = agentChatScrollRef.value;
    if (!el) return;
    if (smooth) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    else el.scrollTop = el.scrollHeight;
    agentPinnedToBottom.value = true;
    agentShowScrollDown.value = false;
  });
}

const leads = ref<Lead[]>([]);
const productProfile = ref<ProductProfile | null>(null);
const metrics = ref<Metrics>({
  total_leads: 0,
  interested_leads: 0,
  sent_emails: 0,
  human_review: 0,
});
const selectedLeadIds = ref<number[]>([]);
const filterRegion = ref("");
const filterCountry = ref("");
const filterStatus = ref("");
const filterLeadType = ref("");
// Distinct region/country values present in the DB (with counts), used to build
// the filter dropdowns so users only filter by values that actually exist.
const leadFacets = ref<{
  regions: { value: string; count: number }[];
  countries: { value: string; count: number }[];
}>({ regions: [], countries: [] });
const query = ref("");
const sortField = ref("id");
const sortDir = ref<"asc" | "desc">("desc");
const leadPage = ref(1);
const leadPageSize = ref(50);
const leadTotal = ref(0);
const leadTotalPages = ref(1);
const sortDropdownOpen = ref(false);
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
const detailLeadType = ref("");
const detailNotes = ref("");
const detailOutreach = ref<EmailEvent[]>([]);
const detailReplies = ref<ReplyAnalysis[]>([]);
const detailLoading = ref(false);
// Manual "paste a reply and analyze it" for the open lead (detail modal).
const detailReplyText = ref("");
const detailReplyBusy = ref(false);
const agentPrompt = ref("");
const agentSessionId = ref("default");
const agentSessions = ref<AgentSessionRecord[]>([]);
const agentTurnsBySession = reactive<Record<string, AgentTurn[]>>({});
const agentChatScrollRef = ref<HTMLElement | null>(null);
const agentComposerRef = ref<HTMLTextAreaElement | null>(null);
// Stick-to-bottom: only auto-follow the stream while the user is already near
// the bottom. If they scroll up to read, stop yanking them and offer a
// floating "back to bottom" button instead.
const agentPinnedToBottom = ref(true);
const agentShowScrollDown = ref(false);
let agentTurnSeq = 0;
let agentToolCallSeq = 0;
// One abort controller per session id, so different sessions can stream concurrently
// (each independently stoppable) without stepping on each other.
const agentAbortControllers = new Map<string, AbortController>();
const agentEditingUserTurnId = ref<number | null>(null);
const agentEditingText = ref("");
// Announced via a visually-hidden aria-live region — updated at meaningful
// STATE changes (not per character delta, which would overwhelm screen readers).
const agentLiveStatus = ref("");
const agentElapsedTick = ref(0);
let agentElapsedTimer: ReturnType<typeof setInterval> | undefined;
const agentSessionResultTotals = reactive<Record<string, { leadsAdded: number; draftsAdded: number }>>({});
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
  auto_send_enabled: false,
  send_daily_cap: 200,
  send_min_interval_seconds: 20,
  send_per_domain_daily_cap: 25,
  ai_content_generation: true,
  ai_content_ready: false,
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
const settingsTab = ref<"email" | "sync" | "agent" | "scoring">("email");
const owaUrl = computed(() => {
  const server = settings.value.email_server.trim();
  if (!server) return "";
  return server.startsWith("http://") || server.startsWith("https://") ? server : `https://${server}/owa`;
});
function openMailbox() {
  if (!owaUrl.value) return;
  window.open(owaUrl.value, "_blank", "noopener");
}
const drafts = ref<EmailEvent[]>([]);
const draftCount = ref(0);
const showOutreachPreview = ref(false);
const outreachLoading = ref(false);
const outreachPreviews = ref<Array<{ lead_id: number; company_name: string; email: string; subject: string; body: string }>>([]);
const showCreateLead = ref(false);
const createError = ref("");
const newLead = ref({ company_name: "", region: "", country: "", website: "", contact_name: "", email: "", category: "medical device distributor" });

// Add-lead form: standard enum dropdowns (mirrors backend/app/geo.py taxonomy).
const regionFormOptions = STANDARD_REGIONS.map((r) => ({ label: r.label, value: r.value }));
// Country options cascade off the chosen region: with a region selected the
// list narrows to that region's countries; with no region, all countries show
// grouped by region.
const countryFormOptions = computed(() => {
  const groups = countryGroupsByRegion();
  if (newLead.value.region) {
    const group = groups.find((g) => g.region === newLead.value.region);
    return group ? group.countries : [];
  }
  return groups.map((g) => ({
    type: "group" as const,
    label: g.label,
    key: g.region,
    children: g.countries,
  }));
});
// Picking a country auto-fills its standard region (still user-overridable).
function onNewLeadCountryChange(country: string): void {
  const region = COUNTRY_TO_REGION[country];
  if (region) newLead.value.region = region;
}
// Changing the region narrows the country list — drop a now-out-of-region pick.
function onNewLeadRegionChange(region: string): void {
  const current = newLead.value.country;
  if (current && COUNTRY_TO_REGION[current] !== region) {
    newLead.value.country = "";
  }
}
const activePage = ref<"workspace" | "agent" | "settings" | "admin" | "usage">("workspace");
const usageReportRef = ref<InstanceType<typeof UsageReport> | null>(null);
const editingSessionId = ref("");
const editingSessionTitle = ref("");
const agentConfigExpanded = ref(false);
const agentGuideOpen = ref(false);
const agentNotificationsOpen = ref(false);
const sidebarUserMenuOpen = ref(false);
const agentSkillDetailsOpen = ref(false);
// On narrow viewports the context rail collapses behind this toggle instead of
// disappearing entirely — desktop widths ignore it and always show the rail.
const agentContextOpen = ref(false);
const agentSessionSearch = ref("");

const selectedCount = computed(() => selectedLeadIds.value.length);
const topbarContent = computed(() => {
  if (activePage.value === "agent") {
    return {
      title: "渠道拓展 Agent",
      copy: "默认使用 overseas-distributor-prospecting skill，支持实时输出、联网搜索和线索入库。",
    };
  }
  if (activePage.value === "settings") {
    return {
      title: "设置",
      copy: "邮件回复自动同步、Agent 模型与 API 配置。",
    };
  }
  if (activePage.value === "usage") {
    return {
      title: "AI 用量看板",
      copy: "实时统计 Agent 对话、回复分析、邮件生成消耗的 token，掌握月度额度与走势。",
    };
  }
  if (activePage.value === "admin") {
    return {
      title: "用户与权限",
      copy: "自定义角色与操作级权限，并管理退订抑制名单与操作审计日志。",
    };
  }
  return {
    title: "海外渠道拓展系统",
    copy: "面向 SkyWalker TKA 的代理商发现、邮箱证据审阅、触达记录和回复处理。",
  };
});
const agentTurns = computed(() => agentTurnsBySession[agentSessionId.value] ?? []);
function isSessionBusy(sessionId: string): boolean {
  const turns = agentTurnsBySession[sessionId];
  if (!turns || turns.length === 0) return false;
  const last = turns[turns.length - 1];
  return last.role === "assistant" && last.pending;
}
// Busy state of the CURRENTLY VIEWED session only — a generation running in a
// different session doesn't disable this one's composer.
const agentLoading = computed(() => isSessionBusy(agentSessionId.value));
const agentElapsedSeconds = computed(() => {
  void agentElapsedTick.value; // reactive dependency for the 1s ticker
  const last = agentTurns.value[agentTurns.value.length - 1];
  if (!last || last.role !== "assistant" || !last.pending) return 0;
  return Math.max(0, Math.floor((Date.now() - last.startedAt) / 1000));
});
const agentSessionResultTotal = computed(
  () => agentSessionResultTotals[agentSessionId.value] ?? { leadsAdded: 0, draftsAdded: 0 },
);
// Edit/regenerate are only offered for the LAST message of each role — editing
// or redoing something buried mid-history would require branching history,
// which this chat model doesn't support.
const lastAgentTurnId = computed(() => {
  const turns = agentTurns.value;
  return turns.length > 0 ? turns[turns.length - 1].id : null;
});
const lastUserTurnId = computed(() => {
  const turns = agentTurns.value;
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    if (turns[i].role === "user") return turns[i].id;
  }
  return null;
});
const activeAgentSession = computed(() =>
  agentSessions.value.find((session) => session.id === agentSessionId.value)
);
const filteredAgentSessions = computed(() => {
  const keyword = agentSessionSearch.value.trim().toLowerCase();
  if (!keyword) return agentSessions.value;

  return agentSessions.value.filter((session) => {
    const matchesMeta = [session.title, session.id, shortAgentSessionId(session.id)].some(
      (value) => value.toLowerCase().includes(keyword),
    );
    if (matchesMeta) return true;
    const turns = agentTurnsBySession[session.id];
    return turns?.some((turn) => turn.text.toLowerCase().includes(keyword)) ?? false;
  });
});
const agentOutputText = computed(() => {
  return agentTurns.value
    .map((turn) => {
      if (turn.role === "user") return `You: ${turn.text}`;
      if (turn.error) return `Agent (失败): ${turn.error}`;
      return `Agent: ${turn.text}`;
    })
    .join("\n\n")
    .trim();
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
      ...(authToken.value ? { Authorization: `Bearer ${authToken.value}` } : {}),
      ...(options.headers || {}),
    },
  });

  if (response.status === 401) {
    // Token expired or invalid → drop back to the login screen.
    logout();
    throw new Error("登录已过期，请重新登录");
  }

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as T;
}

async function loadDashboard(): Promise<void> {
  const params = new URLSearchParams();
  if (filterRegion.value) params.set("region", filterRegion.value);
  if (filterCountry.value) params.set("country", filterCountry.value);
  if (filterStatus.value) params.set("status", filterStatus.value);
  if (filterLeadType.value) params.set("lead_type", filterLeadType.value);
  if (query.value) params.set("q", query.value);
  params.set("sort", sortField.value);
  params.set("order", sortDir.value);
  params.set("page", String(leadPage.value));
  params.set("page_size", String(leadPageSize.value));

  const [leadPayload, metricPayload] = await Promise.all([
    request<LeadListResponse>(`/leads?${params.toString()}`),
    request<Metrics>("/metrics"),
    loadLeadFacets(),
  ]);

  leads.value = leadPayload.leads;
  leadTotal.value = leadPayload.total;
  leadTotalPages.value = leadPayload.total_pages ?? 1;
  // The backend clamps an out-of-range page to the last valid page; mirror
  // that here so the pager stays in sync (e.g. after deleting the last row).
  if (leadPayload.page && leadPayload.page !== leadPage.value) {
    leadPage.value = leadPayload.page;
  }
  metrics.value = metricPayload;
  await loadDrafts();
}

async function loadLeadFacets(): Promise<void> {
  try {
    leadFacets.value = await request<{
      regions: { value: string; count: number }[];
      countries: { value: string; count: number }[];
    }>("/leads/facets");
  } catch {
    // Non-fatal: filters just fall back to whatever was already loaded.
  }
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
    if (result.ok) {
      message.success(result.sent ? "已批准并发送" : "已批准");
    } else {
      message.error("批准失败");
    }
    await loadDrafts();
    await loadDashboard();
  });
}

async function rejectDraft(eventId: number): Promise<void> {
  await runAction("outreach", async () => {
    await request(`/campaigns/drafts/${eventId}/reject`, { method: "POST" });
    message.success("已拒绝");
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
    message.success("线索已添加");
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
    message.success("已批量删除");
    await loadDashboard();
  });
}

async function deleteLead(leadId: number): Promise<void> {
  const confirmed = globalThis.confirm?.("确定删除这条线索及其关联的外联记录和回复分析？") ?? true;
  if (!confirmed) return;
  await runAction("qualify", async () => {
    await request(`/leads/${leadId}`, { method: "DELETE" });
    closeLeadDetail();
    message.success("线索已删除");
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
    message.success(`已批准 ${result.total} 条，成功发送 ${sentCount} 条`);
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

async function syncReplies(): Promise<void> {
  await runAction("sync", async () => {
    const payload = await request<{
      total_inbox: number;
      synced: number;
      skipped: number;
      analysis_failed?: number;
      ai_ready?: boolean;
      opted_out?: number;
      items: Array<{ lead_id: number; company: string; intent: string; auto_reply: boolean }>;
    }>("/replies/sync", { method: "POST" });

    // Replies that arrived but couldn't be classified because no LLM is
    // configured — surface this loudly so "0 synced" isn't misread as "no replies".
    if (payload.analysis_failed && payload.analysis_failed > 0) {
      message.warning(
        payload.ai_ready
          ? `有 ${payload.analysis_failed} 条回复分析失败，请稍后重试。`
          : `有 ${payload.analysis_failed} 条回复因未配置 AI 无法分析——请到「设置 → Agent」配置后重新同步。`,
      );
    }
    if (payload.synced > 0) {
      const companies = [...new Set(payload.items.map((i) => i.company))].join("、");
      const optOut = payload.opted_out ? `，${payload.opted_out} 个地址已按退订抑制` : "";
      message.success(`同步了 ${payload.synced} 条回复（${companies}）${optOut}`);
    } else if (!payload.analysis_failed) {
      message.success(`未发现新回复（扫描 ${payload.total_inbox} 封邮件）`);
    }
    await loadDashboard();
  });
}

// Analyze a reply the operator pasted into the open lead's detail panel.
async function analyzeDetailReply(): Promise<void> {
  const leadId = detailLeadId.value;
  const text = detailReplyText.value.trim();
  if (leadId === null || !text || detailReplyBusy.value) return;
  detailReplyBusy.value = true;
  try {
    const result = await request<ReplyAnalysis>("/replies/analyze", {
      method: "POST",
      body: JSON.stringify({ lead_id: leadId, reply_text: text }),
    });
    detailReplyText.value = "";
    message.success(
      `已分析：${result.requires_human ? "转人工" : formatStatus(result.intent)}`,
    );
    await loadDashboard(); // refresh the lead list first so the panel reads new status
    await openLeadDetail(leadId); // then reload reply/outreach history + status

  } catch (caught) {
    message.error(errorDetail(caught));
  } finally {
    detailReplyBusy.value = false;
  }
}

async function sendAgentPrompt(): Promise<void> {
  const message = agentPrompt.value.trim();
  const sessionKey = agentSessionId.value;
  if (!message || isSessionBusy(sessionKey)) return;

  const turns = agentTurnsBySession[sessionKey] ?? (agentTurnsBySession[sessionKey] = []);
  // Auto-name the session from its first message (unless the user already
  // gave it a custom name), the way ChatGPT/Claude title a new chat.
  if (turns.length === 0) {
    const session = agentSessions.value.find((item) => item.id === sessionKey);
    if (session && isDefaultSessionTitle(session.title)) {
      applyAgentSessionState(
        renameAgentSession(getAgentStorage(), currentAgentSessionState(), sessionKey, deriveSessionTitle(message)),
      );
    }
  }
  turns.push({
    id: ++agentTurnSeq,
    role: "user",
    text: message,
    toolCalls: [],
    pending: false,
    error: "",
    stopped: false,
    startedAt: Date.now(),
  });
  agentPrompt.value = "";
  nextTick(() => autoGrowComposer());
  scrollAgentChatToBottom({ force: true });
  focusComposer();

  await dispatchAssistantResponse(sessionKey, message);
}

function regenerateLastResponse(): void {
  const sessionKey = agentSessionId.value;
  if (isSessionBusy(sessionKey)) return;
  const turns = agentTurnsBySession[sessionKey];
  if (!turns || turns.length === 0) return;

  if (turns[turns.length - 1].role === "assistant") {
    turns.pop();
  }
  const lastUser = turns[turns.length - 1];
  if (!lastUser || lastUser.role !== "user") return;

  scrollAgentChatToBottom({ force: true });
  void dispatchAssistantResponse(sessionKey, lastUser.text);
}

function beginEditLastUserMessage(turn: AgentTurn): void {
  if (isSessionBusy(agentSessionId.value)) return;
  agentEditingUserTurnId.value = turn.id;
  agentEditingText.value = turn.text;
}

function cancelEditUserMessage(): void {
  agentEditingUserTurnId.value = null;
  agentEditingText.value = "";
}

function submitEditedMessage(): void {
  const sessionKey = agentSessionId.value;
  const newText = agentEditingText.value.trim();
  const editingId = agentEditingUserTurnId.value;
  if (!newText || editingId === null || isSessionBusy(sessionKey)) return;

  const turns = agentTurnsBySession[sessionKey];
  if (!turns) return;
  const editIndex = turns.findIndex((turn) => turn.id === editingId);
  if (editIndex === -1) return;

  // Editing is only supported for the LAST user message: drop it and any
  // reply that followed, then resend the edited text as a fresh turn.
  turns.splice(editIndex);
  cancelEditUserMessage();

  turns.push({
    id: ++agentTurnSeq,
    role: "user",
    text: newText,
    toolCalls: [],
    pending: false,
    error: "",
    stopped: false,
    startedAt: Date.now(),
  });
  scrollAgentChatToBottom({ force: true });
  void dispatchAssistantResponse(sessionKey, newText);
}

async function dispatchAssistantResponse(sessionKey: string, message: string): Promise<void> {
  const turns = agentTurnsBySession[sessionKey] ?? (agentTurnsBySession[sessionKey] = []);
  const assistantTurn: AgentTurn = {
    id: ++agentTurnSeq,
    role: "assistant",
    text: "",
    toolCalls: [],
    pending: true,
    error: "",
    stopped: false,
    startedAt: Date.now(),
    toolTimelineExpanded: false,
  };
  turns.push(assistantTurn);

  agentError.value = "";
  if (sessionKey === agentSessionId.value) {
    agentLiveStatus.value = "已发送，等待 Agent 响应";
    scrollAgentChatToBottom({ force: true });
  }
  startAgentElapsedTicker();

  const leadsBefore = metrics.value.total_leads;
  const draftsBefore = draftCount.value;

  const controller = new AbortController();
  agentAbortControllers.set(sessionKey, controller);

  try {
    const response = await fetch(`${apiBase}/agent/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authToken.value ? { Authorization: `Bearer ${authToken.value}` } : {}),
      },
      body: JSON.stringify({
        message,
        session_id: sessionKey || undefined,
      }),
      signal: controller.signal,
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
      // The user pressed stop: exit even if aborting the fetch didn't reject
      // this read (some upstreams keep flushing). Cancel to release the stream.
      if (assistantTurn.stopped) {
        void reader.cancel().catch(() => undefined);
        return;
      }
      buffer = consumeAgentStreamBuffer(
        buffer + decoder.decode(value, { stream: true }),
        assistantTurn,
      );
    }
    if (assistantTurn.stopped) return;
    buffer = consumeAgentStreamBuffer(buffer + decoder.decode(), assistantTurn);
    if (buffer.trim()) {
      handleAgentSseFrame(buffer, assistantTurn);
    }
    if (sessionKey === agentSessionId.value) agentLiveStatus.value = "回复已完成";
    await loadDashboard();

    const leadsAdded = Math.max(0, metrics.value.total_leads - leadsBefore);
    const draftsAdded = Math.max(0, draftCount.value - draftsBefore);
    if (leadsAdded > 0 || draftsAdded > 0) {
      assistantTurn.resultSummary = { leadsAdded, draftsAdded };
      const totals = agentSessionResultTotals[sessionKey] ?? { leadsAdded: 0, draftsAdded: 0 };
      agentSessionResultTotals[sessionKey] = {
        leadsAdded: totals.leadsAdded + leadsAdded,
        draftsAdded: totals.draftsAdded + draftsAdded,
      };
    }
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === "AbortError") {
      assistantTurn.stopped = true;
      if (sessionKey === agentSessionId.value) agentLiveStatus.value = "已停止生成";
    } else {
      assistantTurn.error = caught instanceof Error ? caught.message : "Agent 请求失败";
      agentError.value = assistantTurn.error;
      if (sessionKey === agentSessionId.value) agentLiveStatus.value = `请求失败：${assistantTurn.error}`;
    }
  } finally {
    for (const call of assistantTurn.toolCalls) {
      if (call.status === "running") call.status = assistantTurn.stopped ? "error" : "done";
    }
    assistantTurn.pending = false;
    collapseToolTimelineIfClean(assistantTurn);
    if (agentAbortControllers.get(sessionKey) === controller) {
      agentAbortControllers.delete(sessionKey);
    }
    stopAgentElapsedTickerIfIdle();
    if (sessionKey === agentSessionId.value) scrollAgentChatToBottom();
  }
}

function startAgentElapsedTicker(): void {
  if (agentElapsedTimer) return;
  agentElapsedTimer = setInterval(() => {
    agentElapsedTick.value += 1;
  }, 1000);
}

function stopAgentElapsedTickerIfIdle(): void {
  if (agentAbortControllers.size > 0) return;
  if (agentElapsedTimer) {
    clearInterval(agentElapsedTimer);
    agentElapsedTimer = undefined;
  }
}

function stopAgentPrompt(sessionId: string = agentSessionId.value): void {
  agentAbortControllers.get(sessionId)?.abort();
  agentAbortControllers.delete(sessionId);
  // Optimistic UI: flip out of the "generating" state immediately. Some
  // providers (reasoning models) keep the upstream stream open well past the
  // visible answer, so aborting the fetch may not reject the in-flight read
  // right away — don't make the user wait for that to update the composer.
  const turns = agentTurnsBySession[sessionId];
  const last = turns?.[turns.length - 1];
  if (last && last.role === "assistant" && last.pending) {
    last.pending = false;
    last.stopped = true;
    for (const call of last.toolCalls) {
      if (call.status === "running") call.status = "error";
    }
    collapseToolTimelineIfClean(last);
  }
  if (sessionId === agentSessionId.value) agentLiveStatus.value = "已停止生成";
  stopAgentElapsedTickerIfIdle();
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
    message.error("生成邮件失败");
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
    message.success(payload.note || `已处理 ${payload.sent_count} 条外联`);
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
      body: JSON.stringify({ status: "pending", notes: "重新激活" }),
    });
    message.success("线索已重新激活");
    await loadDashboard();
  });
}

async function markQualified(leadId: number): Promise<void> {
  await runAction("qualify", async () => {
    await request<Lead>(`/leads/${leadId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "qualified", notes: "人工确认：渠道匹配，进入商务跟进。" }),
    });
    message.success("已标记为 qualified");
    await loadDashboard();
  });
}

const detailLead = computed(() =>
  detailLeadId.value ? leads.value.find((l) => l.id === detailLeadId.value) ?? null : null
);

// Two-letter monogram for the detail-modal avatar.
const detailInitials = computed(() => {
  const name = (detailLead.value?.company_name || "").trim();
  if (!name) return "—";
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
});

// Unified, newest-first timeline merging outreach events and reply analyses so
// the modal reads as "what has happened with this lead" rather than two lists.
type TimelineItem =
  | { key: string; kind: "outreach"; at: string; ev: EmailEvent }
  | { key: string; kind: "reply"; at: string; r: ReplyAnalysis };
const detailTimeline = computed<TimelineItem[]>(() => {
  const items: TimelineItem[] = [];
  for (const ev of detailOutreach.value) items.push({ key: `o${ev.id}`, kind: "outreach", at: ev.created_at || "", ev });
  for (const r of detailReplies.value) items.push({ key: `r${r.id}`, kind: "reply", at: r.created_at || "", r });
  return items.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
});

function outreachStatusMeta(s: string): { label: string; type: "success" | "error" | "warning" | "info" | "default" } {
  switch (s) {
    case "sent": return { label: "已发送", type: "success" };
    case "send_failed": return { label: "发送失败", type: "error" };
    case "queued": return { label: "排队中", type: "warning" };
    case "suppressed": return { label: "已抑制", type: "error" };
    case "draft": return { label: "草稿", type: "default" };
    default: return { label: "已记录", type: "info" };
  }
}

async function openLeadDetail(leadId: number): Promise<void> {
  detailLeadId.value = leadId;
  detailLoading.value = true;
  const lead = leads.value.find((l) => l.id === leadId);
  detailStatus.value = lead?.status ?? "";
  detailLeadType.value = lead?.lead_type ?? "";
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
  detailReplyText.value = "";
}

// Outreach from the detail panel: close it first so the preview modal isn't
// layered on top of the detail modal.
function outreachFromDetail(): void {
  const id = detailLeadId.value;
  closeLeadDetail();
  if (id !== null) void sendOutreachSingle(id);
}

async function saveLeadDetail(): Promise<void> {
  if (detailLeadId.value === null) return;
  const lead = leads.value.find((l) => l.id === detailLeadId.value);
  if (
    lead &&
    lead.status === detailStatus.value &&
    (lead.lead_type || "") === (detailLeadType.value || "") &&
    (lead.notes || "") === (detailNotes.value || "")
  ) {
    return; // no change
  }
  await request<Lead>(`/leads/${detailLeadId.value!}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: detailStatus.value || undefined,
      lead_type: detailLeadType.value || undefined,
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

/** Reload the lead list after a filter/sort/search change, always starting
 * from page 1 so the user lands on the top of the new result set. */
function reloadLeadsFromFirstPage(): void {
  leadPage.value = 1;
  runAction("dashboard", loadDashboard);
}

function onLeadPageChange(page: number): void {
  if (page === leadPage.value) return;
  leadPage.value = page;
  runAction("dashboard", loadDashboard);
}

function onLeadPageSizeChange(size: number): void {
  if (size === leadPageSize.value) return;
  leadPageSize.value = size;
  // Keep the top item roughly in view when switching page size.
  leadPage.value = 1;
  runAction("dashboard", loadDashboard);
}

function selectSortField(field: string): void {
  sortDropdownOpen.value = false;
  if (sortField.value === field) return;
  sortField.value = field;
  reloadLeadsFromFirstPage();
}

function toggleSortDir(): void {
  sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  reloadLeadsFromFirstPage();
}

function toggleSortDropdown(): void {
  sortDropdownOpen.value = !sortDropdownOpen.value;
}

const currentSortLabel = computed(() => {
  return sortFieldOptions.find((opt) => opt.value === sortField.value)?.label
    ?? "最新入库";
});

function handleSortOutsideClick(event: MouseEvent): void {
  if (!sortDropdownOpen.value) return;
  const target = event.target as Node | null;
  if (!target) return;
  const container = document.querySelector(".toolbar-sort");
  if (container && !container.contains(target)) {
    sortDropdownOpen.value = false;
  }
}

function setLeadSelection(leadId: number, checked: boolean): void {
  if (checked) {
    selectedLeadIds.value = [...new Set([...selectedLeadIds.value, leadId])];
  } else {
    selectedLeadIds.value = selectedLeadIds.value.filter((id) => id !== leadId);
  }
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

// Backend HTTP errors arrive as a JSON body like {"detail": "..."}; surface the
// human-readable detail instead of the raw JSON string.
function errorDetail(caught: unknown): string {
  if (caught instanceof Error) {
    try {
      const parsed = JSON.parse(caught.message) as { detail?: string };
      if (parsed && typeof parsed.detail === "string" && parsed.detail) return parsed.detail;
    } catch {
      // message wasn't JSON — fall through to the raw message
    }
    return caught.message;
  }
  return "请求失败";
}

async function runAction(
  actionName: NonNullable<typeof currentAction.value>,
  action: () => Promise<void>,
): Promise<void> {
  loading.value = true;
  currentAction.value = actionName;
  try {
    await action();
  } catch (caught) {
    message.error(errorDetail(caught));
  } finally {
    loading.value = false;
    currentAction.value = null;
  }
}

function formatStatus(status: string): string {
  const labels: Record<string, string> = {
    pending: "待确认",
    new: "待确认", // legacy leads created before the status/match-level split
    emailed: "已邮件",
    interested: "有兴趣",
    human_review: "转人工",
    rejected: "已拒绝",
    needs_review: "待复核",
    qualified: "已确认",
  };
  return labels[status] || status;
}

function statusClass(status: string): string {
  return `status status-${status.replace("_", "-")}`;
}

// AI 匹配度徽章：与线索状态解耦，仅表达“AI 觉得这条有多匹配”。
// reject / 空 不显示（状态已是「已拒绝」，无需重复）。
function matchLevelMeta(
  level?: string,
): { label: string; type: "default" | "success" | "warning" | "error" } | null {
  switch (level) {
    case "strong":
      return { label: "强匹配", type: "success" };
    case "medium":
      return { label: "中匹配", type: "warning" };
    case "weak":
      return { label: "弱匹配", type: "default" };
    default:
      return null;
  }
}

// A lead that's been emailed but hasn't replied yet is "awaiting reply"; past a
// week with no reply it's worth a follow-up nudge. Gives the operator a way to
// find who to chase without a whole new status.
function isAwaitingReply(lead: Lead): boolean {
  return lead.status === "emailed" && (lead.reply_count || 0) === 0;
}
function outreachAgeDays(lead: Lead): number | null {
  if (!lead.last_outreach_at) return null;
  const t = new Date(lead.last_outreach_at).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / 86_400_000));
}

// Leads ready for (first) outreach: found or confirmed but not yet emailed /
// rejected. Agent-confirmed (`qualified`) leads belong here too — they're the
// prime targets to send to, so they get the same per-row 外联 button.
function canOutreach(status: string): boolean {
  return status === "pending" || status === "new" || status === "qualified";
}

function statusTagType(status: string): "default" | "info" | "success" | "warning" | "error" {
  if (["interested", "qualified"].includes(status)) return "success";
  if (["pending", "new", "human_review", "needs_review"].includes(status)) return "warning";
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

function showPage(page: "workspace" | "agent" | "settings" | "admin" | "usage", sectionId?: string): void {
  activePage.value = page;
  agentGuideOpen.value = false;
  agentNotificationsOpen.value = false;
  sidebarUserMenuOpen.value = false;
  const hash = page === "agent" ? "agent" : page === "settings" ? "settings" : page === "usage" ? "usage" : sectionId || "overview";
  globalThis.history?.replaceState(null, "", `#${hash}`);

  if (page === "settings") {
    // Land on a tab the user is actually allowed to see.
    if (!can("settings.manage") && can("agent.config")) {
      settingsTab.value = "agent";
    } else if (can("settings.manage")) {
      settingsTab.value = "email";
    }
    if (can("settings.manage")) loadSettings();
    return;
  }
  if (page === "agent") {
    scrollAgentChatToBottom({ force: true });
    focusComposer();
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
    void loadQueueStatus();
  } catch {
    // use defaults
  } finally {
    settingsLoading.value = false;
  }
}

interface QueueStatus {
  queued: number;
  sent_today: number;
  daily_cap: number;
  min_interval_seconds: number;
  per_domain_daily_cap: number;
  email_configured: boolean;
}
const queueStatus = ref<QueueStatus | null>(null);
async function loadQueueStatus(): Promise<void> {
  try {
    queueStatus.value = await request<QueueStatus>("/campaigns/queue");
  } catch {
    queueStatus.value = null;
  }
}

async function saveSettings(): Promise<void> {
  if (settingsSaving.value) return;
  settingsSaving.value = true;
  try {
    const body: Record<string, unknown> = {
      sync_enabled: settings.value.sync_enabled,
      sync_interval_minutes: settings.value.sync_interval_minutes,
      auto_send_enabled: settings.value.auto_send_enabled,
      send_daily_cap: settings.value.send_daily_cap,
      send_min_interval_seconds: settings.value.send_min_interval_seconds,
      send_per_domain_daily_cap: settings.value.send_per_domain_daily_cap,
      ai_content_generation: settings.value.ai_content_generation,
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
    message.success("设置已保存");
  } catch (caught) {
    message.error(caught instanceof Error ? caught.message : "设置保存失败");
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

function toggleAgentSkillDetails(): void {
  agentSkillDetailsOpen.value = !agentSkillDetailsOpen.value;
}

async function copyAgentOutput(): Promise<void> {
  if (!agentOutputText.value) {
    message.warning("暂无 Agent 输出可复制");
    return;
  }
  await copyTextToClipboard(agentOutputText.value, "Agent 输出已复制");
}

function downloadAgentOutput(): void {
  if (!agentOutputText.value) {
    message.warning("暂无 Agent 输出可导出");
    return;
  }

  const documentRef = globalThis.document;
  const urlApi = globalThis.URL;
  if (!documentRef || !urlApi?.createObjectURL) {
    message.warning("当前环境不支持文件导出");
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
  message.success("Agent 输出已导出为 Markdown");
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
      message.success(successMessage);
      return;
    }
  } catch {
    // Fall through to the textarea fallback below.
  }

  if (fallbackCopyText(text)) {
    message.success(successMessage);
  } else {
    message.error("复制失败，请手动选择内容");
  }
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

function startNewAgentSession(): void {
  // Creating a session never conflicts with a generation running in another
  // session — each session streams and can be stopped independently.
  applyAgentSessionState(
    createNextAgentSession(getAgentStorage(), currentAgentSessionState()),
  );
  agentError.value = "";
  scrollAgentChatToBottom({ force: true });
  focusComposer();
}

function switchAgentSession(sessionId: string): void {
  if (sessionId === agentSessionId.value) return;
  applyAgentSessionState(
    activateAgentSession(getAgentStorage(), currentAgentSessionState(), sessionId),
  );
  agentError.value = "";
  scrollAgentChatToBottom({ force: true });
  focusComposer();
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
  const session = agentSessions.value.find((item) => item.id === sessionId);
  const title = session?.title || "当前会话";
  const busy = isSessionBusy(sessionId);
  const confirmMessage = busy
    ? `删除会话"${title}"？该会话正在生成中，将同时停止生成。`
    : `删除会话"${title}"？`;
  const confirmed = globalThis.confirm?.(confirmMessage) ?? true;
  if (!confirmed) return;

  // Don't let a deleted session's request keep running in the background —
  // stop it before the turns it would mutate disappear.
  agentAbortControllers.get(sessionId)?.abort();
  agentAbortControllers.delete(sessionId);

  applyAgentSessionState(
    deleteAgentSession(getAgentStorage(), currentAgentSessionState(), sessionId),
  );
  delete agentTurnsBySession[sessionId];
  delete agentSessionResultTotals[sessionId];
  message.success("已删除 Agent 会话");
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

// ── Chat history persistence (survives page reloads) ─────────────────────────
const AGENT_HISTORY_STORAGE_KEY = "medbot.agent.history";
const AGENT_HISTORY_MAX_TURNS_PER_SESSION = 60;
let agentHistoryPersistTimer: ReturnType<typeof setTimeout> | undefined;

function loadAgentHistoryFromStorage(): void {
  const storage = getAgentStorage();
  const raw = storage?.getItem(AGENT_HISTORY_STORAGE_KEY);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw) as Record<string, AgentTurn[]>;
    if (typeof parsed !== "object" || parsed === null) return;
    for (const [sessionId, turns] of Object.entries(parsed)) {
      if (!Array.isArray(turns)) continue;
      // A turn still "pending" when the page was closed was never really
      // finished — surface it as stopped rather than an eternal spinner.
      agentTurnsBySession[sessionId] = turns.map((turn) => ({
        ...turn,
        pending: false,
        stopped: turn.pending ? true : turn.stopped,
        // Reloaded turns are already finished — start their tool timelines
        // collapsed unless something in them actually failed.
        toolTimelineExpanded:
          Boolean(turn.error) || turn.toolCalls.some((c) => c.status === "error"),
      }));
      let maxTurnId = 0;
      let maxToolCallId = 0;
      for (const turn of turns) {
        maxTurnId = Math.max(maxTurnId, turn.id);
        for (const call of turn.toolCalls) {
          maxToolCallId = Math.max(maxToolCallId, call.id);
        }
      }
      // Reseed both id counters past anything rehydrated from storage so newly
      // created turns/tool-calls after reload never collide with old :key ids.
      agentTurnSeq = Math.max(agentTurnSeq, maxTurnId);
      agentToolCallSeq = Math.max(agentToolCallSeq, maxToolCallId);
    }
  } catch {
    // Corrupt/foreign storage payload — start fresh rather than crash.
  }
}

function scheduleAgentHistoryPersist(): void {
  if (agentHistoryPersistTimer) clearTimeout(agentHistoryPersistTimer);
  agentHistoryPersistTimer = setTimeout(persistAgentHistoryNow, 400);
}

function persistAgentHistoryNow(): void {
  const storage = getAgentStorage();
  if (!storage) return;
  const trimmed: Record<string, AgentTurn[]> = {};
  for (const [sessionId, turns] of Object.entries(agentTurnsBySession)) {
    trimmed[sessionId] = turns.slice(-AGENT_HISTORY_MAX_TURNS_PER_SESSION);
  }
  try {
    storage.setItem(AGENT_HISTORY_STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // Storage full or unavailable (e.g. private browsing) — skip silently,
    // history just won't survive this reload.
  }
}

function consumeAgentStreamBuffer(buffer: string, turn: AgentTurn): string {
  let remaining = buffer;
  let boundary = remaining.indexOf("\n\n");
  while (boundary >= 0) {
    const frame = remaining.slice(0, boundary);
    if (frame.trim()) {
      handleAgentSseFrame(frame, turn);
    }
    remaining = remaining.slice(boundary + 2);
    boundary = remaining.indexOf("\n\n");
  }
  return remaining;
}

function handleAgentSseFrame(frame: string, turn: AgentTurn): void {
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
    handleAgentStreamEvent(eventName, JSON.parse(dataLines.join("\n")), turn);
  } catch (caught) {
    turn.error = caught instanceof Error ? caught.message : "流式事件解析失败";
  }
}

function handleAgentStreamEvent(
  eventName: string,
  payload: Record<string, unknown>,
  turn: AgentTurn,
): void {
  // Once the user has stopped a turn, ignore any late frames the upstream
  // stream is still flushing so a "stopped" reply doesn't keep growing.
  if (turn.stopped) return;

  // Concurrency guard: a background session's events must never yank the
  // globally-viewed session or pop a toast about a conversation the user
  // isn't currently looking at.
  const viewing = isViewingTurn(turn);

  if (eventName === "start") {
    if (viewing && typeof payload.session_id === "string") {
      applyIncomingAgentSession(payload.session_id);
    }
    return;
  }

  if (eventName === "delta") {
    turn.text += typeof payload.text === "string" ? payload.text : "";
    if (viewing) scrollAgentChatToBottom();
    return;
  }

  if (eventName === "agent_event") {
    const event = asAgentEvent(payload.event);
    if (!event) return;
    applyAgentEventToTurn(turn, event);
    if (viewing) scrollAgentChatToBottom();
    return;
  }

  if (eventName === "done") {
    if (typeof payload.message === "string" && payload.message) {
      turn.text = payload.message;
    }
    if (viewing && typeof payload.session_id === "string") {
      applyIncomingAgentSession(payload.session_id);
    }
    for (const call of turn.toolCalls) {
      if (call.status === "running") call.status = "done";
    }
    if (viewing) message.success("Agent 已返回渠道拓展建议");
    return;
  }

  if (eventName === "error") {
    turn.error = typeof payload.detail === "string" ? payload.detail : "Agent 流式请求失败";
    if (viewing) agentError.value = turn.error;
  }
}

function isViewingTurn(turn: AgentTurn): boolean {
  return agentTurns.value.includes(turn);
}

function applyAgentEventToTurn(turn: AgentTurn, event: AgentEvent): void {
  const type = String(event.type || "");
  const toolName = String(event.toolName || event.tool_name || event.name || "");

  if (type === "tool_execution_start" && toolName) {
    turn.toolCalls.push({ id: ++agentToolCallSeq, toolName, status: "running" });
    if (isViewingTurn(turn)) agentLiveStatus.value = `正在执行：${toolMeta(toolName).label}`;
    return;
  }

  if ((type === "tool_execution_end" || type === "tool_execution_done") && toolName) {
    const running = [...turn.toolCalls].reverse().find(
      (call) => call.toolName === toolName && call.status === "running",
    );
    if (running) {
      running.status = "done";
    } else {
      turn.toolCalls.push({ id: ++agentToolCallSeq, toolName, status: "done" });
    }
    if (isViewingTurn(turn)) agentLiveStatus.value = `已完成：${toolMeta(toolName).label}`;
    return;
  }

  if (type === "tool_execution_error" && toolName) {
    const running = [...turn.toolCalls].reverse().find(
      (call) => call.toolName === toolName && call.status === "running",
    );
    if (running) running.status = "error";
    return;
  }

  if (type === "skill_loaded") {
    const skill = event.skillName || event.skill_name;
    turn.toolCalls.push({
      id: ++agentToolCallSeq,
      toolName: "__skill__",
      status: "done",
      detail: skill ? `已加载技能：${String(skill)}` : "已加载技能",
    });
    return;
  }

  if (type === "setup_error") {
    turn.error = `Agent 未配置：缺少 ${String(event.missing || "API Key")}，请在右侧完成配置`;
  }
}

function asAgentEvent(value: unknown): AgentEvent | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as AgentEvent)
    : null;
}

async function bootstrapAfterLogin(): Promise<void> {
  // Load only what the signed-in user is allowed to see.
  const tasks: Promise<unknown>[] = [];
  if (can("leads.view")) {
    tasks.push(
      runAction("dashboard", async () => {
        await Promise.all([loadProductProfile(), loadDashboard()]);
      }),
    );
  } else {
    activePage.value = can("agent.use") ? "agent" : "settings";
  }
  if (can("agent.config")) tasks.push(loadAgentConfig());
  await Promise.all(tasks);
}

onMounted(async () => {
  applyAgentSessionState(loadAgentSessionState(getAgentStorage()));
  loadAgentHistoryFromStorage();
  if (globalThis.location?.hash === "#agent") {
    activePage.value = "agent";
  } else if (globalThis.location?.hash === "#usage" && can("settings.manage")) {
    activePage.value = "usage";
  }
  if (authToken.value) {
    const ok = await fetchMe();
    if (ok) {
      await bootstrapAfterLogin();
      maybeForcePasswordChange();
    }
  }
  document.addEventListener("mousedown", handleSortOutsideClick);
  document.addEventListener("keydown", handleAgentEscToStop);
});

// Esc stops the running Agent generation (the composer is disabled mid-stream,
// so this lives on the document rather than the textarea).
function handleAgentEscToStop(event: KeyboardEvent): void {
  if (event.key === "Escape" && activePage.value === "agent" && agentLoading.value) {
    event.preventDefault();
    stopAgentPrompt();
  }
}

watch(agentTurnsBySession, scheduleAgentHistoryPersist, { deep: true });

onBeforeUnmount(() => {
  if (agentHistoryPersistTimer) clearTimeout(agentHistoryPersistTimer);
  if (agentElapsedTimer) clearInterval(agentElapsedTimer);
  document.removeEventListener("mousedown", handleSortOutsideClick);
  document.removeEventListener("keydown", handleAgentEscToStop);
});
</script>

<template>
  <n-config-provider :theme-overrides="naiveThemeOverrides">
  <n-global-style />

  <!-- Login gate: the whole app is hidden until authenticated. -->
  <div v-if="!isAuthenticated" class="login-overlay">
    <form class="login-card" @submit.prevent="doLogin">
      <div class="login-brand">
        <div class="brand-mark">SW</div>
        <div>
          <strong>SkyWalker 海外渠道拓展系统</strong>
          <span>请登录后使用</span>
        </div>
      </div>
      <label class="field">
        <span>用户名</span>
        <input v-model="loginUsername" type="text" autocomplete="username" placeholder="用户名" />
      </label>
      <label class="field">
        <span>密码</span>
        <input v-model="loginPassword" type="password" autocomplete="current-password" placeholder="密码" />
      </label>
      <p v-if="loginError" class="login-error">{{ loginError }}</p>
      <button class="login-submit" type="submit" :disabled="loginLoading">
        {{ loginLoading ? "登录中..." : "登 录" }}
      </button>
    </form>
  </div>

  <div v-else class="app-shell app-frame">
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
          v-if="can('agent.use')"
          type="button"
          :class="{ active: activePage === 'agent' }"
          @click="showPage('agent')"
        >
          <span class="nav-icon"><Bot :size="18" aria-hidden="true" /></span>
          渠道拓展Agent
        </button>
        <button
          v-if="can('leads.view')"
          type="button"
          :class="{ active: activePage === 'workspace' }"
          @click="showPage('workspace', 'overview')"
        >
          <span class="nav-icon"><Home :size="18" aria-hidden="true" /></span>
          线索管理
          <span v-if="draftCount > 0" class="nav-badge">{{ draftCount }}</span>
        </button>
        <button
          v-if="can('settings.manage')"
          type="button"
          :class="{ active: activePage === 'usage' }"
          @click="showPage('usage')"
        >
          <span class="nav-icon"><Gauge :size="18" aria-hidden="true" /></span>
          AI 用量
        </button>
        <button
          v-if="can('users.manage')"
          type="button"
          :class="{ active: activePage === 'admin' }"
          @click="showPage('admin')"
        >
          <span class="nav-icon"><ShieldCheck :size="18" aria-hidden="true" /></span>
          用户与权限
        </button>
        <button
          v-if="can('settings.manage') || can('agent.config')"
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
          <span class="user-avatar">{{ (me?.display_name || me?.username || "U").slice(0, 1) }}</span>
          <div>
            <strong>{{ me?.display_name || me?.username }}</strong>
            <small>{{ me?.is_superadmin ? "超级管理员" : (me?.roles?.map(r => r.name).join(" / ") || "无角色") }}</small>
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
          <button type="button" role="menuitem" @click="changePwdOpen = true; sidebarUserMenuOpen = false">修改密码</button>
          <button type="button" role="menuitem" @click="refreshDashboardFromUserMenu">刷新数据</button>
          <button type="button" role="menuitem" @click="logout">退出登录</button>
        </div>
      </div>
    </aside>

    <section class="main-workspace workspace-shell">
      <header id="overview" class="topbar workspace-command">
        <div>
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
          <template v-else-if="activePage === 'usage'">
            <span class="live-badge">
              <Gauge :size="16" aria-hidden="true" />
              实时用量
            </span>
            <n-button class="ghost-button" secondary @click="usageReportRef?.reload()">
              <template #icon>
                <n-icon><RefreshCw /></n-icon>
              </template>
              刷新
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
        <section class="content-area" aria-label="线索和回复工作区">
          <section
            v-if="activePage === 'agent'"
            class="ag-shell"
            aria-labelledby="agent-title"
          >
            <h2 id="agent-title" class="sr-only">渠道拓展 Agent 对话</h2>

            <aside class="ag-sidebar" aria-label="会话列表">
              <button
                type="button"
                class="ag-new-chat"
                @click="startNewAgentSession"
              >
                <Plus :size="16" aria-hidden="true" /> 新建会话
              </button>

              <p class="ag-sidebar-label">历史会话</p>

              <label class="ag-sidebar-search">
                <Search :size="14" aria-hidden="true" />
                <input v-model="agentSessionSearch" type="text" placeholder="搜索会话..." />
              </label>

              <div class="ag-session-list" role="list">
                <article
                  v-for="session in filteredAgentSessions"
                  :key="session.id"
                  :class="['ag-session-row', { active: session.id === agentSessionId }]"
                  role="listitem"
                >
                  <form
                    v-if="editingSessionId === session.id"
                    class="ag-session-rename"
                    @submit.prevent="saveAgentSessionTitle(session.id)"
                  >
                    <input v-model="editingSessionTitle" aria-label="会话名称" maxlength="80" />
                    <button type="submit" aria-label="保存会话名称"><Check :size="14" aria-hidden="true" /></button>
                    <button type="button" aria-label="取消重命名" @click="cancelEditAgentSession"><X :size="14" aria-hidden="true" /></button>
                  </form>
                  <template v-else>
                    <button
                      type="button"
                      class="ag-session-btn"
                      @click="switchAgentSession(session.id)"
                    >
                      <MessageSquare :size="15" class="ag-session-icon" aria-hidden="true" />
                      <span class="ag-session-text">
                        <strong>{{ session.title }}</strong>
                        <small>
                          {{ formatAgentSessionTime(session.updatedAt) }}
                          <i v-if="isSessionBusy(session.id)" class="ag-session-busy-dot" aria-label="生成中"></i>
                        </small>
                      </span>
                    </button>
                    <div class="ag-session-actions">
                      <button
                        type="button"
                        :aria-label="`重命名 ${session.title}`"
                        @click="beginEditAgentSession(session)"
                      >
                        <Pencil :size="13" aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        class="danger"
                        :aria-label="`删除 ${session.title}`"
                        @click="removeAgentSession(session.id)"
                      >
                        <Trash2 :size="13" aria-hidden="true" />
                      </button>
                    </div>
                  </template>
                </article>
                <div v-if="filteredAgentSessions.length === 0" class="ag-session-empty">
                  没有匹配的会话
                </div>
              </div>
            </aside>

            <section class="ag-chat" aria-label="对话">
              <header class="ag-chat-bar">
                <div class="ag-chat-bar-title">
                  <strong>{{ activeAgentSession?.title || "当前会话" }}</strong>
                  <span class="ag-skill-tag">overseas-distributor-prospecting</span>
                </div>
                <div class="ag-chat-bar-actions">
                  <button type="button" title="复制会话内容" :disabled="!agentOutputText" @click="copyAgentOutput">
                    <Check :size="15" aria-hidden="true" />
                  </button>
                  <button type="button" title="导出为 Markdown" :disabled="!agentOutputText" @click="downloadAgentOutput">
                    <ExternalLink :size="15" aria-hidden="true" />
                  </button>
                  <button type="button" title="复制会话 ID" @click="copyAgentSessionId">
                    <Clock3 :size="15" aria-hidden="true" />
                  </button>
                </div>
              </header>

              <div class="sr-only" aria-live="polite" aria-atomic="true">{{ agentLiveStatus }}</div>

              <div ref="agentChatScrollRef" class="ag-chat-scroll" @scroll.passive="onAgentChatScroll">
                <div v-if="agentTurns.length === 0" class="ag-chat-empty">
                  <span class="ag-chat-empty-icon"><Bot :size="30" aria-hidden="true" /></span>
                  <strong>向 Agent 发起一个渠道拓展任务</strong>
                  <p>Agent 会调用网页搜索、抓取、线索评分等工具，并把执行过程实时显示在下面。</p>
                  <div class="ag-suggest-grid">
                    <button
                      type="button"
                      class="ag-suggest-card"
                      @click="applySuggestion('帮我找 SkyWalker TKA 在印度的渠道商，优先找骨科植入物、关节置换、TKA 分销商，要求公开邮箱和来源证据。')"
                    >
                      <span class="ag-suggest-icon" style="--c: #6366f1"><Globe2 :size="17" aria-hidden="true" /></span>
                      <span class="ag-suggest-text">
                        <strong>找印度的 TKA 渠道商</strong>
                        <small>骨科植入物 / 关节置换分销商，附公开邮箱与证据</small>
                      </span>
                    </button>
                    <button
                      type="button"
                      class="ag-suggest-card"
                      @click="applySuggestion('搜索德国的骨科机器人代理商，并给出匹配理由和证据来源。')"
                    >
                      <span class="ag-suggest-icon" style="--c: #0ea5e9"><Search :size="17" aria-hidden="true" /></span>
                      <span class="ag-suggest-text">
                        <strong>搜德国骨科机器人代理商</strong>
                        <small>给出匹配理由和公开证据来源</small>
                      </span>
                    </button>
                    <button
                      type="button"
                      class="ag-suggest-card"
                      @click="applySuggestion('帮我分析这条客户回复的意向：暂不确定预算，需要先了解产品资质。')"
                    >
                      <span class="ag-suggest-icon" style="--c: #10b981"><MessageSquare :size="17" aria-hidden="true" /></span>
                      <span class="ag-suggest-text">
                        <strong>分析一条客户回复</strong>
                        <small>判断意向、下一步动作与是否转人工</small>
                      </span>
                    </button>
                  </div>
                </div>

                <template v-for="turn in agentTurns" :key="turn.id">
                  <div v-if="turn.role === 'user'" class="ag-turn ag-turn-user">
                    <form
                      v-if="agentEditingUserTurnId === turn.id"
                      class="ag-edit-form"
                      @submit.prevent="submitEditedMessage"
                    >
                      <textarea v-model="agentEditingText" rows="2" aria-label="编辑消息"></textarea>
                      <div class="ag-edit-actions">
                        <button type="button" class="ag-edit-cancel" @click="cancelEditUserMessage">取消</button>
                        <button type="submit" class="ag-edit-submit" :disabled="!agentEditingText.trim()">重新发送</button>
                      </div>
                    </form>
                    <template v-else>
                      <div class="ag-bubble ag-bubble-user">{{ turn.text }}</div>
                      <button
                        v-if="turn.id === lastUserTurnId && !agentLoading"
                        type="button"
                        class="ag-turn-tool-btn"
                        title="编辑并重新发送"
                        @click="beginEditLastUserMessage(turn)"
                      >
                        <Pencil :size="13" aria-hidden="true" />
                      </button>
                    </template>
                  </div>
                  <div v-else class="ag-turn ag-turn-assistant">
                    <span class="ag-avatar"><Bot :size="16" aria-hidden="true" /></span>
                    <div class="ag-turn-body">
                      <div
                        v-if="turn.toolCalls.length > 0"
                        class="ag-tools"
                        :class="{ 'is-running': toolsHaveRunning(turn) }"
                      >
                        <button
                          type="button"
                          class="ag-tools-summary"
                          :aria-expanded="turn.toolTimelineExpanded ? 'true' : 'false'"
                          @click="toggleToolTimeline(turn)"
                        >
                          <Loader2
                            v-if="toolsHaveRunning(turn)"
                            :size="13"
                            class="ag-spin ag-tools-lead"
                            aria-hidden="true"
                          />
                          <span
                            v-else
                            class="ag-tools-lead-badge"
                            :class="{ 'has-error': toolsHaveError(turn) }"
                          >
                            <X v-if="toolsHaveError(turn)" :size="11" aria-hidden="true" />
                            <Check v-else :size="11" aria-hidden="true" />
                          </span>
                          <span class="ag-tools-summary-text">
                            <template v-if="toolsHaveRunning(turn)">正在{{ runningToolLabel(turn) }}…</template>
                            <template v-else>使用了 {{ turn.toolCalls.length }} 个工具<template v-if="toolsHaveError(turn)"> · 有失败</template></template>
                          </span>
                          <ChevronDown
                            :size="13"
                            class="ag-tools-caret"
                            :class="{ open: turn.toolTimelineExpanded }"
                            aria-hidden="true"
                          />
                        </button>

                        <transition name="ag-tools-expand">
                          <ol v-if="turn.toolTimelineExpanded" class="ag-tools-steps">
                            <li
                              v-for="call in turn.toolCalls"
                              :key="call.id"
                              :class="['ag-tools-step', `is-${call.status}`]"
                            >
                              <span class="ag-tools-node">
                                <Loader2 v-if="call.status === 'running'" :size="10" class="ag-spin" aria-hidden="true" />
                                <X v-else-if="call.status === 'error'" :size="10" aria-hidden="true" />
                                <Check v-else :size="10" aria-hidden="true" />
                              </span>
                              <component :is="toolMeta(call.toolName).icon" :size="13" class="ag-tools-icon" aria-hidden="true" />
                              <span class="ag-tools-name">{{ call.detail || toolMeta(call.toolName).label }}</span>
                            </li>
                          </ol>
                        </transition>
                      </div>

                      <div v-if="turn.text" class="ag-bubble ag-bubble-assistant">
                        <MarkdownRenderer :blocks="renderTurnBlocks(turn.text)" />
                      </div>
                      <div v-else-if="turn.pending" class="ag-typing-wrap">
                        <div class="ag-typing" aria-hidden="true"><span></span><span></span><span></span></div>
                        <small v-if="agentElapsedSeconds >= 3" class="ag-typing-elapsed">
                          {{ turn.toolCalls.some((c) => c.status === 'running') ? '工具执行中' : '模型思考中' }}
                          · {{ agentElapsedSeconds }}s
                          <template v-if="agentElapsedSeconds >= 15">（思考模型可能需要 30–90 秒）</template>
                        </small>
                      </div>

                      <p v-if="turn.error" class="ag-turn-error">{{ turn.error }}</p>
                      <p v-else-if="turn.stopped" class="ag-turn-stopped">已停止生成</p>

                      <div v-if="turn.resultSummary" class="ag-result-chip">
                        <CheckCircle2 :size="13" aria-hidden="true" />
                        本轮
                        <template v-if="turn.resultSummary.leadsAdded > 0">新增 {{ turn.resultSummary.leadsAdded }} 条线索</template>
                        <template v-if="turn.resultSummary.leadsAdded > 0 && turn.resultSummary.draftsAdded > 0"> · </template>
                        <template v-if="turn.resultSummary.draftsAdded > 0">生成 {{ turn.resultSummary.draftsAdded }} 封草稿</template>
                      </div>

                      <button
                        v-if="turn.id === lastAgentTurnId && !turn.pending && !agentLoading"
                        type="button"
                        class="ag-turn-tool-btn"
                        title="重新生成"
                        @click="regenerateLastResponse"
                      >
                        <RefreshCw :size="13" aria-hidden="true" /> 重新生成
                      </button>
                    </div>
                  </div>
                </template>
              </div>

              <transition name="ag-fade">
                <button
                  v-if="agentShowScrollDown"
                  type="button"
                  class="ag-scroll-down"
                  aria-label="回到最新消息"
                  title="回到最新消息"
                  @click="scrollAgentChatToBottom({ force: true, smooth: true })"
                >
                  <ChevronDown :size="18" aria-hidden="true" />
                </button>
              </transition>

              <form class="ag-composer" @submit.prevent="sendAgentPrompt">
                <div class="ag-composer-field" :class="{ 'is-busy': agentLoading }">
                  <textarea
                    ref="agentComposerRef"
                    v-model="agentPrompt"
                    class="ag-composer-input"
                    placeholder="向 Agent 发起渠道拓展任务…"
                    rows="1"
                    :disabled="agentLoading"
                    @input="autoGrowComposer"
                    @keydown.enter.exact.prevent="sendAgentPrompt"
                  ></textarea>
                  <button
                    v-if="agentLoading"
                    type="button"
                    class="ag-send-button ag-stop-button"
                    aria-label="停止生成"
                    title="停止生成"
                    @click="stopAgentPrompt()"
                  >
                    <Square :size="14" fill="currentColor" aria-hidden="true" />
                  </button>
                  <button
                    v-else
                    type="submit"
                    class="ag-send-button"
                    :disabled="!agentPrompt.trim()"
                    aria-label="发送"
                  >
                    <Send :size="17" aria-hidden="true" />
                  </button>
                </div>
                <div class="ag-composer-hint">
                  <span v-if="agentLoading" class="ag-hint-busy"><kbd>Esc</kbd> 停止生成</span>
                  <span v-else><kbd>Enter</kbd> 发送 · <kbd>Shift</kbd>+<kbd>Enter</kbd> 换行</span>
                  <span class="ag-composer-skill"><Bot :size="12" aria-hidden="true" /> overseas-distributor-prospecting</span>
                </div>
              </form>
            </section>

            <button
              type="button"
              class="ag-context-toggle"
              :aria-expanded="agentContextOpen"
              aria-label="打开 Agent 配置面板"
              @click="agentContextOpen = !agentContextOpen"
            >
              <SlidersHorizontal :size="18" aria-hidden="true" />
            </button>
            <div v-if="agentContextOpen" class="ag-context-scrim" @click="agentContextOpen = false"></div>

            <aside class="ag-context" :class="{ 'ag-context-visible': agentContextOpen }" aria-label="Agent 上下文">
              <button type="button" class="ag-context-close" aria-label="关闭面板" @click="agentContextOpen = false">
                <X :size="16" aria-hidden="true" />
              </button>

              <section
                v-if="agentSessionResultTotal.leadsAdded > 0 || agentSessionResultTotal.draftsAdded > 0"
                class="ag-card"
                aria-label="本会话战绩"
              >
                <div class="ag-card-head"><strong>本会话战绩</strong></div>
                <div class="ag-stat-row">
                  <div class="ag-stat"><strong>{{ agentSessionResultTotal.leadsAdded }}</strong><span>新增线索</span></div>
                  <div class="ag-stat"><strong>{{ agentSessionResultTotal.draftsAdded }}</strong><span>生成草稿</span></div>
                </div>
              </section>

              <section class="ag-card" aria-label="Agent 配置">
                <div class="ag-card-head">
                  <strong>Agent 配置</strong>
                  <span :class="['ag-status-dot', agentConfig?.has_api_key ? 'on' : 'off']">
                    <i></i>{{ agentConfig?.has_api_key ? "已连接" : "未连接" }}
                  </span>
                </div>
                <dl class="ag-kv">
                  <div><dt>Provider</dt><dd>{{ agentProviderName }}</dd></div>
                  <div><dt>Model</dt><dd>{{ agentModelName }}</dd></div>
                  <div><dt>API Key</dt><dd>{{ agentConfig?.api_key_preview || "未配置" }}</dd></div>
                </dl>
                <button type="button" class="ag-link-button" @click="agentConfigExpanded = !agentConfigExpanded">
                  {{ agentConfigExpanded ? "收起配置" : "编辑配置" }}
                </button>
                <div v-if="agentConfigExpanded" class="ag-config-form">
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
                    <template #icon><n-icon><Save /></n-icon></template>
                    {{ agentConfigSaving ? "保存中..." : "保存配置" }}
                  </n-button>
                  <p v-if="agentConfigNotice" class="notice">{{ agentConfigNotice }}</p>
                  <p v-if="agentConfigError" class="error">{{ agentConfigError }}</p>
                </div>
              </section>

              <section class="ag-card" aria-label="当前技能">
                <div class="ag-card-head">
                  <strong>当前技能</strong>
                  <button type="button" class="ag-link-button" @click="toggleAgentSkillDetails">
                    {{ agentSkillDetailsOpen ? "收起" : "详情" }}
                  </button>
                </div>
                <span class="ag-tag-success">overseas-distributor-prospecting</span>
                <p class="ag-hint">海外经销商线索挖掘与分析</p>
                <dl v-if="agentSkillDetailsOpen" class="ag-kv">
                  <div><dt>适用产品</dt><dd>SkyWalker TKA / 骨科手术机器人 / 医疗器械渠道</dd></div>
                  <div><dt>默认流程</dt><dd>产品画像、国家市场搜索、线索评分、公开证据汇总</dd></div>
                  <div><dt>输出格式</dt><dd>Markdown 报告 + 可入库线索</dd></div>
                </dl>
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
              @keyup.enter="reloadLeadsFromFirstPage()"
            />
            <button
              v-if="query"
              class="toolbar-search-clear"
              type="button"
              aria-label="清除搜索"
              @click="query = ''; reloadLeadsFromFirstPage()"
            >
              <X :size="13" />
            </button>
          </div>

          <div class="toolbar-filters">
            <FilterSelect
              v-model="filterStatus"
              :options="statusSelectOptions"
              placeholder="全部状态"
              @change="reloadLeadsFromFirstPage()"
            />
            <FilterSelect
              v-model="filterLeadType"
              :options="leadTypeSelectOptions"
              placeholder="全部类型"
              :icon="Tag"
              @change="reloadLeadsFromFirstPage()"
            />
            <FilterSelect
              v-model="filterRegion"
              :options="regionSelectOptions"
              placeholder="全部地区"
              :icon="Globe2"
              @change="reloadLeadsFromFirstPage()"
            />
            <FilterSelect
              v-model="filterCountry"
              :options="countrySelectOptions"
              placeholder="全部国家"
              :icon="MapPin"
              searchable
              search-placeholder="搜索国家…"
              @change="reloadLeadsFromFirstPage()"
            />
          </div>

          <div class="toolbar-sort" aria-label="排序">
            <button
              type="button"
              class="sort-chip sort-chip-trigger"
              :class="{ active: sortField !== 'id', open: sortDropdownOpen }"
              :aria-haspopup="'listbox'"
              :aria-expanded="sortDropdownOpen"
              @click.stop="toggleSortDropdown"
            >
              <SlidersHorizontal :size="13" class="sort-chip-icon" aria-hidden="true" />
              <span class="sort-chip-label">{{ currentSortLabel }}</span>
              <ChevronDown :size="13" class="sort-chip-caret" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="sort-chip sort-chip-dir"
              :class="{ active: sortDir === 'asc' }"
              :aria-label="sortDir === 'desc' ? '当前降序，点击切为升序' : '当前升序，点击切为降序'"
              :title="sortDir === 'desc' ? '降序' : '升序'"
              @click="toggleSortDir"
            >
              <ArrowDown v-if="sortDir === 'desc'" :size="13" />
              <ArrowUp v-else :size="13" />
            </button>
            <div v-if="sortDropdownOpen" class="sort-dropdown" role="listbox">
              <button
                v-for="opt in sortFieldOptions"
                :key="String(opt.value)"
                type="button"
                class="sort-dropdown-item"
                :class="{ active: sortField === opt.value }"
                role="option"
                :aria-selected="sortField === opt.value"
                @click="selectSortField(String(opt.value))"
              >
                <span class="sort-dropdown-label">{{ opt.label }}</span>
                <Check v-if="sortField === opt.value" :size="14" class="sort-dropdown-check" />
              </button>
            </div>
          </div>
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
              <div class="lh-type-stats" aria-label="线索分类统计">
                <span class="lh-stat lh-stat-core" :title="'全部线索总数'">
                  <i class="lh-dot"></i>线索总数
                  <b>{{ metrics.total_leads ?? 0 }}</b>
                </span>
                <span class="lh-stat lh-stat-interested" :title="'状态为有意向的线索数'">
                  <i class="lh-dot"></i>有意向
                  <b>{{ metrics.interested_leads ?? 0 }}</b>
                </span>
                <span class="lh-stat lh-stat-sent" :title="'已发送的外联邮件数'">
                  <i class="lh-dot"></i>已发邮件
                  <b>{{ metrics.sent_emails ?? 0 }}</b>
                </span>
                <span class="lh-stat lh-stat-review" :title="'待人工审核的线索数'">
                  <i class="lh-dot"></i>待人工
                  <b>{{ metrics.human_review ?? 0 }}</b>
                </span>
                <span class="lh-stat lh-stat-distributor">
                  <i class="lh-dot"></i>代理商
                  <b>{{ metrics.distributor_leads ?? 0 }}</b>
                  <em>已确认 {{ metrics.distributor_qualified ?? 0 }}</em>
                </span>
                <span class="lh-stat lh-stat-kol">
                  <i class="lh-dot"></i>KOL
                  <b>{{ metrics.kol_leads ?? 0 }}</b>
                  <em>已确认 {{ metrics.kol_qualified ?? 0 }}</em>
                </span>
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
              <span v-else>{{ leadTotal }} 条</span>
            </div>
          </div>

          <n-empty
            v-if="leads.length === 0"
            class="empty-state"
            description="前往「渠道拓展 Agent」用对话搜索线索，结果会显示在这里。"
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
                <n-tag
                  v-if="matchLevelMeta(lead.match_level)"
                  :type="matchLevelMeta(lead.match_level)!.type"
                  size="small"
                  round
                  :bordered="false"
                >
                  {{ matchLevelMeta(lead.match_level)!.label }}
                </n-tag>
                <n-tag :type="lead.lead_type === 'kol' ? 'warning' : 'info'" size="small" round :bordered="false">
                  {{ leadTypeLabel(lead.lead_type) }}
                </n-tag>
                <span
                  v-if="isAwaitingReply(lead)"
                  class="lead-await-chip"
                  :class="{ stale: (outreachAgeDays(lead) ?? 0) >= 7 }"
                >
                  <Clock3 :size="11" aria-hidden="true" />
                  {{ (outreachAgeDays(lead) ?? 0) >= 7 ? "待跟进" : "待回复" }}<template v-if="outreachAgeDays(lead) !== null"> · {{ outreachAgeDays(lead) }}天</template>
                </span>
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
              <button v-if="canOutreach(lead.status)" class="lead-action-btn primary" @click="sendOutreachSingle(lead.id)"><Send :size="13" />外联</button>
              <button v-if="lead.status === 'emailed' && (lead.reply_count || 0) > 0" class="lead-action-btn" @click="goToReplyForLead(lead.id)"><MailCheck :size="13" />回复</button>
              <button v-if="['pending', 'new', 'emailed', 'interested', 'human_review', 'needs_review'].includes(lead.status)" class="lead-action-btn" @click="markQualified(lead.id)"><UserCheck :size="13" />确认</button>
              <button v-if="lead.status === 'rejected'" class="lead-action-btn" @click="reactivateLead(lead.id)"><RefreshCw :size="13" />激活</button>
              <button class="lead-action-btn danger" @click="deleteLead(lead.id)"><Trash2 :size="13" /></button>
            </div>
          </article>

          <div v-if="leadTotal > 0" class="lead-list-pager">
            <span class="pager-summary">共 {{ leadTotal }} 条</span>
            <n-pagination
              :page="leadPage"
              :page-size="leadPageSize"
              :item-count="leadTotal"
              :page-sizes="[20, 50, 100, 200]"
              show-size-picker
              :disabled="loading"
              @update:page="onLeadPageChange"
              @update:page-size="onLeadPageSizeChange"
            />
          </div>
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
            <header class="ld-header">
              <div class="ld-ident">
                <div class="ld-avatar" aria-hidden="true">{{ detailInitials }}</div>
                <div class="ld-ident-main">
                  <h2 id="lead-detail-title">{{ detailLead?.company_name }}</h2>
                  <div class="ld-badges">
                    <n-tag :type="statusTagType(detailLead?.status || '')" size="small" round :bordered="false">
                      {{ formatStatus(detailLead?.status || '') }}
                    </n-tag>
                    <n-tag
                      v-if="matchLevelMeta(detailLead?.match_level)"
                      :type="matchLevelMeta(detailLead?.match_level)!.type"
                      size="small"
                      round
                      :bordered="false"
                    >
                      {{ matchLevelMeta(detailLead?.match_level)!.label }}
                    </n-tag>
                    <n-tag :type="detailLead?.lead_type === 'kol' ? 'warning' : 'info'" size="small" round :bordered="false">
                      {{ leadTypeLabel(detailLead?.lead_type) }}
                    </n-tag>
                    <span class="ld-score"><Star :size="12" aria-hidden="true" />{{ detailLead?.score ?? '—' }}</span>
                  </div>
                  <div class="ld-meta">
                    <span><MapPin :size="13" aria-hidden="true" />{{ detailLead?.country === detailLead?.region ? detailLead?.country : `${detailLead?.country} · ${detailLead?.region}` }}</span>
                    <span><Mail :size="13" aria-hidden="true" />{{ detailLead?.email }}</span>
                    <span v-if="detailLead?.contact_name"><User :size="13" aria-hidden="true" />{{ detailLead?.contact_name }}</span>
                  </div>
                </div>
              </div>
              <button class="ld-close" type="button" aria-label="关闭详情" @click="closeLeadDetail">
                <X :size="18" aria-hidden="true" />
              </button>
            </header>

            <div class="ld-body">
              <div class="ld-info">
                <div class="ld-reason">
                  <span class="ld-info-label"><Sparkles :size="13" aria-hidden="true" /> 匹配理由</span>
                  <p>{{ detailLead?.match_reason || '—' }}</p>
                </div>
                <div class="ld-info-links">
                  <a
                    v-if="detailLead?.website"
                    class="ld-link"
                    :href="detailLead.website"
                    target="_blank"
                    rel="noreferrer"
                  ><Globe2 :size="14" aria-hidden="true" /> 访问官网 <ExternalLink :size="11" aria-hidden="true" /></a>
                  <a
                    v-if="detailLead?.source"
                    class="ld-link"
                    :href="detailLead.source"
                    target="_blank"
                    rel="noreferrer"
                  ><Link2 :size="14" aria-hidden="true" /> 查看来源 <ExternalLink :size="11" aria-hidden="true" /></a>
                  <span class="ld-cat"><Tag :size="12" aria-hidden="true" /> {{ detailLead?.category }}</span>
                </div>
              </div>

              <div class="ld-grid">
                <div class="ld-col">
                  <div class="ld-card">
                    <p class="ld-card-title">状态与跟进</p>
                    <label class="field">
                      <span>状态</span>
                      <n-select v-model:value="detailStatus" :options="statusFilterOptions.filter(o => o.value !== '')" @update:value="saveLeadDetail" />
                    </label>
                    <label class="field">
                      <span>分类</span>
                      <n-select v-model:value="detailLeadType" :options="leadTypeFilterOptions.filter(o => o.value !== '')" @update:value="saveLeadDetail" />
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
                    <div class="ld-actions">
                      <n-button
                        v-if="detailLead && canOutreach(detailLead.status)"
                        class="primary-button"
                        type="primary"
                        @click="outreachFromDetail"
                      >
                        <template #icon><n-icon><Send /></n-icon></template>
                        发送外联
                      </n-button>
                      <n-button class="ghost-button danger-action" secondary @click="deleteLead(detailLeadId!)">
                        <template #icon><n-icon><Trash2 /></n-icon></template>
                        删除
                      </n-button>
                    </div>
                  </div>

                  <div class="ld-card ld-reply-card">
                    <p class="ld-card-title"><MessageSquare :size="14" aria-hidden="true" /> 分析收到的回复</p>
                    <span class="ld-card-sub">把对方的邮件回复粘贴进来，由 AI 判断意向并更新线索状态。</span>
                    <n-input
                      v-model:value="detailReplyText"
                      type="textarea"
                      :autosize="{ minRows: 3, maxRows: 8 }"
                      placeholder="粘贴对方的回复原文…"
                    />
                    <n-button
                      class="primary-button ld-reply-btn"
                      type="primary"
                      :loading="detailReplyBusy"
                      :disabled="!detailReplyText.trim() || detailReplyBusy"
                      @click="analyzeDetailReply"
                    >
                      <template #icon><n-icon><MessageSquare /></n-icon></template>
                      {{ detailReplyBusy ? "分析中…" : "AI 分析回复" }}
                    </n-button>
                  </div>
                </div>

                <div class="ld-col ld-col-timeline">
                  <p class="ld-card-title">互动记录</p>
                  <div v-if="detailLoading" class="ld-empty">加载中…</div>
                  <div v-else-if="detailTimeline.length === 0" class="ld-empty">
                    <Inbox :size="24" aria-hidden="true" />
                    <span>暂无外联或回复记录</span>
                  </div>
                  <ol v-else class="ld-timeline">
                    <li v-for="item in detailTimeline" :key="item.key" :class="['ld-tl', item.kind]">
                      <span class="ld-tl-dot" aria-hidden="true">
                        <MailCheck v-if="item.kind === 'reply'" :size="12" />
                        <Send v-else :size="11" />
                      </span>
                      <div class="ld-tl-card">
                        <template v-if="item.kind === 'outreach'">
                          <div class="ld-tl-head">
                            <n-tag :type="outreachStatusMeta(item.ev.status).type" size="small" round :bordered="false">
                              {{ outreachStatusMeta(item.ev.status).label }}
                            </n-tag>
                            <small>{{ formatTime(item.ev.created_at) }}</small>
                          </div>
                          <strong>{{ item.ev.subject }}</strong>
                          <span class="ld-tl-to">收件人：{{ item.ev.sent_to }}</span>
                          <p>{{ item.ev.body.slice(0, 180) }}{{ item.ev.body.length > 180 ? '…' : '' }}</p>
                        </template>
                        <template v-else>
                          <div class="ld-tl-head">
                            <n-tag :type="statusTagType(item.r.requires_human ? 'human_review' : item.r.intent)" size="small" round :bordered="false">
                              {{ item.r.requires_human ? '转人工' : formatStatus(item.r.intent) }}
                            </n-tag>
                            <small>{{ Math.round(item.r.confidence * 100) }}% · {{ formatTime(item.r.created_at) }}</small>
                          </div>
                          <blockquote v-if="item.r.reply_text" class="reply-quote">{{ item.r.reply_text }}</blockquote>
                          <p>{{ item.r.summary }}</p>
                          <p class="history-next">{{ item.r.next_action }}</p>
                        </template>
                      </div>
                    </li>
                  </ol>
                </div>
              </div>
            </div>
          </section>
        </div>
      </section>

        <UsageReport
          v-if="activePage === 'usage' && can('settings.manage')"
          ref="usageReportRef"
          :request="request"
        />

        <AdminPanel
          v-if="activePage === 'admin' && can('users.manage')"
          :request="request"
        />

        <section
          v-if="activePage === 'settings'"
          class="settings-page"
          aria-labelledby="settings-title"
        >
          <div class="settings-tabs">
            <button v-if="can('settings.manage')" :class="['settings-tab', { active: settingsTab === 'email' }]" @click="settingsTab = 'email'">邮箱</button>
            <button v-if="can('settings.manage')" :class="['settings-tab', { active: settingsTab === 'sync' }]" @click="settingsTab = 'sync'">同步</button>
            <button v-if="can('agent.config')" :class="['settings-tab', { active: settingsTab === 'agent' }]" @click="settingsTab = 'agent'">Agent</button>
            <button v-if="can('settings.manage')" :class="['settings-tab', { active: settingsTab === 'scoring' }]" @click="settingsTab = 'scoring'">评分规则</button>
          </div>

          <ScoringRulesSettings v-if="settingsTab === 'scoring' && can('settings.manage')" :request="request" />

          <section v-if="settingsTab === 'email' && can('settings.manage')" class="settings-card">
            <div class="settings-card-head">
              <div>
                <p class="panel-label">邮箱配置</p>
                <h3>Exchange 邮件服务</h3>
                <p>配置 EWS 连接信息，用于发送外联和同步回复。</p>
              </div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <button
                  type="button"
                  class="queue-refresh"
                  :disabled="!owaUrl"
                  :title="owaUrl ? `打开 ${owaUrl}` : '请先填写 SMTP 服务器'"
                  @click="openMailbox"
                >
                  打开邮箱网页
                </button>
                <n-tag :type="settings.email_user ? 'success' : 'default'" size="small" round :bordered="false">
                  {{ settings.email_user ? '已配置' : '未配置' }}
                </n-tag>
              </div>
            </div>
            <div class="settings-agent-grid">
              <label class="field"><span>SMTP 服务器</span><n-input v-model:value="settings.email_server" placeholder="mail.microport.com.cn" /></label>
              <label class="field"><span>邮箱账号</span><n-input v-model:value="settings.email_user" placeholder="OB_OSD@microport.com" /></label>
              <label class="field"><span>邮箱密码</span><n-input v-model:value="settingsEmailPasswordInput" autocomplete="off" :placeholder="settings.has_email_password ? '已设置 (不显示)' : '输入密码'" type="password" show-password-on="click" /></label>
            </div>
          </section>

          <section v-if="settingsTab === 'sync' && can('settings.manage')" class="settings-card">
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

            <div class="settings-card-head" style="margin-top: 24px;">
              <div>
                <p class="panel-label">AI 自动发送</p>
                <h3>让 AI 自行发送首封邮件</h3>
                <p>开启后，Agent 生成的首封冷邮件会直接通过 Exchange 发出，无需人工逐封审核。关闭时（默认）一律存为草稿，需人工批准后发送。回复仍按人工审核规则触发转人工。</p>
              </div>
              <n-tag :type="settings.auto_send_enabled ? 'warning' : 'default'" size="small" round :bordered="false">
                {{ settings.auto_send_enabled ? '自动发送' : '草稿模式' }}
              </n-tag>
            </div>
            <label class="toggle-field"><n-checkbox v-model:checked="settings.auto_send_enabled">允许 AI 自动发送首封邮件</n-checkbox></label>
            <p class="setting-hint" v-if="settings.auto_send_enabled" style="color: var(--warning-color, #d97706);">⚠️ 已开启自动发送：Agent 创建外联后将进入发送队列，按下方节流速率发出。</p>

            <div class="settings-card-head" style="margin-top: 24px;">
              <div>
                <p class="panel-label">发送节流</p>
                <h3>发送队列与速率限制</h3>
                <p>外联邮件不会瞬时群发，而是进入队列按速率发出，避免触发垃圾邮件过滤、保护域名声誉。退订/退信地址自动跳过。</p>
              </div>
            </div>
            <div v-if="queueStatus" class="queue-stats">
              <div class="queue-stat"><strong>{{ queueStatus.queued }}</strong><span>排队中</span></div>
              <div class="queue-stat"><strong>{{ queueStatus.sent_today }}</strong><span>今日已发</span></div>
              <div class="queue-stat"><strong>{{ queueStatus.daily_cap }}</strong><span>每日上限</span></div>
              <button class="queue-refresh" type="button" @click="loadQueueStatus">刷新</button>
            </div>
            <p v-if="queueStatus && !queueStatus.email_configured" class="setting-hint" style="color: var(--warning-color, #d97706);">⚠️ 邮箱未配置，队列中的邮件暂不会发出，配置邮箱后会自动开始发送。</p>
            <label class="field"><span>每日发送上限（封）</span><n-input-number v-model:value="settings.send_daily_cap" :min="1" :max="5000" /></label>
            <label class="field"><span>发送最小间隔（秒）</span><n-input-number v-model:value="settings.send_min_interval_seconds" :min="1" :max="3600" /></label>
            <label class="field"><span>同一域名每日上限（封）</span><n-input-number v-model:value="settings.send_per_domain_daily_cap" :min="1" :max="1000" /></label>
            <p class="setting-hint">推荐：起步阶段间隔 20–60 秒、每日 100–200 封、单域名 ≤25 封，随着域名信誉建立再逐步放宽。</p>
          </section>

          <section v-if="settingsTab === 'agent' && can('agent.config')" class="settings-card">
            <div class="settings-card-head">
              <div>
                <p class="panel-label">AI Agent</p>
                <h3>模型与 API 配置</h3>
                <p>此处的 AI 模型 / API Key 同时用于三处：<strong>Agent 对话</strong>、<strong>外联邮件生成</strong>、<strong>回复意图分析</strong>。</p>
              </div>
            </div>

            <label class="toggle-field">
              <n-checkbox v-model:checked="settings.ai_content_generation">用 AI 生成外联邮件正文</n-checkbox>
            </label>
            <p class="setting-hint">
              开启后，外联邮件正文优先由上面配置的 LLM 生成，调用失败或未配置时回退到固定模板；关闭则始终用模板。
              <br />
              <strong>回复意图分析</strong>始终由 LLM 完成（无关键词兜底）——未配置 API Key 时会<strong>直接报错</strong>，不做规则猜测。
            </p>
            <p v-if="!settings.ai_content_ready" class="setting-hint" style="color: var(--warning-color, #d97706);">
              ⚠️ 后端设置与 Agent 配置里都没有可用的 API Key：外联邮件将回退到模板，且<strong>回复分析会直接报错</strong>。请在下方填写 API Key。
            </p>

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
            <label class="field"><span>国家 *</span>
              <n-select
                v-model:value="newLead.country"
                :options="countryFormOptions"
                filterable
                placeholder="选择国家"
                @update:value="onNewLeadCountryChange"
              />
            </label>
          </div>
          <div class="create-lead-row">
            <label class="field"><span>地区 *</span>
              <n-select
                v-model:value="newLead.region"
                :options="regionFormOptions"
                filterable
                placeholder="选择地区（选国家后自动填充）"
                @update:value="onNewLeadRegionChange"
              />
            </label>
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

  <!-- Change-password modal -->
  <div v-if="changePwdOpen" class="modal-overlay" @click.self="forcePwdChange || (changePwdOpen = false)">
    <form class="modal-card" @submit.prevent="submitChangePassword">
      <h3>{{ forcePwdChange ? "请先修改初始密码" : "修改密码" }}</h3>
      <p v-if="forcePwdChange" class="setting-hint" style="margin: -4px 0 4px; color: var(--warning-color, #d97706);">
        为了账号安全，首次登录或密码被重置后必须设置新密码才能继续使用。
      </p>
      <label class="field"><span>原密码</span><input v-model="oldPassword" type="password" autocomplete="current-password" /></label>
      <label class="field"><span>新密码（至少 6 位）</span><input v-model="newPassword" type="password" autocomplete="new-password" /></label>
      <p v-if="changePwdMsg" class="login-error">{{ changePwdMsg }}</p>
      <div class="modal-actions">
        <button v-if="!forcePwdChange" type="button" class="btn-ghost" @click="changePwdOpen = false">取消</button>
        <button type="submit" class="login-submit">保存</button>
      </div>
    </form>
  </div>
  </n-config-provider>
</template>
