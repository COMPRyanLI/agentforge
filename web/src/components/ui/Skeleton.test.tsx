import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Skeleton } from "./Skeleton";

afterEach(cleanup);

describe("Skeleton", () => {
  it("renders a status role for accessibility", () => {
    render(<Skeleton />);
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
  });

  it("reserves the given height to avoid layout shift", () => {
    render(<Skeleton height={32} />);
    const el = screen.getByRole("status");
    expect(el).toHaveStyle({ height: "32px" });
  });
});
