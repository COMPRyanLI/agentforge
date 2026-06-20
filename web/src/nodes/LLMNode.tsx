import type { NodeProps } from "@xyflow/react";
import { Bot } from "lucide-react";
import { NodeShell } from "./NodeShell";

export function LLMNode({ data }: NodeProps) {
  const tools = Array.isArray(data.tools) ? (data.tools as string[]) : [];
  return (
    <NodeShell icon={Bot} accent="var(--af-node-llm)" label="LLM">
      {tools.length > 0 ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
          {tools.map((name) => (
            <span
              key={name}
              style={{
                fontSize: 10,
                padding: "1px 6px",
                borderRadius: 999,
                background: "var(--af-bg-surface-raised)",
                color: "var(--af-text-muted)",
                border: "1px solid var(--af-border)",
              }}
            >
              {name}
            </span>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 11, color: "var(--af-text-faint)", marginTop: 6, textAlign: "left" }}>
          No tools
        </div>
      )}
    </NodeShell>
  );
}
