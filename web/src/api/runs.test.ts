import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunEvent } from "./runs";
import { getAgentRunStats, getRunTimeline, listAgentRuns, streamRunEvents } from "./runs";

class FakeEventSource {
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();

  emit(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

describe("streamRunEvents", () => {
  let fakeES: FakeEventSource;

  beforeEach(() => {
    fakeES = new FakeEventSource();
    vi.stubGlobal(
      "EventSource",
      vi.fn(() => fakeES)
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("forwards node events to onEvent without treating them as terminal", () => {
    const onEvent = vi.fn();
    const onDone = vi.fn();
    streamRunEvents("run1", "tok", onEvent, onDone);

    const nodeEvent: RunEvent = {
      run_id: "run1",
      step_index: 1,
      node_id: "llm1",
      event_type: "node_end",
      payload: {},
      ts: "2026-06-19T00:00:00Z",
    };
    fakeES.emit(nodeEvent);

    expect(onEvent).toHaveBeenCalledWith(nodeEvent);
    expect(onDone).not.toHaveBeenCalled();
    expect(fakeES.close).not.toHaveBeenCalled();
  });

  it.each(["succeeded", "failed", "interrupted"])(
    "on a terminal done event (%s) calls onDone with the final status and closes the stream",
    (status) => {
      const onEvent = vi.fn();
      const onDone = vi.fn();
      streamRunEvents("run1", "tok", onEvent, onDone);

      fakeES.emit({ type: "done", status });

      expect(onDone).toHaveBeenCalledWith(status);
      expect(onDone).toHaveBeenCalledTimes(1);
      expect(fakeES.close).toHaveBeenCalledTimes(1);
      expect(onEvent).not.toHaveBeenCalled();
    }
  );

  it("does not call onEvent for the done frame, only onDone", () => {
    const onEvent = vi.fn();
    const onDone = vi.fn();
    streamRunEvents("run1", "tok", onEvent, onDone);

    fakeES.emit({
      run_id: "run1",
      step_index: 2,
      node_id: "out",
      event_type: "node_end",
      payload: {},
      ts: "2026-06-19T00:00:01Z",
    });
    fakeES.emit({ type: "done", status: "succeeded" });

    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledWith("succeeded");
    expect(fakeES.close).toHaveBeenCalledTimes(1);
  });
});

function mockFetchOnce(body: unknown, ok = true, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok,
      status,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    })
  );
}

describe("listAgentRuns", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the parsed run list", async () => {
    mockFetchOnce([{ id: "r1", status: "succeeded" }]);
    const runs = await listAgentRuns("agent1", "tok");
    expect(runs).toEqual([{ id: "r1", status: "succeeded" }]);
  });

  it("throws on a non-ok response", async () => {
    mockFetchOnce({}, false, 403);
    await expect(listAgentRuns("agent1", "tok")).rejects.toThrow(/403/);
  });
});

describe("getRunTimeline", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the parsed event list", async () => {
    const events = [{ run_id: "r1", step_index: 0, node_id: "in", event_type: "node_start", payload: {}, ts: "t" }];
    mockFetchOnce(events);
    const result = await getRunTimeline("r1", "tok");
    expect(result).toEqual(events);
  });
});

describe("getAgentRunStats", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the parsed stats including null fields as-is", async () => {
    const stats = {
      total_runs: 0,
      in_progress_count: 0,
      success_rate: null,
      p95_latency_ms: null,
      avg_prompt_tokens: null,
      avg_completion_tokens: null,
      avg_steps_per_run: null,
    };
    mockFetchOnce(stats);
    const result = await getAgentRunStats("agent1", "tok");
    expect(result).toEqual(stats);
  });
});
