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

# Modello piu' capace, usato solo da specialist_node per la discussione al
# tavolo: con TEXT_8B (il default sopra) gli specialisti ripetono la stessa
# domanda parola per parola senza rispondere a quella del collega, anche con
# istruzioni esplicite nel prompt di non farlo (osservato in test reale,
# vedi tests/test_round_table.py) - proviamo se un modello piu' grande segue
# meglio questo tipo di istruzione conversazionale. Solo in cloud (Groq):
# Ollama non ha un modello piu' grande catalogato, quindi in locale resta
# lo stesso llm_agents.
llm_specialist = get_llm(model_name=Models.Groq.TEXT_70B) if USE_CLOUD_ACCELERATION else llm_agents

# Database
mdb = MedicalDatabase()
