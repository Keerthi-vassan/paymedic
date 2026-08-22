"use client";

import { useEffect, useRef, useState } from "react";

// Confident-arrival deceleration, not a bounce/elastic reflex curve.
function easeOutExpo(t: number): number {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

/** Animates a numeric value toward `target` on change. A focal moment, not
 * decoration -- it's how the dashboard visualizes money actually moving.
 * Skips the animation entirely under prefers-reduced-motion.
 */
export function useCountUp(target: number, durationMs = 600): number {
  const [value, setValue] = useState(target);
  const fromRef = useRef(target);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReducedMotion) {
      setValue(target);
      fromRef.current = target;
      return;
    }

    const from = fromRef.current;
    if (from === target) return;

    const start = performance.now();

    const tick = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(elapsed / durationMs, 1);
      const eased = easeOutExpo(t);
      setValue(from + (target - from) * eased);

      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = target;
      }
    };

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [target, durationMs]);

  return value;
}
