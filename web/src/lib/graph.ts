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
