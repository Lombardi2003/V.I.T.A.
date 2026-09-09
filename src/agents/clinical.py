# Nodi della fase di valutazione clinica: smistamento (supervisor), consulti
# specialistici (specialist_node + i 10 wrapper), sintesi finale (primario).
import asyncio
import json
import re

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState, RoundTableEntry, GroupHypothesis, FinalDiagnosis
from .prompts import SUPERVISOR_PROMPT, SPECIALIST_PROMPT, PRIMARY_PROMPT, ALL_SPECIALISTS
from .common import stream_response, llm_specialist
from .authors import Authors

# Tetto assoluto di battute nell'intera discussione al tavolo - non e' un
# traguardo (il tavolo puo' convergere prima, se tutti confermano l'ipotesi di
# gruppo), solo il freno di emergenza che garantisce si arrivi sempre al
# primario anche nel caso peggiore di una discussione che non converge da
# sola. Gestito interamente da router() in graph.py.
MAX_TOTAL_TURNS = 10

# Quanti specialisti IN PIU' rispetto alla selezione iniziale del supervisore
# possono essere coinvolti durante la discussione (es. "Cardiologia chiama
# Neurologia perche' il collega scelto dal supervisore non basta") - un tetto
# basso di proposito per evitare che il tavolo cresca senza controllo se gli
# specialisti si chiamano a vicenda. Gestito da router() in graph.py.
MAX_RECRUITED_SPECIALISTS = 1

# Quante volte ciascuno specialista puo' intervenire prima che il router lo
# faccia passare MECCANICAMENTE (senza richiedergli un altro turno) se non ha
# ancora confermato l'ipotesi di gruppo - tetto individuale, piu' stretto del
# tetto globale MAX_TOTAL_TURNS sopra. Senza questo, si e' osservato in test
# reale (nel disegno precedente a referti indipendenti) che due specialisti
# continuano a scambiarsi ipotesi quasi identiche per 4-5 turni a testa prima
# che il tetto globale intervenga - un tetto per-specialista fa convergere la
# discussione molto piu' in fretta. Gestito interamente da router() in graph.py.
MAX_SPEAKS_PER_SPECIALIST = 2


# Nomi leggibili degli specialisti per i messaggi rivolti al paziente - le
# chiavi restano in inglese perche' sono anche i nomi dei nodi nel grafo
# (vedi ALL_SPECIALISTS in prompts.py e i nodi specialisti in questo file).
SPECIALIST_DISPLAY_NAMES = {
    "cardiologist": "Cardiologia",
    "neurologist": "Neurologia",
    "dermatologist": "Dermatologia",
    "orthopedist": "Ortopedia",
    "gastroenterologist": "Gastroenterologia",
    "pulmonologist": "Pneumologia",
    "ent": "Otorinolaringoiatria",
    "ophthalmologist": "Oftalmologia",
    "urologist": "Urologia",
    "general_practitioner": "Medicina",
}

# Mappa inversa nome->ruolo: il campo "to" che gli specialisti restituiscono
# a volte usa il nome mostrato in italiano invece del ruolo interno in inglese
# (osservato in test reale - probabile perche' la trascrizione del tavolo che
# leggono, vedi _format_round_table sotto, mostra proprio i nomi italiani) -
# senza questo, un "to": "Dermatologia" veniva scartato silenziosamente
# perche' non presente in ALL_SPECIALISTS, e il messaggio finiva "a tutti"
# anche quando lo specialista intendeva rivolgersi a un collega preciso.
_DISPLAY_NAME_TO_ROLE = {name.lower(): role for role, name in SPECIALIST_DISPLAY_NAMES.items()}


