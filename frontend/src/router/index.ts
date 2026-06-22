/**
 * Application router.
 *
 * Hash mode is used so the SPA stays fully behind the Nginx reverse proxy
 * without requiring server-side rewrite rules.
 *
 * Migration note (PR1):
 *   App.vue still owns all page rendering as inline templates gated by the
 *   `activePage` computed (see useApp.ts). The router exists to give the
 *   browser history/back/forward and bookmarkable URLs; the route components
 *   are intentionally empty placeholders. Page extraction into real
 *   `<router-view>` components is staged for a later PR so the visual surface
 *   does not change while we land the structural pieces.
 */
import { defineComponent, h } from "vue";
import {
  createRouter,
  createWebHashHistory,
  type RouteLocationNormalized,
  type RouteRecordRaw,
} from "vue-router";

// Empty placeholder — real rendering still happens in App.vue.
const RoutePlaceholder = defineComponent({
  name: "RoutePlaceholder",
  render: () => h("div", { class: "route-placeholder", "aria-hidden": "true" }),
});

export type AppRouteName = "workspace" | "agent" | "settings";

export const routes: RouteRecordRaw[] = [
  {
    path: "/",
    redirect: { name: "workspace" satisfies AppRouteName },
  },
  {
    path: "/leads",
    name: "workspace" satisfies AppRouteName,
    component: RoutePlaceholder,
    meta: { title: "线索数据库" },
  },
  {
    path: "/agent",
    name: "agent" satisfies AppRouteName,
    component: RoutePlaceholder,
    meta: { title: "渠道拓展 Agent" },
  },
  {
    path: "/settings",
    name: "settings" satisfies AppRouteName,
    component: RoutePlaceholder,
    meta: { title: "系统设置" },
  },
  // Catch-all → workspace
  {
    path: "/:pathMatch(.*)*",
    redirect: { name: "workspace" satisfies AppRouteName },
  },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    if (savedPosition) return savedPosition;
    return { top: 0 };
  },
});

router.beforeEach((to: RouteLocationNormalized) => {
  if (to.meta?.title && typeof globalThis.document !== "undefined") {
    globalThis.document.title = `${String(to.meta.title)} · 海外渠道拓展系统`;
  }
});

export default router;
