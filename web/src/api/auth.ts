import { checkOk } from "./client";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserRead {
  id: string;
  email: string;
  created_at: string;
}

// login/register intentionally do NOT go through the shared checkOk() — a
// wrong-password/duplicate-email response is a normal 400/401 form error,
// not "your session expired," and must not trigger the global unauthorized
// handler (which would otherwise log out a user who was never logged in).
async function checkAuthOk(resp: Response, label: string): Promise<Response> {
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${label} failed ${resp.status}: ${body}`);
  }
  return resp;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  await checkAuthOk(resp, "login");
  return resp.json() as Promise<TokenResponse>;
}

export async function register(email: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  await checkAuthOk(resp, "register");
  return resp.json() as Promise<TokenResponse>;
}

export async function getMe(token: string): Promise<UserRead> {
  const resp = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "getMe");
  return resp.json() as Promise<UserRead>;
}
