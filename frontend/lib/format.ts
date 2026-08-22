export function formatCurrency(amount: number, currency = "INR"): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatMinutes(minutes: number | null): string {
  if (minutes === null) return "—";
  if (minutes < 60) return `${Math.round(minutes)} min`;
  return `${(minutes / 60).toFixed(1)} hr`;
}
