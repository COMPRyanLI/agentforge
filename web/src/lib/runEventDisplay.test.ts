import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/runs";
import { eventColor, eventIcon, toTimelineItem } from "./runEventDisplay";

describe("eventIcon / eventColor", () => {
  it("returns a known icon and color for a known event type", () => {
    expect(eventIcon("llm_result")).toBe("💬");
    expect(eventColor("llm_result")).toBe("#4ade80");
  });

  it("falls back gracefully for an unknown event type", () => {
    expect(eventIcon("some_future_event")).toBe("•");
    expect(eventColor("some_future_event")).toBe("#94a3b8");
  });
});

describe("toTimelineItem", () => {
  it("surfaces token and latency badges for an llm_result event", () => {
    const event: RunEvent = {
      run_id: "r1",
      step_index: 0,
      node_id: "llm1",
      event_type: "llm_result",
      payload: { prompt_tokens: 10, completion_tokens: 20, total_duration_ms: 123.6 },
      ts: "2024-01-01T00:00:00Z",
    };
    const item = toTimelineItem(event, 0);
    expect(item.badges).toEqual([
      { label: "tokens", value: "10 in / 20 out" },
      { label: "latency", value: "124ms" },
    ]);
  });

  it("omits badges when an llm_result event carries no usage data", () => {
    const event: RunEvent = {
      run_id: "r1",
      step_index: 0,
      node_id: "llm1",
      event_type: "llm_result",
      payload: { content_preview: "hi" },
      ts: "2024-01-01T00:00:00Z",
    };
    const item = toTimelineItem(event, 0);
    expect(item.badges).toEqual([]);
  });

  it("does not attach badges for non-llm_result events", () => {
    const event: RunEvent = {
      run_id: "r1",
      step_index: 0,
      node_id: "in",
      event_type: "node_start",
      payload: {},
      ts: "2024-01-01T00:00:00Z",
    };
    const item = toTimelineItem(event, 0);
    expect(item.badges).toEqual([]);
  });
});
