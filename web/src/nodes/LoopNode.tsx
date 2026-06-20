import type { NodeProps } from "@xyflow/react";
import { Repeat } from "lucide-react";
import { NodeShell } from "./NodeShell";

export function LoopNode({ data }: NodeProps) {
  const expr = typeof data.expr === "string" && data.expr ? data.expr : "No expression set";
  const maxIterations = typeof data.max_iterations === "number" ? data.max_iterations : "?";
  return (
    <NodeShell
      icon={Repeat}
      accent="var(--af-node-loop)"
      label="Loop"
      subtitle={`${expr} (max ${maxIterations})`}
      sourceHandles="branching"
    />
  );
}
