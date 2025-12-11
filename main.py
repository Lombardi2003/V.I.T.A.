from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from state import MedicalState
from nodes import supervisor_node, cardiologist_node, neurologist_node, primary_node, color_node

# --- 1. FUNZIONE DI ROUTING ---
def route_supervisor(state: MedicalState):
    next_dest = state["next_step"]
    
    if next_dest == "FINISH":
        return "primario"
    
    return next_dest

# --- 2. COSTRUZIONE DEL GRAFO ---
workflow = StateGraph(MedicalState)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("cardiologo", cardiologist_node)
workflow.add_node("neurologo", neurologist_node)
workflow.add_node("primario", primary_node)
workflow.add_node("triage_officer", color_node)

# --- 3. ARCHI ---
workflow.set_entry_point("supervisor")

workflow.add_conditional_edges(
    "supervisor",
    route_supervisor,
    {
        "cardiologo": "cardiologo",
        "neurologo": "neurologo",
        "primario": "primario"
    }
)

workflow.add_edge("cardiologo", "supervisor")
workflow.add_edge("neurologo", "supervisor")
workflow.add_edge("primario", "triage_officer")
workflow.add_edge("triage_officer", END)

app = workflow.compile()

# --- 4. ESECUZIONE ---
if __name__ == "__main__":
    print("--- 🏥 SISTEMA DI TRIAGE ATTIVO ---")
    user_input = input("Descrivi i sintomi del paziente: ")
    
    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "next_step": "",
        "diagnosis": ""
    }
    
    for event in app.stream(initial_state):
        for node_name, value in event.items():
            
            if not value:
                continue
            
            # Messaggi generati da ogni nodo
            if "messages" in value:
                last_msg = value["messages"][-1]
                print(f"\n{'='*20} {node_name.upper()} {'='*20}")
                print(last_msg.content)
            
            # Decisioni del supervisore
            if "next_step" in value:
                print(f"\n>> Supervisore chiama: {value['next_step']}")

            # Referto del Primario
            if "diagnosis" in value:
                print(f"\n\n{'#'*30}\nREFERTO FINALE\n{'#'*30}")
                print(value["diagnosis"])

            # Codice Colore del Triage Officer
            if "priority" in value:
                color = value["priority"]
                icon = "🔴" if "ROSSO" in color else "🟡" if "GIALLO" in color else "🟢"
                print(f"\n\n{icon} CODICE ASSEGNATO: {color} {icon}\n")

    print("\n--- ✅ PROCESSO COMPLETATO ---")