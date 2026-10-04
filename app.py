"""Chainlit entry point: starts a conversation and feeds each operator message to the graph."""

import chainlit as cl
import openai
import uuid
from chainlit.input_widget import Select
from langchain_core.messages import HumanMessage
from scripts.setup_env import ensure_env

# Must run before the imports below, which read the settings.
ensure_env()

from src.state import MedicalState, PatientCard, PhotoAnalysis
from src.graph import generate_graph, thread_config
from src.llm import describe_llm
from src.agents import llm, llm_vision
from src.rag.retriever import warm_up
from src.log import get_logger

log = get_logger("app")

app = generate_graph()  # The compiled graph, built once and shared by every conversation.

# Load the embedding model and the index now, not during the first specialist's turn.
warm_up()


@cl.on_chat_start
async def start():
    """Opens a conversation: new thread, empty state, and the panel showing the models in use."""
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    config = thread_config(thread_id)

    initial_state = MedicalState()
    app.update_state(config, initial_state.model_dump())

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
    """Adds the operator's message (and an attached image) to the state and resumes the graph."""
    thread_id = cl.user_session.get("thread_id")
    config = thread_config(thread_id)

    image_path = None

    if message.elements:
        for element in message.elements:
            if element.mime and element.mime.startswith("image/"):
                image_path = element.path
                break

    update = {
        "general_history": [HumanMessage(content=message.content)],
        "triage_history": [HumanMessage(content=message.content)]
    }
    
    if image_path:
        # patient_card is replaced whole: read it, set the photo, write it all back.
        current_card = PatientCard(**app.get_state(config).values.get("patient_card", {}))
        current_card.symptom.photo = PhotoAnalysis(photo_url=image_path, description="", injury_type="")
        update["patient_card"] = current_card.model_dump()

    app.update_state(config, update)

    try:
        async for _ in app.astream_events(None, config=config, version="v2"):
            pass

    # A node error stops the graph and arrives here: traceback to the log, short message to the chat.
    except Exception as e:
        log.exception("error while processing the message")
        await cl.Message(content=_operator_error_message(e)).send()


def _operator_error_message(error: Exception) -> str:
    """Short error message for the operator; technical details stay in the terminal."""
    if isinstance(error, openai.RateLimitError):
        return ("❌ Il servizio del modello ha raggiunto il limite di utilizzo. "
                "Riprovare tra qualche minuto inviando di nuovo l'ultimo messaggio.")
    if isinstance(error, (openai.APIConnectionError, openai.InternalServerError)):
        return ("❌ Il servizio del modello non è raggiungibile al momento. "
                "Riprovare inviando di nuovo l'ultimo messaggio.")
    return ("❌ Si è verificato un errore durante l'elaborazione. "
            "Riprovare inviando di nuovo l'ultimo messaggio.")
