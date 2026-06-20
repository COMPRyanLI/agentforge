import type { NodeProps } from "@xyflow/react";
import { GitBranch } from "lucide-react";
import { NodeShell } from "./NodeShell";

export function ConditionNode({ data }: NodeProps) {
  const expr = typeof data.expr === "string" && data.expr ? data.expr : "No expression set";
  return (
    <NodeShell
      icon={GitBranch}
      accent="var(--af-node-condition)"
      label="Condition"
      subtitle={expr}
      sourceHandles="branching"
    />
  );
}
