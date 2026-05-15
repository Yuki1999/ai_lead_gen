import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

function countSelector(selector: string): number {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return (styles.match(new RegExp(`(^|\\n)${escaped}\\s*\\{`, "g")) || []).length;
}

describe("style system hygiene", () => {
  it("defines core shell selectors once", () => {
    for (const selector of [
      ":root",
      "body",
      ".app-frame",
      ".sidebar",
      ".workspace-shell",
      ".agent-console-layout",
      ".agent-chat-shell",
      ".agent-conversation-panel",
      ".agent-context-rail",
      ".agent-execution-rail",
      ".modern-data-table",
    ]) {
      assert.equal(countSelector(selector), 1, `${selector} should have one definition`);
    }
  });

  it("does not rely on a late override block", () => {
    assert.equal(styles.includes("Modern console redesign"), false);
  });
});
