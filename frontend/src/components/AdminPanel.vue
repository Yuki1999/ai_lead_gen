<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  Check,
  KeyRound,
  MailX,
  Pencil,
  Plus,
  RotateCcw,
  ScrollText,
  Trash2,
  UserPlus,
  Users,
  X,
} from "lucide-vue-next";

interface Permission {
  key: string;
  group: string;
  label: string;
  description: string;
}
interface Role {
  id: number;
  name: string;
  description: string;
  permissions: string[];
  is_system: boolean;
  user_count?: number;
}
interface AdminUser {
  id: number;
  username: string;
  display_name: string;
  is_active: boolean;
  is_superadmin: boolean;
  roles: { id: number; name: string }[];
}

// The parent passes its authenticated request() helper.
const props = defineProps<{
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
}>();

interface Suppression {
  id: number;
  email: string;
  reason: string;
  source: string;
  notes: string;
  created_at: string;
}
interface AuditEvent {
  id: number;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: string;
  created_at: string;
}

const tab = ref<"users" | "roles" | "suppressions" | "audit">("users");
const permissions = ref<Permission[]>([]);
const roles = ref<Role[]>([]);
const users = ref<AdminUser[]>([]);
const suppressions = ref<Suppression[]>([]);
const audit = ref<AuditEvent[]>([]);
const newSuppressEmail = ref("");
const newSuppressReason = ref("manual");
const loading = ref(true);
const toast = ref<{ text: string; kind: "ok" | "err" } | null>(null);

function fmtTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}
const reasonLabel: Record<string, string> = {
  unsubscribe: "退订",
  "reply-optout": "回复退订",
  bounce: "退信",
  manual: "手动",
  complaint: "投诉",
};

const permissionGroups = computed(() => {
  const groups: { name: string; items: Permission[] }[] = [];
  for (const p of permissions.value) {
    let g = groups.find((x) => x.name === p.group);
    if (!g) {
      g = { name: p.group, items: [] };
      groups.push(g);
    }
    g.items.push(p);
  }
  return groups;
});
const permLabel = (key: string) => permissions.value.find((p) => p.key === key)?.label || key;
const roleName = (id: number) => roles.value.find((r) => r.id === id)?.name || "";

function flash(text: string, kind: "ok" | "err" = "ok"): void {
  toast.value = { text, kind };
  setTimeout(() => (toast.value = null), 2600);
}
function errText(e: unknown): string {
  if (e instanceof Error) {
    try {
      return (JSON.parse(e.message) as { detail?: string }).detail || e.message;
    } catch {
      return e.message;
    }
  }
  return "操作失败";
}
function avatarText(name: string): string {
  return (name || "?").trim().slice(0, 1).toUpperCase();
}

async function loadAll(): Promise<void> {
  loading.value = true;
  try {
    const [perm, roleResp, userResp] = await Promise.all([
      props.request<{ permissions: Permission[] }>("/admin/permissions"),
      props.request<{ roles: Role[] }>("/admin/roles"),
      props.request<{ users: AdminUser[] }>("/admin/users"),
    ]);
    permissions.value = perm.permissions;
    roles.value = roleResp.roles;
    users.value = userResp.users;
  } catch (e) {
    flash(errText(e), "err");
  } finally {
    loading.value = false;
  }
}
async function reloadRoles() {
  roles.value = (await props.request<{ roles: Role[] }>("/admin/roles")).roles;
}
async function loadSuppressions() {
  try {
    suppressions.value = (await props.request<{ suppressions: Suppression[] }>("/admin/suppressions")).suppressions;
  } catch (e) {
    flash(errText(e), "err");
  }
}
async function loadAudit() {
  try {
    audit.value = (await props.request<{ events: AuditEvent[] }>("/admin/audit?limit=300")).events;
  } catch (e) {
    flash(errText(e), "err");
  }
}
async function addSuppression() {
  const email = newSuppressEmail.value.trim();
  if (!email || !email.includes("@")) {
    flash("请输入有效邮箱", "err");
    return;
  }
  try {
    await props.request("/admin/suppressions", {
      method: "POST",
      body: JSON.stringify({ email, reason: newSuppressReason.value }),
    });
    newSuppressEmail.value = "";
    flash("已加入抑制名单");
    await loadSuppressions();
  } catch (e) {
    flash(errText(e), "err");
  }
}
async function removeSuppression(email: string) {
  if (!globalThis.confirm(`将「${email}」移出抑制名单？之后可能会再次向其发信。`)) return;
  try {
    await props.request(`/admin/suppressions?email=${encodeURIComponent(email)}`, { method: "DELETE" });
    flash("已移出抑制名单");
    await loadSuppressions();
  } catch (e) {
    flash(errText(e), "err");
  }
}

