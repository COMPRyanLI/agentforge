import { vi } from "vitest";
import type { AuthUser } from "./AuthContext";

/** Test-only helper: builds an AuthContextValue for `<AuthContext.Provider value={...}>`
 * in page tests that just need a token (and optionally a user) present. */
export function mockAuthValue(token: string, user: AuthUser | null = null) {
  return {
    token,
    user: token ? (user ?? { id: "u1", email: "test@example.com", created_at: "" }) : null,
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  };
}
