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

    # Which LLM backs ambiguous-case classification. Swapping providers is a
    # one-line env var change -- each provider is a drop-in adapter behind the
    # same interface, see app/services/llm/.
    llm_provider: str = "anthropic"  # anthropic | openai | gemini | sarvam

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"

    sarvam_api_key: str = ""
    sarvam_model: str = "sarvam-105b"


settings = Settings()