function switchTab(t: typeof tab.value) {
  tab.value = t;
  if (t === "suppressions" && suppressions.value.length === 0) void loadSuppressions();
  if (t === "audit" && audit.value.length === 0) void loadAudit();
}
async function reloadUsers() {
  users.value = (await props.request<{ users: AdminUser[] }>("/admin/users")).users;
}

// ── Role drawer ───────────────────────────────────────────
const roleDrawer = ref(false);
const savingRole = ref(false);
const roleForm = ref<{ id: number | null; name: string; description: string; permissions: string[]; is_system: boolean }>({
  id: null,
  name: "",
  description: "",
  permissions: [],
  is_system: false,
});

function openRoleDrawer(role?: Role): void {
  if (role) {
    roleForm.value = {
      id: role.id,
      name: role.name,
      description: role.description,
      permissions: [...role.permissions],
      is_system: role.is_system,
    };
  } else {
    roleForm.value = { id: null, name: "", description: "", permissions: [], is_system: false };
  }
  roleDrawer.value = true;
}
function togglePerm(key: string): void {
  const i = roleForm.value.permissions.indexOf(key);
  if (i >= 0) roleForm.value.permissions.splice(i, 1);
  else roleForm.value.permissions.push(key);
}
function groupAllSelected(group: { items: Permission[] }): boolean {
  return group.items.every((p) => roleForm.value.permissions.includes(p.key));
}
function toggleGroup(group: { items: Permission[] }): void {
  const all = groupAllSelected(group);
  for (const p of group.items) {
    const i = roleForm.value.permissions.indexOf(p.key);
    if (all && i >= 0) roleForm.value.permissions.splice(i, 1);
    else if (!all && i < 0) roleForm.value.permissions.push(p.key);
  }
}
async function saveRole(): Promise<void> {
  if (!roleForm.value.name.trim()) {
    flash("请填写角色名", "err");
    return;
  }
  savingRole.value = true;
  try {
    const body = {
      name: roleForm.value.name.trim(),
      description: roleForm.value.description,
      permissions: roleForm.value.permissions,
    };
    if (roleForm.value.id === null) {
      await props.request("/admin/roles", { method: "POST", body: JSON.stringify(body) });
      flash("角色已创建");
    } else {
      await props.request(`/admin/roles/${roleForm.value.id}`, { method: "PATCH", body: JSON.stringify(body) });
      flash("角色已更新");
    }
    roleDrawer.value = false;
    await Promise.all([reloadRoles(), reloadUsers()]);
  } catch (e) {
    flash(errText(e), "err");
  } finally {
    savingRole.value = false;
  }
}
async function removeRole(role: Role): Promise<void> {
  if (!globalThis.confirm(`确定删除角色「${role.name}」？`)) return;
  try {
    await props.request(`/admin/roles/${role.id}`, { method: "DELETE" });
    flash("角色已删除");
    await reloadRoles();
  } catch (e) {
    flash(errText(e), "err");
  }
}

// ── User drawer ───────────────────────────────────────────
const userDrawer = ref(false);
const savingUser = ref(false);
const userForm = ref<{
  id: number | null;
  username: string;
  password: string;
  display_name: string;
  is_active: boolean;
  is_superadmin: boolean;
  role_ids: number[];
}>({
  id: null,
  username: "",
  password: "",
  display_name: "",
  is_active: true,
  is_superadmin: false,
  role_ids: [],
});

