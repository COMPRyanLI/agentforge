import { useState, type CSSProperties, type ReactNode } from "react";
import { createTool, testTool, type ToolRead } from "../api/tools";

interface ParamRow {
  name: string;
  type: "string" | "number" | "boolean";
  required: boolean;
}

interface ToolBuilderProps {
  token: string;
  onCreated: (tool: ToolRead) => void;
  onClose: () => void;
}

function paramsToJsonSchema(params: ParamRow[]): Record<string, unknown> {
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  for (const p of params) {
    if (!p.name) continue;
    properties[p.name] = { type: p.type };
    if (p.required) required.push(p.name);
  }
  return { type: "object", properties, required };
}

export function ToolBuilder({ token, onCreated, onClose }: ToolBuilderProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [implType, setImplType] = useState<"http">("http");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState<"GET" | "POST" | "PUT" | "PATCH" | "DELETE">("GET");
  const [timeoutSeconds, setTimeoutSeconds] = useState(10);
  const [params, setParams] = useState<ParamRow[]>([{ name: "", type: "string", required: false }]);
  const [savedTool, setSavedTool] = useState<ToolRead | null>(null);
  const [testArgsJson, setTestArgsJson] = useState("{}");
  const [testResult, setTestResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const updateParam = (i: number, patch: Partial<ParamRow>) =>
    setParams((prev) => prev.map((p, idx) => (idx === i ? { ...p, ...patch } : p)));

  const handleSave = async () => {
    setError(null);
    try {
      const tool = await createTool(
        {
          name,
          description: description || undefined,
          json_schema: paramsToJsonSchema(params),
          impl_type: implType,
          config_json: { url, method, timeout_seconds: timeoutSeconds },
        },
        token
      );
      setSavedTool(tool);
      onCreated(tool);
    } catch (err) {
      setError(String(err));
    }
  };

  const handleTest = async () => {
    if (!savedTool) return;
    setError(null);
    setTestResult(null);
    try {
      const args = JSON.parse(testArgsJson) as Record<string, unknown>;
      const resp = await testTool(savedTool.id, args, token);
      setTestResult(resp.error ? `Error: ${resp.error}` : JSON.stringify(resp.result, null, 2));
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <div style={{ fontWeight: 700 }}>New HTTP Tool</div>
          <button onClick={onClose} style={closeButtonStyle}>
            ✕
          </button>
        </div>

        <Field label="Name">
          <input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Description">
          <input
            style={inputStyle}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field label="Implementation type">
          <select style={inputStyle} value={implType} onChange={() => setImplType("http")}>
            <option value="http">http</option>
          </select>
          <div style={hintStyle}>
            "builtin" tools are read-only references; "python" has no executor (no sandboxed
            code execution).
          </div>
        </Field>
        <Field label="URL (https only)">
          <input
            style={inputStyle}
            placeholder="https://api.example.com/lookup"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </Field>
        <Field label="Method">
          <select
            style={inputStyle}
            value={method}
            onChange={(e) => setMethod(e.target.value as typeof method)}
          >
            {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Timeout (seconds)">
          <input
            type="number"
            style={inputStyle}
            value={timeoutSeconds}
            onChange={(e) => setTimeoutSeconds(Number(e.target.value) || 10)}
          />
        </Field>

        <Field label="Parameters">
          {params.map((p, i) => (
            <div key={i} style={{ display: "flex", gap: 6, marginBottom: 4 }}>
              <input
                style={{ ...inputStyle, flex: 2, marginBottom: 0 }}
                placeholder="param name"
                value={p.name}
                onChange={(e) => updateParam(i, { name: e.target.value })}
              />
              <select
                style={{ ...inputStyle, flex: 1, marginBottom: 0 }}
                value={p.type}
                onChange={(e) => updateParam(i, { type: e.target.value as ParamRow["type"] })}
              >
                <option value="string">string</option>
                <option value="number">number</option>
                <option value="boolean">boolean</option>
              </select>
              <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
                <input
                  type="checkbox"
                  checked={p.required}
                  onChange={(e) => updateParam(i, { required: e.target.checked })}
                />
                req
              </label>
            </div>
          ))}
          <button
            style={smallButtonStyle}
            onClick={() => setParams((prev) => [...prev, { name: "", type: "string", required: false }])}
          >
            + param
          </button>
        </Field>

        {error && <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 8 }}>{error}</div>}

        <button style={primaryButtonStyle} onClick={handleSave} disabled={!name || !url}>
          Save Tool
        </button>

        {savedTool && (
          <div style={{ marginTop: 16, borderTop: "1px solid #1e293b", paddingTop: 12 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Test "{savedTool.name}"</div>
            <Field label="Args (JSON)">
              <textarea
                style={{ ...inputStyle, fontFamily: "monospace" }}
                rows={3}
                value={testArgsJson}
                onChange={(e) => setTestArgsJson(e.target.value)}
              />
            </Field>
            <button style={smallButtonStyle} onClick={handleTest}>
              Test
            </button>
            {testResult && (
              <pre style={{ fontSize: 11, color: "#94a3b8", whiteSpace: "pre-wrap", marginTop: 8 }}>
                {testResult}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={hintLabelStyle}>{label}</div>
      {children}
    </div>
  );
}

const overlayStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.5)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 100,
};

const modalStyle: CSSProperties = {
  width: 420,
  maxHeight: "85vh",
  overflowY: "auto",
  background: "#0f172a",
  border: "1px solid #1e293b",
  borderRadius: 8,
  padding: 16,
  color: "#e2e8f0",
  fontFamily: "system-ui, sans-serif",
  fontSize: 13,
};

const inputStyle: CSSProperties = {
  width: "100%",
  background: "#1e293b",
  border: "1px solid #334155",
  borderRadius: 4,
  padding: "4px 8px",
  color: "#e2e8f0",
  fontSize: 12,
  boxSizing: "border-box",
  marginBottom: 4,
};

const hintLabelStyle: CSSProperties = { color: "#64748b", fontSize: 11, marginBottom: 2 };
const hintStyle: CSSProperties = { color: "#475569", fontSize: 10, marginTop: 2 };

const primaryButtonStyle: CSSProperties = {
  width: "100%",
  background: "#3b82f6",
  border: "none",
  borderRadius: 4,
  padding: "8px 0",
  color: "#fff",
  fontWeight: 700,
  cursor: "pointer",
};

const smallButtonStyle: CSSProperties = {
  background: "#1e293b",
  border: "1px solid #334155",
  borderRadius: 4,
  padding: "4px 10px",
  color: "#e2e8f0",
  fontSize: 11,
  cursor: "pointer",
};

const closeButtonStyle: CSSProperties = {
  background: "transparent",
  border: "none",
  color: "#94a3b8",
  cursor: "pointer",
  fontSize: 14,
};
