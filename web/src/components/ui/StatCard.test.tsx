import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StatCard } from "./StatCard";

afterEach(cleanup);

describe("StatCard", () => {
  it("renders a numeric value with its label", () => {
    render(<StatCard label="Success rate" value="92%" />);
    expect(screen.getByText("Success rate")).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();
  });

  it("renders an em dash for null value rather than coercing to 0", () => {
    render(<StatCard label="p95 latency" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("renders an optional hint", () => {
    render(<StatCard label="Avg tokens" value={42} hint="per run" />);
    expect(screen.getByText("per run")).toBeInTheDocument();
  });
});
