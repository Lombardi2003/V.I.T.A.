# Librerie per LLM e messaggi
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
# Import dei moduli locali
from state import MedicalState
from config import REVIEWER_PROMPT, SUPERVISOR_PROMPT, SPECIALIST_PROMPTS, PRIMARY_PROMPT

# Altre librerie
import json

# Configurazione API Key
with open('api_key.json') as f:
    API_KEY = json.load(f)

# Configurazione del modello LLM
USE_CLOUD_ACCELERATION = True
if USE_CLOUD_ACCELERATION:
    llm = ChatGroq(
        temperature=0, 
        model_name="llama-3.1-8b-instant",
        groq_api_key=API_KEY["groq_api_key"]
    )
else:
    llm = ChatOllama(model="llama3", temperature=0)

# Nodo del revisore
def reviewer_node(state: MedicalState):
    """ Analizza l'input dell'utente e decide se le informazioni sono sufficienti per fare una diagnosi."""
    print("🧐 REVIEWER: ", end="")
    messages = state["triage_history"]
    prompt = [SystemMessage(content=REVIEWER_PROMPT)] + messages
    response = stream_response(prompt)

    decision_text = response.strip().lower()
    next_node = "sufficiente"
    if "insufficiente" in decision_text:
        next_node = "user"
    elif "sufficiente" in decision_text:
        next_node = "supervisor"
    return {"next_step": next_node, "triage_history": [AIMessage(content=response)], "general_history": [AIMessage(content=response)]}

# Nodo per richiedere più informazioni all'utente
def request_more_information(state: MedicalState):
    """ Chiede ulteriori informazioni all'utente riguardo ai sintomi. """
    message = input("💬 USER: ")
    return {"general_history": [HumanMessage(content=message)], "triage_history": [HumanMessage(content=message)]}

# Nodo del supervisore
def supervisor_node(state: MedicalState):
    """ Analizza la conversazione e decide chi deve intervenire. Stampa FINISH se la diagnosi è completa. """
    print("🚦 SUPERVISOR: ", end="")
    messages = state["general_history"]
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
    messages = state["triage_history"]
    prompt = [SystemMessage(content=SPECIALIST_PROMPTS[role])] + messages
    full_response = stream_response(prompt)
    final_content = f"**{role.upper()}**: {full_response}"
    return {"general_history": [AIMessage(content=final_content)]}

# Wrapper per i nodi specifici
def cardiologist_node(state):
    return specialist_node(state, "cardiologo")

def neurologist_node(state):
    return specialist_node(state, "neurologo")

# Nodo del primario
def primary_node(state: MedicalState):
    """ Nodo finale che genera il report conclusivo. """
    print("🏥 PRIMARIO: ")
    messages = state["general_history"]
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