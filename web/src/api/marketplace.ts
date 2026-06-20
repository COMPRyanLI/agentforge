import type { AgentRead } from "./agents";
import { authHeaders, checkOk } from "./client";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface MarketplaceAgentRead {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  install_count: number;
  avg_rating: number;
  created_at: string;
}

export interface RatingRead {
  id: string;
  agent_id: string;
  user_id: string;
  score: number;
  comment: string | null;
  created_at: string;
}

export async function listMarketplace(
  token: string,
  options?: { q?: string; sort?: "installs" | "rating" }
): Promise<MarketplaceAgentRead[]> {
  const params = new URLSearchParams();
  if (options?.q) params.set("q", options.q);
  if (options?.sort) params.set("sort", options.sort);
  const resp = await fetch(`${API_BASE}/marketplace?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "listMarketplace");
  return resp.json() as Promise<MarketplaceAgentRead[]>;
}

export async function getMarketplaceAgent(
  agentId: string,
  token: string
): Promise<MarketplaceAgentRead> {
  const resp = await fetch(`${API_BASE}/marketplace/${agentId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "getMarketplaceAgent");
  return resp.json() as Promise<MarketplaceAgentRead>;
}

export async function listRatings(agentId: string, token: string): Promise<RatingRead[]> {
  const resp = await fetch(`${API_BASE}/marketplace/${agentId}/ratings`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "listRatings");
  return resp.json() as Promise<RatingRead[]>;
}

export async function installAgent(agentId: string, token: string): Promise<AgentRead> {
  const resp = await fetch(`${API_BASE}/marketplace/${agentId}/install`, {
    method: "POST",
    headers: authHeaders(token),
  });
  await checkOk(resp, "installAgent");
  return resp.json() as Promise<AgentRead>;
}

export async function rateAgent(
  agentId: string,
  score: number,
  comment: string | null,
  token: string
): Promise<RatingRead> {
  const resp = await fetch(`${API_BASE}/marketplace/${agentId}/rate`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ score, comment }),
  });
  await checkOk(resp, "rateAgent");
  return resp.json() as Promise<RatingRead>;
}
