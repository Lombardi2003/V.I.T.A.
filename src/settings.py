"""Values read from .env: provider keys and temperature. The models are chosen in src/llm/factory.py."""

from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # Project folder.
ENV_PATH = PROJECT_ROOT / ".env"  # The .env file.


class Settings(BaseSettings):
    """Every field is a variable of .env; adding one here makes setup_env.py ask for it."""
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

    groq_api_key: Optional[str] = None
    groq_api_key_2: Optional[str] = None  # Second account, with separate daily limits.
    gemini_api_key: Optional[str] = None
    gemini_fra_key: Optional[str] = None  # Second account, with a separate daily quota.
    huggingface_api_key: Optional[str] = None  # Access token with the permission for Inference Providers.
    cloudflare_api_key: Optional[str] = None  # Workers AI API token.
    cloudflare_account_id: Optional[str] = None  # The account the token belongs to: part of the provider's address.

    temperature: float = 0.0


@lru_cache
def get_settings() -> Settings:
    """The settings, read once."""
    return Settings()  # type: ignore[call-arg]
