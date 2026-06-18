import { BRANCHING_NODE_TYPES, type GraphEdgeJson, type GraphJson } from "./graph";

/**
 * Client-side mirror of the backend's GraphCompiler validation
 * (backend/app/runtime/compiler.py) — catches the same errors before a
 * wasted round-trip to POST /agents/{id}/versions. The compiler is the real
 * enforcement boundary; this is UX only.
 */
export function validateGraph(graph: GraphJson): string[] {
  const errors: string[] = [];
  const { nodes, edges } = graph;

  if (nodes.length === 0) {
    return ["Graph has no nodes."];
  }

  const nodeIds = new Set(nodes.map((n) => n.id));
  const nodeTypeById = new Map(nodes.map((n) => [n.id, n.type]));

  const inputNodes = nodes.filter((n) => n.type === "input");
  const outputNodes = nodes.filter((n) => n.type === "output");
  if (inputNodes.length !== 1) {
    errors.push(`Graph must have exactly one input node (found ${inputNodes.length}).`);
  }
  if (outputNodes.length !== 1) {
    errors.push(`Graph must have exactly one output node (found ${outputNodes.length}).`);
  }

  for (const edge of edges) {
    if (!nodeIds.has(edge.source)) {
      errors.push(`Edge references unknown source node '${edge.source}'.`);
    }
    if (!nodeIds.has(edge.target)) {
      errors.push(`Edge references unknown target node '${edge.target}'.`);
    }
  }

  const edgesBySource = new Map<string, GraphEdgeJson[]>();
  for (const edge of edges) {
    const list = edgesBySource.get(edge.source) ?? [];
    list.push(edge);
    edgesBySource.set(edge.source, list);
  }

  const hasIncoming = new Set(edges.map((e) => e.target));
  const hasOutgoing = new Set(edges.map((e) => e.source));

  for (const node of nodes) {
    if (node.type !== "input" && !hasIncoming.has(node.id)) {
      errors.push(`Node '${node.id}' (${node.type}) has no incoming edge.`);
    }
    if (node.type !== "output" && !hasOutgoing.has(node.id)) {
      errors.push(`Node '${node.id}' (${node.type}) has no outgoing edge.`);
    }
  }

  for (const node of nodes) {
    const outgoing = edgesBySource.get(node.id) ?? [];
    if (BRANCHING_NODE_TYPES.has(node.type)) {
      const trueCount = outgoing.filter((e) => e.condition === "true").length;
      const falseCount = outgoing.filter((e) => e.condition === "false").length;
      const untagged = outgoing.filter((e) => e.condition !== "true" && e.condition !== "false");
      if (trueCount !== 1 || falseCount !== 1 || untagged.length > 0) {
        errors.push(
          `${node.type} node '${node.id}' must have exactly one 'true' and one 'false' outgoing edge.`
        );
      }
      if (node.type === "loop" && typeof node.data?.max_iterations !== "number") {
        errors.push(`loop node '${node.id}' must declare a numeric max_iterations.`);
      }
    } else if (outgoing.length > 1) {
      errors.push(
        `Node '${node.id}' (${node.type}) has ${outgoing.length} outgoing edges; only condition/loop nodes may branch.`
      );
    }
  }

  // Nested loops: an inner loop's iteration counter never resets across
  // outer iterations (see GraphCompiler._validate_no_nested_loops), so it
  // would silently run far fewer iterations than declared rather than
  // erroring. Reject at save time instead.
  function loopBodyMembers(loopId: string): Set<string> {
    const trueEdge = (edgesBySource.get(loopId) ?? []).find((e) => e.condition === "true");
    const members = new Set<string>();
    if (!trueEdge) return members;
    const stack = [trueEdge.target];
    while (stack.length > 0) {
      const id = stack.pop();
      if (id === undefined || members.has(id) || id === loopId) continue;
      members.add(id);
      for (const edge of edgesBySource.get(id) ?? []) {
        stack.push(edge.target);
      }
    }
    return members;
  }

  const loopIds = nodes.filter((n) => n.type === "loop").map((n) => n.id);
  for (const outer of loopIds) {
    const body = loopBodyMembers(outer);
    for (const inner of loopIds) {
      if (inner !== outer && body.has(inner)) {
        errors.push(
          `loop node '${inner}' is nested inside loop node '${outer}''s body — nested loops are not supported; flatten into a single loop.`
        );
      }
    }
  }

  // Cycle check: any cycle in the edge graph must pass through a loop node,
  // mirroring GraphCompiler._validate_no_unguarded_cycles.
  const visited = new Set<string>();
  const onStack: string[] = [];
  const onStackSet = new Set<string>();

  function dfs(nodeId: string): void {
    visited.add(nodeId);
    onStack.push(nodeId);
    onStackSet.add(nodeId);
    for (const edge of edgesBySource.get(nodeId) ?? []) {
      const target = edge.target;
      if (!nodeIds.has(target)) continue;
      if (onStackSet.has(target)) {
        const idx = onStack.indexOf(target);
        const cycleNodes = onStack.slice(idx);
        const hasLoopNode = cycleNodes.some((id) => nodeTypeById.get(id) === "loop");
        if (!hasLoopNode) {
          errors.push(`Cycle [${cycleNodes.join(" -> ")}] does not pass through a loop node.`);
        }
      } else if (!visited.has(target)) {
        dfs(target);
      }
    }
    onStack.pop();
    onStackSet.delete(nodeId);
  }

  for (const node of nodes) {
    if (!visited.has(node.id)) dfs(node.id);
  }

  return errors;
}
