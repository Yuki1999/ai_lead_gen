<script setup lang="ts">
import { NButton, NInput, NSelect } from "naive-ui";
import { X } from "lucide-vue-next";
import { showUserEditor, editingUser, allRoles, saveUser } from "@/composables/useSettings";
</script>

<template>
    <div v-if="showUserEditor" class="modal-backdrop" role="presentation" @click.self="showUserEditor = false">
      <section class="create-lead-modal" role="dialog" aria-modal="true" aria-label="编辑用户">
        <header class="modal-header">
          <div>
            <p class="panel-label">用户管理</p>
            <h2>{{ editingUser.id ? '编辑用户' : '新建用户' }}</h2>
          </div>
          <button class="icon-only-button" type="button" @click="showUserEditor = false"><X :size="20" /></button>
        </header>
        <div class="create-lead-body">
          <label class="field"><span>用户名</span><n-input v-model:value="editingUser.username" /></label>
          <label class="field"><span>密码{{ editingUser.id ? '（留空则不变）' : '' }}</span><n-input v-model:value="editingUser.password" type="password" show-password-on="click" /></label>
          <label class="field"><span>角色</span>
            <n-select v-model:value="editingUser.role_id" :options="allRoles.map(r => ({ label: r.name, value: r.id }))" />
          </label>
        </div>
        <footer class="create-lead-footer">
          <n-button class="ghost-button" secondary @click="showUserEditor = false">取消</n-button>
          <n-button class="primary-button" type="primary" :disabled="!editingUser.username" @click="saveUser">保存</n-button>
        </footer>
      </section>
    </div>
</template>
