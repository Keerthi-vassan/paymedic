# Design

<!-- impeccable:design-schema 1 -->

## World

Operate-mode B2B ops console. Restrained color strategy: warm-neutral slate ground, one brand accent, four reserved functional status colors. Built directly from `operate.md`'s Operate-mode guidance rather than a full concept-tournament — this surface's own mode guidance explicitly favors familiarity and consistency over reinvention, so the heavier Persuade/Experience-oriented process (dice-rolled cultural-reference directions, image comps) was skipped by deliberate choice, not omission. See `docs/PLAN.md` Phase 6 for that reasoning.

## Palette

Echoes Razorpay's own design system (Blade) since this is a submission built for and judged by Razorpay:

- Chrome (header): Prussian Blue `#012652`
- Accent (primary actions, selection, links): Dodger Blue `#0d94fb`
- Ground: warm-tinted neutrals, not pure black/white (`#f7f7f6` background, `#ffffff` surface, `#1a1f2b` foreground)
- Dark mode: same roles, restepped for the dark surface (see `frontend/app/globals.css`)

### Status colors (functional, never decorative)

Four reserved roles, independent of the brand accent — `open` / `recovered` / `escalated` / `blocked` must stay visually and semantically distinct (a `blocked` transaction is a retroactive safety-monitor catch, not the same thing as a routine `escalated`).

| Status | Dot/fill | Text (WCAG-AA-safe, 4.5:1+) |
|---|---|---|
| open | `#64748b` | same |
| recovered | `#16a34a` | `#15803d` (darkened — the fill alone is 3.30:1, fails as text) |
| escalated | `#d97706` | `#b45309` (darkened — the fill alone is 3.19:1, fails as text) |
| blocked | `#dc2626` | same (4.83:1, already clears) |

The fill/text split exists because the vivid fills only need to clear 3:1 as non-text graphical elements (dots, backgrounds), but several fail 4.5:1 when used as text — verified by computing actual WCAG contrast ratios, not eyeballed. See `frontend/app/globals.css`'s `--status-*-text` tokens.

## Typography

One family throughout — **Geist Sans** (headings, body, labels) + **Geist Mono** (transaction IDs, hashes — genuine data/identifiers, not a "technical" costume). Already present in the Next.js scaffold; deliberately not Inter/DM Sans (the trained-in default look), and Operate mode explicitly permits a familiar, well-tuned system-adjacent sans rather than requiring an exotic display face. Fixed rem scale, no fluid/clamp sizing. Tabular numerals (`font-variant-numeric: tabular-nums`) reserved for columns that must align (tables), not large standalone values.

## Layout

Chrome top bar (product name + live connection status + primary actions) → KPI tile row → root-cause breakdown + safety-bounds panel side by side → actions-taken table → failed-payments feed with row-click. Detail view is a **side panel** (`AuditTrailPanel`), not a modal — Operate mode explicitly discourages modal-as-first-thought for non-interrupting tasks.

## Components

Every interactive element carries default/hover/focus/disabled/loading states. Loading is skeleton blocks, never spinners-in-content. Error and empty states are visually and textually distinct (an unreachable backend reads differently from "no batch generated yet").

## Motion

Framer Motion drives every stateful transition from one shared token scale (`frontend/lib/motion.ts`): four durations (120ms micro/press, 150ms hover, 200ms base — panel slide, row enter/exit — 300ms moderate — bar-fill, crossfades), one settle curve (`cubic-bezier(0.16,1,0.3,1)`, the original bar/card curve) for entrances and growth, standard ease-out for exits and hovers. Coverage is richer than the original pass — every state swap (skeleton→content, filtered/paginated rows, panel open/close) crossfades or FLIP-reorders rather than jump-cutting, and list entrances (audit event cards, table rows) get a restrained, data-driven stagger. Still no bounce/spring overshoot, and nothing plays on load that isn't tied to a real state or data change — this is a tool people use, not a page people watch load. `MotionConfig reducedMotion="user"` (`app/page.tsx`) plus the global `prefers-reduced-motion` CSS rule (`app/globals.css`) together collapse all of the above for users who've asked for it.

## Browser surfaces

`::selection` and `:focus-visible` themed from the accent color rather than left at browser defaults.

## Provenance / process note

This build's finish review, detector run, and this document were produced as an **in-thread substitute pass** rather than through impeccable's shipped `impeccable-finish-reviewer` / `impeccable-documenter` subagents — those weren't registered in this session (the plugin was installed mid-session; Claude Code plugins require a session restart to register new skills/agents, confirmed via `claude plugin list` showing it installed-but-not-yet-loaded). The mechanical detector (`detect.mjs --json`) was run directly and returned zero findings; a manual pass against `craft-floor.md`'s Verify/Refuse checklist caught and fixed three real issues (two WCAG contrast failures on status text, table loading states using plain text instead of skeletons, unthemed browser focus/selection) before this was called finished.
