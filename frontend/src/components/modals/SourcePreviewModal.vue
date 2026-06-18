<script setup lang="ts">
import { NButton, NEmpty, NTag } from "naive-ui";
import { ExternalLink, FileText, Globe2, Maximize2, X } from "lucide-vue-next";
import { sourcePreviewLead, sourcePreview, sourcePreviewLoading, sourcePreviewError, sourcePreviewMode, closeSourcePreview, highlightedSourceText, highlightedEvidenceExcerpt, sourceHost } from "@/composables/useLeads";
</script>

<template>
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
          <h2 id="source-modal-title">{{ sourcePreviewLead?.company_name }}</h2>
        </div>
        <button class="icon-only-button" type="button" aria-label="关闭来源预览" @click="closeSourcePreview">
          <X :size="20" aria-hidden="true" />
        </button>
      </header>

      <div class="source-summary">
        <div>
          <span class="summary-label">原文地址</span>
          <a :href="sourcePreviewLead?.source" target="_blank" rel="noreferrer">
            <ExternalLink :size="16" aria-hidden="true" />
            {{ sourcePreviewLead?.source }}
          </a>
        </div>
        <div>
          <span class="summary-label">联系人邮箱</span>
          <strong>{{ sourcePreviewLead?.email }}</strong>
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
</template>
