const KEY = 'sentinel.apiToken';
export const AUTH_EVENT = 'sentinel:auth-required';

/** The management-API token lives in sessionStorage only: it is gone when the tab closes. */
export function getToken(): string | null {
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.sessionStorage.setItem(KEY, token);
  } catch {
    /* storage unavailable: the token is simply not remembered */
  }
}

export function clearToken(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export function signalAuthRequired(): void {
  window.dispatchEvent(new Event(AUTH_EVENT));
}
