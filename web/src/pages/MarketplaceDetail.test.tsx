import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as marketplaceApi from "../api/marketplace";
import { AuthContext } from "../auth/AuthContext";
import { mockAuthValue } from "../auth/testAuth";
import { MarketplaceDetail } from "./MarketplaceDetail";

function renderDetail(agentId: string, token: string) {
  return render(
    <AuthContext.Provider value={mockAuthValue(token)}>
      <MemoryRouter initialEntries={[`/marketplace/${agentId}`]}>
        <Routes>
          <Route path="/marketplace/:agentId" element={<MarketplaceDetail />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe("MarketplaceDetail", () => {
  it("prompts for a token when none is set", () => {
    renderDetail("agent-1", "");
    expect(screen.getByText(/enter a jwt token/i)).toBeInTheDocument();
  });

  it("renders agent details and ratings from the API", async () => {
    vi.spyOn(marketplaceApi, "getMarketplaceAgent").mockResolvedValue({
      id: "agent-1",
      owner_id: "owner-1",
      name: "Research Assistant",
      description: "Summarizes topics.",
      install_count: 2,
      avg_rating: 4.0,
      created_at: new Date().toISOString(),
    });
    vi.spyOn(marketplaceApi, "listRatings").mockResolvedValue([
      {
        id: "rating-1",
        agent_id: "agent-1",
        user_id: "user-1",
        score: 4,
        comment: "Pretty good",
        created_at: new Date().toISOString(),
      },
    ]);

    renderDetail("agent-1", "test-token");

    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    expect(screen.getByText("Pretty good")).toBeInTheDocument();
  });
});
