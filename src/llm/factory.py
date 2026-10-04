"""Which models the app uses, and the clients built for them. Every provider is reached the same way."""

from typing import Optional

from langchain_openai import ChatOpenAI

from src.settings import get_settings
from .providers import Model, Models, PROVIDERS

TEXT_MODEL = Models.GPT_OSS_120B  # ACTIVE MODEL for every text agent: the only place where it is chosen.
VISION_MODEL = Models.QWEN_27B  # ACTIVE MODEL for the photo.


def build_llm(model: Model) -> ChatOpenAI:
    """The client for a model of the catalogue."""
    if not isinstance(model, Model):
        raise ValueError(f"'{model}' is not a model of src/llm/providers.py: add it there under its provider.")
    provider = model.provider
    settings = get_settings()
    api_key = getattr(settings, provider.key_field) if provider.key_field else "ollama"
    if not api_key:
        raise RuntimeError(
            f"The chosen model uses the provider '{provider.name}' but {provider.key_field.upper()} is not set "
            "in .env. Set it with 'python scripts/setup_env.py --update', or choose a model "
            "of another provider at the top of src/llm/factory.py."
        )
    extra = {"reasoning_effort": model.reasoning_effort} if model.reasoning_effort else {}
    return ChatOpenAI(
        api_key=api_key,
        base_url=provider.base_url,
        model=model.name,
        temperature=settings.temperature,
        **extra,
        # Explicit: the client's default is low and cut long answers. Reduced per call when needed.
        max_tokens=4096,
        # Retries are handled only by call_with_retry: two layers added up to long silent waits.
        max_retries=0,
        timeout=provider.request_timeout,
    )


def get_llm(*, vision: bool = False) -> ChatOpenAI:
    """The client of the active text model, or of the vision model."""
    return build_llm(VISION_MODEL if vision else TEXT_MODEL)


def needed_key_fields() -> set[str]:
    """The settings fields holding the keys the active models need (none for a local-only setup)."""
    return {m.provider.key_field for m in (TEXT_MODEL, VISION_MODEL) if m.provider.key_field}


def provider_of(llm: ChatOpenAI) -> Optional[str]:
    """The name of the provider of a client, from its server address."""
    base_url = str(getattr(llm, "openai_api_base", "") or "")
    return next((p.name for p in PROVIDERS if p.base_url == base_url), None)


def tokens_per_minute_limit(llm: ChatOpenAI) -> Optional[int]:
    """The per-minute token limit that applies to this client, or None."""
    base_url = str(getattr(llm, "openai_api_base", "") or "")
    return next((p.tokens_per_minute for p in PROVIDERS if p.base_url == base_url), None)


def describe_llm(llm: ChatOpenAI) -> str:
    """The model a client actually uses, as text for the terminal and the settings panel."""
    effort = getattr(llm, "reasoning_effort", None)
    return f"{provider_of(llm) or '?'}/{llm.model_name}" + (f" (ragionamento {effort})" if effort else "")
