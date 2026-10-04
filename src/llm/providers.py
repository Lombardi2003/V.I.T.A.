"""Providers and models: everything needed to reach a model, in one place. The active ones are chosen in factory.py."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Provider:
    """A service that hosts models, reached through an OpenAI-compatible endpoint."""
    name: str
    base_url: str
    key_field: Optional[str] = None  # Settings field holding its API key; None = no key needed.
    tokens_per_minute: Optional[int] = None  # Per-minute token limit of the account; None = no limit.
    request_timeout: Optional[int] = None  # Longest duration of one request, in seconds; None = no limit.


@dataclass(frozen=True)
class Model:
    """A model and what is particular about it."""
    name: str
    provider: Provider
    reasoning_effort: Optional[str] = None  # Hidden reasoning effort ("low", "medium", "high"); None = not sent.
    vision: bool = False  # True if it can read images.


# Free tier: 8,000 tokens per minute and 200,000 per day, per model and per account.
GROQ = Provider(
    name="groq",
    base_url="https://api.groq.com/openai/v1",
    key_field="groq_api_key_2",  # "groq_api_key" is the first account, with its own daily limits.
    tokens_per_minute=8000,
    request_timeout=120,
)

# Local: no key and no limit (a long answer may take minutes). Start it with a context of at least 8,192 tokens.
OLLAMA = Provider(name="ollama", base_url="http://127.0.0.1:11434/v1")

# Google AI Studio. Free tier: about 20 requests per day, per key.
GEMINI = Provider(
    name="gemini",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    key_field="gemini_fra_key",  # "gemini_api_key" is the first account, with its own daily quota.
    request_timeout=120,
)

PROVIDERS = (GROQ, OLLAMA, GEMINI)  # Every provider the project can use.


class Models:
    """The models the project can use. To add one, write it here under its provider."""
    # "low" keeps the hidden reasoning from eating the answer: with the default, answers were cut mid-JSON.
    GPT_OSS_120B = Model("openai/gpt-oss-120b", GROQ, reasoning_effort="low")
    GPT_OSS_20B = Model("openai/gpt-oss-20b", GROQ, reasoning_effort="low")
    QWEN_27B = Model("qwen/qwen3.8-27b", GROQ, vision=True)  # Writes a <think> block before the JSON.

    LLAMA3 = Model("llama3:latest", OLLAMA)
    MOONDREAM = Model("moondream", OLLAMA, vision=True)

    GEMINI_FLASH = Model("gemini-3.8-flash", GEMINI, vision=True)  # Reasoning model.
