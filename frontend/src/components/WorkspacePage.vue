<script setup lang="ts">
import {
  NAlert, NButton, NCard, NCheckbox, NEmpty, NIcon, NInput, NSelect, NTag,
} from "naive-ui";
import {
  AlertTriangle, Check, ChevronDown, Clock3, Database, Edit3, ExternalLink,
  FileText, Globe2, MailCheck, Maximize2, Plus, RefreshCw, Search, Send,
  Trash2, X, Zap,
} from "lucide-vue-next";

import { notice, error } from "@/composables/useNotifications";
import { loading, currentAction } from "@/composables/useActionState";
import { hasPermission } from "@/composables/useAuth";
import {
  activePage, statusFilterOptions, agentGuideOpen,
  toggleAgentGuide, toggleAgentNotifications,
} from "@/composables/useApp";
import {
  leads, metrics,
  selectedLeadIds, filterRegion, filterStatus, query, sortField, sortDir,
  replyText, lastEmail, analysis, sourcePreview, sourcePreviewLead,
  sourcePreviewLoading, sourcePreviewError, sourcePreviewMode,
  leadPage, leadPageSize, leadTotal,
  showCustomEmail, customEmail, customEmailSending,
  availableAttachments, customEmailAttachments,
  showEditLead, editLead, editLeadSaving,
  detailLeadId, detailStatus, detailNotes, detailOutreach, detailReplies,
  detailLoading, showOutreachPreview, outreachLoading, outreachPreviews,
  showReplyAnalyzer,
  selectedCount, detailLead, timelineEvents,
  highlightedSourceText, highlightedEvidenceExcerpt, sourceHost,
  formatStatus, statusClass, statusTagType,
  loadDashboard, loadDrafts, approveDraft, rejectDraft,
  openCreateLead, createLead, batchDeleteLeads, deleteLead,
  approveAllDrafts, loadProductProfile, generateLeads,
  createOutreachRecords, syncReplies, analyzeCurrentReply,
  generateFollowupAndOpen, sendOutreachSingle, sendOutreachBatch,
  fetchOutreachPreview, confirmSendOutreach, openCustomEmail, sendCustomEmail,
  openReplyAnalyzer, reactivateLead, markQualified,
  openLeadDetail, closeLeadDetail, saveLeadDetail,
  openEditLead, saveEditLead, openSourcePreview, closeSourcePreview,
  toggleLead, toggleSelectAll, toggleSort, onLeadPageChange, setLeadSelection,
} from "@/composables/useLeads";
import {
  showCreateLead, createError, newLead,
} from "@/composables/useSettings";
import {
  drafts, draftCount,
  showRoleEditor, showUserEditor, editingRole, editingUser,
  openNewRole, openEditRole, saveRole, deleteRole,
  openNewUser, openEditUser, saveUser, deleteUser,
} from "@/composables/useSettings";
import { ALL_PERMISSIONS, permLabels, allRoles, allUsers } from "@/composables/useSettings";
</script>

