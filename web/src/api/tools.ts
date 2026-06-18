const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type ToolImplType = "builtin" | "http" | "python";

export interface ToolRead {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  json_schema: Record<string, unknown>;
  impl_type: ToolImplType;
  config_json: Record<string, unknown> | null;
  created_at: string;
}

export interface ToolCreate {
  name: string;
  description?: string;
  json_schema: Record<string, unknown>;
  impl_type: ToolImplType;
  config_json?: Record<string, unknown>;
}

export interface ToolTestResponse {
  result: Record<string, unknown> | null;
  error: string | null;
}

function authHeaders(token: string): Record<string, string> {
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

async function checkOk(resp: Response, label: string): Promise<Response> {
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${label} failed ${resp.status}: ${body}`);
  }
  return resp;
}

export async function listTools(token: string): Promise<ToolRead[]> {
  const resp = await fetch(`${API_BASE}/tools`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  await checkOk(resp, "listTools");
  return resp.json() as Promise<ToolRead[]>;
}

export async function createTool(data: ToolCreate, token: string): Promise<ToolRead> {
  const resp = await fetch(`${API_BASE}/tools`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  await checkOk(resp, "createTool");
  return resp.json() as Promise<ToolRead>;
}

export async function testTool(
  toolId: string,
  args: Record<string, unknown>,
  token: string
): Promise<ToolTestResponse> {
  const resp = await fetch(`${API_BASE}/tools/${toolId}/test`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ args }),
  });
  if (resp.status === 400) {
    const body = (await resp.json()) as { detail?: string };
    return { result: null, error: body.detail ?? "Bad request" };
  }
  await checkOk(resp, "testTool");
  return resp.json() as Promise<ToolTestResponse>;
}
