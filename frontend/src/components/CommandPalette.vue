<script setup lang="ts">
/**
 * CommandPalette — Cmd/Ctrl+K modal-style command picker.
 *
 * Self-contained: renders nothing until the palette is opened. Commands
 * are passed in via the `commands` prop so this component stays
 * decoupled from the app's domain (router, auth, etc.). Selection
 * either runs `command.run()` or routes via the parent's handler.
 *
 * Keyboard:
 *   Cmd/Ctrl+K — toggle (handled by parent listener)
 *   Esc        — close (handled here)
 *   ↑/↓        — move highlight
 *   Enter      — invoke
 */
import { computed, nextTick, ref, watch } from "vue";
import { Search } from "lucide-vue-next";

export interface Command {
  /** Stable unique id, used as :key. */
  id: string;
  /** Visible label. */
  label: string;
  /** Optional secondary line (route, hint, etc). */
  hint?: string;
  /** Group label used as the section header. */
  group: string;
  /** Permission predicate; when false, the command is filtered out. */
  available?: () => boolean;
  /** Invoked when the user selects this command. */
  run: () => void | Promise<void>;
}

const props = defineProps<{
  open: boolean;
  commands: Command[];
}>();
const emit = defineEmits<{ (e: "update:open", value: boolean): void }>();

const query = ref("");
const highlight = ref(0);
const inputEl = ref<HTMLInputElement | null>(null);

const visibleCommands = computed<Command[]>(() => {
  const q = query.value.trim().toLowerCase();
  return props.commands
    .filter((c) => (c.available ? c.available() : true))
    .filter((c) => {
      if (!q) return true;
      // Cheap fuzzy: every search char must appear in order in label or hint.
      const hay = `${c.label} ${c.hint || ""} ${c.group}`.toLowerCase();
      let i = 0;
      for (const ch of q) {
        const at = hay.indexOf(ch, i);
        if (at < 0) return false;
        i = at + 1;
      }
      return true;
    });
});

const groupedCommands = computed<{ group: string; items: Command[] }[]>(() => {
  const groups = new Map<string, Command[]>();
  for (const cmd of visibleCommands.value) {
    const list = groups.get(cmd.group) ?? [];
    list.push(cmd);
    groups.set(cmd.group, list);
  }
  return Array.from(groups, ([group, items]) => ({ group, items }));
});

watch(
  () => props.open,
  async (open) => {
    if (open) {
      query.value = "";
      highlight.value = 0;
      await nextTick();
      inputEl.value?.focus();
    }
  },
);

watch(visibleCommands, () => {
  // Whenever the visible list changes (typing, perms toggle), pin the
  // highlight back to the first row so Enter is always sensible.
  highlight.value = 0;
});

function close(): void {
  emit("update:open", false);
}

function moveHighlight(delta: number): void {
  const len = visibleCommands.value.length;
  if (len === 0) return;
  highlight.value = (highlight.value + delta + len) % len;
}

async function invoke(cmd: Command | undefined): Promise<void> {
  if (!cmd) return;
  close();
  try {
    await cmd.run();
  } catch (err) {
    // The parent's notification system will surface failures; we
    // swallow here so a thrown command can't keep the palette open.
    if (typeof console !== "undefined") {
      console.warn("Command failed:", cmd.id, err);
    }
  }
}

function onInputKeydown(event: KeyboardEvent): void {
  switch (event.key) {
    case "Escape":
      event.preventDefault();
      close();
      return;
    case "ArrowDown":
      event.preventDefault();
      moveHighlight(1);
      return;
    case "ArrowUp":
      event.preventDefault();
      moveHighlight(-1);
      return;
    case "Enter":
      event.preventDefault();
      void invoke(visibleCommands.value[highlight.value]);
      return;
  }
}
</script>

