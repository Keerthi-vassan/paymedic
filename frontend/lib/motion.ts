import type { Transition, Variants } from "framer-motion";

/** One shared token scale so every stateful transition in the app draws from
 * the same rhythm instead of ad hoc per-component durations/easings. */
export const DURATION = {
  micro: 0.12, // press/tap feedback
  fast: 0.15, // hover states
  base: 0.2, // panel slide, row enter/exit
  moderate: 0.3, // bar-fill, crossfades
} as const;

export const EASE_SETTLE = [0.16, 1, 0.3, 1] as const; // confident decelerate -- entrances/growth
export const EASE_EXIT = "easeOut" as const; // quick, no lingering -- exits/hovers

export const transitions: Record<string, Transition> = {
  hover: { duration: DURATION.fast, ease: EASE_EXIT },
  press: { duration: DURATION.micro, ease: EASE_EXIT },
  panel: { duration: DURATION.base, ease: EASE_SETTLE },
  row: { duration: DURATION.base, ease: EASE_SETTLE },
  bar: { duration: DURATION.moderate, ease: EASE_SETTLE },
  fade: { duration: DURATION.base, ease: EASE_EXIT },
};

export const rowVariants: Variants = {
  initial: { opacity: 0, y: 4 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0 },
};

export function staggerContainer(staggerMs = 0.04): Variants {
  return {
    animate: { transition: { staggerChildren: staggerMs } },
  };
}
