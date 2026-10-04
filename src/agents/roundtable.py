# Cio' che il tavolo degli specialisti ha in comune (non e' un agente): nomi
# degli specialisti, limiti della discussione, codici colore, trascrizione
# letta da specialisti e primario, nota pediatrica. Usato da supervisor.py,
# specialist.py, router.py e primary.py.
import re

from src.state import PatientCard, RoundTableEntry
from .prompts import ALL_SPECIALISTS


# Tetto assoluto di battute nell'intera discussione al tavolo - non e' un
# traguardo (il tavolo puo' convergere prima, se tutti confermano l'ipotesi di
# gruppo), solo il freno di emergenza che garantisce si arrivi sempre al
# primario anche nel caso peggiore di una discussione che non converge da
# sola. Gestito interamente da router() in router.py. Portato da 10 a 12 con
# il giro di verifica finale e il tetto di 3 interventi a testa, che allungano
# la discussione.
MAX_TOTAL_TURNS = 12


# Quanti turni FALLITI (risposta illeggibile, errore dell'API anche dopo i
# nuovi tentativi, consulto senza destinatario valido) uno specialista puo'
# avere prima che il router lo faccia passare oltre, senza ridargli la parola.
# Prima un turno fallito non veniva contato da nessuna parte e il router
# richiamava lo stesso specialista all'infinito: osservato in test reale, 9
# fallimenti di fila dello stesso specialista fino al tetto MAX_TOTAL_TURNS,
# senza nessuna discussione. Gestito da router() in router.py.
MAX_FAILED_TURNS = 2


# Quanti specialisti IN PIU' rispetto alla selezione iniziale del supervisore
# possono essere coinvolti durante la discussione (es. "Cardiologia chiama
# Neurologia perche' il collega scelto dal supervisore non basta") - un tetto
# basso di proposito per evitare che il tavolo cresca senza controllo se gli
# specialisti si chiamano a vicenda. Gestito da router() in router.py.
MAX_RECRUITED_SPECIALISTS = 1


# Quante volte ciascuno specialista puo' intervenire prima che il router lo
# faccia passare MECCANICAMENTE (senza richiedergli un altro turno) se non ha
# ancora confermato l'ipotesi di gruppo - tetto individuale, piu' stretto del
# tetto globale MAX_TOTAL_TURNS sopra. Senza questo, si e' osservato in test
# reale (nel disegno precedente a referti indipendenti) che due specialisti
# continuano a scambiarsi ipotesi quasi identiche per 4-5 turni a testa prima
# che il tetto globale intervenga - un tetto per-specialista fa convergere la
# discussione molto piu' in fretta. Gestito interamente da router() in router.py.
# Portato da 2 a 3 quando le regole della discussione (replica a chi chiede un
# consulto, battute di reazione) hanno reso piu' frequente il botta e
# risposta: con 2 il secondo intervento finiva spesso per essere l'ultimo. Il
# turno del giro di verifica finale non conta in questo tetto (vedi router).
MAX_SPEAKS_PER_SPECIALIST = 3


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
#
# Oltre al nome della specialita' ("Dermatologia"), gli specialisti usano
# spesso il nome del MEDICO in italiano ("dermatologo") - osservato in test
# reale: un consulto chiesto al "dermatologo" non veniva riconosciuto e finiva
# al medico generico (il ripiego per i ruoli fuori dal roster), anche se il
# dermatologo era disponibile. Le varianti sotto coprono i nomi dei medici
# (maschile e femminile) e le forme brevi piu' comuni.
_ITALIAN_DOCTOR_NAMES = {
    "cardiologist": ["cardiologo", "cardiologa"],
    "neurologist": ["neurologo", "neurologa"],
    "dermatologist": ["dermatologo", "dermatologa"],
    "orthopedist": ["ortopedico", "ortopedica", "ortopedia e traumatologia", "traumatologo"],
    "gastroenterologist": ["gastroenterologo", "gastroenterologa"],
    "pulmonologist": ["pneumologo", "pneumologa"],
    "ent": ["otorinolaringoiatra", "otorino", "orl"],
    "ophthalmologist": ["oftalmologo", "oftalmologa", "oculista", "oculistica"],
    "urologist": ["urologo", "urologa"],
    "general_practitioner": ["medico di base", "medico generico", "medico di medicina generale",
                             "medicina generale", "mmg"],
}


_DISPLAY_NAME_TO_ROLE = {name.lower(): role for role, name in SPECIALIST_DISPLAY_NAMES.items()}


_DISPLAY_NAME_TO_ROLE.update(
    {name: role for role, names in _ITALIAN_DOCTOR_NAMES.items() for name in names}
)


_NAME_PREFIX = re.compile(r"^(il|lo|la|l'|al|allo|alla|dott\.?|dr\.?|dottor|dottoressa)\s*", re.IGNORECASE)


