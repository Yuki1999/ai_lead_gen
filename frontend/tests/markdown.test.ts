import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { parseMarkdown, parseInlineMarkdown } from "../src/markdown.ts";

describe("markdown parsing", () => {
  it("parses headings, bold text, lists, blockquotes, and tables", () => {
    const blocks = parseMarkdown(`
## SkyWalker TKA India

### First tier

- **Adlife Enterprises** has distributor evidence.
- Plus Medical Devices

> Escalate regulatory issues.

| Company | Email |
|---|---|
| **Adlife** | info@adlife.in |
`);

    assert.equal(blocks[0].type, "heading");
    assert.deepEqual(blocks[0].content, [{ type: "text", text: "SkyWalker TKA India" }]);
    assert.equal(blocks[1].type, "heading");
    assert.equal(blocks[2].type, "list");
    assert.equal(blocks[3].type, "blockquote");
    assert.equal(blocks[4].type, "table");
    assert.deepEqual(blocks[4].headers[0], [{ type: "text", text: "Company" }]);
    assert.deepEqual(blocks[4].rows[0][0], [{ type: "strong", text: "Adlife" }]);
  });

  it("parses safe links and leaves unsafe links as text", () => {
    assert.deepEqual(parseInlineMarkdown("[site](https://example.com)"), [
      { type: "link", text: "site", href: "https://example.com" },
    ]);
    assert.deepEqual(parseInlineMarkdown("[bad](javascript:alert(1))"), [
      { type: "text", text: "bad" },
    ]);
  });
});
