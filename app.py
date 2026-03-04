import chainlit as cl
import uuid
from langchain_core.messages import HumanMessage, AIMessage
from src.state import get_initial_state
from src.graph import generate_graph
from src.logger_ui import ui_print

# Inizializziamo il grafo
app = generate_graph()

@cl.on_chat_start
async def start():
    """ Inizializzazione della sessione utente. """
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    
    # Prepariamo lo stato iniziale
    initial_state = get_initial_state()
    app.update_state(config, initial_state)

    await cl.Message(content="🩺 **V.I.T.A. System**\nConnessione stabilita. Per favore, inserisci il tuo **Codice Fiscale** per iniziare.").send()

@cl.on_message
async def main(message: cl.Message):
    thread_id = cl.user_session.get("thread_id")
    config = {"configurable": {"thread_id": thread_id}}

    # 1. Aggiorniamo lo stato con il nuovo messaggio dell'utente SENZA far partire il grafo
    # Questo aggiunge i sintomi allo 'zaino' (stato) proprio dove il grafo li aspetta
    app.update_state(config, {
        "general_history": [HumanMessage(content=message.content)],
        "triage_history": [HumanMessage(content=message.content)]
    })

    # 2. Ora diciamo al grafo di PROSEGUIRE. 
    # Passando 'None' come primo argomento, LangGraph capisce che non deve ricominciare 
    # dall'inizio, ma deve riprendere dal nodo dove c'era l'interrupt (es. user_node)
    async for event in app.astream_events(None, config=config, version="v1"):
        kind = event["event"]
        node_name = event.get("metadata", {}).get("langgraph_node", "")

        # Qui metti i tuoi ui_print o log tecnici
        if kind == "on_chain_start" and node_name:
            await ui_print(f"🚀 Ripresa esecuzione dal nodo: {node_name}")