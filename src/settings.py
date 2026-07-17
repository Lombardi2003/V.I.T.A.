from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Punto unico di lettura per chiavi/config provenienti dall'esterno (.env).

    I nomi dei campi (in minuscolo) corrispondono alle variabili nel file .env
    (in maiuscolo): aggiungere qui un campo e' sufficiente perche' venga anche
    richiesto automaticamente da scripts/setup_env.py.
    """
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

    groq_api_key: str


@lru_cache
def get_settings() -> Settings:
    """Istanzia (e valida) Settings solo alla prima richiesta effettiva."""
    return Settings()  # type: ignore[call-arg]
