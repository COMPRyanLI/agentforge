import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getMe, login as apiLogin, register as apiRegister, type UserRead } from "../api/auth";
import { setUnauthorizedHandler } from "../api/client";

const TOKEN_STORAGE_KEY = "agentforge_token";

export type AuthUser = UserRead;

interface AuthContextValue {
  token: string;
  user: AuthUser | null;
  /** True only while rehydrating a persisted token on first mount. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

// Exported so tests can render pages with a preset session via
// <AuthContext.Provider value={{ token, user, loading: false, login: vi.fn(), ... }}>
export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_STORAGE_KEY) ?? "");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken("");
    setUser(null);
  }, []);

  // Rehydrate the session from a persisted token exactly once on mount. A
  // token written by login()/register() already has its user set by that
  // same call, so this effect intentionally never re-runs on token changes.
  useEffect(() => {
    const persisted = localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";
    if (!persisted) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    getMe(persisted)
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) logout();
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [logout]);

  // Any api/*.ts call that gets a 401 means this token is no longer valid —
  // log out so RequireAuth redirects to /login on the next render.
  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await apiLogin(email, password);
    localStorage.setItem(TOKEN_STORAGE_KEY, access_token);
    setToken(access_token);
    setUser(await getMe(access_token));
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const { access_token } = await apiRegister(email, password);
    localStorage.setItem(TOKEN_STORAGE_KEY, access_token);
    setToken(access_token);
    setUser(await getMe(access_token));
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
