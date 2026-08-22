import { STATUS_DOT_CLASS, STATUS_TEXT_CLASS, statusLabel } from "@/lib/status";

export function StatusBadge({ status }: { status: string }) {
  const dotClass = STATUS_DOT_CLASS[status] ?? "bg-status-open";
  const textClass = STATUS_TEXT_CLASS[status] ?? "text-status-open";

  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${textClass}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
      {statusLabel(status)}
    </span>
  );
}
