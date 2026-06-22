<script setup lang="ts">
import { NButton, NInput } from "naive-ui";
import {
  isAuthenticated,
  loginUsername,
  loginPassword,
  loginLoading,
  loginError,
  login as doLogin,
  onLoginKeydown,
} from "@/composables/useAuth";
import { loadDashboard, loadProductProfile } from "@/composables/useLeads";
import { loadAgentConfig } from "@/composables/useAgent";

async function handleLogin(): Promise<void> {
  await doLogin(async () => {
    await Promise.all([loadProductProfile(), loadDashboard()]);
    void loadAgentConfig();
  });
}
</script>

<template>
  <div v-if="!isAuthenticated" class="login-overlay" aria-label="登录">
    <div class="login-card">
      <div class="login-brand">
        <div class="brand-mark">SW</div>
        <div>
          <strong>SkyWalker</strong>
          <span>Overseas Prospecting</span>
        </div>
      </div>
      <h2>系统登录</h2>
      <p class="login-desc">请输入管理员账号和密码</p>
      <label class="field">
        <span>用户名</span>
        <n-input
          v-model:value="loginUsername"
          placeholder="用户名"
          autocomplete="username"
          :disabled="loginLoading"
          @keydown="onLoginKeydown"
        />
      </label>
      <label class="field">
        <span>密码</span>
        <n-input
          v-model:value="loginPassword"
          type="password"
          placeholder="密码"
          autocomplete="current-password"
          show-password-on="click"
          :disabled="loginLoading"
          @keydown="onLoginKeydown"
        />
      </label>
      <p v-if="loginError" class="login-error">{{ loginError }}</p>
      <n-button
        class="primary-button"
        type="primary"
        size="large"
        block
        :loading="loginLoading"
        :disabled="loginLoading"
        @click="handleLogin"
      >
        {{ loginLoading ? "登录中..." : "登录" }}
      </n-button>
    </div>
  </div>
</template>
