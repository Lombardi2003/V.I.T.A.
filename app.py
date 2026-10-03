import chainlit as cl
import openai
import traceback
import uuid
from chainlit.input_widget import Select
from langchain_core.messages import HumanMessage
from scripts.setup_env import ensure_env

ensure_env()  # completa .env con eventuali valori mancanti prima di importare i moduli che ne dipendono

from src.state import MedicalState, PatientCard, PhotoAnalysis
from src.graph import generate_graph, thread_config
from src.llm import describe_llm
from src.agents import llm, llm_vision
from src.rag.retriever import warm_up

# Inizializziamo il grafo
app = generate_graph()

# Modello di embedding e indice delle linee guida caricati subito, non al primo
# turno del primo specialista (vedi src/rag/retriever.py).
warm_up()


@cl.on_chat_start
async def start():
    """ Inizializzazione della sessione utente. """
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    config = thread_config(thread_id)

    # Prepariamo lo stato iniziale
    initial_state = MedicalState()
    app.update_state(config, initial_state.model_dump())

    # Pannello informativo (disabilitato): mostra i modelli DAVVERO in uso,
    # letti dai client gia' costruiti, senza permettere di cambiarli da qui. La
    # scelta si fa in cima a src/llm/factory.py, apposta - per un benchmark
    # serve la certezza di quale modello e' attivo durante tutti i test, cosa
    # che un selettore cliccabile in chat non garantirebbe.
    active = [
        ("text_model", "Modello - testo (anagrafica, sintomi, supervisore, specialisti, primario)", llm),
        ("vision_model", "Modello - analisi della foto", llm_vision),
    ]
    await cl.ChatSettings(
        [
            Select(id=widget_id, label=f"{label} (informativo)", values=[describe_llm(llm)],
                   initial_index=0, disabled=True)
            for widget_id, label, llm in active
        ]
    ).send()

@cl.on_message
async def main(message: cl.Message):
    thread_id = cl.user_session.get("thread_id")
    config = thread_config(thread_id)

    image_path = None

    if message.elements:
        for element in message.elements:
            if element.mime and element.mime.startswith("image/"):
                # Chainlit salva già il file in .files con un nome alfanumerico univoco
                image_path = element.path
                break


    update = {
        "general_history": [HumanMessage(content=message.content)],
        "triage_history": [HumanMessage(content=message.content)]
    }
    
    if image_path:
        # patient_card non ha un reducer di merge (vedi src/state.py): scrivere
        # solo {"symptom": {"photo": ...}} sostituirebbe l'INTERA cartella
        # clinica, cancellando anagrafica e sintomo gia' raccolti - leggiamo
        # quindi la cartella attuale, aggiorniamo solo il campo foto, e
        # riscriviamo tutto (stesso pattern gia' usato da intake_node/reviewer_node).
        current_card = PatientCard(**app.get_state(config).values.get("patient_card", {}))
        current_card.symptom.photo = PhotoAnalysis(photo_url=image_path, description="", injury_type="")
        update["patient_card"] = current_card.model_dump()

    app.update_state(config, update)

    # Un errore in un nodo interrompe il grafo e arriva qui come eccezione
    # (astream_events non emette un evento dedicato agli errori dei nodi):
    # il traceback va nel terminale, in chat solo il messaggio breve.
    try:
        async for _ in app.astream_events(None, config=config, version="v2"):
            pass

    except Exception as e:
        print(f"❌ ERRORE durante l'elaborazione: {e}")
        traceback.print_exc()
        await cl.Message(content=_operator_error_message(e)).send()


def _operator_error_message(error: Exception) -> str:
    """Messaggio d'errore per l'operatore: breve e comprensibile. Il dettaglio
    tecnico (codici dell'API, identificativo dell'account del provider) resta
    solo nel terminale - prima finiva in chat cosi' com'era."""
    if isinstance(error, openai.RateLimitError):
        return ("❌ Il servizio del modello ha raggiunto il limite di utilizzo. "
                "Riprovare tra qualche minuto inviando di nuovo l'ultimo messaggio.")
    if isinstance(error, (openai.APIConnectionError, openai.InternalServerError)):
        return ("❌ Il servizio del modello non è raggiungibile al momento. "
                "Riprovare inviando di nuovo l'ultimo messaggio.")
    return ("❌ Si è verificato un errore durante l'elaborazione. "
            "Riprovare inviando di nuovo l'ultimo messaggio.")