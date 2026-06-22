/**
 * Cross-cutting notification helpers.
 *
 * Two layers:
 *
 * 1. Legacy `notice` / `error` refs — still updated for the `<n-alert>`
 *    feedback strip components subscribe to. These remain so existing
 *    templates keep working unchanged.
 *
 * 2. Naive UI discrete-style API (`useMessage`/`useDialog`/`useNotification`).
 *    `<NaiveApiBridge>` (mounted inside the provider tree) calls
 *    `registerNotificationApis()` once on app boot, which lets module-level
 *    helpers like `notify()` and `confirmDanger()` reach into the live
 *    APIs without each consumer needing access to a component instance.
 *
 *    Until the bridge is mounted, calls fall back gracefully: setters just
 *    update the legacy refs; `confirmDanger()` falls back to native
 *    `globalThis.confirm` so headless contexts (and SSR) don't crash.
 */
import { ref } from "vue";
import type { DialogApi, MessageApi, NotificationApi } from "naive-ui";

// ── Legacy reactive surface (kept for back-compat) ────

export const notice = ref("");
export const error = ref("");

// ── Live Naive APIs (assigned by NaiveApiBridge) ──────

let messageApi: MessageApi | null = null;
let dialogApi: DialogApi | null = null;
let notificationApi: NotificationApi | null = null;

export function registerNotificationApis(apis: {
  message: MessageApi;
  dialog: DialogApi;
  notification: NotificationApi;
}): void {
  messageApi = apis.message;
  dialogApi = apis.dialog;
  notificationApi = apis.notification;
}

// ── Setters ───────────────────────────────────────────

interface NotifyOpts {
  /** Override the default duration in milliseconds. */
  duration?: number;
  /** When true, the toast stays until the user closes it. */
  closable?: boolean;
}

export function setNotice(msg: string, opts?: NotifyOpts): void {
  notice.value = msg;
  if (!msg) return;
  messageApi?.success(msg, {
    duration: opts?.duration ?? 3500,
    closable: opts?.closable ?? false,
  });
}

export function setError(msg: string, opts?: NotifyOpts): void {
  error.value = msg;
  if (!msg) return;
  messageApi?.error(msg, {
    duration: opts?.duration ?? 5500,
    closable: opts?.closable ?? true,
  });
}

/**
 * Generic toast — does NOT update the legacy `notice`/`error` refs unless
 * the type maps cleanly to them (`success` → notice, `error` → error).
 * Use this for `info` / `warning` so alert strips don't get spammed.
 */
export function notify(
  type: "success" | "info" | "warning" | "error",
  msg: string,
  opts?: NotifyOpts,
): void {
  if (!msg) return;
  if (type === "error") error.value = msg;
  else if (type === "success") notice.value = msg;

  const duration = opts?.duration ?? (type === "error" ? 5500 : 3500);
  const closable = opts?.closable ?? (type === "error" || type === "warning");
  messageApi?.[type](msg, { duration, closable });
}

/**
 * Persistent right-side notification (richer than a toast). Use for
 * "operation completed" reports that include a title/content pair.
 */
export function notifyPersistent(opts: {
  type?: "success" | "info" | "warning" | "error";
  title: string;
  content?: string;
  duration?: number;
}): void {
  const type = opts.type ?? "info";
  notificationApi?.[type]({
    title: opts.title,
    content: opts.content,
    duration: opts.duration ?? 6000,
    keepAliveOnHover: true,
  });
}

// ── Confirmation dialogs ──────────────────────────────

export interface ConfirmOpts {
  title: string;
  content?: string;
  /** Label for the destructive primary button. Defaults to 「确认」. */
  positiveText?: string;
  /** Label for the cancel button. Defaults to 「取消」. */
  negativeText?: string;
  /** When false, the primary button is the standard primary style. */
  danger?: boolean;
}

/**
 * Promise-based replacement for `globalThis.confirm()`. Renders a Naive UI
 * dialog with focus trap, Esc-to-cancel and a customisable danger style.
 *
 * In environments where the bridge has not initialised (SSR, tests, errors
 * during boot) it falls back to native `confirm` so callers always resolve.
 */
export function confirmDanger(opts: ConfirmOpts): Promise<boolean> {
  if (!dialogApi) {
    const fallback = globalThis.confirm?.(
      `${opts.title}${opts.content ? "\n\n" + opts.content : ""}`,
    );
    return Promise.resolve(!!fallback);
  }
  return new Promise<boolean>((resolve) => {
    let settled = false;
    const settle = (value: boolean) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    dialogApi!.warning({
      title: opts.title,
      content: opts.content,
      positiveText: opts.positiveText ?? "确认",
      negativeText: opts.negativeText ?? "取消",
      // Highlight the destructive primary button.
      positiveButtonProps:
        opts.danger !== false ? { type: "error" } : undefined,
      onPositiveClick: () => settle(true),
      onNegativeClick: () => settle(false),
      onClose: () => settle(false),
      onMaskClick: () => settle(false),
      onEsc: () => settle(false),
    });
  });
}
