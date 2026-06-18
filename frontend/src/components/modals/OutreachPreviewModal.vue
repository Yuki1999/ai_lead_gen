<script setup lang="ts">
import { NButton, NIcon, NInput } from "naive-ui";
import { Send, X } from "lucide-vue-next";
import {
  showOutreachPreview,
  outreachPreviews,
  outreachLoading,
  confirmSendOutreach,
} from "@/composables/useLeads";
</script>

<template>
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
          <h2>外联预览</h2>
        </div>
        <button
          class="icon-only-button"
          type="button"
          aria-label="关闭"
          @click="showOutreachPreview = false"
        >
          <X :size="20" aria-hidden="true" />
        </button>
      </header>
      <!--
        `create-lead-body` is the canonical scroll body for `create-lead-modal`
        (`overflow-y: auto`). Without it, multiple preview cards stack outside
        the modal's viewport-bounded grid and overflow the page.
      -->
      <div class="create-lead-body">
        <article
          v-for="preview in outreachPreviews"
          :key="preview.lead_id"
          class="outreach-preview-card"
        >
          <p>
            <strong>{{ preview.company_name }}</strong>
            <span class="muted-meta"> · {{ preview.email }}</span>
          </p>
          <label class="field">
            <span>主题</span>
            <n-input v-model:value="preview.subject" size="small" />
          </label>
          <label class="field">
            <span>正文</span>
            <n-input
              v-model:value="preview.body"
              type="textarea"
              :rows="6"
              size="small"
            />
          </label>
        </article>
      </div>
      <footer class="create-lead-footer">
        <n-button secondary @click="showOutreachPreview = false">取消</n-button>
        <n-button
          type="primary"
          :loading="outreachLoading"
          @click="confirmSendOutreach"
        >
          <template #icon>
            <n-icon><Send /></n-icon>
          </template>
          确认发送
        </n-button>
      </footer>
    </section>
  </div>
</template>
