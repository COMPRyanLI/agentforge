import { describe, expect, it } from "vitest";
import type { GraphJson } from "./graph";
import { toGraphJson } from "./graph";
import { graphJsonToReactFlow } from "./graphToFlow";

const CALCULATOR_ASSISTANT: GraphJson = {
  nodes: [
    { id: "in", type: "input", data: {} },
    {
      id: "llm1",
      type: "llm",
      data: {
        system_prompt: "Always call the calculator tool for arithmetic.",
        tools: ["calculator"],
      },
    },
    { id: "out", type: "output", data: {} },
  ],
  edges: [
    { source: "in", target: "llm1" },
    { source: "llm1", target: "out" },
  ],
};

const TRIAGE_ROUTER: GraphJson = {
  nodes: [
    { id: "in", type: "input", data: {} },
    { id: "classify", type: "llm", data: { system_prompt: "Classify as URGENT/NORMAL.", tools: [] } },
    { id: "route", type: "condition", data: { expr: "'URGENT' in output" } },
    { id: "urgent", type: "llm", data: { system_prompt: "Escalate immediately.", tools: [] } },
    { id: "normal", type: "llm", data: { system_prompt: "Respond helpfully.", tools: [] } },
    { id: "out", type: "output", data: {} },
  ],
  edges: [
    { source: "in", target: "classify" },
    { source: "classify", target: "route" },
    { source: "route", target: "urgent", condition: "true" },
    { source: "route", target: "normal", condition: "false" },
    { source: "urgent", target: "out" },
    { source: "normal", target: "out" },
  ],
};

const ITERATIVE_REFINER: GraphJson = {
  nodes: [
    { id: "in", type: "input", data: {} },
    { id: "loop", type: "loop", data: { expr: "step_index >= 0", max_iterations: 3 } },
    { id: "llm1", type: "llm", data: { system_prompt: "Refine the previous answer.", tools: [] } },
    { id: "out", type: "output", data: {} },
  ],
  edges: [
    { source: "in", target: "loop" },
    { source: "loop", target: "llm1", condition: "true" },
    { source: "loop", target: "out", condition: "false" },
    { source: "llm1", target: "loop" },
  ],
};

describe("graphJsonToReactFlow", () => {
  it("preserves a calculator-assistant llm node's tools", () => {
    const { nodes } = graphJsonToReactFlow(CALCULATOR_ASSISTANT);
    const llm = nodes.find((n) => n.id === "llm1");
    expect(llm?.data.tools).toEqual(["calculator"]);
  });

  it("mounts all 6 triage-router nodes with true/false sourceHandles on the condition's edges", () => {
    const { nodes, edges } = graphJsonToReactFlow(TRIAGE_ROUTER);
    expect(nodes).toHaveLength(6);
    expect(
      nodes.every((n) => Number.isFinite(n.position.x) && Number.isFinite(n.position.y))
    ).toBe(true);

    const trueEdge = edges.find((e) => e.source === "route" && e.target === "urgent");
    const falseEdge = edges.find((e) => e.source === "route" && e.target === "normal");
    expect(trueEdge?.sourceHandle).toBe("true");
    expect(falseEdge?.sourceHandle).toBe("false");
  });

  it("mounts the condition node's expr so its config panel isn't empty", () => {
    const { nodes } = graphJsonToReactFlow(TRIAGE_ROUTER);
    const route = nodes.find((n) => n.id === "route");
    expect(route?.data.expr).toBe("'URGENT' in output");
  });

  it("mounts the iterative refiner's loop node with its max_iterations and expr", () => {
    const { nodes } = graphJsonToReactFlow(ITERATIVE_REFINER);
    const loop = nodes.find((n) => n.id === "loop");
    expect(loop?.type).toBe("loop");
    expect(loop?.data.max_iterations).toBe(3);
    expect(loop?.data.expr).toBe("step_index >= 0");
  });

  it("throws on an unmapped node type instead of silently dropping it", () => {
    const graph = {
      nodes: [{ id: "x", type: "mystery" }],
      edges: [],
    } as unknown as GraphJson;
    expect(() => graphJsonToReactFlow(graph)).toThrow(/mystery/);
  });

  it("round-trips the triage router graph through load then save unchanged", () => {
    const { nodes, edges } = graphJsonToReactFlow(TRIAGE_ROUTER);
    const roundTripped = toGraphJson(nodes, edges);
    expect(roundTripped).toEqual(TRIAGE_ROUTER);
  });
});
