import type { DragEvent } from "react";
import type { NodeType } from "../lib/graph";

const PALETTE_ITEMS: { type: NodeType; label: string }[] = [
  { type: "input", label: "Input" },
  { type: "llm", label: "LLM" },
  { type: "tool", label: "Tool" },
  { type: "condition", label: "Condition" },
  { type: "loop", label: "Loop" },
  { type: "output", label: "Output" },
];

export const NODE_DRAG_MIME = "application/agentforge-node-type";

export function Palette() {
  const onDragStart = (event: DragEvent<HTMLDivElement>, nodeType: NodeType) => {
    event.dataTransfer.setData(NODE_DRAG_MIME, nodeType);
    event.dataTransfer.effectAllowed = "move";
  };

  return (
    <div
      style={{
        width: 140,
        padding: 12,
        borderRight: "1px solid #1e293b",
        background: "#0f172a",
        color: "#e2e8f0",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: 8, textTransform: "uppercase" }}>
        Node Palette
      </div>
      {PALETTE_ITEMS.map(({ type, label }) => (
        <div
          key={type}
          draggable
          onDragStart={(e) => onDragStart(e, type)}
          style={{
            padding: "8px 10px",
            marginBottom: 6,
            borderRadius: 6,
            border: "1px solid #334155",
            background: "#1e293b",
            fontSize: 12,
            cursor: "grab",
          }}
        >
          {label}
        </div>
      ))}
    </div>
  );
}