def _role_from_name(raw) -> str | None:
    """Ruolo interno (es. "dermatologist") dal nome che lo specialista ha
    scritto per un collega: il ruolo stesso, il nome della specialita'
    ("Dermatologia") o il nome del medico ("il dermatologo"); None se non e'
    nessuno dei 10 specialisti del sistema."""
    text = str(raw or "").strip().lower().rstrip(".,;:!?")
    text = _NAME_PREFIX.sub("", text).strip()
    if text in ALL_SPECIALISTS:
        return text
    return _DISPLAY_NAME_TO_ROLE.get(text)


# Scala dei codici colore, dal piu' al meno urgente (stessa di GroupHypothesis
# e FinalDiagnosis in state.py).
URGENCY_LEVELS = ["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"]


def _parse_urgency(value) -> str | None:
    """Urgenza scritta dall'LLM -> uno dei 5 codici, oppure None se assente o
    non riconoscibile. Senza questa normalizzazione un "arancione" minuscolo
    faceva fallire la validazione dell'ipotesi di gruppo (Literal in state.py)."""
    text = str(value or "").strip().upper()
    return text if text in URGENCY_LEVELS else None


# Lunghezza massima di un intervento nella trascrizione letta dai colleghi
# (non in chat, dove resta intero). Rete di sicurezza oltre alla regola
# BREVITA' del prompt: un solo intervento arrivava a ~850 token e, con la
# discussione che cresce, il prompt superava il limite di token al minuto di
# Groq (errore 413, turni persi). Un intervento rivolto proprio a chi parla
# arriva comunque intero, nel blocco "consulto_pendente" (specialist_node).
MAX_ENTRY_CHARS_IN_TRANSCRIPT = 1200


def _format_round_table(entries: list[RoundTableEntry]) -> str:
    """Rende leggibile la discussione finora per il prompt dello specialista
    di turno - ognuno vede l'intera trascrizione, non solo l'ultimo scambio
    (ogni intervento accorciato a MAX_ENTRY_CHARS_IN_TRANSCRIPT)."""
    if not entries:
        return "Nessun intervento precedente - sei il primo a parlare."
    righe = []
    for e in entries:
        content = e.content
        if len(content) > MAX_ENTRY_CHARS_IN_TRANSCRIPT:
            content = content[:MAX_ENTRY_CHARS_IN_TRANSCRIPT].rsplit(" ", 1)[0] + " […]"
        chi_parla = SPECIALIST_DISPLAY_NAMES.get(e.author, e.author)
        destinatario = SPECIALIST_DISPLAY_NAMES.get(e.to, e.to) if e.to else "tutti"
        tag = ", ".join(t for t in (
            "GIRO DI VERIFICA" if e.verification else "",
            e.azione.upper(),
            f"urgenza {e.urgency}" if e.urgency else "",
        ) if t)
        azione_tag = f" [{tag}]" if tag else ""
        righe.append(f"{chi_parla} (a {destinatario}){azione_tag}: {content}")
    return "\n".join(righe)


def _format_urgencies(entries: list[RoundTableEntry]) -> str:
    """Tutte le urgenze espresse durante la discussione, nell'ordine in cui sono
    state dette - per il primario, che altrimenti vede solo quella dell'ultima
    versione dell'ipotesi di gruppo."""
    righe = []
    for turno, e in enumerate(entries, 1):
        if e.urgency:
            chi = SPECIALIST_DISPLAY_NAMES.get(e.author, e.author)
            righe.append(f"- {e.urgency}: {chi} (intervento {turno}, {e.azione})")
    if not righe:
        return "Nessuna urgenza espressa esplicitamente al tavolo."
    livelli = {e.urgency for e in entries if e.urgency}
    if len(livelli) > 1:
        piu_alta = min(livelli, key=URGENCY_LEVELS.index)
        righe.append(f"ATTENZIONE: il tavolo NON e' stato concorde sull'urgenza - la piu' alta espressa e' {piu_alta}.")
    return "\n".join(righe)


def _pediatric_note(card: PatientCard) -> str:
    """Nota per specialisti e primario se il paziente e' minorenne, "" altrimenti
    (anche se l'eta' non si legge). Le linee guida del RAG sono per adulti
    (es. il manuale di triage FVG "adulto") e nessuno lo segnalava: nella prova
    del ginocchio di un quattordicenne si ragionava come per un adulto. Nessun
    nodo nuovo: solo una frase in piu' nel prompt, come per il giro di verifica."""
    age = card.age.strip().lower()
    match = re.match(r"(\d{1,3})", age)
    if not match:
        return ""
    in_mesi_o_giorni = any(u in age for u in ("mes", "giorn", "settiman"))
    if not in_mesi_o_giorni and int(match.group(1)) >= 18:
        return ""
    eta = age if in_mesi_o_giorni else f"{match.group(1)} anni"
    return (
        f"PAZIENTE PEDIATRICO ({eta}): le linee guida recuperate sono pensate per adulti. Tienine conto: "
        "criteri di gravita', esami, dosaggi e codici di urgenza possono essere diversi in eta' pediatrica; "
        "segnala quando serve una valutazione pediatrica."
    )
