# Librerie di base per la costruzione del grafo
from langgraph.graph import StateGraph, START,END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

# Import dei moduli locali
from src.state import MedicalState
from src.agents import reviewer_node, user_node, read_db_node, intake_node, save_db_node, modify_db_node, supervisor_node, cardiologist_node, neurologist_node, primary_node, photography_node, orthopedic_node, gastroenterologist_node, dermatologist_node, pneumologist_node, ent_node, ophthalmologist_node, urologist_node, general_practitioner_node, MAX_TOTAL_TURNS, MAX_RECRUITED_SPECIALISTS, MAX_SPEAKS_PER_SPECIALIST, MAX_FAILED_TURNS

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
def _turns_spoken(round_table, role: str) -> int:
    """Quanti TURNI ha avuto uno specialista (non quante righe ha scritto nella
    discussione): un turno puo' produrre due righe - un'azione sull'ipotesi
    seguita subito dal mini-consulto che lo specialista ha chiesto nello stesso
    turno (vedi specialist_node in clinical.py) - e va contato una volta sola,
    altrimenti MAX_SPEAKS_PER_SPECIALIST scatterebbe dopo un solo turno."""
    turns = 0
    for i, entry in enumerate(round_table):
        # Il turno del giro di verifica finale non conta (vedi router).
        if entry.author != role or entry.verification:
            continue
        same_turn_consult = (
            entry.azione == "consulta" and i > 0
            and round_table[i - 1].author == role and round_table[i - 1].azione != "consulta"
        )
        if not same_turn_consult:
            turns += 1
    return turns


