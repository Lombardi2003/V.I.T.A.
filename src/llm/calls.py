"""Chiamate ai modelli e lettura delle risposte, indipendenti dal modello.

Tutto cio' che dipende da come si comporta un provider/modello (errori
temporanei, limiti di token, formato della risposta) e' gestito qui, cosi' gli
agenti (src/agents/) chiamano solo stream_text/extract_json senza sapere quale
modello c'e' sotto.
"""
import json
import re
import time

import openai
from langchain_openai import ChatOpenAI

from .factory import tokens_per_minute_limit

# --- Nuovi tentativi dopo un errore temporaneo ---
# Solo errori TEMPORANEI dell'API (non quelli definitivi come chiave non valida
# o richiesta malformata, che fallirebbero identici). Il caso tipico e' il 429 di
# Groq (limite di token al minuto, osservato in test reale durante il tavolo
# rotondo): prima non veniva gestito in nessun nodo tranne gli specialisti - un
# 429 nel supervisore, nell'intake o nel primario mandava in errore l'intera
# conversazione - e negli specialisti il turno veniva solo saltato e ritentato
# subito dal router, senza pause, cioe' quasi sempre di nuovo oltre il limite.
MAX_LLM_RETRIES = 2
MAX_RETRY_WAIT_SECONDS = 30  # oltre, meglio arrendersi che bloccare la chat
DEFAULT_RETRY_WAIT_SECONDS = 5
_TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,   # include APITimeoutError
    openai.InternalServerError,
)
# Alcuni provider indicano quanto aspettare nel messaggio d'errore, es. Groq:
# "Please try again in 6.8325s" (oppure "in 1m2.5s" oltre il minuto).
_RETRY_AFTER = re.compile(r"try again in (?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def _retry_wait_seconds(error: Exception) -> float:
    match = _RETRY_AFTER.search(str(error))
    if not match:
        return DEFAULT_RETRY_WAIT_SECONDS
    minutes, seconds = match.groups()
    return int(minutes or 0) * 60 + float(seconds) + 1  # +1 s di margine


def call_with_retry(fn, *args, **kwargs):
    """Esegue una chiamata all'LLM ritentandola dopo un errore temporaneo,
    aspettando il tempo suggerito dall'API (con un tetto). Sincrona: va sempre
    chiamata dentro asyncio.to_thread, come gia' fanno tutti i nodi, cosi'
    l'attesa non blocca il ciclo di eventi di Chainlit."""
    for attempt in range(MAX_LLM_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except _TRANSIENT_ERRORS as e:
            wait = _retry_wait_seconds(e)
            if attempt == MAX_LLM_RETRIES or wait > MAX_RETRY_WAIT_SECONDS:
                raise
            print(f"\n⏳ LLM: errore temporaneo ({type(e).__name__}), nuovo tentativo "
                  f"{attempt + 1}/{MAX_LLM_RETRIES} tra {wait:.1f}s")
            time.sleep(wait)


# --- Spazio per la risposta entro il limite di token al minuto ---
# Con un limite al minuto (vedi tokens_per_minute_limit in factory.py), prompt
# + max_tokens di una richiesta non devono superarlo, altrimenti il provider la
# rifiuta. Il prompt degli specialisti cresce con la discussione (~5000 token
# gia' al secondo turno), quindi un max_tokens fisso a 4096 prima o poi sfora:
# lo calcoliamo a ogni chiamata.
_TOKEN_BUDGET_MARGIN = 300          # la stima dei token del prompt e' approssimata
_MIN_RESPONSE_TOKENS = 1000         # sotto, una risposta JSON rischia di troncarsi
_CHARS_PER_TOKEN = 3.0              # misurato ~3.4 sui prompt reali: 3.0 per stare larghi


def max_tokens_for(prompt: str, llm: ChatOpenAI) -> int | None:
    """max_tokens da usare per questa chiamata, o None per lasciare quello del
    client (provider senza limite di token al minuto)."""
    limit = tokens_per_minute_limit(llm)
    if limit is None:
        return None
    estimated_prompt_tokens = int(len(prompt) / _CHARS_PER_TOKEN)
    budget = limit - estimated_prompt_tokens - _TOKEN_BUDGET_MARGIN
    return max(_MIN_RESPONSE_TOKENS, min(llm.max_tokens or 4096, budget))


def stream_text(prompt: str, llm: ChatOpenAI) -> str:
    """Risposta testuale completa del modello, stampata in streaming sul
    terminale, con nuovi tentativi dopo un errore temporaneo e max_tokens entro
    il limite del provider."""
    max_tokens = max_tokens_for(prompt, llm)
    client = llm.bind(max_tokens=max_tokens) if max_tokens else llm

    def _stream():
        # La risposta si ricostruisce da zero a ogni tentativo: un errore puo'
        # arrivare anche a meta' dello streaming (osservato in test reale).
        full_response = ""
        for chunk in client.stream(prompt):
            content = chunk.content
            print(content, end="", flush=True)
            full_response += content
        print("\n")
        return full_response

    return call_with_retry(_stream)


# --- Lettura della risposta JSON ---
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict:
    """Oggetto JSON contenuto nella risposta di un modello.

    I modelli non restituiscono sempre JSON "puro": alcuni ("thinking", es.
    qwen/qwen3.6-27b) antepongono un blocco <think>...</think> di
    ragionamento, altri racchiudono il JSON in ```json ... ``` o aggiungono una
    frase prima/dopo (tutti casi osservati in test reale). Prima questa pulizia
    c'era solo per specialisti e foto - supervisore, intake, revisore e primario
    fallivano con un modello "thinking". Solleva json.JSONDecodeError (come
    json.loads) se non c'e' un oggetto JSON valido, cosi' i nodi mantengono le
    loro reti di sicurezza.
    """
    clean = _THINK_BLOCK.sub("", text or "")
    clean = clean.replace("```json", "").replace("```", "").strip()
    match = _JSON_OBJECT.search(clean)
    data = json.loads(match.group(0) if match else clean)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("la risposta non e' un oggetto JSON", clean, 0)
    return data
