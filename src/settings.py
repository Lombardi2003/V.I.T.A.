from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic import model_validator
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

    groq_api_key: Optional[str] = None
    # Chiave per l'API di Gemini (Google AI Studio, piano gratuito) - usata
    # solo quando get_llm() viene chiamato con provider="gemini" esplicito
    # (vedi factory.py), non fa parte della scelta groq/ollama principale
    # decisa da use_cloud_acceleration.
    gemini_api_key: Optional[str] = None
    use_cloud_acceleration: bool = True

    # Override opzionali: se assenti, src/llm/factory.py usa un default sensato
    # per il provider attivo (Groq se use_cloud_acceleration=True, altrimenti Ollama).
    model_name: Optional[str] = None
    vision_model_name: Optional[str] = None
    temperature: float = 0.0

    @model_validator(mode="after")
    def _check_groq_key_when_needed(self) -> "Settings":
        if self.use_cloud_acceleration and not self.groq_api_key:
            raise ValueError(
                "USE_CLOUD_ACCELERATION e' true ma GROQ_API_KEY non e' impostata. "
                "Imposta una chiave valida con 'python scripts/setup_env.py --update', "
                "oppure metti USE_CLOUD_ACCELERATION=False per usare Ollama in locale."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Istanzia (e valida) Settings solo alla prima richiesta effettiva."""
    return Settings()  # type: ignore[call-arg]
