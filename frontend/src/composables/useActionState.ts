/**
 * Shared async-action state — loading spinner + current action label.
 *
 * Uses module-level ref() so all UI components bind to the same loading state.
 */

import { ref } from "vue";

export const loading = ref(false);
export const currentAction = ref<
  | "dashboard"
  | "search"
  | "outreach"
  | "reply"
  | "qualify"
  | "sync"
  | "followup"
  | null
>(null);

/**
 * Wrap an async action: sets loading/currentAction, clears errors on start,
 * and resets on completion or failure.
 */
export async function runAction<T>(
  actionName: typeof currentAction.value,
  fn: () => Promise<T>,
): Promise<T> {
  loading.value = true;
  currentAction.value = actionName;
  try {
    return await fn();
  } finally {
    loading.value = false;
    currentAction.value = null;
  }
}
