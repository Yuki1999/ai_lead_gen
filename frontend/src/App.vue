<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { router } from "@/router";
import {
  AlertTriangle,
  Bell,
  Bot,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Copy,
  Database,
  Edit3,
  ExternalLink,
  FileText,
  Globe2,
  Home,
  LogOut,
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
  Zap,
  UserCheck,
  X,
} from "lucide-vue-next";
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NConfigProvider,
  NDialogProvider,
  NEmpty,
  NGlobalStyle,
  NIcon,
  NInput,
  NInputNumber,
  NMessageProvider,
  NNotificationProvider,
  NPagination,
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
import NaiveApiBridge from "./components/NaiveApiBridge.vue";
import CommandPalette, { type Command } from "./components/CommandPalette.vue";
import { confirmDanger } from "./composables/useNotifications";
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
  draft_count?: number;
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
  api_base_url: string;
  backend_base_url: string;
  email_server: string;
  email_user: string;
  has_email_password: boolean;
  email_template: string;
  scoring_rules: string;
}

interface AgentConfigResponse {
  provider_name: string;
  has_api_key: boolean;
  api_key_preview: string | null;
  has_openai_api_key: boolean;
  openai_api_key_preview: string | null;
  model_name: string;
  api_base_url: string;
  backend_base_url: string;
  agent_env_path: string;
  restart_required: boolean;
}

const apiBase = import.meta.env.VITE_API_BASE_URL || "/api";
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
const replyText = ref("");
const lastEmail = ref<EmailEvent | null>(null);
const analysis = ref<ReplyAnalysis | null>(null);
const sourcePreview = ref<SourcePreview | null>(null);
const sourcePreviewLead = ref<Lead | null>(null);
const sourcePreviewLoading = ref(false);
const sourcePreviewError = ref("");
const sourcePreviewMode = ref<"page" | "text">("page");
const loading = ref(false);
const currentAction = ref<"dashboard" | "search" | "outreach" | "reply" | "qualify" | "sync" | "followup" | null>(null);

// Pagination
const leadPage = ref(1);
const leadPageSize = ref(20);
const leadTotal = ref(0);

// Custom email (自拟定)
const showCustomEmail = ref(false);
const customEmail = ref({ lead_id: 0, company_name: "", email: "", subject: "", body: "" });
const customEmailSending = ref(false);
const availableAttachments = ref<string[]>([]);
const customEmailAttachments = ref<string[]>([]);

// Edit lead
const showEditLead = ref(false);
const editLead = ref({
  id: 0, company_name: "", region: "", country: "", website: "",
  contact_name: "", email: "", category: "", match_reason: "",
  source: "", score: 50, status: "", notes: "",
});
const editLeadSaving = ref(false);

// Lead detail panel
const detailLeadId = ref<number | null>(null);
const detailStatus = ref("");
const detailNotes = ref("");
const detailOutreach = ref<EmailEvent[]>([]);
const detailReplies = ref<ReplyAnalysis[]>([]);
const detailLoading = ref(false);
const notice = ref("");
const error = ref("");
// Hard cap on the Agent prompt length. The composer's character counter
// and `n-input :maxlength` both read from this so the displayed limit
// and the enforced limit can never drift.
const AGENT_PROMPT_MAX = 2000;
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
// Wall-clock time of the most recent successful Agent run completion.
// Powers the "完成于 …" badge in the report head.
const agentLastCompletedAt = ref<Date | null>(null);

// ── Agent chat-turn machinery (A-rewrite) ────────────
// We keep `agentResponse` / `agentProcessItems` as the canonical
// in-flight buffers (they're what the SSE handler writes into).
// `currentTurnPrompt` captures the user-side text at send time;
// `agentTurnHistory` collects completed turns so the chat scroll
// shows past Q&A like a real conversation.
interface AgentTurn {
  id: string;
  user: string;
  response: string;
  process: AgentProcessItem[];
  completedAt: Date | null;
  failed?: string;
}
const currentTurnPrompt = ref<string>("");
const agentTurnHistory = ref<AgentTurn[]>([]);
// Map of toolCard id -> expanded?  (lazy collapse state)
const expandedToolCards = ref<Record<string, boolean>>({});

function toggleToolCard(turnId: string, idx: number): void {
  const key = `${turnId}:${idx}`;
  expandedToolCards.value[key] = !expandedToolCards.value[key];
}
function isToolCardExpanded(turnId: string, idx: number): boolean {
  return !!expandedToolCards.value[`${turnId}:${idx}`];
}

const hasAnyConversation = computed<boolean>(() => {
  return (
    agentTurnHistory.value.length > 0 ||
    !!currentTurnPrompt.value ||
    !!agentResponse.value ||
    agentProcessItems.value.length > 0
  );
});

// Rotating starter prompts shown when the conversation is empty.
// Tap a card → drop into the composer + send (chat-app convention).
interface StarterPrompt {
  icon: string;
  title: string;
  body: string;
}
const starterPrompts: StarterPrompt[] = [
  {
    icon: "🇮🇳",
    title: "在印度找 TKA 分销商",
    body: "帮我找 SkyWalker TKA 在印度的渠道商，优先骨科植入物、关节置换、TKA 分销商，要求公开邮箱和来源证据。",
  },
  {
    icon: "🇩🇪",
    title: "德国骨科采购方",
    body: "搜索德国地区的骨科医院采购、GPO 集采、私立连锁，关注 hip/knee implant 类目，给出 contact email。",
  },
  {
    icon: "🇸🇦",
    title: "中东医院采购对接",
    body: "在阿联酋和沙特找私立医院采购或 distributor，列出公司名 + 联系人 + 邮箱 + 是否有官网证据。",
  },
  {
    icon: "📧",
    title: "起草跟进邮件",
    body: "我刚和墨西哥的一家代理商通过邮件，他们要求看 SkyWalker TKA 的临床数据。帮我起草一封跟进邮件。",
  },
];

function applyStarterPrompt(starter: StarterPrompt): void {
  agentPrompt.value = starter.body;
  // Defer one frame so the textarea reflects the bound value before we
  // submit, otherwise composing IME may eat the send.
  globalThis.requestAnimationFrame?.(() => {
    sendAgentPrompt();
  });
}

// Sessions drawer (mobile-first toggle that hides the session list on
// narrow viewports). Defaults to open on desktop, closed on phones.
const sessionDrawerOpen = ref(false);

// Template ref pointing at the chat-scroll container so we can
// auto-pin the viewport to the bottom when new tokens arrive — the
// behaviour every modern chat client expects ("ChatGPT-scroll").
const agentChatScrollEl = ref<HTMLDivElement | null>(null);

function scrollChatToBottom(behavior: ScrollBehavior = "smooth"): void {
  const el = agentChatScrollEl.value;
  if (!el) return;
  // Only auto-scroll when the user is already near the bottom; if they
  // scrolled up to inspect history, leave them alone (chat-app courtesy).
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  if (distanceFromBottom > 240) return;
  el.scrollTo({ top: el.scrollHeight, behavior });
}

watch(
  () => agentResponse.value,
  () => {
    globalThis.requestAnimationFrame?.(() => scrollChatToBottom("smooth"));
  },
);
watch(
  () => agentProcessItems.value.length,
  () => {
    globalThis.requestAnimationFrame?.(() => scrollChatToBottom("smooth"));
  },
);
watch(
  () => agentTurnHistory.value.length,
  () => {
    // New turn pushed → snap to bottom unconditionally so the user
    // immediately sees their latest message.
    globalThis.requestAnimationFrame?.(() => {
      const el = agentChatScrollEl.value;
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    });
  },
);

function toggleSessionDrawer(): void {
  sessionDrawerOpen.value = !sessionDrawerOpen.value;
}

function copyTurnResponse(turn: AgentTurn): void {
  if (!turn.response) return;
  void copyTextToClipboard(turn.response, "已复制 Agent 输出到剪贴板");
}

// Aliases bridging the new chat-shell template to the existing
// session-rename helpers (which were named under the old 3-column
// layout). Keeps the v-on/@submit bindings readable in the new
// markup without duplicating the underlying logic.
function beginAgentSessionRename(session: AgentSessionRecord): void {
  beginEditAgentSession(session);
}
function cancelAgentSessionRename(): void {
  cancelEditAgentSession();
}
function commitAgentSessionRename(): void {
  if (!editingSessionId.value) return;
  saveAgentSessionTitle(editingSessionId.value);
}

// Composer keydown — Cmd/Ctrl+Enter submits, Shift+Enter inserts a
// newline (browser default), plain Enter alone does not submit on
// purpose so users can stage multi-line prompts without surprises.
function onComposerKeydown(event: KeyboardEvent): void {
  if (event.key !== "Enter") return;
  const wantsSubmit = (event.metaKey || event.ctrlKey) && !event.shiftKey;
  if (!wantsSubmit) return;
  event.preventDefault();
  if (agentLoading.value) return;
  void sendAgentPrompt();
}

async function clearChatHistory(): Promise<void> {
  if (agentLoading.value) return;
  if (agentTurnHistory.value.length === 0 && !currentTurnPrompt.value && !agentResponse.value) {
    return;
  }
  const ok = await confirmDanger({
    title: "清空当前对话？",
    content: "本会话的所有问答和工具调用记录都会被清除。",
    positiveText: "清空",
  });
  if (!ok) return;
  agentTurnHistory.value = [];
  currentTurnPrompt.value = "";
  expandedToolCards.value = {};
  clearAgentOutput();
  notice.value = "已清空对话历史";
}

function regenerateTurn(turn: AgentTurn): void {
  if (agentLoading.value) return;
  agentPrompt.value = turn.user;
  globalThis.requestAnimationFrame?.(() => {
    sendAgentPrompt();
  });
}

// Cmd/Ctrl+K command palette (PR6.2). The palette itself is dumb — it
// just renders the list and bubbles the chosen command back up. The
// command list below is the canonical "what you can do" surface; we
// feed it to the palette on every render so permission gates and live
// data (selected leads, current page) are reflected without manual
// refresh.
const commandPaletteOpen = ref(false);
const paletteCommands = computed<Command[]>(() => {
  const list: Command[] = [
    {
      id: "go-leads",
      group: "页面",
      label: "线索数据库",
      hint: "/leads",
      run: () => showPage("workspace", "overview"),
    },
    {
      id: "go-agent",
      group: "页面",
      label: "渠道拓展 Agent",
      hint: "/agent",
      run: () => showPage("agent"),
    },
    {
      id: "go-settings",
      group: "页面",
      label: "系统设置",
      hint: "/settings",
      run: () => showPage("settings"),
    },
    {
      id: "refresh-dashboard",
      group: "操作",
      label: "刷新线索列表",
      hint: "重新拉取当前过滤条件下的线索",
      available: () => isAuthenticated.value,
      run: () => loadDashboard(),
    },
    {
      id: "create-lead",
      group: "操作",
      label: "添加新线索",
      available: () => isAuthenticated.value && hasPermission("leads:write"),
      run: () => {
        showPage("workspace");
        openCreateLead();
      },
    },
    {
      id: "approve-all-drafts",
      group: "操作",
      label: "批准全部待发草稿",
      hint: `${draftCount.value} 条待审批`,
      available: () =>
        isAuthenticated.value &&
        hasPermission("outreach:send") &&
        draftCount.value > 0,
      run: () => approveAllDrafts(),
    },
    {
      id: "sync-replies",
      group: "操作",
      label: "同步邮件回复",
      hint: "立即扫描收件箱",
      available: () => isAuthenticated.value && hasPermission("replies:sync"),
      run: () => syncReplies(),
    },
    {
      id: "logout",
      group: "账户",
      label: "退出登录",
      available: () => isAuthenticated.value,
      run: () => logout(),
    },
  ];
  return list;
});

function toggleCommandPalette(): void {
  commandPaletteOpen.value = !commandPaletteOpen.value;
}
const agentConfig = ref<AgentConfigResponse | null>(null);
const agentApiKeyInput = ref("");
const agentProviderName = ref("deepseek");
const agentModelName = ref("deepseek-v4-pro");
const agentBackendBaseUrl = ref("http://localhost:8000");
const agentApiBaseUrl = ref("");
const agentConfigLoading = ref(false);
const agentConfigSaving = ref(false);
const agentConfigTesting = ref(false);
const agentTestResult = ref<null | { ok: boolean; latency_ms: number; message: string; error?: string }>(null);
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
  api_base_url: "",
  backend_base_url: "http://localhost:8000",
  email_server: "mail.microport.com.cn",
  email_user: "",
  has_email_password: false,
  email_template: "",
  scoring_rules: "",
});
const settingsAgentKeyInput = ref("");
const settingsEmailPasswordInput = ref("");
const settingsEmailTemplate = ref("");
const settingsScoringRules = ref("");

// ── Roles & Users management ──
//
// Permission catalog is fetched from the backend (/permissions/registry) so
// adding a permission only requires a backend change. The registry response
// also drives the role-editor UI (groupings, presets, descriptions).
interface PermissionMeta { key: string; group: string; group_label: string; label: string; description: string }
interface PermissionGroup { key: string; label: string; permissions: string[] }
interface PermissionPreset { key: string; label: string; description: string; permissions: string[] }
interface PermissionRegistry {
  permissions: PermissionMeta[];
  groups: PermissionGroup[];
  presets: PermissionPreset[];
}
const permissionRegistry = ref<PermissionRegistry | null>(null);

