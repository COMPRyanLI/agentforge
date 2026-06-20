import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/AuthContext";
import { mockAuthValue } from "../auth/testAuth";
import { AccountMenu } from "./AccountMenu";

afterEach(cleanup);

function renderMenu(token = "tok", overrides: Partial<ReturnType<typeof mockAuthValue>> = {}) {
  const value = { ...mockAuthValue(token), ...overrides };
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter>
        <AccountMenu />
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe("AccountMenu", () => {
  it("renders nothing when there is no logged-in user", () => {
    const { container } = renderMenu("", { user: null });
    expect(container).toBeEmptyDOMElement();
  });

  it("shows initials derived from the user's email on the avatar button", () => {
    renderMenu("tok", { user: { id: "u1", email: "alice@example.com", created_at: "" } });
    expect(screen.getByRole("button", { name: /account menu/i })).toHaveTextContent("AL");
  });

  it("opens to show the email, a My agents link, and a Logout button", () => {
    renderMenu("tok", { user: { id: "u1", email: "alice@example.com", created_at: "" } });
    fireEvent.click(screen.getByRole("button", { name: /account menu/i }));

    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /my agents/i })).toHaveAttribute("href", "/agents");
    expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
  });

  it("calls logout when the Logout button is clicked", () => {
    const logout = vi.fn();
    renderMenu("tok", {
      user: { id: "u1", email: "alice@example.com", created_at: "" },
      logout,
    });
    fireEvent.click(screen.getByRole("button", { name: /account menu/i }));
    fireEvent.click(screen.getByRole("button", { name: /logout/i }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("closes the dropdown when clicking outside it", () => {
    renderMenu("tok", { user: { id: "u1", email: "alice@example.com", created_at: "" } });
    fireEvent.click(screen.getByRole("button", { name: /account menu/i }));
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();

    fireEvent.mouseDown(document.body);

    expect(screen.queryByText("alice@example.com")).not.toBeInTheDocument();
  });
});
