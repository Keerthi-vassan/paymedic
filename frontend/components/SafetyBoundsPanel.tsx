"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { getConfigRules } from "@/lib/api";
import { transitions } from "@/lib/motion";
import type { ConfigRules } from "@/types";

const ACTION_LABELS: Record<string, string> = {
  retry_immediate: "Retry immediately",
  retry_with_backoff: "Retry with backoff",
  suggest_alternate_method: "Suggest alternate method",
  send_reminder: "Send reminder",
};

export function SafetyBoundsPanel({ refreshKey }: { refreshKey: number }) {
  const [rules, setRules] = useState<ConfigRules | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getConfigRules()
      .then(setRules)
      .catch(() => setRules(null))
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const state = loading ? "loading" : !rules ? "error" : "data";

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
          <div className="h-4 w-32 animate-pulse rounded bg-surface-muted" />
          {Array.from({ length: 4 }).map((_, i) => (
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
          Could not load safety bounds — the backend may be unreachable.
        </motion.div>
      )}

      {state === "data" && rules && (
        <motion.div
          key="data"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitions.fade}
          className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-sm"
        >
      <div>
        <h2 className="text-sm font-semibold text-foreground">Safety Bounds</h2>
        <p className="text-xs text-muted-foreground">
          Live config the decision engine actually enforces — not a claim.
        </p>
      </div>

      <div className="flex flex-col gap-1.5 text-sm">
        {Object.entries(rules.root_cause_actions).map(([cause, actions]) => (
          <div key={cause} className="flex items-baseline justify-between gap-2">
            <span className="text-muted-foreground">{cause.replace(/_/g, " ")}</span>
            <span className="text-right text-foreground">
              {actions.length === 0
                ? "escalate only, 0 attempts"
                : `${actions.map((a) => ACTION_LABELS[a] ?? a)[0]}, max ${actions.length} attempt${
                    actions.length > 1 ? "s" : ""
                  }`}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-1 flex flex-col gap-1 border-t border-border pt-3 text-sm">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Confidence threshold</span>
          <span className="tabular-nums text-foreground">{rules.confidence_threshold}</span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Fraud risk-score threshold</span>
          <span className="tabular-nums text-foreground">{rules.fraud_risk_score_threshold}</span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Velocity check (instrument)</span>
          <span className="tabular-nums text-foreground">
            {rules.velocity_threshold_count}+ / {rules.velocity_window_minutes}min
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Velocity check (IP, distinct instruments)</span>
          <span className="tabular-nums text-foreground">
            {rules.ip_velocity_threshold_count}+ / {rules.velocity_window_minutes}min
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Active classifier</span>
          <span className="text-foreground">{rules.llm_provider}</span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span
            className="text-muted-foreground"
            title="Self-reported LLM confidence predicts its own errors at roughly 0.627 AUROC -- barely above chance. How often independent samples agree is a substantially stronger signal, and costs only repeated calls."
          >
            Confidence scoring
          </span>
          <span className="text-right text-foreground">
            {rules.classification_samples > 1
              ? `${rules.classification_samples}-sample agreement`
              : "self-reported (single sample)"}
          </span>
        </div>
      </div>

      <div className="mt-1 flex flex-col gap-1.5 border-t border-border pt-3 text-sm">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Network compliance
        </h3>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Reattempt ceiling</span>
          <span className="tabular-nums text-foreground">
            {rules.network_retry_ceiling} attempts / instrument
          </span>
        </div>
        <div className="flex flex-col gap-1">
          {Object.entries(rules.decline_type).map(([cause, type]) => (
            <div key={cause} className="flex items-baseline justify-between gap-2">
              <span className="text-muted-foreground">{cause.replace(/_/g, " ")}</span>
              <span className={`text-right ${type === "hard" ? "text-status-blocked-text" : "text-foreground"}`}>
                {type === "hard" ? "hard — never retried" : "soft — retry-eligible"}
              </span>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Per Visa/Mastercard card-network reattempt-limit rules.
        </p>
      </div>

      <div className="mt-1 flex flex-col gap-1.5 border-t border-border pt-3 text-sm">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Retry timing
        </h3>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Quiet window (no attempts)</span>
          <span className="tabular-nums text-foreground">
            {String(rules.quiet_hours_start).padStart(2, "0")}:00 –{" "}
            {String(rules.quiet_hours_end).padStart(2, "0")}:00
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Salary-credit alignment</span>
          <span className="tabular-nums text-foreground">
            within {rules.payday_lookahead_days} days
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          Authorization success rates swing roughly 15% with time of day, and insufficient-funds
          recovers on balance refill rather than on repetition — so retries are placed, not just
          counted.
        </p>
      </div>

      <div className="mt-1 flex flex-col gap-1.5 border-t border-border pt-3 text-sm">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Ingestion
        </h3>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Razorpay webhook endpoint</span>
          <span className={rules.webhook_ingestion_enabled ? "text-status-recovered-text" : "text-muted-foreground"}>
            {rules.webhook_ingestion_enabled ? "signature-verified, live" : "not configured"}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          {rules.webhook_ingestion_enabled
            ? "Real payment.failed deliveries are HMAC-verified and enter the same pipeline as generated rows."
            : "No webhook secret set, so deliveries are refused rather than accepted unverified."}
        </p>
      </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
