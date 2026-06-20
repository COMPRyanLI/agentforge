import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as runsApi from "../api/runs";
import { AuthContext } from "../auth/AuthContext";
import { mockAuthValue } from "../auth/testAuth";
import { RunTimeline } from "./RunTimeline";

afterEach(cleanup);

function renderAt(runId: string, token = "test-token") {
  return render(
    <AuthContext.Provider value={mockAuthValue(token)}>
      <MemoryRouter initialEntries={[`/runs/${runId}/timeline`]}>
        <Routes>
          <Route path="/runs/:runId/timeline" element={<RunTimeline />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

const BASE_RUN: runsApi.RunRead = {
  id: "run-1",
  agent_id: "agent-1",
  status: "succeeded",
  output_json: { output: "done" },
  error_json: null,
  started_at: "2024-01-01T12:00:00Z",
  ended_at: "2024-01-01T12:00:05Z",
};

describe("RunTimeline", () => {
  it("shows a loading state before data arrives", () => {
    vi.spyOn(runsApi, "getRun").mockReturnValue(new Promise(() => {}));
    vi.spyOn(runsApi, "getRunTimeline").mockReturnValue(new Promise(() => {}));
    renderAt("run-1");
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("renders the run summary header and event timeline", async () => {
    vi.spyOn(runsApi, "getRun").mockResolvedValue(BASE_RUN);
    vi.spyOn(runsApi, "getRunTimeline").mockResolvedValue([
      {
        run_id: "run-1",
        step_index: 0,
        node_id: "llm1",
        event_type: "llm_result",
        payload: { prompt_tokens: 5, completion_tokens: 9 },
        ts: "2024-01-01T12:00:01Z",
      },
    ]);

    renderAt("run-1");

    await waitFor(() => expect(screen.getByText(/succeeded/i)).toBeInTheDocument());
    expect(screen.getByText(/llm_result/)).toBeInTheDocument();
    expect(screen.getAllByText(/5 in \/ 9 out/).length).toBeGreaterThan(0);
  });

  it("shows an empty state when a run has no events", async () => {
    vi.spyOn(runsApi, "getRun").mockResolvedValue(BASE_RUN);
    vi.spyOn(runsApi, "getRunTimeline").mockResolvedValue([]);

    renderAt("run-1");

    await waitFor(() => expect(screen.getByText(/no events/i)).toBeInTheDocument());
  });

  it("shows an error state with a retry option on failure", async () => {
    vi.spyOn(runsApi, "getRun").mockRejectedValue(new Error("boom"));
    vi.spyOn(runsApi, "getRunTimeline").mockResolvedValue([]);

    renderAt("run-1");

    await waitFor(() => expect(screen.getByText(/boom/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
