import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { AuthContext } from "./AuthContext";
import { RequireAuth } from "./RequireAuth";
import { mockAuthValue } from "./testAuth";

afterEach(cleanup);

function renderProtected(authValue: ReturnType<typeof mockAuthValue>) {
  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter initialEntries={["/protected"]}>
        <Routes>
          <Route
            path="/protected"
            element={
              <RequireAuth>
                <div>secret content</div>
              </RequireAuth>
            }
          />
          <Route path="/login" element={<div>login page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe("RequireAuth", () => {
  it("shows a loading state and renders neither children nor a redirect while loading", () => {
    renderProtected({ ...mockAuthValue(""), loading: true });
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
  });

  it("redirects to /login when there is no user", () => {
    renderProtected(mockAuthValue(""));
    expect(screen.getByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("renders children when a user is present", () => {
    renderProtected(mockAuthValue("tok"));
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });
});
