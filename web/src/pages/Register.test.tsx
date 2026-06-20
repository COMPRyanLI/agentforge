import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/AuthContext";
import { mockAuthValue } from "../auth/testAuth";
import { Register } from "./Register";

afterEach(cleanup);

function renderRegister(register = vi.fn()) {
  const authValue = { ...mockAuthValue(""), register };
  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter initialEntries={["/register"]}>
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/" element={<div>builder page</div>} />
          <Route path="/login" element={<div>login page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

function fillAndSubmit(email: string, password: string) {
  fireEvent.change(screen.getByLabelText(/email/i), { target: { value: email } });
  fireEvent.change(screen.getByLabelText(/password/i), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: /^register$|create account/i }));
}

describe("Register", () => {
  it("renders email and password fields and a link to login", () => {
    renderRegister();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /log in/i })).toBeInTheDocument();
  });

  it("shows a validation error for an invalid email without calling register", () => {
    const register = vi.fn();
    renderRegister(register);
    fillAndSubmit("not-an-email", "password123");
    expect(screen.getByText(/valid email/i)).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });

  it("shows a validation error for a too-short password without calling register", () => {
    const register = vi.fn();
    renderRegister(register);
    fillAndSubmit("alice@example.com", "short");
    expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });

  it("registers and redirects to the builder on success", async () => {
    const register = vi.fn().mockResolvedValue(undefined);
    renderRegister(register);
    fillAndSubmit("alice@example.com", "password123");
    expect(register).toHaveBeenCalledWith("alice@example.com", "password123");
    await waitFor(() => expect(screen.getByText("builder page")).toBeInTheDocument());
  });

  it("shows an error message and stays on the page when registration fails", async () => {
    const register = vi.fn().mockRejectedValue(new Error("register failed 400: Email already registered"));
    renderRegister(register);
    fillAndSubmit("dup@example.com", "password123");
    await waitFor(() =>
      expect(screen.getByText(/could not create account|already registered/i)).toBeInTheDocument()
    );
  });
});
