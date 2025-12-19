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
    """ Analizza la Patient Card e decide se sono necessarie più informazioni dall'utente. """
    print("🧐 REVIEWER: ", end="", flush=True)
    current_card = state.get("patient_card", {})
    user_msg = state["triage_history"][-1].content
    card_str = json.dumps(current_card, ensure_ascii=False)  
    prompt = REVIEWER_PROMPT.format(patient_card=card_str, user_input=user_msg)    
    content = stream_response(prompt)
    
    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)
        extracted_card = data.get("updated_card", {})
        status = data.get("status", "INSUFFICIENTE").upper()
        reply = data.get("message_to_user")
        current_card.update({k: v for k, v in extracted_card.items() if v}) # aggiorna solo se c'è un valore
        
    except json.JSONDecodeError:
        status = "INSUFFICIENTE"
        reply = "Scusa, non ho capito bene. Puoi ripetere i tuoi dati?"
    
    print(f"   -> Status: {status}")
    print(f"   -> Dati attuali: {current_card}")
    print(f"   -> Risposta all'utente: {reply if reply else "Perfetto, raccolta dati completa ✨"}")

    return {
        "patient_card": current_card,          
        "triage_history": [AIMessage(content=reply)], 
        "general_history": [AIMessage(content=reply)],
        "next_step": "user" if "INSUFFICIENTE" in status else "supervisor",
        "triage_complete": True if status == "SUFFICIENTE" else False
    }

# Nodo per richiedere più informazioni all'utente
def user_node(state: MedicalState):
    """ Chiede ulteriori informazioni all'utente riguardo ai sintomi. """
    message = input("💬 USER: ")
    while message == "" or message.isspace():
        print("⚠️ Per favore, fornisci una risposta valida.")
        message = input("💬 USER: ")
    return {"general_history": [HumanMessage(content=message)], "triage_history": [HumanMessage(content=message)]}

# Nodo del supervisore
def supervisor_node(state: MedicalState):
    """ Analizza la conversazione e decide chi deve intervenire. Stampa FINISH se la diagnosi è completa. """
    print("🚦 SUPERVISOR: ", end="", flush=True)
    current_card = state["general_history"]
    prompt = [SystemMessage(content=SUPERVISOR_PROMPT)] + current_card
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
    current_card = state["triage_history"]
    prompt = [SystemMessage(content=SPECIALIST_PROMPTS[role])] + current_card
    full_response = stream_response(prompt)
    final_content = f"**{role.upper()}**: {full_response}"
    return {"general_history": [AIMessage(content=final_content)]}

# Wrapper per i nodi specifici
def cardiologist_node(state):
    print(f"🫀  CARDIOLOGIT: ", end="", flush=True)
    return specialist_node(state, "cardiologo")

def neurologist_node(state):
    print(f"🧠 NEUROLOGIST: ", end="", flush=True)
    return specialist_node(state, "neurologo")


# Nodo generico per specialisti
def specialist_node(state: MedicalState, role: str):
    """ Il cuore del ragionamento medico. Vale per qualsiasi specialista. """
    current_card = state["triage_history"]
    prompt = [SystemMessage(content=SPECIALIST_PROMPTS[role])] + current_card
    full_response = stream_response(prompt)
    final_content = f"**{role.upper()}**: {full_response}"
    return {"general_history": [AIMessage(content=final_content)]}

# Nodo del primario
def primary_node(state: MedicalState):
    """ Nodo finale che genera il report conclusivo. """
    print("🏥 PRIMARIO: ", end="", flush=True)
    current_card = state["general_history"]
    prompt = [SystemMessage(content=PRIMARY_PROMPT)] + current_card
    full_response = stream_response(prompt)
    return {"diagnosis": AIMessage(content=full_response), "general_history": [AIMessage(content=full_response)]}

# Funzione per lo streaming della risposta dei vari nodi
def stream_response(prompt_current_card):
    full_response = ""
    for chunk in llm.stream(prompt_current_card):
        content = chunk.content
        print(content, end="", flush=True)
        full_response += content
    print("\n")
    return full_response