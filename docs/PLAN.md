# Build Plan

> **Status:** Phases 1-6 complete (scaffold, simulated dataset,
> classify→decide→execute→audit pipeline, multi-provider LLM classification +
> safety monitor, metrics layer, dashboard). Phase 6.5 complete (grounding
> the decision engine's stopping rules in real Visa/Mastercard network
> constraints). Phase 6.6 complete (the real Razorpay sandbox integration
> Phase 6.5 deferred as a stretch item — built after all, see that phase).
> Phase 7 (hardening & submission prep) is next. This doc is kept in sync
> with what's actually implemented, not the original draft.

# Razorpay AI Buildathon — Revenue Recovery Agent

## Context

The user is participating in the Razorpay AI Buildathon (student-only, "Build. Show. Get hired.", deadline 5 Sep 2026). They chose the **AI Revenue Recovery** track. The bar for this track is explicit: show *actual* money recovered on a batch (not one cherry-picked example), keep every action explainable/bounded/gated (no free-roaming agent), enforce stopping rules (retry caps, no auto-action on fraud), keep a full audit trail, and — called out specifically by Razorpay as something that stands out to judges — include at least one deliberate case where the agent is wrong and catches itself.

This is a greenfield project. Decisions locked in:
- **LLM**: provider-agnostic ambiguous-case classification (`app/services/llm/`) — Anthropic (Claude Haiku), OpenAI, Gemini, and Sarvam are all implemented behind a shared interface, selected via the `LLM_PROVIDER` env var. Whichever provider is active, it is used ONLY to classify *ambiguous* root causes — never to decide or execute a money-moving action. Clear cases are handled by deterministic rules first.
- **Backend**: Python + FastAPI, exposing a REST API.
- **Frontend**: Next.js + Tailwind (the user's own preferred stack, chosen over Streamlit for build velocity since it's a stack they already know).
- **Data**: Fully simulated batch (not real Razorpay test-mode API for v1) — must be realistic, not too clean, and include a constructed "wrong action, caught by a safety check" case.
- **Containerization**: Docker Compose, two services (backend, frontend), SQLite (file-based, bind-mounted volume) for persistence — no separate DB container.

The plan below is broken into phases. **Each phase ends with a "What this gives you" summary** stating concretely what is built and what it does, so progress is checkable at every step rather than only at the very end.

## End-to-end architecture (current state)

```
Failed payment event (simulated)
   → Root-cause classifier (deterministic rules first; LLM fallback for ambiguous cases only,
                             provider swappable via LLM_PROVIDER: anthropic | openai | gemini | sarvam)
   → Recovery decision engine (rule-gated: cause → action, retry caps, fraud block, confidence threshold,
                                network compliance ceiling -- a real ~15-attempt/30-day Visa/Mastercard
                                reattempt limit, checked independently of any per-cause cap)
   → Action executor (simulated outcomes via documented per-cause probability table, seeded/reproducible;
                       retry scheduling spaced across days -- 2/5/7-day backoff -- not a flat cosmetic delay)
   → Safety monitor (runs after every action; two independent cross-transaction checks -- shared payment
                      instrument, and distinct instruments sharing one IP -- either can override a
                      transaction even after a rule-gated action was taken, marking it `blocked` rather
                      than `escalated` -- the "agent catches itself" mechanism)
   → Audit log (every step — classification, decision, execution, override — logged with reasoning,
                 timestamp, and the projected retry schedule where applicable)
   → Metrics layer (₹ recovered, recovery rate %, false-action rate, time-to-recovery)
```

The LLM never sees or controls money movement directly — it only emits `(root_cause, confidence, reasoning)` via a structured schema (strict tool-use for Anthropic, `json_schema` response format for OpenAI/Sarvam, `response_schema` for Gemini), which then feeds the independent, rule-based `decision_engine.py`. Every adapter validates the response before it reaches the decision engine — an unrecognized root cause or a failed call falls back to `ambiguous`/0 confidence, which the decision engine turns into a safe escalation rather than a wrong action. Fraud detection is always rule-based (`risk_score` threshold), never delegated to the LLM, since it's the one safety-critical branch.

---

## Phase 1 — Scaffold & wiring (Days 1-2)

Build:
- Repo skeleton: `backend/` (FastAPI app, `Dockerfile`, `requirements.txt`) and `frontend/` (Next.js + Tailwind, `Dockerfile`).
- `backend/app/main.py` with a single `GET /health` route and CORS enabled for the frontend origin.
- `backend/app/config.py` (pydantic Settings: API keys, DB path, thresholds) and `backend/app/db.py` (SQLAlchemy engine/session pointed at a SQLite file under `backend/data/`).
- Next.js placeholder `app/page.tsx` that fetches `/health` and displays connection status.
- Root `docker-compose.yml` (backend on 8000, frontend on 3000, bind-mount `./backend/data`, `depends_on`), `.env.example`, `.gitignore`.

