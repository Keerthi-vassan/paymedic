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

    # Which LLM backs ambiguous-case classification. Swapping providers is a
    # one-line env var change -- each provider is a drop-in adapter behind the
    # same interface, see app/services/llm/.
    llm_provider: str = "anthropic"  # anthropic | openai | gemini | sarvam

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    sarvam_api_key: str = ""
    sarvam_model: str = "sarvam-105b"


settings = Settings()
