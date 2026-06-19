import { createContext, useContext, useState, type ReactNode } from "react";

interface AuthContextValue {
  token: string;
  setToken: (token: string) => void;
}

// Exported so tests can render pages with a preset token via
// <AuthContext value={{ token: "t", setToken: vi.fn() }}> without going
// through the NavBar input.
export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState("");
  return <AuthContext.Provider value={{ token, setToken }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
