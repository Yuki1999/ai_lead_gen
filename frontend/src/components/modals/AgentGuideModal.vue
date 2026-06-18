<script setup lang="ts">
import { X } from "lucide-vue-next";
import { agentGuideOpen } from "@/composables/useApp";
</script>

<template>
  <div
    v-if="agentGuideOpen"
    class="modal-backdrop"
    role="presentation"
    @click.self="agentGuideOpen = false"
  >
    <section class="guide-modal" role="dialog" aria-modal="true" aria-label="使用指南">
      <header class="modal-header">
        <div>
          <p class="panel-label">使用指南</p>
          <h2>渠道拓展 Agent 工作流</h2>
        </div>
        <button class="icon-only-button" type="button" aria-label="关闭" @click="agentGuideOpen = false">
          <X :size="20" aria-hidden="true" />
        </button>
      </header>
      <div class="guide-body">
        <div class="guide-section">
          <h3>Step 1 — 建立线索库</h3>
          <p>在任务框描述目标：产品、国家、渠道类型。Agent 会自动扩展搜索词、调用搜索引擎、提取公开邮箱，并去重入库。</p>
          <p>示例：<code>帮我在德国和新加坡找骨科植入物经销商，要求有公开邮箱和官网证据</code></p>
        </div>
        <div class="guide-section">
          <h3>Step 2 — 发送外联</h3>
          <p>Agent 生成的邮件会进入<strong>线索管理 → 待审核队列</strong>，需人工预览和批准后才会真实发送。</p>
          <p>也可手动勾选线索，点击「发送外联」预览 AI 生成的邮件模板，编辑后确认发送。</p>
        </div>
        <div class="guide-section">
          <h3>Step 3 — 分析回复</h3>
          <p>点击「同步回复」从收件箱拉取真实回复，AI 自动分析意图（感兴趣 / 拒绝 / 复杂 / 待审核）。</p>
          <p>点击线索行查看完整沟通历史、回复原文和分析结果，可在详情中修改状态和备注。</p>
        </div>
        <div class="guide-section">
          <h3>设置</h3>
          <p>在「设置」页面配置邮箱连接、自动同步频率和 AI 模型参数。启用自动同步后，系统定期扫描收件箱。</p>
        </div>
      </div>
    </section>
  </div>
</template>
