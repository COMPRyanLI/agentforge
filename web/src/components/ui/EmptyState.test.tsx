import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { EmptyState } from "./EmptyState";

afterEach(cleanup);

describe("EmptyState", () => {
  it("renders the message", () => {
    render(<EmptyState message="No runs yet" />);
    expect(screen.getByText("No runs yet")).toBeInTheDocument();
  });

  it("renders an optional action", () => {
    render(<EmptyState message="No runs yet" action={<a href="/">Back to builder</a>} />);
    expect(screen.getByRole("link", { name: /back to builder/i })).toBeInTheDocument();
  });
});
