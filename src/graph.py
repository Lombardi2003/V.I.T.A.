# Librerie di base per la costruzione del grafo
from langgraph.graph import StateGraph, START,END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

# Import dei moduli locali
from src.state import MedicalState
from src.agents import reviewer_node, user_node, read_db_node, intake_node, save_db_node, modify_db_node, supervisor_node, cardiologist_node, neurologist_node, primary_node, photography_node, orthopedic_node, gastroenterologist_node, dermatologist_node, pneumologist_node, ent_node, ophthalmologist_node, urologist_node, general_practitioner_node

# Funzione per la creazione del grafo di stato
#
# STATO DI LAVORO: stiamo rivedendo il grafo un nodo alla volta. Per ora sono
# attivi "read_db", "intake", "reviewer", "photography", "supervisor", "router",
# i 10 specialisti e "chief_physician" (+ "user" come punto di interruzione).
# Quando il primario ha sintetizzato la diagnosi finale, il grafo termina su
# END - il salvataggio su DB (save_db/modify_db) NON e' ancora ricollegato
# (deciso cosi' per poter provare il flusso completo senza toccare il
# database) - e' un punto di osservazione temporaneo. Il resto e' commentato
# e verra' riattivato in seguito - NON e' stato rimosso, solo disattivato.
def generate_graph():
    workflow = StateGraph(MedicalState)

    # Nodi attivi
    workflow.add_node("read_db", read_db_node)
    workflow.add_node("user", user_node)
    workflow.add_node("intake", intake_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("photography", photography_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("router", router)
    workflow.add_node("cardiologist", cardiologist_node)
    workflow.add_node("neurologist", neurologist_node)
    workflow.add_node("orthopedist", orthopedic_node)
    workflow.add_node("gastroenterologist", gastroenterologist_node)
    workflow.add_node("dermatologist", dermatologist_node)
    workflow.add_node("pulmonologist", pneumologist_node)
    workflow.add_node("ent", ent_node)
    workflow.add_node("ophthalmologist", ophthalmologist_node)
    workflow.add_node("urologist", urologist_node)
    workflow.add_node("general_practitioner", general_practitioner_node)
    workflow.add_node("chief_physician", primary_node)

    # Nodi non ancora riattivati
    # workflow.add_node("save_db", save_db_node)
    # workflow.add_node("modify_db", modify_db_node)

    # Archi attivi
    workflow.add_edge(START, "read_db")
    workflow.add_edge("read_db", "user")
    workflow.add_edge("intake", "user")
    workflow.add_edge("reviewer", "user")
    workflow.add_edge("photography", "user")

    # user -> routing dinamico tramite next_step.
    # "read_db" permette il ciclo "CF non valido -> richiedilo di nuovo".
    # "intake" permette il ciclo "dati anagrafici incompleti -> richiedili di nuovo".
    # "reviewer" permette il ciclo "dati clinici incompleti -> richiedili di nuovo".
    # "photography" permette il ciclo "nessuna foto ancora -> richiedila di nuovo".
    workflow.add_conditional_edges(
        "user",
        lambda state: state.next_step if state.next_step else "reviewer",
        {
            "read_db":     "read_db",
            "intake":      "intake",
            "reviewer":    "reviewer",
            "photography": "photography",
            "supervisor":  "supervisor",
        }
        )

    workflow.add_edge("supervisor", "router")

    # Il router fa girare il tavolo tra gli specialisti scelti dal supervisore
    # (mai tutti e 10 - solo quelli in state.needed_specialists). Quando tutti
    # hanno depositato la diagnosi, passa al primario.
    workflow.add_conditional_edges(
        "router",
        lambda state: state.next_step,
        {
            "cardiologist": "cardiologist",
            "neurologist": "neurologist",
            "orthopedist": "orthopedist",
            "gastroenterologist": "gastroenterologist",
            "dermatologist": "dermatologist",
            "pulmonologist": "pulmonologist",
            "ent": "ent",
            "ophthalmologist": "ophthalmologist",
            "urologist": "urologist",
            "general_practitioner": "general_practitioner",
            "chief_physician": "chief_physician",
        }
    )

    workflow.add_edge("cardiologist", "router")
    workflow.add_edge("neurologist", "router")
    workflow.add_edge("orthopedist", "router")
    workflow.add_edge("gastroenterologist", "router")
    workflow.add_edge("dermatologist", "router")
    workflow.add_edge("pulmonologist", "router")
    workflow.add_edge("ent", "router")
    workflow.add_edge("ophthalmologist", "router")
    workflow.add_edge("urologist", "router")
    workflow.add_edge("general_practitioner", "router")

    # Il primario chiude il grafo su END - il salvataggio su DB (save_db/modify_db,
    # sotto in "archi non ancora riattivati") non e' ancora collegato di proposito,
    # per poter testare l'intero flusso di diagnosi senza toccare il database.
    workflow.add_edge("chief_physician", END)

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

    # SpecialistReport e RoundTableEntry vivono annidati dentro un dict/list
    # (medical_reports, round_table) - il serializzatore di default di
    # MemorySaver li tratta come tipi "non registrati" e stampa un warning ad
    # ogni checkpoint (osservato in test reale), avvisando che in una futura
    # versione di LangGraph la deserializzazione verrebbe bloccata del tutto.
    # Li registriamo esplicitamente per silenziare l'avviso senza attivare la
    # modalita' strict (che romperebbe la deserializzazione di questi tipi).
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("src.state", "SpecialistReport"),
            ("src.state", "RoundTableEntry"),
        ]
    )
    memory = MemorySaver(serde=serde)
    return workflow.compile(
        checkpointer=memory,
        interrupt_before=["user"]
    )
