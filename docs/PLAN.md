# Build Plan

> This is the original phase-by-phase plan drafted before implementation began.
> Kept as-is for reference; two things have since diverged in practice:
> - **LLM**: rather than Claude-only, ambiguous-case classification is
>   provider-agnostic (`app/services/llm/`) — Anthropic, OpenAI, Gemini, and
>   Sarvam are all implemented, selected via the `LLM_PROVIDER` env var.
> - **Safety monitor status**: an overridden transaction is marked `blocked`
>   (not `escalated`), to distinguish a retroactive safety-monitor override
>   from an ordinary rule-based escalation (fraud/low-confidence/retry-cap).
>
> Progress so far: Phases 1-4 complete (scaffold, simulated dataset,
> classify→decide→execute→audit pipeline, multi-provider LLM classification +
> safety monitor). Phase 5 (metrics) is next.

# Razorpay AI Buildathon — Revenue Recovery Agent

## Context

The user is participating in the Razorpay AI Buildathon (student-only, "Build. Show. Get hired.", deadline 5 Sep 2026). They chose the **AI Revenue Recovery** track. The bar for this track is explicit: show *actual* money recovered on a batch (not one cherry-picked example), keep every action explainable/bounded/gated (no free-roaming agent), enforce stopping rules (retry caps, no auto-action on fraud), keep a full audit trail, and — called out specifically by Razorpay as something that stands out to judges — include at least one deliberate case where the agent is wrong and catches itself.

This is a greenfield project. Decisions locked in this session:
- **LLM**: Claude API, `claude-haiku-4-5-20251001`, used ONLY to classify *ambiguous* root causes — never to decide or execute a money-moving action. Clear cases are handled by deterministic rules first.
- **Backend**: Python + FastAPI, exposing a REST API.
- **Frontend**: Next.js + Tailwind (the user's own preferred stack, chosen over Streamlit for build velocity since it's a stack they already know).
- **Data**: Fully simulated batch (not real Razorpay test-mode API for v1) — must be realistic, not too clean, and include a constructed "wrong action, caught by a safety check" case.
- **Containerization**: Docker Compose, two services (backend, frontend), SQLite (file-based, bind-mounted volume) for persistence — no separate DB container.

The plan below is broken into phases. **Each phase ends with a "What this gives you" summary** stating concretely what is built and what it does, so progress is checkable at every step rather than only at the very end.

## End-to-end architecture (target state, built up across the phases below)

```
Failed payment event (simulated)
   → Root-cause classifier (deterministic rules first; Claude Haiku fallback for ambiguous cases only)
   → Recovery decision engine (rule-gated: cause → action, retry caps, fraud block, confidence threshold)
   → Action executor (simulated outcomes via documented per-cause probability table, seeded/reproducible)
   → Safety monitor (runs after every action; detects cross-transaction patterns like card-testing velocity;
                      can override/escalate even after a rule-gated action was taken — the "agent catches itself" mechanism)
   → Audit log (every step — classification, decision, execution, override — logged with reasoning + timestamp)
   → Metrics layer (₹ recovered, recovery rate %, false-action rate, time-to-recovery)
```

The LLM never sees or controls money movement directly — it only emits `(root_cause, confidence, reasoning)` via a strict tool-use schema, which then feeds the independent, rule-based `decision_engine.py`. Fraud detection is always rule-based (`risk_score` threshold), never delegated to the LLM, since it's the one safety-critical branch.

---

## Phase 1 — Scaffold & wiring (Days 1-2)

Build:
- Repo skeleton: `backend/` (FastAPI app, `Dockerfile`, `requirements.txt`) and `frontend/` (Next.js + Tailwind, `Dockerfile`).
- `backend/app/main.py` with a single `GET /health` route and CORS enabled for the frontend origin.
- `backend/app/config.py` (pydantic Settings: `ANTHROPIC_API_KEY`, DB path, thresholds) and `backend/app/db.py` (SQLAlchemy engine/session pointed at a SQLite file under `backend/data/`).
- Next.js placeholder `app/page.tsx` that fetches `/health` and displays connection status.
- Root `docker-compose.yml` (backend on 8000, frontend on 3000, bind-mount `./backend/data`, `depends_on`), `.env.example`, `.gitignore`.