<template>
  <Transition name="cmd-palette">
    <div
      v-if="open"
      class="cmd-palette-backdrop"
      role="presentation"
      @click.self="close"
    >
      <section
        class="cmd-palette"
        role="dialog"
        aria-modal="true"
        aria-label="命令面板"
      >
        <header class="cmd-palette-search">
          <Search :size="16" aria-hidden="true" />
          <input
            ref="inputEl"
            v-model="query"
            class="cmd-palette-input"
            type="text"
            spellcheck="false"
            autocomplete="off"
            placeholder="搜索命令、跳页、操作..."
            aria-label="命令搜索"
            @keydown="onInputKeydown"
          />
          <kbd class="cmd-palette-kbd">Esc</kbd>
        </header>

        <div class="cmd-palette-results" role="listbox" aria-label="可用命令">
          <template v-if="visibleCommands.length === 0">
            <p class="cmd-palette-empty">没有匹配的命令</p>
          </template>
          <template v-else>
            <div
              v-for="group in groupedCommands"
              :key="group.group"
              class="cmd-palette-group"
            >
              <p class="cmd-palette-group-title">{{ group.group }}</p>
              <button
                v-for="cmd in group.items"
                :key="cmd.id"
                type="button"
                role="option"
                :aria-selected="visibleCommands[highlight]?.id === cmd.id"
                :class="[
                  'cmd-palette-item',
                  { active: visibleCommands[highlight]?.id === cmd.id },
                ]"
                @mouseenter="highlight = visibleCommands.indexOf(cmd)"
                @click="invoke(cmd)"
              >
                <span class="cmd-palette-item-label">{{ cmd.label }}</span>
                <span v-if="cmd.hint" class="cmd-palette-item-hint">{{ cmd.hint }}</span>
              </button>
            </div>
          </template>
        </div>
      </section>
    </div>
  </Transition>
</template>

<style scoped>
.cmd-palette-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: clamp(48px, 12vh, 120px);
  z-index: 9000;
}

.cmd-palette {
  width: min(640px, calc(100% - 32px));
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-height: min(72vh, 560px);
}

.cmd-palette-search {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

.cmd-palette-search > svg {
  color: var(--text-soft);
  flex-shrink: 0;
}

.cmd-palette-input {
  flex: 1 1 auto;
  border: 0;
  outline: 0;
  background: transparent;
  font-size: var(--text-md);
  color: var(--text);
}

.cmd-palette-input::placeholder {
  color: var(--text-soft);
}

.cmd-palette-kbd {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: var(--text-xs);
  color: var(--text-muted);
  background: var(--neutral-100);
  border: 1px solid var(--border);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.cmd-palette-results {
  overflow-y: auto;
  padding: 8px 0;
}

.cmd-palette-empty {
  padding: 24px;
  text-align: center;
  color: var(--text-soft);
  font-size: var(--text-sm);
}

.cmd-palette-group {
  padding: 4px 0 8px;
}

.cmd-palette-group-title {
  padding: 4px 18px;
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--text-soft);
  text-transform: uppercase;
}

.cmd-palette-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 10px 18px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font-size: var(--text-md);
  color: var(--text);
  transition: background 120ms ease, color 120ms ease;
}

.cmd-palette-item.active {
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.cmd-palette-item-label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cmd-palette-item-hint {
  font-size: var(--text-sm);
  color: var(--text-soft);
}

.cmd-palette-item.active .cmd-palette-item-hint {
  color: var(--primary);
}

.cmd-palette-enter-active,
.cmd-palette-leave-active {
  transition: opacity 140ms ease;
}

.cmd-palette-enter-active .cmd-palette,
.cmd-palette-leave-active .cmd-palette {
  transition: transform 140ms ease, opacity 140ms ease;
}

.cmd-palette-enter-from,
.cmd-palette-leave-to {
  opacity: 0;
}

.cmd-palette-enter-from .cmd-palette,
.cmd-palette-leave-to .cmd-palette {
  transform: translateY(-8px);
  opacity: 0;
}
</style>