# Funzioni di routing
def router(state: MedicalState):
    """Fa girare il tavolo tra gli specialisti scelti dal supervisore, in un
    ordine fisso (quello con cui il supervisore li ha selezionati), saltando
    chi ha gia' depositato la diagnosi. Non guarda round_table per capire di
    chi e' il turno (registra solo chi interviene a voce, non chi deposita
    la diagnosi in silenzio) - usa invece current_turn_index, un puntatore
    esplicito gestito solo qui. Quando tutti hanno depositato, passa al
    primario."""
    order = list(state.needed_specialists.keys())
    n = len(order)

    if n == 0:
        # Difensivo: non dovrebbe succedere, il supervisore sceglie sempre
        # almeno uno specialista (fallback su medico generale).
        print("🔀 ROUTER: nessuno specialista selezionato, passo al primario")
        return {"next_step": "chief_physician"}

    pending = {role for role, done in state.needed_specialists.items() if not done}

    if not pending:
        print("🔀 ROUTER: tutti gli specialisti hanno depositato la diagnosi -> primario")
        return {"next_step": "chief_physician"}

    idx = state.current_turn_index % n
    for _ in range(n):
        if order[idx] in pending:
            break
        idx = (idx + 1) % n

    next_role = order[idx]
    round_count = state.round_count + (1 if idx == n - 1 else 0)
    next_idx = (idx + 1) % n

    print(f"🔀 ROUTER: turno di {next_role} (giro {round_count})")
    return {"next_step": next_role, "current_turn_index": next_idx, "round_count": round_count}

def photo_next(state: MedicalState):
    return state.next_step  # "photography" oppure "supervisor"

def triage_complete(state: MedicalState):
    return state.triage_complete

def patient_exists(state: MedicalState):
    print("\n\n\n\n")
    print("Verifica esistenza paziente, stato attuale:", state.get("patient_exists"))
    print("\n\n\n\n")
    return state.get("patient_exists")

# Funzione di routing da user
def user_next(state: MedicalState):
    return state.next_step  # "reviewer" oppure "photography"
