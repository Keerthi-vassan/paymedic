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
  onGenerate,
  onRunPipeline,
}: {
  health: HealthStatus;
  generating: boolean;
  running: boolean;
  onGenerate: () => void;
  onRunPipeline: () => void;
}) {
  return (
    <header className="flex items-center justify-between border-b border-black/10 bg-chrome px-6 py-3.5">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-chrome-foreground">Paymedic</h1>
        <div className="flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[health]}`} />
          <span className="text-xs text-chrome-foreground/70">{STATUS_TEXT[health]}</span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onGenerate}
          disabled={generating}
          className="rounded-md border border-white/15 px-3 py-1.5 text-sm font-medium text-chrome-foreground transition-colors hover:bg-white/10 disabled:opacity-50"
        >
          {generating ? "Generating..." : "Generate Batch"}
        </button>
        <button
          onClick={onRunPipeline}
          disabled={running}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground transition-colors hover:opacity-90 disabled:opacity-50"
        >
          {running ? "Running..." : "Run Pipeline"}
        </button>
      </div>
    </header>
  );
}
