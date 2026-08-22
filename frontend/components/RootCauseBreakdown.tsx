"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { getRootCauseBreakdown } from "@/lib/api";
import { transitions } from "@/lib/motion";
import type { RootCauseBreakdownRow } from "@/types";

const ROOT_CAUSE_LABELS: Record<string, string> = {
  insufficient_funds: "Insufficient funds",
  gateway_timeout: "Gateway timeout",
  auth_failure: "Auth failure",
  network_drop: "Network drop",
  card_declined: "Card declined",
  possible_fraud: "Possible fraud",
};

function BarRow({
  row,
  maxTotal,
  onHover,
}: {
  row: RootCauseBreakdownRow;
  maxTotal: number;
  onHover: (row: RootCauseBreakdownRow | null) => void;
}) {
  const targetWidthPct = Math.max((row.total / maxTotal) * 100, 4);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={transitions.row}
      className="group flex items-center gap-3"
      onMouseEnter={() => onHover(row)}
      onMouseLeave={() => onHover(null)}
    >
      <span className="w-32 shrink-0 text-sm text-foreground">
        {ROOT_CAUSE_LABELS[row.root_cause] ?? row.root_cause}
      </span>
      <div className="relative h-4 flex-1">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-r-sm bg-gradient-to-r from-accent to-accent/80 group-hover:opacity-80"
          initial={{ width: 0 }}
          animate={{ width: `${targetWidthPct}%` }}
          transition={transitions.bar}
        />
      </div>
      <span className="w-28 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
        {row.total} · {row.recovery_rate.toFixed(0)}% recovered
      </span>
    </motion.div>
  );
}

function FraudRow({ row }: { row: RootCauseBreakdownRow }) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-status-blocked/30 bg-status-blocked/5 px-3 py-2">
      <svg
        className="h-4 w-4 shrink-0 text-status-blocked"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M10 1.5a1 1 0 01.894.553l1.382 2.762 3.05.443a1 1 0 01.554 1.706l-2.207 2.152.521 3.037a1 1 0 01-1.451 1.054L10 11.75l-2.743 1.457a1 1 0 01-1.451-1.054l.521-3.037-2.207-2.152a1 1 0 01.554-1.706l3.05-.443 1.382-2.762A1 1 0 0110 1.5z"
          clipRule="evenodd"
        />
      </svg>
      <span className="w-24 shrink-0 text-sm font-medium text-foreground">Possible fraud</span>
      <span className="flex-1 text-sm text-muted-foreground">
        {row.total} transactions · 0% recovered — by design, fraud is never auto-recovered
      </span>
      <span className="shrink-0 text-sm font-semibold tabular-nums text-status-blocked-text">
        {row.escalated} escalated · {row.blocked} blocked
      </span>
    </div>
  );
}

export function RootCauseBreakdown({ refreshKey }: { refreshKey: number }) {
  const [rows, setRows] = useState<RootCauseBreakdownRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState<RootCauseBreakdownRow | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    getRootCauseBreakdown()
      .then(setRows)
      .catch(() => {
        setRows([]);
        setError(true);
      })
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const state = loading ? "loading" : error ? "error" : rows.length === 0 ? "empty" : "data";

  const fraudRow = rows.find((r) => r.root_cause === "possible_fraud");
  const otherRows = rows
    .filter((r) => r.root_cause !== "possible_fraud")
    .sort((a, b) => b.total - a.total);
  const maxTotal = Math.max(...otherRows.map((r) => r.total), 1);

  return (
    <AnimatePresence mode="wait">
      {state === "loading" && (
        <motion.div
          key="loading"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-sm"
        >
          <div className="h-4 w-40 animate-pulse rounded bg-surface-muted" />
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-4 animate-pulse rounded bg-surface-muted" />
          ))}
        </motion.div>
      )}

      {state === "error" && (
        <motion.div
          key="error"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="rounded-lg border border-status-blocked/30 bg-status-blocked/5 p-6 text-center text-sm text-status-blocked-text"
        >
          Could not load root-cause breakdown — the backend may be unreachable.
        </motion.div>
      )}

      {state === "empty" && (
        <motion.div
          key="empty"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm text-muted-foreground"
        >
          No root-cause data yet.
        </motion.div>
      )}

      {state === "data" && (
        <motion.div
          key="data"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 shadow-sm"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground">Root Cause Breakdown</h2>
            {hovered && (
              <span className="text-xs text-muted-foreground">
                {hovered.recovered} recovered · {hovered.escalated} escalated · {hovered.blocked} blocked
              </span>
            )}
          </div>

          <div className="flex flex-col gap-2.5">
            <AnimatePresence initial={false}>
              {otherRows.map((row) => (
                <BarRow key={row.root_cause} row={row} maxTotal={maxTotal} onHover={setHovered} />
              ))}
            </AnimatePresence>
          </div>

          {fraudRow && <FraudRow row={fraudRow} />}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
