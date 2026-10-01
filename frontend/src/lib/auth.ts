const KEY = "octoproc_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(KEY, token);
  } catch {
    /* storage unavailable (private mode): the user will simply be asked to sign in again */
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}