# Nodo del supervisore
async def supervisor_node(state: MedicalState):
    """Legge la cartella clinica (e la foto, se presente) e decide quali
    specialisti coinvolgere - compito puramente di smistamento, non emette
    diagnosi ne' giudizi clinici propri."""
    card = state.patient_card
    photo = card.symptom.photo
    card_str = card.model_dump_json()
    photo_str = photo.model_dump_json() if photo else "Nessuna foto."

    prompt = SUPERVISOR_PROMPT.format(patient_card=card_str, photo_analysis=photo_str)
    selected_specialists = ["general_practitioner"]

    async with cl.Step(name="Smistamento clinico", type="tool", default_open=False, show_input="text") as step:
        step.input = card_str
        # stream_response e' sincrona (bloccante): chiamata cosi' dentro una
        # funzione async bloccherebbe l'INTERO ciclo di eventi di Chainlit per
        # tutta la durata della chiamata - impercettibile con Groq (pochi
        # secondi), ma con un modello locale lento (Ollama) l'app sembra
        # completamente ferma (osservato in test reale). asyncio.to_thread la
        # sposta su un thread separato senza bloccare il resto.
        content = await asyncio.to_thread(stream_response, prompt)
        step.output = content

    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)

        specs = data.get("specialists", [])
        clean_specs = [s.lower() for s in specs if s.lower() in ALL_SPECIALISTS]

        if clean_specs:
            selected_specialists = clean_specs

        print(f"🚦 SUPERVISOR → {selected_specialists}")

    except json.JSONDecodeError:
        print("🚦 SUPERVISOR: errore lettura JSON, fallback su medico generale")

    nomi = ", ".join(SPECIALIST_DISPLAY_NAMES.get(s, s) for s in selected_specialists)
    plurale = len(selected_specialists) > 1
    verbo = "Verranno coinvolti in consulto" if plurale else "Verrà coinvolto in consulto"
    msg = f"{verbo}: **{nomi}**."
    await cl.Message(content=msg, author=Authors.SUPERVISOR).send()

    # Il valore booleano non porta piu' informazione propria (vedi commento su
    # needed_specialists in state.py) - resta sempre True, il dizionario serve
    # solo come insieme ordinato di chi e' seduto al tavolo.
    checklist = {specialist: True for specialist in selected_specialists}
    print(f"   Checklist: {checklist}")
    return {
        "needed_specialists": checklist,
        "general_history": [AIMessage(content=msg)],
    }


def _format_round_table(entries: list[RoundTableEntry]) -> str:
    """Rende leggibile la discussione finora per il prompt dello specialista
    di turno - ognuno vede l'intera trascrizione, non solo l'ultimo scambio."""
    if not entries:
        return "Nessun intervento precedente - sei il primo a parlare."
    righe = []
    for e in entries:
        chi_parla = SPECIALIST_DISPLAY_NAMES.get(e.author, e.author)
        destinatario = SPECIALIST_DISPLAY_NAMES.get(e.to, e.to) if e.to else "tutti"
        azione_tag = f" [{e.azione.upper()}]" if e.azione else ""
        righe.append(f"{chi_parla} (a {destinatario}){azione_tag}: {e.content}")
    return "\n".join(righe)


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


