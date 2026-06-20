import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Timeline, type TimelineItem } from "./Timeline";

afterEach(cleanup);

const items: TimelineItem[] = [
  {
    id: "1",
    color: "#4ade80",
    icon: "▶",
    title: "node_start",
    nodeId: "llm1",
    timestamp: "2024-01-01T12:00:00Z",
    payload: {},
  },
  {
    id: "2",
    color: "#60a5fa",
    icon: "💬",
    title: "llm_result",
    nodeId: "llm1",
    timestamp: "2024-01-01T12:00:01Z",
    badges: [{ label: "tokens", value: "12/34" }],
    payload: { content_preview: "hi" },
  },
];

describe("Timeline", () => {
  it("renders each item's title and node id", () => {
    render(<Timeline items={items} />);
    expect(screen.getByText(/node_start/)).toBeInTheDocument();
    expect(screen.getByText(/llm_result/)).toBeInTheDocument();
    expect(screen.getAllByText("llm1")).toHaveLength(2);
  });

  it("renders badges when provided", () => {
    render(<Timeline items={items} />);
    expect(screen.getByText("tokens: 12/34")).toBeInTheDocument();
  });

  it("does not render a payload disclosure for an empty payload", () => {
    render(<Timeline items={[items[0]]} />);
    expect(screen.queryByText(/show payload/i)).not.toBeInTheDocument();
  });

  it("expands the payload JSON when clicked", () => {
    render(<Timeline items={[items[1]]} />);
    const toggle = screen.getByRole("button", { name: /show payload/i });
    fireEvent.click(toggle);
    expect(screen.getByText(/content_preview/)).toBeInTheDocument();
  });

  it("renders nothing for an empty item list", () => {
    const { container } = render(<Timeline items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
