<script setup lang="ts">
import { NButton, NCheckbox, NInput } from "naive-ui";
import { X } from "lucide-vue-next";
import { showRoleEditor, editingRole, ALL_PERMISSIONS, permLabels, saveRole } from "@/composables/useSettings";
</script>

<template>
    <div v-if="showRoleEditor" class="modal-backdrop" role="presentation" @click.self="showRoleEditor = false">
      <section class="create-lead-modal" role="dialog" aria-modal="true" aria-label="编辑角色">
        <header class="modal-header">
          <div>
            <p class="panel-label">权限管理</p>
            <h2>{{ editingRole.id ? '编辑角色' : '新建角色' }}</h2>
          </div>
          <button class="icon-only-button" type="button" @click="showRoleEditor = false"><X :size="20" /></button>
        </header>
        <div class="create-lead-body">
          <label class="field"><span>角色名称</span><n-input v-model:value="editingRole.name" placeholder="如 operator, viewer" /></label>
          <p class="panel-label" style="margin-top:12px">权限</p>
          <div style="display:flex;flex-wrap:wrap;gap:6px">
            <label v-for="p in ALL_PERMISSIONS" :key="p" class="attachment-check">
              <n-checkbox :checked="editingRole.permissions.includes(p)" @update:checked="(c: boolean) => { if (c) editingRole.permissions.push(p); else editingRole.permissions = editingRole.permissions.filter(x => x !== p); }" />
              <span>{{ permLabels[p] || p }}</span>
            </label>
          </div>
        </div>
        <footer class="create-lead-footer">
          <n-button class="ghost-button" secondary @click="showRoleEditor = false">取消</n-button>
          <n-button class="primary-button" type="primary" :disabled="!editingRole.name" @click="saveRole">保存</n-button>
        </footer>
      </section>
    </div>
</template>

