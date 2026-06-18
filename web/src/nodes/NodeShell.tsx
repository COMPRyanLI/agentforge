import { Handle, Position } from "@xyflow/react";
import type { ReactNode } from "react";

interface NodeShellProps {
  color: string;
  background: string;
  label: string;
  subtitle?: string;
  showTarget?: boolean;
  /** Either a single unconditional source handle, or two labeled
   * "true"/"false" handles for branching nodes (condition/loop). */
  sourceHandles?: "single" | "branching" | "none";
  children?: ReactNode;
}

export function NodeShell({
  color,
  background,
  label,
  subtitle,
  showTarget = true,
  sourceHandles = "single",
  children,
}: NodeShellProps) {
  return (
    <div
      style={{
        padding: "10px 14px",
        borderRadius: 10,
        border: `1px solid ${color}`,
        background,
        color: "#e2e8f0",
        fontFamily: "system-ui, sans-serif",
        fontSize: 13,
        minWidth: 140,
        textAlign: "center",
        position: "relative",
      }}
    >
      {showTarget && <Handle type="target" position={Position.Left} />}
      <div style={{ fontWeight: 700 }}>{label}</div>
      {subtitle && (
        <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>{subtitle}</div>
      )}
      {children}
      {sourceHandles === "single" && <Handle type="source" position={Position.Right} />}
      {sourceHandles === "branching" && (
        <>
          <Handle
            type="source"
            position={Position.Right}
            id="true"
            style={{ top: "35%", background: "#22c55e" }}
          />
          <Handle
            type="source"
            position={Position.Right}
            id="false"
            style={{ top: "65%", background: "#ef4444" }}
          />
          <div style={{ fontSize: 10, color: "#22c55e", marginTop: 4 }}>true ↘ / false ↘</div>
        </>
      )}
    </div>
  );
}
