import type { Edge, Node } from "@xyflow/react";

export type NodeType = "input" | "llm" | "tool" | "condition" | "loop" | "output";

export const BRANCHING_NODE_TYPES: ReadonlySet<NodeType> = new Set(["condition", "loop"]);

export interface GraphNodeJson {
  id: string;
  type: NodeType;
  data?: Record<string, unknown>;
}

export interface GraphEdgeJson {
  source: string;
  target: string;
  condition?: "true" | "false";
}

export interface GraphJson {
  nodes: GraphNodeJson[];
  edges: GraphEdgeJson[];
}

/** Inverse of graphJsonToReactFlow (lib/graphToFlow.ts) — converts builder
 * canvas state back into the persisted graph_json shape. Reads back the
 * same sourceHandle/condition convention NodeShell's branching handles
 * write (web/src/nodes/NodeShell.tsx). */
export function toGraphJson(nodes: Node[], edges: Edge[]): GraphJson {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type as NodeType,
      data: n.data as Record<string, unknown>,
    })),
    edges: edges.map((e) => ({
      source: e.source,
      target: e.target,
      ...(e.sourceHandle === "true" || e.sourceHandle === "false"
        ? { condition: e.sourceHandle }
        : {}),
    })),
  };
}
