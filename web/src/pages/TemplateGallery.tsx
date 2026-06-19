import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createAgentFromTemplate, listTemplates, type TemplateRead } from "../api/templates";
import { useAuth } from "../auth/AuthContext";

const pageStyle = {
  padding: 24,
  color: "#e2e8f0",
  fontFamily: "system-ui, sans-serif",
  height: "100%",
  overflow: "auto",
};

const cardStyle = {
  background: "#0f172a",
  border: "1px solid #1e293b",
  borderRadius: 8,
  padding: 16,
  marginBottom: 12,
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
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

export function TemplateGallery() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<TemplateRead[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    listTemplates(token)
      .then(setTemplates)
      .catch((err) => setError(String(err)));
  }, [token]);

  const handleUse = useCallback(
    async (templateId: string) => {
      if (!token) return;
      try {
        const agent = await createAgentFromTemplate(templateId, token);
        navigate("/", { state: { agentId: agent.id, agentName: agent.name } });
      } catch (err) {
        setError(String(err));
      }
    },
    [token, navigate]
  );

  if (!token) {
    return <div style={pageStyle}>Enter a JWT token above to browse templates.</div>;
  }

  return (
    <div style={pageStyle}>
      <h2>Templates</h2>
      {error && <div style={{ color: "#ef4444", marginBottom: 12 }}>{error}</div>}
      {templates.length === 0 && <div style={{ color: "#64748b" }}>No templates available.</div>}
      {templates.map((t) => (
        <div key={t.id} style={cardStyle}>
          <div>
            <div style={{ fontWeight: 700 }}>{t.name}</div>
            {t.description && (
              <div style={{ color: "#94a3b8", fontSize: 13 }}>{t.description}</div>
            )}
            <div style={{ color: "#64748b", fontSize: 12 }}>{t.category}</div>
          </div>
          <button onClick={() => handleUse(t.id)} style={buttonStyle}>
            Use this template
          </button>
        </div>
      ))}
    </div>
  );
}