const ALL_PERMISSIONS = computed<string[]>(() =>
  permissionRegistry.value?.permissions.map((p) => p.key) ?? [],
);
const permLabels = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  for (const p of permissionRegistry.value?.permissions ?? []) {
    map[p.key] = p.label;
  }
  return map;
});
const permissionGroupsForUI = computed<PermissionGroup[]>(() =>
  permissionRegistry.value?.groups ?? [],
);
const permissionPresets = computed<PermissionPreset[]>(() =>
  permissionRegistry.value?.presets ?? [],
);

async function loadPermissionRegistry(): Promise<void> {
  if (permissionRegistry.value) return;
  try {
    permissionRegistry.value = await request<PermissionRegistry>("/permissions/registry");
  } catch { /* falls back to empty list — UI hides the editor */ }
}

const allRoles = ref<Array<{ id: number; name: string; permissions: string; user_count: number }>>([]);
const allUsers = ref<Array<{ id: number; username: string; role_id: number; role_name: string }>>([]);
const showRoleEditor = ref(false);
const showUserEditor = ref(false);
const editingRole = ref({ id: 0, name: "", permissions: [] as string[] });
const editingRoleSnapshot = ref<{ name: string; permissions: string[] }>({ name: "", permissions: [] });
const editingUser = ref({ id: 0, username: "", password: "", role_id: 0 });
const editingUserSnapshot = ref<{ username: string; password: string; role_id: number }>({ username: "", password: "", role_id: 0 });

// ── Access-tab UI state ──────────────────────────────────
const roleSearch = ref("");
const userSearch = ref("");
const permSearch = ref("");
const collapsedGroups = ref<Record<string, boolean>>({});
const showResetPasswordResult = ref(false);
const resetPasswordResult = ref({ username: "", password: "" });

const filteredRoles = computed(() =>
  roleSearch.value.trim()
    ? allRoles.value.filter((r) => r.name.toLowerCase().includes(roleSearch.value.trim().toLowerCase()))
    : allRoles.value,
);
const filteredUsers = computed(() =>
  userSearch.value.trim()
    ? allUsers.value.filter((u) => {
        const q = userSearch.value.trim().toLowerCase();
        return u.username.toLowerCase().includes(q) || (u.role_name || "").toLowerCase().includes(q);
      })
    : allUsers.value,
);

function permsAsArray(role: { permissions: string | string[] }): string[] {
  return typeof role.permissions === "string" ? JSON.parse(role.permissions) : (role.permissions || []);
}

function roleEditorDirty(): boolean {
  return (
    editingRole.value.name !== editingRoleSnapshot.value.name ||
    JSON.stringify([...editingRole.value.permissions].sort()) !==
      JSON.stringify([...editingRoleSnapshot.value.permissions].sort())
  );
}

function isGrantedKey(perms: string[], key: string): boolean {
  // Match the wildcard rules so the editor visually tracks "*" and "<group>:*".
  if (perms.includes("*")) return true;
  if (perms.includes(key)) return true;
  const colon = key.indexOf(":");
  if (colon > 0 && perms.includes(key.slice(0, colon) + ":*")) return true;
  return false;
}

function togglePermissionKey(key: string, on: boolean): void {
  // Editing a group-wildcard role: toggling a single key clears the wildcard
  // and replaces it with the explicit set so the user gets exactly what they
  // see checked.
  let perms = [...editingRole.value.permissions];
  if (perms.includes("*")) {
    perms = ALL_PERMISSIONS.value.slice();
  }
  const colon = key.indexOf(":");
  if (colon > 0) {
    const wildcard = key.slice(0, colon) + ":*";
    if (perms.includes(wildcard)) {
      const groupKeys = (permissionGroupsForUI.value.find((g) => g.key === key.slice(0, colon))?.permissions) ?? [];
      perms = perms.filter((p) => p !== wildcard).concat(groupKeys);
    }
  }
  if (on) {
    if (!perms.includes(key)) perms.push(key);
  } else {
    perms = perms.filter((p) => p !== key);
  }
  editingRole.value.permissions = Array.from(new Set(perms));
}

function groupSelectionState(group: PermissionGroup): "all" | "some" | "none" {
  const granted = editingRole.value.permissions;
  if (granted.includes("*") || granted.includes(`${group.key}:*`)) return "all";
  const checked = group.permissions.filter((k) => granted.includes(k)).length;
  if (checked === 0) return "none";
  if (checked === group.permissions.length) return "all";
  return "some";
}

function toggleGroup(group: PermissionGroup, on: boolean): void {
  let perms = [...editingRole.value.permissions];
  if (perms.includes("*")) perms = ALL_PERMISSIONS.value.slice();
  // strip group's keys + group wildcard
  perms = perms.filter((p) => p !== `${group.key}:*` && !group.permissions.includes(p));
  if (on) perms.push(...group.permissions);
  editingRole.value.permissions = Array.from(new Set(perms));
}

function applyPreset(presetKey: string): void {
  const preset = permissionPresets.value.find((p) => p.key === presetKey);
  if (!preset) return;
  editingRole.value.permissions = [...preset.permissions];
}

function visiblePermissionsForGroup(group: PermissionGroup): string[] {
  const q = permSearch.value.trim().toLowerCase();
  if (!q) return group.permissions;
  return group.permissions.filter((k) => {
    const meta = permissionRegistry.value?.permissions.find((p) => p.key === k);
    return (
      k.toLowerCase().includes(q) ||
      (meta?.label || "").toLowerCase().includes(q) ||
      (meta?.description || "").toLowerCase().includes(q)
    );
  });
}

function permLabel(key: string): string {
  return permLabels.value[key] || key;
}
function permDescription(key: string): string {
  return permissionRegistry.value?.permissions.find((p) => p.key === key)?.description || "";
}

function generateRandomPassword(): string {
  // 12-char URL-safe-ish password — consistent with backend secrets.token_urlsafe(10).
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789";
  const out: string[] = [];
  const random = globalThis.crypto?.getRandomValues
    ? () => {
        const arr = new Uint32Array(1);
        globalThis.crypto.getRandomValues(arr);
        return arr[0];
      }
    : () => Math.floor(Math.random() * 0xffffffff);
  for (let i = 0; i < 12; i++) out.push(alphabet[random() % alphabet.length]);
  return out.join("");
}

async function loadRolesAndUsers(): Promise<void> {
  try {
    await loadPermissionRegistry();
    const [r, u] = await Promise.all([
      request<{ roles: typeof allRoles.value }>("/roles"),
      request<{ users: typeof allUsers.value }>("/users"),
    ]);
    allRoles.value = r.roles.map((role) => ({ ...role, permissions: typeof role.permissions === "string" ? JSON.parse(role.permissions) : role.permissions }));
    allUsers.value = u.users;
  } catch { /* ignore */ }
}

function openNewRole(): void {
  editingRole.value = { id: 0, name: "", permissions: [] };
  editingRoleSnapshot.value = { name: "", permissions: [] };
  permSearch.value = "";
  collapsedGroups.value = {};
  showRoleEditor.value = true;
}

function openEditRole(role: typeof allRoles.value[0]): void {
  const perms = permsAsArray(role);
  editingRole.value = { id: role.id, name: role.name, permissions: [...perms] };
  editingRoleSnapshot.value = { name: role.name, permissions: [...perms] };
  permSearch.value = "";
  collapsedGroups.value = {};
  showRoleEditor.value = true;
}

async function saveRole(): Promise<void> {
  const body = { name: editingRole.value.name, permissions: editingRole.value.permissions };
  if (editingRole.value.id > 0) {
    await request(`/roles/${editingRole.value.id}`, { method: "PUT", body: JSON.stringify(body) });
  } else {
    await request("/roles", { method: "POST", body: JSON.stringify(body) });
  }
  showRoleEditor.value = false;
  await loadRolesAndUsers();
  // If the admin just edited a role they themselves hold, their own UI permissions
  // need to refresh — backend cache is wiped, but the frontend ref isn't.
  await refreshPermissions();
  notice.value = `角色已${editingRole.value.id ? "更新" : "创建"}`;
}

async function deleteRole(role: typeof allRoles.value[0]): Promise<void> {
  const tail = role.user_count > 0 ? `${role.user_count} 个使用此角色的用户会被移至 admin。` : "";
  const confirmed = await confirmDanger({
    title: `删除角色「${role.name}」？`,
    content: `${tail}此操作不可恢复。`.trim(),
    positiveText: "删除角色",
  });
  if (!confirmed) return;
  await request(`/roles/${role.id}`, { method: "DELETE" });
  await loadRolesAndUsers();
  await refreshPermissions();
  notice.value = `角色「${role.name}」已删除`;
}

function openNewUser(): void {
  editingUser.value = { id: 0, username: "", password: "", role_id: allRoles.value[0]?.id || 1 };
  editingUserSnapshot.value = { username: "", password: "", role_id: allRoles.value[0]?.id || 1 };
  showUserEditor.value = true;
}

function openEditUser(user: typeof allUsers.value[0]): void {
  editingUser.value = { id: user.id, username: user.username, password: "", role_id: user.role_id };
  editingUserSnapshot.value = { username: user.username, password: "", role_id: user.role_id };
  showUserEditor.value = true;
}

function userEditorDirty(): boolean {
  return (
    editingUser.value.username !== editingUserSnapshot.value.username ||
    editingUser.value.role_id !== editingUserSnapshot.value.role_id ||
    !!editingUser.value.password
  );
}

function generateNewPasswordForUser(): void {
  editingUser.value.password = generateRandomPassword();
}

async function saveUser(): Promise<void> {
  const body: Record<string, unknown> = { username: editingUser.value.username, role_id: editingUser.value.role_id };
  if (editingUser.value.password) body.password = editingUser.value.password;
  const wasReset = !!editingUser.value.password && editingUser.value.id > 0;
  const newPassword = editingUser.value.password;
  const username = editingUser.value.username;
  if (editingUser.value.id > 0) {
    await request(`/users/${editingUser.value.id}`, { method: "PUT", body: JSON.stringify(body) });
  } else {
    await request("/users", { method: "POST", body: JSON.stringify(body) });
  }
  showUserEditor.value = false;
  await loadRolesAndUsers();
  // If the admin edited their own role assignment, their own UI must refresh.
  await refreshPermissions();
  if (wasReset) {
    resetPasswordResult.value = { username, password: newPassword };
    showResetPasswordResult.value = true;
  } else {
    notice.value = `用户已${editingUser.value.id ? "更新" : "创建"}`;
  }
}

async function deleteUser(user: typeof allUsers.value[0]): Promise<void> {
  const confirmed = await confirmDanger({
    title: `删除用户「${user.username}」？`,
    content: "此操作不可恢复，账号下的访问凭证会立即失效。",
    positiveText: "删除用户",
  });
  if (!confirmed) return;
  await request(`/users/${user.id}`, { method: "DELETE" });
  await loadRolesAndUsers();
  notice.value = `用户「${user.username}」已删除`;
}
const settingsLoading = ref(false);
const settingsSaving = ref(false);
const settingsTab = ref<"email" | "sync" | "agent" | "template" | "scoring" | "access">("email");

// Keyboard-navigable tablist support (PR6.1). The list is rebuilt
// reactively because the "权限" tab is permission-gated; arrow-key
// navigation must skip a tab that isn't currently mounted.
type SettingsTabValue = "email" | "sync" | "agent" | "template" | "scoring" | "access";
const settingsTabList = computed<{ value: SettingsTabValue; label: string }[]>(() => {
  const tabs: { value: SettingsTabValue; label: string }[] = [
    { value: "email", label: "邮箱" },
    { value: "sync", label: "同步" },
    { value: "agent", label: "Agent" },
    { value: "template", label: "模板" },
    { value: "scoring", label: "评分" },
  ];
  if (hasPermission("users:manage")) {
    tabs.push({ value: "access", label: "权限" });
  }
  return tabs;
});

const settingsTabRefs: Partial<Record<SettingsTabValue, HTMLButtonElement>> = {};
function bindSettingsTabRef(value: SettingsTabValue, el: HTMLButtonElement | null): void {
  if (el) settingsTabRefs[value] = el;
  else delete settingsTabRefs[value];
}

function onSettingsTabKeydown(event: KeyboardEvent): void {
  const list = settingsTabList.value.map((t) => t.value);
  const current = settingsTab.value;
  const idx = list.indexOf(current);
  if (idx < 0) return;
  let next: SettingsTabValue | null = null;
  switch (event.key) {
    case "ArrowLeft":
      next = list[(idx - 1 + list.length) % list.length];
      break;
    case "ArrowRight":
      next = list[(idx + 1) % list.length];
      break;
    case "Home":
      next = list[0];
      break;
    case "End":
      next = list[list.length - 1];
      break;
    default:
      return;
  }
  if (!next) return;
  event.preventDefault();
  settingsTab.value = next;
  // Move DOM focus too so subsequent ←/→ keep working without the user
  // having to mouse-click.
  globalThis.requestAnimationFrame?.(() => {
    settingsTabRefs[next!]?.focus();
  });
}
const drafts = ref<EmailEvent[]>([]);
const draftCount = ref(0);
const showOutreachPreview = ref(false);
const outreachLoading = ref(false);
const outreachPreviews = ref<Array<{ lead_id: number; company_name: string; email: string; subject: string; body: string }>>([]);
const showCreateLead = ref(false);
const createError = ref("");
const newLead = ref({ company_name: "", region: "", country: "", website: "", contact_name: "", email: "", category: "medical device distributor" });
const activePage = ref<"workspace" | "agent" | "settings">("workspace");

