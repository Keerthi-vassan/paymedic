import type { GenerateBatchResponse, PaymentsListResponse } from "@/types";

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

export function generateBatch(count = 100, seed = 42) {
  return apiFetch<GenerateBatchResponse>(
    `/payments/generate?count=${count}&seed=${seed}`,
    { method: "POST" }
  );
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
