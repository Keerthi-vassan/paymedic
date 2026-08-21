from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    database_url: str = "sqlite:///./data/recovery.db"
    frontend_origin: str = "http://localhost:3000"

    confidence_threshold: float = 0.6
    fraud_risk_score_threshold: float = 0.85


settings = Settings()
