<script setup lang="ts">
import type { InlineToken } from "../markdown";

defineProps<{
  tokens: InlineToken[];
}>();
</script>

<template>
  <template v-for="(token, index) in tokens" :key="index">
    <strong v-if="token.type === 'strong'">{{ token.text }}</strong>
    <code v-else-if="token.type === 'code'">{{ token.text }}</code>
    <a
      v-else-if="token.type === 'link'"
      :href="token.href"
      target="_blank"
      rel="noreferrer"
    >
      {{ token.text }}
    </a>
    <template v-else>{{ token.text }}</template>
  </template>
</template>
