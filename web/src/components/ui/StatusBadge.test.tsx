import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

afterEach(cleanup);

describe("StatusBadge", () => {
  it("renders a known status", () => {
    render(<StatusBadge status="succeeded" />);
    expect(screen.getByText(/succeeded/i)).toBeInTheDocument();
  });

  it("falls back gracefully for an unknown status", () => {
    render(<StatusBadge status="some_future_status" />);
    expect(screen.getByText(/some_future_status/i)).toBeInTheDocument();
  });
});