async def specialist_node(state: MedicalState, role: str):
    """Un turno di uno specialista al tavolo: legge cartella clinica e
    l'ipotesi di gruppo condivisa (con l'intera discussione come contesto),
    poi la propone/conferma/rivede, oppure chiama in causa un collega assente
    con un mini-consulto. Il router (graph.py) decide chi parla dopo e quando
    la discussione e' conclusa - questo nodo non lo decide da solo, e non
    viene MAI invocato oltre i tetti di MAX_TOTAL_TURNS/MAX_SPEAKS_PER_SPECIALIST
    (il router passa oltre meccanicamente prima di richiamarlo, vedi graph.py)."""
    display_name = SPECIALIST_DISPLAY_NAMES.get(role, role)
    author = getattr(Authors, role.upper(), Authors.SYSTEM)

    card_str = state.patient_card.model_dump_json()
    table_text = _format_round_table(state.round_table)
    hypothesis_text = _format_group_hypothesis(state.group_hypothesis)

    # Se l'ultimo intervento era rivolto PROPRIO a questo specialista (to ==
    # role) - un mini-consulto (azione "consulta") o una riapertura per
    # reazione decisa dal router quando tutti avevano gia' confermato (vedi
    # router in graph.py) - questo turno DEVE rispondere a quel punto preciso
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

    prompt = SPECIALIST_PROMPT.format(
        role_display=display_name,
        role=role,
        card=card_str,
        round_table=table_text,
        hypothesis=hypothesis_text,
        consulto_pendente=consulto_pendente,
    )

    try:
        async with cl.Step(name=display_name, type="tool", default_open=False, show_input="text") as step:
            step.input = table_text
            # asyncio.to_thread: vedi commento su supervisor_node poco sopra -
            # stessa identica ragione. Qui e' il punto piu' critico del grafo
            # per questo problema, dato che llm_specialist puo' essere un
            # modello locale (Ollama) molto piu' lento di Groq.
            content = await asyncio.to_thread(stream_response, prompt, llm_specialist)
            step.output = content
    except Exception as e:
        # Un errore diretto dell'API (es. rate limit superato a meta' dello
        # streaming, osservato in test reale con openai.APIError) non deve
        # mandare in crash l'intero grafo - stesso trattamento riservato al
        # JSON malformato/troncato piu' sotto: nessun aggiornamento, il
        # router richiamera' comunque questo specialista al prossimo giro
        # (fino a MAX_SPEAKS_PER_SPECIALIST).
        print(f"⚠️ {role}: errore API ({e}), nessun aggiornamento - richiamato al prossimo giro")
        return {}

    try:
        # qwen/qwen3.6-27b (e altri modelli "thinking") antepongono un blocco
        # <think>...</think> di ragionamento prima del JSON vero - lo scartiamo
        # ed estraiamo il primo oggetto {...} invece di assumere che l'intera
        # risposta sia gia' JSON puro (stesso identico problema gia' risolto
        # per l'analisi foto in intake.py, quando questo modello veniva usato
        # solo per la visione).
        clean_content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        clean_content = clean_content.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", clean_content, flags=re.DOTALL)
        if match:
            clean_content = match.group(0)
        data = json.loads(clean_content)
        azione = str(data.get("azione", "")).lower().strip()
    except json.JSONDecodeError:
        # Un JSON malformato/troncato (osservato in test reale: la risposta
        # si tronca a meta' parola, es. per un limite di token) NON deve mai
        # ricadere sul ramo "conferma" piu' sotto - altrimenti un guasto
        # tecnico si travestirebbe da giudizio clinico genuino (un'obiezione
        # vera, magari gia' scritta ma troncata prima del completamento del
        # JSON, verrebbe convertita in un consenso silenzioso alla diagnosi
        # sbagliata - trovato mentre si testava apposta la correzione di
        # un'ipotesi iniettata scorretta). Usciamo qui senza aggiornare nulla:
        # il router richiamera' comunque questo specialista al turno
        # successivo (fino a MAX_SPEAKS_PER_SPECIALIST), stesso identico
        # trattamento riservato a un intervento vuoto piu' sotto.
        print(f"⚠️ {role}: errore lettura JSON (risposta malformata/troncata), nessun aggiornamento - richiamato al prossimo giro")
        return {}

    # Campo obbligatorio forzato "consulto_utile" (vedi SPECIALIST_PROMPT): se
    # lo specialista dichiara che il parere di un collega ASSENTE cambierebbe
    # davvero la sua valutazione, il turno diventa un mini-consulto verso quel
    # collega A PRESCINDERE da quale "azione" avesse scelto separatamente -
    # stessa tecnica del campo obbligatorio gia' usata con successo altrove in
    # questo progetto (es. ipotesi_alternativa_scartata): un valore da
    # dichiarare esplicitamente ad ogni turno cambia il comportamento molto
    # piu' della sola prosa che "permette" un'opzione tra tante (osservato in
    # test reale: la sola prosa non bastava mai a far scegliere "consulta").
    consulto_utile = str(data.get("consulto_utile", "")).strip().lower() == "si"
    raw_collega = str(data.get("collega_da_consultare") or "").strip().lower()
    collega = raw_collega if raw_collega in ALL_SPECIALISTS else _DISPLAY_NAME_TO_ROLE.get(raw_collega)
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
    if consulto_utile and collega and azione != "consulta":
        print(f"🔀 {role}: consulto_utile=si -> mini-consulto forzato verso {collega}")
        azione = "consulta"
        data = {**data, "to": collega, "message": data.get("domanda_per_il_collega") or ""}

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

    raw_target = str(data.get("to") or "").strip().lower()
    target = raw_target if raw_target in ALL_SPECIALISTS else _DISPLAY_NAME_TO_ROLE.get(raw_target)
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
    # generale (vedi SPECIALIST_PROMPT). Il router (graph.py) lo "recluta"
    # leggendo il campo "to" di questo intervento.
    if azione == "consulta":
        if not target:
            print(f"⚠️ {role}: 'consulta' senza destinatario valido, ignorato")
            return {}
        domanda = message or motivazione or "(nessuna domanda specificata)"
        entry = RoundTableEntry(author=role, to=target, azione="consulta", content=domanda)
        destinatario = SPECIALIST_DISPLAY_NAMES.get(target, target)
        msg_text = f"**{display_name}** chiede un mini-consulto a **{destinatario}**: {domanda}"
        await cl.Message(content=msg_text, author=author).send()
        return {
            "round_table": [entry],
            "general_history": [AIMessage(content=msg_text)],
        }

    # --- "proponi"/"conferma"/"rivedi": agiscono sull'ipotesi di gruppo condivisa ---
    if not target:
        # Rete di sicurezza puramente meccanica (basata su CHI ha parlato per
        # ultimo, non su COSA ha detto): se non specificato e la discussione
        # e' gia' iniziata, ci si rivolge di default all'ultimo collega
        # diverso da noi che ha parlato - senza questo il modello lascia quasi
        # sempre "to" vuoto anche quando dovrebbe confrontarsi con qualcuno
        # (osservato in test reale nel disegno precedente).
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
    if azione == "proponi":
        gh = GroupHypothesis(
            diagnosis=str(data.get("diagnosi", "")).strip() or "Diagnosi non determinata",
            urgency_level=data.get("urgenza", "BIANCO"),
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
            urgency_level=data.get("urgenza") or prev_gh.urgency_level,
            recommended_exams=data.get("esami_consigliati") or prev_gh.recommended_exams,
            details=str(data.get("dettagli", "")).strip() or prev_gh.details,
            discarded_alternative=alternativa or prev_gh.discarded_alternative,
            discard_reason=motivo_scarto or prev_gh.discard_reason,
            last_updated_by=role,
            # Si azzera apposta: chiunque avesse gia' confermato la versione
            # PRECEDENTE deve riconfermare esplicitamente questa nuova (vedi
            # GroupHypothesis in state.py e router in graph.py).
            confirmed_by=[role],
        )
    else:  # conferma - l'ipotesi resta identica, si aggiunge solo il conferma
        already = set(prev_gh.confirmed_by)
        already.add(role)
        gh = prev_gh.model_copy(update={"confirmed_by": sorted(already)})

    if not content_msg:
        content_msg = "(nessun commento aggiuntivo)"

    entry = RoundTableEntry(author=role, to=target, azione=azione, content=content_msg)
    destinatario = SPECIALIST_DISPLAY_NAMES.get(target, target) if target else "tutti"
    azione_label = {"proponi": "apre la discussione", "conferma": "conferma", "rivedi": "rivede l'ipotesi"}[azione]
    msg_text = f"**{display_name}** {azione_label} (a {destinatario}): {content_msg}"
    if azione in ("proponi", "rivedi"):
        msg_text += f"\n\n*Ipotesi di gruppo aggiornata: {gh.diagnosis} (urgenza {gh.urgency_level})*"
    await cl.Message(content=msg_text, author=author).send()

    return {
        "round_table": [entry],
        "group_hypothesis": gh.model_dump(),
        "general_history": [AIMessage(content=msg_text)],
    }


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


