<script setup lang="ts">
import { NButton, NIcon, NInput, NTag } from "naive-ui";
import {
  Bell, BookOpen, Bot, Check, ChevronDown, Clock3, ExternalLink,
  FileText, Maximize2, Pencil, Plus, RefreshCw, Search, Send, SlidersHorizontal,
  Trash2, X,
} from "lucide-vue-next";

import { notice } from "@/composables/useNotifications";
import { hasPermission } from "@/composables/useAuth";
import {
  activePage, agentGuideOpen, agentNotificationsOpen,
  toggleAgentGuide, toggleAgentNotifications,
} from "@/composables/useApp";
import {
  agentPrompt, agentResponse, agentSessionId, agentSessions,
  agentEvents, agentProcessItems, agentLoading, agentError,
  agentConfig, agentProviderName, agentModelName,
  editingSessionId, editingSessionTitle,
  agentConfigExpanded, agentSettingsOpen, agentSkillDetailsOpen,
  agentLogsOpen, agentReportFullscreen, agentSessionSearch,
  agentProcessDisplay, currentAgentProcessItem,
  historicalAgentProcessItems, historicalAgentStatusItems,
  agentHistoryCount, agentMarkdownBlocks, activeAgentSession,
  filteredAgentSessions, agentOutputText, agentLogRows, agentNotificationItems,
  sendAgentPrompt, loadAgentConfig,
  clearAgentOutput, appendAgentProcess,
  getAgentStorage, shortAgentSessionId, formatTime, formatAgentSessionTime,
  startNewAgentSession, switchAgentSession,
  beginEditAgentSession, cancelEditAgentSession, saveAgentSessionTitle,
  removeAgentSession, toggleAgentSettings, toggleAgentSkillDetails,
  toggleAgentLogs, toggleAgentReportFullscreen,
  copyAgentOutput, downloadAgentOutput, copyAgentSessionId,
} from "@/composables/useAgent";
import MarkdownRenderer from "./MarkdownRenderer.vue";
</script>

