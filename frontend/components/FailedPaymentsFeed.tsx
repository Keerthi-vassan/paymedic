"use client";

import { useCallback, useEffect, useState } from "react";

import { generateBatch, listPayments } from "@/lib/api";
import type { FailedPayment } from "@/types";

const ROOT_CAUSES = [
  "insufficient_funds",
  "gateway_timeout",
  "auth_failure",
  "network_drop",
  "card_declined",
  "possible_fraud",
];

const STATUSES = ["open", "recovered", "escalated", "blocked"];

const PAGE_SIZE = 20;

function formatAmount(amount: number, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amount);
}

export function FailedPaymentsFeed() {
  const [items, setItems] = useState<FailedPayment[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    listPayments({ status: status || undefined, rootCause: rootCause || undefined, page, pageSize: PAGE_SIZE })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Could not load payments feed"))
      .finally(() => setLoading(false));
  }, [status, rootCause, page]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      await generateBatch(100, 42);
      setPage(1);
      refresh();
    } catch {
      setError("Could not generate batch");
    } finally {
      setGenerating(false);
    }
  };

  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  return (
    <div className="w-full max-w-6xl">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="rounded bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
        >
          {generating ? "Generating..." : "Generate Batch (100)"}
        </button>

        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="rounded border border-zinc-300 bg-white px-2 py-2 text-sm dark:border-zinc-700 dark:bg-black"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          value={rootCause}
          onChange={(e) => {
            setRootCause(e.target.value);
            setPage(1);
          }}
          className="rounded border border-zinc-300 bg-white px-2 py-2 text-sm dark:border-zinc-700 dark:bg-black"
        >
          <option value="">All root causes</option>
          {ROOT_CAUSES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <span className="text-sm text-zinc-500">{total} transactions</span>
      </div>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      <div className="overflow-x-auto rounded border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50 text-xs uppercase text-zinc-500 dark:bg-zinc-900">
            <tr>
              <th className="px-3 py-2">Transaction</th>
              <th className="px-3 py-2">Amount</th>
              <th className="px-3 py-2">Method</th>
              <th className="px-3 py-2">Error Code</th>
              <th className="px-3 py-2">Root Cause</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Failed At</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-zinc-500">
                  Loading...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-zinc-500">
                  No payments yet. Generate a batch to get started.
                </td>
              </tr>
            ) : (
              items.map((p) => (
                <tr key={p.transaction_id} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="px-3 py-2 font-mono text-xs">{p.transaction_id}</td>
                  <td className="px-3 py-2">{formatAmount(p.amount, p.currency)}</td>
                  <td className="px-3 py-2">{p.payment_method}</td>
                  <td className="px-3 py-2 text-xs text-zinc-500">{p.error_code ?? "—"}</td>
                  <td className="px-3 py-2">{p.true_root_cause}</td>
                  <td className="px-3 py-2">{p.status}</td>
                  <td className="px-3 py-2 text-xs text-zinc-500">
                    {new Date(p.failed_at).toLocaleString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between text-sm">
        <button
          onClick={() => setPage((p) => Math.max(p - 1, 1))}
          disabled={page <= 1}
          className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-50 dark:border-zinc-700"
        >
          Previous
        </button>
        <span>
          Page {page} of {totalPages}
        </span>
        <button
          onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
          disabled={page >= totalPages}
          className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-50 dark:border-zinc-700"
        >
          Next
        </button>
      </div>
    </div>
  );
}
