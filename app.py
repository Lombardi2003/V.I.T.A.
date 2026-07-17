import chainlit as cl
import uuid
from langchain_core.messages import HumanMessage
from scripts.setup_env import ensure_env

ensure_env()  # completa .env con eventuali valori mancanti prima di importare i moduli che ne dipendono

from src.state import MedicalState
from src.graph import generate_graph
from src.logger_ui import ui_print

# Inizializziamo il grafo
app = generate_graph()
NODI_PENSIERO = {"reviewer", "photography", "supervisor", "router", "cardiologist", "neurologist", "orthopedist", "gastroenterologist", "dermatologist", "pulmonologist", "ent", "ophthalmologist", "urologist", "general_practitioner", "chief_physician"}


@cl.on_chat_start
async def start():
    """ Inizializzazione della sessione utente. """
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    
    # Prepariamo lo stato iniziale
    initial_state = MedicalState()
    app.update_state(config, initial_state.model_dump())

@cl.on_message
async def main(message: cl.Message):
    thread_id = cl.user_session.get("thread_id")
    config = {"configurable": {"thread_id": thread_id}}

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
        update["patient_card"] = {
            "symptom": {
                "photo": {
                    "photo_url": image_path,
                    "description": "",
                    "injury_type": ""
                }
            }
        }

    app.update_state(config, update)

    try:
        async for event in app.astream_events(None, config=config, version="v2"):
            kind = event["event"]
            node_name = event.get("metadata", {}).get("langgraph_node", "")

            if kind == "on_chain_error":
                node_name = event.get("metadata", {}).get("langgraph_node", "")
                error = event.get("data", {}).get("error", "")
                print(f"❌ ERRORE in {node_name}: {error}")  # ← aggiungi error
                import traceback
                traceback.print_exc()
                await cl.Message(content=f"❌ Errore durante l'elaborazione: {error}").send()

            if kind == "on_chain_start" and node_name in NODI_PENSIERO:
                await ui_print(f"⚙️ {node_name} in elaborazione...")

            if kind == "on_chat_model_stream" and node_name == "chief_physician":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    await cl.Message(content=chunk.content).stream_token(chunk.content)  # type: ignore

    except Exception as e:
        await cl.Message(
            content=f"❌ Errore durante l'elaborazione: {str(e)}"
        ).send()