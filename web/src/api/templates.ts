import type { GraphJson } from "../lib/graph";
import type { AgentRead } from "./agents";
import { checkOk } from "./client";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface TemplateRead {
  id: string;
  name: string;
  description: string | null;
  category: string;
  graph_json: GraphJson;
  created_at: string;
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
