"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { getMetricsSummary } from "@/lib/api";
import { formatCurrency, formatMinutes, formatPercent } from "@/lib/format";
import { transitions } from "@/lib/motion";
import { useCountUp } from "@/lib/useCountUp";
import type { MetricsSummary as MetricsSummaryType } from "@/types";

function TileSkeleton() {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="h-3 w-20 animate-pulse rounded bg-surface-muted" />
      <div className="h-7 w-24 animate-pulse rounded bg-surface-muted" />
    </div>
  );
}

function Tile({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <motion.div
      whileHover={{ y: -2, boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
      transition={transitions.hover}
      className={`flex flex-col gap-1 rounded-lg border p-4 shadow-sm ${
        emphasis ? "border-accent/20 bg-accent/5" : "border-border bg-surface"
      }`}
    >
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span
        className={`tabular-nums text-2xl font-semibold ${emphasis ? "text-accent" : "text-foreground"}`}
      >
        {value}
      </span>
    </motion.div>
  );
}

export function MetricsSummary({ refreshKey }: { refreshKey: number }) {
  const [metrics, setMetrics] = useState<MetricsSummaryType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    getMetricsSummary()
      .then(setMetrics)
      .catch(() => {
        setMetrics(null);
        setError(true);
      })
      .finally(() => setLoading(false));
  }, [refreshKey]);

  // Fixed hook count regardless of loading/error/empty state -- animated
  // toward the real values once loaded, toward 0 otherwise (invisible while
  // those branches render their own early return).
  const recoveredAmount = useCountUp(metrics?.total_recovered_amount ?? 0);
  const recoveryRate = useCountUp(metrics?.recovery_rate ?? 0);
  const fraudBlockRate = useCountUp(metrics?.fraud_block_rate ?? 0);
  const falseActionRate = useCountUp(metrics?.false_action_rate ?? 0);
  const medianMinutes = useCountUp(metrics?.median_time_to_recovery_minutes ?? 0);

  const state = loading
    ? "loading"
    : error
      ? "error"
      : !metrics || metrics.total_transactions === 0
        ? "empty"
        : "data";

  const tiles = metrics
    ? [
        { label: "₹ Recovered", value: formatCurrency(recoveredAmount), emphasis: true },
        { label: "Recovery Rate", value: formatPercent(recoveryRate) },
        { label: "Fraud Block Rate", value: formatPercent(fraudBlockRate) },
        { label: "False-Action Rate", value: formatPercent(falseActionRate) },
        {
          label: "Median Time to Recovery",
          value:
            metrics.median_time_to_recovery_minutes === null ? "—" : formatMinutes(medianMinutes),
        },
      ]
    : [];

  return (
    <AnimatePresence mode="wait">
      {state === "loading" && (
        <motion.div
          key="loading"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
        >
          {Array.from({ length: 5 }).map((_, i) => (
            <TileSkeleton key={i} />
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
          Could not load metrics — the backend may be unreachable.
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
          No batch generated yet. Generate a batch and run the pipeline to see metrics.
        </motion.div>
      )}

      {state === "data" && (
        <motion.div
          key="data"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
        >
          {tiles.map((tile) => (
            <Tile key={tile.label} label={tile.label} value={tile.value} emphasis={tile.emphasis} />
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
