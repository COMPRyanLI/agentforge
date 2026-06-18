import { useCallback, useRef, useState } from "react";
import type { RunEvent } from "../api/runs";
import { getRun, startRun, streamRunEvents } from "../api/runs";

const EVENT_ICONS: Record<string, string> = {
  node_start: "▶",
  node_end: "■",
  llm_call: "🤖",
  llm_result: "💬",
  tool_call: "🔧",
  tool_result: "✅",
  error: "❌",
  retry: "🔄",
};

interface LogEntry {
  id: number;
  icon: string;
  text: string;
  ts: string;
}

interface RunPanelProps {
  token: string;
  agentId: string;
  /** Non-null reason disables Run — e.g. "Save the graph before testing." */
  disabledReason: string | null;
}

export function RunPanel({ token, agentId, disabledReason }: RunPanelProps) {
  const [input, setInput] = useState("");
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [output, setOutput] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [running, setRunning] = useState(false);
  const stopRef = useRef<(() => void) | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const appendLog = useCallback((entry: LogEntry) => {
    setLogs((prev) => [...prev, entry]);
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const handleRun = useCallback(async () => {
    if (!agentId || !input || !token || disabledReason) return;
    setLogs([]);
    setOutput(null);
    setRunStatus("pending");
    setRunning(true);

    try {
      const { run_id } = await startRun(agentId, input, token);
      setRunStatus("running");

      stopRef.current = streamRunEvents(
        run_id,
        token,
        (ev: RunEvent) => {
          const icon = EVENT_ICONS[ev.event_type] ?? "•";
          const payloadStr =
            Object.keys(ev.payload).length > 0
              ? ` — ${JSON.stringify(ev.payload).slice(0, 120)}`
              : "";
          appendLog({
            id: ev.step_index,
            icon,
            text: `[${ev.node_id}] ${ev.event_type}${payloadStr}`,
            ts: new Date(ev.ts).toLocaleTimeString(),
          });
        },
        async (status) => {
          setRunStatus(status);
          setRunning(false);
          if (status === "succeeded") {
            try {
              const finalRun = await getRun(run_id, token);
              setOutput(finalRun.output_json?.output ?? null);
            } catch {
              // ignore
            }
          }
        }
      );
    } catch (err) {
      appendLog({ id: -1, icon: "❌", text: String(err), ts: new Date().toLocaleTimeString() });
      setRunStatus("failed");
      setRunning(false);
    }
  }, [agentId, input, token, disabledReason, appendLog]);

  const handleStop = useCallback(() => {
    stopRef.current?.();
    setRunning(false);
  }, []);

  const statusColor: Record<string, string> = {
    pending: "#f59e0b",
    running: "#3b82f6",
    succeeded: "#22c55e",
    failed: "#ef4444",
  };

  return (
    <div
      style={{
        width: 380,
        height: "100%",
        flexShrink: 0,
        background: "#0f172a",
        borderLeft: "1px solid #1e293b",
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        fontSize: 13,
        color: "#e2e8f0",
      }}
    >
      {/* Header */}
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #1e293b", fontWeight: 700 }}>
        AgentForge Test Panel
        {runStatus && (
          <span
            style={{
              marginLeft: 8,
              fontSize: 11,
              color: statusColor[runStatus] ?? "#94a3b8",
              textTransform: "uppercase",
            }}
          >
            {runStatus}
          </span>
        )}
      </div>

      <div style={{ padding: "8px 12px", borderBottom: "1px solid #1e293b" }}>
        {disabledReason && (
          <div style={{ color: "#f59e0b", fontSize: 11, marginBottom: 6 }}>{disabledReason}</div>
        )}
        <textarea
          placeholder="Input message…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={2}
          style={{
            width: "100%",
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 4,
            padding: "4px 8px",
            color: "#e2e8f0",
            fontSize: 12,
            resize: "vertical",
            boxSizing: "border-box",
          }}
        />
        <div style={{ marginTop: 6, display: "flex", gap: 8 }}>
          <button
            onClick={handleRun}
            disabled={running || !agentId || !input || !token || Boolean(disabledReason)}
            style={{
              flex: 1,
              background: running ? "#1e293b" : "#3b82f6",
              border: "none",
              borderRadius: 4,
              padding: "6px 0",
              color: "#fff",
              cursor: running ? "not-allowed" : "pointer",
              fontWeight: 700,
            }}
          >
            {running ? "Running…" : "▶ Test"}
          </button>
          {running && (
            <button
              onClick={handleStop}
              style={{
                background: "#ef4444",
                border: "none",
                borderRadius: 4,
                padding: "6px 12px",
                color: "#fff",
                cursor: "pointer",
              }}
            >
              Stop
            </button>
          )}
        </div>
      </div>

      {/* Log stream */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
        {logs.length === 0 && !output && (
          <div style={{ color: "#475569", fontSize: 12, paddingTop: 8 }}>
            Logs will stream here when you click Test.
          </div>
        )}
        {logs.map((entry, i) => (
          <div key={i} style={{ marginBottom: 4, lineHeight: 1.5 }}>
            <span style={{ color: "#475569", fontSize: 11 }}>{entry.ts} </span>
            <span>{entry.icon} </span>
            <span style={{ color: "#94a3b8" }}>{entry.text}</span>
          </div>
        ))}
        <div ref={logEndRef} />
      </div>

      {/* Output */}
      {output && (
        <div
          style={{
            padding: "10px 12px",
            borderTop: "1px solid #1e293b",
            background: "#0b1520",
          }}
        >
          <div style={{ color: "#22c55e", fontWeight: 700, marginBottom: 4 }}>Output</div>
          <div style={{ color: "#e2e8f0", whiteSpace: "pre-wrap", fontSize: 13 }}>{output}</div>
        </div>
      )}
    </div>
  );
}
