export type DebugRequest = {
  issue_summary: string;
  domain: string;
  os: string;
  logs: string;
};

export type DebugResponse = {
  session_id: string;
  status: string;
};

const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const API_BASE =
  (import.meta as any).env?.VITE_API_BASE?.toString?.() || DEFAULT_API_BASE;

export function getApiBase(): string {
  return API_BASE;
}

export async function startDebug(payload: DebugRequest): Promise<DebugResponse> {
  const res = await fetch(`${API_BASE}/debug`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Request failed (${res.status}): ${text || res.statusText}`);
  }

  return (await res.json()) as DebugResponse;
}

