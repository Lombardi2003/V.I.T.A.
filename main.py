# Librerie di base per la costruzione del grafo
from langgraph.graph import StateGraph, START,END
from langchain_core.messages import HumanMessage
# Import dei moduli locali
from state import MedicalState
from nodes import reviewer_node, request_more_information, supervisor_node, cardiologist_node, neurologist_node, primary_node

# Altre librerie
import os
import shutil

# Funzione per la creazione del grafo di stato
def generate_graph():
    # Configurazione dello stato
    workflow = StateGraph(MedicalState)
    # Nodi
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("user", request_more_information)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("cardiologo", cardiologist_node)
    workflow.add_node("neurologo", neurologist_node)
    workflow.add_node("primario", primary_node)
    # Archi
    workflow.add_edge(START, "reviewer") # Nodo iniziale (Entry Point)

    workflow.add_conditional_edges(
        "reviewer",
        route_reviewer,
        {
            "supervisor": "supervisor",
            "user": "user",
        }
    )
    workflow.add_edge("user", "reviewer")

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

    workflow.add_edge("primario", END)
    return workflow.compile()

# Funzioni di routing
def route_supervisor(state: MedicalState):
    next_dest = state["next_step"]
    if next_dest == "FINISH":
        return "primario"
    return next_dest
def route_reviewer(state: MedicalState):
    next_dest = state["next_step"]
    if next_dest == "user":
        return "user"
    return "supervisor"

# Main
if __name__ == "__main__":
    app = generate_graph()

    os.system('cls' if os.name == 'nt' else 'clear')
    terminal_width = shutil.get_terminal_size().columns
    titolo = "🩺 Virtual Intelligent Triage Assistant 🩺"
    print(titolo.center(terminal_width))
    

    initial_message = input("💬 USER: ")
    initial_state = {
        "general_history": [HumanMessage(content=initial_message)],
        "triage_history": [HumanMessage(content=initial_message)],
    }

    app.invoke(initial_state)

    titolo = "✅ PROCESSO COMPLETATO ✅"
    print(titolo.center(terminal_width))