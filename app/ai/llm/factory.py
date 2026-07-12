"""Select an LLM provider from application settings."""

from app.ai.llm.base import LLMProvider
from app.ai.llm.mock import MockLLMProvider
from app.core.config import Settings, get_settings


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Return the configured LLM provider.

    ``mock`` is the offline default used by tests and local runs. Set
    ``LLM_PROVIDER=openai`` (with ``LLM_API_KEY``) to use OpenAI or any
    OpenAI-compatible endpoint behind the same protocol, without touching call
    sites.
    """
    settings = settings or get_settings()
    provider = settings.llm_provider.lower()

    if provider == "mock":
        return MockLLMProvider(model=settings.llm_model)

    if provider in ("openai", "openai-compatible"):
        # Imported lazily so the offline/mock path never requires httpx.
        from app.ai.llm.openai import OpenAILLMProvider

        return OpenAILLMProvider(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens or None,
        )

    raise ValueError(f"Unsupported LLM provider: {provider!r}")
