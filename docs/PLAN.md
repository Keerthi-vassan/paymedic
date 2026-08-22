# Build Plan

> **Status:** Phases 1-6 complete (scaffold, simulated dataset,
> classify→decide→execute→audit pipeline, multi-provider LLM classification +
> safety monitor, metrics layer, dashboard). Phase 7 (hardening & submission
> prep) is next. This doc is kept in sync with what's actually implemented,
> not the original draft.

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
   → Recovery decision engine (rule-gated: cause → action, retry caps, fraud block, confidence threshold)
   → Action executor (simulated outcomes via documented per-cause probability table, seeded/reproducible)
   → Safety monitor (runs after every action; detects cross-transaction patterns like card-testing velocity;
                      can override a transaction even after a rule-gated action was taken, marking it `blocked`
                      rather than `escalated` -- the "agent catches itself" mechanism)
   → Audit log (every step — classification, decision, execution, override — logged with reasoning + timestamp)
   → Metrics layer (₹ recovered, recovery rate %, false-action rate, time-to-recovery)  [Phase 5, next]
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
- `backend/app/models.py`: SQLAlchemy `FailedPayment` model — `transaction_id, customer_id, amount, currency, payment_method, payment_instrument_id, issuer_bank, error_code, error_description, failed_at, network_type, latency_ms, risk_score, true_root_cause, status, final_action, total_attempts, recovered_amount, resolved_at`.
- `backend/scripts/generate_dataset.py`: seeded, Faker-based generator producing 100 rows with a realistic weighted mix across all 6 root causes, ~17% deliberately ambiguous rows (masked error codes, generic descriptions — designed to defeat every deterministic rule later), and a constructed cluster: 4 transactions sharing one `payment_instrument_id`, small increasing amounts, minutes apart, each individually tagged with an innocuous-looking `error_code` (`GATEWAY_TIMEOUT`) and a risk_score safely under the fraud threshold — this cluster is the seed of the flagship "agent was wrong" case built in Phase 4. Uses a fixed reference timestamp so the whole batch, including every `failed_at`, is byte-identical across runs for the same `(count, seed)`.
- `routers/payments.py`: `POST /payments/generate`, `GET /payments` (filterable/paginated), `GET /payments/{id}`.
- Frontend `FailedPaymentsFeed.tsx` rendering the raw feed, with a "Generate Batch" control and status/root-cause filters.

**What this gives you:** a real, inspectable batch of 100 simulated failed payments sitting in SQLite and visible in the dashboard — the raw material every later phase (classification, decisions, metrics) operates on. This is also the point where you can eyeball the dataset and confirm it's "not too clean."

---

## Phase 3 — Classification → decision → execution → audit (Days 5-6)

Build:
- `services/classifier.py`: deterministic `error_code` matching for 5 root causes, plus the hard rule `risk_score >= 0.85 → possible_fraud` (never LLM-decided). Unmatched codes route to the LLM fallback (wired in Phase 4).
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
- `MetricsSummary.tsx` (KPI tiles), `ActionsTakenTable.tsx` (every bounded action executed, batch-wide), `AuditTrailPanel.tsx` (side panel, not modal — chronological per-transaction timeline with `safety_override` visually distinct), `SafetyBoundsPanel.tsx` (renders `/config/rules` verbatim). `FailedPaymentsFeed.tsx` gets row-click-to-open-audit-panel.
- Self-review against the skill's `craft-floor.md` checklist (mechanical detector: zero findings) caught and fixed 3 real issues before calling it done: two WCAG contrast failures (status-recovered and status-escalated text were 3.30:1/3.19:1 on white, below the 4.5:1 AA floor — fixed with darker text-only variants, verified by computing exact contrast ratios), plain "Loading..." text upgraded to skeleton rows in two tables, and browser-default focus ring/text selection themed from the accent color.

**What this gives you:** the actual thing judges click through — a legible, non-cherry-picked, genuinely well-designed view of the whole batch's outcomes. Screenshot-verified: the flagship card-testing cluster shows the full sequence (confident `gateway_timeout` classification → bounded retry → success → red `SAFETY OVERRIDE` card with the exact velocity-detection reasoning) live in the audit panel, ready to screen-record for the pitch video.

---

## Phase 7 — Hardening & submission prep (Days 13-15)

Build:
- Day 13: finalize `docker-compose.yml`, run a clean-clone smoke test, add a one-click "Run Pipeline" control in the UI.
- Day 14: `README.md` (problem statement, architecture diagram from `docs/architecture.md`, metrics from a fixed-seed run, setup/run instructions, explicit safety-bounds/stopping-rules section) — freeze demo numbers so the video and README match exactly.
- Day 15: record the 5-minute pitch video (30s problem, 30s approach, 2min live demo including the deliberate failure case, 1min architecture/safety, 1min future work); buffer for last fixes; submit.

**What this gives you:** a submission-ready public repo — clean clone runs with one command, README and video tell a consistent story backed by the same frozen numbers, and the judged criteria (audit trail, bounded actions, batch metrics, deliberate failure case) are each independently pointable-to in the running app.

---

## Verification

- Unit tests (`backend/tests/`, 20 passing) assert: fraud-flagged transactions are never retried; retry caps are never exceeded; low-confidence classifications always escalate rather than act; the safety monitor triggers only at threshold, respects the time window, ignores unrelated instruments, and doesn't reprocess already-blocked transactions.
- `docker compose up --build` from a clean clone should bring up both services and let the dashboard load real data end-to-end — re-run before every phase boundary, not just at the end.
- **Manually confirmed** (not just assumed from the code) that the constructed card-testing transaction cluster, viewed via `GET /audit/{transaction_id}` and the dashboard's `blocked` status filter, shows: initial confident classification → bounded retry action → success → `safety_override` audit event → `blocked` status. This is the flagship "agent was wrong, caught itself" demo moment.

## Critical files

- `backend/app/services/decision_engine.py`
- `backend/app/services/classifier.py`
- `backend/app/services/llm/` (`base.py`, `anthropic_provider.py`, `openai_provider.py`, `gemini_provider.py`, `sarvam_provider.py`, `__init__.py`)
- `backend/app/services/safety_monitor.py`
- `backend/scripts/generate_dataset.py`
- `backend/app/models.py`
- `docker-compose.yml`
