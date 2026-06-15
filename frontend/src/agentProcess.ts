export interface AgentProcessItem {
  id: number;
  kind: "running" | "event" | "done" | "error";
  label: string;
  detail?: string;
}

export function splitAgentProcessHistory(items: readonly AgentProcessItem[]): {
  current: AgentProcessItem | null;
  history: AgentProcessItem[];
} {
  if (items.length === 0) {
    return { current: null, history: [] };
  }

  return {
    current: items[items.length - 1],
    history: items.slice(0, -1),
  };
}

export function countAgentHistoryItems(
  processHistory: readonly AgentProcessItem[],
  toolEvents: readonly unknown[],
): number {
  return processHistory.length + toolEvents.length;
}
