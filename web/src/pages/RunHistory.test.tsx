import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as runsApi from "../api/runs";
import { AuthContext } from "../auth/AuthContext";
import { RunHistory } from "./RunHistory";

afterEach(cleanup);

function renderAt(agentId: string, token = "test-token") {
  return render(
    <AuthContext.Provider value={{ token, setToken: vi.fn() }}>
      <MemoryRouter initialEntries={[`/agents/${agentId}/runs`]}>
        <Routes>
          <Route path="/agents/:agentId/runs" element={<RunHistory />} />
          <Route path="/runs/:runId/timeline" element={<div>timeline page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

const EMPTY_STATS: runsApi.AgentRunStats = {
  total_runs: 0,
  in_progress_count: 0,
  success_rate: null,
  p95_latency_ms: null,
  avg_prompt_tokens: null,
  avg_completion_tokens: null,
  avg_steps_per_run: null,
};

describe("RunHistory", () => {
  it("shows a loading state before data arrives", () => {
    vi.spyOn(runsApi, "listAgentRuns").mockReturnValue(new Promise(() => {}));
    vi.spyOn(runsApi, "getAgentRunStats").mockReturnValue(new Promise(() => {}));
    renderAt("agent-1");
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("shows an empty state with a link back to the builder when there are no runs", async () => {
    vi.spyOn(runsApi, "listAgentRuns").mockResolvedValue([]);
    vi.spyOn(runsApi, "getAgentRunStats").mockResolvedValue(EMPTY_STATS);

    renderAt("agent-1");

    await waitFor(() => expect(screen.getByText(/no runs yet/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /builder/i })).toHaveAttribute("href", "/");
  });

  it("renders stat cards and a row per run, with a working link to its timeline", async () => {
    vi.spyOn(runsApi, "listAgentRuns").mockResolvedValue([
      {
        id: "run-1",
        agent_id: "agent-1",
        status: "succeeded",
        output_json: { output: "ok" },
        error_json: null,
        started_at: "2024-01-01T12:00:00Z",
        ended_at: "2024-01-01T12:00:05Z",
      },
    ]);
    vi.spyOn(runsApi, "getAgentRunStats").mockResolvedValue({
      total_runs: 1,
      in_progress_count: 0,
      success_rate: 1,
      p95_latency_ms: 5000,
      avg_prompt_tokens: 10,
      avg_completion_tokens: 20,
      avg_steps_per_run: 2,
    });

    renderAt("agent-1");

    await waitFor(() => expect(screen.getByText(/100%/)).toBeInTheDocument());
    // p95 latency stat card and the row's duration column both render "5000ms"
    // for this fixture — assert both occurrences are present rather than just one.
    expect(screen.getAllByText("5000ms")).toHaveLength(2);

    const link = screen.getByRole("link", { name: /run-1|succeeded/i });
    fireEvent.click(link);
    expect(await screen.findByText("timeline page")).toBeInTheDocument();
  });

  it("shows an error state with a retry option on failure", async () => {
    vi.spyOn(runsApi, "listAgentRuns").mockRejectedValue(new Error("network down"));
    vi.spyOn(runsApi, "getAgentRunStats").mockResolvedValue(EMPTY_STATS);

    renderAt("agent-1");

    await waitFor(() => expect(screen.getByText(/network down/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