**What this gives you:** a working two-container app — `docker compose up --build` from a clean clone brings up both services, and the browser shows the frontend successfully talking to the backend. No business logic yet; this phase exists purely so every later phase has something running to plug into, and so the "clean clone and run" judge experience is proven early rather than left to Day 13.

---

## Phase 2 — Simulated data (Days 3-4)

Build:
- `backend/app/models.py`: SQLAlchemy `FailedPayment` model — `transaction_id, customer_id, amount (paise), currency, payment_method, payment_instrument_id, issuer_bank, error_code, error_source, error_step, error_reason, failed_at, network_type, latency_ms, risk_score, true_root_cause, status, final_action, total_attempts, recovered_amount (paise), resolved_at`. Error fields mirror Razorpay's real Payment entity shape (coarse `error_code` enum + `error_source`/`error_step`/fine-grained `error_reason`) rather than a flat invented code+description pair; amounts are integers in paise, matching Razorpay's real subunit convention.
- `backend/scripts/generate_dataset.py`: seeded, Faker-based generator producing 100 rows with a realistic weighted mix across all 6 root causes, ~17% deliberately ambiguous rows (masked `error_reason` — designed to defeat every deterministic rule later), and a constructed cluster: 4 transactions sharing one `payment_instrument_id`, small increasing amounts, minutes apart, each individually tagged with an innocuous-looking `error_reason` (`gateway_timeout_error`) and a risk_score safely under the fraud threshold — this cluster is the seed of the flagship "agent was wrong" case built in Phase 4. Uses a fixed reference timestamp so the whole batch, including every `failed_at`, is byte-identical across runs for the same `(count, seed)`; the API/UI default omits `seed` for a genuinely random batch each generate, while `seed=42` remains available as an explicit reproducible/demo path.
- `routers/payments.py`: `POST /payments/generate`, `GET /payments` (filterable/paginated), `GET /payments/{id}`.
- Frontend `FailedPaymentsFeed.tsx` rendering the raw feed, with a "Generate Batch" control and status/root-cause filters.

**What this gives you:** a real, inspectable batch of 100 simulated failed payments sitting in SQLite and visible in the dashboard — the raw material every later phase (classification, decisions, metrics) operates on. This is also the point where you can eyeball the dataset and confirm it's "not too clean."

---

## Phase 3 — Classification → decision → execution → audit (Days 5-6)

