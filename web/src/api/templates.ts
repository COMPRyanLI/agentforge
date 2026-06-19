import type { GraphJson } from "../lib/graph";
import type { AgentRead } from "./agents";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface TemplateRead {
  id: string;
  name: string;
  description: string | null;
  category: string;
  graph_json: GraphJson;
  created_at: string;
}

async function checkOk(resp: Response, label: string): Promise<Response> {
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${label} failed ${resp.status}: ${body}`);
  }
  return resp;
}

export async function listTemplates(token: string): Promise<TemplateRead[]> {
  const resp = await fetch(`${API_BASE}/templates`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "listTemplates");
  return resp.json() as Promise<TemplateRead[]>;
}

export async function createAgentFromTemplate(
  templateId: string,
  token: string
): Promise<AgentRead> {
  const resp = await fetch(`${API_BASE}/agents/from-template/${templateId}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "createAgentFromTemplate");
  return resp.json() as Promise<AgentRead>;
}
