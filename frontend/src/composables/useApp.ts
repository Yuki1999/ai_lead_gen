/**
 * App-level navigation and theming state.
 *
 * Navigation is driven by vue-router. `activePage` is a read-only computed
 * derived from the active route name; `showPage` writes through to the
 * router. Components that previously read/wrote `activePage` directly keep
 * working because we re-export the same symbol shape.
 */
import { computed, watch } from "vue";
import { ref } from "vue";
import type { SelectOption } from "naive-ui";
import { router, type AppRouteName } from "@/router";

export type ActivePage = AppRouteName;

// ── Static config ─────────────────────────────────────

export const naiveThemeOverrides = {
  common: {
    primaryColor: "#2563EB",
    primaryColorHover: "#1D4ED8",
    primaryColorPressed: "#1E40AF",
    primaryColorSuppl: "#2563EB",
    borderRadius: "8px",
    borderRadiusSmall: "6px",
    fontFamily:
      'Inter, "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
};

export const statusFilterOptions: SelectOption[] = [
  { label: "全部", value: "" },
  { label: "新线索", value: "new" },
  { label: "已邮件", value: "emailed" },
  { label: "有兴趣", value: "interested" },
  { label: "转人工", value: "human_review" },
  { label: "已确认", value: "qualified" },
  { label: "拒绝", value: "rejected" },
];

export const providerOptions: SelectOption[] = [
  { label: "OpenAI", value: "openai" },
  { label: "DeepSeek", value: "deepseek" },
];

// ── Navigation state (route-driven) ───────────────────

/**
 * `activePage` mirrors the active route name. Falls back to "workspace"
 * for the initial tick before router has resolved.
 */
export const activePage = computed<ActivePage>(() => {
  const name = router.currentRoute.value.name;
  if (name === "agent" || name === "settings" || name === "workspace") {
    return name;
  }
  return "workspace";
});

// Agent UI toggle state (shared between agent page and app shell)
export const agentGuideOpen = ref(false);
export const agentNotificationsOpen = ref(false);
export const sidebarUserMenuOpen = ref(false);

// Reset transient popovers when the route changes — prevents stale popovers
// from leaking onto the next page.
watch(
  () => router.currentRoute.value.name,
  () => {
    agentGuideOpen.value = false;
    agentNotificationsOpen.value = false;
    sidebarUserMenuOpen.value = false;
  },
);

// ── Computed ──────────────────────────────────────────

export const topbarContent = computed(() => {
  if (activePage.value === "agent") {
    return {
      eyebrow: "Pi / pi-mono Agent",
      title: "渠道拓展 Agent",
      copy: "默认使用 overseas-distributor-prospecting skill，支持实时输出、联网搜索和线索入库。",
    };
  }
  if (activePage.value === "settings") {
    return {
      eyebrow: "系统配置",
      title: "设置",
      copy: "邮件回复自动同步、Agent 模型与 API 配置。",
    };
  }
  return {
    eyebrow: "微创畅行机器人 · 海外业务",
    title: "海外渠道拓展系统",
    copy: "面向 SkyWalker TKA 的代理商发现、邮箱证据审阅、触达记录和回复处理。",
  };
});

// ── Navigation actions ────────────────────────────────

/**
 * Programmatic navigation. Equivalent to clicking a sidebar nav link.
 * `sectionId` triggers a same-page scroll once the route is resolved.
 */
export function showPage(page: ActivePage, sectionId?: string): void {
  const current = router.currentRoute.value;
  const isSameRoute = current.name === page;

  // Reset shared popover state immediately — even when navigating to the
  // same page, the user clicked a sidebar entry and expects a clean view.
  agentGuideOpen.value = false;
  agentNotificationsOpen.value = false;
  sidebarUserMenuOpen.value = false;

  const navigation = isSameRoute ? Promise.resolve() : router.push({ name: page });

  void Promise.resolve(navigation).then(() => {
    if (page === "settings") {
      // Lazy import to avoid circular dependency with useSettings.
      import("@/composables/useSettings").then((m) => m.loadSettings());
      return;
    }
    const targetId = sectionId || (page === "agent" ? "overview" : "");
    if (!targetId) return;
    globalThis.requestAnimationFrame?.(() => {
      globalThis.document?.getElementById(targetId)?.scrollIntoView({ block: "start" });
    });
  });
}

export function toggleAgentGuide(): void {
  agentGuideOpen.value = !agentGuideOpen.value;
  if (agentGuideOpen.value) agentNotificationsOpen.value = false;
}

export function toggleAgentNotifications(): void {
  agentNotificationsOpen.value = !agentNotificationsOpen.value;
  if (agentNotificationsOpen.value) agentGuideOpen.value = false;
}

export function toggleSidebarUserMenu(): void {
  sidebarUserMenuOpen.value = !sidebarUserMenuOpen.value;
}

export function useApp() {
  return {
    naiveThemeOverrides,
    statusFilterOptions,
    providerOptions,
    activePage,
    agentGuideOpen,
    agentNotificationsOpen,
    sidebarUserMenuOpen,
    topbarContent,
    showPage,
    toggleAgentGuide,
    toggleAgentNotifications,
    toggleSidebarUserMenu,
  };
}
