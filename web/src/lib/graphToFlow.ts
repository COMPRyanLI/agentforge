import type { Edge, Node } from "@xyflow/react";
import type { GraphJson, NodeType } from "./graph";
import { layoutPositions } from "./layout";

const KNOWN_NODE_TYPES: ReadonlySet<string> = new Set<NodeType>([
  "input",
  "llm",
  "tool",
  "condition",
  "loop",
  "output",
]);

/** Converts a persisted graph_json into React Flow state for the builder
 * canvas. Used whenever an agent is opened from a template/install clone or
 * an existing draft — graph_json is the only source of truth for node/edge
 * shape, so nothing here may fall back to a default skeleton. */
export function graphJsonToReactFlow(graph: GraphJson): { nodes: Node[]; edges: Edge[] } {
  const unmapped = graph.nodes.filter((n) => !KNOWN_NODE_TYPES.has(n.type));
  if (unmapped.length > 0) {
    throw new Error(
      `Unsupported node type(s) in loaded graph: ${unmapped
        .map((n) => `${n.id} (${n.type})`)
        .join(", ")}`
    );
  }

  const positions = layoutPositions(graph.nodes, graph.edges);
  const nodes: Node[] = graph.nodes.map((n) => ({
    id: n.id,
    type: n.type,
    position: positions[n.id] ?? { x: 0, y: 0 },
    data: { ...(n.data ?? {}) },
  }));

  const edges: Edge[] = graph.edges.map((e, i) => ({
    id: `e${i}-${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    ...(e.condition ? { sourceHandle: e.condition } : {}),
  }));

  return { nodes, edges };
}
