import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as marketplaceApi from "../api/marketplace";
import { AuthContext } from "../auth/AuthContext";
import { mockAuthValue } from "../auth/testAuth";
import { MarketplaceList } from "./MarketplaceList";

function renderWithToken(token: string) {
  return render(
    <AuthContext.Provider value={mockAuthValue(token)}>
      <MemoryRouter>
        <MarketplaceList />
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe("MarketplaceList", () => {
  it("prompts for a token when none is set", () => {
    renderWithToken("");
    expect(screen.getByText(/enter a jwt token/i)).toBeInTheDocument();
  });

  it("renders published agents from the API", async () => {
    vi.spyOn(marketplaceApi, "listMarketplace").mockResolvedValue([
      {
        id: "agent-1",
        owner_id: "owner-1",
        name: "Research Assistant",
        description: "Summarizes topics.",
        install_count: 3,
        avg_rating: 4.5,
        created_at: new Date().toISOString(),
      },
    ]);

    renderWithToken("test-token");

    await waitFor(() => expect(screen.getByText("Research Assistant")).toBeInTheDocument());
    expect(screen.getByText(/3 installs/i)).toBeInTheDocument();
  });
});
