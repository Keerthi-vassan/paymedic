from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/recovery.db"
    frontend_origin: str = "http://localhost:3000"

    confidence_threshold: float = 0.6
    fraud_risk_score_threshold: float = 0.85

    # Cross-transaction velocity check (safety_monitor): N+ actioned
    # transactions on the same payment instrument within the window is
    # treated as a card-testing pattern, regardless of what the per-
    # transaction classifier concluded.
    velocity_window_minutes: int = 60
    velocity_threshold_count: int = 3

    # Second cross-transaction signal: N+ actioned transactions on DISTINCT
    # payment instruments sharing one IP address within the same window
    # (velocity_window_minutes) catches distributed card-testing that the
    # instrument-based check above can't see. Distinct-instrument count, not
    # raw row count, so one customer retrying their own card doesn't trip it.
    ip_velocity_threshold_count: int = 3

    # Visa/Mastercard cap non-fraud card reattempts at ~15 per card per
    # merchant per rolling 30 days and fine merchants who exceed it. Per-cause
    # caps in decision_engine.ROOT_CAUSE_ACTIONS already stay well under this,
    # but this is the actual compliance backstop they're implicitly obeying --
    # made explicit and enforced independently of any per-cause policy.
    network_retry_ceiling: int = 15

    # Retry *timing*, not retry count (see app/services/retry_scheduler.py).
    # Authorization success rates swing ~15% with time of day, so a scheduled
    # attempt landing in the small hours is moved to the next morning, and an
    # insufficient_funds retry landing just before a salary-credit date is
    # nudged onto it rather than firing into a trough. Bounded by
    # payday_lookahead_days so this can never push an attempt past the
    # industry 10-14 day retry envelope.
    quiet_hours_start: int = 1
    quiet_hours_end: int = 6
    quiet_hours_resume_hour: int = 9
    payday_lookahead_days: int = 3
    payday_retry_hour: int = 10

    # Customer-facing nudge drafting (see app/services/notifier.py). The LLM
    # may personalize within a fixed template's bounds; anything longer than
    # this, or containing content the guard rejects, falls back to the
    # template verbatim.
    notification_max_chars: int = 240
    notification_llm_enabled: bool = True

    # Shared secret for verifying real Razorpay webhook deliveries
    # (app/routers/webhooks.py). Empty means the endpoint refuses every
    # request rather than accepting unverified ones.
    razorpay_webhook_secret: str = ""

    # Which LLM backs ambiguous-case classification. Swapping providers is a
    # one-line env var change -- each provider is a drop-in adapter behind the
    # same interface, see app/services/llm/.
    llm_provider: str = "anthropic"  # anthropic | openai | gemini | sarvam

    # Hard bound on how long a single classification may take, and how many
    # times its SDK may retry internally. Without these, a rate-limited or
    # degraded provider turns a ~10s batch into minutes of invisible backoff:
    # the SDKs honour a 429's "retry after" and keep going, so the pipeline
    # appears to hang rather than fail. One retry, then fail fast -- the
    # classifier's fail-closed path already turns an error into a safe
    # escalation, and an escalation now beats a correct answer in four
    # minutes. The llm_error count in /metrics/classifier is what makes the
    # degradation visible instead of silent.
    llm_timeout_seconds: float = 20.0
    llm_max_retries: int = 1

    # How many times each ambiguous transaction is classified. The LLM's own
    # stated confidence is a poor predictor of whether it is right (~0.627
    # AUROC, barely above chance); how often independent samples agree with
    # each other is substantially better (0.65-0.74) and costs nothing but
    # repeated calls. See classifier._classify_by_consensus.
    #
    # Set to 1 to reproduce the previous single-sample behaviour exactly --
    # useful for an honest before/after comparison via /metrics/classifier.
    # Note the cost is linear: 3 samples means 3x the requests on the ~17% of
    # rows that reach the LLM at all, which matters on a free-tier key.
    classification_samples: int = 3

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    sarvam_api_key: str = ""
    sarvam_model: str = "sarvam-105b"

    # Optional real Razorpay test-mode integration: blends a small, fixed
    # number of real API-driven transactions into each generated batch
    # instead of every outcome being a simulated hash-roll. Off by default --
    # dataset generation, batch composition, and seed=42 reproducibility are
    # byte-identical to the fully-simulated system when disabled, so a clean
    # clone with no Razorpay keys behaves exactly as it always has.
    razorpay_execution_enabled: bool = False
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_real_txn_count: int = 4
    razorpay_real_execution_timeout_seconds: int = 45
    razorpay_base_url: str = "https://api.razorpay.com/v1"


settings = Settings()
