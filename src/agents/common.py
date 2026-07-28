# Configurazione condivisa tra tutti i moduli di agents/: client LLM, connessione
# al database, e piccole utility comuni (stream_response, l'autore "System" usato
# nei messaggi di sistema).
from src.database import MedicalDatabase
from src.settings import get_settings
from src.llm import get_llm

SYSTEM_AUTHOR = "System"


def stream_response(prompt_current_card):
    full_response = ""
    for chunk in llm_agents.stream(prompt_current_card):
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

# Database
mdb = MedicalDatabase()
