"use client";

import { AnimatePresence, motion } from "framer-motion";

import { transitions } from "@/lib/motion";

type HealthStatus = "checking" | "ok" | "error";

const STATUS_DOT: Record<HealthStatus, string> = {
  checking: "bg-chrome-foreground/40",
  ok: "bg-status-recovered",
  error: "bg-status-blocked",
};

const STATUS_TEXT: Record<HealthStatus, string> = {
  checking: "Connecting...",
  ok: "Backend connected",
  error: "Backend unreachable",
};

export function TopBar({
  health,
  generating,
  running,
  runningReal,
  showRealButton,
  lastRunSummary,
  onGenerate,
  onRunPipeline,
  onRunRealPipeline,
}: {
  health: HealthStatus;
  generating: boolean;
  running: boolean;
  runningReal: boolean;
  showRealButton: boolean;
  lastRunSummary: string | null;
  onGenerate: () => void;
  onRunPipeline: () => void;
  onRunRealPipeline: () => void;
}) {
  return (
    <header className="flex items-center justify-between bg-chrome px-6 py-3.5 shadow-md">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-chrome-foreground">Paymedic</h1>
        <div className="flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full transition-colors duration-200 ${STATUS_DOT[health]}`} />
          <span className="text-xs text-chrome-foreground/70">{STATUS_TEXT[health]}</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <AnimatePresence>
          {lastRunSummary && (
            <motion.span
              key={lastRunSummary}
              initial={{ opacity: 0, x: 4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={transitions.fade}
              className="text-sm font-medium text-status-recovered"
              aria-live="polite"
            >
              {lastRunSummary}
            </motion.span>
          )}
        </AnimatePresence>

        <motion.button
          onClick={onGenerate}
          disabled={generating}
          whileHover={{ backgroundColor: "rgba(255,255,255,0.1)" }}
          whileTap={{ scale: 0.95 }}
          transition={transitions.hover}
          className="rounded-md border border-white/15 px-3 py-1.5 text-sm font-medium text-chrome-foreground disabled:opacity-50"
        >
          {generating ? "Generating..." : "Generate Batch"}
        </motion.button>
        {showRealButton && (
          <motion.button
            onClick={onRunRealPipeline}
            disabled={runningReal}
            title="Runs the small real-candidate subset against a genuine Razorpay test-mode transaction. Kept separate from Run Pipeline since it involves real network + browser-automation time."
            whileHover={{ backgroundColor: "rgba(255,255,255,0.1)" }}
            whileTap={{ scale: 0.95 }}
            transition={transitions.hover}
            className="rounded-md border border-accent/60 px-3 py-1.5 text-sm font-medium text-accent disabled:opacity-50"
          >
            {runningReal ? "Running..." : "Run Real Transactions"}
          </motion.button>
        )}
        <motion.button
          onClick={onRunPipeline}
          disabled={running}
          whileHover={{ opacity: 0.9 }}
          whileTap={{ scale: 0.95 }}
          transition={transitions.hover}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground disabled:opacity-50"
        >
          {running ? "Running..." : "Run Pipeline"}
        </motion.button>
      </div>
    </header>
  );
}
