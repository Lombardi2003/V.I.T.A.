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
    account_field: Optional[str] = None  # Settings field holding the account id that fills "{account}" in base_url.


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

# Local: no key and no limit (a long answer may take minutes). Start it with a context of at least 16,384 tokens:
# a turn of the round table is about 10,000, and Ollama cuts a longer prompt without saying so.
OLLAMA = Provider(name="ollama", base_url="http://127.0.0.1:11434/v1")

# Google AI Studio. Free tier: about 20 requests per day, per key.
GEMINI = Provider(
    name="gemini",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    key_field="gemini_fra_key",  # "gemini_api_key" is the first account, with its own daily quota.
    request_timeout=120,
)

# Hugging Face Inference Providers: one token, requests routed to the service that hosts the model.
# Free accounts get a small monthly credit; the model's licence must be accepted on its page first.
HUGGINGFACE = Provider(
    name="huggingface",
    base_url="https://router.huggingface.co/v1",
    key_field="huggingface_api_key",
    request_timeout=120,
)

# Cloudflare Workers AI. Free tier: 10,000 "neurons" per day, shared by every model of the account.
# The address holds the account id, so it needs two settings: the id and the API token.
CLOUDFLARE = Provider(
    name="cloudflare",
    base_url="https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1",
    key_field="cloudflare_api_key",
    account_field="cloudflare_account_id",
    request_timeout=120,
)

PROVIDERS = (GROQ, OLLAMA, GEMINI, HUGGINGFACE, CLOUDFLARE)  # Every provider the project can use.


class Models:
    """The models the project can use. To add one, write it here under its provider."""
    # GROQ models
    GPT_OSS_120B = Model("openai/gpt-oss-120b", GROQ, reasoning_effort="low")
    GPT_OSS_20B = Model("openai/gpt-oss-20b", GROQ, reasoning_effort="low")
    QWEN_27B = Model("qwen/qwen3.8-27b", GROQ, vision=True)  # Writes a <think> block before the JSON.

    # OLLAMA models
    LLAMA3_2 = Model("llama3.2:latest", OLLAMA)
    LLAMA3_1_8B = Model("llama3.1:8b", OLLAMA)
    MOONDREAM = Model("moondream", OLLAMA, vision=True)

    # GEMINI models
    GEMINI_FLASH = Model("gemini-3.8-flash", GEMINI, vision=True)  # Reasoning model.

    # HUGGING FACE models (the part after ":" names the service that hosts the model)
    LLAMA3_2_HF = Model("meta-llama/Llama-3.2-3B-Instruct:featherless-ai", HUGGINGFACE)

    # CLOUDFLARE models
    LLAMA3_2_CF = Model("@cf/meta/llama-3.2-3b-instruct", CLOUDFLARE)
    LLAMA3_2_1B = Model("@cf/meta/llama-3.2-1b-instruct", CLOUDFLARE)
    GRANITE_MICRO = Model("@cf/ibm-granite/granite-4.0-h-micro", CLOUDFLARE)
