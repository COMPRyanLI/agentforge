import { SlidersHorizontal } from "lucide-react";
import type { CSSProperties } from "react";
import type { ToolRead } from "../api/tools";

export interface ConfigurableNode {
  id: string;
  type: string;
  data: Record<string, unknown>;
}

interface ConfigPanelProps {
  node: ConfigurableNode | null;
  tools: ToolRead[];
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
}

const fieldStyle: CSSProperties = {
  width: "100%",
  background: "var(--af-bg-surface-raised)",
  border: "1px solid var(--af-border)",
  borderRadius: 4,
  padding: "4px 8px",
  color: "var(--af-text)",
  fontSize: 12,
  fontFamily: "var(--af-font-sans)",
  boxSizing: "border-box",
  marginBottom: 8,
};

const labelStyle: CSSProperties = { color: "var(--af-text-faint)", fontSize: 11, marginBottom: 2 };

export function ConfigPanel({ node, tools, onChange }: ConfigPanelProps) {
  if (!node) {
    return (
      <div style={panelStyle}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            textAlign: "center",
            color: "var(--af-text-faint)",
            paddingTop: 48,
            gap: 8,
          }}
        >
          <SlidersHorizontal size={20} strokeWidth={1.5} />
          <div style={{ fontSize: 12 }}>Select a node to configure it.</div>
        </div>
      </div>
    );
  }

  const set = (key: string, value: unknown) => onChange(node.id, { ...node.data, [key]: value });

  return (
    <div style={panelStyle}>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>
        {node.type}{" "}
        <span style={{ color: "var(--af-text-faint)", fontWeight: 400 }}>({node.id})</span>
      </div>

      {node.type === "llm" && (
        <>
          <div style={labelStyle}>System prompt</div>
          <textarea
            style={{ ...fieldStyle, resize: "vertical" }}
            rows={4}
            value={typeof node.data.system_prompt === "string" ? node.data.system_prompt : ""}
            onChange={(e) => set("system_prompt", e.target.value)}
          />
          <div style={labelStyle}>Tools (comma-separated names)</div>
          <input
            style={fieldStyle}
            value={Array.isArray(node.data.tools) ? (node.data.tools as string[]).join(", ") : ""}
            onChange={(e) =>
              set(
                "tools",
                e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean)
              )
            }
          />
          <div style={{ fontSize: 11, color: "var(--af-text-faint)" }}>
            Known tools: {tools.map((t) => t.name).join(", ") || "(none yet)"}
          </div>
        </>
      )}

      {node.type === "tool" && (
        <>
          <div style={labelStyle}>Tool</div>
          <select
            style={fieldStyle}
            value={typeof node.data.tool_id === "string" ? node.data.tool_id : ""}
            onChange={(e) => set("tool_id", e.target.value)}
          >
            <option value="">(select a tool)</option>
            {tools.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={Boolean(node.data.require_approval)}
              onChange={(e) => set("require_approval", e.target.checked)}
            />
            Require human approval
          </label>
        </>
      )}

      {(node.type === "condition" || node.type === "loop") && (
        <>
          <div style={labelStyle}>Expression</div>
          <input
            style={fieldStyle}
            placeholder="last_tool_result.score > 0.5"
            value={typeof node.data.expr === "string" ? node.data.expr : ""}
            onChange={(e) => set("expr", e.target.value)}
          />
          <div style={{ fontSize: 11, color: "var(--af-text-faint)", marginBottom: 8 }}>
            Available: output, last_tool_result (dict-key access OK), step_index
          </div>
        </>
      )}

      {node.type === "loop" && (
        <>
          <div style={labelStyle}>Max iterations</div>
          <input
            type="number"
            min={1}
            style={fieldStyle}
            value={typeof node.data.max_iterations === "number" ? node.data.max_iterations : ""}
            onChange={(e) => set("max_iterations", Number(e.target.value) || 1)}
          />
        </>
      )}

      {(node.type === "input" || node.type === "output") && (
        <div style={{ fontSize: 12, color: "var(--af-text-muted)" }}>This node has no configuration.</div>
      )}
    </div>
  );
}

const panelStyle: CSSProperties = {
  width: 280,
  padding: 12,
  borderLeft: "1px solid var(--af-border)",
  background: "var(--af-bg-surface)",
  color: "var(--af-text)",
  fontFamily: "var(--af-font-sans)",
  fontSize: 13,
  overflowY: "auto",
};
