import { Handle, Position, type NodeProps } from "@xyflow/react";

/** Minimal custom node. Phase 5 expands this into a configurable LLM node
 * (system prompt, model, tool selection) plus tool/condition/loop nodes. */
export function LLMNode({ data }: NodeProps) {
  const label = typeof data.label === "string" ? data.label : undefined;
  return (
    <div
      style={{
        padding: "10px 14px",
        borderRadius: 10,
        border: "1px solid #4f46e5",
        background: "#1e1b4b",
        color: "#e0e7ff",
        fontFamily: "system-ui, sans-serif",
        fontSize: 13,
        minWidth: 120,
        textAlign: "center",
      }}
    >
      <Handle type="target" position={Position.Left} />
      {label ?? "LLM"}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
