import chainlit as cl
import uuid
from langchain_core.messages import HumanMessage
from scripts.setup_env import ensure_env

ensure_env()  # completa .env con eventuali valori mancanti prima di importare i moduli che ne dipendono

from src.state import MedicalState
from src.graph import generate_graph
from src.logger_ui import ui_print
from pathlib import Path
import shutil
import os




# Inizializziamo il grafo
app = generate_graph()
NODI_PENSIERO = {"reviewer", "photography", "supervisor", "router", "cardiologo", "neurologo", "ortopedico", "gastroenterologo", "dermatologo", "pneumologo", "otorino", "oculista", "urologo", "medico_generale", "primario"}
TEMP_IMAGE_DIR = Path("temp_images")  # cartella base nel progetto


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

    # Protezione: se session_dir non esiste ancora, creala
    session_dir_str = cl.user_session.get("session_dir")
    if not session_dir_str:
        session_dir = TEMP_IMAGE_DIR / thread_id
        session_dir.mkdir(parents=True, exist_ok=True)
        cl.user_session.set("session_dir", str(session_dir))
        session_dir_str = str(session_dir)
    
    session_dir = Path(session_dir_str)

    image_path = None

    if message.elements:
        for element in message.elements:
            if element.mime and element.mime.startswith("image/"):
                # Copia dalla cartella temporanea di Chainlit alla tua cartella sessione
                dest = session_dir / element.name
                shutil.copy(element.path, dest)
                image_path = str(dest)
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
                    "descrizione": "",
                    "tipo_danno": ""
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

            if kind == "on_chat_model_stream" and node_name == "primario":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    await cl.Message(content=chunk.content).stream_token(chunk.content)  # type: ignore

    except Exception as e:
        await cl.Message(
            content=f"❌ Errore durante l'elaborazione: {str(e)}"
        ).send()

@cl.on_chat_end
async def end():
    import shutil
    temp_dir = cl.user_session.get("temp_dir")
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)