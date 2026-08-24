"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { getClassifierMetrics } from "@/lib/api";
import { formatPercent } from "@/lib/format";
import { transitions } from "@/lib/motion";
import type { ClassifierMetrics } from "@/types";

const PATH_LABELS: Record<string, string> = {
  rule_engine: "Deterministic rules",
  llm: "LLM fallback",
  llm_error: "LLM call failed",
};

const PATH_NOTES: Record<string, string> = {
  rule_engine:
    "Graded against labels written by the same project as the rules — a high number here is close to tautological, and the interesting part is where it still misses.",
  llm: "The one path never told the error-code mapping, so this figure carries real information.",
  llm_error:
    "Forced to 'ambiguous' at zero confidence and escalated for human review. Safe, but these transactions were never actually classified.",
};

function shortCause(cause: string) {
  return cause.replace(/_/g, " ");
}

export function ClassifierAccuracyPanel({ refreshKey }: { refreshKey: number }) {
  const [metrics, setMetrics] = useState<ClassifierMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    getClassifierMetrics()
      .then(setMetrics)
      .catch(() => {
        setMetrics(null);
        setError(true);
      })
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const state = loading
    ? "loading"
    : error
      ? "error"
      : !metrics || metrics.graded === 0
        ? "empty"
        : "data";

  const llmErrors = metrics?.paths.find((p) => p.path === "llm_error")?.total ?? 0;
  // A gate that doesn't separate right answers from wrong ones is decoration.
  // Stated as a delta rather than left for the reader to subtract.
  const gateDelta = metrics
    ? metrics.above_threshold_accuracy - metrics.below_threshold_accuracy
    : 0;

  return (
    <AnimatePresence mode="wait">
      {state === "loading" && (
        <motion.div
          key="loading"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-sm"
        >
          <div className="h-4 w-40 animate-pulse rounded bg-surface-muted" />
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-6 animate-pulse rounded bg-surface-muted" />
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
          className="rounded-lg border border-status-blocked/30 bg-status-blocked/5 p-4 text-sm text-status-blocked-text"
        >
          Could not load classifier metrics — the backend may be unreachable.
        </motion.div>
      )}

      {state === "empty" && (
        <motion.div
          key="empty"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="rounded-lg border border-dashed border-border bg-surface p-4 text-center text-sm text-muted-foreground"
        >
          Run the pipeline to grade the classifier against the batch&apos;s hidden labels.
        </motion.div>
      )}

      {state === "data" && metrics && (
        <motion.div
          key="data"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 shadow-sm"
        >
          <div>
            <h2 className="text-sm font-semibold text-foreground">Classifier Accuracy</h2>
            <p className="text-xs text-muted-foreground">
              Graded against the generator&apos;s hidden <code>true_root_cause</code>, which the
              classifier never sees.{" "}
              {metrics.ungraded > 0 &&
                `${metrics.ungraded} webhook-ingested row${metrics.ungraded > 1 ? "s" : ""} excluded — real events carry no label.`}
            </p>
          </div>

          <div className="flex items-baseline gap-3">
            <span className="tabular-nums text-3xl font-semibold text-foreground">
              {formatPercent(metrics.overall_accuracy)}
            </span>
            <span className="text-xs text-muted-foreground">
              across {metrics.graded} graded transaction{metrics.graded > 1 ? "s" : ""}
            </span>
          </div>

          {llmErrors > 0 && (
            <div className="rounded-md border border-status-blocked/30 bg-status-blocked/5 p-2.5 text-xs text-status-blocked-text">
              <strong>{llmErrors}</strong> transaction{llmErrors > 1 ? "s" : ""} never reached the
              classifier — the LLM call failed and each was forced to zero confidence and escalated
              for human review. The system failed closed, but these are not classifications.
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              By path
            </h3>
            {metrics.paths.map((row) => (
              <div key={row.path} className="flex items-baseline justify-between gap-2 text-sm">
                <span className="text-muted-foreground" title={PATH_NOTES[row.path]}>
                  {PATH_LABELS[row.path] ?? row.path}
                </span>
                <span className="text-right tabular-nums text-foreground">
                  {row.total === 0 ? (
                    <span className="text-muted-foreground">not exercised</span>
                  ) : (
                    <>
                      {formatPercent(row.accuracy)}{" "}
                      <span className="text-xs text-muted-foreground">
                        ({row.correct}/{row.total})
                      </span>
                    </>
                  )}
                </span>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-1.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Confidence calibration
            </h3>
            <p className="text-xs text-muted-foreground">
              When the classifier says it is confident, is it right? This is the one question the
              system cannot answer about itself.
            </p>
            {metrics.calibration
              .filter((bucket) => bucket.total > 0)
              .map((bucket) => (
                <div
                  key={bucket.label}
                  className="flex items-center gap-2 text-sm"
                  title={`mean reported confidence ${bucket.mean_confidence.toFixed(2)}`}
                >
                  <span className="w-16 shrink-0 tabular-nums text-xs text-muted-foreground">
                    {bucket.label}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${bucket.accuracy}%` }}
                      transition={transitions.fade}
                      className="h-full rounded-full bg-accent"
                    />
                  </div>
                  <span className="w-24 shrink-0 text-right tabular-nums text-xs text-foreground">
                    {formatPercent(bucket.accuracy)}{" "}
                    <span className="text-muted-foreground">(n={bucket.total})</span>
                  </span>
                </div>
              ))}

            <div className="mt-1 rounded-md border border-border bg-surface-muted/40 p-2.5 text-xs text-muted-foreground">
              At the gate the decision engine actually enforces (confidence &lt;{" "}
              {metrics.confidence_threshold} escalates):{" "}
              <strong className="text-foreground">
                {formatPercent(metrics.above_threshold_accuracy)}
              </strong>{" "}
              accurate above it (n={metrics.above_threshold_total}) vs{" "}
              <strong className="text-foreground">
                {formatPercent(metrics.below_threshold_accuracy)}
              </strong>{" "}
              below (n={metrics.below_threshold_total}).{" "}
              {metrics.below_threshold_total === 0
                ? "Nothing fell below the gate in this batch, so it went unexercised."
                : gateDelta > 0
                  ? "The gate is separating right answers from wrong ones."
                  : "The gate is not separating right answers from wrong ones in this batch."}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Where it goes wrong
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-muted-foreground">
                    <th className="py-1 pr-3 font-medium">Actual</th>
                    <th className="py-1 pr-3 font-medium">n</th>
                    <th className="py-1 font-medium">Classified as</th>
                  </tr>
                </thead>
                <tbody>
                  {metrics.confusion.map((row) => {
                    const missed = Object.entries(row.predicted).filter(
                      ([label]) => label !== row.true_root_cause,
                    );
                    return (
                      <tr key={row.true_root_cause} className="border-t border-border">
                        <td className="py-1.5 pr-3 text-foreground">
                          {shortCause(row.true_root_cause)}
                        </td>
                        <td className="py-1.5 pr-3 tabular-nums text-muted-foreground">
                          {row.total}
                        </td>
                        <td className="py-1.5">
                          {missed.length === 0 ? (
                            <span className="text-muted-foreground">all correct</span>
                          ) : (
                            <span className="flex flex-wrap gap-1">
                              {missed.map(([label, count]) => (
                                <span
                                  key={label}
                                  className="rounded bg-status-blocked/10 px-1.5 py-0.5 text-status-blocked-text"
                                >
                                  {shortCause(label)} ×{count}
                                </span>
                              ))}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">
              Fraud read as an ordinary decline is the card-testing cluster: individually
              plausible, only visible across transactions — which is what the safety monitor
              catches after the fact.
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
