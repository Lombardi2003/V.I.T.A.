"""Chainlit entry point: starts a conversation and feeds each operator message to the graph."""

import asyncio
from datetime import datetime
import chainlit as cl
import openai
import uuid
from chainlit.input_widget import Select
from langchain_core.messages import HumanMessage
from scripts.setup_env import ensure_env, ensure_session_secret

# Must run before the imports below, which read the settings.
ensure_env()
ensure_session_secret()

from src.state import MedicalState, PatientCard, PhotoAnalysis
from src.graph import generate_graph, thread_config
from src import chat_history, model_choice
from src.rag.retriever import warm_up
from src.log import get_logger

log = get_logger("app")

app = generate_graph()  # The compiled graph, built once and shared by every conversation.

# Load the embedding model and the index now, not during the first specialist's turn.
warm_up()


@cl.data_layer
def data_layer():
    """The archive of the chats: with it, Chainlit shows the past conversations in the sidebar."""
    return chat_history.build_data_layer()


@cl.header_auth_callback
def automatic_user(headers) -> cl.User:
    """Signs every visitor in as the same operator, without a login page: the history needs a user to belong to."""
    return cl.User(identifier=chat_history.OPERATOR, display_name=chat_history.OPERATOR_NAME)


# The two model choices of the panel: widget id, kind and label.
MODEL_WIDGETS = [
    ("text_model", "text", "Modello di testo (anagrafica, sintomi, supervisore, specialisti, primario)"),
    ("vision_model", "vision", "Modello per l'analisi della foto"),
]
LOCKED_NOTE = " - non modificabile: chat iniziata, aprirne una nuova per cambiarlo"


async def send_panel(locked: bool, problems: dict | None = None) -> None:
    """Shows the settings panel: the two model choices, locked once the chat has started, each with its notes."""
    widgets = []
    for widget_id, kind, text in MODEL_WIDGETS:
        labels = [model_choice.label(m) for m in model_choice.choices(kind)]
        # Under a choice: why the last one was refused, and which models are left out for a missing key.
        notes = [(problems or {}).get(kind), model_choice.missing_keys_note(kind)]
        widgets.append(Select(id=widget_id, label=text + (LOCKED_NOTE if locked else ""), values=labels,
                              initial_index=labels.index(model_choice.label(model_choice.current[kind])),
                              description=" ".join(note for note in notes if note) or None, disabled=locked))
    await cl.ChatSettings(widgets).send()


@cl.on_chat_start
async def start():
    """Opens a conversation: new thread, empty state, and the settings panel."""
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("chat_started", False)
    config = thread_config(thread_id)

    initial_state = MedicalState()
    app.update_state(config, initial_state.model_dump())

    await send_panel(locked=False)


@cl.on_settings_update
async def settings_update(new_settings: dict):
    """Applies the models confirmed in the panel, only before the first message: afterwards the choice is ignored."""
    problems = {}
    locked = bool(cl.user_session.get("chat_started"))
    if not locked:
        for widget_id, kind, _ in MODEL_WIDGETS:
            chosen = new_settings.get(widget_id)
            if chosen:
                # Checking a local model asks its server, which blocks: run it in a thread.
                problem = await asyncio.to_thread(model_choice.choose, kind, chosen)
                if problem:
                    problems[kind] = problem

    # Nothing about the models is written in the chat: the panel is sent again, showing the models really in use
    # and, under a choice that was refused, why.
    await send_panel(locked=locked, problems=problems)


@cl.on_message
async def main(message: cl.Message):
    """Adds the operator's message (and an attached image) to the state and resumes the graph."""
    thread_id = cl.user_session.get("thread_id")
    config = thread_config(thread_id)

    # A triage runs on one model from start to end: the choice is locked at the first message.
    if not cl.user_session.get("chat_started"):
        cl.user_session.set("chat_started", True)
        cl.user_session.set("chat_started_at", datetime.now())
        await send_panel(locked=True)

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

    await _title_chat(config)


async def _title_chat(config: dict) -> None:
    """Titles the chat: a neutral title from the first message, the patient's name once the card is confirmed."""
    state = app.get_state(config).values
    started_at = cl.user_session.get("chat_started_at")
    title = None
    if state.get("card_confirmed"):
        card = state.get("patient_card")
        title = chat_history.chat_title(card if isinstance(card, dict) else card.model_dump(), started_at)
    # Chainlit titles a chat with its first message, here the fiscal code: it is replaced at once.
    title = title or chat_history.new_chat_title(started_at)
    if title == cl.user_session.get("chat_title"):
        return
    try:
        if await chat_history.rename_chat(title):
            cl.user_session.set("chat_title", title)
    # The title is a convenience: a failure here must not disturb the triage.
    except Exception:
        log.exception("could not title the chat")


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