<template>
  <template v-if="activePage === 'workspace'">
    <section
      v-if="draftCount > 0"
      class="draft-queue"
      aria-label="待审核外联"
    >
      <div class="draft-queue-head">
        <div class="draft-queue-title">
          <strong>{{ draftCount }} 条待审批</strong>
          <span class="draft-queue-desc">Agent 生成的邮件在此统一审核，批准后真实发送，拒绝则废弃</span>
        </div>
        <n-button class="draft-approve-all" size="small" type="primary" @click="approveAllDrafts">
          全部批准发送
        </n-button>
      </div>
      <div class="draft-list">
        <div v-for="draft in drafts" :key="draft.id" class="draft-card">
          <div class="draft-card-head">
            <strong>{{ draft.company_name }}</strong>
            <small>{{ draft.sent_to }}</small>
          </div>
          <p class="draft-subject">{{ draft.subject }}</p>
          <div class="draft-card-actions">
            <n-button size="tiny" type="primary" @click="approveDraft(draft.id)"><Check :size="14" /> 批准</n-button>
            <n-button size="tiny" secondary @click="rejectDraft(draft.id)"><X :size="14" /> 拒绝</n-button>
          </div>
        </div>
      </div>
    </section>

    <div class="toolbar" aria-label="筛选线索">
      <div class="toolbar-left">
        <n-input v-model:value="query" placeholder="搜索公司、邮箱、国家..." size="small" clearable @keydown.enter="loadDashboard()">
          <template #prefix><n-icon><Search /></n-icon></template>
        </n-input>
        <n-select v-model:value="filterStatus" :options="statusFilterOptions" size="small" placeholder="全部状态" clearable @update:value="loadDashboard()" />
        <n-input v-model:value="filterRegion" placeholder="地区筛选" size="small" clearable @keydown.enter="loadDashboard()" />
      </div>
      <div class="toolbar-right">
        <n-button size="small" secondary @click="loadDashboard()"><RefreshCw :size="14" /></n-button>
        <n-button v-if="hasPermission('leads:write')" size="small" secondary @click="openCreateLead()"><Plus :size="14" /> 添加</n-button>
        <n-button v-if="hasPermission('outreach:send') && selectedLeadIds.length > 0" size="small" type="primary" @click="sendOutreachBatch()"><Send :size="14" /> 外联 ({{ selectedCount }})</n-button>
        <n-button v-if="hasPermission('replies:sync')" size="small" secondary @click="syncReplies()"><MailCheck :size="14" /> 同步</n-button>
      </div>
    </div>

    <div class="modern-data-table" aria-label="线索列表">
      <div class="table-header">
        <div class="table-cell checkbox-col"><n-checkbox :checked="selectedLeadIds.length === leads.length && leads.length > 0" @update:checked="toggleSelectAll" /></div>
        <div class="table-cell company-col" @click="toggleSort('company_name')">公司 <span v-if="sortField === 'company_name'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
        <div class="table-cell region-col" @click="toggleSort('country')">国家 <span v-if="sortField === 'country'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
        <div class="table-cell category-col" @click="toggleSort('category')">类别 <span v-if="sortField === 'category'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
        <div class="table-cell email-col" @click="toggleSort('email')">邮箱 <span v-if="sortField === 'email'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
        <div class="table-cell source-col" @click="toggleSort('source')">来源 <span v-if="sortField === 'source'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
        <div class="table-cell score-col" @click="toggleSort('score')">评分 <span v-if="sortField === 'score'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
        <div class="table-cell status-col" @click="toggleSort('status')">状态 <span v-if="sortField === 'status'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
        <div class="table-cell actions-col">操作</div>
      </div>

      <div v-if="leads.length === 0" class="table-empty">
        <n-empty description="暂无线索，使用 Agent 搜索或手动添加" />
      </div>

      <div v-for="lead in leads" :key="lead.id" class="table-row" :class="statusClass(lead.status)">
        <div class="table-cell checkbox-col"><n-checkbox :checked="selectedLeadIds.includes(lead.id)" @update:checked="setLeadSelection(lead.id, $event)" /></div>
        <div class="table-cell company-col">
          <strong>{{ lead.company_name }}</strong>
          <small v-if="lead.reply_count">{{ lead.reply_count }} 回复</small>
        </div>
        <div class="table-cell region-col">{{ lead.country }}</div>
        <div class="table-cell category-col">{{ lead.category }}</div>
        <div class="table-cell email-col"><a :href="'mailto:' + lead.email">{{ lead.email }}</a></div>
        <div class="table-cell source-col">
          <button class="source-link" @click="openSourcePreview(lead)"><ExternalLink :size="12" /> {{ sourceHost || '查看' }}</button>
        </div>
        <div class="table-cell score-col"><span class="score-badge">{{ lead.score }}</span></div>
        <div class="table-cell status-col"><n-tag :type="statusTagType(lead.status)" size="small">{{ formatStatus(lead.status) }}</n-tag></div>
        <div class="table-cell actions-col">
          <button class="lead-action-btn" @click="openLeadDetail(lead.id)"><FileText :size="13" />详情</button>
          <button v-if="hasPermission('outreach:send') && lead.status === 'new' && !(lead.draft_count && lead.draft_count > 0)" class="lead-action-btn" @click="sendOutreachSingle(lead.id)"><Send :size="13" />外联</button>
          <button v-if="hasPermission('leads:write')" class="lead-action-btn" @click="openEditLead(lead.id)"><Edit3 :size="13" />编辑</button>
          <button v-if="hasPermission('leads:write')" class="lead-action-btn danger-action" @click="deleteLead(lead.id)"><Trash2 :size="13" />删除</button>
        </div>
      </div>

      <div class="table-footer">
        <span>共 {{ leadTotal }} 条，第 {{ leadPage }} / {{ Math.ceil(leadTotal / leadPageSize) || 1 }} 页</span>
        <div class="pagination">
          <n-button size="tiny" :disabled="leadPage <= 1" @click="onLeadPageChange(leadPage - 1)">上一页</n-button>
          <n-button size="tiny" :disabled="leadPage * leadPageSize >= leadTotal" @click="onLeadPageChange(leadPage + 1)">下一页</n-button>
        </div>
      </div>
    </div>

    <!-- Lead Detail Modal -->
    <div v-if="detailLeadId !== null" class="modal-backdrop" @click.self="closeLeadDetail()">
      <section class="lead-detail-modal" role="dialog" aria-modal="true">
        <header class="modal-header">
          <div>
            <p class="panel-label">线索详情</p>
            <h2>{{ detailLead?.company_name || '加载中...' }}</h2>
          </div>
          <button class="icon-only-button" @click="closeLeadDetail()"><X :size="20" /></button>
        </header>
        <div v-if="detailLoading" class="detail-loading">加载中...</div>
        <template v-else-if="detailLead">
          <div class="detail-summary">
            <div><strong>国家:</strong> {{ detailLead.country }}</div>
            <div><strong>邮箱:</strong> <a :href="'mailto:' + detailLead.email">{{ detailLead.email }}</a></div>
            <div><strong>评分:</strong> {{ detailLead.score }}</div>
            <div><strong>来源:</strong> <button class="source-link" @click="openSourcePreview(detailLead)">{{ detailLead.source }}</button></div>
          </div>
          <div class="detail-form">
            <label class="field"><span>状态</span>
              <n-select v-model:value="detailStatus" :options="statusFilterOptions.filter(o => o.value !== '')" size="small" />
            </label>
            <label class="field"><span>备注</span>
              <n-input v-model:value="detailNotes" type="textarea" :rows="2" size="small" />
            </label>
          </div>
          <div class="detail-actions">
            <n-button size="small" type="primary" @click="saveLeadDetail()">保存</n-button>
            <n-button size="small" secondary @click="reactivateLead(detailLead.id)">重新激活</n-button>
            <n-button size="small" secondary @click="markQualified(detailLead.id)">确认合格</n-button>
            <n-button class="ghost-button danger-action" secondary @click="detailLeadId !== null && deleteLead(detailLeadId)">
              <Trash2 :size="14" />删除
            </n-button>
          </div>

          <div class="communication-timeline">
            <h3>沟通时间线</h3>
            <div v-if="timelineEvents.length === 0" class="history-empty">暂无沟通记录</div>
            <div v-for="event in timelineEvents" :key="event.kind + '-' + event.id" class="timeline-event">
              <span :class="['timeline-dot', event.kind]"></span>
              <div>
                <small>{{ event.created_at }}</small>
                <p v-if="event.kind === 'outreach'"><strong>外发:</strong> {{ event.subject }}</p>
                <p v-else><strong>回复 ({{ event.intent }}):</strong> {{ event.subject }}</p>
              </div>
            </div>
          </div>

          <div class="reply-analyzer-section">
            <h3>回复分析</h3>
            <n-input v-model:value="replyText" type="textarea" :rows="3" placeholder="粘贴代理商的回复邮件..." />
            <div class="reply-actions">
              <n-button size="small" type="primary" :loading="currentAction === 'reply'" @click="analyzeCurrentReply()">分析回复</n-button>
              <n-button size="small" secondary @click="generateFollowupAndOpen()">生成跟进邮件</n-button>
              <n-button class="ghost-button" secondary @click="showReplyAnalyzer = !showReplyAnalyzer">
                {{ showReplyAnalyzer ? '收起' : '展开' }}分析
              </n-button>
            </div>
            <div v-if="showReplyAnalyzer && analysis" class="analysis-result">
              <n-tag :type="analysis.intent === 'interested' ? 'success' : analysis.intent === 'rejected' ? 'error' : 'warning'" size="small">
                意图: {{ analysis.intent }}
              </n-tag>
              <p>{{ analysis.summary }}</p>
              <p><strong>建议:</strong> {{ analysis.next_action }}</p>
              <p v-if="analysis.requires_human" class="human-flag">⚠ 需要人工处理</p>
            </div>
          </div>
        </template>
      </section>
    </div>

    <div v-if="notice || error" class="feedback-alerts">
      <n-alert v-if="notice" type="success" closable @close="notice = ''">{{ notice }}</n-alert>
      <n-alert v-if="error" type="error" closable @close="error = ''">{{ error }}</n-alert>
    </div>
  </template>
</template>
