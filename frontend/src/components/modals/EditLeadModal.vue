<script setup lang="ts">
import { NButton, NIcon, NInput, NInputNumber, NSelect } from "naive-ui";
import { Save, X } from "lucide-vue-next";
import { showEditLead, editLead, editLeadSaving, saveEditLead } from "@/composables/useLeads";
import { statusFilterOptions } from "@/composables/useApp";
</script>

<template>
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
          <label class="field"><span>状态</span><n-input v-model:value="editLead.status" /></label>
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
</template>
