<script setup lang="ts">
import { NButton, NCheckbox, NIcon, NInput } from "naive-ui";
import { Send, X } from "lucide-vue-next";
import { showCustomEmail, customEmail, customEmailSending, availableAttachments, customEmailAttachments, sendCustomEmail } from "@/composables/useLeads";
</script>

<template>
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
</template>
