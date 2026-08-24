/** Marks a row/event as backed by a genuine Razorpay test-mode transaction,
 * not the simulated hash-roll every other transaction uses. Only ever shown
 * once real_execution_verified is true -- a real candidate that fell back to
 * simulated must read as simulated everywhere in the UI, so this badge is
 * never rendered speculatively.
 */
export function RealBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent"
      title="Verified against a real Razorpay test-mode transaction"
    >
      <span className="h-1 w-1 rounded-full bg-accent" />
      Real
    </span>
  );
}
