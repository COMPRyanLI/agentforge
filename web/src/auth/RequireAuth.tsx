import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

const loadingStyle = {
  padding: 24,
  color: "var(--af-text-muted)",
  fontFamily: "var(--af-font-sans)",
  fontSize: 13,
};

/** Wraps a route element: redirects to /login when there's no authenticated
 * user, preserving the attempted location so Login can send them back. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div style={loadingStyle}>Checking session…</div>;
  }
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}
