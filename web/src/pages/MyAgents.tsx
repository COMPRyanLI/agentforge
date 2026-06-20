import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { deleteAgent, getCurrentVersion, listAgents, type AgentRead } from "../api/agents";
import { useAuth } from "../auth/AuthContext";
import { DataTable, type DataTableColumn } from "../components/ui/DataTable";
import { EmptyState } from "../components/ui/EmptyState";
import { Skeleton } from "../components/ui/Skeleton";
import { colors, fontFamily, radius, space, typeScale } from "../components/ui/tokens";

const pageStyle = {
  padding: space.xl,
  color: colors.text,
  background: "var(--af-bg-canvas)",
  fontFamily,
  height: "100%",
  overflow: "auto",
};

const actionButtonStyle = {
  background: "none",
  border: "none",
  color: colors.accent,
  cursor: "pointer",
  fontSize: typeScale.base,
  padding: 0,
  marginLeft: space.md,
};

async function exportAgent(agent: AgentRead, token: string): Promise<void> {
  const version = await getCurrentVersion(agent.id, token);
  const payload = {
    name: agent.name,
    version_number: version.version_number,
    graph_json: version.graph_json,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${agent.name.replace(/\s+/g, "_")}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export function MyAgents() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentRead[]>([]);
  const [loading, setLoading] = useState(true);
  // Separate from actionError: a load failure replaces the whole page with a
  // retry state, but a failed export/delete on one row shouldn't hide a list
  // that loaded fine — that's surfaced as an inline banner instead.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setLoadError(null);
    listAgents(token)
      .then(setAgents)
      .catch((err) => setLoadError(String(err)))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const handleOpen = useCallback(
    (agent: AgentRead) => {
      navigate("/", { state: { agentId: agent.id, agentName: agent.name } });
    },
    [navigate]
  );

  const handleExport = useCallback(
    (agent: AgentRead) => {
      setActionError(null);
      void exportAgent(agent, token).catch((err) => setActionError(String(err)));
    },
    [token]
  );

  const handleDelete = useCallback(
    (agent: AgentRead) => {
      if (!window.confirm(`Delete "${agent.name}"? This cannot be undone.`)) return;
      setActionError(null);
      deleteAgent(agent.id, token)
        .then(() => setAgents((prev) => prev.filter((a) => a.id !== agent.id)))
        .catch((err) => setActionError(String(err)));
    },
    [token]
  );

  const columns: DataTableColumn<AgentRead>[] = [
    { key: "name", header: "Name", render: (a) => a.name },
    { key: "visibility", header: "Visibility", render: (a) => a.visibility },
    {
      key: "installs",
      header: "Installs",
      align: "right",
      render: (a) => a.install_count,
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (a) => (
        <>
          <button onClick={() => handleOpen(a)} style={actionButtonStyle}>
            Open
          </button>
          <button
            onClick={() => handleExport(a)}
            disabled={!a.current_version_id}
            title={a.current_version_id ? undefined : "No saved version to export yet"}
            style={{
              ...actionButtonStyle,
              opacity: a.current_version_id ? 1 : 0.5,
              cursor: a.current_version_id ? "pointer" : "not-allowed",
            }}
          >
            Export
          </button>
          <button
            onClick={() => handleDelete(a)}
            style={{ ...actionButtonStyle, color: "var(--af-state-danger)" }}
          >
            Delete
          </button>
        </>
      ),
    },
  ];

  if (!token) {
    return <div style={pageStyle}>Enter a JWT token above to view your agents.</div>;
  }

  if (loading) {
    return (
      <div style={pageStyle}>
        <Skeleton height={32} style={{ marginBottom: space.sm }} />
        <Skeleton height={32} style={{ marginBottom: space.sm }} />
        <Skeleton height={32} />
      </div>
    );
  }

  if (loadError) {
    return (
      <div style={pageStyle}>
        <EmptyState
          message={`Failed to load your agents: ${loadError}`}
          action={
            <button onClick={load} style={retryButtonStyle}>
              Retry
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div style={pageStyle}>
      <h2 style={{ marginTop: 0, fontSize: typeScale.lg }}>My agents</h2>

      {actionError && (
        <div
          style={{
            color: "var(--af-state-danger)",
            fontSize: typeScale.sm,
            marginBottom: space.md,
          }}
        >
          {actionError}
        </div>
      )}

      {agents.length === 0 ? (
        <EmptyState
          message="No agents yet — create one in the builder."
          action={<Link to="/">Back to the builder</Link>}
        />
      ) : (
        <DataTable columns={columns} rows={agents} getRowKey={(a) => a.id} />
      )}
    </div>
  );
}

const retryButtonStyle = {
  background: colors.accent,
  border: "none",
  borderRadius: radius.sm,
  padding: "6px 14px",
  color: "#fff",
  cursor: "pointer",
  fontSize: typeScale.sm,
};
