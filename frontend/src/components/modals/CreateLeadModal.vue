<script setup lang="ts">
import { NButton, NIcon, NInput } from "naive-ui";
import { Plus, X } from "lucide-vue-next";
import { showCreateLead, createError, newLead } from "@/composables/useSettings";
import { createLead } from "@/composables/useLeads";
import { currentAction } from "@/composables/useActionState";
</script>

<template>
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
</template>
