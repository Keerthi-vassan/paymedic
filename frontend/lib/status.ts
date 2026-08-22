export const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  recovered: "Recovered",
  escalated: "Escalated",
  blocked: "Blocked",
};

export const STATUS_DOT_CLASS: Record<string, string> = {
  open: "bg-status-open",
  recovered: "bg-status-recovered",
  escalated: "bg-status-escalated",
  blocked: "bg-status-blocked",
};

// WCAG-AA-safe (4.5:1+) darker variants for text -- see globals.css comment.
export const STATUS_TEXT_CLASS: Record<string, string> = {
  open: "text-status-open-text",
  recovered: "text-status-recovered-text",
  escalated: "text-status-escalated-text",
  blocked: "text-status-blocked-text",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}
