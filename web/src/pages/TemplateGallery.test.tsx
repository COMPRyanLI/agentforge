import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as templatesApi from "../api/templates";
import { AuthContext } from "../auth/AuthContext";
import { mockAuthValue } from "../auth/testAuth";
import { TemplateGallery } from "./TemplateGallery";

function renderWithToken(token: string) {
  return render(
    <AuthContext.Provider value={mockAuthValue(token)}>
      <MemoryRouter>
        <TemplateGallery />
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe("TemplateGallery", () => {
  it("prompts for a token when none is set", () => {
    renderWithToken("");
    expect(screen.getByText(/enter a jwt token/i)).toBeInTheDocument();
  });

  it("renders templates from the API", async () => {
    vi.spyOn(templatesApi, "listTemplates").mockResolvedValue([
      {
        id: "template-1",
        name: "Research Assistant",
        description: "Summarizes topics.",
        category: "research",
        graph_json: { nodes: [], edges: [] },
        created_at: new Date().toISOString(),
      },
    ]);

    renderWithToken("test-token");

    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    expect(screen.getByText("Use this template")).toBeInTheDocument();
  });
});