<template>
  <section
    v-if="activePage === 'agent'"
    class="agent-console"
    aria-label="渠道拓展 Agent"
  >
    <div class="agent-header">
      <div>
        <p class="panel-label">Pi / pi-mono Agent · 默认 Skill: overseas-distributor-prospecting</p>
        <h2>渠道拓展 Agent</h2>
      </div>
      <div class="agent-header-actions">
        <n-button size="small" secondary @click="toggleAgentGuide"><BookOpen :size="14" /> 使用指南</n-button>
        <n-button size="small" secondary @click="toggleAgentNotifications"><Bell :size="14" /></n-button>
        <n-tag :type="agentError ? 'error' : agentLoading ? 'warning' : 'success'" size="small" round :bordered="false">
          {{ agentLoading ? '运行中' : agentError ? '错误' : '在线' }}
        </n-tag>
      </div>
    </div>

    <div class="agent-layout">
      <aside class="agent-sessions" aria-label="Agent 会话列表">
        <div class="agent-sessions-head">
          <strong>会话</strong>
          <n-button size="tiny" secondary @click="startNewAgentSession"><Plus :size="14" /> 新建</n-button>
        </div>
        <div class="agent-session-search">
          <n-input v-model:value="agentSessionSearch" placeholder="搜索会话..." size="small" clearable />
        </div>
        <div class="agent-sessions-list">
          <div
            v-for="session in filteredAgentSessions"
            :key="session.id"
            :class="['agent-session-card', { active: session.id === agentSessionId }]"
            @click="switchAgentSession(session.id)"
          >
            <div v-if="editingSessionId === session.id" class="session-edit-row">
              <n-input
                v-model:value="editingSessionTitle"
                size="tiny"
                @keydown.enter="saveAgentSessionTitle(session.id)"
                @keydown.escape="cancelEditAgentSession"
              />
              <n-button size="tiny" @click="saveAgentSessionTitle(session.id)"><Check :size="14" /></n-button>
              <n-button size="tiny" @click="cancelEditAgentSession"><X :size="14" /></n-button>
            </div>
            <template v-else>
              <div class="session-card-main">
                <strong>{{ session.title }}</strong>
                <small>{{ formatAgentSessionTime(session.updatedAt || session.createdAt) }}</small>
              </div>
              <div class="session-card-actions">
                <n-button size="tiny" @click.stop="beginEditAgentSession(session)"><Pencil :size="12" /></n-button>
                <n-button size="tiny" @click.stop="removeAgentSession(session.id)"><Trash2 :size="12" /></n-button>
              </div>
            </template>
          </div>
          <div v-if="filteredAgentSessions.length === 0" class="history-empty">暂无会话</div>
        </div>
      </aside>

      <div class="agent-conversation">
        <div class="agent-composer">
          <n-input
            v-model:value="agentPrompt"
            type="textarea"
            :rows="3"
            placeholder="描述你要找的渠道类型和目标市场..."
            :disabled="agentLoading"
            @keydown.ctrl.enter="sendAgentPrompt"
          />
          <div class="agent-composer-actions">
            <n-button
              type="primary"
              :loading="agentLoading"
              :disabled="agentLoading || !agentPrompt.trim()"
              @click="sendAgentPrompt"
            >
              <template #icon><n-icon><Send /></n-icon></template>
              {{ agentLoading ? '处理中...' : '发送' }}
            </n-button>
            <n-button
              v-if="agentOutputText"
              secondary
              size="small"
              @click="clearAgentOutput"
            >
              清空
            </n-button>
          </div>
        </div>

        <div class="agent-output">
          <div v-if="!agentOutputText && !agentLoading && agentEvents.length === 0" class="agent-placeholder">
            <Bot :size="48" />
            <p>描述你需要查找的海外代理商，Agent 将实时搜索并入库线索。</p>
          </div>

          <div v-if="agentLoading || currentAgentProcessItem" class="agent-process-bar">
            <div class="agent-process-item" v-if="currentAgentProcessItem">
              <span :class="['process-indicator', currentAgentProcessItem.kind]"></span>
              <span>{{ currentAgentProcessItem.label }}</span>
              <small v-if="currentAgentProcessItem.detail">{{ currentAgentProcessItem.detail }}</small>
            </div>
          </div>

          <div v-if="agentError" class="agent-error-card">
            <p>{{ agentError }}</p>
          </div>

          <div v-if="agentOutputText" class="agent-report">
            <div class="agent-report-toolbar">
              <n-button size="tiny" secondary @click="copyAgentOutput">复制</n-button>
              <n-button size="tiny" secondary @click="downloadAgentOutput">导出</n-button>
              <n-button size="tiny" secondary @click="toggleAgentReportFullscreen">全屏</n-button>
            </div>
            <MarkdownRenderer :blocks="agentMarkdownBlocks" />
          </div>
        </div>
      </div>

      <aside class="agent-context" aria-label="Agent 上下文">
        <div class="context-section">
          <button class="context-toggle" @click="toggleAgentSettings">
            <SlidersHorizontal :size="14" /> 配置
            <ChevronDown :size="14" :class="{ rotated: agentSettingsOpen }" />
          </button>
          <div v-if="agentSettingsOpen" class="context-body">
            <div class="agent-config-mini">
              <label class="field"><span>Provider</span>
                <n-input v-model:value="agentProviderName" size="small" placeholder="deepseek" />
              </label>
              <label class="field"><span>模型</span>
                <n-input v-model:value="agentModelName" size="small" placeholder="deepseek-v4-pro" />
              </label>
            </div>
          </div>
        </div>

        <div class="context-section">
          <button class="context-toggle" @click.prevent="toggleAgentSkillDetails">
            <BookOpen :size="14" /> Skill
            <ChevronDown :size="14" :class="{ rotated: agentSkillDetailsOpen }" />
          </button>
          <div v-if="agentSkillDetailsOpen" class="context-body">
            <p class="context-text">overseas-distributor-prospecting — 海外渠道拓展工作流</p>
            <p class="context-text">默认使用联网搜索 + 官网邮箱抽取 + 线索入库</p>
          </div>
        </div>

        <div class="context-section">
          <button class="context-toggle" @click="toggleAgentLogs">
            <FileText :size="14" /> 执行日志 ({{ agentLogRows.length }})
            <ChevronDown :size="14" :class="{ rotated: agentLogsOpen }" />
          </button>
          <div v-if="agentLogsOpen" class="context-body">
            <div v-if="agentLogRows.length === 0" class="history-empty">暂无日志</div>
            <div v-for="(row, idx) in agentLogRows" :key="idx" class="log-row">
              <span :class="['log-kind', row.kind]">{{ row.kind === 'process' ? '⚙' : '📌' }}</span>
              <span>{{ row.label }}</span>
              <small v-if="row.time">{{ row.time }}</small>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>
