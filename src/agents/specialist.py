# Nodo dello specialista: un turno al tavolo (propone, conferma, rivede
# l'ipotesi di gruppo o chiede un mini-consulto) e i 10 nodi specialistici.
import asyncio
import json

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState, RoundTableEntry, GroupHypothesis
from .prompts import SPECIALIST_PROMPT
from .common import extract_json, stream_response, as_list, as_text, is_no, is_yes
from .authors import Authors
from .roundtable import (
    SPECIALIST_DISPLAY_NAMES, _format_round_table, _parse_urgency, _pediatric_note, _role_from_name,
)
from src.rag.retriever import build_queries, retrieve


def _failed_turn(state: MedicalState, role: str) -> dict:
    """Aggiornamento dello stato per un turno fallito di questo specialista:
    nessun effetto sulla discussione, solo il conteggio dei fallimenti."""
    failed = dict(state.failed_turns)
    failed[role] = failed.get(role, 0) + 1
    return {"failed_turns": failed}


def _format_group_hypothesis(gh: GroupHypothesis | None) -> str:
    """Rende leggibile l'ipotesi di gruppo ATTUALE per il prompt dello
    specialista di turno - il contenuto per intero (non solo "esiste"),
    altrimenti nessuno potrebbe davvero confermarla/rivederla nel merito.
    Include anche chi l'ha gia' confermata, cosi' chi legge sa se sta
    reagendo a qualcosa di nuovo o gia' ampiamente condiviso."""
    if gh is None:
        return (
            'Nessuna ipotesi ancora proposta - sei il primo a parlare. Usa "azione": "proponi" '
            'per aprire tu la discussione, oppure "consulta" se preferisci un parere di un '
            "collega assente PRIMA di sbilanciarti con una tua ipotesi."
        )
    confermato_da = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in gh.confirmed_by) or "nessuno ancora"
    return (
        f"Diagnosi: {gh.diagnosis}\n"
        f"Urgenza: {gh.urgency_level}\n"
        f"Esami consigliati: {', '.join(gh.recommended_exams) or 'nessuno indicato'}\n"
        f"Dettagli: {gh.details}\n"
        f"Alternativa considerata e scartata dal tavolo: {gh.discarded_alternative or '(nessuna)'}"
        f"{f' ({gh.discard_reason})' if gh.discard_reason else ''}\n"
        f"Proposta/rivista per ultimo da: {SPECIALIST_DISPLAY_NAMES.get(gh.last_updated_by, gh.last_updated_by)}\n"
        f"Confermata finora da: {confermato_da}"
    )


_SPECIALIST_TEXT_FIELDS = (
    "azione", "diagnosi", "dettagli", "motivazione", "message", "valutazione_indipendente",
    "ipotesi_alternativa_scartata", "motivo_scarto", "domanda_per_il_collega", "fonti_consultate", "urgenza",
)


