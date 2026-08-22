"use client";

import { useEffect, useState } from "react";

import { getMetricsSummary } from "@/lib/api";
import { formatCurrency, formatMinutes, formatPercent } from "@/lib/format";
import type { MetricsSummary as MetricsSummaryType } from "@/types";

interface Tile {
  label: string;
  value: string;
  emphasis?: boolean;
}

function TileSkeleton() {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
      <div className="h-3 w-20 animate-pulse rounded bg-surface-muted" />
      <div className="h-7 w-24 animate-pulse rounded bg-surface-muted" />
    </div>
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

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <TileSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-status-blocked/30 bg-status-blocked/5 p-6 text-center text-sm text-status-blocked-text">
        Could not load metrics — the backend may be unreachable.
      </div>
    );
  }

  if (!metrics || metrics.total_transactions === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm text-muted-foreground">
        No batch generated yet. Generate a batch and run the pipeline to see metrics.
      </div>
    );
  }

  const tiles: Tile[] = [
    { label: "₹ Recovered", value: formatCurrency(metrics.total_recovered_amount), emphasis: true },
    { label: "Recovery Rate", value: formatPercent(metrics.recovery_rate) },
    { label: "Fraud Block Rate", value: formatPercent(metrics.fraud_block_rate) },
    { label: "False-Action Rate", value: formatPercent(metrics.false_action_rate) },
    { label: "Median Time to Recovery", value: formatMinutes(metrics.median_time_to_recovery_minutes) },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {tiles.map((tile) => (
        <div
          key={tile.label}
          className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-4"
        >
          <span className="text-xs font-medium text-muted-foreground">{tile.label}</span>
          <span
            className={`tabular-nums ${
              tile.emphasis ? "text-2xl font-semibold text-accent" : "text-2xl font-semibold text-foreground"
            }`}
          >
            {tile.value}
          </span>
        </div>
      ))}
    </div>
  );
}
