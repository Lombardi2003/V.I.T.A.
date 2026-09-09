"""Costruisce i client LLM (testo e visione) come ChatOpenAI.

Groq, Ollama e Gemini espongono tutti un endpoint compatibile con l'API REST
di OpenAI (rispettivamente /openai/v1, /v1 e /v1beta/openai/, quest'ultimo
verificato con una chiamata reale a GET .../models): usare ChatOpenAI per
tutti e tre, invece dei client dedicati, permette di passare da un provider
all'altro cambiando solo base_url/model/api_key, con un'unica funzione invece
di piu' implementazioni parallele.
"""
from typing import Optional

from langchain_openai import ChatOpenAI

from src.settings import get_settings
from .models import Models

_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    # Stesso endpoint di "gemini" - solo un progetto/account Google diverso
    # (vedi gemini_fra_api_key in settings.py), quindi con la sua quota
    # gratuita giornaliera separata (20 richieste/giorno "per progetto").
    "gemini_fra": "https://generativelanguage.googleapis.com/v1beta/openai/",
}
_DEFAULT_TEXT_MODELS = {
    # TEXT_8B non e' piu' nel catalogo modelli dell'account (verificato dalla
    # pagina dei rate limit Groq) - TEXT_20B come default di fallback.
    "groq": Models.Groq.TEXT_20B,
    "ollama": Models.Ollama.TEXT_LLAMA3,
    "gemini": Models.Gemini.TEXT_FLASH,
    "gemini_fra": Models.Gemini.TEXT_FLASH,
}
_DEFAULT_VISION_MODELS = {
    "groq": Models.Groq.VISION_QWEN,
    "ollama": Models.Ollama.VISION_MOONDREAM,
    # gemini-2.5-flash e' nativamente multimodale (nessun modello di visione
    # separato come per Groq), quindi riusiamo lo stesso TEXT_FLASH qui.
    "gemini": Models.Gemini.TEXT_FLASH,
    "gemini_fra": Models.Gemini.TEXT_FLASH,
}


def get_llm(
    *,
    vision: bool = False,
    temperature: Optional[float] = None,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
) -> ChatOpenAI:
    """Restituisce un client ChatOpenAI pronto per il provider attivo.

    provider e' normalmente deciso da use_cloud_acceleration (True -> Groq,
    False -> Ollama in locale); vision=True seleziona il modello di visione
    invece di quello testuale. model_name/temperature, se non passati, vengono
    presi da Settings e in ultima istanza da un default per-provider.

    Il parametro "provider" qui sopra e' una via di fuga esplicita: forza
    "groq"/"ollama"/"gemini" per QUESTA chiamata, ignorando
    use_cloud_acceleration - serve per i casi in cui un singolo client (es.
    llm_specialist in common.py) deve restare su un provider specifico
    indipendentemente dal resto dell'app (es. Ollama in locale o Gemini per
    non consumare la quota Groq durante i test del tavolo rotondo, mentre gli
    altri nodi restano su Groq).
    """
    settings = get_settings()
    resolved_provider = provider or ("groq" if settings.use_cloud_acceleration else "ollama")

    defaults = _DEFAULT_VISION_MODELS if vision else _DEFAULT_TEXT_MODELS
    override = settings.vision_model_name if vision else settings.model_name
    resolved_model = model_name or (override if not provider else None) or defaults[resolved_provider]

    # Ollama in locale non richiede una vera autenticazione (il valore non
    # viene verificato), quindi usiamo una stringa segnaposto.
    api_keys = {
        "groq": settings.groq_api_key,
        "gemini": settings.gemini_api_key,
        "gemini_fra": settings.gemini_fra_key,
        "ollama": "ollama",
    }
    kwargs = dict(
        model=resolved_model,
        temperature=temperature if temperature is not None else settings.temperature,
        base_url=_BASE_URLS[resolved_provider],
        api_key=api_keys[resolved_provider],
        # Senza un max_tokens esplicito, il default (basso) del client tronca
        # risposte lunghe a meta' - osservato in test reale con Gemini
        # (modello "thinking": il ragionamento interno consuma token dallo
        # stesso budget di quello visibile, quindi si esaurisce ancora piu'
        # in fretta). 4096 e' abbondante per un turno del tavolo rotondo
        # (JSON con piu' campi di testo) senza essere eccessivo.
        max_tokens=4096,
    )
    # NB: niente response_format={"type": "json_object"} forzato per la visione -
    # qwen/qwen3.6-27b (il modello vision Groq attuale) e' un modello "thinking":
    # antepone un blocco <think>...</think> di ragionamento prima del JSON, e il
    # validatore server-side di response_format=json_object si aspetta l'INTERA
    # risposta come JSON puro, quindi fallisce con 400 json_validate_failed
    # (verificato con chiamata reale). Il parsing lato Python (photography_node)
    # gestisce gia' testo extra prima/dopo il JSON.

    return ChatOpenAI(**kwargs)