**What this gives you:** a working two-container app — `docker compose up --build` from a clean clone brings up both services, and the browser shows the frontend successfully talking to the backend. No business logic yet; this phase exists purely so every later phase has something running to plug into, and so the "clean clone and run" judge experience is proven early rather than left to Day 13.

---

## Phase 2 — Simulated data (Days 3-4)

Build:
- `backend/app/models.py`: SQLAlchemy `FailedPayment` model — `transaction_id, customer_id, amount, currency, payment_method, payment_instrument_id, issuer_bank, error_code, error_description, failed_at, network_type, latency_ms, risk_score, true_root_cause, status, final_action, total_attempts, recovered_amount, resolved_at`.
- `backend/scripts/generate_dataset.py`: seeded (`random.seed(42)`), Faker-based generator producing 100 rows with a realistic weighted mix across all 6 root causes, ~15-20% deliberately ambiguous rows (generic error text, missing/conflicting codes — designed to defeat every deterministic rule later), and a constructed cluster: 3-4 transactions sharing one `payment_instrument_id`, small increasing amounts, minutes apart, each individually tagged with an innocuous-looking `error_code` like `GATEWAY_TIMEOUT` — this cluster is the seed of the flagship "agent was wrong" case built in Phase 4.
- `routers/payments.py`: `POST /payments/generate`, `GET /payments` (filterable/paginated), `GET /payments/{id}`.
- Frontend `FailedPaymentsFeed.tsx` rendering the raw feed.

**What this gives you:** a real, inspectable batch of 100 simulated failed payments sitting in SQLite and visible in the dashboard — the raw material every later phase (classification, decisions, metrics) operates on. This is also the point where you can eyeball the dataset and confirm it's "not too clean."

---

## Phase 3 — Classification → decision → execution → audit (Days 5-6)