// Sync the local `activePage` with the router so browser back/forward
// and bookmarkable URLs work without rewriting every consumer of
// `activePage.value` in this file. Pages still read `activePage` exactly
// as before; navigation is just URL-aware now.
watch(
  () => router.currentRoute.value.name,
  (name) => {
    if (name === "agent" || name === "settings" || name === "workspace") {
      activePage.value = name;
    }
  },
  { immediate: true },
);

// ── Auth state ────────────────────────────────────────
const STORAGE_TOKEN_KEY = "medbot_auth_token";
const STORAGE_USERNAME_KEY = "medbot_auth_username";
const authToken = ref(localStorageGet(STORAGE_TOKEN_KEY));
const authUsername = ref(localStorageGet(STORAGE_USERNAME_KEY));
const authPermissions = ref<string[]>(JSON.parse(localStorageGet("medbot_auth_permissions") || "[]"));
const loginUsername = ref("");
const loginPassword = ref("");
const loginLoading = ref(false);
const loginError = ref("");
const isAuthenticated = computed(() => !!authToken.value);

function hasPermission(perm: string): boolean {
  // Wildcard rules — must match backend app/permissions.py::matches:
  //   "*"          → grants everything
  //   "<group>:*"  → grants every action in that group
  //   exact match  → as you'd expect
  const granted = authPermissions.value;
  if (!granted || granted.length === 0) return false;
  if (granted.includes("*")) return true;
  if (granted.includes(perm)) return true;
  const colon = perm.indexOf(":");
  if (colon > 0) {
    const groupWildcard = perm.slice(0, colon) + ":*";
    if (granted.includes(groupWildcard)) return true;
  }
  return false;
}

function setAuthPermissions(perms: string[] | undefined | null): void {
  const list = Array.isArray(perms) ? perms.map(String) : [];
  authPermissions.value = list;
  localStorageSet("medbot_auth_permissions", JSON.stringify(list));
}

async function refreshPermissions(): Promise<void> {
  // Re-pull the latest permissions from the server. Cheap (cached for 30s
  // backend-side); call after admin actions or on a periodic timer so users
  // see role changes without a manual reload.
  if (!authToken.value) return;
  try {
    const resp = await fetch(`${apiBase}/auth/verify`, {
      headers: { Authorization: `Bearer ${authToken.value}` },
    });
    if (!resp.ok) {
      if (resp.status === 401) clearAuth();
      return;
    }
    const data = await resp.json() as {
      username: string; valid: boolean; permissions?: string[];
    };
    if (data.valid) setAuthPermissions(data.permissions);
  } catch {
    // network glitch — keep current state
  }
}

function localStorageGet(key: string): string {
  try {
    return globalThis.localStorage?.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function localStorageSet(key: string, value: string): void {
  try {
    globalThis.localStorage?.setItem(key, value);
  } catch {
    // storage unavailable
  }
}

function localStorageRemove(key: string): void {
  try {
    globalThis.localStorage?.removeItem(key);
  } catch {
    // storage unavailable
  }
}
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

/**
 * Human-readable label for the last successful Agent completion.
 * Empty when nothing has finished yet (the badge is hidden).
 *
 * Recent completions are shown as a relative phrase ("刚刚", "3 分钟前");
 * older ones fall back to a "YYYY-MM-DD HH:mm" stamp so the timestamp
 * stays unambiguous when a session has been idle for hours.
 */
const agentCompletedAtLabel = computed<string>(() => {
  const at = agentLastCompletedAt.value;
  if (!at) return "";
  const elapsedMs = Date.now() - at.getTime();
  if (elapsedMs < 60 * 1000) return "完成于 刚刚";
  if (elapsedMs < 60 * 60 * 1000) {
    return `完成于 ${Math.floor(elapsedMs / (60 * 1000))} 分钟前`;
  }
  if (elapsedMs < 12 * 60 * 60 * 1000) {
    return `完成于 ${Math.floor(elapsedMs / (60 * 60 * 1000))} 小时前`;
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `完成于 ${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())} ` +
    `${pad(at.getHours())}:${pad(at.getMinutes())}`
  );
});

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
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };

  // Attach auth token if available
  if (authToken.value) {
    headers["Authorization"] = `Bearer ${authToken.value}`;
  }

  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const body = await response.text();
    // On 401, clear auth state
    if (response.status === 401 && authToken.value) {
      clearAuth();
    }
    throw new Error(body);
  }

  return (await response.json()) as T;
}

// ── Auth actions ──────────────────────────────────────

function clearAuth(): void {
  authToken.value = "";
  authUsername.value = "";
  authPermissions.value = [];
  localStorageRemove(STORAGE_TOKEN_KEY);
  localStorageRemove(STORAGE_USERNAME_KEY);
  localStorageRemove("medbot_auth_permissions");
}

async function login(): Promise<void> {
  loginError.value = "";
  if (!loginUsername.value.trim() || !loginPassword.value.trim()) {
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
      const body = await resp.text();
      let detail = "登录失败";
      try {
        detail = JSON.parse(body).detail || detail;
      } catch {}
      loginError.value = detail;
      return;
    }

    const data = await resp.json() as {
      access_token: string;
      username: string;
      permissions?: string[];
    };
    authToken.value = data.access_token;
    authUsername.value = data.username;
    setAuthPermissions(data.permissions);
    localStorageSet(STORAGE_TOKEN_KEY, data.access_token);
    localStorageSet(STORAGE_USERNAME_KEY, data.username);
    loginPassword.value = "";

    // Reload dashboard data after login
    await loadProductProfile();
    await loadDashboard();
    await loadAgentConfig();
    notice.value = `欢迎，${data.username}`;
  } catch (caught) {
    loginError.value = caught instanceof Error ? caught.message : "登录失败";
  } finally {
    loginLoading.value = false;
  }
}

async function verifyAndRestoreAuth(): Promise<boolean> {
  if (!authToken.value) return false;
  try {
    const resp = await fetch(`${apiBase}/auth/verify`, {
      headers: { Authorization: `Bearer ${authToken.value}` },
    });
    if (!resp.ok) {
      clearAuth();
      return false;
    }
    const data = await resp.json() as {
      username: string;
      valid: boolean;
      permissions?: string[];
    };
    if (data.valid && data.username) {
      authUsername.value = data.username;
      setAuthPermissions(data.permissions);
      localStorageSet(STORAGE_USERNAME_KEY, data.username);
      return true;
    }
  } catch {
    // Network error — keep token and try later
    return !!authToken.value;
  }
  clearAuth();
  return false;
}

function logout(): void {
  clearAuth();
  // Navigate via router so the URL/back-button stay consistent. The watch
  // mirrors this into `activePage` before the login overlay appears.
  void router.push({ name: "workspace" });
  sidebarUserMenuOpen.value = false;
  notice.value = "已退出登录";
}

function onLoginKeydown(event: KeyboardEvent): void {
  if (event.key === "Enter") {
    login();
  }
}

async function loadDashboard(resetPage: boolean = true): Promise<void> {
  if (resetPage) leadPage.value = 1;
  const params = new URLSearchParams();
  if (filterRegion.value) params.set("region", filterRegion.value);
  if (filterStatus.value) params.set("status", filterStatus.value);
  if (query.value) params.set("q", query.value);
  params.set("sort", sortField.value);
  params.set("order", sortDir.value);
  params.set("offset", String((leadPage.value - 1) * leadPageSize.value));
  params.set("limit", String(leadPageSize.value));

  const [leadPayload, metricPayload] = await Promise.all([
    request<LeadListResponse>(`/leads?${params.toString()}`),
    request<Metrics>("/metrics"),
  ]);

  leads.value = leadPayload.leads;
  leadTotal.value = leadPayload.total;
  metrics.value = metricPayload;
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
  const email = newLead.value.email.trim();
  if (!email) {
    createError.value = "请填写邮箱";
    return;
  }
  // Permissive email check — same family as the HTML5 input[type=email]
  // pattern; rejects clearly broken values like "bob" or "x@" without
  // chasing every RFC edge case.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    createError.value = "邮箱格式不正确";
    return;
  }
  const website = newLead.value.website.trim();
  if (website && !/^https?:\/\/[^\s]+$/i.test(website)) {
    createError.value = "网址需以 http:// 或 https:// 开头";
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
  const confirmed = await confirmDanger({
    title: `删除选中的 ${selectedLeadIds.value.length} 条线索？`,
    content: "关联的外联记录、回复分析和草稿都会一并清除，此操作不可恢复。",
    positiveText: "全部删除",
  });
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
  const confirmed = await confirmDanger({
    title: "删除这条线索？",
    content: "关联的外联记录和回复分析也会被清除，此操作不可恢复。",
    positiveText: "删除线索",
  });
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
        lead_id: detailLeadId.value || null,
        reply_text: replyText.value,
      }),
    });
    showReplyAnalyzer.value = true;
    await loadDashboard();
  });
}

async function generateFollowupAndOpen(): Promise<void> {
  if (!detailLeadId.value || !replyText.value.trim()) return;
  await runAction("followup", async () => {
    const result = await request<{ subject: string; body: string; sent_to: string }>("/replies/followup", {
      method: "POST",
      body: JSON.stringify({
        lead_id: detailLeadId.value,
        reply_text: replyText.value,
      }),
    });
    // Pre-fill the custom email modal with the AI-generated follow-up
    const lead = leads.value.find((l) => l.id === detailLeadId.value);
    if (lead) {
      customEmail.value = {
        lead_id: lead.id,
        company_name: lead.company_name,
        email: lead.email,
        subject: result.subject,
        body: result.body,
      };
      showCustomEmail.value = true;
    }
  });
}

// Aborter for the in-flight Agent SSE stream. Held at module scope so
// the cancel button can call `agentAbort.value?.abort()` without needing
// to thread a reference through composables.
const agentAbort = ref<AbortController | null>(null);

function cancelAgentPrompt(): void {
  const controller = agentAbort.value;
  if (!controller) return;
  controller.abort();
  // The fetch will reject in the running `sendAgentPrompt` and the
  // `finally` clause clears `agentLoading` and the controller; we just
  // surface a clean process-bar message so the user sees confirmation.
  appendAgentProcess("error", "已中断", "用户主动取消了本次 Agent 任务");
}

async function sendAgentPrompt(): Promise<void> {
  const message = agentPrompt.value.trim();
  if (!message || agentLoading.value) return;

  // Chat-app convention: captured user text moves to the active turn,
  // and any previously completed turn slides into the scrollback. This
  // lets the chat shell re-render the conversation as a real history
  // instead of overwriting in place.
  if (
    currentTurnPrompt.value &&
    (agentResponse.value || agentProcessItems.value.length > 0 || agentError.value)
  ) {
    agentTurnHistory.value.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      user: currentTurnPrompt.value,
      response: agentResponse.value,
      process: [...agentProcessItems.value],
      completedAt: agentLastCompletedAt.value,
      failed: agentError.value || undefined,
    });
  }

  currentTurnPrompt.value = message;
  // Pre-clear the composer so the in-flight bubble owns the prompt
  // text. Restoring on error keeps work recoverable.
  agentPrompt.value = "";

  const controller = new AbortController();
  agentAbort.value = controller;
  agentLoading.value = true;
  clearAgentOutput();
  notice.value = "";
  appendAgentProcess("running", "连接 Agent", `Session ${agentSessionId.value || "default"}`);
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
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
      buffer = consumeAgentStreamBuffer(
        buffer + decoder.decode(value, { stream: true }),
      );
    }
    buffer = consumeAgentStreamBuffer(buffer + decoder.decode());
    if (buffer.trim()) {
      handleAgentSseFrame(buffer);
    }
    agentLastCompletedAt.value = new Date();
    await loadDashboard();
  } catch (caught) {
    // AbortError fires when the user clicked cancel — already messaged.
    const aborted =
      controller.signal.aborted ||
      (caught instanceof DOMException && caught.name === "AbortError");
    if (!aborted) {
      agentError.value = caught instanceof Error ? caught.message : "Agent 请求失败";
      appendAgentProcess("error", "Agent 请求失败", agentError.value);
      // Make the failed prompt available again so the user can edit
      // and retry without retyping. Cancel doesn't restore — the user
      // chose to abandon.
      if (!agentPrompt.value) {
        agentPrompt.value = currentTurnPrompt.value;
      }
    }
  } finally {
    agentLoading.value = false;
    if (agentAbort.value === controller) {
      agentAbort.value = null;
    }
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
    agentConfigError.value = caught instanceof Error ? caught.message : "Agent 配置保存失败";
  } finally {
    agentConfigSaving.value = false;
  }
}

async function testAgentConnection(): Promise<void> {
  if (agentConfigTesting.value) return;
  agentConfigTesting.value = true;
  agentTestResult.value = null;
  agentConfigError.value = "";
  try {
    // Use entered key if provided, otherwise fall back to saved key status
    const apiKey = agentApiKeyInput.value.trim() || settingsAgentKeyInput.value.trim();
    if (!apiKey) {
      agentTestResult.value = { ok: false, latency_ms: 0, message: "请先输入 API Key", error: "未提供 API Key" };
      return;
    }
    const result = await request<{
      ok: boolean;
      latency_ms: number;
      provider: string;
      model: string;
      message: string;
      error?: string;
    }>("/agent/test-connection", {
      method: "POST",
      body: JSON.stringify({
        provider_name: agentProviderName.value.trim(),
        api_key: apiKey,
        model_name: agentModelName.value.trim(),
        api_base_url: agentApiBaseUrl.value.trim() || undefined,
      }),
    });
    agentTestResult.value = {
      ok: result.ok,
      latency_ms: result.latency_ms,
      message: result.message,
      error: result.error || undefined,
    };
  } catch (caught) {
    agentTestResult.value = {
      ok: false,
      latency_ms: 0,
      message: "测试请求失败",
      error: caught instanceof Error ? caught.message : "网络错误",
    };
  } finally {
    agentConfigTesting.value = false;
  }
}

