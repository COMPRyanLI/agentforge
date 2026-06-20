import type { RunEvent } from "../api/runs";
import type { TimelineItem } from "../components/ui/Timeline";

// Shared between RunPanel's live SSE log and RunTimeline's static event
// history view, so both render the same icon/color per event_type.
export const EVENT_ICONS: Record<string, string> = {
  node_start: "▶",
  node_end: "■",
  llm_call: "🤖",
  llm_result: "💬",
  tool_call: "🔧",
  tool_result: "✅",
  error: "❌",
  retry: "🔄",
  interrupt: "⏸",
  resume: "▶",
};

export const EVENT_COLORS: Record<string, string> = {
  node_start: "#94a3b8",
  node_end: "#64748b",
  llm_call: "#60a5fa",
  llm_result: "#4ade80",
  tool_call: "#a78bfa",
  tool_result: "#4ade80",
  error: "#f87171",
  retry: "#fbbf24",
  interrupt: "#fbbf24",
  resume: "#60a5fa",
};

export function eventIcon(eventType: string): string {
  return EVENT_ICONS[eventType] ?? "•";
}

export function eventColor(eventType: string): string {
  return EVENT_COLORS[eventType] ?? "#94a3b8";
}

/** Builds a Timeline-primitive item from a persisted run event, surfacing
 * token/latency usage (when present on an llm_result event) as badges. */
export function toTimelineItem(event: RunEvent, index: number): TimelineItem {
  const badges: { label: string; value: string }[] = [];
  if (event.event_type === "llm_result") {
    const { prompt_tokens, completion_tokens, total_duration_ms } = event.payload as {
      prompt_tokens?: number | null;
      completion_tokens?: number | null;
      total_duration_ms?: number | null;
    };
    if (prompt_tokens != null || completion_tokens != null) {
      badges.push({
        label: "tokens",
        value: `${prompt_tokens ?? "—"} in / ${completion_tokens ?? "—"} out`,
      });
    }
    if (total_duration_ms != null) {
      badges.push({ label: "latency", value: `${Math.round(total_duration_ms)}ms` });
    }
  }
  return {
    id: `${event.step_index}-${event.node_id}-${index}`,
    color: eventColor(event.event_type),
    icon: eventIcon(event.event_type),
    title: event.event_type,
    nodeId: event.node_id,
    timestamp: event.ts,
    badges,
    payload: event.payload,
  };
}
