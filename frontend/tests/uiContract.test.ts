import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const appVue = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
const loginPage = readFileSync(new URL("../src/components/LoginPage.vue", import.meta.url), "utf8");
const agentPage = readFileSync(new URL("../src/components/AgentPage.vue", import.meta.url), "utf8");
const workspacePage = readFileSync(new URL("../src/components/WorkspacePage.vue", import.meta.url), "utf8");
const settingsPage = readFileSync(new URL("../src/components/SettingsPage.vue", import.meta.url), "utf8");
const allTemplates = appVue + loginPage + agentPage + workspacePage + settingsPage;
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const packageJson = readFileSync(new URL("../package.json", import.meta.url), "utf8");

describe("modern console UI contract", () => {
  it("uses a workspace shell with modern summary and data table regions", () => {
    for (const className of [
      "workspace-shell",
      "workspace-command",
      "workspace-ops-panel",
      "product-summary-card",
      "summary-strip",
      "modern-data-table",
      "lead-intelligence-panel",
    ]) {
      assert.match(allTemplates + styles, new RegExp(className));
    }
  });

  it("uses a chat-first Agent console layout", () => {
    // After the agent-page rewrite, the shell is a chat app (header /
    // drawer + scroll / sticky composer). Legacy class names are kept
    // alongside the new ones so consumers depending on the old contract
    // — and Vue style hooks that already shipped — still resolve.
    for (const className of [
      "agent-console-layout",
      "agent-chat-shell",
      "agent-design-shell",
      "agent-conversation-panel",
      "agent-sidebar-panel",
      "agent-main-panel",
      "agent-compose-surface",
      "agent-session-search",
      "agent-skill-pill",
      // Chat-rewrite primitives
      "agent-chat-head",
      "agent-chat-body",
      "agent-chat-drawer",
      "agent-chat-stage",
      "agent-chat-scroll",
      "agent-chat-composer",
      "agent-chat-turn",
      "agent-msg-user",
      "agent-msg-agent",
      "agent-tool-card",
      "agent-welcome",
      "agent-starter-card",
    ]) {
      assert.match(allTemplates + styles, new RegExp(className));
    }
  });

  it("matches the referenced Agent page chrome", () => {
    for (const className of [
      "nav-icon",
      "sidebar-usage-card",
      "sidebar-user-card",
      "agent-hero-actions",
      "agent-guide-button",
      "agent-online-badge",
      "notification-button",
    ]) {
      assert.match(allTemplates + styles, new RegExp(className));
    }
  });

  it("lets the Agent workspace use the full available horizontal canvas", () => {
    assert.match(
      styles,
      /\.dashboard-grid\.agent-route \.content-area\s*\{[^}]*width:\s*100%;[^}]*max-width:\s*none;/s,
    );
    // Chat shell collapses the previous 3-column grid into a single
    // column that the drawer + stage live inside `.agent-chat-body`.
    assert.match(
      styles,
      /\.agent-chat-shell\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*!important;/s,
    );
  });

  it("uses fluid shell sizing instead of a fixed desktop canvas", () => {
    assert.doesNotMatch(styles, /1440px/);
    assert.match(
      styles,
      /\.app-frame\s*\{[^}]*grid-template-columns:\s*clamp\(248px,\s*18vw,\s*288px\) minmax\(0,\s*1fr\);/s,
    );
    assert.match(
      styles,
      /\.workspace-shell\s*\{[^}]*padding:\s*clamp\(16px,\s*1\.1vw,\s*24px\) clamp\(18px,\s*1\.3vw,\s*22px\) clamp\(32px,\s*3vw,\s*56px\) clamp\(16px,\s*1vw,\s*18px\);/s,
    );
  });

  it("keeps Agent page controls aligned to the reference design", () => {
    for (const className of [
      "agent-crumb",
      "agent-action-buttons",
      "agent-config-manage-button",
    ]) {
      assert.match(allTemplates + styles, new RegExp(className));
    }
    assert.match(styles, /\.agent-hero-actions\s*\{[^}]*margin-top:\s*14px;/s);
  });

  it("uses a Vue component library for core controls", () => {
    assert.match(packageJson, /"naive-ui"/);
    for (const component of [
      "n-config-provider",
      "n-card",
      "n-button",
      "n-input",
      "n-select",
      "n-tag",
    ]) {
      assert.match(allTemplates, new RegExp(component));
    }
  });

  it("wires Agent page interactive controls to visible behavior", () => {
    // Core interactions kept across the chat-rewrite. `@click=` bindings
    // for the legacy panels are gone (skill/logs/notifications still
    // exist but live inside the new composer/drawer surfaces).
    for (const binding of [
      '@click="toggleSidebarUserMenu"',
      '@click="toggleAgentGuide"',
      '@click="toggleAgentNotifications"',
      'v-model="agentSessionSearch"',
      "filteredAgentSessions",
      '@click="toggleAgentSettings"',
      '@click="toggleAgentSkillDetails"',
      '@click="sendAgentPrompt"',
      '@click="cancelAgentPrompt"',
      '@click="clearChatHistory"',
      '@click="startNewAgentSession"',
      '@click="toggleSessionDrawer"',
    ]) {
      assert.match(allTemplates, new RegExp(binding.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    }

    for (const stateClass of [
      "agent-topbar-panels",
      "agent-guide-panel",
      "agent-notification-panel",
      "sidebar-user-menu",
      "agent-settings-panel",
      "agent-msg-thinking",
      "agent-streaming-cursor",
      "agent-tool-card",
      "agent-chat-drawer",
    ]) {
      assert.match(allTemplates + styles, new RegExp(stateClass));
    }
  });
});
