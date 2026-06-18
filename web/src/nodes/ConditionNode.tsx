import type { NodeProps } from "@xyflow/react";
import { NodeShell } from "./NodeShell";

export function ConditionNode({ data }: NodeProps) {
  const expr = typeof data.expr === "string" && data.expr ? data.expr : "no expr set";
  return (
    <NodeShell
      color="#d97706"
      background="#451a03"
      label="Condition"
      subtitle={expr}
      sourceHandles="branching"
    />
  );
}
