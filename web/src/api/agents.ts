import type { GraphJson } from "../lib/graph";
import { authHeaders, checkOk } from "./client";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface AgentRead {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  current_version_id: string | null;
  visibility: string;
  install_count: number;
  avg_rating: number | null;
  created_at: string;
}

export interface AgentVersionRead {
  id: string;
  agent_id: string;
  version_number: number;
  graph_json: GraphJson;
  created_at: string;
}

export async function createAgent(
  name: string,
  token: string,
  description?: string
): Promise<AgentRead> {
  const resp = await fetch(`${API_BASE}/agents`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ name, description: description ?? null }),
  });
  await checkOk(resp, "createAgent");
  return resp.json() as Promise<AgentRead>;
}

export async function listAgents(token: string): Promise<AgentRead[]> {
  const resp = await fetch(`${API_BASE}/agents`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "listAgents");
  return resp.json() as Promise<AgentRead[]>;
}

export async function getAgent(agentId: string, token: string): Promise<AgentRead> {
  const resp = await fetch(`${API_BASE}/agents/${agentId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "getAgent");
  return resp.json() as Promise<AgentRead>;
}

export async function getCurrentVersion(
  agentId: string,
  token: string
): Promise<AgentVersionRead> {
  const resp = await fetch(`${API_BASE}/agents/${agentId}/versions/current`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "getCurrentVersion");
  return resp.json() as Promise<AgentVersionRead>;
}

export async function createVersion(
  agentId: string,
  graphJson: GraphJson,
  token: string
): Promise<AgentVersionRead> {
  const resp = await fetch(`${API_BASE}/agents/${agentId}/versions`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ graph_json: graphJson }),
  });
  await checkOk(resp, "createVersion");
  return resp.json() as Promise<AgentVersionRead>;
}

export async function publishAgent(agentId: string, token: string): Promise<AgentRead> {
  const resp = await fetch(`${API_BASE}/agents/${agentId}/publish`, {
    method: "POST",
    headers: authHeaders(token),
  });
  await checkOk(resp, "publishAgent");
  return resp.json() as Promise<AgentRead>;
}
