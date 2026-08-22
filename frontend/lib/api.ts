import type {
  AuditListResponse,
  ConfigRules,
  GenerateBatchResponse,
  MetricsSummary,
  PaymentsListResponse,
  PipelineRunResponse,
  RootCauseBreakdownRow,
  TimelinePoint,
} from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, init);
  if (!res.ok) {
    throw new Error(`API request to ${path} failed with status ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function getHealth() {
  return apiFetch<{ status: string }>("/health");
}

export function generateBatch(count = 100, seed?: number) {
  const query = new URLSearchParams({ count: String(count) });
  if (seed !== undefined) query.set("seed", String(seed));
  return apiFetch<GenerateBatchResponse>(`/payments/generate?${query.toString()}`, {
    method: "POST",
  });
}

export function listPayments(params: {
  status?: string;
  rootCause?: string;
  page?: number;
  pageSize?: number;
}) {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.rootCause) query.set("root_cause", params.rootCause);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 20));

  return apiFetch<PaymentsListResponse>(`/payments?${query.toString()}`);
}

export function runPipeline() {
  return apiFetch<PipelineRunResponse>("/pipeline/run", { method: "POST" });
}

export function getTransactionAudit(transactionId: string) {
  return apiFetch<AuditListResponse>(`/audit/${transactionId}`);
}

export function getMetricsSummary() {
  return apiFetch<MetricsSummary>("/metrics/summary");
}

export function getRootCauseBreakdown() {
  return apiFetch<RootCauseBreakdownRow[]>("/metrics/root-cause-breakdown");
}

export function getTimeline() {
  return apiFetch<TimelinePoint[]>("/metrics/timeline");
}

export function getConfigRules() {
  return apiFetch<ConfigRules>("/config/rules");
}