async function sendOutreachSingle(leadId: number): Promise<void> {
  await fetchOutreachPreview([leadId]);
}

async function openCustomEmail(leadId: number): Promise<void> {
  const lead = leads.value.find((l) => l.id === leadId);
  if (!lead) return;
  customEmail.value = {
    lead_id: leadId,
    company_name: lead.company_name,
    email: lead.email,
    subject: "",
    body: "",
  };
  customEmailAttachments.value = [];
  // Load available attachments
  try {
    const result = await request<{ files: string[] }>("/attachments");
    availableAttachments.value = result.files.filter((f) => f !== "README.txt");
  } catch {
    availableAttachments.value = [];
  }
  showCustomEmail.value = true;
}

async function openEditLead(leadId: number): Promise<void> {
  try {
    const lead = await request<Lead>(`/leads/${leadId}`);
    editLead.value = {
      id: lead.id, company_name: lead.company_name, region: lead.region,
      country: lead.country, website: lead.website || "",
      contact_name: lead.contact_name || "", email: lead.email || "",
      category: lead.category || "", match_reason: lead.match_reason || "",
      source: lead.source || "", score: lead.score,
      status: lead.status, notes: lead.notes || "",
    };
    showEditLead.value = true;
  } catch {
    error.value = "加载线索详情失败";
  }
}

async function saveEditLead(): Promise<void> {
  if (editLeadSaving.value) return;
  // Same shape as the create-lead validation. We only check fields the
  // user can edit non-trivially — empty values blank a field; bad-format
  // values block the save and surface a global error.
  const email = (editLead.value.email || "").trim();
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    error.value = "邮箱格式不正确";
    return;
  }
  const website = (editLead.value.website || "").trim();
  if (website && !/^https?:\/\/[^\s]+$/i.test(website)) {
    error.value = "网址需以 http:// 或 https:// 开头";
    return;
  }
  editLeadSaving.value = true;
  try {
    await request(`/leads/${editLead.value.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        company_name: editLead.value.company_name,
        region: editLead.value.region,
        country: editLead.value.country,
        website: editLead.value.website || undefined,
        contact_name: editLead.value.contact_name || undefined,
        email: editLead.value.email || undefined,
        category: editLead.value.category || undefined,
        match_reason: editLead.value.match_reason || undefined,
        source: editLead.value.source || undefined,
        score: editLead.value.score,
        status: editLead.value.status || undefined,
        notes: editLead.value.notes || undefined,
      }),
    });
    showEditLead.value = false;
    notice.value = "线索已更新";
    await loadDashboard(false); // keep current page
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "保存失败";
  } finally {
    editLeadSaving.value = false;
  }
}

async function sendCustomEmail(): Promise<void> {
  if (customEmailSending.value) return;
  customEmailSending.value = true;
  try {
    await request("/campaigns/custom-send", {
      method: "POST",
      body: JSON.stringify({
        lead_id: customEmail.value.lead_id,
        subject: customEmail.value.subject,
        body: customEmail.value.body,
        attachments: customEmailAttachments.value,
      }),
    });
    showCustomEmail.value = false;
    notice.value = "自定义邮件已发送";
    await loadDashboard(true);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "发送失败";
  } finally {
    customEmailSending.value = false;
  }
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

const showReplyAnalyzer = ref(false);

function openReplyAnalyzer(replyTextContent?: string): void {
  replyText.value = replyTextContent || "";
  analysis.value = null;
  showReplyAnalyzer.value = true;
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

interface TimelineEvent {
  kind: "outreach" | "reply";
  id: number;
  time: string;
  // outreach fields
  subject?: string;
  sent_to?: string;
  body?: string;
  status?: string;
  source?: string;
  // reply fields
  reply_text?: string;
  intent?: string;
  confidence?: number;
  summary?: string;
  next_action?: string;
  requires_human?: boolean;
}

const timelineEvents = computed<TimelineEvent[]>(() => {
  const items: TimelineEvent[] = [
    ...detailOutreach.value.map((ev) => ({
      kind: "outreach" as const,
      id: ev.id,
      time: ev.created_at || "",
      subject: ev.subject,
      sent_to: ev.sent_to,
      body: ev.body,
      status: ev.status,
      source: ev.source,
    })),
    ...detailReplies.value.map((r) => ({
      kind: "reply" as const,
      id: r.id,
      time: r.created_at || "",
      reply_text: r.reply_text,
      intent: r.intent,
      confidence: r.confidence,
      summary: r.summary,
      next_action: r.next_action,
      requires_human: r.requires_human,
    })),
  ];
  items.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
  return items;
});

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
  runAction("dashboard", () => loadDashboard(true));
}

function onLeadPageChange(page: number): void {
  leadPage.value = page;
  runAction("dashboard", () => loadDashboard(false));
}

function onLeadPageSizeChange(size: number): void {
  leadPageSize.value = size;
  leadPage.value = 1;
  runAction("dashboard", () => loadDashboard(false));
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

/**
 * Maps a 0–100 lead score onto a visual tier.
 * Tiers map to `--score-{high,mid,low}` design tokens via the
 * `.lead-score-badge.score-{high,mid,low}` rules in styles.css.
 */
function scoreTier(score: number): "score-high" | "score-mid" | "score-low" {
  if (score >= 75) return "score-high";
  if (score >= 40) return "score-mid";
  return "score-low";
}

function applyAgentConfig(config: AgentConfigResponse): void {
  agentConfig.value = config;
  agentProviderName.value = config.provider_name;
  agentModelName.value = config.model_name;
  agentApiBaseUrl.value = config.api_base_url || "";
  agentBackendBaseUrl.value = config.backend_base_url;
}

function showPage(page: "workspace" | "agent" | "settings", sectionId?: string): void {
  agentGuideOpen.value = false;
  agentNotificationsOpen.value = false;
  sidebarUserMenuOpen.value = false;

  // Drive navigation through the router so browser history works.
  // The watch on `router.currentRoute.value.name` mirrors this back into
  // the local `activePage` ref, so existing template `v-if` checks still
  // resolve before the next paint.
  const routeName = page;
  const navigation = router.currentRoute.value.name === routeName
    ? Promise.resolve()
    : router.push({ name: routeName });

  void Promise.resolve(navigation).then(() => {
    if (page === "settings") {
      loadSettings();
      return;
    }
    const targetId = sectionId || (page === "agent" ? "overview" : "");
    if (!targetId) return;
    globalThis.requestAnimationFrame?.(() => {
      globalThis.document?.getElementById(targetId)?.scrollIntoView({ block: "start" });
    });
  });
}

async function loadSettings(): Promise<void> {
  settingsLoading.value = true;
  try {
    settings.value = await request<SettingsResponse>("/settings");
    agentApiBaseUrl.value = settings.value.api_base_url || "";
    settingsEmailTemplate.value = settings.value.email_template || "";
    settingsScoringRules.value = settings.value.scoring_rules || "";
    if (hasPermission("users:manage")) loadRolesAndUsers();
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
      api_base_url: agentApiBaseUrl.value,
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
    if (settingsEmailTemplate.value.trim()) {
      body.email_template = settingsEmailTemplate.value.trim();
    }
    if (settingsScoringRules.value.trim()) {
      body.scoring_rules = settingsScoringRules.value.trim();
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

/**
 * Mutual-exclusion control for the Agent page's stack of popovers.
 *
 * The Agent page can show up to 5 different floating panels (guide,
 * notifications, settings, skill detail, logs) plus the sidebar user
 * menu. Pre-PR5 each toggle was hand-rolled, leading to overlap when
 * multiple were opened at once. `closeOtherPopovers(except)` is the
 * single source of truth: every toggle calls it before opening, so at
 * most one popover is visible at a time.
 *
 * Note: `agentReportFullscreen` is intentionally excluded — it's a
 * full-canvas overlay rather than a small popover, and a user opening
 * a report panel on top of it would close it.
 */
type PopoverKey =
  | "guide"
  | "notifications"
  | "userMenu"
  | "settings"
  | "skill"
  | "logs";

function closeOtherPopovers(except: PopoverKey | null): void {
  if (except !== "guide") agentGuideOpen.value = false;
  if (except !== "notifications") agentNotificationsOpen.value = false;
  if (except !== "userMenu") sidebarUserMenuOpen.value = false;
  if (except !== "settings") agentSettingsOpen.value = false;
  if (except !== "skill") agentSkillDetailsOpen.value = false;
  if (except !== "logs") agentLogsOpen.value = false;
}

function toggleAgentGuide(): void {
  agentGuideOpen.value = !agentGuideOpen.value;
  if (agentGuideOpen.value) closeOtherPopovers("guide");
}

function toggleAgentNotifications(): void {
  agentNotificationsOpen.value = !agentNotificationsOpen.value;
  if (agentNotificationsOpen.value) closeOtherPopovers("notifications");
}

function toggleSidebarUserMenu(): void {
  sidebarUserMenuOpen.value = !sidebarUserMenuOpen.value;
  if (sidebarUserMenuOpen.value) closeOtherPopovers("userMenu");
}

function toggleAgentSettings(): void {
  agentSettingsOpen.value = !agentSettingsOpen.value;
  if (agentSettingsOpen.value) {
    agentConfigExpanded.value = true;
    closeOtherPopovers("settings");
  }
}

function toggleAgentSkillDetails(): void {
  agentSkillDetailsOpen.value = !agentSkillDetailsOpen.value;
  if (agentSkillDetailsOpen.value) closeOtherPopovers("skill");
}

function toggleAgentLogs(): void {
  agentLogsOpen.value = !agentLogsOpen.value;
  if (agentLogsOpen.value) closeOtherPopovers("logs");
}

function toggleAgentReportFullscreen(): void {
  // The fullscreen button is `:disabled="!agentOutputText"`, but a
  // keyboard-driven activate could still slip through if the disabled
  // state lags the data. We still bail silently to avoid throwing.
  if (!agentOutputText.value) return;
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

async function removeAgentSession(sessionId: string): Promise<void> {
  if (agentLoading.value) return;
  const session = agentSessions.value.find((item) => item.id === sessionId);
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

onMounted(async () => {
  applyAgentSessionState(loadAgentSessionState(getAgentStorage()));
  // Legacy hash format (`#agent`, `#settings`) → upgrade to router URLs.
  const legacyHash = globalThis.location?.hash;
  if (legacyHash === "#agent") {
    void router.replace({ name: "agent" });
  } else if (legacyHash === "#settings") {
    void router.replace({ name: "settings" });
  }

  // Global Esc handler — closes the topmost modal/popover in priority
  // order. Naive UI's `n-dialog` already handles its own Esc, so this
  // only needs to cover the legacy `modal-backdrop` overlays still
  // inlined in this template (until PR7 ports them to `n-modal`).
  const onGlobalKeydown = (event: KeyboardEvent) => {
    // Cmd/Ctrl+K opens the command palette. Skip when the user is
    // composing inside a textarea/input — most browsers reserve the
    // shortcut already for power-user actions, but inside the agent
    // composer (a multi-line textarea) we still want it to work.
    if ((event.metaKey || event.ctrlKey) && (event.key === "k" || event.key === "K")) {
      event.preventDefault();
      toggleCommandPalette();
      return;
    }
    if (event.key !== "Escape") return;
    if (commandPaletteOpen.value) {
      // The palette has its own Esc handler on the input, but if focus
      // has bubbled out (e.g. clicking the backdrop) we need this fallback.
      commandPaletteOpen.value = false;
      event.preventDefault();
      return;
    }
    if (agentReportFullscreen.value) {
      agentReportFullscreen.value = false;
      event.preventDefault();
      return;
    }
    if (sourcePreviewLead.value) {
      closeSourcePreview();
      event.preventDefault();
      return;
    }
    if (showResetPasswordResult.value) {
      showResetPasswordResult.value = false;
      event.preventDefault();
      return;
    }
    if (showRoleEditor.value) {
      showRoleEditor.value = false;
      event.preventDefault();
      return;
    }
    if (showUserEditor.value) {
      showUserEditor.value = false;
      event.preventDefault();
      return;
    }
    if (showCreateLead.value) {
      showCreateLead.value = false;
      event.preventDefault();
      return;
    }
    if (showEditLead.value) {
      showEditLead.value = false;
      event.preventDefault();
      return;
    }
    if (showCustomEmail.value) {
      showCustomEmail.value = false;
      event.preventDefault();
      return;
    }
    if (showOutreachPreview.value) {
      showOutreachPreview.value = false;
      event.preventDefault();
      return;
    }
    if (detailLeadId.value !== null) {
      closeLeadDetail();
      event.preventDefault();
      return;
    }
    if (agentGuideOpen.value) {
      agentGuideOpen.value = false;
      event.preventDefault();
      return;
    }
    if (agentNotificationsOpen.value) {
      agentNotificationsOpen.value = false;
      event.preventDefault();
      return;
    }
    if (sidebarUserMenuOpen.value) {
      sidebarUserMenuOpen.value = false;
      event.preventDefault();
      return;
    }
  };
  globalThis.addEventListener?.("keydown", onGlobalKeydown);
  void onGlobalKeydown;

  // Verify or restore auth on startup
  const loggedIn = await verifyAndRestoreAuth();
  if (loggedIn) {
    void runAction("dashboard", async () => {
      await Promise.all([loadProductProfile(), loadDashboard()]);
    });
    void loadAgentConfig();
    void loadPermissionRegistry();

    // Periodically re-pull permissions so admin-side role changes propagate
    // without forcing the user to refresh the page. The backend caches the
    // lookup for 30s so this is cheap.
    const PERM_REFRESH_MS = 5 * 60 * 1000;
    const timer = globalThis.setInterval(() => {
      if (authToken.value) void refreshPermissions();
    }, PERM_REFRESH_MS);
    // Refresh on tab focus too — gives the user immediate feedback after a
    // role change without waiting for the timer.
    const onFocus = () => { if (authToken.value) void refreshPermissions(); };
    globalThis.addEventListener?.("focus", onFocus);
    // No onUnmounted in App.vue — the root component lives for the session,
    // so manual cleanup is unnecessary; storing the handles for symmetry only.
    void timer; void onFocus;
  }
});
</script>

