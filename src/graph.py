# Librerie di base per la costruzione del grafo
from langgraph.graph import StateGraph, START,END
from langgraph.checkpoint.memory import MemorySaver

# Import dei moduli locali
from src.state import MedicalState
from src.nodes import reviewer_node, user_node, read_db_node, save_db_node, modify_db_node, supervisor_node, cardiologist_node, neurologist_node, primary_node, photography_node, orthopedic_node, gastroenterologist_node, dermatologist_node, pneumologist_node, ent_node, ophthalmologist_node, urologist_node, general_practitioner_node

# Funzione per la creazione del grafo di stato
def generate_graph():
    # Configurazione dello stato
    workflow = StateGraph(MedicalState)
    # Nodi
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("read_db", read_db_node)
    workflow.add_node("user", user_node)
    workflow.add_node("photography", photography_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("router", router)
    workflow.add_node("save_db", save_db_node)
    workflow.add_node("modify_db", modify_db_node)

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
    workflow.add_edge(START, "read_db") # Nodo iniziale (Entry Point)
    workflow.add_edge("read_db", "user")
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
        router_decision,
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

    workflow.add_conditional_edges(
        "primario",
        patient_exists,
        {
            True: "modify_db",
            False: "save_db",
        }
    )

    workflow.add_edge("save_db", END) # Nodo finale (Exit Point)
    workflow.add_edge("modify_db", END) # Nodo finale (Exit Point)
    memory = MemorySaver()
    return workflow.compile(
        checkpointer=memory,
        interrupt_before=["user"]
    )
    return workflow.compile()

# Funzioni di routing
def router(state: MedicalState):
    specialist = state.get("needed_specialists", {})
    consultation = state.get("inter_consultation")
    
    print("\n\n" + "="*40)
    print("🔀 ROUTER: Controllo la direzione...")
    print("Stato specialisti:", specialist)
    if consultation:
        print("⚠️ CONSULTO IN CORSO:", consultation)
    print("="*40 + "\n\n")

    # 1. PRECEDENZA ASSOLUTA: C'è un consulto in sospeso?
    if consultation:
        # Se c'è una domanda senza risposta, mandiamo dal destinatario ('a')
        if not consultation.get("risposta"):
            print(f"   -> 🚨 Deviazione: Mando la cartella al {consultation['a'].upper()} per rispondere alla domanda!")
            return {"next_step": consultation["a"]}
            
        # Se c'è la risposta, rimandiamo la cartella a chi l'aveva chiesta ('da')
        else:
            print(f"   -> 🚨 Risposta pronta: Rimando la cartella al {consultation['da'].upper()} per fargli finire il referto!")
            return {"next_step": consultation["da"]}

    # 2. LOGICA NORMALE: Nessun consulto tra medici, smistamento classico
    for role, status in specialist.items():
        if not status:
            print(f"   -> Smisto la visita normale al: {role}")
            return {"next_step": role}
            
    # 3. Se tutti hanno visitato, andiamo dal primario
    print("   -> Tutti i medici hanno concluso. Passo al PRIMARIO.")
    return {"next_step": "primario"}

def triage_complete(state: MedicalState):
    return state["triage_complete"]

def patient_exists(state: MedicalState):
    print("\n\n\n\n")
    print("Verifica esistenza paziente, stato attuale:", state.get("patient_exists"))
    print("\n\n\n\n")
    return state.get("patient_exists")

def router_decision(state: MedicalState):
    # Recuperiamo la decisione presa dal nodo router
    destinazione = state.get("next_step")
    print(f"🛤️ ROUTER: Smistamento verso -> {destinazione}")
    return destinazione