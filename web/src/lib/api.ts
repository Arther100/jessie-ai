// All backend API calls — base URL from env
// BYOK: X-Claude-API-Key sent per request; never stored on server.
import {
  clearApiKey,
  getApiKey,
  getProvider,
  getUserId,
  getWorkspaceId,
} from "./keyStorage";

const BASE = process.env.NEXT_PUBLIC_JESSIE_API ?? "http://localhost:8000";

export type ApiKeyRequiredHandler = () => void;
let _onApiKeyRequired: ApiKeyRequiredHandler | null = null;

export function setOnApiKeyRequired(handler: ApiKeyRequiredHandler): void {
  _onApiKeyRequired = handler;
}

export function authHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-Claude-API-Key": getApiKey() || "",
    "X-AI-Provider": getProvider() || "anthropic",
    "X-User-Id": getUserId() || "web_user",
    "X-Workspace-Id": getWorkspaceId() || "web",
  };
}

async function handleUnauthorized(res: Response): Promise<void> {
  if (res.status !== 401) return;
  try {
    const data = await res.clone().json();
    if (data?.error === "api_key_required" || data?.detail?.error === "api_key_required") {
      clearApiKey();
      _onApiKeyRequired?.();
    }
  } catch {
    clearApiKey();
    _onApiKeyRequired?.();
  }
}

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE}${path}`);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url.toString(), {
    cache: "no-store",
    headers: authHeaders(),
  });
  await handleUnauthorized(res);
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.text()).trim(); } catch { /* ignore */ }
    throw new Error(detail ? `GET ${path} → ${res.status}: ${detail.slice(0, 240)}` : `GET ${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  await handleUnauthorized(res);
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.text()).trim(); } catch { /* ignore */ }
    throw new Error(detail ? `POST ${path} → ${res.status}: ${detail.slice(0, 240)}` : `POST ${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  await handleUnauthorized(res);
  if (!res.ok) throw new Error(`PUT ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export async function verifyApiKey(
  key: string,
  provider: string,
): Promise<{ valid: boolean; model?: string; message: string }> {
  const res = await fetch(`${BASE}/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Claude-API-Key": key,
      "X-AI-Provider": provider,
      "X-User-Id": getUserId() || "web_user",
      "X-Workspace-Id": getWorkspaceId() || "web",
    },
  });
  const data = await res.json();
  if (res.ok && data.valid) {
    return { valid: true, model: data.model, message: data.message || "API key is valid ✓" };
  }
  return {
    valid: false,
    message: data.message || "API key rejected. Check your key.",
  };
}

export const api = {
  getHealth: () => get<{ status: string; version: string }>("/health"),

  getTeamUsage: (workspaceId = "", userId = "admin") =>
    get<{ date: string; usage: TeamMember[] }>("/team/usage", {
      workspace_id: workspaceId,
      user_id: userId,
    }),

  getDashboardStats: () =>
    get<DashboardStats>("/dashboard/stats"),

  getReviewHistory: (workspaceId: string) =>
    get<ReviewHistoryRow[]>(`/review/history/${workspaceId}`),

  getMergeHistory: (workspaceId: string) =>
    get<MergeHistoryRow[]>(`/merge/history/${workspaceId}`),

  getOpenPRs: (params: OpenPRsParams) =>
    postJson<{ prs: PR[] }>("/merge/open-prs", params),

  getBranches: (params: OpenPRsParams) =>
    postJson<{ branches: string[] }>("/merge/branches", params),

  getReport: (reviewId: string) =>
    get<ReportResponse>(`/reports/${reviewId}`),

  getRequestCount: (userId: string) =>
    get<{ user_id: string; requests_today: number }>(`/requests/${userId}`),

  browseFs: (path = "") =>
    get<{
      path: string;
      parent: string | null;
      dirs: { name: string; path: string }[];
      is_root_list: boolean;
    }>("/fs/browse", path ? { path } : undefined),

  updateQuota: (userId: string, dailyLimit: number) =>
    put(`/team/quota/${userId}`, { daily_limit: dailyLimit }),

  testWebhook: () =>
    get<{ status: string; version: string }>("/webhook/test"),

  verifyApiKey,
};

// ── Types ───────────────────────────────────────────────────────────────────

export interface TeamMember {
  user_id: string;
  used: number;
  limit: number;
  remaining: number;
}

export interface DashboardStats {
  reviews_this_week: number;
  avg_score_this_week: number;
  critical_issues_this_week: number;
  active_members_today: number;
  score_trend: ScoreTrendPoint[];
  recent_reviews: RecentReview[];
}

export interface ScoreTrendPoint {
  date: string;
  avg_score: number;
  frontend: number;
  backend: number;
  database: number;
}

export interface RecentReview {
  id: number;
  type: "code_review" | "merge_review";
  date: string;
  project: string;
  overall_score: number;
  grade: string;
  verdict?: string;
  critical_count: number;
  total_issues: number;
}

export interface ReviewHistoryRow {
  date: string;
  overall_score: number;
  frontend_score: number;
  backend_score: number;
  db_score: number;
  total_issues: number;
  critical_count: number;
  report_path: string;
  tokens_used: number;
  cost_estimate: number;
  created_at: string;
}

export interface MergeHistoryRow {
  date: string;
  verdict: string;
  overall_score: number;
  total_issues: number;
  critical_count: number;
  report_path: string;
  cost_estimate: number;
  created_at: string;
}

export interface PR {
  number: number;
  title: string;
  author: string;
  added: number;
  removed: number;
  created_at: string;
  url?: string;
}

export interface OpenPRsParams {
  platform: string;
  repo: string;
  token: string;
  azure_org?: string;
  azure_project?: string;
  gitlab_project_id?: string;
}

export interface ReportResponse {
  id: number;
  type: "code_review" | "merge_review";
  metadata: Record<string, unknown>;
  markdown_content: string;
}
