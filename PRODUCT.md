# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: a merchant/fintech ops team member monitoring failed-payment recovery — built to be genuinely usable for that ongoing workflow, not just a one-time demo path. Secondary/evaluating audience: Razorpay AI Buildathon judges assessing an AI Builder Intern candidate via a screen-recorded 5-minute pitch video walkthrough.

## Product Purpose

Paymedic detects at-risk revenue (failed payments) and runs a bounded, auditable recovery workflow: classify the root cause (deterministic rules first, LLM fallback only for ambiguous cases), execute a capped/rule-gated recovery action, and log every step. Success means money genuinely recovered on a full batch with zero unsafe actions taken (no auto-retry on fraud, no runaway retries), and every decision explainable after the fact.

## Positioning

Unlike a free-roaming AI agent that decides and acts autonomously, Paymedic's LLM only ever emits a classification label — never a decision or an executed action. The rule-based decision engine is the sole authority on what happens to money, enforcing hard stopping rules: retry caps, fraud never auto-actioned, and a real Visa/Mastercard-grounded network compliance ceiling (~15 reattempts) enforced independently of any per-cause policy. Soft/hard decline typing is explicit, not implicit. A cross-transaction safety monitor can retroactively catch and block a transaction even after an individually-reasonable bounded action already succeeded — two independent checks now (shared payment instrument, and distinct instruments sharing an IP), not just one static rule.

## Operating Context

Backend: FastAPI + SQLite, exposing `/payments`, `/pipeline`, `/audit`, `/metrics`, `/config/rules`. Frontend: Next.js + Tailwind, calling these endpoints directly. An operator generates a simulated batch, runs the pipeline, and inspects real recovered ₹, recovery rate, root-cause breakdown, and the full audit trail per transaction — including two deliberate "agent was wrong, caught itself" cases the safety monitor catches: the original single-instrument card-testing cluster, and a second, distinct pattern (many different card instruments sharing one IP address) that only the newer IP-based cross-signal check can see.

## Capabilities and Constraints

- Live data only: every number shown must come from a real API response; nothing hardcoded or fabricated for visual polish, even for otherwise-empty states.
- LLM provider is swappable at the backend (Anthropic/OpenAI/Gemini/Sarvam) via env var; the dashboard shows which is active via `/config/rules` but has no provider-specific UI beyond that.
- No authentication/multi-tenancy in scope — single operator view.
- Transaction statuses: `open`, `recovered`, `escalated`, `blocked` (`blocked` = retroactive safety-monitor override, distinct from an ordinary rule-based `escalated`) — these four must stay visually and semantically distinct.
- Built to be genuinely operable (robust loading/error/empty states, not just a happy-path demo), but the buildathon deadline (5 Sep 2026) is a real constraint on how far that extends — no auth, no settings surface for adjusting thresholds without redeploying.

## Brand Commitments

Name: "Paymedic" (fixed, do not rename). No existing logo/visual identity yet — this record establishes product truth only; visual identity is established separately.

## Evidence on Hand

Real live pipeline run data available via the running backend (100-transaction batch, seed 42, re-run after grounding retry caps/scheduling/fraud detection in real network constraints): ~39% recovery rate, ~₹10.9L recovered, 0% recovery rate on all 13 `possible_fraud` cases (5 escalated on a plain risk-score flag, 8 caught retroactively — 4 via the single-instrument card-testing cluster, 4 via the newer distinct-instrument/shared-IP cluster), median time-to-recovery 48 hours. That last number moved deliberately from ~5 minutes in the earlier build — retries are now spaced across days (2/5/7-day backoff), matching how real dunning systems actually schedule attempts, rather than resolving a whole multi-attempt sequence in one instant. Note ~17% of rows route through live LLM classification, so re-running the same seed can shift outcome counts by roughly ±1 transaction; these are real numbers from an actual run, not placeholders — design work should always pull live rather than hardcode even these.

## Product Principles

1. Every recovery action must be explainable after the fact — audit trail over cleverness.
2. Bounded and rule-gated beats autonomous and impressive-looking — the safety story is the actual differentiator, not a caveat.
3. Real data, always — no cherry-picked or fabricated numbers, anywhere, ever.
4. Genuinely operable, not just demoable — within the constraints the deadline imposes.

## Accessibility & Inclusion

No specific requirement established beyond standard web accessibility practice. Worth noting: status color-coding here carries real meaning (not decoration), so sufficient contrast and a non-color-only distinction (icon/label) between statuses matters more than in a typical dashboard.
