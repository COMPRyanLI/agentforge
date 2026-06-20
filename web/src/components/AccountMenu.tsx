import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

function initials(email: string): string {
  const local = email.split("@")[0] ?? "";
  return local.slice(0, 2).toUpperCase() || "?";
}

/** Account avatar + dropdown: email, a link to My agents, and Logout.
 * The avatar is always a neutral/outlined circle — never the accent fill —
 * so it doesn't compete with Publish as a second primary action. */
export function AccountMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as globalThis.Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  if (!user) return null;

  return (
    <div ref={containerRef} style={{ position: "relative", marginLeft: "auto" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Account menu"
        aria-expanded={open}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 28,
          height: 28,
          borderRadius: "50%",
          border: "1px solid var(--af-border)",
          background: "var(--af-bg-surface-raised)",
          color: "var(--af-text)",
          fontSize: 10,
          fontWeight: 700,
          cursor: "pointer",
        }}
      >
        {initials(user.email)}
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 6px)",
            width: 220,
            padding: 8,
            borderRadius: "var(--af-radius-md)",
            border: "1px solid var(--af-border)",
            background: "var(--af-bg-surface-raised)",
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            zIndex: 50,
          }}
        >
          <div
            style={{
              color: "var(--af-text-muted)",
              fontSize: 12,
              padding: "6px 8px",
              borderBottom: "1px solid var(--af-border)",
              marginBottom: 4,
              wordBreak: "break-all",
            }}
          >
            {user.email}
          </div>
          <Link
            to="/agents"
            onClick={() => setOpen(false)}
            style={{
              display: "block",
              padding: "6px 8px",
              borderRadius: "var(--af-radius-sm)",
              color: "var(--af-text)",
              textDecoration: "none",
              fontSize: 12,
            }}
          >
            My agents
          </Link>
          <button
            onClick={() => {
              setOpen(false);
              logout();
            }}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              padding: "6px 8px",
              borderRadius: "var(--af-radius-sm)",
              border: "none",
              background: "none",
              color: "var(--af-state-danger)",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Logout
          </button>
        </div>
      )}
    </div>
  );
}
