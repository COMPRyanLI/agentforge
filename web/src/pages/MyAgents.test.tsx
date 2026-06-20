import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as agentsApi from "../api/agents";
import { AuthContext } from "../auth/AuthContext";
import { mockAuthValue } from "../auth/testAuth";
import { MyAgents } from "./MyAgents";

afterEach(cleanup);

function renderPage(token = "test-token") {
  return render(
    <AuthContext.Provider value={mockAuthValue(token)}>
      <MemoryRouter initialEntries={["/agents"]}>
        <Routes>
          <Route path="/agents" element={<MyAgents />} />
          <Route path="/" element={<div>builder page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

const AGENT: agentsApi.AgentRead = {
  id: "agent-1",
  owner_id: "u1",
  name: "Research Assistant",
  description: null,
  current_version_id: "v1",
  visibility: "private",
  install_count: 0,
  avg_rating: null,
  created_at: "2024-01-01T00:00:00Z",
};

describe("MyAgents", () => {
  it("shows a loading state before data arrives", () => {
    vi.spyOn(agentsApi, "listAgents").mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("shows an empty state with a link back to the builder when there are no agents", async () => {
    vi.spyOn(agentsApi, "listAgents").mockResolvedValue([]);
    renderPage();
    await waitFor(() => expect(screen.getByText(/no agents yet/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /builder/i })).toHaveAttribute("href", "/");
  });

  it("renders a row per agent with Open, Export, and Delete actions", async () => {
    vi.spyOn(agentsApi, "listAgents").mockResolvedValue([AGENT]);
    renderPage();
    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /open/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /delete/i })).toBeInTheDocument();
  });

  it("disables Export for an agent with no saved version", async () => {
    vi.spyOn(agentsApi, "listAgents").mockResolvedValue([
      { ...AGENT, current_version_id: null },
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /export/i })).toBeDisabled();
  });

  it("shows an error state with a retry option on failure", async () => {
    vi.spyOn(agentsApi, "listAgents").mockRejectedValue(new Error("network down"));
    renderPage();
    await waitFor(() => expect(screen.getByText(/network down/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("exports the agent's current version as a downloaded JSON file", async () => {
    vi.spyOn(agentsApi, "listAgents").mockResolvedValue([AGENT]);
    vi.spyOn(agentsApi, "getCurrentVersion").mockResolvedValue({
      id: "v1",
      agent_id: "agent-1",
      version_number: 3,
      graph_json: { nodes: [], edges: [] },
      created_at: "2024-01-01T00:00:00Z",
    });

    const createObjectURL = vi.fn().mockReturnValue("blob:fake-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    const blobParts: BlobPart[][] = [];
    class FakeBlob {
      constructor(parts: BlobPart[]) {
        blobParts.push(parts);
      }
    }
    vi.stubGlobal("Blob", FakeBlob);
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = originalCreateElement(tag);
      if (tag === "a") el.click = clickSpy;
      return el;
    });

    renderPage();
    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /export/i }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
    expect(blobParts).toHaveLength(1);
    const text = blobParts[0][0] as string;
    const parsed = JSON.parse(text);
    expect(parsed).toEqual({
      name: "Research Assistant",
      version_number: 3,
      graph_json: { nodes: [], edges: [] },
    });
    expect(clickSpy).toHaveBeenCalledTimes(1);

    vi.unstubAllGlobals();
  });

  it("deletes the agent and removes it from the list after confirming", async () => {
    vi.spyOn(agentsApi, "listAgents").mockResolvedValue([AGENT]);
    const deleteAgent = vi.spyOn(agentsApi, "deleteAgent").mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage();
    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteAgent).toHaveBeenCalledWith("agent-1", "test-token"));
    await waitFor(() =>
      expect(screen.queryByText("Research Assistant")).not.toBeInTheDocument()
    );
  });

  it("does not delete when the confirmation is declined", async () => {
    vi.spyOn(agentsApi, "listAgents").mockResolvedValue([AGENT]);
    const deleteAgent = vi.spyOn(agentsApi, "deleteAgent");
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderPage();
    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /delete/i }));

    expect(deleteAgent).not.toHaveBeenCalled();
    expect(screen.getByText("Research Assistant")).toBeInTheDocument();
  });

  it("navigates to the builder when Open is clicked", async () => {
    vi.spyOn(agentsApi, "listAgents").mockResolvedValue([AGENT]);
    renderPage();
    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /open/i }));
    await waitFor(() => expect(screen.getByText("builder page")).toBeInTheDocument());
  });

  it("shows an inline error (without hiding the list) when export fails", async () => {
    vi.spyOn(agentsApi, "listAgents").mockResolvedValue([AGENT]);
    vi.spyOn(agentsApi, "getCurrentVersion").mockRejectedValue(
      new Error("getCurrentVersion failed 404: Agent has no saved version")
    );

    renderPage();
    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /export/i }));

    await waitFor(() => expect(screen.getByText(/no saved version/i)).toBeInTheDocument());
    // The list itself must still be visible — an action failure isn't a load failure.
    expect(screen.getByText("Research Assistant")).toBeInTheDocument();
  });

  it("shows an inline error (without hiding the list) when delete is rejected", async () => {
    vi.spyOn(agentsApi, "listAgents").mockResolvedValue([AGENT]);
    vi.spyOn(agentsApi, "deleteAgent").mockRejectedValue(
      new Error("deleteAgent failed 403: Not your agent")
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage();
    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(screen.getByText(/not your agent/i)).toBeInTheDocument());
    expect(screen.getByText("Research Assistant")).toBeInTheDocument();
  });
});
