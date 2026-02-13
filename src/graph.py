# Librerie di base per la costruzione del grafo
from langgraph.graph import StateGraph, START,END
from langgraph.checkpoint.memory import MemorySaver

# Import dei moduli locali
from src.state import MedicalState, get_initial_state
from src.nodes import reviewer_node, user_node, supervisor_node, cardiologist_node, neurologist_node, primary_node, photography_node, orthopedic_node, gastroenterologist_node, dermatologist_node, pneumologist_node, ent_node, ophthalmologist_node, urologist_node, general_practitioner_node

# Funzione per la creazione del grafo di stato
def generate_graph():
    # Configurazione dello stato
    workflow = StateGraph(MedicalState)
    # Nodi
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("user", user_node)
    workflow.add_node("photography", photography_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("router", router)

    # Specialisti
    workflow.add_node("cardiologo", cardiologist_node)
    workflow.add_node("neurologo", neurologist_node)
    workflow.add_node("ortopedico", orthopedic_node)
    workflow.add_node("gastroenterologo", gastroenterologist_node)
    workflow.add_node("dermatologo", dermatologist_node)
    workflow.add_node("pneumologo", pneumologist_node)
    workflow.add_node("otorino", ent_node)
    workflow.add_node("oculista", ophthalmologist_node)
    workflow.add_node("urologo", urologist_node)
    workflow.add_node("medico_generale", general_practitioner_node)
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

    workflow.add_edge("photography", "supervisor")
    workflow.add_edge("supervisor", "router")
    workflow.add_conditional_edges(
        "router",
        lambda x: x["next_step"],
        {
            "cardiologo": "cardiologo",
            "neurologo": "neurologo",
            "ortopedico": "ortopedico",
            "gastroenterologo": "gastroenterologo",
            "dermatologo": "dermatologo",
            "pneumologo": "pneumologo",
            "otorino": "otorino",
            "oculista": "oculista",
            "urologo": "urologo",
            "medico_generale": "medico_generale",
            "primario": "primario"
        }
    )

    workflow.add_edge("cardiologo", "router")
    workflow.add_edge("neurologo", "router")
    workflow.add_edge("ortopedico", "router")
    workflow.add_edge("gastroenterologo", "router")
    workflow.add_edge("dermatologo", "router")
    workflow.add_edge("pneumologo", "router")
    workflow.add_edge("otorino", "router")
    workflow.add_edge("oculista", "router")
    workflow.add_edge("urologo", "router")
    workflow.add_edge("medico_generale", "router")

    workflow.add_edge("primario", END)
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)

# Funzioni di routing
def router(state: MedicalState):
    specialist = state.get("needed_specialists")
    print("\n\n\n\n")
    print("Routing specialisti, stato attuale:", specialist)
    print("\n\n\n\n")
    for role, status in specialist.items():
        if not status:
            return {"next_step": role}
    return {"next_step": "primario"}

def triage_complete(state: MedicalState):
    return state["triage_complete"]