Build:
- `services/classifier.py`: deterministic `error_code` matching for 5 root causes, plus the hard rule `risk_score >= 0.85 → possible_fraud` (never LLM-decided). Ambiguous rows are stubbed to auto-escalate for now (LLM wired in Phase 4).
- `services/decision_engine.py`: pure, unit-testable function — cause→action table with per-cause max-retry caps (e.g. `gateway_timeout` retry up to 3, `possible_fraud` 0 attempts allowed), check order: fraud flag → escalate; confidence below threshold (0.6) → escalate; retry cap reached → escalate; else map to action.
- `services/executor.py`: seeded, documented probability table per (root_cause, action, attempt_number) simulating retry/action outcomes (e.g. gateway_timeout retry succeeds 65%/40%/20% across attempts — diminishing because genuine outages don't fix on blind retry).
- `services/audit.py` + `audit_log` SQLite table (`transaction_id, source, root_cause, confidence, action_taken, reasoning, outcome, attempt_number, created_at`) — one row per pipeline step.
- `app/pipeline.py` orchestrating classify→decide→execute→log; `routers/pipeline.py`: `POST /pipeline/run` (batch/subset), `POST /pipeline/run/{id}` (single transaction).
- `backend/tests/test_decision_engine.py`, `test_executor.py`: prove fraud is never retried and caps are never exceeded.

**What this gives you:** the full bounded-recovery loop working end-to-end for every clear-cut case in the batch — you can `POST /pipeline/run` over the 100 rows and get real ₹-recovered outcomes with a full audit trail per transaction, demoable via curl/Postman even before the LLM or dashboard exist. This is the core "prove it on a batch" mechanism the judges are scoring.

---

## Phase 4 — LLM classification + safety monitor (Days 7-8)

Build:
- `services/llm_client.py`: call to `claude-haiku-4-5-20251001` for ambiguous rows only, fixed system prompt stating the model classifies only and never decides/executes actions, strict tool-use schema (`emit_classification`: `root_cause` enum, `confidence` 0-1, `reasoning` ≤240 chars) so output is guaranteed parseable. Wired into `classifier.py` as the fallback path for rows the deterministic rules can't match.
- `services/safety_monitor.py`: runs after every action_execution, independently scans recent activity per `payment_instrument_id`; when it detects the constructed velocity/card-testing pattern from Phase 2, it overrides the in-flight decision — writes a `safety_override` audit row, blocks further automated actions on that instrument, flips status to `escalated`.
- `backend/tests/test_classifier.py`, `test_safety_monitor.py`.

**What this gives you:** the two hardest, most judge-visible pieces of the whole build — (1) ambiguous cases are now handled by the LLM instead of blanket-escalating, and (2) the flagship "agent was wrong, caught itself" transaction cluster now actually produces the sequence: confident classification → bounded retry action → `safety_override` audit event → escalated status, fully reconstructable from the audit log alone. This is the single most important checkpoint in the whole plan — verify it manually (see Verification section) before moving on.

---

## Phase 5 — Metrics (Days 9-10)

Build:
- `services/metrics.py`: `total_recovered`, `total_at_risk`, `recovery_rate`, `false_action_rate` (transactions with a `safety_override` / transactions with any action), mean/median `time_to_recovery`, `escalation_rate`, `fraud_block_rate`.
- `routers/metrics.py`: `GET /metrics/summary`, `GET /metrics/root-cause-breakdown`, `GET /metrics/timeline`.
- `routers/config_rules.py`: `GET /config/rules` — renders the same cause→action/caps/threshold config the decision engine actually uses, so the "here are the bounds" claim is provably real, not just asserted.

**What this gives you:** every number the pitch video and README need — ₹ recovered, recovery rate %, false-action rate, time-to-recovery — computed live from the batch via API, plus a machine-readable proof of the safety bounds for judges to inspect directly.

---

## Phase 6 — Dashboard (Days 11-12)

Build:
- `MetricsSummary.tsx` (KPI tiles), `RootCauseBreakdown.tsx` (chart — use the `dataviz` skill for color/legend consistency), `ActionsTakenTable.tsx`, `AuditTrailPanel.tsx` (chronological per-transaction timeline with the `safety_override` event visually highlighted), `SafetyBoundsPanel.tsx` (renders `/config/rules` verbatim). `FailedPaymentsFeed.tsx` from Phase 2 gets a row-click-to-open-audit-panel interaction.

**What this gives you:** the actual thing judges click through — a legible, non-cherry-picked view of the whole batch's outcomes, with the deliberate failure case reachable and visually distinct in the audit trail, ready to screen-record for the pitch video.

---

## Phase 7 — Hardening & submission prep (Days 13-15)

Build:
- Day 13: finalize `docker-compose.yml`, run a clean-clone smoke test, add a one-click "Run Pipeline" control in the UI.
- Day 14: `README.md` (problem statement, architecture diagram from `docs/architecture.md`, metrics from a fixed-seed run, setup/run instructions, explicit safety-bounds/stopping-rules section) — freeze demo numbers so the video and README match exactly.
- Day 15: record the 5-minute pitch video (30s problem, 30s approach, 2min live demo including the deliberate failure case, 1min architecture/safety, 1min future work); buffer for last fixes; submit.

**What this gives you:** a submission-ready public repo — clean clone runs with one command, README and video tell a consistent story backed by the same frozen numbers, and the judged criteria (audit trail, bounded actions, batch metrics, deliberate failure case) are each independently pointable-to in the running app.

---

## Verification

- Unit tests (`backend/tests/`) assert: fraud-flagged transactions are never retried; retry caps are never exceeded; low-confidence classifications always escalate rather than act.
- `backend/scripts/run_batch.py` runs the full pipeline over the generated batch and prints a metrics summary.
- `docker compose up --build` from a clean clone should bring up both services and let the dashboard load real data end-to-end — re-run before every phase boundary, not just at the end.
- **Manually confirm** (do not just assume from the code) that the constructed card-testing transaction cluster, viewed in `AuditTrailPanel`, shows: initial confident classification → bounded retry action → `safety_override` audit event → escalated status. This is the flagship "agent was wrong, caught itself" demo moment and is the single highest-value thing to check before Phase 5.

## Critical files to create first

- `backend/app/services/decision_engine.py`
- `backend/app/services/classifier.py`
- `backend/app/services/llm_client.py`
- `backend/app/services/safety_monitor.py`
- `backend/scripts/generate_dataset.py`
- `backend/app/models.py`
- `docker-compose.yml`
