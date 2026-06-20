import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import type { RunEvent, RunRead } from "../api/runs";
import { getRun, getRunTimeline } from "../api/runs";
import { useAuth } from "../auth/AuthContext";
import { EmptyState } from "../components/ui/EmptyState";
import { Skeleton } from "../components/ui/Skeleton";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Timeline } from "../components/ui/Timeline";
import { colors, fontFamily, radius, space, typeScale } from "../components/ui/tokens";
import { toTimelineItem } from "../lib/runEventDisplay";

const pageStyle = {
  padding: space.xl,
  color: colors.text,
  background: "var(--af-bg-canvas)",
  fontFamily,
  height: "100%",
  overflow: "auto",
};

function durationMs(run: RunRead): number | null {
  if (!run.started_at || !run.ended_at) return null;
  return new Date(run.ended_at).getTime() - new Date(run.started_at).getTime();
}

function totalTokens(events: RunEvent[]): { prompt: number | null; completion: number | null } {
  let prompt: number | null = null;
  let completion: number | null = null;
  for (const e of events) {
    if (e.event_type !== "llm_result") continue;
    const p = e.payload as { prompt_tokens?: number | null; completion_tokens?: number | null };
    if (typeof p.prompt_tokens === "number") prompt = (prompt ?? 0) + p.prompt_tokens;
    if (typeof p.completion_tokens === "number") completion = (completion ?? 0) + p.completion_tokens;
  }
  return { prompt, completion };
}

export function RunTimeline() {
  const { runId } = useParams<{ runId: string }>();
  const { token } = useAuth();
  const [run, setRun] = useState<RunRead | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!runId || !token) return;
    setLoading(true);
    setError(null);
    Promise.all([getRun(runId, token), getRunTimeline(runId, token)])
      .then(([runData, eventData]) => {
        setRun(runData);
        setEvents(eventData);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [runId, token]);

  useEffect(() => {
    load();
  }, [load]);

  if (!token) {
    return <div style={pageStyle}>Enter a JWT token above to view this run.</div>;
  }

  if (loading) {
    return (
      <div style={pageStyle}>
        <Skeleton height={48} style={{ marginBottom: space.lg }} />
        <Skeleton height={20} style={{ marginBottom: space.sm }} />
        <Skeleton height={20} style={{ marginBottom: space.sm }} />
        <Skeleton height={20} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={pageStyle}>
        <EmptyState
          message={`Failed to load this run: ${error}`}
          action={
            <button onClick={load} style={retryButtonStyle}>
              Retry
            </button>
          }
        />
      </div>
    );
  }

  if (!run) return null;

  const duration = durationMs(run);
  const { prompt, completion } = totalTokens(events);

  return (
    <div style={pageStyle}>
      <div
        style={{
          position: "sticky",
          top: 0,
          background: colors.bg,
          paddingBottom: space.md,
          marginBottom: space.lg,
          borderBottom: `1px solid ${colors.border}`,
          display: "flex",
          alignItems: "center",
          gap: space.md,
          flexWrap: "wrap",
        }}
      >
        <h2 style={{ margin: 0, fontSize: typeScale.lg }}>Run {run.id.slice(0, 8)}</h2>
        <StatusBadge status={run.status} />
        <span style={{ color: colors.textMuted, fontSize: typeScale.sm }}>
          {duration !== null ? `${duration}ms` : "—"} · {events.length} steps · {prompt ?? "—"} in
          / {completion ?? "—"} out tokens
        </span>
      </div>

      {events.length === 0 ? (
        <EmptyState message="No events recorded for this run." />
      ) : (
        <Timeline items={events.map((e, i) => toTimelineItem(e, i))} />
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
