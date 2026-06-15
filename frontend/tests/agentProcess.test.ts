import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  countAgentHistoryItems,
  splitAgentProcessHistory,
  type AgentProcessItem,
} from "../src/agentProcess.ts";

describe("agent process history display helpers", () => {
  it("keeps only the latest process item visible by default", () => {
    const items: AgentProcessItem[] = [
      { id: 1, kind: "running", label: "会话已开始" },
      { id: 2, kind: "event", label: "工具开始: web_search" },
      { id: 3, kind: "event", label: "工具完成: web_search" },
    ];

    const split = splitAgentProcessHistory(items);

    assert.deepEqual(split.current, items[2]);
    assert.deepEqual(split.history, [items[0], items[1]]);
  });

  it("counts collapsed process and tool-event history", () => {
    const processHistory: AgentProcessItem[] = [
      { id: 1, kind: "running", label: "会话已开始" },
      { id: 2, kind: "event", label: "工具开始: web_search" },
    ];

    assert.equal(countAgentHistoryItems(processHistory, [{ type: "tool_execution_start" }]), 3);
  });
});
