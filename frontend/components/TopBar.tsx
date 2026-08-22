"use client";

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
  lastRunSummary,
  onGenerate,
  onRunPipeline,
}: {
  health: HealthStatus;
  generating: boolean;
  running: boolean;
  lastRunSummary: string | null;
  onGenerate: () => void;
  onRunPipeline: () => void;
}) {
  return (
    <header className="flex items-center justify-between bg-chrome px-6 py-3.5 shadow-md">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-chrome-foreground">Paymedic</h1>
        <div className="flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[health]}`} />
          <span className="text-xs text-chrome-foreground/70">{STATUS_TEXT[health]}</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span
          className={`text-sm font-medium text-status-recovered transition-all duration-300 ${
            lastRunSummary ? "translate-x-0 opacity-100" : "translate-x-1 opacity-0"
          }`}
          aria-live="polite"
        >
          {lastRunSummary}
        </span>

        <button
          onClick={onGenerate}
          disabled={generating}
          className="rounded-md border border-white/15 px-3 py-1.5 text-sm font-medium text-chrome-foreground transition-all hover:bg-white/10 active:scale-95 disabled:opacity-50 disabled:active:scale-100"
        >
          {generating ? "Generating..." : "Generate Batch"}
        </button>
        <button
          onClick={onRunPipeline}
          disabled={running}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground transition-all hover:opacity-90 active:scale-95 disabled:opacity-50 disabled:active:scale-100"
        >
          {running ? "Running..." : "Run Pipeline"}
        </button>
      </div>
    </header>
  );
}
