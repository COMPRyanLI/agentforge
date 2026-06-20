// Shared fetch helpers for every api/*.ts module: auth headers, the
// check-response-ok pattern, and a single hook point for "the token is no
// longer valid" so AuthContext can react (clear state, redirect to /login)
// without every call site needing to know about routing.

let onUnauthorized: (() => void) | null = null;

/** Registered by AuthProvider on mount; cleared on unmount. */
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

export function authHeaders(token: string): Record<string, string> {
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

export async function checkOk(resp: Response, label: string): Promise<Response> {
  if (resp.status === 401) {
    onUnauthorized?.();
  }
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${label} failed ${resp.status}: ${body}`);
  }
  return resp;
}