# Nodo del primario
async def primary_node(state: MedicalState):
    """Legge la scheda del paziente e l'ipotesi di gruppo a cui il tavolo degli
    specialisti e' arrivato discutendo insieme (non piu' N referti indipendenti
    da confrontare lui stesso), e la traduce nella diagnosi finale ufficiale
    (FinalDiagnosis).

    NOTA: per ora chief_physician->END e' un punto di osservazione temporaneo
    (vedi graph.py) - il salvataggio su DB (save_db/modify_db) non e' ancora
    ricollegato, verra' fatto in un passo successivo.
    """
    card = state.patient_card
    gh = state.group_hypothesis
    coinvolti = list(state.needed_specialists.keys())

    card_str = card.model_dump_json()

    if gh is None:
        # Caso limite: il tetto MAX_TOTAL_TURNS e' scattato prima che
        # chiunque aprisse la discussione (non dovrebbe succedere in pratica,
        # il primo turno e' sempre "proponi" - vedi specialist_node).
        hypothesis_text = "Il tavolo non e' arrivato a nessuna ipotesi condivisa."
    else:
        confermato_da = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in gh.confirmed_by) or "nessuno"
        mancano = [r for r in coinvolti if r not in gh.confirmed_by]
        mancano_txt = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in mancano) or "nessuno"
        hypothesis_text = (
            f"Diagnosi: {gh.diagnosis}\n"
            f"Urgenza: {gh.urgency_level}\n"
            f"Esami consigliati: {', '.join(gh.recommended_exams) or 'nessuno indicato'}\n"
            f"Dettagli: {gh.details}\n"
            f"Alternativa considerata e scartata dal tavolo: {gh.discarded_alternative or '(nessuna)'}"
            f"{f' ({gh.discard_reason})' if gh.discard_reason else ''}\n"
            f"Confermata da: {confermato_da}\n"
            f"NON (ancora) confermata da: {mancano_txt}"
        )

    round_table_text = _format_round_table(state.round_table)

    prompt = PRIMARY_PROMPT.format(card=card_str, hypothesis_text=hypothesis_text, round_table_text=round_table_text)

    async with cl.Step(name="Sintesi finale", type="tool", default_open=False, show_input="text") as step:
        step.input = hypothesis_text
        # asyncio.to_thread: vedi commento su supervisor_node piu' sopra.
        content = await asyncio.to_thread(stream_response, prompt)
        step.output = content

    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        report_data = json.loads(clean_content)
        final = FinalDiagnosis(
            diagnosis=report_data.get("diagnosis", "Diagnosi non determinata"),
            urgency_level=report_data.get("urgency_level", "BIANCO"),
            specialists_involved=coinvolti,
            operational_guidance=report_data.get("operational_guidance", ""),
            recommendations=report_data.get("recommendations", ""),
        )
    except Exception as e:
        # Stessa rete di sicurezza degli altri nodi: JSON malformato o fuori
        # schema (es. urgency_level non tra i 5 valori validi) non deve
        # crashare il grafo - ripieghiamo su una diagnosi segnaposto.
        print(f"⚠️ PRIMARIO: risposta non valida dall'LLM, fallback ({e})")
        final = FinalDiagnosis(
            diagnosis="Diagnosi non determinata per un errore tecnico.",
            urgency_level="BIANCO",
            specialists_involved=coinvolti,
            recommendations="Si consiglia una valutazione medica diretta.",
        )

    print(f"👨‍⚕️ PRIMARIO → diagnosi={final.diagnosis!r} | urgenza={final.urgency_level}")

    msg = (
        f"**Diagnosi finale:** {final.diagnosis}\n\n"
        f"{final.recommendations}\n\n"
        f"**Indicazioni operative:** {final.operational_guidance}\n\n"
        f"**Livello di urgenza:** {final.urgency_level}"
    )
    await cl.Message(content=msg, author=Authors.PRIMARY_PHYSICIAN).send()

    return {
        "final_diagnosis": final.model_dump(),
        "general_history": [AIMessage(content=msg)],
    }
