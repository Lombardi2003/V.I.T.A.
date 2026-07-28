import chainlit as cl
import uuid
from chainlit.input_widget import Select
from langchain_core.messages import HumanMessage
from scripts.setup_env import ensure_env

ensure_env()  # completa .env con eventuali valori mancanti prima di importare i moduli che ne dipendono

from src.state import MedicalState
from src.graph import generate_graph
from src.llm import Models
from src.agents import llm_agents, llm_photography

# Inizializziamo il grafo
app = generate_graph()


@cl.on_chat_start
async def start():
    """ Inizializzazione della sessione utente. """
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    # Prepariamo lo stato iniziale
    initial_state = MedicalState()
    app.update_state(config, initial_state.model_dump())

    # Placeholder visivo (disabilitato, non collegato a nulla): mostra quali
    # sistemi/modelli il progetto puo' usare (vedi src/llm/models.py), senza
    # permettere di cambiarli da qui. La scelta reale del modello resta nel
    # .env, apposta - per un benchmark serve la certezza di quale modello e'
    # attivo durante tutti i test, cosa che un selettore cliccabile in chat
    # non garantirebbe. Questo pannello serve solo a documentare visivamente
    # l'esistenza della scelta (es. per screenshot nella tesi).
    text_choices = [
        f"Groq / {Models.Groq.TEXT_8B}",
        f"Groq / {Models.Groq.TEXT_70B}",
        f"Ollama / {Models.Ollama.TEXT_LLAMA3}",
    ]
    vision_choices = [
        f"Groq / {Models.Groq.VISION_MAVERICK}",
        f"Ollama / {Models.Ollama.VISION_MOONDREAM}",
    ]

    def _active_index(choices: list[str], model_name: str) -> int:
        # Riflette il modello davvero attivo (letto dal client gia' costruito
        # in base al .env), non un valore fisso - altrimenti il pannello
        # mostrerebbe un'informazione falsa appena cambi MODEL_NAME/VISION_MODEL_NAME
        # per un test.
        try:
            return next(i for i, c in enumerate(choices) if c.endswith(model_name))
        except StopIteration:
            return 0  # modello attivo non presente nel catalogo (es. prova estemporanea)

    await cl.ChatSettings(
        [
            Select(
                id="model_choice",
                label="Sistema LLM - testo (informativo, non modificabile qui)",
                values=text_choices,
                initial_index=_active_index(text_choices, llm_agents.model_name),
                disabled=True,
            ),
            Select(
                id="vision_model_choice",
                label="Sistema LLM - visione foto (informativo, non modificabile qui)",
                values=vision_choices,
                initial_index=_active_index(vision_choices, llm_photography.model_name),
                disabled=True,
            ),
        ]
    ).send()

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

            if kind == "on_chat_model_stream" and node_name == "chief_physician":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    await cl.Message(content=chunk.content).stream_token(chunk.content)  # type: ignore

    except Exception as e:
        await cl.Message(
            content=f"❌ Errore durante l'elaborazione: {str(e)}"
        ).send()