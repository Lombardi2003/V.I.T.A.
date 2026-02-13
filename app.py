import chainlit as cl
from langgraph.checkpoint.memory import MemorySaver # O AsyncSqliteSaver per persistenza su disco
from langchain_core.messages import HumanMessage
import uuid

from src.state import get_initial_state
from src.graph import generate_graph

app = generate_graph()

@cl.on_chat_start
async def start():
    """
    Questo viene eseguito SOLO quando l'utente apre la pagina o ricarica.
    Serve a creare lo 'scheletro' dello stato vuoto.
    """
    # Creiamo un ID univoco per questa conversazione
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    
    # Configurazione per dire a LangGraph "Salva tutto sotto questo ID"
    config = {"configurable": {"thread_id": thread_id}}
    
    # INIZIALIZZAZIONE (Solo la prima volta!)
    # Carichiamo lo stato iniziale (card vuota, ecc.) nella memoria
    initial_state = get_initial_state()
    
    # Usiamo aupdate_state per "iniettare" lo stato senza far partire il grafo
    # In questo modo patient_card è pronta e non avrai KeyError
    await app.aupdate_state(config, initial_state)

    await cl.Message(content="Ciao! Sono pronto. Raccontami come stai.").send()

@cl.on_message
async def main(message: cl.Message):
    """
    Questo viene eseguito ogni volta che l'utente scrive.
    """
    thread_id = cl.user_session.get("thread_id")
    config = {"configurable": {"thread_id": thread_id}}


    inputs = {
        "general_history": [HumanMessage(content=message.content)],
        "triage_history": [HumanMessage(content=message.content)]
    }

    async for event in app.astream_events(inputs, config=config, version="v1"):
        # ... tua logica di visualizzazione ...
        pass