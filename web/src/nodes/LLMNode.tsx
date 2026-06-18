import type { NodeProps } from "@xyflow/react";
import { NodeShell } from "./NodeShell";

export function LLMNode({ data }: NodeProps) {
  const tools = Array.isArray(data.tools) ? (data.tools as string[]) : [];
  const subtitle = tools.length > 0 ? `tools: ${tools.join(", ")}` : "no tools";
  return <NodeShell color="#4f46e5" background="#1e1b4b" label="LLM" subtitle={subtitle} />;
}
