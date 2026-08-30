import { authenticatedFetch } from "../auth/session";

export type MetricCard = {
  code: string;
  label: string;
  value: number;
  display_value: string;
  change_display: string;
  trend: "up" | "down" | "flat";
};

export type OperatingAlert = {
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  description: string;
  module: string;
  occurred_at: string;
};

export type DashboardOverview = {
  shop_id: string;
  data_cutoff: string;
  metrics: MetricCard[];
  alerts: OperatingAlert[];
  pending_approval_count: number;
};

export type AgentTask = {
  id: string;
  status: string;
  created_at: string;
  approval_status: string;
  request: { user_query: string; intent: string; priority: string; user_id: string };
  result?: { result_type: string; summary: string; confidence: number };
};

type TaskList = { items: AgentTask[]; total: number };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  headers.set("Content-Type", "application/json");
  const response = await authenticatedFetch(`/api/v1${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) throw new Error(`请求失败：${response.status}`);
  return response.json() as Promise<T>;
}

export function fetchOverview(shopId = "amazon-us-demo") {
  return request<DashboardOverview>(`/dashboard/overview?shop_id=${encodeURIComponent(shopId)}`);
}

export function fetchTasks() {
  return request<TaskList>("/agent/tasks?limit=20");
}
