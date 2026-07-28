# Librerie di base per la costruzione del grafo
from langgraph.graph import StateGraph, START,END
from langgraph.checkpoint.memory import MemorySaver

# Import dei moduli locali
from src.state import MedicalState
from src.agents import reviewer_node, user_node, read_db_node, intake_node, save_db_node, modify_db_node, supervisor_node, cardiologist_node, neurologist_node, primary_node, photography_node, orthopedic_node, gastroenterologist_node, dermatologist_node, pneumologist_node, ent_node, ophthalmologist_node, urologist_node, general_practitioner_node

# Funzione per la creazione del grafo di stato
#
# STATO DI LAVORO: stiamo rivedendo il grafo un nodo alla volta. Per ora sono
# attivi "read_db", "intake" e "reviewer" (+ "user" come punto di interruzione).
# Il resto e' commentato e verra' riattivato mano a mano che sistemiamo
# ciascun nodo - NON e' stato rimosso, solo disattivato temporaneamente.
def generate_graph():
    workflow = StateGraph(MedicalState)

    # Nodi attivi
    workflow.add_node("read_db", read_db_node)
    workflow.add_node("user", user_node)
    workflow.add_node("intake", intake_node)
    workflow.add_node("reviewer", reviewer_node)

    # Nodi non ancora riattivati
    # workflow.add_node("photography", photography_node)
    # workflow.add_node("supervisor", supervisor_node)
    # workflow.add_node("router", router)
    # workflow.add_node("save_db", save_db_node)
    # workflow.add_node("modify_db", modify_db_node)

    # Specialisti (non ancora riattivati)
    # workflow.add_node("cardiologist", cardiologist_node)
    # workflow.add_node("neurologist", neurologist_node)
    # workflow.add_node("orthopedist", orthopedic_node)
    # workflow.add_node("gastroenterologist", gastroenterologist_node)
    # workflow.add_node("dermatologist", dermatologist_node)
    # workflow.add_node("pulmonologist", pneumologist_node)
    # workflow.add_node("ent", ent_node)
    # workflow.add_node("ophthalmologist", ophthalmologist_node)
    # workflow.add_node("urologist", urologist_node)
    # workflow.add_node("general_practitioner", general_practitioner_node)
    # workflow.add_node("chief_physician", primary_node)

    # Archi attivi
    workflow.add_edge(START, "read_db")
    workflow.add_edge("read_db", "user")
    workflow.add_edge("intake", "user")
    workflow.add_edge("reviewer", "user")

    # user -> routing dinamico tramite next_step.
    # "read_db" permette il ciclo "CF non valido -> richiedilo di nuovo".
    # "intake" permette il ciclo "dati anagrafici incompleti -> richiedili di nuovo".
    # "reviewer" permette il ciclo "dati clinici incompleti -> richiedili di nuovo".
    # "photography" e' ancora un placeholder verso END finche' non riattiviamo quel nodo.
    workflow.add_conditional_edges(
        "user",
        lambda state: state.next_step if state.next_step else "reviewer",
        {
            "read_db":     "read_db",
            "intake":      "intake",
            "reviewer":    "reviewer",
            "photography": END,
        }
        )

    # Archi non ancora riattivati
    # workflow.add_conditional_edges(
    #     "reviewer",
    #     triage_complete,
    #     {
    #         True:  "photography",
    #         False: "user",
    #     }
    # )
    #
    # workflow.add_conditional_edges(
    #     "photography",
    #     lambda state: state.next_step,
    #     {
    #         "photography": "user",      # ← chiedi foto → vai a user (interrupt)
    #         "supervisor":  "supervisor",
    #     }
    # )
    # workflow.add_edge("supervisor", "router")
    # workflow.add_conditional_edges(
    #     "router",
    #     router_decision,
    #     {
    #         "cardiologist": "cardiologist",
    #         "neurologist": "neurologist",
    #         "orthopedist": "orthopedist",
    #         "gastroenterologist": "gastroenterologist",
    #         "dermatologist": "dermatologist",
    #         "pulmonologist": "pulmonologist",
    #         "ent": "ent",
    #         "ophthalmologist": "ophthalmologist",
    #         "urologist": "urologist",
    #         "general_practitioner": "general_practitioner",
    #         "chief_physician": "chief_physician"
    #     }
    # )
    #
    # workflow.add_edge("cardiologist", "router")
    # workflow.add_edge("neurologist", "router")
    # workflow.add_edge("orthopedist", "router")
    # workflow.add_edge("gastroenterologist", "router")
    # workflow.add_edge("dermatologist", "router")
    # workflow.add_edge("pulmonologist", "router")
    # workflow.add_edge("ent", "router")
    # workflow.add_edge("ophthalmologist", "router")
    # workflow.add_edge("urologist", "router")
    # workflow.add_edge("general_practitioner", "router")
    #
    # workflow.add_conditional_edges(
    #     "chief_physician",
    #     patient_exists,
    #     {
    #         True: "modify_db",
    #         False: "save_db",
    #     }
    # )
    #
    # workflow.add_edge("save_db", END) # Nodo finale (Exit Point)
    # workflow.add_edge("modify_db", END) # Nodo finale (Exit Point)

    memory = MemorySaver()
    return workflow.compile(
        checkpointer=memory,
        interrupt_before=["user"]
    )
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
    return {"next_step": "chief_physician"}

def photo_next(state: MedicalState):
    return state.next_step  # "photography" oppure "supervisor"

def triage_complete(state: MedicalState):
    return state.triage_complete

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

# Funzione di routing da user
def user_next(state: MedicalState):
    return state.next_step  # "reviewer" oppure "photography"
