import { ref } from "vue";

const storageKey = "ecommerce-agent-session";

export type SessionUser = {
  id: string;
  tenant_id: string;
  username: string;
  display_name: string;
  roles: string[];
  permissions: string[];
  enabled: boolean;
};

export type LoginSession = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: SessionUser;
};

function readSession(): LoginSession | null {
  try {
    const raw = sessionStorage.getItem(storageKey);
    return raw ? (JSON.parse(raw) as LoginSession) : null;
  } catch {
    return null;
  }
}

export const currentSession = ref<LoginSession | null>(readSession());

export function setSession(session: LoginSession | null) {
  currentSession.value = session;
  if (session) sessionStorage.setItem(storageKey, JSON.stringify(session));
  else sessionStorage.removeItem(storageKey);
}

export function authenticationHeaders(): Record<string, string> {
  return currentSession.value
    ? { Authorization: `Bearer ${currentSession.value.access_token}` }
    : {};
}

export function hasPermission(permission: string) {
  return currentSession.value?.user.permissions.includes(permission) ?? false;
}

export async function authenticatedFetch(path: string, options?: RequestInit) {
  const headers = new Headers(options?.headers);
  for (const [name, value] of Object.entries(authenticationHeaders())) headers.set(name, value);
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) setSession(null);
  return response;
}
