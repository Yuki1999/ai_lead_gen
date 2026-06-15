import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const appVue = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
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
      assert.match(appVue + styles, new RegExp(className));
    }
  });

  it("uses a chat-first Agent console layout", () => {
    for (const className of [
      "agent-console-layout",
      "agent-chat-shell",
      "agent-design-shell",
      "agent-conversation-panel",
      "agent-sidebar-panel",
      "agent-main-panel",
      "agent-side-panel",
      "agent-context-rail",
      "agent-execution-rail",
      "agent-compose-surface",
      "agent-session-search",
      "agent-skill-pill",
      "agent-report-card",
      "agent-capability-card",
      "agent-log-button",
    ]) {
      assert.match(appVue + styles, new RegExp(className));
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
      assert.match(appVue + styles, new RegExp(className));
    }
  });

  it("lets the Agent workspace use the full available horizontal canvas", () => {
    assert.match(
      styles,
      /\.dashboard-grid\.agent-route \.content-area\s*\{[^}]*width:\s*100%;[^}]*max-width:\s*none;/s,
    );
    assert.match(
      styles,
      /\.agent-design-shell\s*\{[^}]*width:\s*100%;[^}]*grid-template-columns:\s*minmax\(220px,\s*clamp\(232px,\s*16vw,\s*280px\)\) minmax\(0,\s*1fr\) minmax\(280px,\s*clamp\(300px,\s*20\.5vw,\s*340px\)\);/s,
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
      "agent-config-header",
      "agent-config-summary",
      "agent-config-manage-button",
      "session-manager-foot",
    ]) {
      assert.match(appVue + styles, new RegExp(className));
    }
    assert.match(styles, /\.agent-hero-actions\s*\{[^}]*margin-top:\s*14px;/s);
    assert.match(styles, /\.agent-context-rail\s*\{[^}]*gap:\s*16px;/s);
    assert.match(
      styles,
      /\.agent-design-shell \.agent-session-manager\s*\{[^}]*min-height:\s*calc\(100dvh - 186px\);[^}]*grid-template-rows:\s*auto auto minmax\(0,\s*1fr\) auto;/s,
    );
    assert.match(styles, /\.session-list\s*\{[^}]*align-content:\s*start;/s);
    assert.match(styles, /\.agent-config\s*\{[^}]*padding:\s*15px;/s);
    assert.match(styles, /\.agent-capability-card\s*\{[^}]*padding:\s*15px;/s);
    assert.match(styles, /\.agent-execution-rail\s*\{[^}]*min-height:\s*380px;/s);
    assert.match(
      styles,
      /\.agent-output,\s*\.agent-empty-state\s*\{[^}]*min-height:\s*clamp\(360px,\s*calc\(100dvh - 485px\),\s*560px\);/s,
    );
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
      assert.match(appVue, new RegExp(component));
    }
  });

  it("wires Agent page interactive controls to visible behavior", () => {
    for (const binding of [
      '@click="toggleAgentGuide"',
      '@click="toggleAgentNotifications"',
      '@click="toggleSidebarUserMenu"',
      'v-model:value="agentSessionSearch"',
      "filteredAgentSessions",
      '@click="toggleAgentSettings"',
      '@click="copyAgentOutput"',
      '@click="downloadAgentOutput"',
      '@click="toggleAgentReportFullscreen"',
      '@click.prevent="toggleAgentSkillDetails"',
      '@click="toggleAgentLogs"',
    ]) {
      assert.match(appVue, new RegExp(binding.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    }

    for (const stateClass of [
      "agent-topbar-panels",
      "agent-guide-panel",
      "agent-notification-panel",
      "sidebar-user-menu",
      "agent-settings-panel",
      "agent-report-fullscreen",
      "agent-skill-detail-panel",
      "agent-log-panel",
      "session-empty-state",
    ]) {
      assert.match(appVue + styles, new RegExp(stateClass));
    }
  });
});
