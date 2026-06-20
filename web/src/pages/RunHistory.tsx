import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { AgentRunStats, RunRead } from "../api/runs";
import { getAgentRunStats, listAgentRuns } from "../api/runs";
import { useAuth } from "../auth/AuthContext";
import { DataTable, type DataTableColumn } from "../components/ui/DataTable";
import { EmptyState } from "../components/ui/EmptyState";
import { Skeleton } from "../components/ui/Skeleton";
import { StatCard } from "../components/ui/StatCard";
import { StatusBadge } from "../components/ui/StatusBadge";
import { colors, fontFamily, radius, space, typeScale } from "../components/ui/tokens";

const pageStyle = {
  padding: space.xl,
  color: colors.text,
  background: "var(--af-bg-canvas)",
  fontFamily,
  height: "100%",
  overflow: "auto",
};

function formatPercent(rate: number | null): string | null {
  return rate === null ? null : `${Math.round(rate * 100)}%`;
}

function formatMs(ms: number | null): string | null {
  return ms === null ? null : `${Math.round(ms)}ms`;
}

function formatAvgPair(a: number | null, b: number | null): string | null {
  if (a === null && b === null) return null;
  return `${a !== null ? a.toFixed(1) : "—"} / ${b !== null ? b.toFixed(1) : "—"}`;
}

function durationLabel(run: RunRead): string {
  if (!run.started_at || !run.ended_at) return "—";
  const ms = new Date(run.ended_at).getTime() - new Date(run.started_at).getTime();
  return `${ms}ms`;
}

const columns: DataTableColumn<RunRead>[] = [
  { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
  {
    key: "started_at",
    header: "Started",
    render: (r) =>
      r.started_at ? (
        <span title={new Date(r.started_at).toLocaleString()}>
          {new Date(r.started_at).toLocaleString()}
        </span>
      ) : (
        "—"
      ),
  },
  { key: "duration", header: "Duration", align: "right", render: (r) => durationLabel(r) },
  {
    key: "view",
    header: "",
    align: "right",
    render: (r) => (
      <Link to={`/runs/${r.id}/timeline`} style={{ color: colors.accent }}>
        View {r.id.slice(0, 8)}
      </Link>
    ),
  },
];

export function RunHistory() {
  const { agentId } = useParams<{ agentId: string }>();
  const { token } = useAuth();
  const [runs, setRuns] = useState<RunRead[]>([]);
  const [stats, setStats] = useState<AgentRunStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!agentId || !token) return;
    setLoading(true);
    setError(null);
    Promise.all([listAgentRuns(agentId, token), getAgentRunStats(agentId, token)])
      .then(([runData, statsData]) => {
        setRuns(runData);
        setStats(statsData);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [agentId, token]);

  useEffect(() => {
    load();
  }, [load]);

  if (!token) {
    return <div style={pageStyle}>Enter a JWT token above to view run history.</div>;
  }

  if (loading) {
    return (
      <div style={pageStyle}>
        <div style={{ display: "flex", gap: space.lg, marginBottom: space.xl }}>
          <Skeleton height={84} width={160} />
          <Skeleton height={84} width={160} />
          <Skeleton height={84} width={160} />
        </div>
        <Skeleton height={32} style={{ marginBottom: space.sm }} />
        <Skeleton height={32} style={{ marginBottom: space.sm }} />
        <Skeleton height={32} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={pageStyle}>
        <EmptyState
          message={`Failed to load run history: ${error}`}
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
      <h2 style={{ marginTop: 0, fontSize: typeScale.lg }}>Run History</h2>
      <div style={{ display: "flex", gap: space.lg, marginBottom: space.xl, flexWrap: "wrap" }}>
        <StatCard label="Success rate" value={formatPercent(stats?.success_rate ?? null)} />
        <StatCard label="p95 latency" value={formatMs(stats?.p95_latency_ms ?? null)} />
        <StatCard
          label="Avg tokens (in/out)"
          value={formatAvgPair(stats?.avg_prompt_tokens ?? null, stats?.avg_completion_tokens ?? null)}
          hint={
            stats?.avg_steps_per_run !== null && stats?.avg_steps_per_run !== undefined
              ? `${stats.avg_steps_per_run.toFixed(1)} steps/run`
              : undefined
          }
        />
      </div>

      {runs.length === 0 ? (
        <EmptyState
          message="No runs yet — run this agent to see history."
          action={<Link to="/">Back to the builder</Link>}
        />
      ) : (
        <DataTable columns={columns} rows={runs} getRowKey={(r) => r.id} />
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
