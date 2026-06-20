import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as authApi from "../api/auth";
import * as client from "../api/client";
import { AuthProvider, useAuth } from "./AuthContext";

const USER = { id: "u1", email: "alice@example.com", created_at: "2024-01-01T00:00:00Z" };

function Probe() {
  const { token, user, loading, login, register, logout } = useAuth();
  return (
    <div>
      <div data-testid="loading">{String(loading)}</div>
      <div data-testid="token">{token}</div>
      <div data-testid="email">{user?.email ?? "none"}</div>
      <button onClick={() => void login("alice@example.com", "password123")}>login</button>
      <button onClick={() => void register("alice@example.com", "password123")}>register</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

afterEach(cleanup);

describe("AuthProvider", () => {
  it("starts logged out with no token in localStorage", async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    expect(screen.getByTestId("token").textContent).toBe("");
    expect(screen.getByTestId("email").textContent).toBe("none");
  });

  it("login stores the token (in state and localStorage) and fetches the user", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue({ access_token: "tok123", token_type: "bearer" });
    vi.spyOn(authApi, "getMe").mockResolvedValue(USER);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

    screen.getByText("login").click();

    await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("alice@example.com"));
    expect(screen.getByTestId("token").textContent).toBe("tok123");
    expect(localStorage.getItem("agentforge_token")).toBe("tok123");
  });

  it("register stores the token and fetches the user", async () => {
    vi.spyOn(authApi, "register").mockResolvedValue({
      access_token: "tok456",
      token_type: "bearer",
    });
    vi.spyOn(authApi, "getMe").mockResolvedValue(USER);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

    screen.getByText("register").click();

    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("tok456"));
  });

  it("logout clears the token, user, and localStorage", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue({ access_token: "tok123", token_type: "bearer" });
    vi.spyOn(authApi, "getMe").mockResolvedValue(USER);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    screen.getByText("login").click();
    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("tok123"));

    screen.getByText("logout").click();

    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe(""));
    expect(screen.getByTestId("email").textContent).toBe("none");
    expect(localStorage.getItem("agentforge_token")).toBeNull();
  });

  it("rehydrates the user from a token already in localStorage on mount", async () => {
    localStorage.setItem("agentforge_token", "persisted-tok");
    vi.spyOn(authApi, "getMe").mockResolvedValue(USER);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("alice@example.com"));
    expect(screen.getByTestId("token").textContent).toBe("persisted-tok");
  });

  it("clears an invalid persisted token instead of staying logged in", async () => {
    localStorage.setItem("agentforge_token", "stale-tok");
    vi.spyOn(authApi, "getMe").mockRejectedValue(new Error("getMe failed 401"));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    expect(screen.getByTestId("token").textContent).toBe("");
    expect(localStorage.getItem("agentforge_token")).toBeNull();
  });

  it("registers a 401 handler with the shared api client that logs the user out", async () => {
    const setHandlerSpy = vi.spyOn(client, "setUnauthorizedHandler");
    vi.spyOn(authApi, "login").mockResolvedValue({ access_token: "tok123", token_type: "bearer" });
    vi.spyOn(authApi, "getMe").mockResolvedValue(USER);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    screen.getByText("login").click();
    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("tok123"));

    // The most recent non-null registration is the live handler — invoking it
    // simulates any api/*.ts call hitting a 401 and should log the user out.
    const registeredHandler = setHandlerSpy.mock.calls
      .map((call) => call[0])
      .filter((fn): fn is () => void => fn !== null)
      .at(-1);
    expect(registeredHandler).toBeTypeOf("function");
    registeredHandler?.();

    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe(""));
    expect(screen.getByTestId("email").textContent).toBe("none");
  });
});
