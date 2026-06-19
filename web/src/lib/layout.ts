import type { GraphEdgeJson, GraphNodeJson } from "./graph";

const COLUMN_WIDTH = 240;
const ROW_HEIGHT = 140;
const ORIGIN_X = 60;
const ORIGIN_Y = 60;

/** Assigns left-to-right grid positions from BFS depth over the edge graph,
 * for graphs whose nodes carry no position (e.g. seeded templates) — without
 * this, every loaded node would render stacked at React Flow's origin. */
export function layoutPositions(
  nodes: GraphNodeJson[],
  edges: GraphEdgeJson[]
): Record<string, { x: number; y: number }> {
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    const list = adjacency.get(edge.source) ?? [];
    list.push(edge.target);
    adjacency.set(edge.source, list);
  }

  const depth = new Map<string, number>();
  const roots = nodes.filter((n) => n.type === "input").map((n) => n.id);
  const queue: string[] = roots.length > 0 ? roots : nodes.slice(0, 1).map((n) => n.id);
  for (const id of queue) depth.set(id, 0);

  while (queue.length > 0) {
    const id = queue.shift();
    if (id === undefined) break;
    const d = depth.get(id) ?? 0;
    for (const next of adjacency.get(id) ?? []) {
      if (!depth.has(next)) {
        depth.set(next, d + 1);
        queue.push(next);
      }
    }
  }

  // Any node unreachable from the root (shouldn't happen in a validated
  // graph, but stay defensive so it gets finite coordinates instead of
  // disappearing) is placed in its own column after the deepest reached node.
  const reachedDepths = Array.from(depth.values());
  let nextFallbackDepth = (reachedDepths.length > 0 ? Math.max(...reachedDepths) : 0) + 1;
  for (const node of nodes) {
    if (!depth.has(node.id)) {
      depth.set(node.id, nextFallbackDepth++);
    }
  }

  const countAtDepth = new Map<number, number>();
  const positions: Record<string, { x: number; y: number }> = {};
  for (const node of nodes) {
    const d = depth.get(node.id) ?? 0;
    const row = countAtDepth.get(d) ?? 0;
    countAtDepth.set(d, row + 1);
    positions[node.id] = { x: ORIGIN_X + d * COLUMN_WIDTH, y: ORIGIN_Y + row * ROW_HEIGHT };
  }
  return positions;
}
