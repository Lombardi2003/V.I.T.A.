from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Punto unico di lettura per chiavi/config provenienti dall'esterno (.env).

    I nomi dei campi (in minuscolo) corrispondono alle variabili nel file .env
    (in maiuscolo): aggiungere qui un campo e' sufficiente perche' venga anche
    richiesto automaticamente da scripts/setup_env.py.

    Nel .env stanno solo le chiavi (segrete, fuori da git) e la temperatura:
    QUALI modelli usa l'app si sceglie in cima a src/llm/factory.py (su git,
    cosi' ogni esperimento e' ripetibile), e i modelli davvero in uso vengono
    stampati all'avvio. Eventuali vecchie voci MODEL_NAME, VISION_MODEL_NAME,
    USE_CLOUD_ACCELERATION ancora presenti nel .env vengono ignorate.
    """
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

    # Chiavi dei provider: servono solo quelle dei provider dei modelli scelti
    # (se ne manca una necessaria, l'errore arriva alla creazione del client,
    # vedi _api_key_for in src/llm/factory.py).
    groq_api_key: Optional[str] = None
    # Chiave per l'API di Gemini (Google AI Studio, piano gratuito).
    gemini_api_key: Optional[str] = None
    # Seconda chiave Gemini, da un account/progetto Google Cloud diverso da
    # quello di gemini_api_key (la quota gratuita di 20 richieste/giorno e'
    # per-progetto). Attualmente non usata da src/llm/factory.py: basta
    # metterla al posto di GEMINI_API_KEY quando la prima si esaurisce.
    gemini_fra_key: Optional[str] = None

    temperature: float = 0.0


@lru_cache
def get_settings() -> Settings:
    """Istanzia (e valida) Settings solo alla prima richiesta effettiva."""
    return Settings()  # type: ignore[call-arg]
