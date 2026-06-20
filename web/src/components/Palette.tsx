import { Bot, GitBranch, LogIn, LogOut, Repeat, Wrench, type LucideIcon } from "lucide-react";
import type { DragEvent } from "react";
import type { NodeType } from "../lib/graph";

const PALETTE_ITEMS: { type: NodeType; label: string; icon: LucideIcon; accent: string }[] = [
  { type: "input", label: "Input", icon: LogIn, accent: "var(--af-node-input)" },
  { type: "llm", label: "LLM", icon: Bot, accent: "var(--af-node-llm)" },
  { type: "tool", label: "Tool", icon: Wrench, accent: "var(--af-node-tool)" },
  { type: "condition", label: "Condition", icon: GitBranch, accent: "var(--af-node-condition)" },
  { type: "loop", label: "Loop", icon: Repeat, accent: "var(--af-node-loop)" },
  { type: "output", label: "Output", icon: LogOut, accent: "var(--af-node-output)" },
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
        width: 168,
        padding: 12,
        borderRight: "1px solid var(--af-border)",
        background: "var(--af-bg-surface)",
        color: "var(--af-text)",
        fontFamily: "var(--af-font-sans)",
      }}
    >
      <div
        style={{
          color: "var(--af-text-muted)",
          fontSize: 11,
          marginBottom: 8,
          fontWeight: 600,
        }}
      >
        Node palette
      </div>
      {PALETTE_ITEMS.map(({ type, label, icon: Icon, accent }) => (
        <div
          key={type}
          draggable
          onDragStart={(e) => onDragStart(e, type)}
          className="af-palette-item"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "7px 10px",
            marginBottom: 6,
            borderRadius: "var(--af-radius-md)",
            border: "1px solid var(--af-border)",
            background: "var(--af-bg-surface-raised)",
            fontSize: 12,
            cursor: "grab",
          }}
        >
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 18,
              height: 18,
              borderRadius: "var(--af-radius-sm)",
              background: `${accent}26`,
              color: accent,
              flexShrink: 0,
            }}
          >
            <Icon size={11} strokeWidth={2} />
          </span>
          {label}
        </div>
      ))}
    </div>
  );
}
