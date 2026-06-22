<script setup lang="ts">
/**
 * Mounted once inside the Naive provider tree. Grabs the live message,
 * dialog and notification APIs and registers them with `useNotifications`
 * so module-level helpers (`setNotice`, `notify`, `confirmDanger`, etc.)
 * can reach into them without each consumer needing component-level
 * access. Renders nothing.
 */
import { useDialog, useMessage, useNotification } from "naive-ui";
import { registerNotificationApis } from "@/composables/useNotifications";

const message = useMessage();
const dialog = useDialog();
const notification = useNotification();

registerNotificationApis({ message, dialog, notification });
</script>

<template><span class="naive-api-bridge" aria-hidden="true" /></template>

<style scoped>
.naive-api-bridge {
  display: none;
}
</style>
