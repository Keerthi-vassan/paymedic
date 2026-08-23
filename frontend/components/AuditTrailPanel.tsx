"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { getTransactionAudit } from "@/lib/api";
import { rowVariants, staggerContainer, transitions } from "@/lib/motion";
import type { AuditLogEntry } from "@/types";

const EVENT_LABELS: Record<string, string> = {
  classification: "Classification",
  decision: "Decision",
  action_execution: "Action executed",
  safety_override: "Safety override",
};

function EventCard({ entry }: { entry: AuditLogEntry }) {
  const isOverride = entry.event_type === "safety_override";

  return (
    <motion.div
      variants={rowVariants}
      transition={transitions.row}
      className={`relative rounded-md border px-3 py-2.5 shadow-sm ${
        isOverride ? "border-status-blocked/40 bg-status-blocked/5" : "border-border bg-surface"
      }`}
    >
      {/* Independent of the card's own (staggered) entrance -- runs once,
          starting once entrances have settled, to draw the eye to the
          flagship "agent caught itself" moment. */}
      {isOverride && (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-md"
          initial={{ boxShadow: "0 0 0 0 rgba(220, 38, 38, 0.35)" }}
          animate={{ boxShadow: "0 0 0 8px rgba(220, 38, 38, 0)" }}
          transition={{ duration: 1, ease: "easeOut", delay: 0.3 }}
        />
      )}

      <div className="flex items-center justify-between gap-2">
        <span
          className={`text-xs font-semibold uppercase tracking-wide ${
            isOverride ? "text-status-blocked-text" : "text-muted-foreground"
          }`}
        >
          {EVENT_LABELS[entry.event_type] ?? entry.event_type}
        </span>
        <span className="text-xs text-muted-foreground">
          {new Date(entry.created_at).toLocaleTimeString()}
        </span>
      </div>

      <p className="mt-1 text-sm text-foreground">{entry.reasoning}</p>

      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {entry.root_cause && <span>root cause: {entry.root_cause}</span>}
        {entry.confidence !== null && <span>confidence: {entry.confidence.toFixed(2)}</span>}
        {entry.action_taken && <span>action: {entry.action_taken}</span>}
        {entry.attempt_number !== null && <span>attempt {entry.attempt_number}</span>}
        {entry.scheduled_at && (
          <span>next attempt scheduled: {new Date(entry.scheduled_at).toLocaleDateString()}</span>
        )}
        {entry.outcome && (
          <span className={entry.outcome === "success" ? "text-status-recovered-text" : "text-muted-foreground"}>
            outcome: {entry.outcome}
          </span>
        )}
        <span>source: {entry.source}</span>
      </div>
    </motion.div>
  );
}

export function AuditTrailPanel({
  transactionId,
  onClose,
}: {
  transactionId: string | null;
  onClose: () => void;
}) {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!transactionId) return;
    setLoading(true);
    getTransactionAudit(transactionId)
      .then((res) => setEntries(res.items))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [transactionId]);

  const isOpen = transactionId !== null;

  return (
    <>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={transitions.fade}
            className="fixed inset-0 z-40 bg-black/20"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="panel"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={transitions.panel}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-surface shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Audit Trail</h2>
                <p className="font-mono text-xs text-muted-foreground">{transactionId}</p>
              </div>
              <motion.button
                onClick={onClose}
                whileTap={{ scale: 0.9 }}
                transition={transitions.press}
                className="rounded p-1 text-muted-foreground transition-colors hover:bg-surface-muted hover:text-foreground"
                aria-label="Close"
              >
                <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                </svg>
              </motion.button>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-4">
              <AnimatePresence mode="wait">
                {loading ? (
                  <motion.div
                    key="loading"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={transitions.fade}
                    className="flex flex-col gap-2"
                  >
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div key={i} className="h-16 animate-pulse rounded-md bg-surface-muted" />
                    ))}
                  </motion.div>
                ) : entries.length === 0 ? (
                  <motion.p
                    key="empty"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={transitions.fade}
                    className="text-sm text-muted-foreground"
                  >
                    No audit events for this transaction.
                  </motion.p>
                ) : (
                  <motion.div
                    key="entries"
                    initial="initial"
                    animate="animate"
                    exit={{ opacity: 0 }}
                    variants={staggerContainer(0.06)}
                    className="flex flex-col gap-2"
                  >
                    {entries.map((entry) => (
                      <EventCard key={entry.id} entry={entry} />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
