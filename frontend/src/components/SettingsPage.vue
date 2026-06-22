<script setup lang="ts">
import {
  NAlert, NButton, NCheckbox, NIcon, NInput, NInputNumber, NSelect, NTag,
} from "naive-ui";
import { Edit3, Save, Trash2 } from "lucide-vue-next";

import { notice, error } from "@/composables/useNotifications";
import { hasPermission } from "@/composables/useAuth";
import {
  activePage, providerOptions,
} from "@/composables/useApp";
import {
  settings, settingsAgentKeyInput, settingsEmailPasswordInput,
  settingsEmailTemplate, settingsScoringRules,
  settingsLoading, settingsSaving, settingsTab,
  ALL_PERMISSIONS, permLabels, allRoles, allUsers,
  showRoleEditor, showUserEditor, editingRole, editingUser,
  openNewRole, openEditRole, saveRole, deleteRole,
  openNewUser, openEditUser, saveUser, deleteUser,
  saveSettings,
} from "@/composables/useSettings";
import {
  agentProviderName, agentModelName, agentApiBaseUrl, agentBackendBaseUrl,
  agentConfigTesting, agentTestResult, agentConfigError, agentConfigNotice,
  agentApiKeyInput, testAgentConnection,
} from "@/composables/useAgent";
</script>

<template>
  <section
    v-if="activePage === 'settings'"
    class="settings-page"
    aria-labelledby="settings-title"
  >
    <div class="settings-tabs">
      <button :class="['settings-tab', { active: settingsTab === 'email' }]" @click="settingsTab = 'email'">邮箱</button>
      <button :class="['settings-tab', { active: settingsTab === 'sync' }]" @click="settingsTab = 'sync'">同步</button>
      <button :class="['settings-tab', { active: settingsTab === 'agent' }]" @click="settingsTab = 'agent'">Agent</button>
      <button :class="['settings-tab', { active: settingsTab === 'template' }]" @click="settingsTab = 'template'">模板</button>
      <button :class="['settings-tab', { active: settingsTab === 'scoring' }]" @click="settingsTab = 'scoring'">评分</button>
      <button v-if="hasPermission('users:manage')" :class="['settings-tab', { active: settingsTab === 'access' }]" @click="settingsTab = 'access'">权限</button>
    </div>

    <section v-if="settingsTab === 'template'" class="settings-card">
      <p class="panel-label">邮件模板</p>
      <n-input type="textarea" :rows="12" v-model:value="settingsEmailTemplate" placeholder="输入邮件模板，支持 [Name]、[Role]、[Target Market]、[Company] 等占位符" />
    </section>

    <section v-if="settingsTab === 'scoring'" class="settings-card">
      <p class="panel-label">评分规则</p>
      <n-input type="textarea" :rows="12" v-model:value="settingsScoringRules" placeholder="输入评分规则文本，使用 Markdown 格式" />
    </section>

    <section v-if="settingsTab === 'access'" class="settings-card">
      <p class="panel-label">角色管理</p>
      <div class="role-grid">
        <div v-for="role in allRoles" :key="role.id" class="role-card">
          <div class="role-info">
            <strong>{{ role.name }}</strong>
            <span class="role-meta">{{ role.user_count }} 位用户</span>
          </div>
          <div class="role-actions">
            <n-button size="tiny" secondary @click="openEditRole(role)"><Edit3 :size="14" /></n-button>
            <n-button v-if="role.name !== 'admin'" size="tiny" secondary @click="deleteRole(role.id)"><Trash2 :size="14" /></n-button>
          </div>
        </div>
      </div>
      <n-button size="small" secondary @click="openNewRole">新增角色</n-button>

      <hr class="settings-sep" />
      <p class="panel-label">用户管理</p>
      <div class="user-grid">
        <div v-for="user in allUsers" :key="user.id" class="user-card">
          <div><strong>{{ user.username }}</strong> <span class="role-meta">{{ user.role_name }}</span></div>
          <div class="role-actions">
            <n-button size="tiny" secondary @click="openEditUser(user)"><Edit3 :size="14" /></n-button>
            <n-button v-if="user.username !== 'microport_admin'" size="tiny" secondary @click="deleteUser(user.id)"><Trash2 :size="14" /></n-button>
          </div>
        </div>
      </div>
      <n-button size="small" secondary @click="openNewUser">新增用户</n-button>
    </section>

    <section v-if="settingsTab === 'email'" class="settings-card">
      <p class="panel-label">Exchange EWS 连接</p>
      <div class="settings-grid">
        <label class="field"><span>服务器</span><n-input v-model:value="settings.email_server" /></label>
        <label class="field"><span>用户名</span><n-input v-model:value="settings.email_user" /></label>
        <label class="field"><span>密码</span><n-input v-model:value="settingsEmailPasswordInput" type="password" placeholder="留空不修改" /></label>
      </div>
    </section>

    <section v-if="settingsTab === 'sync'" class="settings-card">
      <p class="panel-label">自动同步</p>
      <div class="sync-status-row">
        <span>当前状态</span>
        <n-tag :type="settings.sync_enabled ? 'success' : 'default'" size="small" round :bordered="false">
          {{ settings.sync_enabled ? '已开启' : '已关闭' }}
        </n-tag>
      </div>
      <label class="toggle-field"><n-checkbox v-model:checked="settings.sync_enabled">启用自动同步</n-checkbox></label>
      <label class="field" v-if="settings.sync_enabled"><span>同步间隔（分钟）</span><n-input-number v-model:value="settings.sync_interval_minutes" :min="5" :max="1440" /></label>
      <p class="setting-hint" v-if="settings.sync_enabled && settings.sync_interval_minutes > 0">每 {{ settings.sync_interval_minutes }} 分钟自动扫描收件箱，仅同步新回复。</p>
    </section>

    <section v-if="settingsTab === 'agent'" class="settings-card">
      <p class="panel-label">Agent 模型与 API</p>
      <div class="settings-grid">
        <label class="field"><span>Provider</span><n-select v-model:value="agentProviderName" :options="providerOptions" /></label>
        <label class="field"><span>模型</span><n-input v-model:value="agentModelName" placeholder="deepseek-v4-pro" /></label>
        <label class="field"><span>API Key</span><n-input v-model:value="agentApiKeyInput" type="password" placeholder="留空不修改" /></label>
        <label class="field"><span>API Base URL</span><n-input v-model:value="agentApiBaseUrl" placeholder="留空使用默认: https://api.deepseek.com" /></label>
        <label class="field"><span>Backend Base URL</span><n-input v-model:value="agentBackendBaseUrl" placeholder="http://localhost:8000" /></label>
      </div>
      <div class="settings-actions-row">
        <n-button secondary size="small" :loading="agentConfigTesting" @click="testAgentConnection">测试连接</n-button>
      </div>
      <div v-if="agentTestResult" class="agent-test-result">
        <p :class="agentTestResult.ok ? 'notice' : 'login-error'">
          {{ agentTestResult.ok ? '✓' : '✗' }} {{ agentTestResult.message }}
          <span v-if="agentTestResult.latency_ms">({{ agentTestResult.latency_ms }}ms)</span>
        </p>
        <p v-if="agentTestResult.error" class="login-error">{{ agentTestResult.error }}</p>
      </div>
      <p v-if="agentConfigError" class="login-error">{{ agentConfigError }}</p>
      <p v-if="agentConfigNotice" class="notice">{{ agentConfigNotice }}</p>
    </section>

    <div class="settings-actions">
      <n-button
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
</template>
