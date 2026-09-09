# Librerie di base per la costruzione del grafo
from langgraph.graph import StateGraph, START,END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

# Import dei moduli locali
from src.state import MedicalState
from src.agents import reviewer_node, user_node, read_db_node, intake_node, save_db_node, modify_db_node, supervisor_node, cardiologist_node, neurologist_node, primary_node, photography_node, orthopedic_node, gastroenterologist_node, dermatologist_node, pneumologist_node, ent_node, ophthalmologist_node, urologist_node, general_practitioner_node, MAX_TOTAL_TURNS, MAX_RECRUITED_SPECIALISTS, MAX_SPEAKS_PER_SPECIALIST

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
# Funzioni di routing
def router(state: MedicalState):
    """Decide chi parla al prossimo turno al tavolo degli specialisti, e
    quando la discussione e' conclusa.

    La discussione verte su un'UNICA ipotesi di gruppo condivisa
    (state.group_hypothesis, vedi state.py) invece di N referti indipendenti:
    "conclusa" non significa piu' "tutti hanno depositato un referto", ma
    "tutti gli specialisti seduti al tavolo hanno confermato la versione
    ATTUALE dell'ipotesi" (group_hypothesis.confirmed_by). Ogni volta che
    qualcuno la rivede, confirmed_by si azzera (vedi specialist_node) - gli
    altri devono riconfermare la nuova versione, non quella vecchia.

    Prima di scegliere chi parla, il router passa meccanicamente per
    "confermato" chiunque abbia gia' raggiunto MAX_SPEAKS_PER_SPECIALIST
    interventi senza mai confermare - non gli viene richiesto un altro turno
    (nessuna chiamata LLM aggiuntiva), e non gli si mette in bocca un
    "conferma" finto: e' solo instradamento meccanico (chi ha gia' parlato
    abbastanza volte), non un giudizio sul contenuto - evita che due
    specialisti si scambino ipotesi quasi identiche all'infinito.

    Poi, chi parla: se l'ultimo intervento in round_table aveva un
    destinatario specifico ("to"), parla lui al turno successivo - anche se
    non era ancora al tavolo (lo "recluta" per un mini-consulto, tetto
    MAX_RECRUITED_SPECIALISTS oltre alla selezione del supervisore: vedi
    clinical.py). Simula una vera conversazione (chi viene interpellato
    risponde subito) invece di un giro rigido A-B-A-B.

    Ripiego: se l'ultimo intervento era rivolto "a tutti" (o non c'e' ancora
    nessun intervento, o il destinatario ha gia' confermato/il tetto di
    reclutamento e' pieno), si torna al giro tra chi resta da confermare,
    nell'ordine in cui sono entrati al tavolo (current_turn_index).

    Riapertura per reazione: se TUTTI hanno gia' confermato ma l'ultimissimo
    intervento chiama in causa per nome un collega gia' seduto al tavolo
    (anche se gia' tra i confermati) - una conferma con un'aggiunta nuova, o
    una domanda mirata - gli si da' UNA battuta in piu' per reagire prima di
    chiudere, invece di passare dritto al primario. Senza questo, un "confermo,
    e aggiungerei anche l'EGA" non riceveva mai una replica: il tavolo si
    chiudeva nell'istante stesso in cui l'ultimo confermava, anche se aveva
    appena detto qualcosa di nuovo (osservato in test reale: la discussione
    sembrava "uno propone, uno conferma" invece di un vero botta-e-risposta).
    Il tetto MAX_SPEAKS_PER_SPECIALIST (gia' usato sopra) basta a evitare un
    ping-pong infinito: chi viene riaperto ha comunque un numero massimo di
    interventi.

    total_turns e' il freno di emergenza assoluto: oltre MAX_TOTAL_TURNS si va
    comunque al primario con l'ipotesi di gruppo cosi' com'e', confermata o meno.
    """
    if state.total_turns >= MAX_TOTAL_TURNS:
        print(f"🔀 ROUTER: raggiunto il tetto di {MAX_TOTAL_TURNS} battute -> primario")
        return {"next_step": "chief_physician"}

    needed = dict(state.needed_specialists)
    gh = state.group_hypothesis
    confirmed = set(gh.confirmed_by) if gh else set()

    # Passaggio meccanico per chi ha esaurito i propri interventi senza
    # confermare (vedi docstring sopra).
    changed = False
    for role in needed:
        if role not in confirmed:
            speak_count = sum(1 for e in state.round_table if e.author == role)
            if speak_count >= MAX_SPEAKS_PER_SPECIALIST:
                confirmed.add(role)
                changed = True
                print(f"🔀 ROUTER: {role} ha esaurito i propri interventi ({MAX_SPEAKS_PER_SPECIALIST}), passa senza confermare")

    update = {}
    if changed and gh:
        update["group_hypothesis"] = gh.model_copy(update={"confirmed_by": sorted(confirmed)}).model_dump()

    pending = {role for role in needed if role not in confirmed}

    # Riapertura per reazione (vedi docstring): solo quando non resta piu'
    # nessuno da confermare, altrimenti la normale priorita' al punto 1 sotto
    # se ne occupa gia'.
    reopen_role = None
    if not pending and state.round_table:
        last_entry = state.round_table[-1]
        last_to = last_entry.to
        if last_to and last_to in needed and last_to != last_entry.author:
            speak_count = sum(1 for e in state.round_table if e.author == last_to)
            if speak_count < MAX_SPEAKS_PER_SPECIALIST:
                reopen_role = last_to
                print(f"🔀 ROUTER: {last_to} chiamato in causa dopo aver gia' confermato, una battuta di reazione")

    if not needed or (not pending and not reopen_role):
        print("🔀 ROUTER: ipotesi di gruppo confermata da tutti -> primario")
        return {**update, "next_step": "chief_physician"}

    recruited_count = state.recruited_specialists_count
    next_role = reopen_role

    # 1. Priorita': chi e' stato interpellato direttamente nell'ultimo intervento
    # (non se abbiamo gia' deciso una riapertura per reazione sopra).
    if next_role is None and state.round_table:
        last_to = state.round_table[-1].to
        if last_to:
            if last_to in pending:
                next_role = last_to
            elif last_to not in needed and recruited_count < MAX_RECRUITED_SPECIALISTS:
                needed[last_to] = True
                recruited_count += 1
                next_role = last_to
                print(f"🔀 ROUTER: {last_to} coinvolto nella discussione su richiesta di un collega")
            # altrimenti (gia' confermato, o tetto di reclutamento pieno):
            # si ricade nel ripiego al punto 2, "last_to" non e' piu' valido.

    # 2. Ripiego: giro tra chi resta da confermare, nell'ordine di ingresso al tavolo.
    order = list(needed.keys())
    n = len(order)
    if not next_role:
        idx = state.current_turn_index % n
        for _ in range(n):
            if order[idx] in pending:
                next_role = order[idx]
                break
            idx = (idx + 1) % n

    next_idx = (order.index(next_role) + 1) % n
    total_turns = state.total_turns + 1

    print(f"🔀 ROUTER: turno di {next_role} (battuta {total_turns}/{MAX_TOTAL_TURNS})")
    return {
        **update,
        "next_step": next_role,
        "current_turn_index": next_idx,
        "total_turns": total_turns,
        "needed_specialists": needed,
        "recruited_specialists_count": recruited_count,
    }

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