function openUserDrawer(user?: AdminUser): void {
  if (user) {
    userForm.value = {
      id: user.id,
      username: user.username,
      password: "",
      display_name: user.display_name,
      is_active: user.is_active,
      is_superadmin: user.is_superadmin,
      role_ids: user.roles.map((r) => r.id),
    };
  } else {
    userForm.value = {
      id: null,
      username: "",
      password: "",
      display_name: "",
      is_active: true,
      is_superadmin: false,
      role_ids: [],
    };
  }
  userDrawer.value = true;
}
function toggleUserRole(roleId: number): void {
  const i = userForm.value.role_ids.indexOf(roleId);
  if (i >= 0) userForm.value.role_ids.splice(i, 1);
  else userForm.value.role_ids.push(roleId);
}
async function saveUser(): Promise<void> {
  if (userForm.value.id === null && (!userForm.value.username.trim() || userForm.value.password.length < 6)) {
    flash("用户名必填，密码至少 6 位", "err");
    return;
  }
  savingUser.value = true;
  try {
    if (userForm.value.id === null) {
      await props.request("/admin/users", {
        method: "POST",
        body: JSON.stringify({
          username: userForm.value.username.trim(),
          password: userForm.value.password,
          display_name: userForm.value.display_name,
          is_active: userForm.value.is_active,
          is_superadmin: userForm.value.is_superadmin,
          role_ids: userForm.value.role_ids,
        }),
      });
      flash("用户已创建");
    } else {
      await props.request(`/admin/users/${userForm.value.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: userForm.value.display_name,
          is_active: userForm.value.is_active,
          is_superadmin: userForm.value.is_superadmin,
          role_ids: userForm.value.role_ids,
        }),
      });
      flash("用户已更新");
    }
    userDrawer.value = false;
    await reloadUsers();
  } catch (e) {
    flash(errText(e), "err");
  } finally {
    savingUser.value = false;
  }
}
async function resetPassword(user: AdminUser): Promise<void> {
  const pwd = globalThis.prompt(`为「${user.username}」设置新密码（至少 6 位）`);
  if (!pwd) return;
  if (pwd.length < 6) {
    flash("密码至少 6 位", "err");
    return;
  }
  try {
    await props.request(`/admin/users/${user.id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password: pwd }),
    });
    flash("密码已重置");
  } catch (e) {
    flash(errText(e), "err");
  }
}
async function removeUser(user: AdminUser): Promise<void> {
  if (!globalThis.confirm(`确定删除用户「${user.username}」？`)) return;
  try {
    await props.request(`/admin/users/${user.id}`, { method: "DELETE" });
    flash("用户已删除");
    await reloadUsers();
  } catch (e) {
    flash(errText(e), "err");
  }
}

onMounted(loadAll);
</script>

