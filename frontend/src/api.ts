/**
 * Shared HTTP client for the frontend.
 *
 * All API calls go through the `request<T>()` wrapper which attaches the
 * JWT auth token and normalises error handling (401 → clear token).
 */
import { ref } from "vue";

// Module-level token holder — set via useAuth on login/logout.
const _authToken = ref("");

export function setApiAuthToken(token: string): void {
  _authToken.value = token;
}

export function getApiAuthToken(): string {
  return _authToken.value;
}

export const apiBase =
  import.meta.env.VITE_API_BASE_URL || "/api";

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  if (_authToken.value) {
    headers["Authorization"] = `Bearer ${_authToken.value}`;
  }
  const response = await fetch(`${apiBase}${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.text();
    if (response.status === 401 && _authToken.value) {
      _authToken.value = ""; // back-pressure: auth module will notice
    }
    throw new Error(body);
  }
  return (await response.json()) as T;
}

// ── Permission registry ────────────────────────────────
//
// The backend (/permissions/registry) is the single source of truth for the
// permission catalog (keys, group labels, descriptions, presets). The frontend
// fetches it once after auth and caches it module-level. This eliminates the
// previous duplicated ALL_PERMISSIONS / permLabels constants.

export interface PermissionMeta {
  key: string;
  group: string;
  group_label: string;
  label: string;
  description: string;
}

export interface PermissionGroup {
  key: string;
  label: string;
  permissions: string[];
}

export interface PermissionPreset {
  key: string;
  label: string;
  description: string;
  permissions: string[];
}

export interface PermissionRegistry {
  permissions: PermissionMeta[];
  groups: PermissionGroup[];
  presets: PermissionPreset[];
}

export const permissionRegistry = ref<PermissionRegistry | null>(null);

let _registryPromise: Promise<PermissionRegistry> | null = null;

export async function fetchPermissionRegistry(force = false): Promise<PermissionRegistry> {
  if (!force && permissionRegistry.value) return permissionRegistry.value;
  if (!force && _registryPromise) return _registryPromise;
  _registryPromise = request<PermissionRegistry>("/permissions/registry").then((reg) => {
    permissionRegistry.value = reg;
    _registryPromise = null;
    return reg;
  }).catch((err) => {
    _registryPromise = null;
    throw err;
  });
  return _registryPromise;
}
