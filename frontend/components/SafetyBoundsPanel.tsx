"use client";

import { useEffect, useState } from "react";

import { getConfigRules } from "@/lib/api";
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

  if (loading) {
    return (
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-sm">
        <div className="h-4 w-32 animate-pulse rounded bg-surface-muted" />
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-6 animate-pulse rounded bg-surface-muted" />
        ))}
      </div>
    );
  }

  if (!rules) {
    return (
      <div className="rounded-lg border border-status-blocked/30 bg-status-blocked/5 p-4 text-sm text-status-blocked-text">
        Could not load safety bounds — the backend may be unreachable.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-sm">
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
          <span className="text-muted-foreground">Velocity check</span>
          <span className="tabular-nums text-foreground">
            {rules.velocity_threshold_count}+ / {rules.velocity_window_minutes}min
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Active classifier</span>
          <span className="text-foreground">{rules.llm_provider}</span>
        </div>
      </div>
    </div>
  );
}
