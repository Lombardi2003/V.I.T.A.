# Configurazione condivisa tra tutti i moduli di agents/: client LLM, connessione
# al database, e piccole utility comuni (stream_response). I nomi degli autori
# per i messaggi (es. "System") vivono in authors.py, non qui.
import re
import time

import openai

from src.database import MedicalDatabase
from src.settings import get_settings
from src.llm import get_llm, Models

# Nuovi tentativi per gli errori TEMPORANEI dell'API (non per quelli
# definitivi come chiave non valida o richiesta malformata, che fallirebbero
# identici). Il caso tipico e' il 429 di Groq (limite di token al minuto,
# osservato in test reale durante il tavolo rotondo): prima non veniva gestito
# in nessun nodo tranne gli specialisti - un 429 nel supervisore, nell'intake
# o nel primario mandava in errore l'intera conversazione - e negli specialisti
# il turno veniva solo saltato e ritentato subito dal router, senza pause, cioe'
# quasi sempre di nuovo oltre il limite.
MAX_LLM_RETRIES = 2
MAX_RETRY_WAIT_SECONDS = 30  # oltre, meglio arrendersi che bloccare la chat
DEFAULT_RETRY_WAIT_SECONDS = 5
_TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,   # include APITimeoutError
    openai.InternalServerError,
)
# Groq indica quanto aspettare nel messaggio d'errore: "Please try again in 6.8325s"
# (oppure "in 1m2.5s" quando l'attesa supera il minuto).
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


def stream_response(prompt_current_card, llm=None):
    llm = llm or llm_agents

    def _stream():
        # La risposta si ricostruisce da zero a ogni tentativo: un errore puo'
        # arrivare anche a meta' dello streaming (osservato in test reale).
        full_response = ""
        for chunk in llm.stream(prompt_current_card):
            content = chunk.content
            print(content, end="", flush=True)
            full_response += content
        print("\n")
        return full_response

    return call_with_retry(_stream)


# Configurazione del modello LLM (Groq o Ollama, vedi src/llm/factory.py)
settings = get_settings()
USE_CLOUD_ACCELERATION = settings.use_cloud_acceleration
llm_agents = get_llm()
llm_photography = get_llm(vision=True)

# Modello dedicato, usato solo da specialist_node per la discussione al
# tavolo. Storico dei tentativi (tutti con un qualche limite che rende
# difficili i test ripetuti nella stessa sessione):
# - Groq TEXT_8B/TEXT_70B: non piu' nel catalogo modelli dell'account.
# - Groq TEXT_120B/TEXT_20B: stesso limite di fondo, 8K token/minuto.
# - Groq TEXT_COMPOUND_MINI (sistema "agentic", 70K TPM dichiarati): provato
#   e SCARTATO - un errore reale ha rivelato che si appoggia internamente a
#   TEXT_120B per generare la risposta, quindi consuma lo stesso budget da 8K
#   TPM, nessun vantaggio reale.
# - Ollama TEXT_LLAMA3 in locale: provato con successo (nessun limite, l'app
#   non si blocca piu' - vedi asyncio.to_thread in specialist_node), ma con
#   un compromesso di qualita' notato in test reale (llama3 8B a volte scrive
#   parte del ragionamento in inglese anziche' in italiano).
# - Gemini TEXT_FLASH (Google AI Studio, piano gratuito): alta precisione
#   clinica nei test, ma limite di 20 richieste/GIORNO (non al minuto) sul
#   piano gratuito - esaurito nella stessa sessione di test con poche
#   conversazioni del tavolo rotondo (ogni turno = una chiamata, i
#   mini-consulti ne aggiungono altre).
#
# Provato a tornare su Groq TEXT_20B, ma il tavolo rotondo genera piu'
# chiamate consecutive SENZA pause (nessun interrupt "user" tra un turno di
# specialista e il successivo, a differenza di intake/reviewer che aspettano
# la risposta del paziente) - questo esaurisce l'8K TPM di Groq quasi subito
# quando la discussione ha piu' di 2-3 battute, molto piu' in fretta di
# quanto accadesse sui nodi "lenti". Tornati su Gemini TEXT_FLASH.
#
# Entrambe le chiavi Gemini (gemini_api_key e gemini_fra_api_key, vedi
# settings.py) hanno esaurito la quota gratuita di 20 richieste/giorno durante
# i test di oggi, in momenti diversi - la quota e' per-progetto Google Cloud,
# non per-chiave, quindi le due si esauriscono indipendentemente.
#
# Tornati su Groq TEXT_20B per la fase di sviluppo del RAG (vedi src/rag/):
# in questa fase serve iterare rapidamente sull'integrazione, non tanto
# discussioni lunghe del tavolo - Groq resta piu' rapido a rispondere quando
# funziona, anche con lo svantaggio noto dell'8K TPM condiviso. Gli altri nodi
# (intake/reviewer/supervisor/primario) restano su Groq/.env come sempre.
llm_specialist = get_llm(model_name=Models.Groq.TEXT_20B, provider="groq")

# Database
mdb = MedicalDatabase()
