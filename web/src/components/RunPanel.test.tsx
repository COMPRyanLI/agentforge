import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunEvent } from "../api/runs";
import { RunPanel } from "./RunPanel";

const { getRun, startRun, streamRunEvents } = vi.hoisted(() => ({
  getRun: vi.fn(),
  startRun: vi.fn(),
  streamRunEvents: vi.fn(),
}));

vi.mock("../api/runs", () => ({ getRun, startRun, streamRunEvents }));

// jsdom doesn't implement scrollIntoView; RunPanel calls it on every log line.
Element.prototype.scrollIntoView = vi.fn();

const FULL_OUTPUT =
  "This is the full, untruncated answer that is much longer than any preview field would allow.";

function renderPanel(): void {
  render(<RunPanel token="tok" agentId="agent1" disabledReason={null} />);
}

async function clickTest(): Promise<void> {
  fireEvent.change(screen.getByPlaceholderText(/input message/i), {
    target: { value: "hello" },
  });
  fireEvent.click(screen.getByRole("button", { name: /test/i }));
}

describe("RunPanel completion handling", () => {
  let closeSpy: ReturnType<typeof vi.fn>;
  let onEvent: (e: RunEvent) => void;
  let onDone: (status: string) => void;

  beforeEach(() => {
    closeSpy = vi.fn();
    startRun.mockResolvedValue({ run_id: "run1", status: "pending" });
    streamRunEvents.mockImplementation(
      (_runId: string, _token: string, evCb: (e: RunEvent) => void, doneCb: (s: string) => void) => {
        onEvent = evCb;
        onDone = doneCb;
        return closeSpy;
      }
    );
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("flips out of Running and shows the FULL output (not a preview) on the done event", async () => {
    getRun.mockResolvedValue({
      id: "run1",
      status: "succeeded",
      output_json: { output: FULL_OUTPUT },
      error_json: null,
    });

    renderPanel();
    await clickTest();

    expect(screen.getByRole("button", { name: /running/i })).toBeInTheDocument();

    onDone("succeeded");

    await waitFor(() => expect(screen.getByText(/▶ test/i)).toBeInTheDocument());
    expect(screen.getByText(/succeeded/i)).toBeInTheDocument();
    expect(screen.getByText(FULL_OUTPUT)).toBeInTheDocument();
    expect(closeSpy).toHaveBeenCalled();
  });

  it("finalizes from the [out] node_end event even if the done frame never arrives", async () => {
    getRun.mockResolvedValue({
      id: "run1",
      status: "succeeded",
      output_json: { output: FULL_OUTPUT },
      error_json: null,
    });

    renderPanel();
    await clickTest();

    onEvent({
      run_id: "run1",
      step_index: 1,
      node_id: "out",
      event_type: "node_end",
      payload: { output_preview: FULL_OUTPUT.slice(0, 20) },
      ts: new Date().toISOString(),
    });

    await waitFor(() => expect(screen.getByText(/▶ test/i)).toBeInTheDocument());
    expect(screen.getByText(FULL_OUTPUT)).toBeInTheDocument();
    expect(closeSpy).toHaveBeenCalled();
  });

  it("flips to FAILED and shows the error when the run fails", async () => {
    getRun.mockResolvedValue({
      id: "run1",
      status: "failed",
      output_json: null,
      error_json: { error: "tool exploded" },
    });

    renderPanel();
    await clickTest();

    onDone("failed");

    await waitFor(() => expect(screen.getByText(/failed/i)).toBeInTheDocument());
    expect(screen.getByText("tool exploded")).toBeInTheDocument();
  });

  it("flips to INTERRUPTED on a paused run", async () => {
    getRun.mockResolvedValue({
      id: "run1",
      status: "interrupted",
      output_json: null,
      error_json: null,
    });

    renderPanel();
    await clickTest();

    onDone("interrupted");

    await waitFor(() => expect(screen.getByText(/interrupted/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /▶ test/i })).toBeInTheDocument();
  });

  it("offers a Create one now action when there's no agent yet", () => {
    const onCreateAgent = vi.fn();
    render(
      <RunPanel
        token="tok"
        agentId=""
        disabledReason="Create an agent first."
        onCreateAgent={onCreateAgent}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /create one now/i }));
    expect(onCreateAgent).toHaveBeenCalledTimes(1);
  });

  it("still stops Running on a done event even if the GET /runs/{id} follow-up fails", async () => {
    getRun.mockRejectedValue(new Error("network error"));

    renderPanel();
    await clickTest();

    onDone("succeeded");

    await waitFor(() => expect(screen.getByText(/▶ test/i)).toBeInTheDocument());
    expect(screen.getByText(/succeeded/i)).toBeInTheDocument();
  });
});
