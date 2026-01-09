# Librerie di base per la costruzione del grafo
from langgraph.graph import StateGraph, START,END
from langchain_core.messages import HumanMessage
# Import dei moduli locali
from state import MedicalState
from nodes import reviewer_node, user_node, supervisor_node, cardiologist_node, neurologist_node, primary_node, photography_node

# Altre librerie
import os
import shutil

# Funzione per la creazione del grafo di stato
def generate_graph():
    # Configurazione dello stato
    workflow = StateGraph(MedicalState)
    # Nodi
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("user", user_node)
    workflow.add_node("photography", photography_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("cardiologo", cardiologist_node)
    workflow.add_node("neurologo", neurologist_node)
    workflow.add_node("primario", primary_node)
    # Archi
    workflow.add_edge(START, "user") # Nodo iniziale (Entry Point)
    workflow.add_edge("user", "reviewer")

    workflow.add_conditional_edges(
        "reviewer",
        triage_complete,
        {
            True: "photography",
            False: "user",
        }
    )
    workflow.add_edge("user", "reviewer")

    workflow.add_edge("photography", "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        router,
        {
            "cardiologo": "cardiologo",
            "neurologo": "neurologo",
            "primario": "primario",
        }
    )
    workflow.add_edge("cardiologo", "supervisor")
    workflow.add_edge("neurologo", "supervisor")

    workflow.add_edge("primario", END)
    return workflow.compile()

# Funzioni di routing
def router(state: MedicalState):
    next_dest = state["next_step"]
    if next_dest == "FINISH":
        return "primario"
    return next_dest

def triage_complete(state: MedicalState):
    return state["triage_complete"]

# Main
if __name__ == "__main__":
    app = generate_graph()

    os.system('cls' if os.name == 'nt' else 'clear')
    terminal_width = shutil.get_terminal_size().columns
    titolo = "🩺 Virtual Intelligent Triage Assistant 🩺"
    print(titolo.center(terminal_width))

    app.invoke(MedicalState())

    titolo = "✅ PROCESSO COMPLETATO ✅"
    print(titolo.center(terminal_width))