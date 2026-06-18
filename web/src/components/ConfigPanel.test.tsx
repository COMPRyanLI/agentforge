import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfigPanel } from "./ConfigPanel";

describe("ConfigPanel", () => {
  it("shows a placeholder when no node is selected", () => {
    render(<ConfigPanel node={null} tools={[]} onChange={vi.fn()} />);
    expect(screen.getByText(/select a node/i)).toBeInTheDocument();
  });

  it("calls onChange with merged data when editing an llm node's system prompt", () => {
    const onChange = vi.fn();
    render(
      <ConfigPanel
        node={{ id: "llm1", type: "llm", data: { system_prompt: "old", tools: [] } }}
        tools={[]}
        onChange={onChange}
      />
    );

    const textarea = screen.getByDisplayValue("old");
    fireEvent.change(textarea, { target: { value: "new prompt" } });

    expect(onChange).toHaveBeenCalledWith("llm1", { system_prompt: "new prompt", tools: [] });
  });

  it("renders the expression field for a condition node", () => {
    const onChange = vi.fn();
    render(
      <ConfigPanel
        node={{ id: "cond1", type: "condition", data: { expr: "step_index == 0" } }}
        tools={[]}
        onChange={onChange}
      />
    );
    expect(screen.getByDisplayValue("step_index == 0")).toBeInTheDocument();
  });

  it("updates max_iterations as a number for a loop node", () => {
    const onChange = vi.fn();
    render(
      <ConfigPanel
        node={{ id: "loop1", type: "loop", data: { expr: "true", max_iterations: 3 } }}
        tools={[]}
        onChange={onChange}
      />
    );
    const input = screen.getByDisplayValue("3");
    fireEvent.change(input, { target: { value: "5" } });
    expect(onChange).toHaveBeenCalledWith("loop1", { expr: "true", max_iterations: 5 });
  });
});
