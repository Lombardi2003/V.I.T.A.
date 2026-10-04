"""Which models the app uses, and the clients built for them. Every provider is reached the same way."""

from typing import Optional

from langchain_openai import ChatOpenAI

from src.settings import get_settings
from .models import Models

TEXT_MODEL = Models.Groq.TEXT_120B  # ACTIVE MODEL for every text agent: the only place where it is chosen.
TEXT_REASONING = "low"  # Hidden reasoning effort; "low" keeps answers from being cut mid-JSON. None = not sent.
VISION_MODEL = Models.Groq.VISION_QWEN  # ACTIVE MODEL for the photo.
GROQ_KEY = "groq_api_key_2"  # Settings field holding the Groq key to use.
GEMINI_KEY = "gemini_fra_key"  # Settings field holding the Gemini key to use.

# Provider -> (server address, settings field of its key; None = no key needed).
_PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", GROQ_KEY),
    "ollama": ("http://127.0.0.1:11434/v1", None),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", GEMINI_KEY),
}

# Per-minute token limit of each provider's account (absent = none).
TOKENS_PER_MINUTE = {
    "groq": 8000,
}

# Longest duration of one request (absent = none: a local model may take minutes).
REQUEST_TIMEOUT_SECONDS = {
    "groq": 120,
    "gemini": 120,
}


def provider_of_model(model_name: str) -> str:
    """The provider of a model, from the catalogue class its name belongs to."""
    for provider_name, provider_models in vars(Models).items():
        if isinstance(provider_models, type) and model_name in vars(provider_models).values():
            return provider_name.lower()
    raise ValueError(
        f"Model '{model_name}' is not in src/llm/models.py: add it under its provider."
    )


def build_llm(model_name: str, reasoning_effort: Optional[str] = None) -> ChatOpenAI:
    """The client for a model of the catalogue."""
    provider = provider_of_model(model_name)
    base_url, key_field = _PROVIDERS[provider]
    settings = get_settings()
    api_key = getattr(settings, key_field) if key_field else "ollama"
    if not api_key:
        raise RuntimeError(
            f"The chosen model uses the provider '{provider}' but {key_field.upper()} is not set "
            "in .env. Set it with 'python scripts/setup_env.py --update', or choose a model "
            "of another provider at the top of src/llm/factory.py."
        )
    extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=settings.temperature,
        **extra,
        # Explicit: the client's default is low and cut long answers. Reduced per call when needed.
        max_tokens=4096,
        # Retries are handled only by call_with_retry: two layers added up to long silent waits.
        max_retries=0,
        timeout=REQUEST_TIMEOUT_SECONDS.get(provider),
    )


def get_llm(*, vision: bool = False) -> ChatOpenAI:
    """The client of the active text model, or of the vision model."""
    if vision:
        return build_llm(VISION_MODEL)
    return build_llm(TEXT_MODEL, reasoning_effort=TEXT_REASONING)


def provider_of(llm: ChatOpenAI) -> Optional[str]:
    """The provider of a client, from its server address."""
    base_url = str(getattr(llm, "openai_api_base", "") or "")
    return next((name for name, (url, _) in _PROVIDERS.items() if url == base_url), None)


def tokens_per_minute_limit(llm: ChatOpenAI) -> Optional[int]:
    """The per-minute token limit that applies to this client, or None."""
    return TOKENS_PER_MINUTE.get(provider_of(llm))


def describe_llm(llm: ChatOpenAI) -> str:
    """The model a client actually uses, as text for the terminal and the settings panel."""
    effort = getattr(llm, "reasoning_effort", None)
    return f"{provider_of(llm) or '?'}/{llm.model_name}" + (f" (ragionamento {effort})" if effort else "")
