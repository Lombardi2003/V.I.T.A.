from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from state import MedicalState
from config import SUPERVISOR_PROMPT, SPECIALIST_PROMPTS
from config import PRIMARY_PROMPT, TRIAGE_PROMPT

# --- 1. CONFIGURAZIONE DEL MODELLO ---
llm = ChatOllama(model="llama3", temperature=0)         # temperature=0 è fondamentale in medicina per evitare "allucinazioni" creative.

# --- 2. IL NODO SUPERVISORE ---
def supervisor_node(state: MedicalState):
    """
    Analizza la conversazione e decide chi deve intervenire.
    Non aggiunge messaggi alla chat, restituisce solo la direzione.
    """
    messages = state["messages"]
    
    prompt = [SystemMessage(content=SUPERVISOR_PROMPT)] + messages
    
    response = llm.invoke(prompt)
    decision_text = response.content.strip().lower()
    
    next_node = "FINISH" # Default
    
    if "cardiologo" in decision_text:
        next_node = "cardiologo"
    elif "neurologo" in decision_text:
        next_node = "neurologo"
    
    print(f"\n--- 🚦 SUPERVISOR DECISION: {next_node.upper()} ---\n")
    
    return {"next_step": next_node}

# --- 3. IL NODO SPECIALISTA (GENERICO) ---
def specialist_node(state: MedicalState, role: str):
    """
    Il cuore del ragionamento medico. Vale per qualsiasi specialista.
    """
    messages = state["messages"]
    
    role_prompt = SPECIALIST_PROMPTS[role]
    
    prompt = [SystemMessage(content=role_prompt)] + messages
    
    print(f"--- 👨‍⚕️ {role.upper()} IS THINKING... ---")
    response = llm.invoke(prompt)
    
    response.content = f"**{role.upper()}**: {response.content}"
    
    return {"messages": [response]}


# --- 4. WRAPPER SPECIFICI ---
def cardiologist_node(state):
    return specialist_node(state, "cardiologo")

def neurologist_node(state):
    return specialist_node(state, "neurologo")

# --- 5. IL NODO PRIMARIO ---
def primary_node(state: MedicalState):
    """
    Nodo finale che genera il report conclusivo.
    """
    messages = state["messages"]
    
    prompt = [SystemMessage(content=PRIMARY_PROMPT)] + messages
    
    print("\n--- 🏥 IL PRIMARIO STA SCRIVENDO IL REFERTO... ---")
    response = llm.invoke(prompt)
    
    return {"diagnosis": response.content}

# --- 6. IL NODO TRIAGE OFFICER ---
def color_node(state: MedicalState):
    """
    Legge tutto e decide SOLO il colore.
    """
    messages = state["messages"]
    diagnosis = state.get("diagnosis", "") # Si legge anche la diagnosi del primario
    
    context = f"DIAGNOSI FORMULATA: {diagnosis}\n\nSTORICO CHAT:\n"
    
    prompt = [
        SystemMessage(content=TRIAGE_PROMPT),
        HumanMessage(content=context)     ] + messages
    
    print("\n--- 🚨 VALUTAZIONE GRAVITÀ IN CORSO... ---")
    response = llm.invoke(prompt)
    
    # Pulizia base della stringa (toglie spazi o punti)
    color = response.content.strip().upper().replace(".", "")
    
    return {"priority": color}