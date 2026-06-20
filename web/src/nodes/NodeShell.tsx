import { Handle, Position } from "@xyflow/react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface NodeShellProps {
  /** Lucide icon component rendered inside the small type-accent chip. */
  icon: LucideIcon;
  /** Desaturated per-type accent (one of the --af-node-* tokens) — used only
   * for the icon chip, never as the card's border or fill. */
  accent: string;
  label: string;
  subtitle?: ReactNode;
  showTarget?: boolean;
  /** Either a single unconditional source handle, or two labeled
   * "true"/"false" handles for branching nodes (condition/loop). */
  sourceHandles?: "single" | "branching" | "none";
  children?: ReactNode;
}

export function NodeShell({
  icon: Icon,
  accent,
  label,
  subtitle,
  showTarget = true,
  sourceHandles = "single",
  children,
}: NodeShellProps) {
  return (
    <div
      style={{
        padding: "10px 12px",
        borderRadius: "var(--af-radius-lg)",
        border: "1px solid var(--af-border)",
        background: "var(--af-bg-surface)",
        color: "var(--af-text)",
        fontFamily: "var(--af-font-sans)",
        fontSize: 13,
        minWidth: 160,
        position: "relative",
      }}
    >
      {showTarget && <Handle type="target" position={Position.Left} />}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 22,
            height: 22,
            borderRadius: "var(--af-radius-sm)",
            background: `${accent}26`,
            color: accent,
            flexShrink: 0,
          }}
        >
          <Icon size={13} strokeWidth={2} />
        </span>
        <div style={{ fontWeight: 600, textAlign: "left" }}>{label}</div>
      </div>
      {subtitle && (
        <div
          style={{
            fontSize: 11,
            color: "var(--af-text-muted)",
            marginTop: 6,
            textAlign: "left",
          }}
        >
          {subtitle}
        </div>
      )}
      {children}
      {sourceHandles === "single" && <Handle type="source" position={Position.Right} />}
      {sourceHandles === "branching" && (
        <>
          <Handle
            type="source"
            position={Position.Right}
            id="true"
            style={{ top: "35%", background: "var(--af-state-true)" }}
          />
          <Handle
            type="source"
            position={Position.Right}
            id="false"
            style={{ top: "65%", background: "var(--af-state-false)" }}
          />
          <div style={{ fontSize: 10, color: "var(--af-text-faint)", marginTop: 6, textAlign: "left" }}>
            true ↘ / false ↘
          </div>
        </>
      )}
    </div>
  );
}
