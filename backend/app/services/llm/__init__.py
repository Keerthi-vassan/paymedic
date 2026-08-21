from app.config import settings
from app.services.llm.base import LLMClassification, LLMProvider

_provider_instance: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    provider_name = settings.llm_provider

    if provider_name == "anthropic":
        from app.services.llm.anthropic_provider import AnthropicProvider

        _provider_instance = AnthropicProvider()
    elif provider_name == "openai":
        from app.services.llm.openai_provider import OpenAIProvider

        _provider_instance = OpenAIProvider()
    elif provider_name == "gemini":
        from app.services.llm.gemini_provider import GeminiProvider

        _provider_instance = GeminiProvider()
    elif provider_name == "sarvam":
        from app.services.llm.sarvam_provider import SarvamProvider

        _provider_instance = SarvamProvider()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider_name!r}")

    return _provider_instance


__all__ = ["get_provider", "LLMClassification", "LLMProvider"]
