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


# --- Lettura robusta dei campi della risposta JSON di un modello ---
# I modelli non rispettano sempre il tipo richiesto (osservato in prove reali e
# verificato con risposte finte): un si'/no scritto come vero/falso o con
# l'accento, una lista scritta come testo singolo, un nome scritto come
# oggetto. Queste funzioni riportano ogni campo alla forma attesa, invece di
# far saltare in silenzio la logica che lo legge.

def as_list(value) -> list:
    """Una lista, anche se il modello ha scritto un testo singolo
    ("penicillina" invece di ["penicillina"]) - senza, un testo veniva letto
    lettera per lettera."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def is_yes(value) -> bool:
    """Si': true, "si", "sì", "si'", "yes" (anche come valore booleano)."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "si", "sì", "si'", "yes"}


def is_no(value) -> bool:
    """No: false, "no" (anche come valore booleano)."""
    if isinstance(value, bool):
        return not value
    return str(value).strip().lower() in {"false", "no"}


def as_text(value) -> str:
    """Testo, anche se il modello ha scritto una lista o un oggetto (le parti
    unite da virgole) invece di un testo - prima finivano in chat come
    "['a', 'b']" o "{'esame': ...}"."""
    if value is None:
        return ""
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return ", ".join(t for t in (as_text(v) for v in value) if t)
    return str(value).strip()


settings = get_settings()

# "Ecco il tuo LLM": creati una volta sola, all'avvio.
llm = get_llm()                    # tutti i nodi di testo (anagrafica, sintomi, supervisore, specialisti, primario)
llm_vision = get_llm(vision=True)  # analisi della foto

# Certezza di quali modelli stanno girando davvero (letti dai client appena
# creati, non dalla configurazione): utile soprattutto per test e benchmark.
print(f"🤖 Modelli attivi: testo = {describe_llm(llm)} | foto = {describe_llm(llm_vision)}")

# Database
mdb = MedicalDatabase()
