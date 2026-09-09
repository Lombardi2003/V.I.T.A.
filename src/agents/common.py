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
# tavolo. Storico dei tentativi su Groq (tutti con lo stesso limite di fondo,
# 8K token/minuto su questo account): TEXT_8B/TEXT_70B non sono piu' nel
# catalogo modelli dell'account; TEXT_120B/TEXT_20B stessa famiglia, stesso
# limite TPM; TEXT_COMPOUND_MINI (sistema "agentic", 70K TPM dichiarati)
# provato e SCARTATO - un errore reale ha rivelato che si appoggia
# internamente a TEXT_120B per generare la risposta, quindi consuma lo stesso
# budget da 8K TPM, nessun vantaggio reale.
#
# TEXT_LLAMA3 su OLLAMA IN LOCALE e' stato provato con successo (nessun
# limite di token/minuto, l'app non si blocca piu' - vedi asyncio.to_thread
# in specialist_node), ma con un compromesso di qualita' notato in test reale
# (llama3 8B a volte scrive parte del ragionamento in inglese anziche' in
# italiano). GEMINI (Google AI Studio, piano gratuito, provider forzato
# esplicitamente come sopra - indipendente da USE_CLOUD_ACCELERATION): un
# terzo provider con una propria quota separata da quella Groq, per lo stesso
# motivo (il tavolo genera molte chiamate consecutive durante i test) ma
# restando su un modello cloud piu' capace invece che locale. Verificato con
# una chiamata reale a GET /v1beta/openai/models con la chiave dell'account.
# Gli altri nodi (intake/reviewer/supervisor/primario) restano su Groq/.env
# come prima, invariati - e' una scelta isolata al solo tavolo, per la fase
# di test.
llm_specialist = get_llm(model_name=Models.Gemini.TEXT_FLASH, provider="gemini")

# Database
mdb = MedicalDatabase()
