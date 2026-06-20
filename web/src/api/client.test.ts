import { afterEach, describe, expect, it, vi } from "vitest";
import { authHeaders, checkOk, setUnauthorizedHandler } from "./client";

function mockResponse(status: number, body = ""): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(body),
  } as Response;
}

describe("authHeaders", () => {
  it("builds the standard bearer + content-type headers", () => {
    expect(authHeaders("tok")).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer tok",
    });
  });
});

describe("checkOk", () => {
  afterEach(() => setUnauthorizedHandler(null));

  it("resolves with the response on a 2xx status", async () => {
    const resp = mockResponse(200);
    await expect(checkOk(resp, "test")).resolves.toBe(resp);
  });

  it("throws a labeled error on a non-ok status", async () => {
    const resp = mockResponse(404, "not found");
    await expect(checkOk(resp, "getThing")).rejects.toThrow(/getThing failed 404/);
  });

  it("invokes the registered unauthorized handler on 401", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const resp = mockResponse(401, "nope");
    await expect(checkOk(resp, "test")).rejects.toThrow();
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not invoke the handler for non-401 statuses", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    await checkOk(mockResponse(200), "test");
    expect(handler).not.toHaveBeenCalled();
  });

  it("does nothing if no handler is registered", async () => {
    setUnauthorizedHandler(null);
    await expect(checkOk(mockResponse(401, "nope"), "test")).rejects.toThrow();
  });
});
