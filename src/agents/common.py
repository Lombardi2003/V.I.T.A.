# Configurazione condivisa tra tutti i moduli di agents/: client LLM, connessione
# al database, e piccole utility comuni (stream_response). I nomi degli autori
# per i messaggi (es. "System") vivono in authors.py, non qui.
from src.database import MedicalDatabase
from src.settings import get_settings
from src.llm import get_llm, Models


def stream_response(prompt_current_card, llm=None):
    llm = llm or llm_agents
    full_response = ""
    for chunk in llm.stream(prompt_current_card):
        content = chunk.content
        print(content, end="", flush=True)
        full_response += content
    print("\n")
    return full_response


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
