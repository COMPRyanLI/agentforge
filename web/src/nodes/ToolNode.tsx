import type { NodeProps } from "@xyflow/react";
import { NodeShell } from "./NodeShell";

export function ToolNode({ data }: NodeProps) {
  const toolId = typeof data.tool_id === "string" ? data.tool_id : undefined;
  return (
    <NodeShell
      color="#0891b2"
      background="#083344"
      label="Tool"
      subtitle={toolId ? `tool: ${toolId.slice(0, 8)}…` : "no tool selected"}
    />
  );
}
