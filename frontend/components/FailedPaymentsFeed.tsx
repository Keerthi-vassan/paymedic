"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { listPayments } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { rowVariants, transitions } from "@/lib/motion";
import { StatusBadge } from "@/components/StatusBadge";
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

const PAGE_SIZE = 12;

export function FailedPaymentsFeed({
  refreshKey,
  onSelectTransaction,
}: {
  refreshKey: number;
  onSelectTransaction: (transactionId: string) => void;
}) {
  const [items, setItems] = useState<FailedPayment[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [loading, setLoading] = useState(false);
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
  }, [refresh, refreshKey]);

  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold text-foreground">Failed Payments</h2>

        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="ml-auto rounded border border-border bg-surface px-2 py-1.5 text-xs"
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
          className="rounded border border-border bg-surface px-2 py-1.5 text-xs"
        >
          <option value="">All root causes</option>
          {ROOT_CAUSES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <span className="text-xs text-muted-foreground">{total} transactions</span>
      </div>

      {error && <p className="text-sm text-status-blocked-text">{error}</p>}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-muted-foreground">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Transaction</th>
              <th className="py-1.5 pr-3 font-medium">Amount</th>
              <th className="py-1.5 pr-3 font-medium">Method</th>
              <th className="py-1.5 pr-3 font-medium">Root Cause</th>
              <th className="py-1.5 pr-3 font-medium">Status</th>
              <th className="py-1.5 font-medium">Failed At</th>
            </tr>
          </thead>
          <tbody>
            <AnimatePresence mode="wait" initial={false}>
              {loading
                ? Array.from({ length: PAGE_SIZE }).map((_, i) => (
                    <motion.tr
                      key={`skeleton-${i}`}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={transitions.fade}
                      className="border-t border-border"
                    >
                      <td colSpan={6} className="py-2">
                        <div className="h-4 animate-pulse rounded bg-surface-muted" />
                      </td>
                    </motion.tr>
                  ))
                : items.length === 0
                  ? (
                      <motion.tr
                        key="empty"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={transitions.fade}
                      >
                        <td colSpan={6} className="py-6 text-center text-muted-foreground">
                          No payments yet. Generate a batch to get started.
                        </td>
                      </motion.tr>
                    )
                  : items.map((p) => (
                      <motion.tr
                        key={p.transaction_id}
                        variants={rowVariants}
                        initial="initial"
                        animate="animate"
                        exit="exit"
                        transition={transitions.row}
                        whileHover={{ x: 2 }}
                        className="cursor-pointer border-t border-border hover:bg-surface-muted"
                        onClick={() => onSelectTransaction(p.transaction_id)}
                      >
                        <td className="py-1.5 pr-3 font-mono text-xs text-foreground">{p.transaction_id}</td>
                        <td className="py-1.5 pr-3 tabular-nums text-foreground">
                          {formatCurrency(p.amount, p.currency)}
                        </td>
                        <td className="py-1.5 pr-3 text-foreground">{p.payment_method}</td>
                        <td className="py-1.5 pr-3 text-foreground">{p.true_root_cause}</td>
                        <td className="py-1.5 pr-3">
                          <StatusBadge status={p.status} />
                        </td>
                        <td className="py-1.5 text-xs text-muted-foreground">
                          {new Date(p.failed_at).toLocaleString()}
                        </td>
                      </motion.tr>
                    ))}
            </AnimatePresence>
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <motion.button
          onClick={() => setPage((p) => Math.max(p - 1, 1))}
          disabled={page <= 1}
          whileTap={{ scale: 0.95 }}
          transition={transitions.press}
          className="rounded border border-border px-2.5 py-1 text-xs disabled:opacity-50"
        >
          Previous
        </motion.button>
        <span className="text-xs text-muted-foreground">
          Page {page} of {totalPages}
        </span>
        <motion.button
          onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
          disabled={page >= totalPages}
          whileTap={{ scale: 0.95 }}
          transition={transitions.press}
          className="rounded border border-border px-2.5 py-1 text-xs disabled:opacity-50"
        >
          Next
        </motion.button>
      </div>
    </div>
  );
}
