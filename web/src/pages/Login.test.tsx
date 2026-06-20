import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/AuthContext";
import { mockAuthValue } from "../auth/testAuth";
import { Login } from "./Login";

afterEach(cleanup);

function renderLogin(login = vi.fn(), initialEntries: string[] = ["/login"]) {
  const authValue = { ...mockAuthValue(""), login };
  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<div>builder page</div>} />
          <Route path="/protected" element={<div>protected page</div>} />
          <Route path="/register" element={<div>register page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

function fillAndSubmit(email: string, password: string) {
  fireEvent.change(screen.getByLabelText(/email/i), { target: { value: email } });
  fireEvent.change(screen.getByLabelText(/password/i), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: /log in/i }));
}

describe("Login", () => {
  it("renders email and password fields and a link to register", () => {
    renderLogin();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /register/i })).toBeInTheDocument();
  });

  it("shows a validation error for an invalid email without calling login", () => {
    const login = vi.fn();
    renderLogin(login);
    fillAndSubmit("not-an-email", "password123");
    expect(screen.getByText(/valid email/i)).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("shows a validation error for a too-short password without calling login", () => {
    const login = vi.fn();
    renderLogin(login);
    fillAndSubmit("alice@example.com", "short");
    expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("logs in and redirects to the builder on success", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    renderLogin(login);
    fillAndSubmit("alice@example.com", "password123");
    expect(login).toHaveBeenCalledWith("alice@example.com", "password123");
    await waitFor(() => expect(screen.getByText("builder page")).toBeInTheDocument());
  });

  it("redirects back to the originally requested page after login", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    render(
      <AuthContext.Provider value={{ ...mockAuthValue(""), login }}>
        <MemoryRouter
          initialEntries={[{ pathname: "/login", state: { from: { pathname: "/protected" } } }]}
        >
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/protected" element={<div>protected page</div>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    );
    fillAndSubmit("alice@example.com", "password123");
    await waitFor(() => expect(screen.getByText("protected page")).toBeInTheDocument());
  });

  it("shows an error message and stays on the page when login fails", async () => {
    const login = vi.fn().mockRejectedValue(new Error("login failed 401: bad creds"));
    renderLogin(login);
    fillAndSubmit("alice@example.com", "wrongpassword");
    await waitFor(() => expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument());
  });
});