<template>
  <section class="admin">
    <!-- Header: tabs only; the page title lives in the shared topbar. -->
    <header class="admin-head">
      <div class="seg">
        <button :class="['seg-btn', { active: tab === 'users' }]" @click="switchTab('users')">
          <Users :size="15" /> 用户 <span class="seg-count">{{ users.length }}</span>
        </button>
        <button :class="['seg-btn', { active: tab === 'roles' }]" @click="switchTab('roles')">
          <KeyRound :size="15" /> 角色 <span class="seg-count">{{ roles.length }}</span>
        </button>
        <button :class="['seg-btn', { active: tab === 'suppressions' }]" @click="switchTab('suppressions')">
          <MailX :size="15" /> 抑制名单 <span class="seg-count">{{ suppressions.length }}</span>
        </button>
        <button :class="['seg-btn', { active: tab === 'audit' }]" @click="switchTab('audit')">
          <ScrollText :size="15" /> 审计日志
        </button>
      </div>
    </header>

    <transition name="fade">
      <div v-if="toast" :class="['admin-toast', toast.kind]">
        <Check v-if="toast.kind === 'ok'" :size="15" /><X v-else :size="15" />
        {{ toast.text }}
      </div>
    </transition>

    <div v-if="loading" class="admin-loading">加载中…</div>

    <!-- ── USERS ── -->
    <div v-else-if="tab === 'users'" class="panel">
      <div class="panel-bar">
        <span class="panel-bar-label">共 {{ users.length }} 个账号</span>
        <button class="btn-primary" @click="openUserDrawer()"><UserPlus :size="16" /> 新建用户</button>
      </div>

      <div class="ucard-list">
        <article v-for="u in users" :key="u.id" class="ucard">
          <span class="avatar" :class="{ super: u.is_superadmin }">{{ avatarText(u.display_name || u.username) }}</span>
          <div class="ucard-main">
            <div class="ucard-name">
              {{ u.display_name || u.username }}
              <span class="dim">@{{ u.username }}</span>
              <span v-if="u.is_superadmin" class="tag tag-amber">超级管理员</span>
            </div>
            <div class="ucard-roles">
              <span v-if="u.is_superadmin" class="dim sm">拥有全部权限</span>
              <span v-else-if="u.roles.length === 0" class="dim sm">未分配角色</span>
              <span v-for="r in u.roles" v-else :key="r.id" class="tag">{{ r.name }}</span>
            </div>
          </div>
          <span :class="['pill', u.is_active ? 'pill-on' : 'pill-off']">
            <i></i>{{ u.is_active ? "启用" : "停用" }}
          </span>
          <div class="row-actions">
            <button title="编辑" @click="openUserDrawer(u)"><Pencil :size="15" /></button>
            <button title="重置密码" @click="resetPassword(u)"><KeyRound :size="15" /></button>
            <button title="删除" class="danger" @click="removeUser(u)"><Trash2 :size="15" /></button>
          </div>
        </article>
      </div>
    </div>

    <!-- ── ROLES ── -->
    <div v-else-if="tab === 'roles'" class="panel">
      <div class="panel-bar">
        <span class="panel-bar-label">共 {{ roles.length }} 个角色</span>
        <button class="btn-primary" @click="openRoleDrawer()"><Plus :size="16" /> 新建角色</button>
      </div>

      <div class="role-grid">
        <article v-for="r in roles" :key="r.id" class="role-card">
          <div class="role-card-head">
            <h3>{{ r.name }}<span v-if="r.is_system" class="tag tag-soft">内置</span></h3>
            <div class="role-actions">
              <button title="编辑" @click="openRoleDrawer(r)"><Pencil :size="15" /></button>
              <button title="删除" class="danger" :disabled="r.is_system" @click="removeRole(r)"><Trash2 :size="15" /></button>
            </div>
          </div>
          <p class="role-desc">{{ r.description || "—" }}</p>
          <div class="role-perm-preview">
            <span v-if="r.permissions.length === 0" class="dim sm">无权限</span>
            <span v-for="key in r.permissions.slice(0, 6)" :key="key" class="tag tag-soft">{{ permLabel(key) }}</span>
            <span v-if="r.permissions.length > 6" class="tag tag-soft">+{{ r.permissions.length - 6 }}</span>
          </div>
          <div class="role-card-foot">
            <span><KeyRound :size="13" /> {{ r.permissions.length }} 项权限</span>
            <span><Users :size="13" /> {{ r.user_count ?? 0 }} 个用户</span>
          </div>
        </article>
      </div>
    </div>

    <!-- ── SUPPRESSIONS (退订/抑制名单) ── -->
    <div v-else-if="tab === 'suppressions'" class="panel">
      <div class="compliance-note">
        <MailX :size="16" class="compliance-note-icon" />
        <span>名单内的邮箱<strong>不会再被发送任何邮件</strong>。退订链接点击、回复"不感兴趣"会自动加入；也可手动添加退信/投诉地址。</span>
      </div>

      <div class="panel-bar">
        <span class="panel-bar-label">共 {{ suppressions.length }} 条抑制记录</span>
        <button class="btn-ghost" @click="loadSuppressions"><RotateCcw :size="14" /> 刷新</button>
      </div>

      <form class="suppress-add-card" @submit.prevent="addSuppression">
        <input v-model="newSuppressEmail" type="email" placeholder="email@example.com" required />
        <select v-model="newSuppressReason">
          <option value="manual">手动</option>
          <option value="bounce">退信</option>
          <option value="complaint">投诉</option>
        </select>
        <button type="submit" class="btn-primary"><Plus :size="16" /> 加入名单</button>
      </form>

      <div v-if="suppressions.length === 0" class="empty">暂无抑制记录</div>
      <div v-else class="ucard-list">
        <article v-for="s in suppressions" :key="s.id" class="ucard">
          <span class="avatar suppress-avatar" :class="'reason-' + s.reason"><MailX :size="18" /></span>
          <div class="ucard-main">
            <div class="ucard-name">{{ s.email }}<span class="tag" :class="'tag-reason-' + s.reason">{{ reasonLabel[s.reason] || s.reason }}</span></div>
            <div class="dim sm">{{ s.source || "—" }} · {{ fmtTime(s.created_at) }}</div>
          </div>
          <div class="row-actions">
            <button title="移出名单" @click="removeSuppression(s.email)"><RotateCcw :size="15" /></button>
          </div>
        </article>
      </div>
    </div>

    <!-- ── AUDIT LOG (审计日志) ── -->
    <div v-else-if="tab === 'audit'" class="panel">
      <div class="panel-bar">
        <span class="panel-bar-label">最近 {{ audit.length }} 条操作记录（发信、登录、权限、退订等）</span>
        <button class="btn-ghost" @click="loadAudit"><RotateCcw :size="14" /> 刷新</button>
      </div>
      <div v-if="audit.length === 0" class="empty">暂无审计记录</div>
      <table v-else class="audit-table">
        <thead>
          <tr><th>时间</th><th>操作者</th><th>动作</th><th>对象</th><th>详情</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in audit" :key="e.id">
            <td class="nowrap dim sm">{{ fmtTime(e.created_at) }}</td>
            <td>{{ e.actor }}</td>
            <td><span class="tag" :class="{ 'tag-amber': e.action.includes('delete'), 'tag-soft': !e.action.includes('delete') }">{{ e.action }}</span></td>
            <td class="dim sm">{{ e.target_type }}<span v-if="e.target_id"> #{{ e.target_id }}</span></td>
            <td class="dim sm">{{ e.detail }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ── USER DRAWER ── -->
    <transition name="drawer">
      <div v-if="userDrawer" class="drawer-scrim" @click.self="userDrawer = false">
        <aside class="drawer">
          <header class="drawer-head">
            <h3>{{ userForm.id === null ? "新建用户" : "编辑用户" }}</h3>
            <button class="icon-x" @click="userDrawer = false"><X :size="18" /></button>
          </header>
          <div class="drawer-body">
            <div class="drawer-id">
              <span class="avatar lg" :class="{ super: userForm.is_superadmin }">
                {{ avatarText(userForm.display_name || userForm.username) }}
              </span>
              <div>
                <strong>{{ userForm.display_name || userForm.username || "新用户" }}</strong>
                <small v-if="userForm.username">@{{ userForm.username }}</small>
              </div>
            </div>

            <label v-if="userForm.id === null" class="fld">
              <span>用户名</span>
              <input v-model="userForm.username" type="text" placeholder="登录用户名" />
            </label>
            <label v-if="userForm.id === null" class="fld">
              <span>初始密码 <em>至少 6 位</em></span>
              <input v-model="userForm.password" type="password" placeholder="设置初始密码" />
            </label>
            <label class="fld">
              <span>姓名 / 显示名</span>
              <input v-model="userForm.display_name" type="text" placeholder="例如 张明" />
            </label>

            <div class="switch-row">
              <div><strong>启用账号</strong><small>停用后无法登录</small></div>
              <button type="button" :class="['switch', { on: userForm.is_active }]" @click="userForm.is_active = !userForm.is_active"><i></i></button>
            </div>
            <div class="switch-row">
              <div><strong>超级管理员</strong><small>拥有全部权限，忽略角色</small></div>
              <button type="button" :class="['switch', { on: userForm.is_superadmin }]" @click="userForm.is_superadmin = !userForm.is_superadmin"><i></i></button>
            </div>

            <div class="fld" :class="{ disabled: userForm.is_superadmin }">
              <span>分配角色</span>
              <div class="chip-pick">
                <button
                  v-for="r in roles"
                  :key="r.id"
                  type="button"
                  :class="['chip-toggle', { on: userForm.role_ids.includes(r.id) }]"
                  :disabled="userForm.is_superadmin"
                  @click="toggleUserRole(r.id)"
                >
                  <Check v-if="userForm.role_ids.includes(r.id)" :size="13" /> {{ r.name }}
                </button>
                <span v-if="roles.length === 0" class="dim sm">暂无角色，请先到「角色」页创建</span>
              </div>
            </div>
          </div>
          <footer class="drawer-foot">
            <button class="btn-ghost" @click="userDrawer = false">取消</button>
            <button class="btn-primary" :disabled="savingUser" @click="saveUser">{{ savingUser ? "保存中…" : "保存" }}</button>
          </footer>
        </aside>
      </div>
    </transition>

    <!-- ── ROLE DRAWER ── -->
    <transition name="drawer">
      <div v-if="roleDrawer" class="drawer-scrim" @click.self="roleDrawer = false">
        <aside class="drawer wide">
          <header class="drawer-head">
            <h3>{{ roleForm.id === null ? "新建角色" : "编辑角色" }}</h3>
            <button class="icon-x" @click="roleDrawer = false"><X :size="18" /></button>
          </header>
          <div class="drawer-body">
            <label class="fld">
              <span>角色名</span>
              <input v-model="roleForm.name" type="text" placeholder="例如 区域操作员" />
            </label>
            <label class="fld">
              <span>描述</span>
              <input v-model="roleForm.description" type="text" placeholder="角色用途说明（可选）" />
            </label>

            <div class="perm-head">
              <span>操作级权限</span>
              <span class="perm-count">{{ roleForm.permissions.length }} / {{ permissions.length }}</span>
            </div>
            <div v-for="g in permissionGroups" :key="g.name" class="perm-group">
              <div class="perm-group-head">
                <strong>{{ g.name }}</strong>
                <button type="button" class="link-btn" @click="toggleGroup(g)">
                  {{ groupAllSelected(g) ? "取消全选" : "全选" }}
                </button>
              </div>
              <div class="perm-items">
                <button
                  v-for="p in g.items"
                  :key="p.key"
                  type="button"
                  :class="['perm-item', { on: roleForm.permissions.includes(p.key) }]"
                  :title="p.description"
                  @click="togglePerm(p.key)"
                >
                  <span class="perm-check"><Check v-if="roleForm.permissions.includes(p.key)" :size="13" /></span>
                  <span class="perm-text"><strong>{{ p.label }}</strong><small>{{ p.description }}</small></span>
                </button>
              </div>
            </div>
          </div>
          <footer class="drawer-foot">
            <button class="btn-ghost" @click="roleDrawer = false">取消</button>
            <button class="btn-primary" :disabled="savingRole" @click="saveRole">{{ savingRole ? "保存中…" : "保存角色" }}</button>
          </footer>
        </aside>
      </div>
    </transition>
  </section>
</template>

<style scoped>
.admin {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1080px;
}

/* Header */
.admin-head {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

/* Segmented control */
.seg {
  display: flex; gap: 4px; padding: 4px;
  background: var(--surface-muted);
  border: 1px solid var(--border); border-radius: 10px;
}
.seg-btn {
  display: inline-flex; align-items: center; gap: 6px;
  border: 0; background: transparent; cursor: pointer;
  padding: 7px 14px; border-radius: 7px;
  font-size: 13px; font-weight: 700; color: var(--text-muted);
  transition: all 140ms ease;
}
.seg-btn:hover { color: var(--text); }
.seg-btn.active { background: var(--surface); color: var(--primary-strong); box-shadow: var(--shadow-xs); }
.seg-count {
  font-size: 11px; font-weight: 800; padding: 1px 7px; border-radius: 999px;
  background: var(--bg-subtle); color: var(--text-muted);
}
.seg-btn.active .seg-count { background: var(--primary-soft); color: var(--primary-strong); }

/* Toast */
.admin-toast {
  position: fixed; top: 22px; left: 50%; transform: translateX(-50%);
  z-index: 1200; display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 18px; border-radius: 10px; font-size: 13px; font-weight: 700;
  box-shadow: var(--shadow-md);
}
.admin-toast.ok { background: var(--success-soft); color: var(--success); }
.admin-toast.err { background: var(--danger-soft); color: var(--danger); }

.admin-loading { padding: 60px; text-align: center; color: var(--text-soft); }

/* Panel bar */
.panel { display: flex; flex-direction: column; gap: 16px; }
.panel-bar { display: flex; justify-content: space-between; align-items: center; }
.panel-bar-label { font-size: 13px; color: var(--text-muted); font-weight: 600; }

/* Buttons */
.btn-primary {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--primary); color: #fff; border: 0;
  padding: 9px 16px; border-radius: 9px; font-size: 13px; font-weight: 700;
  cursor: pointer; transition: background 140ms ease;
}
.btn-primary:hover { background: var(--primary-strong); }
.btn-primary:disabled { opacity: .6; cursor: not-allowed; }
.btn-ghost {
  background: var(--surface); border: 1px solid var(--border);
  padding: 9px 16px; border-radius: 9px; font-size: 13px; font-weight: 600;
  cursor: pointer; color: var(--text-muted);
}
.btn-ghost:hover { background: var(--surface-muted); color: var(--text); }

/* User cards */
.ucard-list { display: flex; flex-direction: column; gap: 10px; }
.ucard {
  display: flex; align-items: center; gap: 14px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 14px 16px;
  box-shadow: var(--shadow-xs); transition: box-shadow 140ms ease, border-color 140ms ease;
}
.ucard:hover { box-shadow: var(--shadow-sm); border-color: var(--border-strong); }
.avatar {
  width: 40px; height: 40px; border-radius: 11px; flex-shrink: 0;
  display: grid; place-items: center; font-weight: 800; font-size: 15px;
  background: linear-gradient(135deg, #3b82f6, #2563eb); color: #fff;
}
.avatar.super { background: linear-gradient(135deg, #f59e0b, #d97706); }
.avatar.lg { width: 52px; height: 52px; border-radius: 14px; font-size: 19px; }
.ucard-main { flex: 1; min-width: 0; }
.ucard-name { font-weight: 700; font-size: 14px; color: var(--text); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ucard-roles { margin-top: 5px; display: flex; gap: 5px; flex-wrap: wrap; }
.dim { color: var(--text-soft); font-weight: 500; }
.dim.sm, .sm { font-size: 12px; }

/* Tags / pills */
.tag {
  display: inline-flex; align-items: center; font-size: 11px; font-weight: 700;
  padding: 2px 9px; border-radius: 999px;
  background: var(--primary-soft); color: var(--primary-strong);
}
.tag-soft { background: var(--bg-subtle); color: var(--text-muted); }
.tag-amber { background: var(--warning-soft); color: var(--warning); }
.pill {
  display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0;
  font-size: 12px; font-weight: 700; padding: 4px 11px; border-radius: 999px;
}
.pill i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.pill-on { background: var(--success-soft); color: var(--success); }
.pill-on i { background: var(--success); }
.pill-off { background: var(--bg-subtle); color: var(--text-soft); }
.pill-off i { background: var(--text-soft); }

/* Row actions */
.row-actions, .role-actions { display: flex; gap: 4px; flex-shrink: 0; }
.row-actions button, .role-actions button {
  width: 32px; height: 32px; display: grid; place-items: center;
  border: 1px solid var(--border); background: var(--surface);
  border-radius: 8px; cursor: pointer; color: var(--text-muted);
  transition: all 140ms ease;
}
.row-actions button:hover, .role-actions button:hover { background: var(--surface-muted); color: var(--text); border-color: var(--border-strong); }
.row-actions button.danger:hover, .role-actions button.danger:hover { background: var(--danger-soft); color: var(--danger); border-color: #fecaca; }
.row-actions button:disabled, .role-actions button:disabled { opacity: .4; cursor: not-allowed; }

/* Role grid */
.role-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.role-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px 18px; box-shadow: var(--shadow-xs);
  display: flex; flex-direction: column; gap: 10px;
  transition: box-shadow 140ms ease, border-color 140ms ease;
}
.role-card:hover { box-shadow: var(--shadow-sm); border-color: var(--border-strong); }
.role-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.role-card-head h3 { margin: 0; font-size: 15px; color: var(--text); display: flex; align-items: center; gap: 8px; }
.role-desc { margin: 0; font-size: 13px; color: var(--text-muted); line-height: 1.5; min-height: 18px; }
.role-perm-preview { display: flex; gap: 5px; flex-wrap: wrap; min-height: 22px; }
.role-card-foot {
  display: flex; gap: 16px; padding-top: 10px; border-top: 1px solid var(--border);
  font-size: 12px; color: var(--text-soft); font-weight: 600;
}
.role-card-foot span { display: inline-flex; align-items: center; gap: 5px; }

/* Drawer */
.drawer-scrim {
  position: fixed; inset: 0; z-index: 1100;
  background: rgba(15, 23, 42, 0.38);
  display: flex; justify-content: flex-end;
}
.drawer {
  width: 440px; max-width: 92vw; height: 100%;
  background: var(--surface); display: flex; flex-direction: column;
  box-shadow: -20px 0 60px rgba(15, 23, 42, 0.18);
}
.drawer.wide { width: 540px; }
.drawer-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 18px 22px; border-bottom: 1px solid var(--border);
}
.drawer-head h3 { margin: 0; font-size: 16px; }
.icon-x { width: 32px; height: 32px; display: grid; place-items: center; border: 0; background: transparent; border-radius: 8px; cursor: pointer; color: var(--text-muted); }
.icon-x:hover { background: var(--surface-muted); color: var(--text); }
.drawer-body { flex: 1; overflow-y: auto; padding: 22px; display: flex; flex-direction: column; gap: 16px; }
.drawer-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 16px 22px; border-top: 1px solid var(--border); }

.drawer-id { display: flex; align-items: center; gap: 14px; padding-bottom: 4px; }
.drawer-id strong { display: block; font-size: 15px; color: var(--text); }
.drawer-id small { color: var(--text-soft); font-size: 12px; }

/* Fields */
.fld { display: flex; flex-direction: column; gap: 6px; }
.fld > span { font-size: 12px; font-weight: 700; color: var(--text-muted); }
.fld > span em { font-style: normal; font-weight: 500; color: var(--text-soft); }
.fld input {
  width: 100%; padding: 9px 12px; border: 1px solid var(--border-strong);
  border-radius: 9px; font-size: 14px; box-sizing: border-box; color: var(--text);
}
.fld input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }
.fld.disabled { opacity: .5; pointer-events: none; }

/* Switch */
.switch-row {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-muted);
}
.switch-row strong { display: block; font-size: 13px; color: var(--text); }
.switch-row small { color: var(--text-soft); font-size: 11px; }
.switch {
  width: 42px; height: 24px; border-radius: 999px; border: 0; cursor: pointer;
  background: var(--border-strong); position: relative; transition: background 160ms ease; flex-shrink: 0;
}
.switch i { position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%; background: #fff; transition: left 160ms ease; box-shadow: var(--shadow-xs); }
.switch.on { background: var(--primary); }
.switch.on i { left: 21px; }

/* Chip picker (roles on user) */
.chip-pick { display: flex; flex-wrap: wrap; gap: 8px; }
.chip-toggle {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 7px 13px; border-radius: 999px; cursor: pointer; font-size: 13px; font-weight: 600;
  border: 1px solid var(--border-strong); background: var(--surface); color: var(--text-muted);
  transition: all 140ms ease;
}
.chip-toggle:hover { border-color: var(--primary); color: var(--primary-strong); }
.chip-toggle.on { background: var(--primary-soft); border-color: var(--primary); color: var(--primary-strong); }
.chip-toggle:disabled { opacity: .5; cursor: not-allowed; }

/* Permission picker */
.perm-head { display: flex; justify-content: space-between; align-items: center; }
.perm-head > span:first-child { font-size: 13px; font-weight: 800; color: var(--text); }
.perm-count { font-size: 12px; font-weight: 700; color: var(--primary-strong); background: var(--primary-soft); padding: 2px 10px; border-radius: 999px; }
.perm-group { display: flex; flex-direction: column; gap: 8px; }
.perm-group-head { display: flex; justify-content: space-between; align-items: center; }
.perm-group-head strong { font-size: 12px; font-weight: 800; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
.link-btn { border: 0; background: transparent; color: var(--primary); font-size: 12px; font-weight: 700; cursor: pointer; padding: 0; }
.link-btn:hover { text-decoration: underline; }
.perm-items { display: grid; gap: 8px; }
.perm-item {
  display: flex; align-items: flex-start; gap: 11px; text-align: left;
  padding: 11px 13px; border-radius: 10px; cursor: pointer;
  border: 1px solid var(--border); background: var(--surface); transition: all 140ms ease;
}
.perm-item:hover { border-color: var(--primary); background: var(--surface-muted); }
.perm-item.on { border-color: var(--primary); background: var(--primary-soft); }
.perm-check {
  width: 19px; height: 19px; border-radius: 6px; flex-shrink: 0; margin-top: 1px;
  border: 1.5px solid var(--border-strong); background: var(--surface);
  display: grid; place-items: center; color: #fff; transition: all 140ms ease;
}
.perm-item.on .perm-check { background: var(--primary); border-color: var(--primary); }
.perm-text { display: flex; flex-direction: column; gap: 2px; }
.perm-text strong { font-size: 13px; font-weight: 700; color: var(--text); }
.perm-text small { font-size: 11px; color: var(--text-soft); line-height: 1.4; }

/* Transitions */
.fade-enter-active, .fade-leave-active { transition: opacity 200ms ease, transform 200ms ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translate(-50%, -8px); }
.drawer-enter-active, .drawer-leave-active { transition: opacity 220ms ease; }
.drawer-enter-active .drawer, .drawer-leave-active .drawer { transition: transform 240ms cubic-bezier(0.32, 0.72, 0, 1); }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .drawer, .drawer-leave-to .drawer { transform: translateX(100%); }

/* Compliance: suppressions + audit */
.compliance-note {
  display: flex; align-items: flex-start; gap: 10px;
  background: var(--warning-soft); color: var(--warning);
  border: 1px solid #fde9d0; border-radius: 10px; padding: 12px 14px;
  font-size: 13px; line-height: 1.6;
}
.compliance-note strong { font-weight: 700; }
.compliance-note-icon { flex-shrink: 0; margin-top: 1px; }

.suppress-add-card {
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 14px 16px;
}
.suppress-add-card input {
  flex: 1 1 220px; min-width: 180px; padding: 9px 12px; border: 1px solid var(--border-strong);
  border-radius: 9px; font-size: 14px; box-sizing: border-box; color: var(--text);
}
.suppress-add-card input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }
.suppress-add-card select {
  flex: 0 0 auto; padding: 9px 10px; border: 1px solid var(--border-strong); border-radius: 9px;
  font-size: 14px; background: var(--surface); color: var(--text); cursor: pointer;
}
.suppress-add-card .btn-primary { flex: 0 0 auto; white-space: nowrap; }

/* Suppression reason → color coding (keeps 4 reasons visually distinct) */
.suppress-avatar.reason-bounce { background: linear-gradient(135deg, #f87171, #dc2626); }
.suppress-avatar.reason-complaint { background: linear-gradient(135deg, #fb923c, #ea580c); }
.suppress-avatar.reason-unsubscribe,
.suppress-avatar.reason-reply-optout { background: linear-gradient(135deg, #60a5fa, #2563eb); }
.suppress-avatar.reason-manual { background: linear-gradient(135deg, #94a3b8, #64748b); }
.tag-reason-bounce { background: var(--danger-soft); color: var(--danger); }
.tag-reason-complaint { background: var(--warning-soft); color: var(--warning); }
.tag-reason-unsubscribe, .tag-reason-reply-optout { background: var(--primary-soft); color: var(--primary-strong); }
.tag-reason-manual { background: var(--bg-subtle); color: var(--text-muted); }

.empty { padding: 40px; text-align: center; color: var(--text-soft); font-size: 14px; }
.audit-table { width: 100%; border-collapse: collapse; font-size: 13px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.audit-table th { text-align: left; color: var(--text-muted); font-weight: 600; padding: 11px 14px; background: var(--surface-muted); border-bottom: 1px solid var(--border); }
.audit-table td { padding: 10px 14px; border-bottom: 1px solid var(--surface-muted); vertical-align: top; }
.audit-table tr:last-child td { border-bottom: 0; }
.nowrap { white-space: nowrap; }

@media (max-width: 720px) {
  .admin-head { align-items: flex-start; }
  .ucard { flex-wrap: wrap; }
  .role-grid { grid-template-columns: 1fr; }
  .audit-table { font-size: 12px; }
}
</style>