<template>
  <n-config-provider :theme-overrides="naiveThemeOverrides">
  <n-global-style />
  <!--
    Naive's discrete API providers wrap the whole shell so any descendant
    can call `useMessage()`, `useDialog()` or `useNotification()` (PR2+).
    They are pure providers — no DOM cost when nothing is queued.
  -->
  <n-message-provider :max="5" placement="top-right">
  <n-dialog-provider>
  <n-notification-provider :max="4" placement="top-right">
  <NaiveApiBridge />

  <!--
    Cmd/Ctrl+K command palette. Lives at the root so its z-index
    overlay sits above every page surface (workspace, agent, settings)
    and every modal-backdrop.
  -->
  <CommandPalette
    v-model:open="commandPaletteOpen"
    :commands="paletteCommands"
  />

  <!-- Login screen -->
  <!--
    Modern login screen (V1)
    Split-pane layout: brand hero on the left, form on the right.
    A radial gradient + soft decorative blobs replace the previous flat
    gradient card, giving the screen visual depth without imagery.
  -->
  <div v-if="!isAuthenticated" class="login-shell" aria-label="登录">
    <aside class="login-hero" aria-hidden="true">
      <div class="login-hero-glow login-hero-glow-a"></div>
      <div class="login-hero-glow login-hero-glow-b"></div>

      <div class="login-hero-brand">
        <div class="brand-mark login-brand-mark">SW</div>
        <div>
          <strong>SkyWalker</strong>
          <span>Overseas Prospecting</span>
        </div>
      </div>

      <div class="login-hero-copy">
        <h1>把海外渠道<br />拓展工作交给 Agent。</h1>
        <p>
          从产品画像出发，自动检索分销商、抓取证据、生成可发邮件 — 你只需要审核和点击。
        </p>
      </div>

      <ul class="login-hero-points">
        <li><span class="login-hero-dot login-hero-dot-blue" />多源证据 · 网页/邮箱/PDF 自动汇总</li>
        <li><span class="login-hero-dot login-hero-dot-teal" />一键外联 · 草稿审核 → 自动发送</li>
        <li><span class="login-hero-dot login-hero-dot-amber" />自动转人工 · 高意向回复主动提醒</li>
      </ul>

      <div class="login-hero-foot">
        <span>v0.9.0 · 微创畅行</span>
        <span>仅限授权访问</span>
      </div>
    </aside>

    <main class="login-form-pane">
      <form
        class="login-form"
        autocomplete="on"
        @submit.prevent="login"
      >
        <header class="login-form-head">
          <p class="login-form-eyebrow">系统登录</p>
          <h2>欢迎回来</h2>
          <p class="login-form-sub">请使用授权账户登录工作台</p>
        </header>

        <label class="field">
          <span>用户名</span>
          <n-input
            v-model:value="loginUsername"
            size="large"
            placeholder="例如 microport_admin"
            autocomplete="username"
            :disabled="loginLoading"
            @keydown="onLoginKeydown"
          />
        </label>

        <label class="field">
          <span>密码</span>
          <n-input
            v-model:value="loginPassword"
            type="password"
            size="large"
            placeholder="••••••••"
            autocomplete="current-password"
            show-password-on="click"
            :disabled="loginLoading"
            @keydown="onLoginKeydown"
          />
        </label>

        <p
          v-if="loginError"
          class="login-error"
          role="alert"
          aria-live="polite"
        >
          {{ loginError }}
        </p>

        <n-button
          class="primary-button login-submit"
          type="primary"
          size="large"
          block
          attr-type="submit"
          :loading="loginLoading"
          :disabled="loginLoading || !loginUsername || !loginPassword"
        >
          {{ loginLoading ? "登录中..." : "登录工作台" }}
        </n-button>

        <p class="login-form-foot">
          忘记密码？请联系系统管理员重置 ·
          <kbd>Tab</kbd> 切换 <kbd>Enter</kbd> 登录
        </p>
      </form>
    </main>
  </div>


  <div v-show="isAuthenticated" class="app-shell app-frame">
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
          v-if="hasPermission('settings:read')"
          type="button"
          :class="{ active: activePage === 'settings' }"
          @click="showPage('settings')"
        >
          <span class="nav-icon"><SlidersHorizontal :size="18" aria-hidden="true" /></span>
          设置
        </button>
      </nav>
      <div class="sidebar-footer">
        <!--
          Sidebar Cmd+K cue (V2). Acts as a discoverable affordance for
          the keyboard shortcut: clicking it opens the same palette so
          mouse users get the same surface. The kbd hints adapt to the
          OS via JS detection; we keep static "⌘ K" as the visual since
          Tailwind/Naive don't ship platform detection helpers.
        -->
        <button
          type="button"
          class="sidebar-cmd-hint"
          aria-label="打开命令面板 (Ctrl/Cmd + K)"
          @click="toggleCommandPalette"
        >
          <span class="sidebar-cmd-hint-label">
            <Search :size="14" aria-hidden="true" />
            搜索 / 跳页
          </span>
          <span class="sidebar-cmd-hint-keys">
            <kbd>⌘</kbd><kbd>K</kbd>
          </span>
        </button>

        <button
          class="sidebar-user-card"
          type="button"
          :aria-expanded="sidebarUserMenuOpen"
          aria-controls="sidebar-user-menu"
          @click="toggleSidebarUserMenu"
        >
          <span class="user-avatar">{{ authUsername ? authUsername.charAt(0).toUpperCase() : "管" }}</span>
          <div>
            <strong>{{ authUsername || "管理员" }}</strong>
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
          <button type="button" role="menuitem" class="logout-menu-item" @click="logout">
            <span><LogOut :size="14" aria-hidden="true" /></span>
            退出登录
          </button>
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
              v-if="hasPermission('replies:sync')"
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
                <strong>{{ productProfile?.product_name }}</strong>
                <span class="product-procedure">{{ productProfile?.procedure }}</span>
              </div>
            </div>
            <p>{{ productProfile?.summary }}</p>
            <div class="chip-row">
              <span v-for="point in productProfile?.value_points.slice(0, 2) || []" :key="point">
                {{ point }}
              </span>
            </div>
            <small>
              资料：{{ productProfile?.source_files.length || 0 }} PDF ·
              {{ productProfile?.video_assets.length || 0 }} 视频
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
            <strong>{{ lastEmail?.subject }}</strong>
            <span>{{ lastEmail?.sent_to }}</span>
            <p>{{ lastEmail?.body }}</p>
          </n-card>
        </section>

        <section class="content-area" aria-label="线索和回复工作区">
          <!--
            ── Agent page (chat-style rewrite) ──────────
            Three structural pieces:
              1. agent-chat-head    sticky title bar + actions
              2. agent-chat-body    sessions drawer + chat scroll area
              3. agent-chat-composer  fixed bottom prompt input

            Compared to the previous 3-column report-card layout, this
            shell mirrors modern Agent UIs (Claude / ChatGPT / Cursor):
            a continuous turn-by-turn scroll where each user prompt is
            answered by an agent message that contains tool-call cards
            inline plus a streaming markdown body. The bottom-anchored
            composer keeps the input within thumb-reach on every device.
          -->
          <section
            v-if="activePage === 'agent'"
            class="agent-panel agent-page-panel agent-console-layout agent-chat-shell agent-design-shell"
            aria-labelledby="agent-title"
          >
            <header class="agent-chat-head">
              <button
                class="agent-chat-drawer-toggle"
                type="button"
                aria-label="切换会话列表"
                aria-controls="agent-sessions-drawer"
                :aria-expanded="sessionDrawerOpen"
                @click="toggleSessionDrawer"
              >
                <span class="agent-chat-drawer-toggle-bar" />
                <span class="agent-chat-drawer-toggle-bar" />
                <span class="agent-chat-drawer-toggle-bar" />
              </button>

              <div class="agent-chat-head-identity">
                <div class="agent-chat-avatar agent-chat-avatar-lg">
                  <Bot :size="20" aria-hidden="true" />
                </div>
                <div class="agent-chat-head-meta">
                  <h2 id="agent-title">{{ activeAgentSession?.title || "渠道拓展 Agent" }}</h2>
                  <p>
                    <span class="agent-chat-meta-pill">
                      <span class="agent-chat-meta-dot" />
                      {{ agentLoading ? "正在生成" : (agentResponse || agentTurnHistory.length) ? "已就绪" : "等待输入" }}
                    </span>
                    <span class="agent-chat-meta-divider" aria-hidden="true">·</span>
                    <span>overseas-distributor-prospecting</span>
                    <span class="agent-chat-meta-divider" aria-hidden="true">·</span>
                    <span>{{ shortAgentSessionId(agentSessionId) }}</span>
                  </p>
                </div>
              </div>

              <div class="agent-chat-head-actions">
                <n-button
                  size="small"
                  secondary
                  :disabled="agentLoading || (!hasAnyConversation)"
                  @click="clearChatHistory"
                >
                  <template #icon>
                    <n-icon><Trash2 /></n-icon>
                  </template>
                  清空
                </n-button>
                <n-button
                  size="small"
                  type="primary"
                  ghost
                  @click="startNewAgentSession"
                >
                  <template #icon>
                    <n-icon><Plus /></n-icon>
                  </template>
                  新会话
                </n-button>
              </div>
            </header>

            <div class="agent-chat-body">
              <!-- Sessions drawer (collapsible on narrow viewports) -->
              <aside
                id="agent-sessions-drawer"
                class="agent-chat-drawer agent-sidebar-panel"
                :class="{ open: sessionDrawerOpen }"
                aria-label="Agent 会话列表"
              >
                <header class="agent-chat-drawer-head">
                  <strong>会话</strong>
                  <button
                    class="agent-chat-drawer-new"
                    type="button"
                    aria-label="新建会话"
                    @click="startNewAgentSession"
                  >
                    <Plus :size="14" aria-hidden="true" />
                    新建
                  </button>
                </header>

                <div class="agent-chat-drawer-search agent-session-search">
                  <Search :size="14" aria-hidden="true" />
                  <input
                    v-model="agentSessionSearch"
                    type="text"
                    placeholder="搜索会话..."
                    aria-label="搜索会话"
                  />
                </div>

                <ul class="agent-chat-drawer-list" role="list">
                  <li
                    v-for="session in filteredAgentSessions"
                    :key="session.id"
                    :class="['agent-chat-drawer-item', { active: session.id === agentSessionId }]"
                    role="listitem"
                  >
                    <form
                      v-if="editingSessionId === session.id"
                      class="agent-chat-drawer-rename"
                      @submit.prevent="commitAgentSessionRename"
                    >
                      <input
                        v-model="editingSessionTitle"
                        autofocus
                        @keydown.escape="cancelAgentSessionRename"
                        @blur="commitAgentSessionRename"
                      />
                    </form>
                    <button
                      v-else
                      type="button"
                      class="agent-chat-drawer-item-button"
                      @click="switchAgentSession(session.id)"
                      @dblclick="beginAgentSessionRename(session)"
                    >
                      <span class="agent-chat-drawer-item-title">{{ session.title || "未命名会话" }}</span>
                      <span class="agent-chat-drawer-item-time">{{ formatAgentSessionTime(session.updatedAt) }}</span>
                    </button>
                    <button
                      v-if="editingSessionId !== session.id"
                      type="button"
                      class="agent-chat-drawer-item-delete"
                      aria-label="删除会话"
                      @click="removeAgentSession(session.id)"
                    >
                      <Trash2 :size="13" aria-hidden="true" />
                    </button>
                  </li>
                  <li v-if="filteredAgentSessions.length === 0" class="agent-chat-drawer-empty">
                    没有匹配的会话
                  </li>
                </ul>
              </aside>

              <!-- Chat scroll stage -->
              <main class="agent-chat-stage agent-conversation-panel agent-main-panel">
                <div ref="agentChatScrollEl" class="agent-chat-scroll">
                  <!-- Welcome / starter prompts when empty -->
                  <section v-if="!hasAnyConversation" class="agent-welcome">
                    <div class="agent-welcome-glow agent-welcome-glow-a" aria-hidden="true" />
                    <div class="agent-welcome-glow agent-welcome-glow-b" aria-hidden="true" />
                    <div class="agent-welcome-mark">
                      <Bot :size="32" aria-hidden="true" />
                    </div>
                    <h1>你好，我是 <span class="agent-welcome-accent">Pi</span></h1>
                    <p>
                      骨科海外渠道拓展 Agent — 告诉我你想找什么样的代理商，我会上网搜证据、把符合条件的线索写入数据库，并在你确认后起草触达邮件。
                    </p>
                    <ul class="agent-starter-grid" role="list">
                      <li v-for="starter in starterPrompts" :key="starter.title">
                        <button
                          type="button"
                          class="agent-starter-card"
                          :disabled="agentLoading"
                          @click="applyStarterPrompt(starter)"
                        >
                          <span class="agent-starter-icon" aria-hidden="true">{{ starter.icon }}</span>
                          <strong>{{ starter.title }}</strong>
                          <span class="agent-starter-body">{{ starter.body }}</span>
                          <span class="agent-starter-arrow" aria-hidden="true">↗</span>
                        </button>
                      </li>
                    </ul>
                  </section>

                  <!-- Completed turn history -->
                  <article
                    v-for="turn in agentTurnHistory"
                    :key="turn.id"
                    class="agent-chat-turn"
                  >
                    <div class="agent-msg agent-msg-user">
                      <div class="agent-msg-bubble">{{ turn.user }}</div>
                    </div>
                    <div class="agent-msg agent-msg-agent">
                      <div class="agent-msg-avatar" aria-hidden="true">
                        <Bot :size="14" />
                      </div>
                      <div class="agent-msg-body">
                        <div
                          v-for="(item, idx) in turn.process"
                          :key="idx"
                          :class="['agent-tool-card', `is-${item.kind}`]"
                        >
                          <button
                            type="button"
                            class="agent-tool-card-head"
                            :aria-expanded="isToolCardExpanded(turn.id, idx)"
                            @click="toggleToolCard(turn.id, idx)"
                          >
                            <span class="agent-tool-card-status">
                              <CheckCircle2 v-if="item.kind === 'done'" :size="14" aria-hidden="true" />
                              <AlertTriangle v-else-if="item.kind === 'error'" :size="14" aria-hidden="true" />
                              <RefreshCw v-else :size="14" aria-hidden="true" class="spin" />
                            </span>
                            <span class="agent-tool-card-title">{{ item.label }}</span>
                            <span class="agent-tool-card-detail">{{ item.detail }}</span>
                            <ChevronDown
                              :size="14"
                              aria-hidden="true"
                              class="agent-tool-card-chevron"
                              :class="{ rotate: isToolCardExpanded(turn.id, idx) }"
                            />
                          </button>
                          <div
                            v-if="isToolCardExpanded(turn.id, idx) && item.detail"
                            class="agent-tool-card-body"
                          >{{ item.detail }}</div>
                        </div>

                        <div v-if="turn.failed" class="agent-msg-error" role="alert">
                          <AlertTriangle :size="14" aria-hidden="true" />
                          {{ turn.failed }}
                        </div>
                        <div v-else-if="turn.response" class="agent-msg-md">
                          <MarkdownRenderer :blocks="parseMarkdown(turn.response)" />
                        </div>

                        <div class="agent-msg-actions">
                          <button
                            v-if="turn.response"
                            type="button"
                            class="agent-msg-action"
                            @click="copyTurnResponse(turn)"
                          >
                            <Copy :size="12" aria-hidden="true" />
                            复制
                          </button>
                          <button
                            type="button"
                            class="agent-msg-action"
                            :disabled="agentLoading"
                            @click="regenerateTurn(turn)"
                          >
                            <RefreshCw :size="12" aria-hidden="true" />
                            重试
                          </button>
                          <span v-if="turn.completedAt" class="agent-msg-time">
                            {{ formatTime(turn.completedAt.toISOString()) }}
                          </span>
                        </div>
                      </div>
                    </div>
                  </article>

                  <!-- Active in-flight turn -->
                  <article
                    v-if="currentTurnPrompt"
                    class="agent-chat-turn agent-chat-turn-active"
                  >
                    <div class="agent-msg agent-msg-user">
                      <div class="agent-msg-bubble">{{ currentTurnPrompt }}</div>
                    </div>
                    <div class="agent-msg agent-msg-agent">
                      <div
                        class="agent-msg-avatar"
                        :class="{ 'is-thinking': agentLoading }"
                        aria-hidden="true"
                      >
                        <Bot :size="14" />
                      </div>
                      <div class="agent-msg-body">
                        <div
                          v-for="(item, idx) in agentProcessItems"
                          :key="`active-${idx}`"
                          :class="['agent-tool-card', `is-${item.kind}`]"
                        >
                          <button
                            type="button"
                            class="agent-tool-card-head"
                            :aria-expanded="isToolCardExpanded('active', idx)"
                            @click="toggleToolCard('active', idx)"
                          >
                            <span class="agent-tool-card-status">
                              <CheckCircle2 v-if="item.kind === 'done'" :size="14" aria-hidden="true" />
                              <AlertTriangle v-else-if="item.kind === 'error'" :size="14" aria-hidden="true" />
                              <RefreshCw v-else :size="14" aria-hidden="true" class="spin" />
                            </span>
                            <span class="agent-tool-card-title">{{ item.label }}</span>
                            <span class="agent-tool-card-detail">{{ item.detail }}</span>
                            <ChevronDown
                              :size="14"
                              aria-hidden="true"
                              class="agent-tool-card-chevron"
                              :class="{ rotate: isToolCardExpanded('active', idx) }"
                            />
                          </button>
                          <div
                            v-if="isToolCardExpanded('active', idx) && item.detail"
                            class="agent-tool-card-body"
                          >{{ item.detail }}</div>
                        </div>

                        <div
                          v-if="agentLoading && !agentResponse && agentProcessItems.length === 0"
                          class="agent-msg-thinking"
                          aria-live="polite"
                        >
                          <span class="agent-thinking-dot" />
                          <span class="agent-thinking-dot" />
                          <span class="agent-thinking-dot" />
                          <span class="agent-thinking-text">Pi 正在思考...</span>
                        </div>

                        <div v-if="agentResponse" class="agent-msg-md">
                          <MarkdownRenderer :blocks="agentMarkdownBlocks" />
                          <span v-if="agentLoading" class="agent-streaming-cursor" aria-hidden="true">▌</span>
                        </div>

                        <div v-if="agentError" class="agent-msg-error" role="alert">
                          <AlertTriangle :size="14" aria-hidden="true" />
                          {{ agentError }}
                        </div>

                        <div v-if="!agentLoading && (agentResponse || agentError)" class="agent-msg-actions">
                          <button
                            v-if="agentResponse"
                            type="button"
                            class="agent-msg-action"
                            @click="copyTextToClipboard(agentResponse, '已复制 Agent 输出')"
                          >
                            <Copy :size="12" aria-hidden="true" />
                            复制
                          </button>
                          <button
                            type="button"
                            class="agent-msg-action"
                            :disabled="agentLoading"
                            @click="agentPrompt = currentTurnPrompt; sendAgentPrompt()"
                          >
                            <RefreshCw :size="12" aria-hidden="true" />
                            重试
                          </button>
                          <button
                            v-if="agentResponse"
                            type="button"
                            class="agent-msg-action"
                            @click="agentReportFullscreen = true"
                          >
                            <Maximize2 :size="12" aria-hidden="true" />
                            全屏
                          </button>
                          <span v-if="agentCompletedAtLabel" class="agent-msg-time">
                            {{ agentCompletedAtLabel }}
                          </span>
                        </div>
                      </div>
                    </div>
                  </article>
                </div>

                <!-- Sticky composer at bottom -->
                <footer class="agent-chat-composer agent-compose-surface" aria-label="发送任务">
                  <div class="agent-chat-composer-meta">
                    <button
                      type="button"
                      class="agent-chat-composer-skill agent-skill-pill"
                      :aria-expanded="agentSkillDetailsOpen"
                      @click="toggleAgentSkillDetails"
                    >
                      <Zap :size="13" aria-hidden="true" />
                      overseas-distributor-prospecting
                      <ChevronDown :size="12" aria-hidden="true" />
                    </button>
                    <span
                      class="agent-chat-composer-counter"
                      :class="{ 'is-over': agentPrompt.length > AGENT_PROMPT_MAX }"
                    >
                      {{ agentPrompt.length }} / {{ AGENT_PROMPT_MAX }}
                    </span>
                  </div>
                  <div class="agent-chat-composer-row">
                    <textarea
                      v-model="agentPrompt"
                      :maxlength="AGENT_PROMPT_MAX"
                      class="agent-chat-composer-input"
                      placeholder="向 Pi 描述你的渠道拓展需求…例如：找印度的 TKA 分销商"
                      aria-label="Agent 提示输入"
                      @keydown="onComposerKeydown"
                    />
                    <div class="agent-chat-composer-actions">
                      <button
                        v-if="agentLoading"
                        type="button"
                        class="agent-chat-composer-stop"
                        aria-label="停止生成 (Esc)"
                        @click="cancelAgentPrompt"
                      >
                        <X :size="14" aria-hidden="true" />
                        停止
                      </button>
                      <button
                        v-else
                        type="button"
                        class="agent-chat-composer-send"
                        :disabled="!agentPrompt.trim()"
                        aria-label="发送 (Cmd+Enter)"
                        @click="sendAgentPrompt"
                      >
                        <Send :size="14" aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                  <div class="agent-chat-composer-foot">
                    <span class="agent-chat-composer-shortcut">
                      <kbd>⌘</kbd><kbd>↵</kbd> 发送 ·
                      <kbd>Shift</kbd><kbd>↵</kbd> 换行
                    </span>
                    <button
                      type="button"
                      class="agent-chat-composer-settings agent-config-manage-button"
                      @click="toggleAgentSettings"
                    >
                      <SlidersHorizontal :size="13" aria-hidden="true" />
                      模型设置
                    </button>
                  </div>
                </footer>
              </main>
            </div>
          </section>

        <section
          v-if="activePage === 'workspace' && draftCount > 0"
          class="draft-queue"
          aria-label="待审核外联"
        >
          <div class="draft-queue-head">
            <div class="draft-queue-title">
              <strong>{{ draftCount }} 条待审批</strong>
              <span class="draft-queue-desc">Agent 生成的邮件在此统一审核，批准后真实发送，拒绝则废弃</span>
            </div>
            <n-button
              v-if="hasPermission('outreach:approve')"
              class="draft-approve-all"
              size="medium"
              @click="approveAllDrafts"
            >
              <template #icon><n-icon><Check /></n-icon></template>
              全部批准发送
            </n-button>
          </div>
          <article v-for="draft in drafts" :key="draft.id" class="draft-card">
            <div class="draft-card-body">
              <div class="draft-meta">
                <strong>{{ draft.company_name || 'Unknown' }}</strong>
                <span class="draft-card-country">{{ draft.country }}</span>
                <span class="draft-card-email">{{ draft.sent_to }}</span>
              </div>
              <p class="draft-subject">{{ draft.subject }}</p>
              <p class="draft-preview">{{ draft.body.slice(0, 250) }}{{ draft.body.length > 250 ? '...' : '' }}</p>
            </div>
            <div v-if="hasPermission('outreach:approve')" class="draft-actions">
              <n-button class="draft-btn-approve" size="small" @click="approveDraft(draft.id)">
                <template #icon><n-icon><Check /></n-icon></template>
                批准发送
              </n-button>
              <n-button class="draft-btn-reject" size="small" @click="rejectDraft(draft.id)">
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
              <n-button v-if="hasPermission('leads:write')" class="ghost-button" secondary size="small" @click="openCreateLead">
                <template #icon><n-icon><Plus /></n-icon></template>
                添加线索
              </n-button>
              <template v-if="selectedLeadIds.length > 0">
                <span class="selection-count">已选 {{ selectedLeadIds.length }} 条</span>
                <n-button
                  v-if="hasPermission('outreach:send')"
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

          <!--
            Skeleton: shown while the very first dashboard load is in
            flight. Once leads are populated we render the rows below;
            on empty (post-load) the `n-empty` block takes over.
          -->
          <div
            v-if="currentAction === 'dashboard' && leads.length === 0"
            class="lead-skeleton-list"
            aria-busy="true"
            aria-label="线索加载中"
          >
            <div v-for="n in 6" :key="n" class="lead-skeleton-row">
              <span class="skeleton-bar skeleton-checkbox" />
              <span class="skeleton-bar skeleton-strong" />
              <span class="skeleton-bar skeleton-meta" />
              <span class="skeleton-bar skeleton-meta short" />
              <span class="skeleton-bar skeleton-pill" />
            </div>
          </div>

          <n-empty
            v-else-if="leads.length === 0"
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
                <span :class="['lead-score-badge', scoreTier(lead.score)]" :title="`匹配评分 ${lead.score}/100`">{{ lead.score }}</span>
                <button class="source-link" type="button" @click.stop="openSourcePreview(lead)">{{ lead.source }}</button>
                <span class="lead-reason-inline">{{ lead.match_reason }}</span>
              </div>
            </div>

            <div class="lead-tools" @click.stop>
              <button v-if="hasPermission('outreach:send') && lead.status === 'new' && !(lead.draft_count && lead.draft_count > 0)" class="lead-action-btn" @click="sendOutreachSingle(lead.id)"><Send :size="13" />外联</button>
              <button v-if="hasPermission('outreach:send') && lead.email" class="lead-action-btn primary" @click="openCustomEmail(lead.id)"><Edit3 :size="13" />自拟定</button>
              <span v-if="lead.status === 'new' && lead.draft_count && lead.draft_count > 0" class="draft-indicator">📝 {{ lead.draft_count }}条待审</span>
              <button v-if="['new', 'emailed', 'interested', 'human_review', 'needs_review'].includes(lead.status)" class="lead-action-btn" @click="markQualified(lead.id)"><UserCheck :size="13" />确认</button>
              <button v-if="lead.status === 'rejected'" class="lead-action-btn" @click="reactivateLead(lead.id)"><RefreshCw :size="13" />激活</button>
              <button class="lead-action-btn" @click="openEditLead(lead.id)"><Pencil :size="13" /></button>
              <button class="lead-action-btn danger" @click="deleteLead(lead.id)"><Trash2 :size="13" /></button>
            </div>
          </article>

          <div v-if="leadTotal > leadPageSize" class="pagination-bar">
            <n-pagination
              :page="leadPage"
              :page-size="leadPageSize"
              :item-count="leadTotal"
              :page-slot="7"
              show-size-picker
              :page-sizes="[10, 20, 50]"
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
                  <n-button class="ghost-button" secondary @click="showReplyAnalyzer = !showReplyAnalyzer">
                    <template #icon><n-icon><Search /></n-icon></template>
                    {{ showReplyAnalyzer ? '收起分析' : '回复分析' }}
                  </n-button>
                </div>
              </div>

              <div class="detail-history">
                <div v-if="timelineEvents.length > 0">
                  <p class="panel-label">沟通时间线（{{ timelineEvents.length }} 条记录）</p>
                  <div class="email-timeline">
                    <div
                      v-for="(ev, idx) in timelineEvents"
                      :key="`${ev.kind}-${ev.id}`"
                      :class="['timeline-node', idx === 0 ? 'first' : '', `kind-${ev.kind}`]"
                    >
                      <div class="timeline-dot" aria-hidden="true">
                        <Send v-if="ev.kind === 'outreach'" :size="12" />
                        <MailCheck v-else :size="12" />
                      </div>

                      <!-- Outbound email -->
                      <article v-if="ev.kind === 'outreach'" class="timeline-card outreach-card">
                        <div class="timeline-card-head">
                          <n-tag
                            :type="ev.status === 'sent' ? 'success' : ev.status === 'send_failed' ? 'error' : ev.status === 'draft' ? 'warning' : 'info'"
                            size="tiny" round :bordered="false"
                          >
                            {{ ev.status === 'sent' ? '📤 已发送' : ev.status === 'send_failed' ? '❌ 失败' : ev.status === 'draft' ? '⏳ 草稿' : '已记录' }}
                          </n-tag>
                          <small>{{ formatTime(ev.time) }}</small>
                        </div>
                        <strong>{{ ev.subject }}</strong>
                        <span class="timeline-meta">→ {{ ev.sent_to }}</span>
                        <p v-if="ev.status === 'draft'" class="draft-hint">💡 此草稿在页面顶部「待审核」队列中统一审批</p>
                        <p class="timeline-preview">{{ (ev.body || '').slice(0, 150) }}{{ (ev.body || '').length > 150 ? '...' : '' }}</p>
                      </article>

                      <!-- Inbound reply -->
                      <article v-else class="timeline-card reply-card">
                        <div class="timeline-card-head">
                          <n-tag
                            :type="ev.requires_human ? 'warning' : ev.intent === 'interested' ? 'success' : ev.intent === 'rejected' ? 'error' : 'info'"
                            size="tiny" round :bordered="false"
                          >
                            📥 {{ ev.requires_human ? '需转人工' : ev.intent === 'interested' ? '感兴趣' : ev.intent === 'rejected' ? '已拒绝' : '待审核' }}
                          </n-tag>
                          <small>{{ ev.confidence ? Math.round(ev.confidence * 100) + '%' : '' }} · {{ formatTime(ev.time) }}</small>
                        </div>
                        <blockquote v-if="ev.reply_text" class="reply-quote">{{ ev.reply_text }}</blockquote>
                        <p v-if="ev.summary">{{ ev.summary }}</p>
                        <p v-if="ev.next_action" class="history-next">{{ ev.next_action }}</p>
                        <div class="history-actions">
                          <n-button class="ghost-button" size="tiny" secondary @click="openReplyAnalyzer(ev.reply_text); showReplyAnalyzer = true;">
                            <template #icon><n-icon><RefreshCw /></n-icon></template>
                            重新分析
                          </n-button>
                        </div>
                      </article>
                    </div>
                  </div>
                </div>

                <!-- Inline reply analyzer -->
                <div v-if="showReplyAnalyzer" class="reply-analyzer-inline">
                  <p class="panel-label">回复分析</p>
                  <label class="field">
                    <span>回复原文</span>
                    <n-input v-model:value="replyText" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" placeholder="粘贴客户回复原文..." />
                  </label>
                  <div class="analyzer-actions">
                    <n-button
                      class="primary-button"
                      type="primary"
                      size="small"
                      :loading="currentAction === 'reply'"
                      :disabled="!replyText.trim()"
                      @click="analyzeCurrentReply"
                    >
                      <template #icon><n-icon><Search /></n-icon></template>
                      {{ currentAction === 'reply' ? '分析中...' : '分析' }}
                    </n-button>
                    <n-button class="ghost-button" size="small" secondary @click="showReplyAnalyzer = false">收起</n-button>
                  </div>
                  <div v-if="analysis && showReplyAnalyzer" class="reply-analysis-result" style="margin-top:12px">
                    <div class="analysis-row">
                      <span class="analysis-label">意图</span>
                      <n-tag :type="analysis.intent === 'interested' ? 'success' : analysis.intent === 'rejected' ? 'error' : 'info'" size="small" round :bordered="false">
                        {{ analysis.intent === 'interested' ? '感兴趣' : analysis.intent === 'rejected' ? '拒绝' : analysis.intent === 'needs_review' ? '待审核' : analysis.intent }}
                      </n-tag>
                      <span class="analysis-confidence">{{ Math.round(analysis.confidence * 100) }}%</span>
                    </div>
                    <div class="analysis-row">
                      <span class="analysis-label">总结</span>
                      <span>{{ analysis.summary }}</span>
                    </div>
                    <div class="analysis-row">
                      <span class="analysis-label">建议</span>
                      <span>{{ analysis.next_action }}</span>
                    </div>
                    <div v-if="analysis.requires_human" class="analysis-row human-alert">
                      ⚠️ 需要转人工处理
                    </div>
                    <div v-if="analysis.intent !== 'rejected'" class="analyzer-actions" style="margin-top:4px">
                      <n-button
                        class="primary-button"
                        type="primary"
                        size="small"
                        :loading="currentAction === 'followup'"
                        @click="generateFollowupAndOpen"
                      >
                        <template #icon><n-icon><Send /></n-icon></template>
                        生成跟进邮件
                      </n-button>
                    </div>
                  </div>
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
          <!--
            ARIA tablist (PR6.1) — gives the settings tabs first-class
            keyboard navigation: ←/→ to move focus, Home/End to jump.
            Each tab declares the panel id it controls so AT can announce
            the relationship even when the inner card uses ad-hoc markup.
          -->
          <div
            class="settings-tabs"
            role="tablist"
            aria-label="设置分组"
            @keydown="onSettingsTabKeydown"
          >
            <button
              v-for="tab in settingsTabList"
              :key="tab.value"
              :id="`settings-tab-${tab.value}`"
              :ref="(el) => bindSettingsTabRef(tab.value, el as HTMLButtonElement | null)"
              role="tab"
              :class="['settings-tab', { active: settingsTab === tab.value }]"
              :aria-selected="settingsTab === tab.value"
              :aria-controls="`settings-panel-${tab.value}`"
              :tabindex="settingsTab === tab.value ? 0 : -1"
              @click="settingsTab = tab.value"
            >
              {{ tab.label }}
            </button>
          </div>

          <section v-if="settingsTab === 'template'" class="settings-card">
            <div class="settings-card-head">
              <div>
                <p class="panel-label">邮件模板</p>
                <h3>广撒网外发模板</h3>
                <p>批量发送外联时的基础邮件模板。变量：<code>[Name]</code> <code>[Role]</code> <code>[Target Market]</code> <code>[Company]</code>，条件块：<code>[IfDistributor]...[/IfDistributor]</code> <code>[IfBuyer]...[/IfBuyer]</code></p>
              </div>
            </div>
            <label class="field">
              <n-input
                v-model:value="settingsEmailTemplate"
                type="textarea"
                :autosize="{ minRows: 12, maxRows: 30 }"
                placeholder="输入邮件模板..."
              />
            </label>
          </section>

          <section v-if="settingsTab === 'scoring'" class="settings-card">
            <div class="settings-card-head">
              <div>
                <p class="panel-label">评分规则</p>
                <h3>线索评分标准</h3>
                <p>Agent 搜索线索时使用的评分规则。包含正向加分、负向扣分和阈值解释。保存后自动同步到 Agent Skill。</p>
              </div>
            </div>
            <label class="field">
              <n-input
                v-model:value="settingsScoringRules"
                type="textarea"
                :autosize="{ minRows: 16, maxRows: 40 }"
                placeholder="输入评分规则..."
              />
            </label>
          </section>

          <section v-if="settingsTab === 'access'" class="settings-card access-pane">
            <div class="settings-card-head">
              <div>
                <p class="panel-label">用户与权限</p>
                <h3>角色与用户管理</h3>
                <p>权限目录由后端 <code>/permissions/registry</code> 提供，新增权限只需后端一处修改。</p>
              </div>
            </div>

            <!-- Roles -->
            <div class="access-block">
              <header class="access-block-head">
                <div class="access-title">
                  <p class="panel-label">角色（{{ allRoles.length }}）</p>
                  <small class="muted">点击编辑可调整权限；admin 角色不可删除。</small>
                </div>
                <div class="access-actions">
                  <n-input
                    v-model:value="roleSearch"
                    placeholder="搜索角色"
                    size="small"
                    clearable
                    style="width:180px"
                  >
                    <template #prefix><n-icon><Search :size="14" /></n-icon></template>
                  </n-input>
                  <n-button size="small" type="primary" @click="openNewRole">
                    <template #icon><n-icon><Plus /></n-icon></template>新建角色
                  </n-button>
                </div>
              </header>
              <div v-if="allRoles.length === 0" class="history-empty">加载中...</div>
              <div v-else-if="filteredRoles.length === 0" class="history-empty">未找到匹配的角色</div>
              <div v-else class="role-grid">
                <article v-for="role in filteredRoles" :key="role.id" class="role-card">
                  <div class="role-card-head">
                    <div>
                      <strong>{{ role.name }}</strong>
                      <div class="role-meta">
                        <n-tag size="tiny" round :bordered="false">{{ role.user_count }} 用户</n-tag>
                        <n-tag size="tiny" round :bordered="false" type="info">
                          {{ permsAsArray(role).includes("*") ? "全部权限" : `${permsAsArray(role).length} 权限` }}
                        </n-tag>
                      </div>
                    </div>
                    <div class="role-card-actions">
                      <button class="link-button" type="button" @click="openEditRole(role)">编辑</button>
                      <button
                        v-if="role.name !== 'admin'"
                        class="link-button danger"
                        type="button"
                        @click="deleteRole(role)"
                      >删除</button>
                    </div>
                  </div>
                  <div v-if="!permsAsArray(role).includes('*')" class="role-card-perms">
                    <n-tag
                      v-for="p in permsAsArray(role).slice(0, 8)"
                      :key="p"
                      size="tiny"
                      round
                      :bordered="false"
                    >{{ permLabel(p) }}</n-tag>
                    <small v-if="permsAsArray(role).length > 8" class="muted">
                      +{{ permsAsArray(role).length - 8 }} 项
                    </small>
                  </div>
                </article>
              </div>
            </div>

            <!-- Users -->
            <div class="access-block">
              <header class="access-block-head">
                <div class="access-title">
                  <p class="panel-label">用户（{{ allUsers.length }}）</p>
                  <small class="muted">microport_admin 是初始管理员，不可删除。</small>
                </div>
                <div class="access-actions">
                  <n-input
                    v-model:value="userSearch"
                    placeholder="搜索用户名或角色"
                    size="small"
                    clearable
                    style="width:200px"
                  >
                    <template #prefix><n-icon><Search :size="14" /></n-icon></template>
                  </n-input>
                  <n-button size="small" type="primary" @click="openNewUser">
                    <template #icon><n-icon><Plus /></n-icon></template>新建用户
                  </n-button>
                </div>
              </header>
              <div v-if="allUsers.length === 0" class="history-empty">加载中...</div>
              <div v-else-if="filteredUsers.length === 0" class="history-empty">未找到匹配的用户</div>
              <table v-else class="user-table">
                <thead>
                  <tr>
                    <th>用户名</th>
                    <th>角色</th>
                    <th class="user-table-actions">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="user in filteredUsers" :key="user.id">
                    <td><strong>{{ user.username }}</strong></td>
                    <td><n-tag size="tiny" round :bordered="false">{{ user.role_name }}</n-tag></td>
                    <td class="user-table-actions">
                      <button class="link-button" type="button" @click="openEditUser(user)">编辑</button>
                      <button
                        v-if="user.username !== 'microport_admin'"
                        class="link-button danger"
                        type="button"
                        @click="deleteUser(user)"
                      >删除</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

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
              <label class="field"><span>API Base URL</span><n-input v-model:value="agentApiBaseUrl" placeholder="留空使用默认: https://api.deepseek.com" /></label>
              <label class="field"><span>Backend URL</span><n-input v-model:value="agentBackendBaseUrl" /></label>
              <div class="settings-agent-test">
                <n-button
                  class="ghost-button"
                  secondary
                  :loading="agentConfigTesting"
                  :disabled="agentConfigTesting"
                  @click="testAgentConnection"
                >
                  <template #icon>
                    <n-icon><Zap /></n-icon>
                  </template>
                  {{ agentConfigTesting ? "测试中..." : "测试连接" }}
                </n-button>
                <div v-if="agentTestResult" :class="['agent-test-result', agentTestResult.ok ? 'success' : 'error']">
                  <span class="agent-test-status">{{ agentTestResult.ok ? '✅' : '❌' }}</span>
                  <span class="agent-test-message">{{ agentTestResult.message }}</span>
                  <span v-if="agentTestResult.latency_ms > 0" class="agent-test-latency">{{ agentTestResult.latency_ms }}ms</span>
                  <p v-if="agentTestResult.error" class="agent-test-error">{{ agentTestResult.error }}</p>
                </div>
              </div>
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

    <!-- Custom Email Modal (自拟定) -->
    <div
      v-if="showCustomEmail"
      class="modal-backdrop"
      role="presentation"
      @click.self="showCustomEmail = false"
    >
      <section class="create-lead-modal" role="dialog" aria-modal="true" aria-label="自拟定邮件">
        <header class="modal-header">
          <div>
            <p class="panel-label">自拟定邮件</p>
            <h2>{{ customEmail.company_name }}</h2>
          </div>
          <button class="icon-only-button" type="button" aria-label="关闭" @click="showCustomEmail = false">
            <X :size="20" aria-hidden="true" />
          </button>
        </header>
        <div class="create-lead-body">
          <p class="muted" style="margin-bottom:12px">收件人：{{ customEmail.email }}</p>
          <label class="field"><span>主题</span><n-input v-model:value="customEmail.subject" placeholder="输入邮件主题" /></label>
          <label class="field"><span>正文</span><n-input v-model:value="customEmail.body" type="textarea" :autosize="{ minRows: 6, maxRows: 16 }" placeholder="输入邮件正文" /></label>
          <div v-if="availableAttachments.length > 0" class="field">
            <span>附件</span>
            <div class="attachment-checks">
              <label v-for="f in availableAttachments" :key="f" class="attachment-check">
                <n-checkbox :checked="customEmailAttachments.includes(f)" @update:checked="(checked: boolean) => { if (checked) customEmailAttachments.push(f); else customEmailAttachments = customEmailAttachments.filter(a => a !== f); }" />
                <span>{{ f }}</span>
              </label>
            </div>
          </div>
        </div>
        <footer class="create-lead-footer">
          <n-button class="ghost-button" secondary @click="showCustomEmail = false">取消</n-button>
          <n-button class="primary-button" type="primary" :loading="customEmailSending" :disabled="!customEmail.subject || !customEmail.body" @click="sendCustomEmail">
            <template #icon><n-icon><Send /></n-icon></template>
            发送
          </n-button>
        </footer>
      </section>
    </div>

    <!-- Edit Lead Modal -->
    <div
      v-if="showEditLead"
      class="modal-backdrop"
      role="presentation"
      @click.self="showEditLead = false"
    >
      <section class="create-lead-modal" role="dialog" aria-modal="true" aria-label="编辑线索">
        <header class="modal-header">
          <div>
            <p class="panel-label">编辑线索</p>
            <h2>{{ editLead.company_name }}</h2>
          </div>
          <button class="icon-only-button" type="button" aria-label="关闭" @click="showEditLead = false">
            <X :size="20" aria-hidden="true" />
          </button>
        </header>
        <div class="create-lead-body">
          <div class="create-lead-row">
            <label class="field"><span>公司名称</span><n-input v-model:value="editLead.company_name" /></label>
            <label class="field"><span>国家</span><n-input v-model:value="editLead.country" /></label>
          </div>
          <div class="create-lead-row">
            <label class="field"><span>地区</span><n-input v-model:value="editLead.region" /></label>
            <label class="field"><span>网站</span><n-input v-model:value="editLead.website" /></label>
          </div>
          <div class="create-lead-row">
            <label class="field"><span>邮箱</span><n-input v-model:value="editLead.email" /></label>
            <label class="field"><span>联系人</span><n-input v-model:value="editLead.contact_name" /></label>
          </div>
          <div class="create-lead-row">
            <label class="field"><span>类别</span><n-input v-model:value="editLead.category" /></label>
            <label class="field"><span>来源</span><n-input v-model:value="editLead.source" /></label>
          </div>
          <label class="field"><span>匹配理由</span><n-input v-model:value="editLead.match_reason" /></label>
          <div class="create-lead-row">
            <label class="field"><span>评分</span><n-input-number v-model:value="editLead.score" :min="0" :max="100" /></label>
            <label class="field"><span>状态</span>
              <n-select
                v-model:value="editLead.status"
                :options="statusFilterOptions.filter(o => o.value !== '')"
                placeholder="选择状态"
              />
            </label>
          </div>
          <label class="field"><span>备注</span><n-input v-model:value="editLead.notes" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" /></label>
        </div>
        <footer class="create-lead-footer">
          <n-button class="ghost-button" secondary @click="showEditLead = false">取消</n-button>
          <n-button class="primary-button" type="primary" :loading="editLeadSaving" @click="saveEditLead">
            <template #icon><n-icon><Save /></n-icon></template>
            保存
          </n-button>
        </footer>
      </section>
    </div>

    <!-- Role Editor Modal -->
    <div v-if="showRoleEditor" class="modal-backdrop" role="presentation" @click.self="showRoleEditor = false">
      <section class="create-lead-modal role-editor-modal" role="dialog" aria-modal="true" aria-label="编辑角色">
        <header class="modal-header">
          <div>
            <p class="panel-label">权限管理</p>
            <h2>{{ editingRole.id ? `编辑角色：${editingRoleSnapshot.name}` : '新建角色' }}</h2>
          </div>
          <button class="icon-only-button" type="button" @click="showRoleEditor = false"><X :size="20" /></button>
        </header>
        <div class="create-lead-body">
          <div class="role-editor-meta">
            <label class="field" style="flex:1 1 220px">
              <span>角色名称</span>
              <n-input v-model:value="editingRole.name" placeholder="如 operator, viewer" />
            </label>
            <label class="field" style="flex:1 1 220px">
              <span>预设模板</span>
              <n-select
                placeholder="可选：套用预设权限"
                clearable
                :options="permissionPresets.map(p => ({ label: p.label + ' — ' + p.description, value: p.key }))"
                @update:value="(v: string | null) => v && applyPreset(v)"
              />
            </label>
          </div>

          <div class="perm-toolbar">
            <p class="panel-label" style="margin:0">权限（{{ editingRole.permissions.includes("*") ? "全部权限" : `${editingRole.permissions.length} / ${ALL_PERMISSIONS.length}` }}）</p>
            <n-input
              v-model:value="permSearch"
              placeholder="搜索权限"
              size="small"
              clearable
              style="width:220px"
            >
              <template #prefix><n-icon><Search :size="14" /></n-icon></template>
            </n-input>
          </div>

          <div v-if="editingRole.permissions.includes('*')" class="perm-wildcard-banner">
            <ShieldCheck :size="16" />
            <span>该角色拥有全部权限（含未来新增的权限）。点击下方任一权限将解开通配符并展开为显式列表。</span>
          </div>

          <div class="perm-groups">
            <article
              v-for="group in permissionGroupsForUI"
              :key="group.key"
              v-show="visiblePermissionsForGroup(group).length > 0"
              class="perm-group"
            >
              <header class="perm-group-head">
                <button
                  class="perm-group-toggle"
                  type="button"
                  :aria-expanded="!collapsedGroups[group.key]"
                  @click="collapsedGroups[group.key] = !collapsedGroups[group.key]"
                >
                  <ChevronDown
                    :size="16"
                    :style="{ transform: collapsedGroups[group.key] ? 'rotate(-90deg)' : 'none', transition: 'transform 0.15s' }"
                  />
                  <strong>{{ group.label }}</strong>
                  <small class="muted">
                    {{ group.permissions.filter(k => isGrantedKey(editingRole.permissions, k)).length }} / {{ group.permissions.length }}
                  </small>
                </button>
                <n-checkbox
                  :checked="groupSelectionState(group) === 'all'"
                  :indeterminate="groupSelectionState(group) === 'some'"
                  @update:checked="(c: boolean) => toggleGroup(group, c)"
                >整组</n-checkbox>
              </header>
              <div v-if="!collapsedGroups[group.key]" class="perm-group-body">
                <label
                  v-for="key in visiblePermissionsForGroup(group)"
                  :key="key"
                  class="perm-row"
                  :title="permDescription(key)"
                >
                  <n-checkbox
                    :checked="isGrantedKey(editingRole.permissions, key)"
                    @update:checked="(c: boolean) => togglePermissionKey(key, c)"
                  />
                  <div class="perm-row-text">
                    <span class="perm-row-label">{{ permLabel(key) }}</span>
                    <small class="perm-row-desc">{{ permDescription(key) }}</small>
                  </div>
                  <code class="perm-row-key">{{ key }}</code>
                </label>
              </div>
            </article>
          </div>
        </div>
        <footer class="create-lead-footer">
          <small v-if="editingRole.id && roleEditorDirty()" class="muted" style="margin-right:auto">有未保存的修改</small>
          <n-button class="ghost-button" secondary @click="showRoleEditor = false">取消</n-button>
          <n-button
            class="primary-button"
            type="primary"
            :disabled="!editingRole.name.trim() || (editingRole.id > 0 && !roleEditorDirty())"
            @click="saveRole"
          >保存</n-button>
        </footer>
      </section>
    </div>

    <!-- User Editor Modal -->
    <div v-if="showUserEditor" class="modal-backdrop" role="presentation" @click.self="showUserEditor = false">
      <section class="create-lead-modal" role="dialog" aria-modal="true" aria-label="编辑用户">
        <header class="modal-header">
          <div>
            <p class="panel-label">用户管理</p>
            <h2>{{ editingUser.id ? `编辑用户：${editingUserSnapshot.username}` : '新建用户' }}</h2>
          </div>
          <button class="icon-only-button" type="button" @click="showUserEditor = false"><X :size="20" /></button>
        </header>
        <div class="create-lead-body">
          <label class="field"><span>用户名</span><n-input v-model:value="editingUser.username" /></label>
          <label class="field">
            <span>密码{{ editingUser.id ? '（留空则不修改）' : '' }}</span>
            <div class="password-row">
              <n-input
                v-model:value="editingUser.password"
                :type="editingUser.id ? 'text' : 'password'"
                show-password-on="click"
                :placeholder="editingUser.id ? '留空表示不修改密码' : '至少 6 个字符'"
                style="flex:1"
              />
              <n-button
                size="small"
                secondary
                title="生成 12 位随机密码"
                @click="generateNewPasswordForUser"
              >
                <template #icon><n-icon><RefreshCw :size="14" /></n-icon></template>
                生成
              </n-button>
            </div>
            <small v-if="editingUser.id && editingUser.password" class="hint warning">
              保存后将弹出一次性密码确认框，请提醒用户立即记录。
            </small>
          </label>
          <label class="field">
            <span>角色</span>
            <n-select v-model:value="editingUser.role_id" :options="allRoles.map(r => ({ label: r.name, value: r.id }))" />
          </label>
          <small
            v-if="editingUser.id && editingUser.role_id !== editingUserSnapshot.role_id"
            class="hint info"
          >
            角色变更后该用户的权限将立即生效（无需重新登录，最长 30 秒后端缓存自动刷新）。
          </small>
        </div>
        <footer class="create-lead-footer">
          <n-button class="ghost-button" secondary @click="showUserEditor = false">取消</n-button>
          <n-button
            class="primary-button"
            type="primary"
            :disabled="!editingUser.username.trim() || (editingUser.id === 0 && !editingUser.password) || (editingUser.id > 0 && !userEditorDirty())"
            @click="saveUser"
          >保存</n-button>
        </footer>
      </section>
    </div>

    <!-- Reset Password Result Modal — one-time display after admin resets a user's password -->
    <div v-if="showResetPasswordResult" class="modal-backdrop" role="presentation" @click.self="showResetPasswordResult = false">
      <section class="create-lead-modal" role="dialog" aria-modal="true" aria-label="新密码">
        <header class="modal-header">
          <div>
            <p class="panel-label">密码已重置</p>
            <h2>{{ resetPasswordResult.username }} 的新密码</h2>
          </div>
          <button class="icon-only-button" type="button" @click="showResetPasswordResult = false"><X :size="20" /></button>
        </header>
        <div class="create-lead-body">
          <p class="reset-password-warning">⚠️ 此密码仅显示一次，请立即复制并发给用户。关闭此对话框后将无法再次查看。</p>
          <div class="reset-password-display">
            <code>{{ resetPasswordResult.password }}</code>
            <n-button size="small" secondary @click="copyTextToClipboard(resetPasswordResult.password, '密码已复制到剪贴板')">
              复制
            </n-button>
          </div>
        </div>
        <footer class="create-lead-footer">
          <n-button class="primary-button" type="primary" @click="showResetPasswordResult = false">已记录</n-button>
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
  </n-notification-provider>
  </n-dialog-provider>
  </n-message-provider>
  </n-config-provider>
</template>
