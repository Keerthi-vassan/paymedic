"use client";

import { useCallback, useEffect, useState } from "react";

import type { AuditLogEntry } from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function listActionExecutions(page: number, pageSize: number) {
  const query = new URLSearchParams({
    event_type: "action_execution",
    page: String(page),
    page_size: String(pageSize),
  });
  const res = await fetch(`${API_BASE_URL}/audit?${query.toString()}`);
  if (!res.ok) throw new Error("Failed to load actions");
  return res.json() as Promise<{ total: number; page: number; page_size: number; items: AuditLogEntry[] }>;
}

const PAGE_SIZE = 15;

export function ActionsTakenTable({
  refreshKey,
  onSelectTransaction,
}: {
  refreshKey: number;
  onSelectTransaction: (transactionId: string) => void;
}) {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    listActionExecutions(page, PAGE_SIZE)
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Actions Taken</h2>
        <span className="text-xs text-muted-foreground">{total} actions executed</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-muted-foreground">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Transaction</th>
              <th className="py-1.5 pr-3 font-medium">Root Cause</th>
              <th className="py-1.5 pr-3 font-medium">Action</th>
              <th className="py-1.5 pr-3 font-medium">Attempt</th>
              <th className="py-1.5 font-medium">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-t border-border">
                  <td colSpan={5} className="py-2">
                    <div className="h-4 animate-pulse rounded bg-surface-muted" />
                  </td>
                </tr>
              ))
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-6 text-center text-muted-foreground">
                  No actions executed yet.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr
                  key={item.id}
                  className="cursor-pointer border-t border-border transition-all duration-150 hover:translate-x-0.5 hover:bg-surface-muted"
                  onClick={() => onSelectTransaction(item.transaction_id)}
                >
                  <td className="py-1.5 pr-3 font-mono text-xs text-foreground">
                    {item.transaction_id}
                  </td>
                  <td className="py-1.5 pr-3 text-foreground">{item.root_cause ?? "—"}</td>
                  <td className="py-1.5 pr-3 text-foreground">{item.action_taken ?? "—"}</td>
                  <td className="py-1.5 pr-3 tabular-nums text-muted-foreground">
                    {item.attempt_number ?? "—"}
                  </td>
                  <td
                    className={`py-1.5 font-medium ${
                      item.outcome === "success" ? "text-status-recovered-text" : "text-muted-foreground"
                    }`}
                  >
                    {item.outcome ?? "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <button
          onClick={() => setPage((p) => Math.max(p - 1, 1))}
          disabled={page <= 1}
          className="rounded border border-border px-2.5 py-1 text-xs transition-transform active:scale-95 disabled:opacity-50 disabled:active:scale-100"
        >
          Previous
        </button>
        <span className="text-xs text-muted-foreground">
          Page {page} of {totalPages}
        </span>
        <button
          onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
          disabled={page >= totalPages}
          className="rounded border border-border px-2.5 py-1 text-xs transition-transform active:scale-95 disabled:opacity-50 disabled:active:scale-100"
        >
          Next
        </button>
      </div>
    </div>
  );
}
