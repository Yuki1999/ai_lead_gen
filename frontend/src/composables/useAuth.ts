/**
 * Authentication state and actions.
 *
 * Manages JWT token lifecycle, login/logout/verify, and localStorage persistence.
 * Uses module-level ref() for isAuthenticated so the api.ts module can also
 * reference it for 401 detection.
 */
import { computed, ref } from "vue";
import { apiBase, setApiAuthToken } from "@/api";

// ── Constants ──────────────────────────────────────────

const STORAGE_TOKEN_KEY = "medbot_auth_token";
const STORAGE_USERNAME_KEY = "medbot_auth_username";
const STORAGE_PERMS_KEY = "medbot_auth_permissions";

// ── Helpers (module-private) ───────────────────────────

function localStorageGet(key: string): string {
  try {
    return globalThis.localStorage?.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function localStorageSet(key: string, value: string): void {
  try {
    globalThis.localStorage?.setItem(key, value);
  } catch {
    // storage unavailable
  }
}

function localStorageRemove(key: string): void {
  try {
    globalThis.localStorage?.removeItem(key);
  } catch {
    // storage unavailable
  }
}

// ── Module-level state ─────────────────────────────────

export const authToken = ref(localStorageGet(STORAGE_TOKEN_KEY));
export const authUsername = ref(localStorageGet(STORAGE_USERNAME_KEY));
export const authPermissions = ref<string[]>(
  JSON.parse(localStorageGet(STORAGE_PERMS_KEY) || "[]"),
);
export const loginUsername = ref("");
export const loginPassword = ref("");
export const loginLoading = ref(false);
export const loginError = ref("");

export const isAuthenticated = computed(() => !!authToken.value);

// Sync initial token into api.ts on module load
if (authToken.value) {
  setApiAuthToken(authToken.value);
}

// ── Permission helpers ─────────────────────────────────
//
// Wildcard rules (must match backend app/permissions.py::matches):
//   - "*"          grants everything
//   - "<group>:*"  grants every action in that group
//   - exact match  works as you'd expect
//
// Anything else is treated as a plain string.

export function hasPermission(perm: string): boolean {
  const granted = authPermissions.value;
  if (!granted || granted.length === 0) return false;
  if (granted.includes("*")) return true;
  if (granted.includes(perm)) return true;
  const colon = perm.indexOf(":");
  if (colon > 0) {
    const groupWildcard = perm.slice(0, colon) + ":*";
    if (granted.includes(groupWildcard)) return true;
  }
  return false;
}

function setAuthPermissions(perms: string[] | undefined | null): void {
  const list = Array.isArray(perms) ? perms.map(String) : [];
  authPermissions.value = list;
  localStorageSet(STORAGE_PERMS_KEY, JSON.stringify(list));
}

/**
 * Re-fetch the latest permission list from the server. Called on app boot
 * (via verifyAndRestoreAuth) and any time the UI suspects state has shifted —
 * e.g. after the admin edits a role, or on tab focus / periodic timer.
 */
export async function refreshPermissions(): Promise<string[]> {
  if (!authToken.value) return authPermissions.value;
  try {
    const resp = await fetch(`${apiBase}/auth/verify`, {
      headers: { Authorization: `Bearer ${authToken.value}` },
    });
    if (!resp.ok) {
      // 401: token is dead — clear and bounce.
      if (resp.status === 401) clearAuth();
      return authPermissions.value;
    }
    const data = (await resp.json()) as {
      username: string;
      valid: boolean;
      permissions?: string[];
    };
    if (data.valid) {
      setAuthPermissions(data.permissions);
    }
    return authPermissions.value;
  } catch {
    return authPermissions.value;
  }
}

// ── Auth actions ───────────────────────────────────────

export function clearAuth(): void {
  authToken.value = "";
  authUsername.value = "";
  authPermissions.value = [];
  setApiAuthToken("");
  localStorageRemove(STORAGE_TOKEN_KEY);
  localStorageRemove(STORAGE_USERNAME_KEY);
  localStorageRemove(STORAGE_PERMS_KEY);
}

export async function login(
  postLogin?: () => Promise<void>,
): Promise<void> {
  loginError.value = "";
  if (!loginUsername.value.trim() || !loginPassword.value.trim()) {
    loginError.value = "请输入用户名和密码";
    return;
  }
  loginLoading.value = true;
  try {
    const resp = await fetch(`${apiBase}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: loginUsername.value.trim(),
        password: loginPassword.value,
      }),
    });

    if (!resp.ok) {
      const body = await resp.text();
      let detail = "登录失败";
      try {
        detail = JSON.parse(body).detail || detail;
      } catch {
        /* ignore parse errors */
      }
      loginError.value = detail;
      return;
    }

    const data = (await resp.json()) as {
      access_token: string;
      username: string;
      permissions?: string[];
    };
    authToken.value = data.access_token;
    authUsername.value = data.username;
    setApiAuthToken(data.access_token);
    setAuthPermissions(data.permissions);
    localStorageSet(STORAGE_TOKEN_KEY, data.access_token);
    localStorageSet(STORAGE_USERNAME_KEY, data.username);
    loginPassword.value = "";

    const { setNotice } = await import("@/composables/useNotifications");
    setNotice(`欢迎，${data.username}`);

    // Allow caller to chain post-login data loading
    if (postLogin) await postLogin();
  } catch (caught) {
    loginError.value = caught instanceof Error ? caught.message : "登录失败";
  } finally {
    loginLoading.value = false;
  }
}

export async function verifyAndRestoreAuth(): Promise<boolean> {
  if (!authToken.value) return false;
  try {
    const resp = await fetch(`${apiBase}/auth/verify`, {
      headers: { Authorization: `Bearer ${authToken.value}` },
    });
    if (!resp.ok) {
      clearAuth();
      return false;
    }
    const data = (await resp.json()) as {
      username: string;
      valid: boolean;
      permissions?: string[];
    };
    if (data.valid && data.username) {
      authUsername.value = data.username;
      setAuthPermissions(data.permissions);
      localStorageSet(STORAGE_USERNAME_KEY, data.username);
      return true;
    }
  } catch {
    // Network error — keep token and try later
    return !!authToken.value;
  }
  clearAuth();
  return false;
}

export function logout(): void {
  clearAuth();
}

export function onLoginKeydown(event: KeyboardEvent): void {
  if (event.key === "Enter") {
    login();
  }
}

// ── Clipboard utilities ────────────────────────────────

function fallbackCopyText(text: string): boolean {
  const documentRef = globalThis.document;
  if (!documentRef?.body) return false;

  const textarea = documentRef.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  documentRef.body.append(textarea);
  textarea.select();
  try {
    documentRef.execCommand("copy");
    return true;
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}

export async function copyTextToClipboard(
  text: string,
  successMessage: string,
): Promise<void> {
  const { setNotice } = await import("@/composables/useNotifications");
  try {
    const clipboard = globalThis.navigator?.clipboard;
    if (clipboard?.writeText) {
      await clipboard.writeText(text);
      setNotice(successMessage);
      return;
    }
  } catch {
    // Fall through to the textarea fallback below.
  }

  setNotice(fallbackCopyText(text) ? successMessage : "复制失败，请手动选择内容");
}

// ── Re-export state for consumers ──────────────────────

export function useAuth() {
  return {
    authToken,
    authUsername,
    authPermissions,
    loginUsername,
    loginPassword,
    loginLoading,
    loginError,
    // Computed
    isAuthenticated,
    // Functions
    hasPermission,
    refreshPermissions,
    clearAuth,
    login,
    verifyAndRestoreAuth,
    logout,
    onLoginKeydown,
    copyTextToClipboard,
  };
}
