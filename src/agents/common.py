# Configurazione condivisa tra tutti i moduli di agents/: client LLM, connessione
# al database, e piccole utility comuni (stream_response). I nomi degli autori
# per i messaggi (es. "System") vivono in authors.py, non qui.
#
# Gli agenti non sanno quale provider/modello usano: chiedono il proprio LLM a
# src/llm/ (quali modelli usa l'app e' scelto in cima a src/llm/factory.py), e
# chiamate/lettura delle risposte passano da src/llm/calls.py.
from src.database import MedicalDatabase
from src.settings import get_settings
from src.llm import call_with_retry, describe_llm, extract_json, get_llm, stream_text


def stream_response(prompt_current_card, llm_client=None):
    """Risposta completa del modello per questo prompt (llm se non indicato) -
    vedi stream_text in src/llm/calls.py."""
    return stream_text(prompt_current_card, llm_client or llm)


settings = get_settings()

# "Ecco il tuo LLM": creati una volta sola, all'avvio.
llm = get_llm()                    # tutti i nodi di testo (anagrafica, sintomi, supervisore, specialisti, primario)
llm_vision = get_llm(vision=True)  # analisi della foto

# Certezza di quali modelli stanno girando davvero (letti dai client appena
# creati, non dalla configurazione): utile soprattutto per test e benchmark.
print(f"🤖 Modelli attivi: testo = {describe_llm(llm)} | foto = {describe_llm(llm_vision)}")

# Database
mdb = MedicalDatabase()
