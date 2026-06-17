const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface RunEnqueueResponse {
  run_id: string;
  status: string;
}

export interface RunRead {
  id: string;
  agent_id: string;
  status: string;
  output_json: { output: string } | null;
  error_json: { error: string } | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface RunEvent {
  run_id: string;
  step_index: number;
  node_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  ts: string;
}

export async function startRun(
  agentId: string,
  input: string,
  token: string
): Promise<RunEnqueueResponse> {
  const resp = await fetch(`${API_BASE}/agents/${agentId}/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ input }),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`startRun failed ${resp.status}: ${body}`);
  }
  return resp.json() as Promise<RunEnqueueResponse>;
}

export async function getRun(runId: string, token: string): Promise<RunRead> {
  const resp = await fetch(`${API_BASE}/runs/${runId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new Error(`getRun failed ${resp.status}`);
  return resp.json() as Promise<RunRead>;
}

export function streamRunEvents(
  runId: string,
  token: string,
  onEvent: (e: RunEvent) => void,
  onDone: (status: string) => void
): () => void {
  const url = new URL(`${API_BASE}/runs/${runId}/events`);
  url.searchParams.set("token", token);

  const es = new EventSource(url.toString());

  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data) as { type?: string; status?: string } & RunEvent;
      if (data.type === "done") {
        onDone(data.status ?? "unknown");
        es.close();
      } else {
        onEvent(data as RunEvent);
      }
    } catch {
      // malformed frame — ignore
    }
  };

  es.onerror = () => {
    es.close();
  };

  return () => es.close();
}
