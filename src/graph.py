# Librerie di base per la costruzione del grafo
from langgraph.graph import StateGraph, START,END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from langchain_core.messages import HumanMessage

# Import dei moduli locali
from src.state import MedicalState
from src.agents import reviewer_node, read_db_node, intake_node, save_db_node, supervisor_node, cardiologist_node, neurologist_node, primary_node, photography_node, orthopedic_node, gastroenterologist_node, dermatologist_node, pneumologist_node, ent_node, ophthalmologist_node, urologist_node, general_practitioner_node, router, MAX_TOTAL_TURNS

# Nodo per la gestione del messaggio dell'utente
async def user_node(state: MedicalState):
    """Nodo di passaggio: il messaggio e' gia' nello stato (aggiunto da app.py
    prima che il grafo riprendesse) - qui non va ri-aggiunto, altrimenti si
    duplica nello storico (general_history/triage_history si concatenano con
    operator.add). NON tocchiamo next_step: resta quello impostato dal nodo precedente.
    """
    if state.triage_history and isinstance(state.triage_history[-1], HumanMessage):
        print("💬 USER: " + state.triage_history[-1].content.strip().lower())

    return {}


# Funzione per la creazione del grafo di stato
#
# Nodi: "read_db", "intake", "reviewer", "photography", "supervisor", "router",
# i 10 specialisti, "chief_physician" e "save_db" (+ "user" come punto di
# interruzione). Dopo il report del primario, save_db salva la scheda nel
# database e il grafo termina.
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
    workflow.add_node("save_db", save_db_node)

    # Archi attivi
    workflow.add_edge(START, "read_db")
    # Codice fiscale valido (paziente nuovo o gia' registrato): subito intake,
    # senza pausa, che mostra la scheda. Non valido: pausa, poi read_db lo
    # richiede (ciclo tramite "user", sotto).
    workflow.add_conditional_edges(
        "read_db",
        lambda state: "intake" if state.next_step == "intake" else "user",
        {"intake": "intake", "user": "user"},
    )
    # Anagrafica confermata: subito il revisore, senza pausa, che chiede i
    # sintomi. Altrimenti pausa e intake riprende al prossimo messaggio.
    workflow.add_conditional_edges(
        "intake",
        lambda state: "reviewer" if state.next_step == "reviewer" else "user",
        {"reviewer": "reviewer", "user": "user"},
    )
    # Sintomi confermati: subito photography, senza pausa, che chiede la foto.
    workflow.add_conditional_edges(
        "reviewer",
        lambda state: "photography" if state.next_step == "photography" else "user",
        {"photography": "photography", "user": "user"},
    )
    # Foto analizzata o rifiutata: subito il supervisore, senza pausa (prima
    # l'arco era fisso verso "user" e dopo "procedo senza foto" l'app si
    # fermava di nuovo ad aspettare un messaggio - verificato con una prova).
    workflow.add_conditional_edges(
        "photography",
        lambda state: "supervisor" if state.next_step == "supervisor" else "user",
        {"supervisor": "supervisor", "user": "user"},
    )

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

    # Dopo il report del primario si salva la scheda (un nodo solo: crea il
    # paziente o lo aggiorna, vedi save_db_node in persistence.py), poi fine.
    workflow.add_edge("chief_physician", "save_db")
    workflow.add_edge("save_db", END)

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

    # GroupHypothesis e RoundTableEntry vivono annidati dentro un campo/lista
    # (group_hypothesis, round_table) - il serializzatore di default di
    # MemorySaver li tratta come tipi "non registrati" e stampa un warning ad
    # ogni checkpoint (osservato in test reale), avvisando che in una futura
    # versione di LangGraph la deserializzazione verrebbe bloccata del tutto.
    # Li registriamo esplicitamente per silenziare l'avviso senza attivare la
    # modalita' strict (che romperebbe la deserializzazione di questi tipi).
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("src.state", "GroupHypothesis"),
            ("src.state", "RoundTableEntry"),
        ]
    )
    memory = MemorySaver(serde=serde)
    return workflow.compile(
        checkpointer=memory,
        interrupt_before=["user"]
    )


# Limite di passi di una singola ripresa del grafo. Il default di LangGraph (25)
# non basta: una discussione che arriva a MAX_TOTAL_TURNS fa due passi a battuta
# (router + specialista), poi router, primario e save_db - con 12 battute sono
# 27 passi, e il grafo andava in errore proprio nei casi piu' discussi (trovato
# dai test dopo aver aggiunto save_db). Calcolato dal tetto delle battute, con
# margine per i nodi prima e dopo il tavolo.
RECURSION_LIMIT = 2 * MAX_TOTAL_TURNS + 20


def thread_config(thread_id: str) -> dict:
    """Configurazione con cui usare il grafo per una conversazione: il suo
    identificativo e il limite di passi. Va usata ovunque si chiama il grafo
    (app.py, test, script): impostare il limite sul grafo compilato non basta,
    astream_events riparte dal default."""
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}


def photo_next(state: MedicalState):
    return state.next_step  # "photography" oppure "supervisor"

def triage_complete(state: MedicalState):
    return state.triage_complete

# Funzione di routing da user
def user_next(state: MedicalState):
    return state.next_step  # "reviewer" oppure "photography"
