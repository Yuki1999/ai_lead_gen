/**
 * Settings page state, role & user management.
 *
 * All refs are module-level so functions can reference them directly
 * without body changes when extracted from App.vue.
 */
import { ref } from "vue";
import { request } from "@/api";
import { hasPermission } from "@/composables/useAuth";
import { notice, error, setNotice } from "@/composables/useNotifications";
import type { EmailEvent } from "@/composables/useLeads";
import {
  agentProviderName,
  agentModelName,
  agentApiBaseUrl,
  agentBackendBaseUrl,
  saveAgentConfig,
} from "@/composables/useAgent";

// ── Interfaces ────────────────────────────────────────

export interface SettingsResponse {
  sync_enabled: boolean;
  sync_interval_minutes: number;
  email_server: string;
  email_user: string;
  email_password_set: boolean;
  agent_provider: string;
  agent_model: string;
  api_base_url: string;
  backend_base_url: string;
  email_template: string;
  scoring_rules: string;
}

// ── Settings state ────────────────────────────────────

export const settings = ref<SettingsResponse>({
  sync_enabled: false,
  sync_interval_minutes: 15,
  email_server: "mail.microport.com.cn",
  email_user: "",
  email_password_set: false,
  agent_provider: "deepseek",
  agent_model: "deepseek-v4-pro",
  api_base_url: "",
  backend_base_url: "http://localhost:8000",
  email_template: "",
  scoring_rules: "",
});
export const settingsAgentKeyInput = ref("");
export const settingsEmailPasswordInput = ref("");
export const settingsEmailTemplate = ref("");
export const settingsScoringRules = ref("");
export const settingsLoading = ref(false);
export const settingsSaving = ref(false);
export const settingsTab = ref<
  "email" | "sync" | "agent" | "template" | "scoring" | "access"
>("email");

// Drafts (shown on workspace page, stored here as cross-cutting)
export const drafts = ref<EmailEvent[]>([]);
export const draftCount = ref(0);

export function setDrafts(newDrafts: EmailEvent[], count: number): void {
  drafts.value = newDrafts;
  draftCount.value = count;
}

// ── Roles & Users state ───────────────────────────────

export const ALL_PERMISSIONS = [
  "leads:read",
  "leads:write",
  "outreach:send",
  "outreach:approve",
  "replies:sync",
  "replies:analyze",
  "settings:read",
  "settings:write",
  "users:manage",
  "agent:chat",
];
export const permLabels: Record<string, string> = {
  "leads:read": "查看线索",
  "leads:write": "编辑线索",
  "outreach:send": "发送邮件",
  "outreach:approve": "审批邮件",
  "replies:sync": "同步回复",
  "replies:analyze": "分析回复",
  "settings:read": "查看设置",
  "settings:write": "修改设置",
  "users:manage": "管理用户",
  "agent:chat": "使用 Agent",
};

export const allRoles = ref<
  Array<{ id: number; name: string; permissions: string; user_count: number }>
>([]);
export const allUsers = ref<
  Array<{
    id: number;
    username: string;
    role_id: number;
    role_name: string;
  }>
>([]);
export const showRoleEditor = ref(false);
export const showUserEditor = ref(false);
export const editingRole = ref<{
  id: number;
  name: string;
  permissions: string[];
}>({ id: 0, name: "", permissions: [] });
export const editingUser = ref<{
  id: number;
  username: string;
  password: string;
  role_id: number;
}>({ id: 0, username: "", password: "", role_id: 0 });

// New lead creation (used in workspace page)
export const showCreateLead = ref(false);
export const createError = ref("");
export const newLead = ref({
  company_name: "",
  region: "",
  country: "",
  website: "",
  contact_name: "",
  email: "",
  category: "medical device distributor",
});

// ── Functions ─────────────────────────────────────────

export async function loadRolesAndUsers(): Promise<void> {
  try {
    const [roles, users] = await Promise.all([
      request<typeof allRoles.value>("/roles"),
      request<typeof allUsers.value>("/users"),
    ]);
    allRoles.value = roles;
    allUsers.value = users;
  } catch {
    // silently ignore
  }
}

export function openNewRole(): void {
  editingRole.value = { id: 0, name: "", permissions: [] };
  showRoleEditor.value = true;
}

export function openEditRole(role: {
  id: number;
  name: string;
  permissions: string | string[];
}): void {
  editingRole.value = {
    id: role.id,
    name: role.name,
    permissions:
      typeof role.permissions === "string"
        ? (JSON.parse(role.permissions) as string[])
        : [...role.permissions],
  };
  showRoleEditor.value = true;
}

export async function saveRole(): Promise<void> {
  const { id, name, permissions } = editingRole.value;
  const body = JSON.stringify({ name, permissions });
  if (id) {
    await request(`/roles/${id}`, { method: "PUT", body });
  } else {
    await request("/roles", { method: "POST", body });
  }
  showRoleEditor.value = false;
  await loadRolesAndUsers();
}

export async function deleteRole(roleId: number): Promise<void> {
  await request(`/roles/${roleId}`, { method: "DELETE" });
  await loadRolesAndUsers();
}

export function openNewUser(): void {
  editingUser.value = { id: 0, username: "", password: "", role_id: 0 };
  showUserEditor.value = true;
}

export function openEditUser(user: {
  id: number;
  username: string;
  role_id: number;
  role_name?: string;
}): void {
  editingUser.value = { ...user, password: "" };
  showUserEditor.value = true;
}

export async function saveUser(): Promise<void> {
  const { id, username, password, role_id } = editingUser.value;
  const bodyObj: Record<string, unknown> = { username, role_id };
  if (password) bodyObj.password = password;
  const body = JSON.stringify(bodyObj);
  if (id) {
    await request(`/users/${id}`, { method: "PUT", body });
  } else {
    await request("/users", { method: "POST", body });
  }
  showUserEditor.value = false;
  await loadRolesAndUsers();
}

export async function deleteUser(userId: number): Promise<void> {
  await request(`/users/${userId}`, { method: "DELETE" });
  await loadRolesAndUsers();
}

export async function loadSettings(): Promise<void> {
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

export async function saveSettingsFn(): Promise<void> {
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
    await saveAgentConfig();
    setNotice("设置已保存");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "设置保存失败";
  } finally {
    settingsSaving.value = false;
  }
}

export const saveSettings = saveSettingsFn;

export function useSettings() {
  return {
    settings,
    settingsAgentKeyInput,
    settingsEmailPasswordInput,
    settingsEmailTemplate,
    settingsScoringRules,
    settingsLoading,
    settingsSaving,
    settingsTab,
    drafts,
    draftCount,
    ALL_PERMISSIONS,
    permLabels,
    allRoles,
    allUsers,
    showRoleEditor,
    showUserEditor,
    editingRole,
    editingUser,
    showCreateLead,
    createError,
    newLead,
    loadRolesAndUsers,
    openNewRole,
    openEditRole,
    saveRole,
    deleteRole,
    openNewUser,
    openEditUser,
    saveUser,
    deleteUser,
    loadSettings,
    saveSettings,
  };
}
