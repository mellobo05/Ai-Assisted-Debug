export type DebugRequest = {
  issue_summary: string;
  domain: string;
  os: string;
  logs: string;
};

export type DebugResponse = {
  session_id: string;
  status: string;
  os?: string;
  domain?: string;
  issue_summary?: string;
  has_embedding?: boolean;
};

export type SearchRequest = {
  query: string;
  limit?: number;
};

export type JiraSearchResult = {
  source?: "jira";
  issue_key: string;
  similarity: number;
  summary?: string | null;
  status?: string | null;
  priority?: string | null;
  assignee?: string | null;
  issue_type?: string | null;
  url?: string | null;
  program_theme?: string | null;
  labels?: string[] | null;
  components?: string[] | null;
  latest_comment?: string | null;
};

export type SearchResponse = {
  query: string;
  results_count: number;
  results: JiraSearchResult[];
};

const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const API_BASE =
  (import.meta as any).env?.VITE_API_BASE?.toString?.() || DEFAULT_API_BASE;

export function getApiBase(): string {
  return API_BASE;
}

async function fetchJsonWithTimeout<T>(
  url: string,
  init: RequestInit,
  timeoutMs: number
): Promise<T> {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      ...init,
      signal: controller.signal
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Request failed (${res.status}): ${text || res.statusText}`);
    }

    return (await res.json()) as T;
  } catch (e: any) {
    if (e?.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs}ms. Is the backend running?`);
    }
    throw e;
  } finally {
    clearTimeout(t);
  }
}

export async function startDebug(payload: DebugRequest): Promise<DebugResponse> {
  return await fetchJsonWithTimeout<DebugResponse>(
    `${API_BASE}/debug`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    },
    15000
  );
}

export async function getDebugStatus(sessionId: string): Promise<DebugResponse> {
  return await fetchJsonWithTimeout<DebugResponse>(
    `${API_BASE}/debug/${encodeURIComponent(sessionId)}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" }
    },
    15000
  );
}

export async function searchJira(payload: SearchRequest): Promise<SearchResponse> {
  return await fetchJsonWithTimeout<SearchResponse>(
    `${API_BASE}/search`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: payload.query,
        limit: payload.limit ?? 5
      })
    },
    15000
  );
}