Build:
- `services/classifier.py`: deterministic `error_reason` matching for 5 root causes (Razorpay's real `error_code` is too coarse a 3-value enum on its own to drive 6-way classification), plus the hard rule `risk_score >= 0.85 → possible_fraud` (never LLM-decided). Unmatched/masked reasons route to the LLM fallback (wired in Phase 4).
- `services/decision_engine.py`: pure, unit-testable function — cause→action table with per-cause max-retry caps (e.g. `gateway_timeout` retry up to 3, `possible_fraud` 0 attempts allowed), check order: fraud flag → escalate; confidence below threshold (0.6) → escalate; retry cap reached → escalate; else map to action.
- `services/executor.py`: seeded, documented probability table per (root_cause, attempt_number) simulating retry/action outcomes (e.g. gateway_timeout retry succeeds 65%/40%/20% across attempts — diminishing because genuine outages don't fix on blind retry). Outcomes are deterministic per `(transaction_id, attempt_number)` via hashing, so re-running the pipeline reproduces identical results regardless of batch order.
- `services/audit.py` + `audit_log` SQLite table (`transaction_id, source, root_cause, confidence, action_taken, reasoning, outcome, attempt_number, created_at`) — one row per pipeline step.
- `app/pipeline.py` orchestrating classify→decide→execute→log; `routers/pipeline.py`: `POST /pipeline/run` (batch/subset), `POST /pipeline/run/{id}` (single transaction); `routers/audit.py`: `GET /audit`, `GET /audit/{id}`.
- `backend/tests/test_decision_engine.py`, `test_executor.py`: prove fraud is never retried and caps are never exceeded.

**What this gives you:** the full bounded-recovery loop working end-to-end for every clear-cut case in the batch — you can `POST /pipeline/run` over the 100 rows and get real ₹-recovered outcomes with a full audit trail per transaction, demoable via curl/Postman even before the LLM or dashboard exist. This is the core "prove it on a batch" mechanism the judges are scoring.

---

## Phase 4 — LLM classification + safety monitor (Days 7-8)

Build:
- `app/services/llm/`: a shared `LLMProvider` interface (`base.py`) plus four adapters — `anthropic_provider.py` (Claude Haiku, strict tool-use), `openai_provider.py` (`gpt-5-mini`, `json_schema` response format), `gemini_provider.py` (`gemini-flash-latest`, `response_schema` — note Gemini's schema is a stricter OpenAPI subset than standard JSON Schema, so it needs its own schema definition, not the shared one), and `sarvam_provider.py` (`sarvam-105b`, via the OpenAI SDK pointed at Sarvam's OpenAI-compatible endpoint). A factory (`llm/__init__.py`) picks the active one from `settings.llm_provider`. Every adapter shares one system prompt and validates its response (`validate_classification`) before returning it — malformed output or an unrecognized root cause becomes `ambiguous`/0 confidence rather than reaching the decision engine.
- `classifier.py` calls the active provider for unmatched error codes; any exception (auth failure, rate limit, network error) is caught and also falls back to `ambiguous`/0 confidence with the error logged, so the system fails closed rather than crashing or guessing.
- `services/safety_monitor.py`: runs after every action_execution, independently scans recent activity per `payment_instrument_id` within a configurable time window; when it detects `settings.velocity_threshold_count`+ actioned transactions on one instrument, it retroactively overrides *all* of them (including ones already marked `recovered`) — writes a `safety_override` audit row per transaction, zeroes any recovered amount, and sets status to `blocked` (a status distinct from ordinary `escalated`, so the dashboard can tell a retroactive safety catch apart from a routine rule-based escalation).
- `backend/tests/test_classifier.py` (rule matching, fraud override, LLM routing and failure fallback via a stub provider — no real API calls in tests), `test_safety_monitor.py` (threshold, time window, unrelated-instrument isolation, idempotency).

**What this gives you:** the two hardest, most judge-visible pieces of the whole build — (1) ambiguous cases are now handled by a real, swappable LLM instead of blanket-escalating, and (2) the flagship "agent was wrong, caught itself" transaction cluster now actually produces the sequence: confident classification → bounded retry action → success → `safety_override` audit event → `blocked` status, fully reconstructable from the audit log alone. Verified live against a real Gemini API key: classification, schema validation, and the safe-fallback-on-error path all confirmed working end-to-end (one real bug found and fixed along the way — Gemini's schema format needed its own adapter-specific definition).

---

## Phase 5 — Metrics (Days 9-10)

Build:
- `services/metrics.py`: `total_at_risk_amount`, `total_recovered_amount`, `recovery_rate`, `escalation_rate`, `blocked_rate`, `false_action_rate` (blocked / actioned transactions), `fraud_block_rate` (of all `true_root_cause == possible_fraud` cases — obvious and disguised — the % that ended `escalated` or `blocked`, i.e. never recovered), mean/median `time_to_recovery`. Also a per-root-cause breakdown and a cumulative-₹-recovered timeline.
- `routers/metrics.py`: `GET /metrics/summary`, `GET /metrics/root-cause-breakdown`, `GET /metrics/timeline`.
- `routers/config_rules.py`: `GET /config/rules` — renders the same cause→action/caps/threshold config the decision engine actually uses, so the "here are the bounds" claim is provably real, not just asserted.
- `backend/tests/test_metrics.py`: rate calculations, empty-batch edge case, root-cause grouping, timeline ordering.
- Bug found and fixed along the way: `resolved_at` was being set to real wall-clock time while `failed_at` is a backdated synthetic timestamp, making `time_to_recovery` measure "days since the dataset was generated" instead of anything meaningful. Fixed with a synthetic, deterministic resolution delay per action type (`executor.resolution_delay_minutes`) — immediate retries resolve in ~1 min, backoff retries in ~20 min, nudges in ~4 hours — so `resolved_at = failed_at + elapsed delay`.

**What this gives you:** every number the pitch video and README need — ₹ recovered, recovery rate %, false-action rate, time-to-recovery — computed live from the batch via API, plus a machine-readable proof of the safety bounds for judges to inspect directly. Verified on a real run: `possible_fraud` shows a hard 0% recovery rate across both the obviously-flagged and the disguised card-testing cases, and time-to-recovery now reads as realistic minutes (median ~5 min) instead of an artifact of dataset generation time.

---

## Phase 6 — Dashboard (Days 11-12)

### Design tooling setup (before any component code)

Wanted the dashboard to be genuinely well-designed rather than default AI-generated-looking output, so design tooling was set up and researched (not assumed) before writing any component code:
- **Installed `impeccable`** (github.com/pbakaus/impeccable) — a real, actively maintained design-anti-slop skill for AI coding agents: 23 commands (`/polish`, `/audit`, `/typeset`, etc.), 59 automated checks against generic AI defaults, requires a `PRODUCT.md`/`DESIGN.md` design-context step before generating UI. Installed via the Claude-Code-native path (`/plugin marketplace add pbakaus/impeccable` + `/impeccable init`), not the generic cross-harness installer.
- **No MCP servers.** Considered Tailwind MCP (mostly community utility-class lookups, or Flowbite's official one bundling a pre-built component kit) and Framer MCP (syncs code *from* an existing Framer canvas project). Neither adds value here — Tailwind is already well understood without a lookup server, a pre-built kit like Flowbite works against impeccable's whole purpose of rejecting generic/templated defaults, and there's no existing Framer file to sync from.

Build:
- `PRODUCT.md` — audience, purpose, positioning, constraints, captured via impeccable's structured init interview (deliberately: "genuinely operable, not just demoable" over pure demo-optimization, per explicit direction).
- `DESIGN.md` — Razorpay Blade-aligned palette (Prussian Blue `#012652` chrome, Dodger Blue `#0d94fb` accent — this is a submission built for and judged by Razorpay), restrained neutrals, Geist Sans/Mono, functional status colors independent of brand.
- `RootCauseBreakdown.tsx`: used the `dataviz` skill's "emphasis form" guidance — `possible_fraud`'s 0% recovery rate is a deliberate safety guarantee, not a performance shortfall, so it's pulled out as a distinct annotated card (icon + label + explanation) rather than color-ranked alongside the other 5 categories on a shared magnitude scale, which would have misread it as a failure.
- `MetricsSummary.tsx` (KPI tiles), `ActionsTakenTable.tsx` (every bounded action executed, batch-wide), `AuditTrailPanel.tsx` (side panel, not modal — chronological per-transaction timeline with `safety_override` visually distinct), `SafetyBoundsPanel.tsx` (renders the live `/config/rules` data, labeled/formatted for readability rather than a raw JSON dump — see Phase 6.5 for the network-compliance section added later). `FailedPaymentsFeed.tsx` gets row-click-to-open-audit-panel.
- Self-review against the skill's `craft-floor.md` checklist (mechanical detector: zero findings) caught and fixed 3 real issues before calling it done: two WCAG contrast failures (status-recovered and status-escalated text were 3.30:1/3.19:1 on white, below the 4.5:1 AA floor — fixed with darker text-only variants, verified by computing exact contrast ratios), plain "Loading..." text upgraded to skeleton rows in two tables, and browser-default focus ring/text selection themed from the accent color.
- **Polish pass** (user feedback: "colors are solid, no micro-interactions") — mapped to impeccable's `bolder`/`animate` guidance rather than freehand changes. Depth: soft elevation shadows throughout (previously border-only), a subtle same-hue gradient on chart bars, accent-tinted background on the emphasized ₹-Recovered tile. Micro-interactions: KPI numbers count up on load/change (`lib/useCountUp.ts`, respects `prefers-reduced-motion`), root-cause bars grow in from 0 on data change, button press feedback, a brief inline success toast after Generate Batch/Run Pipeline, richer row hover, and a one-time entrance pulse specifically on the `safety_override` card. Global `prefers-reduced-motion` CSS override added. Re-ran the mechanical detector after — zero findings.

**What this gives you:** the actual thing judges click through — a legible, non-cherry-picked, genuinely well-designed view of the whole batch's outcomes. Screenshot-verified: the flagship card-testing cluster shows the full sequence (confident `gateway_timeout` classification → bounded retry → success → red `SAFETY OVERRIDE` card with the exact velocity-detection reasoning) live in the audit panel, ready to screen-record for the pitch video.

---

## Phase 6.5 — Grounding stopping rules in real network constraints

Prompted by a deep-research pass (kept outside the repo, at the parent directory of `paymedic/`) into how real payment-recovery systems and card networks actually work: the project's stopping rules were internally consistent but self-authored — invented per-cause retry caps, a flat cosmetic delay model, a single-signal fraud check — rather than grounded in the constraints Visa/Mastercard and the industry actually publish and enforce. Three changes converted already-correct-by-accident behavior into explicitly cited, on-screen-legible policy, without touching the "no real money" boundary already committed to:

- `decision_engine.py`: added `DECLINE_TYPE` (soft/hard per root cause — purely additive labeling, no behavior change, since `card_declined`/`possible_fraud` already got zero same-instrument retries) and one new check — `attempts_so_far >= settings.network_retry_ceiling` (15, the real Visa/Mastercard ~15-attempt/30-day reattempt-limit rule) → escalate, citing the rule by name. Positioned between the fraud checks and the confidence check specifically because every per-cause cap tops out at 3 — placed after the per-cause-cap check instead, it would be permanently unreachable.
- `executor.py`: `resolution_delay_minutes` is now keyed by `(action, attempt_number)` instead of action alone — backoff retries escalate 2/5/7 days across attempts (a full `gateway_timeout` sequence lands ~12 days out, inside the industry's "3-5 attempts over 10-14 days" pattern) instead of a flat 20 minutes. `pipeline.py` now writes the projected `scheduled_at` onto the "decision" audit event.
- `safety_monitor.py`: a second, independent check — 3+ *distinct* payment instruments sharing one IP within the velocity window (not raw row count, so one customer retrying their own card doesn't false-positive) — runs alongside the original single-instrument check. Both always run; a transaction matching both is only overridden once (relies on SQLAlchemy's default autoflush so the second check sees the first's pending status change).
- `generate_dataset.py`: every row now carries a synthetic `ip_address` (RFC 5737 documentation ranges only). Two new always-present engineered cases, so all three mechanisms have an actual on-screen demo moment rather than only being reachable in a unit test: a 4-row IP-velocity cluster (distinct cards, one shared IP — the inverse of the existing single-instrument cluster) and a single row pre-seeded at `total_attempts = network_retry_ceiling` to trigger the new compliance check on its very first pass.
- Frontend: `SafetyBoundsPanel.tsx` gained a **Network compliance** section (decline-type map, reattempt ceiling, citation) and a second velocity-check row; `AuditTrailPanel.tsx` shows a "next attempt scheduled" line on decision events that didn't escalate. Both are additive uses of the existing panel/badge patterns — no new visual language.
- Backend: 35/35 tests passing (11 new, including a fix to two pre-existing test helpers — `test_classifier.py`, `test_metrics.py` — that constructed `FailedPayment` rows directly and would have broken once `ip_address` became a required column).

**Deferred at the time as a stretch item**: real Razorpay test-mode sandbox integration (blending a small number of real API-driven transactions into the batch). The research found Razorpay's UPI Collect flow — the simplest, pure-API-call path for this — was deprecated February 2026. Built anyway immediately after, in Phase 6.6 below, via a different (netbanking + mock-bank-page) path.

**What this gives you:** every stopping rule in the demo is now citable against a real, external constraint rather than an internal judgment call — the kind of grounding that reads very differently to judges who operate the real version of this system. Verified live via Docker and a real browser: the network-ceiling escalation, both safety-override clusters (4 instrument-based, 4 IP-based), and the "next attempt scheduled" badge all render correctly. One expected, deliberate side effect: median time-to-recovery moved from ~5 minutes to 48 hours, and the frozen `seed=42` numbers below reflect the new run — not a regression, the realistic-scheduling change working as intended.

**Updated frozen `seed=42` numbers** (100 transactions, re-run after this phase): 39% recovery rate, ₹10,90,085 recovered, 100% fraud block rate (13 fraud-labeled transactions: 5 escalated on a plain risk-score flag, 8 caught retroactively — 4 single-instrument, 4 IP-based), 9.88% false-action rate, 48 hr median time-to-recovery, 39 recovered / 53 escalated / 8 blocked. Not yet written into any submission doc (there isn't one yet — see Phase 7). Note: ~17% of rows route through live LLM classification, so re-running the same seed can shift outcome counts by roughly ±1 transaction.

---

## Phase 6.6 — Real Razorpay test-mode execution (the deferred stretch item, built)

Picked back up the same session, once real Razorpay test-mode credentials were available. Confirmed live against the actual Razorpay sandbox that the "obvious, easy" path assumed in Phase 6.5's research doesn't exist in its simple form, then built and validated a working alternative end-to-end.

**What actually works, and how it was found** (Razorpay's exact Checkout DOM isn't public API, so every step below was discovered by driving the live widget and reading real screenshots/DOM dumps, not by guessing from memory):
- A small, fixed-count subset of each batch (`RAZORPAY_REAL_TXN_COUNT`, default 4) is marked `FailedPayment.is_real=True` at generation time — always `payment_method="netbanking"`, root cause restricted to `gateway_timeout`/`network_drop`/`auth_failure` (multi-attempt causes, so there's an actual retry sequence to demonstrate; `card_declined`/`possible_fraud`/`insufficient_funds` all cap at 1 action, nothing to route through a real attempt), identifiers kept fresh so these rows can never collide with the safety-monitor fraud clusters. Off by default (`RAZORPAY_EXECUTION_ENABLED=false`) — with it off, `generate_dataset.py`'s output is byte-identical to before this phase existed.
- `app/services/execution/razorpay_client.py`: a thin `httpx` wrapper around Razorpay's real Orders/Payments REST API (Basic Auth, test-mode key_id/key_secret) — `create_order`, `fetch_order_payments`, `fetch_payment`. No local simulation anywhere in this module.
- `app/services/execution/harness.py`: a minimal page (`GET /internal/checkout-harness`, not a documented API endpoint) that embeds Razorpay's real Checkout.js SDK and auto-opens it for a given order — needed because Checkout.js is meant to be embedded in a merchant's own page, not hosted standalone.
- `app/services/execution/browser_driver.py`: a headless Playwright/Chromium session that clicks through the *real* Checkout widget. Three real findings from live debugging, each would have been a guess otherwise:
  1. Razorpay's checkout shows a blocking "Contact details" modal requiring a mobile number even with `prefill.contact` set, and — confirmed live — rejects obviously-fake numbers like `9999999999` (repeated digit) and `9876543210` (sequential) as "invalid" even in test mode; a normal scrambled-looking number passes.
  2. Netbanking's bank list is real bank names (Bank of Baroda, Canara Bank, PNB, IDBI...), not a literal "Test Bank" entry — any of them routes to a mock bank page in test mode. One suggested bank displayed its own "currently facing issues" warning live; picking a different one avoided it.
  3. The actual mock bank page (`api.razorpay.com/v1/gateway/mocksharp/payment`, titled "Razorpay Bank", literally `<button data-val="S">Success</button>` / `data-val="F">Failure</button>`) opens as a **genuine new browser popup**, not a redirect within the checkout iframe — the reason earlier attempts here silently hung indefinitely on Razorpay's own "Confirming Payment" transition screen.
- `app/services/execution/__init__.py` (`attempt_real_execution`): orchestrates the above, targeting whichever outcome the *same* deterministic simulated hash-roll (`executor.execute`) already decided — keeps `seed=42` reproducibility intact even for real candidates, and gives the browser a concrete button to aim for. After the browser reports it clicked Success/Failure, **the actual outcome is read back from Razorpay's own Orders API** (`fetch_order_payments`, polled for a terminal `captured`/`failed` status), not trusted from the checkout widget's client-side JS callback — confirmed live that callback is unreliable under headless automation (a payment was genuinely `captured` server-side while the page's own `document.title` signal never fired). Any failure anywhere in this chain (API unreachable, browser automation breaks) falls back to the exact same simulated outcome every other transaction uses, `real_execution_verified=False` — a broken real-execution attempt degrades that one transaction back to 100% simulated rather than blocking the pipeline.
- `pipeline.py`: only the *first* bounded action of an `is_real` transaction goes through this path; every later retry on that transaction, and every other transaction, uses the simulated path as before. The audit trail's `action_execution` event carries `execution_source`/`gateway_order_id`/`gateway_payment_id`/`gateway_status` and a reasoning string that says outright whether this was a verified real transaction or a fallback.
- Docker: switched the backend's base image from `python:3.12-slim` to Playwright's own `mcr.microsoft.com/playwright/python:v1.49.0-jammy` — Playwright's `--with-deps` OS-package installer doesn't yet know Debian trixie (`python:3.12-slim`'s current base) and fails on renamed font packages there; Playwright's own image ships Chromium plus every OS dependency pre-verified.

**Verified live** (2026-08-24, real test-mode credentials): both a genuine `captured` payment and a genuine `failed` payment obtained end-to-end through the full browser-driven flow, each in 15-20 seconds; a full 100-transaction batch (4 real candidates) processed correctly through `POST /pipeline/run` with `RAZORPAY_EXECUTION_ENABLED=true`, producing real `pay_...`/`order_...` IDs in the audit trail; the default-disabled state re-confirmed byte-identical in shape afterward (0 `is_real` rows, same recovered/escalated/blocked distribution as before this phase). Backend: 41/41 tests passing (3 new, covering the fallback-to-simulated guarantee — the one property that must always hold regardless of what Razorpay or the browser automation does).

**What this gives you**: at least 4 transactions in every batch (when enabled) aren't simulated at all — they're real orders and real payments in Razorpay's own test-mode system, reachable and independently verifiable via Razorpay's own dashboard, going through the exact same classify→decide→execute→audit pipeline as everything else. For a submission judged by the team that built Razorpay's real payment infrastructure, that's a materially different claim than "the whole system is simulated."

---

## Phase 6.7 — Close the research-to-code gaps: measurement, timing, dunning, ingestion

A pass driven by re-reading the project's own research notes against the code and
finding places where the two disagreed, plus one stated requirement that had never been
met.

**The unmet requirement.** The build plan called for tracking classification accuracy
from Days 3-5, and the README's own must-include list named accuracy as a headline
metric. Nothing measured it. `true_root_cause` sat on every row and was read only for
fraud-block rate. `GET /metrics/classifier` now grades classification against that
hidden label: overall accuracy, a per-path split (deterministic rules / LLM fallback /
failed LLM call), a confusion matrix, and a confidence-calibration table reporting
accuracy either side of the gate the decision engine actually enforces.

**What that measurement immediately found**, on its first real run — which is the
argument for having built it:
- **0 of 8 true fraud cases were classified as fraud** (5 read as `gateway_timeout`,
  3 as `card_declined`). Not a bug: that is the card-testing clusters behaving exactly
  as card testing does, and it is the quantitative statement of why the per-transaction
  classifier cannot be the last line of defence. The metric and the flagship demo case
  turn out to be the same finding.
- **14 transactions never reached the classifier at all** — the configured provider's
  free-tier quota was exhausted, every ambiguous row's LLM call 429'd, and each was
  forced to zero confidence and escalated. The fail-closed path worked perfectly and
  was completely invisible before this endpoint existed. The dashboard now shows it as
  a warning rather than letting it read as ordinary escalations.

**A metric that didn't mean what it said.** `false_action_rate` was `blocked / actioned`
— which counts only mistakes the system's own safety monitor happened to catch, so any
wrong action the monitor misses is invisible to it and the number can only ever flatter
us. It is now graded against ground truth (any action on a true fraud case, or any retry
against a true hard decline — the combination card networks fine merchants for). The old
measurement is kept, honestly renamed `safety_override_rate`.

**Two research-to-code disagreements in the retry policy.**
- `insufficient_funds` had one reminder and *no retry at all*, despite being ~34% of
  failed recurring payments, the largest bucket and the most time-recoverable — nothing
  about the customer's intent failed, their balance was short at that moment. Now
  notify → retry → retry, landing ~13 days out, inside the 3-5 attempts / 10-14 day
  envelope.
- Retry *timing* was attempt-indexed only, so an attempt landed at whatever clock time
  the original failure happened at, including 3am — despite the research noting a ~15%
  success swing with time of day, and both Stripe Smart Retries and Razorpay's own
  Intelligent Payment Retry being fundamentally about choosing the moment. New
  `retry_scheduler` moves day-scale attempts out of a quiet window and pulls
  `insufficient_funds` retries onto a nearby salary-credit date, bounded so it can only
  nudge rather than push past the envelope. Adjustments are appended to the decision's
  audit reasoning.

**Dunning is now real copy, not a label.** `send_reminder` produced nothing an operator
could read. `notifier` drafts the actual customer-facing message: template-first, with
the LLM only ever rewriting the template (not the message — `{amount}` stays a
placeholder and is substituted afterwards, so the model never sees a real amount, one
rewrite serves the whole batch, and the guard can reject *every digit* rather than
adjudicating which numbers were legitimate). Guard violations, LLM errors and empty
responses all fall back to the template verbatim with the reason recorded. The exact
copy sent is stored on the audit event.

**Event-driven ingestion.** `POST /webhooks/razorpay` accepts the real `payment.failed`
event, HMAC-SHA256 verified over the raw body in constant time, verified before parsing,
refusing everything when no secret is configured rather than falling open. Redelivery is
idempotent on the payment id. This is where mirroring Razorpay's real Payment entity in
the synthetic schema pays off — the error fields copy straight across. Real rows carry
no ground-truth label and no risk score, both recorded on the row rather than guessed,
and both excluded from the metrics that would otherwise silently misreport them.

**Robustness finding, from the quota exhaustion above.** A rate-limited provider turned
a ~10s batch into **2m49s** of invisible SDK backoff — the SDKs honour a 429's
retry-after and keep going, so the pipeline appears to hang rather than fail. Every
provider client now has a bounded timeout and retry cap. Measured against the same
genuinely quota-exhausted key: **2m49s → 35s**. Failing fast is correct here, since the
classifier's fail-closed path already turns an error into a safe escalation.

**Also in this pass:** CI (`.github/workflows/ci.yml`) running the backend suite plus
frontend typecheck/lint/build on every push; tests asserting the three parallel policy
tables stay aligned and that no hard decline is ever assigned a retry; a corrected
`safety_monitor` docstring (it credited autoflush for the double-override dedup, but
`SessionLocal` disables autoflush — the guard actually holds because `audit.log_event`
commits each override as it is written); and a `StaticPool` fix in the test fixture,
without which a TestClient-driven test writes to a different in-memory database than it
asserts against.

**Backend: 93 tests passing** (was 44).

**Follow-up in the same session: self-consistency, built.** Initially descoped again,
then picked up -- it is the only change that turns the confidence number into a
measurement rather than an assertion, and it is the sharpest question the submission
invites ("how is confidence even generated?").

Each ambiguous transaction is now classified `CLASSIFICATION_SAMPLES` times (default 3)
and confidence is scored by inter-sample agreement, at
`min(agreement, mean self-report among the winning votes)` -- the more pessimistic of
the two signals, so neither can inflate the other. The case it exists to catch is a
model that answers differently every time while insisting on 0.99 each time: under
self-report it clears the 0.6 gate and a bounded action is taken on a coin flip; under
agreement it escalates. Ties escalate with no special-casing (3 samples / 3 answers =
0.33; 4 split 2-2 = 0.50).

`CLASSIFICATION_SAMPLES=1` reproduces the old single-sample behaviour exactly, which is
what makes the before/after comparison honest -- run the same batch both ways and diff
the calibration table. Costs 3x the requests on the ~17% of rows that reach the LLM,
and depends on the provider sampling non-deterministically (all four adapters use
non-zero default temperature; pinning it to 0 makes agreement trivially 1.0 and the
measurement meaningless). Both caveats are in the README.

**Backend: 101 tests passing.**

**Metrics need re-freezing.** The `seed=42` run recorded in the README was made while
the provider quota was exhausted, so it reflects a degraded classifier. Re-run and
re-freeze before the pitch video.

---

## Phase 7 — Hardening & submission prep (Days 13-15)

Build:
- Day 13: finalize `docker-compose.yml`, run a clean-clone smoke test, add a one-click "Run Pipeline" control in the UI.
- Day 14: `README.md` (problem statement, architecture diagram from `docs/architecture.md`, metrics from a fixed-seed run, setup/run instructions, explicit safety-bounds/stopping-rules section) — freeze demo numbers so the video and README match exactly.
- Day 15: record the 5-minute pitch video (30s problem, 30s approach, 2min live demo including the deliberate failure case, 1min architecture/safety, 1min future work); buffer for last fixes; submit.

**What this gives you:** a submission-ready public repo — clean clone runs with one command, README and video tell a consistent story backed by the same frozen numbers, and the judged criteria (audit trail, bounded actions, batch metrics, deliberate failure case) are each independently pointable-to in the running app.

---

## Verification

- Unit tests (`backend/tests/`, 41 passing) assert: fraud-flagged transactions are never retried; retry caps are never exceeded, including the network compliance ceiling independent of any per-cause cap; low-confidence classifications always escalate rather than act; the safety monitor triggers only at threshold on either signal (shared instrument, or distinct instruments sharing an IP), respects the time window, ignores unrelated instruments, doesn't reprocess already-blocked transactions, and doesn't double-log a transaction matching both patterns; retry scheduling escalates correctly across attempts; `scheduled_at` is populated exactly when the engine doesn't escalate; real-candidate rows are absent when Razorpay execution is disabled and present with the right count/constraints when enabled; a real-execution attempt falls back to the exact simulated outcome (not verified, not blocking) if the Razorpay API or the browser automation fails at any point.
- Real-execution end-to-end behavior (order creation, browser-driven checkout, outcome polling) was verified live against Razorpay's actual test-mode API rather than mocked — see Phase 6.6. Re-verify manually after any Razorpay Checkout UI change, since the browser driver depends on undocumented DOM structure.
- `docker compose up --build` from a clean clone should bring up both services and let the dashboard load real data end-to-end — re-run before every phase boundary, not just at the end.
- **Manually confirmed** (not just assumed from the code) that the constructed card-testing transaction cluster, viewed via `GET /audit/{transaction_id}` and the dashboard's `blocked` status filter, shows: initial confident classification → bounded retry action → success → `safety_override` audit event → `blocked` status. This is the flagship "agent was wrong, caught itself" demo moment.

## Critical files

- `backend/app/services/decision_engine.py`
- `backend/app/services/classifier.py`
- `backend/app/services/llm/` (`base.py`, `anthropic_provider.py`, `openai_provider.py`, `gemini_provider.py`, `sarvam_provider.py`, `__init__.py`)
- `backend/app/services/safety_monitor.py`
- `backend/app/services/executor.py`
- `backend/app/services/retry_scheduler.py` (when a scheduled attempt lands)
- `backend/app/services/notifier.py` (customer copy + content guard)
- `backend/app/services/metrics.py` (batch metrics + classifier grading/calibration)
- `backend/app/services/ingest.py`, `backend/app/routers/webhooks.py` (real webhook ingestion)
- `backend/app/pipeline.py`
- `backend/app/config.py` (every threshold, including the network compliance ceiling and the real-execution settings)
- `backend/app/services/execution/` (`razorpay_client.py`, `harness.py`, `browser_driver.py`, `__init__.py`) — the real Razorpay test-mode integration, off by default
- `backend/scripts/generate_dataset.py`
- `backend/app/models.py`
- `backend/Dockerfile` (Playwright's own base image, not `python:3.12-slim`)
- `docker-compose.yml`
- `.github/workflows/ci.yml`
