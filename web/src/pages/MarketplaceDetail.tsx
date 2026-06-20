import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getMarketplaceAgent,
  installAgent,
  listRatings,
  rateAgent,
  type MarketplaceAgentRead,
  type RatingRead,
} from "../api/marketplace";
import { useAuth } from "../auth/AuthContext";

const pageStyle = {
  padding: 24,
  color: "#e2e8f0",
  background: "var(--af-bg-canvas)",
  fontFamily: "system-ui, sans-serif",
  height: "100%",
  overflow: "auto",
  maxWidth: 640,
};

const buttonStyle = {
  background: "#3b82f6",
  border: "none",
  borderRadius: 4,
  padding: "6px 14px",
  color: "#fff",
  fontSize: 13,
  cursor: "pointer",
};

const inputStyle = {
  background: "#1e293b",
  border: "1px solid #334155",
  borderRadius: 4,
  padding: "6px 10px",
  color: "#e2e8f0",
  fontSize: 13,
};

export function MarketplaceDetail() {
  const { agentId } = useParams<{ agentId: string }>();
  const { token } = useAuth();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<MarketplaceAgentRead | null>(null);
  const [ratings, setRatings] = useState<RatingRead[]>([]);
  const [score, setScore] = useState(5);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token || !agentId) return;
    getMarketplaceAgent(agentId, token)
      .then(setAgent)
      .catch((err) => setError(String(err)));
    listRatings(agentId, token)
      .then(setRatings)
      .catch(() => setRatings([]));
  }, [token, agentId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleInstall = useCallback(async () => {
    if (!token || !agentId) return;
    try {
      const clone = await installAgent(agentId, token);
      navigate("/", { state: { agentId: clone.id, agentName: clone.name } });
    } catch (err) {
      setError(String(err));
    }
  }, [token, agentId, navigate]);

  const handleRate = useCallback(async () => {
    if (!token || !agentId) return;
    try {
      await rateAgent(agentId, score, comment || null, token);
      setComment("");
      setError(null);
      load();
    } catch (err) {
      setError(String(err));
    }
  }, [token, agentId, score, comment, load]);

  if (!token) {
    return <div style={pageStyle}>Enter a JWT token above to view this agent.</div>;
  }
  if (!agent) {
    return <div style={pageStyle}>{error ?? "Loading…"}</div>;
  }

  return (
    <div style={pageStyle}>
      <h2>{agent.name}</h2>
      {agent.description && <p style={{ color: "#94a3b8" }}>{agent.description}</p>}
      <div style={{ color: "#64748b", marginBottom: 16 }}>
        {agent.install_count} installs · {agent.avg_rating.toFixed(1)}★
      </div>
      {error && <div style={{ color: "#ef4444", marginBottom: 12 }}>{error}</div>}
      <button onClick={handleInstall} style={buttonStyle}>
        Install
      </button>

      <h3 style={{ marginTop: 32 }}>Rate this agent</h3>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
        <select
          value={score}
          onChange={(e) => setScore(Number(e.target.value))}
          style={inputStyle}
        >
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n} value={n}>
              {n}★
            </option>
          ))}
        </select>
        <input
          placeholder="Comment (optional)"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          style={{ ...inputStyle, flex: 1 }}
        />
        <button onClick={handleRate} style={buttonStyle}>
          Submit rating
        </button>
      </div>

      <h3 style={{ marginTop: 32 }}>Ratings</h3>
      {ratings.length === 0 && <div style={{ color: "#64748b" }}>No ratings yet.</div>}
      {ratings.map((r) => (
        <div
          key={r.id}
          style={{ borderTop: "1px solid #1e293b", padding: "8px 0", fontSize: 13 }}
        >
          <div>{r.score}★</div>
          {r.comment && <div style={{ color: "#94a3b8" }}>{r.comment}</div>}
        </div>
      ))}
    </div>
  );
}
