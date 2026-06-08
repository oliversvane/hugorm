from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ..config import Settings


def make_llm_model(settings: Settings) -> OpenAIChatModel:
    """
    Builds a pydantic-ai OpenAI-compatible model. Works for both the real OpenAI
    API and self-hosted OpenAI-compatible endpoints like vLLM — vLLM is selected
    by setting `HUGORM_LLM_BASE_URL=http://<vllm-host>/v1`.
    """
    provider_kwargs: dict = {}
    if settings.openai_api_key:
        provider_kwargs["api_key"] = settings.openai_api_key
    if settings.llm_base_url:
        provider_kwargs["base_url"] = settings.llm_base_url
        provider_kwargs.setdefault("api_key", "not-needed")
    return OpenAIChatModel(settings.llm_model, provider=OpenAIProvider(**provider_kwargs))
