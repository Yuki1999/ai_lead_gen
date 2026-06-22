import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const router = readFileSync(new URL("../src/router/index.ts", import.meta.url), "utf8");
const main = readFileSync(new URL("../src/main.ts", import.meta.url), "utf8");
const useApp = readFileSync(new URL("../src/composables/useApp.ts", import.meta.url), "utf8");
const appVue = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");

describe("router contract (PR1)", () => {
  it("uses hash mode so the SPA stays behind the proxy", () => {
    assert.match(router, /createWebHashHistory\(\)/);
  });

  it("declares a workspace route as the default landing page", () => {
    // `/` redirects to the named workspace route; the workspace path
    // itself owns the human-readable URL `/leads`.
    assert.match(router, /redirect:\s*\{\s*name:\s*"workspace"/);
    assert.match(router, /path:\s*"\/leads"[\s\S]+?name:\s*"workspace"/);
  });

  it("declares the agent and settings routes the sidebar links to", () => {
    assert.match(router, /path:\s*"\/agent"[\s\S]+?name:\s*"agent"/);
    assert.match(router, /path:\s*"\/settings"[\s\S]+?name:\s*"settings"/);
  });

  it("falls back to workspace on unknown paths", () => {
    assert.match(router, /path:\s*"\/:pathMatch\(\.\*\)\*"/);
  });

  it("is installed as the global router via main.ts", () => {
    assert.match(main, /import\s+\{\s*router\s*\}\s+from\s+"\.\/router"/);
    assert.match(main, /\.use\(router\)/);
  });

  it("exposes activePage as a route-driven computed in useApp", () => {
    // `activePage` must be derived from the live route name so back/
    // forward navigation updates it without manual `.value =` writes.
    assert.match(useApp, /activePage\s*=\s*computed/);
    assert.match(useApp, /router\.currentRoute\.value\.name/);
  });

  it("App.vue mirrors the route into its local activePage ref", () => {
    // The shell still renders pages as `v-if="activePage === ..."`;
    // this watch keeps the local ref in sync with router state.
    assert.match(appVue, /watch\(\s*\(\)\s*=>\s*router\.currentRoute\.value\.name/);
  });

  it("App.vue routes navigation through router.push (no direct activePage writes outside the watch)", () => {
    // Allow the single-line write inside the watch callback; flag any
    // others as regressions. Only assignments (`= …`) count, not
    // comparisons (`=== …`).
    const matches = appVue.match(/activePage\.value\s*=(?!=)/g) || [];
    assert.equal(
      matches.length,
      1,
      `Expected exactly one assignment to activePage.value (inside the route watch); found ${matches.length}.`,
    );
  });

  it("upgrades legacy #agent / #settings hashes on mount", () => {
    assert.match(appVue, /legacyHash\s*===\s*"#agent"/);
    assert.match(appVue, /legacyHash\s*===\s*"#settings"/);
  });
});

describe("provider tree contract (PR2)", () => {
  it("wraps the shell in NaiveUI message/dialog/notification providers", () => {
    assert.match(appVue, /<n-message-provider[^>]*>/);
    assert.match(appVue, /<n-dialog-provider>/);
    assert.match(appVue, /<n-notification-provider[^>]*>/);
  });

  it("mounts NaiveApiBridge so module-level helpers can reach the live APIs", () => {
    assert.match(appVue, /<NaiveApiBridge\s*\/>/);
  });

  it("replaces every globalThis.confirm() with confirmDanger() in App.vue", () => {
    assert.equal(
      (appVue.match(/globalThis\.confirm/g) || []).length,
      0,
      "App.vue should not call globalThis.confirm directly anymore.",
    );
    assert.match(appVue, /confirmDanger\(/);
  });
});

describe("design + interaction polish (PR3-PR6)", () => {
  it("declares the tier-2 design tokens", () => {
    const styles = readFileSync(
      new URL("../src/styles.css", import.meta.url),
      "utf8",
    );
    for (const token of [
      "--neutral-50:",
      "--neutral-900:",
      "--radius-pill:",
      "--radius-lg:",
      "--text-xs:",
      "--text-3xl:",
      "--space-1:",
      "--space-8:",
      "--score-high:",
      "--score-low:",
    ]) {
      assert.ok(
        styles.includes(token),
        `Expected design token ${token} in styles.css`,
      );
    }
  });

  it("loads the Inter font via @fontsource", () => {
    assert.match(main, /@fontsource\/inter\/400\.css/);
    assert.match(main, /@fontsource\/inter\/700\.css/);
  });

  it("applies score-tier classes to the lead score badge", () => {
    assert.match(appVue, /scoreTier\(lead\.score\)/);
    assert.match(appVue, /function scoreTier\(/);
  });

  it("enforces a real character cap on the agent prompt", () => {
    assert.match(appVue, /AGENT_PROMPT_MAX\s*=\s*2000/);
    assert.match(appVue, /:maxlength="AGENT_PROMPT_MAX"/);
  });

  it("removes the hardcoded '完成于 2026-05-15' placeholder", () => {
    assert.equal(
      (appVue.match(/2026-05-15/g) || []).length,
      0,
      "Hardcoded date placeholder should be replaced with agentCompletedAtLabel.",
    );
    assert.match(appVue, /agentCompletedAtLabel/);
  });

  it("exposes a stop button while the agent stream is running", () => {
    assert.match(appVue, /cancelAgentPrompt/);
    assert.match(appVue, /AbortController\(\)/);
  });

  it("wires the settings tabs as an ARIA tablist with keyboard support", () => {
    assert.match(appVue, /role="tablist"/);
    assert.match(appVue, /role="tab"/);
    assert.match(appVue, /onSettingsTabKeydown/);
  });

  it("ships a Cmd+K command palette mounted at the root", () => {
    assert.match(appVue, /<CommandPalette[\s\S]*?:commands="paletteCommands"/);
    // The keydown handler must intercept Meta/Ctrl+K.
    assert.match(appVue, /event\.metaKey\s*\|\|\s*event\.ctrlKey/);
    assert.match(appVue, /event\.key === "k"|event\.key === "K"/);
  });

  it("groups all agent-side popovers through closeOtherPopovers", () => {
    // Mutual-exclusion guarantees only one popover is visible at a time.
    assert.match(appVue, /function closeOtherPopovers\(/);
    for (const key of ["guide", "notifications", "settings", "skill", "logs", "userMenu"]) {
      assert.ok(
        appVue.includes(`closeOtherPopovers("${key}"`),
        `Expected closeOtherPopovers("${key}") to be invoked`,
      );
    }
  });
});
