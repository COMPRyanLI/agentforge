import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listMarketplace, type MarketplaceAgentRead } from "../api/marketplace";
import { useAuth } from "../auth/AuthContext";

const pageStyle = {
  padding: 24,
  color: "#e2e8f0",
  background: "var(--af-bg-canvas)",
  fontFamily: "system-ui, sans-serif",
  height: "100%",
  overflow: "auto",
};

const inputStyle = {
  background: "#1e293b",
  border: "1px solid #334155",
  borderRadius: 4,
  padding: "6px 10px",
  color: "#e2e8f0",
  fontSize: 13,
};

const cardStyle = {
  background: "#0f172a",
  border: "1px solid #1e293b",
  borderRadius: 8,
  padding: 16,
  marginBottom: 12,
  display: "block",
  textDecoration: "none",
  color: "#e2e8f0",
};

export function MarketplaceList() {
  const { token } = useAuth();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"installs" | "rating">("installs");
  const [agents, setAgents] = useState<MarketplaceAgentRead[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    listMarketplace(token, { q: q || undefined, sort })
      .then((result) => {
        setAgents(result);
        setError(null);
      })
      .catch((err) => setError(String(err)));
  }, [token, q, sort]);

  useEffect(() => {
    load();
  }, [load]);

  if (!token) {
    return <div style={pageStyle}>Enter a JWT token above to browse the marketplace.</div>;
  }

  return (
    <div style={pageStyle}>
      <h2>Marketplace</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          placeholder="Search by name"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={inputStyle}
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as "installs" | "rating")}
          style={inputStyle}
        >
          <option value="installs">Sort by installs</option>
          <option value="rating">Sort by rating</option>
        </select>
      </div>
      {error && <div style={{ color: "#ef4444", marginBottom: 12 }}>{error}</div>}
      {agents.length === 0 && <div style={{ color: "#64748b" }}>No published agents found.</div>}
      {agents.map((agent) => (
        <Link key={agent.id} to={`/marketplace/${agent.id}`} style={cardStyle}>
          <div style={{ fontWeight: 700 }}>{agent.name}</div>
          {agent.description && (
            <div style={{ color: "#94a3b8", fontSize: 13 }}>{agent.description}</div>
          )}
          <div style={{ color: "#64748b", fontSize: 12, marginTop: 4 }}>
            {agent.install_count} installs · {agent.avg_rating.toFixed(1)}★
          </div>
        </Link>
      ))}
    </div>
  );
}
