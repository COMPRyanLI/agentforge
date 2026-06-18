import type { NodeProps } from "@xyflow/react";
import { NodeShell } from "./NodeShell";

export function LoopNode({ data }: NodeProps) {
  const expr = typeof data.expr === "string" && data.expr ? data.expr : "no expr set";
  const maxIterations = typeof data.max_iterations === "number" ? data.max_iterations : "?";
  return (
    <NodeShell
      color="#9333ea"
      background="#2e1065"
      label="Loop"
      subtitle={`${expr} (max ${maxIterations})`}
      sourceHandles="branching"
    />
  );
}
