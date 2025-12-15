# Librerie per LLM e messaggi
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
# Import dei moduli locali
from state import MedicalState
from config import SUPERVISOR_PROMPT, SPECIALIST_PROMPTS, PRIMARY_PROMPT

# Altre librerie
import json

# Configurazione API Key e modello LLM
USE_CLOUD_ACCELERATION = True

with open('api_key.json') as f:
    API_KEY = json.load(f)

# Configurazione del modello LLM
if USE_CLOUD_ACCELERATION:
    llm = ChatGroq(
        temperature=0, 
        model_name="llama-3.1-8b-instant",
        groq_api_key=API_KEY["groq_api_key"]
    )
else:
    llm = ChatOllama(model="llama3", temperature=0)

# Nodo del supervisore
def supervisor_node(state: MedicalState):
    """ Analizza la conversazione e decide chi deve intervenire.bStampa il pensiero in tempo reale (streaming)."""
    print("🚦 SUPERVISOR: ", end="")
    messages = state["messages"]
    prompt = [SystemMessage(content=SUPERVISOR_PROMPT)] + messages
    response = stream_response(prompt)
    decision_text = response.strip().lower()
    next_node = "FINISH"
    if "cardiologo" in decision_text:
        next_node = "cardiologo"
    elif "neurologo" in decision_text:
        next_node = "neurologo"
    return {"next_step": next_node}

# Nodo generico per specialisti
def specialist_node(state: MedicalState, role: str):
    """ Il cuore del ragionamento medico. Vale per qualsiasi specialista. """
    print(f"👨‍⚕️ {role.upper()}: ", end="")
    messages = state["messages"]
    prompt = [SystemMessage(content=SPECIALIST_PROMPTS[role])] + messages
    full_response = stream_response(prompt)
    final_content = f"**{role.upper()}**: {full_response}"
    return {"messages": [AIMessage(content=final_content)]}

# Wrapper per i nodi specifici
def cardiologist_node(state):
    return specialist_node(state, "cardiologo")

def neurologist_node(state):
    return specialist_node(state, "neurologo")

# Nodo del primario
def primary_node(state: MedicalState):
    """ Nodo finale che genera il report conclusivo. """
    print("🏥 PRIMARIO: ")
    messages = state["messages"]
    prompt = [SystemMessage(content=PRIMARY_PROMPT)] + messages
    full_response = stream_response(prompt)
    return {"diagnosis": AIMessage(content=full_response)}

# Funzione per lo streaming della risposta dei vari nodi
def stream_response(prompt_messages):
    full_response = ""
    for chunk in llm.stream(prompt_messages):
        content = chunk.content
        print(content, end="", flush=True)
        full_response += content
    print("\n")
    return full_response