def _one_name(value) -> str:
    """Un solo nome (destinatario/collega), anche se scritto come lista
    (["cardiologist"]) o come oggetto ({"name": "pulmonologist"})."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("name") or value.get("role") or value.get("specialist") or next(iter(value.values()), "")
    return as_text(value)


def _normalize_specialist_answer(data: dict) -> dict:
    """Risposta dello specialista riportata alla forma che il resto del nodo
    si aspetta. Prima, con risposte finte in forme diverse, il nodo non andava
    in errore ma in 6 casi su 11 capiva male in silenzio: "coincide_con_gruppo":
    false (vero/falso invece di "no") faceva saltare la protezione contro
    l'ancoraggio, "consulto_utile": true o "sì" (accentato) il consulto, un
    destinatario scritto come oggetto finiva "a tutti", testi scritti come
    liste arrivavano in chat come "['a', 'b']"."""
    data = dict(data)
    for field in _SPECIALIST_TEXT_FIELDS:
        if field in data:
            data[field] = as_text(data[field])
    for field in ("consulto_utile", "coincide_con_gruppo"):
        if field in data:
            value = data[field]
            data[field] = "si" if is_yes(value) else "no" if is_no(value) else as_text(value).lower()
    for field in ("to", "collega_da_consultare"):
        if field in data:
            data[field] = _one_name(data[field]) or None
    if "esami_consigliati" in data:
        exams = data["esami_consigliati"]
        if isinstance(exams, dict):
            exams = list(exams.values())
        data["esami_consigliati"] = [t for t in (as_text(e) for e in as_list(exams)) if t]
    return data


async def specialist_node(state: MedicalState, role: str):
    """Un turno di uno specialista al tavolo: legge cartella clinica e
    l'ipotesi di gruppo condivisa (con l'intera discussione come contesto),
    poi la propone/conferma/rivede, oppure chiama in causa un collega assente
    con un mini-consulto. Il router (router.py) decide chi parla dopo e quando
    la discussione e' conclusa - questo nodo non lo decide da solo, e non
    viene MAI invocato oltre i tetti di MAX_TOTAL_TURNS/MAX_SPEAKS_PER_SPECIALIST
    (il router passa oltre meccanicamente prima di richiamarlo, vedi router.py)."""
    display_name = SPECIALIST_DISPLAY_NAMES.get(role, role)
    author = getattr(Authors, role.upper(), Authors.SYSTEM)

    card_str = state.patient_card.model_dump_json()
    table_text = _format_round_table(state.round_table)
    hypothesis_text = _format_group_hypothesis(state.group_hypothesis)

    # Se l'ultimo intervento era rivolto PROPRIO a questo specialista (to ==
    # role) - un mini-consulto (azione "consulta") o una riapertura per
    # reazione decisa dal router quando tutti avevano gia' confermato (vedi
    # router in router.py) - questo turno DEVE rispondere a quel punto preciso
    # prima di qualsiasi altra cosa. Senza questo, uno specialista appena
    # chiamato in causa apre semplicemente una sua ipotesi/conferma generica,
    # ignorando cio' che lo ha fatto richiamare (osservato in test reale sul
    # mini-consulto: nessuna regola generica bastava a farglielo notare).
    # Iniettiamo un'istruzione dedicata solo quando serve, stesso pattern gia'
    # usato per force_final nel disegno precedente (Python rileva il contesto
    # meccanicamente, il prompt si adatta).
    consulto_pendente = ""
    if state.round_table:
        last = state.round_table[-1]
        if last.to == role:
            chi_chiede = SPECIALIST_DISPLAY_NAMES.get(last.author, last.author)
            e_domanda = last.azione == "consulta"
            consulto_pendente = (
                f'ATTENZIONE: {chi_chiede} ti ha appena rivolto '
                f'{"un mini-consulto con una domanda SPECIFICA" if e_domanda else "una considerazione specifica, indirizzata a te"}: '
                f'"{last.content}". Il tuo turno DEVE rispondere '
                f'ESPLICITAMENTE e per primo a questo punto (nel campo "dettagli"/"message"), '
                f"prima di qualsiasi altra cosa."
            )

    # Turno del giro di verifica finale (deciso dal router, vedi router.py):
    # tutti hanno gia' confermato, ora ciascuno deve dire se, letti i
    # colleghi, la propria valutazione e' cambiata - in modo esplicito, non con
    # una conferma di rito.
    is_verification = state.verifying_role == role
    istruzione_verifica = ""
    if is_verification:
        istruzione_verifica = (
            "GIRO DI VERIFICA FINALE: tutti gli specialisti al tavolo hanno confermato l'ipotesi di "
            "gruppo attuale. Prima della chiusura, rileggi con attenzione TUTTA la discussione qui "
            "sopra, in particolare cio' che hanno detto i colleghi dopo il tuo ultimo intervento. "
            "Alla luce dei loro interventi, la tua valutazione e' cambiata? Se si', usa \"rivedi\" "
            "e spiega in \"motivazione\" quale intervento di quale collega ti ha fatto cambiare idea. "
            "Se no, usa \"conferma\" e in \"motivazione\" indica quale punto sollevato dai colleghi "
            "hai considerato e perche' non cambia la tua valutazione - non limitarti a ripetere "
            "che sei d'accordo."
        )

    # Medico generico aggiunto dal supervisore per un secondo parere (vedi
    # supervisor_node): gli si dice perche' e' al tavolo, invece di farlo
    # comportare come uno specialista qualunque.
    istruzione_secondo_parere = ""
    if role == state.second_opinion_role:
        collega = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in state.needed_specialists if r != role)
        istruzione_secondo_parere = (
            f"SECONDO PARERE: sei al tavolo per un secondo parere, perche' per questo caso era stato "
            f"scelto un solo specialista ({collega}). Rileggi il caso nel suo insieme (eta', patologie "
            "pregresse, tutti i sintomi) e controlla che l'ipotesi del collega sia sostenuta dai DATI "
            "PAZIENTE: se lo e', confermala spiegando perche'; se no (un dato non riferito dato per "
            "acquisito, un codice di urgenza non giustificato, una spiegazione piu' semplice trascurata), "
            "usa \"rivedi\"."
        )

    # Recupero RAG (src/rag/): SEMPRE eseguito, un turno = una ricerca - non e'
    # una scelta del modello (vedi discussione: lasciare al modello "se
    # cercare" ha lo stesso rischio gia' visto oggi con consulto_utile e
    # coincide_con_gruppo, entrambi ignorati quando lasciati liberi, funzionanti
    # solo forzati meccanicamente). Il modello resta libero pero' di IGNORARE il
    # risultato se non pertinente (vedi SPECIALIST_PROMPT, campo
    # "fonti_consultate") - il recupero e' obbligatorio, l'uso no.
    #
    # Query per-turno (non solo i sintomi fissi, Opzione A): include anche il
    # contenuto dell'ultimo intervento se rivolto a questo specialista, cosi'
    # un mini-consulto su un dettaglio specifico (es. "criteri di sospensione
    # anticoagulante") recupera contesto mirato a QUEL dettaglio, non solo al
    # quadro clinico generale del paziente.
    #
    # Il ruolo passato a retrieve() limita la ricerca alle linee guida della
    # specialita' di chi parla + i documenti generali di triage (vedi
    # retriever.py), e ogni pezzo arriva nel prompt con documento e pagina -
    # cosi' "fonti_consultate" puo' citare una fonte vera e verificabile,
    # invece di una descrizione inventata dal modello.
    #
    # Una ricerca per ciascun sintomo, non una sola con tutti i sintomi
    # insieme (vedi build_queries in retriever.py): i sintomi fuori
    # dall'ambito di questo specialista non devono "sporcare" la ricerca.
    queries = build_queries(
        display_name,
        [s.description for s in state.patient_card.symptom.symptoms],
        extra=state.round_table[-1].content if consulto_pendente and state.round_table else "",
    )
    # asyncio.to_thread: la ricerca (embedding della query + indice) e'
    # sincrona - stessa ragione delle chiamate LLM piu' sotto, non deve
    # bloccare il ciclo di eventi di Chainlit.
    linee_guida_chunks = await asyncio.to_thread(retrieve, queries, role)
    linee_guida_text = (
        "\n\n".join(f"- [{chunk.citation}] {chunk.text}" for chunk in linee_guida_chunks)
        if linee_guida_chunks
        else "Nessuna linea guida pertinente trovata nel database."
    )
    # Log di cosa e' stato recuperato per QUESTO turno - permette di verificare
    # durante i test se il contenuto che lo specialista dichiara di aver usato
    # (campo "fonti_consultate" nella risposta) corrisponde davvero a quello
    # che il RAG ha trovato, invece di fidarsi solo della dichiarazione del modello.
    print(f"📚 RAG [{role}]: {len(linee_guida_chunks)} pezzi recuperati")
    for i, chunk in enumerate(linee_guida_chunks, 1):
        print(f"   {i}. [{chunk.citation}] {chunk.text[:150]}...")

    prompt = SPECIALIST_PROMPT.format(
        role_display=display_name,
        role=role,
        card=card_str,
        round_table=table_text,
        hypothesis=hypothesis_text,
        consulto_pendente="\n\n".join(t for t in (_pediatric_note(state.patient_card), consulto_pendente,
                                                    istruzione_secondo_parere, istruzione_verifica) if t),
        linee_guida=linee_guida_text,
    )

    try:
        async with cl.Step(name=display_name, type="tool", default_open=False, show_input="text") as step:
            step.input = table_text
            # asyncio.to_thread: vedi commento su supervisor_node poco sopra -
            # stessa identica ragione. Qui e' il punto piu' critico del grafo
            # per questo problema (molte chiamate consecutive, e il modello
            # potrebbe essere uno locale molto piu' lento di Groq).
            content = await asyncio.to_thread(stream_response, prompt)
            step.output = content
    except Exception as e:
        # Un errore diretto dell'API che resta anche dopo i nuovi tentativi di
        # stream_response (vedi call_with_retry in common.py - es. rate limit
        # superato a meta' dello streaming, osservato in test reale con
        # openai.APIError) non deve mandare in crash l'intero grafo - stesso trattamento riservato al
        # JSON malformato/troncato piu' sotto: nessun aggiornamento della
        # discussione, solo il conteggio del turno fallito (il router lo fa
        # passare oltre dopo MAX_FAILED_TURNS fallimenti).
        print(f"⚠️ {role}: errore API ({e}), nessun aggiornamento - turno fallito")
        return _failed_turn(state, role)

    try:
        # extract_json gestisce anche i modelli che antepongono al JSON un
        # blocco <think>...</think> o testo libero (vedi src/llm/calls.py).
        data = _normalize_specialist_answer(extract_json(content))
        azione = str(data.get("azione", "")).lower().strip()
    except json.JSONDecodeError:
        # Un JSON malformato/troncato (osservato in test reale: la risposta
        # si tronca a meta' parola, es. per un limite di token) NON deve mai
        # ricadere sul ramo "conferma" piu' sotto - altrimenti un guasto
        # tecnico si travestirebbe da giudizio clinico genuino (un'obiezione
        # vera, magari gia' scritta ma troncata prima del completamento del
        # JSON, verrebbe convertita in un consenso silenzioso alla diagnosi
        # sbagliata - trovato mentre si testava apposta la correzione di
        # un'ipotesi iniettata scorretta). Usciamo qui senza aggiornare la
        # discussione, contando solo il turno fallito: il router puo'
        # ridargli la parola, ma dopo MAX_FAILED_TURNS fallimenti lo fa
        # passare oltre (stesso trattamento degli altri turni falliti).
        print(f"⚠️ {role}: errore lettura JSON (risposta malformata/troncata), nessun aggiornamento - turno fallito")
        return _failed_turn(state, role)

    # Campo obbligatorio forzato "consulto_utile" (vedi SPECIALIST_PROMPT): se
    # lo specialista dichiara che il parere di un collega ASSENTE cambierebbe
    # davvero la sua valutazione, il turno diventa un mini-consulto verso quel
    # collega A PRESCINDERE da quale "azione" avesse scelto separatamente -
    # stessa tecnica del campo obbligatorio gia' usata con successo altrove in
    # questo progetto (es. ipotesi_alternativa_scartata): un valore da
    # dichiarare esplicitamente ad ogni turno cambia il comportamento molto
    # piu' della sola prosa che "permette" un'opzione tra tante (osservato in
    # test reale: la sola prosa non bastava mai a far scegliere "consulta").
    # Nome scritto dallo specialista quando chiede un collega che non esiste
    # (es. "ematologo"): il consulto va al medico generico, e in chat si dice
    # per chi era la richiesta (vedi _send_consult).
    requested_for = ""
    consulto_utile = str(data.get("consulto_utile", "")).strip().lower() == "si"
    raw_collega = str(data.get("collega_da_consultare") or "").strip().lower()
    collega = _role_from_name(raw_collega)
    if collega == role:
        collega = None
    if consulto_utile and raw_collega and not collega:
        # Lo specialista ha chiesto un consulto specifico ma verso un ruolo
        # che non esiste tra i 10 disponibili (es. "hematologist",
        # "radiologist" - osservato in test reale: ambiti clinici reali ma
        # non presenti nel roster di questo sistema). Invece di scartare
        # silenziosamente una richiesta di consulto genuina (il giudizio
        # clinico che il parere di qualcuno serve resta valido, solo il
        # nome del ruolo non combacia), reindirizziamo al medico generico -
        # gia' pensato in questo sistema come ruolo "jolly" per casi fuori
        # standard (vedi SUPERVISOR_PROMPT, "SINTOMI MISTI/NON CHIARI").
        print(f"🔀 {role}: consulto_utile=si verso '{raw_collega}' (non nel roster) -> reindirizzato a general_practitioner")
        collega = "general_practitioner" if role != "general_practitioner" else None
        if collega:
            requested_for = str(data.get("collega_da_consultare") or "").strip()
    # Il mini-consulto forzato si AGGIUNGE all'azione scelta dallo specialista,
    # non la sostituisce: prima si registra la sua proposta/revisione/conferma
    # dell'ipotesi di gruppo, poi parte il consulto (vedi fondo del nodo).
    # Prima il turno diventava SOLO un consulto e il resto della risposta veniva
    # buttato: osservato in test reale, un gastroenterologo propone urgenza
    # ARANCIONE + consulto, la proposta si perde, il dermatologo consultato apre
    # lui l'ipotesi con VERDE e il primario chiude su VERDE - mentre in altre
    # esecuzioni dello stesso caso, senza consulto forzato al primo turno, il
    # risultato era ARANCIONE.
    forced_consult_to = None
    if consulto_utile and collega and azione != "consulta":
        print(f"🔀 {role}: consulto_utile=si -> mini-consulto verso {collega}, in aggiunta all'azione '{azione}'")
        forced_consult_to = collega

    # "consulta" verso un ruolo che non esiste tra i 10 disponibili (es.
    # "allergologo"): stesso ripiego di consulto_utile qui sopra, il consulto va
    # al medico generico. Se non si puo' (chi chiede E' il medico generico, o
    # non ha indicato nessun destinatario) il turno non fallisce: il resto della
    # risposta vale come intervento normale sull'ipotesi di gruppo. Prima il
    # turno falliva e basta - osservato in test reale: il medico generico,
    # chiamato a rispondere al consulto di un dermatologo, chiede a sua volta
    # l'"allergologo", fallisce due volte di fila e la sua risposta al collega
    # va persa.
    if azione == "consulta":
        raw_to = str(data.get("to") or "").strip()
        consult_target = _role_from_name(raw_to)
        if not consult_target or consult_target == role:
            if raw_to and role != "general_practitioner":
                print(f"🔀 {role}: 'consulta' verso '{raw_to}' (non nel roster) -> reindirizzato a general_practitioner")
                data = {**data, "to": "general_practitioner"}
                requested_for = raw_to
            else:
                azione = "conferma" if state.group_hypothesis is not None else "proponi"
                print(f"🔀 {role}: 'consulta' senza destinatario possibile -> la risposta vale come '{azione}'")
                if azione == "proponi" and not str(data.get("diagnosi", "")).strip():
                    print(f"⚠️ {role}: nessuna diagnosi da proporre - turno fallito")
                    return _failed_turn(state, role)

    # Rete di sicurezza puramente meccanica: "proponi" e' valido solo se non
    # esiste ancora un'ipotesi, "conferma"/"rivedi" solo se esiste gia' - un'azione
    # fuori schema o incoerente col contesto (risposta malformata, o "proponi"
    # quando qualcun altro ha gia' aperto la discussione) ripiega sull'unica
    # azione sempre valida in quel contesto, senza richiedere una nuova
    # chiamata all'LLM. "consulta" invece e' valido SEMPRE, anche al primissimo
    # turno: e' proprio il caso in cui serve di piu' (uno specialista solo,
    # incerto, che vuole un parere PRIMA di sbilanciarsi con una prima ipotesi)
    # - vietarlo finche' non esiste un'ipotesi lo avrebbe reso impossibile
    # proprio quando servirebbe (osservato in test reale: con un solo
    # specialista al tavolo, "proponi" si auto-conferma all'istante e la
    # discussione finisce al primo turno, senza mai dargli occasione di
    # chiedere un consulto).
    has_hypothesis = state.group_hypothesis is not None
    if azione not in ("proponi", "conferma", "rivedi", "consulta"):
        azione = "conferma" if has_hypothesis else "proponi"
    elif azione == "proponi" and has_hypothesis:
        azione = "conferma"
    elif azione in ("conferma", "rivedi") and not has_hypothesis:
        azione = "proponi"

    # Campo obbligatorio forzato "coincide_con_gruppo" (vedi SPECIALIST_PROMPT,
    # sezione "ATTENZIONE ALL'ANCORAGGIO"): se la valutazione indipendente
    # dello specialista (scritta PRIMA di guardare l'ipotesi di gruppo nel
    # dettaglio, per non farsi influenzare) non coincide con l'ipotesi di
    # gruppo attuale, il turno diventa comunque "rivedi" - a prescindere da
    # quale azione lo specialista avesse scelto separatamente. Senza questo,
    # e' possibile che il modello noti una discrepanza nel proprio
    # ragionamento indipendente e poi la ignori confermando comunque (bias di
    # ancoraggio verso quanto gia' scritto - osservato in test reale). Se il
    # campo "diagnosi" del "rivedi" forzato manca (il modello aveva compilato
    # lo schema di "conferma", che non lo prevede), usiamo la valutazione
    # indipendente stessa come diagnosi aggiornata.
    valutazione_indipendente = str(data.get("valutazione_indipendente", "")).strip()
    if str(data.get("coincide_con_gruppo", "")).strip().lower() == "no" and azione == "conferma":
        print(f"🔀 {role}: coincide_con_gruppo=no ma azione=conferma -> 'rivedi' forzato (anti-ancoraggio)")
        azione = "rivedi"
        if not str(data.get("diagnosi", "")).strip() and valutazione_indipendente:
            data = {**data, "diagnosi": valutazione_indipendente}

    # Consulto forzato al primo turno senza una diagnosi da proporre: non c'e'
    # nessuna proposta da salvare (si aprirebbe un'ipotesi vuota, "Diagnosi non
    # determinata") - il turno resta un semplice mini-consulto, come prima.
    if forced_consult_to and azione == "proponi" and not str(data.get("diagnosi", "")).strip():
        azione = "consulta"
        data = {**data, "to": forced_consult_to, "message": data.get("domanda_per_il_collega") or ""}
        forced_consult_to = None

    target = _role_from_name(data.get("to"))
    if target == role:
        target = None

    motivazione = str(data.get("motivazione", "")).strip()
    message = str(data.get("message", "")).strip()
    # ipotesi_alternativa_scartata/motivo_scarto: obbligano a nominare sempre
    # un'altra spiegazione clinica considerata e scartata (non richiesto per
    # "consulta", che e' solo una domanda) - da' ai colleghi materiale
    # concreto su cui eventualmente dissentire (vedi SPECIALIST_PROMPT).
    alternativa = str(data.get("ipotesi_alternativa_scartata", "")).strip()
    motivo_scarto = str(data.get("motivo_scarto", "")).strip()

    # --- "consulta": mini-consulto a un collega ASSENTE dal tavolo, non
    # tocca l'ipotesi di gruppo - solo una domanda di conoscenza clinica
    # generale (vedi SPECIALIST_PROMPT). Il router (router.py) lo "recluta"
    # leggendo il campo "to" di questo intervento.
    if azione == "consulta":
        if not target:
            print(f"⚠️ {role}: 'consulta' senza destinatario valido, ignorato - turno fallito")
            return _failed_turn(state, role)
        entry, msg_text = await _send_consult(
            role, display_name, author, target, message or motivazione or "(nessuna domanda specificata)",
            requested_for,
        )
        return {
            "round_table": [entry],
            "general_history": [AIMessage(content=msg_text)],
        }

    # --- "proponi"/"conferma"/"rivedi": agiscono sull'ipotesi di gruppo condivisa ---
    # Risposta a un mini-consulto: e' SEMPRE rivolta a chi l'ha chiesto, in modo
    # esplicito, cosi' il router gli ridara' la parola per replicare (vedi
    # "riapertura per reazione" nel router in router.py). Prima la risposta
    # andava a chiunque indicasse il modello (spesso nessuno), e chi aveva
    # chiesto il consulto non parlava piu': osservato in test reale, il
    # gastroenterologo chiede un parere al dermatologo, il dermatologo risponde
    # e conferma, e la discussione si chiude senza che la domanda abbia avuto
    # un seguito.
    if state.round_table:
        last = state.round_table[-1]
        if last.azione == "consulta" and last.to == role and last.author != role:
            target = last.author
    target_explicit = bool(target)
    if not target:
        # Rete di sicurezza puramente meccanica (basata su CHI ha parlato per
        # ultimo, non su COSA ha detto): se non specificato e la discussione
        # e' gia' iniziata, ci si rivolge di default all'ultimo collega
        # diverso da noi che ha parlato - senza questo il modello lascia quasi
        # sempre "to" vuoto anche quando dovrebbe confrontarsi con qualcuno
        # (osservato in test reale nel disegno precedente). Segnato come NON
        # esplicito (to_explicit=False): il router non lo tratta come una
        # chiamata in causa che meriti una battuta di reazione.
        for prev in reversed(state.round_table):
            if prev.author != role:
                target = prev.author
                break

    parti = []
    if motivazione:
        parti.append(motivazione)
    if message:
        parti.append(message)
    if alternativa:
        scarto = f" ({motivo_scarto})" if motivo_scarto else ""
        parti.append(f"Ho considerato anche '{alternativa}' ma l'ho esclusa{scarto}.")
    content_msg = " — ".join(parti)

    prev_gh = state.group_hypothesis
    stated_urgency = _parse_urgency(data.get("urgenza"))
    # Lista di esami: un modello puo' restituirla come testo unico invece che
    # come lista, e la validazione dell'ipotesi fallirebbe - la normalizziamo.
    exams = data.get("esami_consigliati") or []
    if isinstance(exams, str):
        exams = [exams]
    exams = [str(e) for e in exams if str(e).strip()]
    data = {**data, "esami_consigliati": exams}
    if azione == "proponi":
        gh = GroupHypothesis(
            diagnosis=str(data.get("diagnosi", "")).strip() or "Diagnosi non determinata",
            urgency_level=stated_urgency or "BIANCO",
            recommended_exams=data.get("esami_consigliati", []),
            details=str(data.get("dettagli", "")).strip(),
            discarded_alternative=alternativa,
            discard_reason=motivo_scarto,
            last_updated_by=role,
            confirmed_by=[role],
        )
        content_msg = content_msg or gh.diagnosis
    elif azione == "rivedi":
        gh = GroupHypothesis(
            diagnosis=str(data.get("diagnosi", "")).strip() or prev_gh.diagnosis,
            urgency_level=stated_urgency or prev_gh.urgency_level,
            recommended_exams=data.get("esami_consigliati") or prev_gh.recommended_exams,
            details=str(data.get("dettagli", "")).strip() or prev_gh.details,
            discarded_alternative=alternativa or prev_gh.discarded_alternative,
            discard_reason=motivo_scarto or prev_gh.discard_reason,
            last_updated_by=role,
            # Si azzera apposta: chiunque avesse gia' confermato la versione
            # PRECEDENTE deve riconfermare esplicitamente questa nuova (vedi
            # GroupHypothesis in state.py e router in router.py).
            confirmed_by=[role],
        )
    else:  # conferma - l'ipotesi resta identica, si aggiunge solo il conferma
        already = set(prev_gh.confirmed_by)
        already.add(role)
        gh = prev_gh.model_copy(update={"confirmed_by": sorted(already)})

    if not content_msg:
        content_msg = "(nessun commento aggiuntivo)"

    # Urgenza sostenuta da chi parla: per "proponi"/"rivedi" quella della nuova
    # versione dell'ipotesi; per "conferma" quella dell'ipotesi confermata,
    # A MENO CHE lo specialista non ne abbia scritta una sua diversa - succede
    # quando voleva "proporre" ma un'ipotesi c'era gia' e il turno e' stato
    # trasformato in conferma (vedi rete di sicurezza sulle azioni piu' sopra):
    # prima quella sua urgenza andava persa senza lasciare traccia.
    entry_urgency = gh.urgency_level if azione in ("proponi", "rivedi") else (stated_urgency or gh.urgency_level)
    entry = RoundTableEntry(
        author=role, to=target, to_explicit=target_explicit,
        azione=azione, content=content_msg, urgency=entry_urgency, verification=is_verification,
    )
    destinatario = SPECIALIST_DISPLAY_NAMES.get(target, target) if target else "tutti"
    azione_label = {"proponi": "apre la discussione", "conferma": "conferma", "rivedi": "rivede l'ipotesi"}[azione]
    msg_text = f"**{display_name}** {azione_label} (a {destinatario}): {content_msg}"
    if is_verification:
        msg_text = "*Giro di verifica finale* — " + msg_text
    if azione in ("proponi", "rivedi"):
        msg_text += f"\n\n*Ipotesi di gruppo aggiornata: {gh.diagnosis} (urgenza {gh.urgency_level})*"
    elif entry_urgency != gh.urgency_level:
        msg_text += f"\n\n*Urgenza indicata da {display_name}: {entry_urgency} (ipotesi di gruppo: {gh.urgency_level})*"
    await cl.Message(content=msg_text, author=author).send()

    entries = [entry]
    messages = [AIMessage(content=msg_text)]
    if forced_consult_to:
        # Il consulto va per ULTIMO nella discussione: il router fa parlare
        # subito il destinatario dell'ultimo intervento (vedi router in router.py).
        domanda = str(data.get("domanda_per_il_collega") or "").strip() or "(nessuna domanda specificata)"
        consult_entry, consult_text = await _send_consult(role, display_name, author, forced_consult_to, domanda,
                                                            requested_for)
        entries.append(consult_entry)
        messages.append(AIMessage(content=consult_text))

    return {
        "round_table": entries,
        "group_hypothesis": gh.model_dump(),
        "general_history": messages,
    }


async def _send_consult(role: str, display_name: str, author: str, target: str, domanda: str,
                        requested_for: str = ""):
    """Registra e mostra in chat un mini-consulto verso un collega. Se la
    richiesta era per uno specialista che il sistema non ha (requested_for),
    la chat lo dice: prima compariva solo "Medicina", e il nome inventato
    restava soltanto nel testo dello specialista."""
    entry = RoundTableEntry(author=role, to=target, azione="consulta", content=domanda)
    destinatario = SPECIALIST_DISPLAY_NAMES.get(target, target)
    nota = f" (richiesta per \"{requested_for}\", specialista non disponibile)" if requested_for else ""
    msg_text = f"**{display_name}** chiede un mini-consulto a **{destinatario}**{nota}: {domanda}"
    await cl.Message(content=msg_text, author=author).send()
    return entry, msg_text


# Wrapper per i nodi specifici: ognuno chiama semplicemente specialist_node
# con il proprio ruolo - e' quest'ultimo (non il wrapper) a mandare il
# messaggio in chat, gia' con il profilo giusto.
async def cardiologist_node(state):
    return await specialist_node(state, "cardiologist")


async def neurologist_node(state):
    return await specialist_node(state, "neurologist")


async def orthopedic_node(state):
    return await specialist_node(state, "orthopedist")


async def gastroenterologist_node(state):
    return await specialist_node(state, "gastroenterologist")


async def dermatologist_node(state):
    return await specialist_node(state, "dermatologist")


async def pneumologist_node(state):
    return await specialist_node(state, "pulmonologist")


async def ent_node(state):  # Otorino (Ear Nose Throat)
    return await specialist_node(state, "ent")


async def ophthalmologist_node(state):
    return await specialist_node(state, "ophthalmologist")


async def urologist_node(state):
    return await specialist_node(state, "urologist")


async def general_practitioner_node(state):
    return await specialist_node(state, "general_practitioner")
