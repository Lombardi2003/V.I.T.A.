"""Costruisce i client LLM (testo e visione) come ChatOpenAI.

Groq e Ollama espongono entrambi un endpoint compatibile con l'API REST di
OpenAI (rispettivamente /openai/v1 e /v1): usare ChatOpenAI per entrambi,
invece dei client dedicati ChatGroq/ChatOllama, permette di passare da cloud
a locale cambiando solo base_url/model/api_key, con un'unica funzione invece
di due implementazioni parallele.
"""
from typing import Optional

from langchain_openai import ChatOpenAI

from src.settings import get_settings
from .models import Models

_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://127.0.0.1:11434/v1",
}
_DEFAULT_TEXT_MODELS = {
    "groq": Models.Groq.TEXT_8B,
    "ollama": Models.Ollama.TEXT_LLAMA3,
}
_DEFAULT_VISION_MODELS = {
    "groq": Models.Groq.VISION_MAVERICK,
    "ollama": Models.Ollama.VISION_MOONDREAM,
}


def get_llm(
    *,
    vision: bool = False,
    temperature: Optional[float] = None,
    model_name: Optional[str] = None,
) -> ChatOpenAI:
    """Restituisce un client ChatOpenAI pronto per il provider attivo.

    provider e' deciso da use_cloud_acceleration (True -> Groq, False -> Ollama
    in locale); vision=True seleziona il modello di visione invece di quello
    testuale. model_name/temperature, se non passati, vengono presi da Settings
    e in ultima istanza da un default per-provider.
    """
    settings = get_settings()
    provider = "groq" if settings.use_cloud_acceleration else "ollama"

    defaults = _DEFAULT_VISION_MODELS if vision else _DEFAULT_TEXT_MODELS
    override = settings.vision_model_name if vision else settings.model_name
    resolved_model = model_name or override or defaults[provider]

    kwargs = dict(
        model=resolved_model,
        temperature=temperature if temperature is not None else settings.temperature,
        base_url=_BASE_URLS[provider],
        api_key=settings.groq_api_key if provider == "groq" else "ollama",
    )
    if vision and provider == "groq":
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

    return ChatOpenAI(**kwargs)
