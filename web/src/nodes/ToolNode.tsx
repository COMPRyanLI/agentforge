import type { NodeProps } from "@xyflow/react";
import { Wrench } from "lucide-react";
import { NodeShell } from "./NodeShell";

export function ToolNode({ data }: NodeProps) {
  const toolId = typeof data.tool_id === "string" ? data.tool_id : undefined;
  return (
    <NodeShell
      icon={Wrench}
      accent="var(--af-node-tool)"
      label="Tool"
      subtitle={toolId ? `${toolId.slice(0, 8)}…` : "No tool selected"}
    />
  );
}
