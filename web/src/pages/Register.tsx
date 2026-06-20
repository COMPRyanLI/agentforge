import { useState, type CSSProperties, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function validate(): string | null {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return "Enter a valid email address.";
    if (password.length < 8) return "Password must be at least 8 characters.";
    return null;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await register(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      // Surface the backend's reason (e.g. "Email already registered")
      // when present, since unlike a login failure this one is actionable.
      const message = err instanceof Error ? err.message : "";
      const detail = message.match(/failed \d+: (.+)$/)?.[1];
      setError(detail || "Could not create account.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={pageStyle}>
      <form onSubmit={handleSubmit} style={cardStyle} noValidate>
        <h1 style={titleStyle}>Create account</h1>
        <label style={labelStyle} htmlFor="register-email">
          Email
        </label>
        <input
          id="register-email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={inputStyle}
        />
        <label style={labelStyle} htmlFor="register-password">
          Password
        </label>
        <input
          id="register-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={inputStyle}
        />
        {error && <div style={errorStyle}>{error}</div>}
        <button type="submit" disabled={submitting} style={primaryButtonStyle}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
        <div style={footerStyle}>
          Already have an account?{" "}
          <Link to="/login" style={linkStyle}>
            Log in
          </Link>
        </div>
      </form>
    </div>
  );
}

const pageStyle: CSSProperties = {
  height: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "var(--af-bg-canvas)",
  fontFamily: "var(--af-font-sans)",
};

const cardStyle: CSSProperties = {
  width: 320,
  padding: 24,
  borderRadius: "var(--af-radius-lg)",
  border: "1px solid var(--af-border)",
  background: "var(--af-bg-surface)",
  display: "flex",
  flexDirection: "column",
};

const titleStyle: CSSProperties = {
  margin: 0,
  marginBottom: 16,
  fontSize: 18,
  color: "var(--af-text)",
};

const labelStyle: CSSProperties = {
  color: "var(--af-text-faint)",
  fontSize: 11,
  marginBottom: 4,
  marginTop: 8,
};

const inputStyle: CSSProperties = {
  background: "var(--af-bg-surface-raised)",
  border: "1px solid var(--af-border)",
  borderRadius: "var(--af-radius-sm)",
  padding: "8px 10px",
  color: "var(--af-text)",
  fontSize: 13,
  fontFamily: "var(--af-font-sans)",
  boxSizing: "border-box",
};

const errorStyle: CSSProperties = {
  color: "var(--af-state-danger)",
  fontSize: 12,
  marginTop: 8,
};

const primaryButtonStyle: CSSProperties = {
  marginTop: 16,
  background: "var(--af-accent)",
  border: "none",
  borderRadius: "var(--af-radius-sm)",
  padding: "9px 0",
  color: "var(--af-accent-fg)",
  fontWeight: 600,
  fontSize: 13,
  cursor: "pointer",
};

const footerStyle: CSSProperties = {
  marginTop: 16,
  fontSize: 12,
  color: "var(--af-text-muted)",
  textAlign: "center",
};

const linkStyle: CSSProperties = { color: "var(--af-accent)" };
