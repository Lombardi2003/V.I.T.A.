# Configurazione condivisa tra tutti i moduli di nodes/: client LLM, connessione
# al database, e piccole utility comuni (stream_response, l'autore "System" usato
# nei messaggi di sistema).
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq

from src.database import MedicalDatabase
from src.settings import get_settings

SYSTEM_AUTHOR = "System"


def stream_response(prompt_current_card):
    full_response = ""
    for chunk in llm_agents.stream(prompt_current_card):
        content = chunk.content
        print(content, end="", flush=True)
        full_response += content
    print("\n")
    return full_response


# Configurazione del modello LLM
settings = get_settings()
USE_CLOUD_ACCELERATION = settings.use_cloud_acceleration
if USE_CLOUD_ACCELERATION:
    llm_agents = ChatGroq(
        temperature=0,
        model_name="llama-3.1-8b-instant",
        groq_api_key=settings.groq_api_key
    )
    llm_photography = ChatGroq(
        temperature=0,
        model_name="meta-llama/llama-4-maverick-17b-128e-instruct",
        groq_api_key=settings.groq_api_key,
        model_kwargs={"response_format": {"type": "json_object"}}
    )
else:
    llm_agents = ChatOllama(model="llama3", temperature=0)
    llm_photography = ChatOllama(model="moondream", temperature=0)

# Database
mdb = MedicalDatabase()
