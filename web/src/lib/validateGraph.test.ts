import { describe, expect, it } from "vitest";
import type { GraphJson } from "./graph";
import { validateGraph } from "./validateGraph";

function graph(overrides: Partial<GraphJson>): GraphJson {
  return { nodes: [], edges: [], ...overrides };
}

describe("validateGraph", () => {
  it("accepts a minimal valid graph", () => {
    const g = graph({
      nodes: [
        { id: "in", type: "input" },
        { id: "out", type: "output" },
      ],
      edges: [{ source: "in", target: "out" }],
    });
    expect(validateGraph(g)).toEqual([]);
  });

  it("rejects an empty graph", () => {
    expect(validateGraph(graph({}))).toEqual(["Graph has no nodes."]);
  });

  it("requires exactly one input node", () => {
    const g = graph({
      nodes: [
        { id: "in1", type: "input" },
        { id: "in2", type: "input" },
        { id: "out", type: "output" },
      ],
      edges: [],
    });
    expect(validateGraph(g).some((e) => e.includes("exactly one input"))).toBe(true);
  });

  it("requires exactly one output node", () => {
    const g = graph({ nodes: [{ id: "in", type: "input" }], edges: [] });
    expect(validateGraph(g).some((e) => e.includes("exactly one output"))).toBe(true);
  });

  it("flags an edge referencing an unknown node", () => {
    const g = graph({
      nodes: [
        { id: "in", type: "input" },
        { id: "out", type: "output" },
      ],
      edges: [{ source: "in", target: "ghost" }],
    });
    expect(validateGraph(g).some((e) => e.includes("unknown target"))).toBe(true);
  });

  it("flags an orphan node with no incoming edge", () => {
    const g = graph({
      nodes: [
        { id: "in", type: "input" },
        { id: "llm1", type: "llm" },
        { id: "out", type: "output" },
      ],
      edges: [{ source: "in", target: "out" }],
    });
    expect(validateGraph(g).some((e) => e.includes("llm1") && e.includes("incoming"))).toBe(true);
  });

  it("flags a non-branching node with more than one outgoing edge", () => {
    const g = graph({
      nodes: [
        { id: "in", type: "input" },
        { id: "out1", type: "output" },
      ],
      edges: [
        { source: "in", target: "out1" },
        { source: "in", target: "out1" },
      ],
    });
    // duplicate edge still counts as 2 outgoing edges from 'in'
    expect(validateGraph(g).some((e) => e.includes("only condition/loop"))).toBe(true);
  });

  it("requires a condition node to have exactly one true and one false edge", () => {
    const g = graph({
      nodes: [
        { id: "in", type: "input" },
        { id: "cond", type: "condition", data: { expr: "step_index == 0" } },
        { id: "out", type: "output" },
      ],
      edges: [
        { source: "in", target: "cond" },
        { source: "cond", target: "out" },
      ],
    });
    expect(validateGraph(g).some((e) => e.includes("true' and one 'false'"))).toBe(true);
  });

  it("accepts a well-formed condition graph", () => {
    const g = graph({
      nodes: [
        { id: "in", type: "input" },
        { id: "cond", type: "condition", data: { expr: "step_index == 0" } },
        { id: "t1", type: "tool", data: { tool_id: "x" } },
        { id: "out", type: "output" },
      ],
      edges: [
        { source: "in", target: "cond" },
        { source: "cond", target: "t1", condition: "true" },
        { source: "cond", target: "out", condition: "false" },
        { source: "t1", target: "out" },
      ],
    });
    expect(validateGraph(g)).toEqual([]);
  });

  it("requires a loop node to declare numeric max_iterations", () => {
    const g = graph({
      nodes: [
        { id: "in", type: "input" },
        { id: "loop", type: "loop", data: { expr: "step_index >= 0" } },
        { id: "llm1", type: "llm" },
        { id: "out", type: "output" },
      ],
      edges: [
        { source: "in", target: "loop" },
        { source: "loop", target: "llm1", condition: "true" },
        { source: "loop", target: "out", condition: "false" },
        { source: "llm1", target: "loop" },
      ],
    });
    expect(validateGraph(g).some((e) => e.includes("max_iterations"))).toBe(true);
  });

  it("accepts a well-formed loop graph", () => {
    const g = graph({
      nodes: [
        { id: "in", type: "input" },
        { id: "loop", type: "loop", data: { expr: "step_index >= 0", max_iterations: 3 } },
        { id: "llm1", type: "llm" },
        { id: "out", type: "output" },
      ],
      edges: [
        { source: "in", target: "loop" },
        { source: "loop", target: "llm1", condition: "true" },
        { source: "loop", target: "out", condition: "false" },
        { source: "llm1", target: "loop" },
      ],
    });
    expect(validateGraph(g)).toEqual([]);
  });

  it("rejects a cycle that does not pass through a loop node", () => {
    const g = graph({
      nodes: [
        { id: "in", type: "input" },
        { id: "cond", type: "condition", data: { expr: "step_index < 3" } },
        { id: "out", type: "output" },
      ],
      edges: [
        { source: "in", target: "cond" },
        { source: "cond", target: "in", condition: "true" },
        { source: "cond", target: "out", condition: "false" },
      ],
    });
    expect(validateGraph(g).some((e) => e.includes("does not pass through a loop node"))).toBe(
      true
    );
  });
});
