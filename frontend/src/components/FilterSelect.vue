<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from "vue";
import { Check, ChevronDown, Search, X } from "lucide-vue-next";

interface Option {
  value: string;
  label: string;
  count?: number;
}

const props = withDefaults(
  defineProps<{
    modelValue: string;
    options: Option[];
    placeholder: string;
    searchable?: boolean;
    searchPlaceholder?: string;
    icon?: Component;
    align?: "left" | "right";
  }>(),
  { searchable: false, searchPlaceholder: "搜索…", align: "left" },
);

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "change", value: string): void;
}>();

const open = ref(false);
const search = ref("");
const rootRef = ref<HTMLElement | null>(null);
const searchRef = ref<HTMLInputElement | null>(null);

const selectedLabel = computed(() => {
  if (!props.modelValue) return props.placeholder;
  return props.options.find((o) => o.value === props.modelValue)?.label || props.modelValue;
});
const hasSelection = computed(() => props.modelValue !== "");

const filteredOptions = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return props.options;
  return props.options.filter((o) => o.label.toLowerCase().includes(q));
});

function toggle(): void {
  open.value = !open.value;
  if (open.value && props.searchable) {
    requestAnimationFrame(() => searchRef.value?.focus());
  }
}
function close(): void {
  open.value = false;
  search.value = "";
}
function pick(value: string): void {
  close();
  if (value === props.modelValue) return;
  emit("update:modelValue", value);
  emit("change", value);
}

function onOutside(event: MouseEvent): void {
  if (!open.value) return;
  const target = event.target as Node | null;
  if (target && rootRef.value && !rootRef.value.contains(target)) close();
}
function onKeydown(event: KeyboardEvent): void {
  if (open.value && event.key === "Escape") {
    event.stopPropagation();
    close();
  }
}

watch(
  () => props.modelValue,
  () => {
    if (open.value) close();
  },
);

onMounted(() => {
  document.addEventListener("mousedown", onOutside);
  document.addEventListener("keydown", onKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener("mousedown", onOutside);
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div ref="rootRef" class="fs">
    <button
      type="button"
      class="fs-trigger"
      :class="{ active: hasSelection, open }"
      :aria-haspopup="'listbox'"
      :aria-expanded="open"
      @click.stop="toggle"
    >
      <component :is="icon" v-if="icon" :size="13" class="fs-icon" aria-hidden="true" />
      <span class="fs-label">{{ selectedLabel }}</span>
      <X
        v-if="hasSelection"
        :size="13"
        class="fs-clear"
        role="button"
        aria-label="清除筛选"
        @click.stop="pick('')"
      />
      <ChevronDown v-else :size="13" class="fs-caret" aria-hidden="true" />
    </button>

    <div v-if="open" class="fs-menu" :class="[`fs-menu-${align}`]" role="listbox">
      <div v-if="searchable" class="fs-search">
        <Search :size="13" aria-hidden="true" />
        <input
          ref="searchRef"
          v-model="search"
          type="text"
          :placeholder="searchPlaceholder"
          @keydown.stop
        />
      </div>

      <div class="fs-list">
        <button
          type="button"
          class="fs-option"
          :class="{ active: !hasSelection }"
          role="option"
          :aria-selected="!hasSelection"
          @click="pick('')"
        >
          <span class="fs-option-label">{{ placeholder }}</span>
          <Check v-if="!hasSelection" :size="14" class="fs-check" />
        </button>

        <button
          v-for="opt in filteredOptions"
          :key="opt.value"
          type="button"
          class="fs-option"
          :class="{ active: opt.value === modelValue }"
          role="option"
          :aria-selected="opt.value === modelValue"
          @click="pick(opt.value)"
        >
          <span class="fs-option-label">{{ opt.label }}</span>
          <span v-if="typeof opt.count === 'number'" class="fs-count">{{ opt.count }}</span>
          <Check v-if="opt.value === modelValue" :size="14" class="fs-check" />
        </button>

        <p v-if="searchable && filteredOptions.length === 0" class="fs-empty">无匹配项</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fs { position: relative; display: inline-flex; }

.fs-trigger {
  height: 30px;
  max-width: 190px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 800;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 150ms ease, color 150ms ease, background 150ms ease;
}
.fs-trigger:hover { border-color: var(--border-strong); color: var(--text); }
.fs-trigger.active,
.fs-trigger.open {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary-strong);
  font-weight: 900;
}
.fs-icon { opacity: 0.7; flex-shrink: 0; }
.fs-trigger.active .fs-icon, .fs-trigger.open .fs-icon { opacity: 1; }
.fs-label { overflow: hidden; text-overflow: ellipsis; }
.fs-caret { opacity: 0.6; flex-shrink: 0; transition: transform 150ms ease; }
.fs-trigger.open .fs-caret { transform: rotate(180deg); opacity: 1; }
.fs-clear {
  flex-shrink: 0;
  opacity: 0.65;
  border-radius: 50%;
  transition: opacity 120ms ease, background 120ms ease;
}
.fs-clear:hover { opacity: 1; background: rgba(37, 99, 235, 0.14); }

.fs-menu {
  position: absolute;
  top: calc(100% + 6px);
  z-index: 60;
  min-width: 190px;
  max-width: 280px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.14);
  padding: 5px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fs-menu-left { left: 0; }
.fs-menu-right { right: 0; }

.fs-search {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 9px;
  border-radius: 8px;
  background: var(--surface-muted);
  color: var(--text-soft);
  transition: box-shadow 140ms ease, background 140ms ease;
}
.fs-search:focus-within { background: #fff; box-shadow: 0 0 0 2px var(--primary-soft); }
.fs-search input {
  border: 0;
  background: transparent;
  outline: none;
  box-shadow: none;
  font-size: 12.5px;
  color: var(--text);
  width: 100%;
}

.fs-list { display: flex; flex-direction: column; gap: 2px; max-height: 264px; overflow-y: auto; }
.fs-option {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 0 9px;
  border: 0;
  background: transparent;
  border-radius: 8px;
  color: var(--text);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  transition: background 120ms ease, color 120ms ease;
}
.fs-option:hover { background: var(--surface-muted); }
.fs-option.active { color: var(--primary-strong); background: var(--primary-soft); font-weight: 800; }
.fs-option-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fs-count {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-soft);
  background: var(--bg-subtle);
  border-radius: 999px;
  padding: 1px 7px;
}
.fs-option.active .fs-count { background: #fff; color: var(--primary-strong); }
.fs-check { flex-shrink: 0; color: var(--primary-strong); }
.fs-empty { margin: 0; padding: 12px; text-align: center; font-size: 12px; color: var(--text-soft); }
</style>
