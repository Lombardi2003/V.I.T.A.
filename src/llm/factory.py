"""Costruisce i client LLM che gli agenti usano ("ecco il tuo LLM").

Groq, Ollama e Gemini espongono tutti un endpoint compatibile con l'API REST
di OpenAI: per tutti il client si costruisce nello stesso identico modo,
ChatOpenAI(api_key, base_url, model, temperature) - cambiano solo i valori.
Un provider nuovo con API compatibile si aggiunge in _PROVIDERS (e il suo
elenco di modelli in models.py), senza toccare gli agenti.
"""
from typing import Optional

from langchain_openai import ChatOpenAI

from src.settings import get_settings
from .models import Models

# ============================================================================
# MODELLI ATTIVI - l'UNICO punto del progetto in cui si sceglie quale modello
# usa l'app. Per cambiarlo, sostituire il nome con un altro del catalogo
# (models.py), es. Models.Ollama.TEXT_LLAMA3 per lavorare in locale. I modelli
# davvero in uso vengono stampati all'avvio e mostrati nel pannello dell'app.
# ============================================================================
TEXT_MODEL = Models.Groq.TEXT_120B     # tutti i nodi di testo (anagrafica, sintomi, supervisore, specialisti, primario)
# Quanto "ragiona" in silenzio il modello del testo prima di rispondere
# ("low"/"medium"/"high"), solo per i modelli di ragionamento che lo
# supportano (es. openai/gpt-oss-*); None = parametro non inviato (da usare con
# modelli che non lo supportano, altrimenti la richiesta viene rifiutata).
# "low": con il default, un turno di specialista ha usato fino a ~4000 token di
# solo ragionamento interno (misurato con chiamate reali) - con il limite di
# Groq le risposte venivano troncate a meta' del JSON e il turno saltava (in
# una prova, 9 volte di fila). Con "low" lo stesso turno ne usa ~600.
TEXT_REASONING = "low"
VISION_MODEL = Models.Groq.VISION_QWEN  # analisi della foto
# Quale chiave Groq usare (nome del campo in settings.py): "groq_api_key" o
# "groq_api_key_2" (secondo account, con limiti giornalieri separati - utile
# quando il primo ha esaurito i 200K token al giorno di un modello).
GROQ_KEY = "groq_api_key_2"

# Provider: indirizzo del server e nome della chiave in settings.py (None =
# nessuna chiave: Ollama in locale non la verifica, basta un valore qualsiasi).
_PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", GROQ_KEY),
    "ollama": ("http://127.0.0.1:11434/v1", None),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini_api_key"),
}

# Limite di token al MINUTO dell'account, per provider (assente = nessun
# limite, es. Ollama in locale). Groq (piano gratuito) rifiuta con errore 413
# "Request too large" ogni richiesta in cui token del prompt + max_tokens
# riservati alla risposta superano questo limite - a prescindere da quanti
# token la risposta userebbe davvero (verificato con chiamate reali:
# "Requested 8032" = 5032 di prompt + 3000 di max_tokens, rifiutata). Vedi
# calls.py per come viene rispettato.
TOKENS_PER_MINUTE = {
    "groq": 8000,
}

# Durata massima di UNA richiesta, in secondi, per provider (assente = nessun
# limite: Ollama gira in locale e una risposta lunga puo' durare anche piu'
# di qualche minuto). Senza, valeva il default del client: 10 minuti di chat
# ferma per una richiesta bloccata verso un servizio in cloud.
REQUEST_TIMEOUT_SECONDS = {
    "groq": 120,
    "gemini": 120,
}


def provider_of_model(model_name: str) -> str:
    """Provider di un modello, dalla classe di models.py in cui sta il suo nome
    (Models.Groq.* -> "groq")."""
    for provider_name, provider_models in vars(Models).items():
        if isinstance(provider_models, type) and model_name in vars(provider_models).values():
            return provider_name.lower()
    raise ValueError(
        f"Modello '{model_name}' non presente in src/llm/models.py: aggiungilo sotto il suo provider."
    )


def build_llm(model_name: str, reasoning_effort: Optional[str] = None) -> ChatOpenAI:
    """Client per un modello del catalogo - stessa costruzione per ogni provider."""
    provider = provider_of_model(model_name)
    base_url, key_field = _PROVIDERS[provider]
    settings = get_settings()
    api_key = getattr(settings, key_field) if key_field else "ollama"
    if not api_key:
        raise RuntimeError(
            f"Il modello scelto usa il provider '{provider}' ma {key_field.upper()} non e' impostata "
            "nel .env. Impostala con 'python scripts/setup_env.py --update', oppure scegli un modello "
            "di un altro provider in cima a src/llm/factory.py."
        )
    extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=settings.temperature,
        **extra,
        # Senza un max_tokens esplicito, il default (basso) del client tronca
        # risposte lunghe a meta' - osservato in test reale. 4096 e' il
        # massimo; calls.py lo riduce a ogni chiamata se serve per stare nel
        # limite di token al minuto del provider.
        max_tokens=4096,
        # Nessun nuovo tentativo dentro il client: li gestisce SOLO
        # call_with_retry (calls.py), che legge l'attesa suggerita dal
        # provider. Prima i due meccanismi si sommavano (fino a 9 tentativi,
        # attese in silenzio di 40+ secondi non controllate dal nostro tetto -
        # osservato in prova reale: "Retrying request ... in 44 seconds").
        max_retries=0,
        timeout=REQUEST_TIMEOUT_SECONDS.get(provider),
    )


def get_llm(*, vision: bool = False) -> ChatOpenAI:
    """"Ecco il tuo LLM": il client del modello attivo (testo, o foto con
    vision=True). Da chiamare una volta, all'avvio."""
    if vision:
        return build_llm(VISION_MODEL)
    return build_llm(TEXT_MODEL, reasoning_effort=TEXT_REASONING)


def provider_of(llm: ChatOpenAI) -> Optional[str]:
    """Provider di un client costruito qui, dal suo indirizzo."""
    base_url = str(getattr(llm, "openai_api_base", "") or "")
    return next((name for name, (url, _) in _PROVIDERS.items() if url == base_url), None)


def tokens_per_minute_limit(llm: ChatOpenAI) -> Optional[int]:
    """Limite di token al minuto del provider di questo client, o None se non c'e'."""
    return TOKENS_PER_MINUTE.get(provider_of(llm))


def describe_llm(llm: ChatOpenAI) -> str:
    """Modello EFFETTIVAMENTE usato da un client (letto dal client stesso, non
    dalla configurazione), es. "groq/openai/gpt-oss-120b" - per il terminale
    all'avvio, il pannello dell'app e i risultati dei benchmark."""
    effort = getattr(llm, "reasoning_effort", None)
    return f"{provider_of(llm) or '?'}/{llm.model_name}" + (f" (ragionamento {effort})" if effort else "")