def _can_speak(state: MedicalState, role: str) -> bool:
    """Lo specialista puo' ancora avere un turno: non ha esaurito i propri
    interventi (MAX_SPEAKS_PER_SPECIALIST) ne' i turni falliti ammessi
    (MAX_FAILED_TURNS, vedi clinical.py)."""
    return (_turns_spoken(state.round_table, role) < MAX_SPEAKS_PER_SPECIALIST
            and state.failed_turns.get(role, 0) < MAX_FAILED_TURNS)


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

    Prima di scegliere chi parla, il router fa passare oltre chiunque abbia
    gia' raggiunto MAX_SPEAKS_PER_SPECIALIST interventi (o MAX_FAILED_TURNS
    turni falliti) senza confermare - lo segna in passed_without_confirming,
    NON tra chi ha confermato, e il primario lo sa. Non gli viene richiesto un altro turno
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

    Giro di verifica finale: quando tutti hanno confermato (e non resta nessuna
    reazione o mini-consulto in sospeso), prima del primario ogni specialista
    al tavolo ha UN ultimo turno per dire se, letti gli interventi dei
    colleghi, la sua valutazione e' cambiata (istruzione aggiunta al prompt da
    specialist_node, vedi verifying_role in state.py). Se qualcuno rivede
    l'ipotesi, gli altri devono riconfermarla e la discussione riprende come
    sempre; il giro si fa una volta sola, e il suo turno non conta nel tetto
    MAX_SPEAKS_PER_SPECIALIST.

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
    # confermare (vedi docstring sopra). Resta FUORI da confirmed_by: prima
    # veniva aggiunto li', e il primario leggeva "confermata da tutti" anche
    # quando qualcuno non si era mai espresso (osservato in prova: medico
    # generico con 2 turni falliti contato tra chi confermava). Si ricalcola a
    # ogni giro: dopo un "rivedi" chi non puo' piu' parlare passa di nuovo.
    passed = [role for role in needed if role not in confirmed and not _can_speak(state, role)]
    for role in passed:
        if role in state.passed_without_confirming:
            continue
        if state.failed_turns.get(role, 0) >= MAX_FAILED_TURNS:
            print(f"🔀 ROUTER: {role} ha avuto {MAX_FAILED_TURNS} turni falliti, passa senza confermare")
        else:
            print(f"🔀 ROUTER: {role} ha esaurito i propri interventi ({MAX_SPEAKS_PER_SPECIALIST}), passa senza confermare")

    update = {}
    if passed != state.passed_without_confirming:
        update["passed_without_confirming"] = passed

    pending = {role for role in needed if role not in confirmed and role not in passed}

    # Riapertura per reazione (vedi docstring): solo quando non resta piu'
    # nessuno da confermare, altrimenti la normale priorita' al punto 1 sotto
    # se ne occupa gia'.
    reopen_role = None
    if not pending and state.round_table:
        last_entry = state.round_table[-1]
        last_to = last_entry.to
        # Solo se il destinatario l'ha scelto lo specialista (to_explicit), non
        # quello messo in automatico da specialist_node - vedi state.py.
        if last_to and last_entry.to_explicit and last_to in needed and last_to != last_entry.author:
            if _can_speak(state, last_to):
                reopen_role = last_to
                print(f"🔀 ROUTER: {last_to} chiamato in causa dopo aver gia' confermato, una battuta di reazione")

    # Mini-consulto ancora senza risposta verso un collega non ancora al tavolo:
    # la discussione resta aperta anche se tutti hanno gia' confermato - caso
    # tipico, uno specialista da solo al tavolo che nello STESSO turno propone
    # l'ipotesi (e quindi la conferma) e chiede un consulto (vedi
    # specialist_node): senza questo si passava al primario e la domanda
    # restava senza risposta. Il reclutamento vero e proprio avviene al punto 1.
    open_consult = False
    if state.round_table:
        last_entry = state.round_table[-1]
        open_consult = (
            last_entry.azione == "consulta"
            and bool(last_entry.to)
            and last_entry.to not in needed
            and state.recruited_specialists_count < MAX_RECRUITED_SPECIALISTS
        )

    if not needed or (not pending and not reopen_role and not open_consult):
        # Solo per il registro nel terminale: chi e' passato oltre NON ha
        # confermato, e prima la riga diceva comunque "confermata da tutti".
        esito = f"confermata da tutti tranne chi e' passato oltre ({', '.join(passed)})" if passed else "confermata da tutti"
        # Giro di verifica finale (vedi docstring): parte la prima volta che
        # tutti hanno confermato, poi un turno a testa nell'ordine del tavolo.
        queue = list(state.verification_queue)
        if needed and not state.verification_started:
            queue = list(needed.keys())
            update["verification_started"] = True
            print(f"🔀 ROUTER: ipotesi {esito} -> giro di verifica finale")
        # Chi ha gia' esaurito i turni falliti ammessi non fa il giro di verifica.
        queue = [r for r in queue if state.failed_turns.get(r, 0) < MAX_FAILED_TURNS]
        if needed and queue:
            next_role = queue.pop(0)
            total_turns = state.total_turns + 1
            print(f"🔀 ROUTER: giro di verifica, turno di {next_role} (battuta {total_turns}/{MAX_TOTAL_TURNS})")
            return {
                **update,
                "next_step": next_role,
                "verifying_role": next_role,
                "verification_queue": queue,
                "total_turns": total_turns,
            }
        print(f"🔀 ROUTER: ipotesi di gruppo {esito} -> primario")
        return {**update, "next_step": "chief_physician", "verifying_role": ""}

    recruited_count = state.recruited_specialists_count
    next_role = reopen_role

    # 1. Priorita': chi e' stato interpellato direttamente nell'ultimo intervento
    # (non se abbiamo gia' deciso una riapertura per reazione sopra).
    if next_role is None and state.round_table:
        last_entry = state.round_table[-1]
        last_to = last_entry.to
        if last_to:
            if last_to in pending:
                next_role = last_to
            elif (last_to in needed and last_entry.to_explicit and last_to != last_entry.author
                  and _can_speak(state, last_to)):
                # Chiamato in causa ESPLICITAMENTE dopo aver gia' confermato (es.
                # la risposta a un suo mini-consulto, vedi specialist_node): parla
                # subito, prima degli altri ancora da confermare - altrimenti,
                # finito il giro, l'ultimo intervento non sarebbe piu' rivolto a
                # lui e la replica andrebbe persa (osservato con due specialisti:
                # il consulto riceveva risposta ma chi l'aveva chiesto non
                # replicava mai).
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
        "verifying_role": "",
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
