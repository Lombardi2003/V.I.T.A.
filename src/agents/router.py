# Router del tavolo degli specialisti: decide chi parla al prossimo turno e
# quando la discussione e' conclusa. Non usa il modello.
from src.state import MedicalState
from .roundtable import MAX_TOTAL_TURNS, MAX_RECRUITED_SPECIALISTS, MAX_SPEAKS_PER_SPECIALIST, MAX_FAILED_TURNS


# Funzioni di routing
def _turns_spoken(round_table, role: str) -> int:
    """Quanti TURNI ha avuto uno specialista (non quante righe ha scritto nella
    discussione): un turno puo' produrre due righe - un'azione sull'ipotesi
    seguita subito dal mini-consulto che lo specialista ha chiesto nello stesso
    turno (vedi specialist_node in specialist.py) - e va contato una volta sola,
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
    (MAX_FAILED_TURNS, vedi roundtable.py)."""
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
    roundtable.py). Simula una vera conversazione (chi viene interpellato
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
