# Nodi di acquisizione dati dal/sul paziente: passaggio del messaggio utente,
# raccolta anagrafica, raccolta sintomi, analisi foto.
import asyncio
import json
import base64
import io
import mimetypes
import re

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import chainlit as cl
from PIL import Image, ImageOps

from src.state import MedicalState, PatientCard, PhotoAnalysis
from .prompts import INTAKE_PROMPT, REVIEWER_PROMPT, PHOTO_PROMPT
from .common import stream_response, call_with_retry, extract_json, llm_vision, as_list, is_yes
from .authors import Authors


def _mentions(text: str, keywords: list[str]) -> bool:
    """Controllo grezzo indipendente dall'LLM: il testo contiene almeno una di
    queste parole chiave - usato in più nodi come rete di sicurezza quando non
    ci si puo' fidare al 100% di quello che l'LLM dichiara di aver estratto."""
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


def _format_card(card: PatientCard, allergies_addressed: bool, previous_conditions_addressed: bool) -> str:
    """Scheda anagrafica compatta da mostrare all'operatore a ogni turno di
    intake_node: nella prima riga solo i dati gia' presenti (quelli mancanti li
    elenca la riga "Mancano"). Niente elenco puntato: in chat ogni voce
    prendeva molto spazio. Una lista vuota si legge "nessuna" solo se
    l'argomento e' stato affrontato, altrimenti "da indicare"."""
    def _list(items: list[str], addressed: bool) -> str:
        if items:
            return ", ".join(items)
        return "nessuna" if addressed else "da indicare"

    name = f"{card.first_name.strip()} {card.last_name.strip()}".strip()
    age = card.age.strip()
    if age and age.isdigit():
        age = f"{age} anni"
    parts = [f"**CF** {card.fiscal_code.strip() or '—'}"]
    if name:
        parts.append(f"**Paziente** {name}")
    if age:
        parts.append(f"**Età** {age}")
    if card.sex.strip():
        parts.append(f"**Sesso** {card.sex.strip()}")

    lines = ["**Scheda paziente**", " · ".join(parts)]
    # Paziente appena creato: niente "da indicare", lo dice gia' la riga "Mancano".
    if card.allergies or allergies_addressed or card.previous_conditions or previous_conditions_addressed \
            or len(parts) > 1:
        lines.append(
            f"**Allergie** {_list(card.allergies, allergies_addressed)} · "
            f"**Patologie pregresse** {_list(card.previous_conditions, previous_conditions_addressed)}"
        )
    return "\n".join(lines)


def _format_symptoms(card: PatientCard) -> str:
    """Sintomi da mostrare all'operatore a ogni turno di reviewer_node: uno per
    blocco, "Sintomo N" e sotto descrizione - intensita' - durata (e
    caratteristiche e circostanze, facoltative, solo se indicate)."""
    blocks = []
    for i, s in enumerate(card.symptom.symptoms, start=1):
        parts = [
            s.description.strip() or "—",
            f"**Intensità** {s.intensity.strip() or 'da indicare'}",
            f"**Durata** {s.duration.strip() or 'da indicare'}",
        ]
        if s.characteristics.strip():
            parts.append(f"**Caratteristiche** {s.characteristics.strip()}")
        if s.trigger.strip():
            parts.append(f"**Circostanze** {s.trigger.strip()}")
        blocks.append(f"**Sintomo {i}**\n" + " - ".join(parts))
    return "\n".join(blocks)


_SEX_VALUES = {
    "uomo": {"m", "maschio", "uomo", "maschile", "male"},
    "donna": {"f", "femmina", "donna", "femminile", "female"},
}


def _capitalize_name(text: str) -> str:
    """Iniziale maiuscola per ogni parte del nome ("de luca" -> "De Luca",
    "d'angelo" -> "D'Angelo"). Le parti gia' scritte con maiuscole e minuscole
    miste (es. "McKenzie") restano come sono."""
    def _part(p: str) -> str:
        return p.capitalize() if p.islower() or p.isupper() else p
    return re.sub(r"[^\s'\-]+", lambda m: _part(m.group(0)), text.strip())


def _normalize_card(card: PatientCard) -> PatientCard:
    """Dati uniformi nella scheda stessa (non solo nella stampa), cosi' anche
    nel database finiscono uguali: sesso "uomo"/"donna" (se non riconosciuto resta com'e'),
    nome e cognome con l'iniziale maiuscola."""
    sex = card.sex.strip()
    for code, words in _SEX_VALUES.items():
        if sex.lower() in words:
            sex = code
    return card.model_copy(update={
        "sex": sex,
        "first_name": _capitalize_name(card.first_name),
        "last_name": _capitalize_name(card.last_name),
    })


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


# Nodo di raccolta dati anagrafici (non i sintomi, quelli restano al Revisore)
async def intake_node(state: MedicalState):
    """Raccoglie i campi anagrafici di primo livello di PatientCard.

    Continua a chiedere finche' nome, cognome, eta' e sesso non sono compilati,
    E allergie/patologie pregresse non sono state esplicitamente affrontate (anche
    per negarle) - questi ultimi due sono tracciati con due flag su MedicalState
    (non su PatientCard, perche' sono contabilita' di conversazione, non dato
    clinico da salvare nel referto).
    """

    def _missing_fields(card: PatientCard, allergies_addressed: bool, previous_conditions_addressed: bool) -> list[str]:
        missing = []
        if not card.first_name.strip():
            missing.append("nome")
        if not card.last_name.strip():
            missing.append("cognome")
        if not card.age.strip():
            missing.append("età")
        if not card.sex.strip():
            missing.append("sesso")
        if not allergies_addressed:
            missing.append("allergie")
        if not previous_conditions_addressed:
            missing.append("patologie pregresse")
        return missing

    def _merge(base: dict, update: dict) -> dict:
        for k, v in update.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = _merge(base[k], v)
            elif v not in (None, "", []):
                base[k] = v
        return base

    # L'LLM a volte non rispetta lo schema richiesto per le liste (osservato in
    # test reale: ha restituito [{"name": "penicillina"}] invece di ["penicillina"],
    # che senza questo controllo mandava in crash la validazione di PatientCard).
    # Normalizziamo ogni elemento a stringa prima di fidarcene.
    def _sanitize_string_list(value):
        if not isinstance(value, list):
            return value
        cleaned = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    cleaned.append(item)
            elif isinstance(item, dict):
                text = item.get("name") or item.get("nome") or item.get("value") or next(iter(item.values()), None)
                if text:
                    cleaned.append(str(text))
            elif item is not None:
                cleaned.append(str(item))
        return cleaned

    # Rete di sicurezza indipendente dall'LLM (_mentions, a livello di modulo):
    # se il messaggio contiene una di queste parole chiave, l'argomento e' stato
    # quantomeno toccato - non sostituisce l'estrazione del contenuto (quella
    # resta all'LLM), serve solo a confermare il flag "addressed" anche quando
    # il modello lo sottovaluta in una frase composta (osservato in test reale:
    # "e' maschio e non ha allergie" -> l'LLM ha colto "maschio" ma non "non ha
    # allergie" nello stesso messaggio).
    ALLERGY_KEYWORDS = ["allerg"]  # allergia/allergie/allergico/allergica
    CONDITION_KEYWORDS = ["patolog", "pregress", "malatt"]  # patologia/e, pregressa/e, malattia/e

    CONFIRM_REQUEST = "Confermi i dati? Altrimenti indicare cosa correggere."

    def _reply_for(card: PatientCard, allergies_addressed: bool, previous_conditions_addressed: bool) -> str:
        """Scheda aggiornata + cosa manca, oppure la richiesta di conferma se e' completa."""
        missing = _missing_fields(card, allergies_addressed, previous_conditions_addressed)
        scheda = _format_card(card, allergies_addressed, previous_conditions_addressed)
        if missing:
            return f"{scheda}\n\nMancano: {', '.join(missing)}."
        return f"{scheda}\n\n{CONFIRM_REQUEST}"

    # 1. Stato attuale (normalizzata anche la scheda che arriva dal database)
    current_card: PatientCard = _normalize_card(state.patient_card)

    # Primo passaggio, appena arrivati da read_db (senza pausa, vedi graph.py):
    # l'operatore non ha ancora scritto nulla dopo il codice fiscale, quindi
    # nessuna chiamata al modello - si mostra la scheda (vuota per un paziente
    # nuovo, quella del database per uno gia' registrato) e cosa manca, oppure
    # si chiede subito la conferma se e' gia' completa.
    if not state.intake_card_shown:
        reply = _reply_for(current_card, state.allergies_addressed, state.previous_conditions_addressed)
        print("🪪 INTAKE → scheda mostrata (primo passaggio, nessuna chiamata al modello)")
        await cl.Message(content=reply, author=Authors.INTAKE).send()
        return {
            "patient_card":      current_card.model_dump(),
            "triage_history":    [AIMessage(content=reply)],
            "general_history":   [AIMessage(content=reply)],
            "intake_card_shown": True,
            "next_step":         "intake",
        }

    # La scheda era gia' completa al turno prima: l'operatore ha davanti la
    # richiesta di conferma, e questo messaggio e' la sua risposta.
    awaiting_confirmation = not _missing_fields(
        current_card, state.allergies_addressed, state.previous_conditions_addressed
    )
    user_msg = state.triage_history[-1].content if state.triage_history else ""
    allergies_mentioned = _mentions(user_msg, ALLERGY_KEYWORDS)
    previous_conditions_mentioned = _mentions(user_msg, CONDITION_KEYWORDS)

    # 2. Chiamata LLM (Step collassato "sto pensando...", stesso pattern di read_db_node)
    prompt = INTAKE_PROMPT.format(
        patient_card=current_card.model_dump_json(),
        allergies_addressed=state.allergies_addressed,
        previous_conditions_addressed=state.previous_conditions_addressed,
        awaiting_confirmation=awaiting_confirmation,
        user_input=user_msg,
    )
    async with cl.Step(name="Analisi dati anagrafici", type="tool", default_open=False, show_input="text") as step:
        step.input = user_msg
        # stream_response e' sincrona (bloccante): chiamata cosi', dentro una
        # funzione async, bloccherebbe l'INTERO ciclo di eventi di Chainlit
        # per tutta la durata della chiamata all'LLM - impercettibile con
        # Groq (pochi secondi), ma con un modello locale lento (Ollama)
        # l'app sembra completamente ferma (osservato in test reale). asyncio.
        # to_thread la sposta su un thread separato senza bloccare il resto.
        content = await asyncio.to_thread(stream_response, prompt)
        step.output = content

    # 3. Parsing + merge
    # Campi che il modello puo' aggiornare qui: SOLO l'anagrafica. Il codice
    # fiscale (validato da read_db) e i sintomi (del revisore) restano fuori -
    # prima qualunque chiave restituita finiva nella scheda (verificato con una
    # prova: un codice fiscale scritto dal modello sostituiva quello vero).
    EDITABLE_FIELDS = ("first_name", "last_name", "age", "sex", "allergies", "previous_conditions")

    try:
        data = extract_json(content)
        extracted = data.get("updated_card")
        # JSON valido ma con "updated_card" nullo o scritto come testo: come
        # una risposta illeggibile (nessun aggiornamento), invece di mandare
        # in errore il nodo (verificato con una prova).
        if not isinstance(extracted, dict):
            extracted = {}
        extracted = {k: v for k, v in extracted.items() if k in EDITABLE_FIELDS}
        if "allergies" in extracted:
            extracted["allergies"] = _sanitize_string_list(as_list(extracted["allergies"]))
        if "previous_conditions" in extracted:
            extracted["previous_conditions"] = _sanitize_string_list(as_list(extracted["previous_conditions"]))
        llm_reply: str = data.get("message_to_user", "")
        # L'LLM a volte "dimentica" lo stato gia' true quando il messaggio corrente
        # non tocca l'argomento (osservato in test reale) - una volta true, Python
        # non lo lascia piu' tornare false qualunque cosa dica il modello. Idem se
        # la parola chiave e' presente nel messaggio ma l'LLM non l'ha colta.
        allergies_addressed = state.allergies_addressed or bool(data.get("allergies_addressed", False)) or allergies_mentioned
        previous_conditions_addressed = state.previous_conditions_addressed or bool(data.get("previous_conditions_addressed", False)) or previous_conditions_mentioned
        # "conferma" conta solo se era davvero stata chiesta (vedi sopra).
        confirmed_by_llm = awaiting_confirmation and is_yes(data.get("conferma"))
        to_remove = {
            "allergies": _sanitize_string_list(as_list(data.get("allergies_to_remove"))),
            "previous_conditions": _sanitize_string_list(as_list(data.get("previous_conditions_to_remove"))),
        }
    except json.JSONDecodeError:
        extracted = {}
        llm_reply = ""
        allergies_addressed = state.allergies_addressed or allergies_mentioned
        previous_conditions_addressed = state.previous_conditions_addressed or previous_conditions_mentioned
        confirmed_by_llm = False
        to_remove = {"allergies": [], "previous_conditions": []}

    # Le liste si accumulano tra turni invece di sostituirsi (a differenza dei campi
    # scalari come l'eta', dove l'ultimo valore detto e' la correzione giusta): se
    # il paziente cita un'allergia in un turno e un'altra in un turno successivo,
    # non vogliamo perdere la prima (osservato in test reale senza questo fix).
    for list_field in ("allergies", "previous_conditions"):
        new_items = extracted.get(list_field)
        if isinstance(new_items, list) and new_items:
            existing_items = getattr(current_card, list_field)
            # Senza maiuscole/spazi ai lati: "Penicillina" e "penicillina" sono
            # la stessa voce, non due.
            seen = {str(x).strip().lower() for x in existing_items}
            added = []
            for x in new_items:
                key = str(x).strip().lower()
                if key not in seen:
                    seen.add(key)
                    added.append(x)
            extracted[list_field] = existing_items + added

    merged_dict = _merge(current_card.model_dump(), extracted)

    # Rimozioni esplicite (correzione dell'operatore, es. "non e' allergico alla
    # penicillina, era un errore"): le liste si accumulano tra i turni, quindi
    # senza questo una voce sbagliata non si poteva piu' togliere. Confronto
    # senza maiuscole/spazi ai lati.
    for list_field, items in to_remove.items():
        remove = {str(x).strip().lower() for x in items if str(x).strip()}
        if remove and isinstance(merged_dict.get(list_field), list):
            merged_dict[list_field] = [x for x in merged_dict[list_field] if str(x).strip().lower() not in remove]
    try:
        merged_card = _normalize_card(PatientCard(**merged_dict))
    except Exception as e:
        # Ultima rete di sicurezza: se l'LLM ha restituito qualcosa che non rispetta
        # comunque lo schema (nonostante la normalizzazione sopra), non facciamo
        # crashare il nodo - manteniamo la scheda precedente e richiediamo di nuovo.
        print(f"⚠️ INTAKE: dati non validi dall'LLM, scarto questo aggiornamento: {e}")
        merged_card = current_card

    # 4. Validazione Python
    missing = _missing_fields(merged_card, allergies_addressed, previous_conditions_addressed)
    intake_complete = len(missing) == 0
    # Una conferma vale solo se in questo stesso messaggio non e' cambiato nulla:
    # "si' ma l'eta' e' 45" e' una correzione anche se il modello dice
    # "conferma" - la scheda va ristampata e riconfermata.
    card_changed = merged_card.model_dump() != current_card.model_dump()
    card_confirmed = intake_complete and confirmed_by_llm and not card_changed

    if card_confirmed:
        # Cosa scrivere dopo lo dira' il revisore (stessa scheda + conferma,
        # da fare nel suo nodo).
        reply = "Dati anagrafici confermati."
    else:
        # La scheda stampata mostra gia' cosa e' stato capito: la frase del
        # modello ("Ho capito che...", llm_reply) la ripeteva, allungando il
        # messaggio - resta solo nel log del terminale.
        reply = _reply_for(merged_card, allergies_addressed, previous_conditions_addressed)
        if llm_reply:
            print(f"   INTAKE (modello): {llm_reply}")

    # 5. Log + output
    print(f"🪪 INTAKE → completo={intake_complete} | confermata={card_confirmed} | mancanti={missing}")
    print(f"   Card: {merged_card.model_dump_json()}")
    await cl.Message(content=reply, author=Authors.INTAKE).send()

    return {
        "patient_card":    merged_card.model_dump(),
        "triage_history":  [AIMessage(content=reply)],
        "general_history": [AIMessage(content=reply)],
        "allergies_addressed": allergies_addressed,
        "previous_conditions_addressed": previous_conditions_addressed,
        "card_confirmed": card_confirmed,
        "next_step": "reviewer" if card_confirmed else "intake",
    }


# Nodo del revisore
async def reviewer_node(state: MedicalState):
    """Il modello estrae i dati del sintomo → Python valida → Python decide se continuare.

    A differenza di intake_node, qui l'LLM non deve toccare i campi anagrafici
    (gia' raccolti e bloccati da intake_node): l'estrazione prende quindi SOLO
    la chiave "symptom" dalla risposta del modello - anche se il prompt gli
    chiede di non includere altro, non ci fidiamo solo dell'istruzione testuale,
    lo garantiamo anche lato codice ignorando qualunque altra chiave restituita.
    """

    # Lista (non insieme): l'ordine serve nel messaggio all'operatore, e con un
    # insieme cambiava a ogni avvio.
    VALID_INTENSITY_VALUES = ["lieve", "moderata", "forte", "insopportabile"]

    # Rete di sicurezza indipendente dal prompt: osservato in test reale che con
    # un messaggio breve tipo "Ho mal di testa" (senza intensita'/durata) l'LLM
    # a volte inventa comunque questi due campi copiandoli dagli esempi dentro
    # il prompt (es. "forte"/"3 ore") - istruire il prompt a non farlo non e'
    # bastato (fallito in 4/4 test). Se il messaggio dell'utente non contiene
    # nessuna parola plausibilmente legata a intensita'/durata, scartiamo il
    # valore estratto invece di fidarcene.
    INTENSITY_KEYWORDS = ["liev", "legger", "modest", "moderat", "fort", "intens", "insopportabil", "grave", "acut"]
    # Espressione regolare a parole intere (non sottostringhe): prima era una
    # lista di pezzi di parola senza "stamattina", "stasera", "anno" e con
    # " ora" preceduto da uno spazio, quindi "da stamattina" o "da un'ora"
    # (proprio gli esempi B ed F di REVIEWER_PROMPT) venivano scartati e il
    # sistema richiedeva una durata gia' data (verificato con una prova).
    DURATION_PATTERN = re.compile(
        r"\b(giorn\w*|settiman\w*|minut\w*|mes[ei]|or[ae]|ann[oi]|\d+\s*h|"
        r"stanotte|stamattina|stamani|stasera|stamane|ieri|oggi|adesso|poco|"
        r"mattina|pomeriggio|sera|notte|da quando)\b",
        re.IGNORECASE,
    )

    def _is_complete(s: dict) -> bool:
        return s["intensity"].strip().lower() in VALID_INTENSITY_VALUES and bool(s["duration"].strip())

    # Rete di sicurezza per il caso con PIU' sintomi in scheda: il modello puo'
    # restituire un match esatto sulla "description" di un sintomo diverso da
    # quello a cui il messaggio si riferisce davvero (osservato in test reale:
    # "la vista sfocata e' lieve", che nomina esplicitamente il sintomo giusto,
    # ha comunque aggiornato "mal di testa" lasciando "vista sfocata" vuoto -
    # il sistema e' rimasto bloccato a richiedere la stessa informazione).
    # Se il sintomo bersaglio non e' l'UNICO incompleto in scheda, pretendiamo
    # un riscontro testuale prima di fidarci; se e' l'unico incompleto, un
    # riferimento implicito ("e' un dolore forte, ce l'ho da 2 giorni" senza
    # rinominare il sintomo) resta valido, come gia' prima di questo fix.
    def _symptom_mentioned(description: str, text_lower: str) -> bool:
        words = [w for w in re.findall(r"\w+", description.lower()) if len(w) >= 4]
        if not words:
            return True  # descrizione troppo corta per un controllo affidabile
        return any(w in text_lower for w in words)

    # Solo i sintomi: nome ed eta' li garantisce gia' intake_node (confermati).
    def _missing_fields(card: PatientCard) -> list[str]:
        missing = []
        if not card.symptom.symptoms:
            missing.append("almeno un sintomo")
        for s in card.symptom.symptoms:
            if s.intensity.strip().lower() not in VALID_INTENSITY_VALUES:
                missing.append(f'intensità di "{s.description}"')
            if not s.duration.strip():
                missing.append(f'durata di "{s.description}"')
        return missing

    CONFIRM_REQUEST = "Confermi i dati? Altrimenti indicare cosa correggere."

    def _reply_for(card: PatientCard) -> str:
        """Sintomi aggiornati + cosa manca, oppure la richiesta di conferma."""
        missing = _missing_fields(card)
        if not card.symptom.symptoms:
            return "Descrivere i sintomi: natura del disturbo, intensità e durata."
        sintomi = _format_symptoms(card)
        if missing:
            reply = f"{sintomi}\n\nMancano: {', '.join(missing)}."
            if any(m.startswith("intensità") for m in missing):
                reply += f"\nIntensità: {', '.join(VALID_INTENSITY_VALUES[:-1])} o {VALID_INTENSITY_VALUES[-1]}."
            return reply
        return f"{sintomi}\n\n{CONFIRM_REQUEST}"

    # 1. Stato attuale
    current_card: PatientCard = state.patient_card

    # Primo passaggio, appena confermata l'anagrafica (senza pausa, vedi
    # graph.py): l'operatore non ha ancora scritto nulla, quindi nessuna
    # chiamata al modello - si chiedono i sintomi.
    if not state.reviewer_card_shown:
        reply = _reply_for(current_card)
        print("🧐 REVIEWER → richiesta sintomi (primo passaggio, nessuna chiamata al modello)")
        await cl.Message(content=reply, author=Authors.REVIEWER).send()
        return {
            "triage_history":      [AIMessage(content=reply)],
            "general_history":     [AIMessage(content=reply)],
            "reviewer_card_shown": True,
            "next_step":           "reviewer",
        }

    # Sintomi gia' completi al turno prima: l'operatore ha davanti la richiesta
    # di conferma, e questo messaggio e' la sua risposta.
    awaiting_confirmation = not _missing_fields(current_card)
    user_msg = state.triage_history[-1].content if state.triage_history else ""

    # 2. Chiamata LLM (Step collassato "sto pensando...", stesso pattern di read_db/intake)
    prompt = REVIEWER_PROMPT.format(
        patient_card=current_card.model_dump_json(indent=2),
        awaiting_confirmation=awaiting_confirmation,
        user_input=user_msg
    )
    async with cl.Step(name="Analisi sintomi", type="tool", default_open=False, show_input="text") as step:
        step.input = user_msg
        # Vedi commento su asyncio.to_thread in intake_node poco sopra -
        # stessa identica ragione.
        content = await asyncio.to_thread(stream_response, prompt)
        step.output = content

    # 3. Parsing (solo il sintomo: l'anagrafica resta di competenza di intake_node)
    try:
        data = extract_json(content)
        # Ogni livello puo' arrivare nullo o come testo invece che come oggetto:
        # nessun aggiornamento, invece di mandare in errore il nodo (verificato).
        updated_card = data.get("updated_card")
        symptom = updated_card.get("symptom") if isinstance(updated_card, dict) else None
        extracted_list = symptom.get("symptoms") if isinstance(symptom, dict) else None
        if not isinstance(extracted_list, list):
            extracted_list = []
        llm_reply: str = data.get("message_to_user", "")
        # "conferma" conta solo se era davvero stata chiesta (vedi sopra).
        confirmed_by_llm = awaiting_confirmation and is_yes(data.get("conferma"))
        to_remove = as_list(data.get("symptoms_to_remove"))
    except json.JSONDecodeError:
        extracted_list = []
        llm_reply = ""
        confirmed_by_llm = False
        to_remove = []

    # 4. Merge sintomo-per-sintomo: un elemento estratto aggiorna un sintomo
    # esistente se la sua "description" coincide (case-insensitive) con uno già
    # in scheda - il prompt istruisce l'LLM a riusare la stringa esistente
    # verbatim per questo scopo (vedi REVIEWER_PROMPT) - altrimenti diventa un
    # sintomo nuovo. Lavoriamo su dict, non sui modelli Pydantic, per semplicita'.
    symptoms = [s.model_dump() for s in current_card.symptom.symptoms]
    incomplete_before = [s["description"].strip().lower() for s in symptoms if not _is_complete(s)]
    user_msg_lower = user_msg.lower()

    for item in extracted_list:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description", "")).strip()
        if not desc:
            continue  # senza descrizione non c'e' modo di associarlo a un sintomo

        intensity = str(item.get("intensity", "")).strip()
        duration = str(item.get("duration", "")).strip()
        # 'trigger' e' testo libero (circostanze che scatenano/aggravano il
        # sintomo, es. "peggiora in piedi") - a differenza di intensity/duration
        # non ha un vocabolario fisso di parole chiave su cui costruire una rete
        # di sicurezza affidabile (i modi di dire sono troppo vari), quindi qui
        # ci affidiamo alla regola anti-invenzione nel prompt (REVIEWER_PROMPT,
        # regola 9) senza un doppio controllo lato Python, come gia' avviene per
        # 'description'.
        trigger = str(item.get("trigger", "")).strip()
        # Stessa logica di 'trigger' (testo libero, regola anti-invenzione nel prompt).
        characteristics = str(item.get("characteristics", "")).strip()

        # Stessa normalizzazione/rete di sicurezza di prima, applicata per sintomo.
        if intensity.lower() == "moderato":
            intensity = "moderata"
        if intensity and not _mentions(user_msg, INTENSITY_KEYWORDS):
            print(f"⚠️ REVIEWER: 'intensity' scartata per '{desc}', nessun riscontro nel messaggio: {intensity!r}")
            intensity = ""
        if duration and not DURATION_PATTERN.search(user_msg):
            print(f"⚠️ REVIEWER: 'duration' scartata per '{desc}', nessun riscontro nel messaggio: {duration!r}")
            duration = ""

        existing = next((s for s in symptoms if s["description"].strip().lower() == desc.lower()), None)
        if existing:
            # Riferimento implicito valido SOLO se questo e' l'unico sintomo
            # ancora incompleto in scheda (nessun'altra ambiguita' possibile) -
            # altrimenti pretendiamo che il messaggio nomini davvero questo
            # sintomo, per non rischiare di aggiornare quello sbagliato.
            # Vale anche quando in scheda c'e' UN SOLO sintomo: durante la
            # conferma i sintomi sono tutti completi, e prima una correzione
            # come "no, e' moderata" veniva scartata in silenzio (verificato).
            is_only_incomplete = incomplete_before == [desc.lower()]
            is_only_symptom = len(current_card.symptom.symptoms) == 1
            if not (is_only_incomplete or is_only_symptom) and not _symptom_mentioned(desc, user_msg_lower):
                print(f"⚠️ REVIEWER: aggiornamento per '{desc}' scartato, il messaggio non lo nomina e ci sono altri sintomi in scheda")
                continue
            if intensity:
                existing["intensity"] = intensity
            if duration:
                existing["duration"] = duration
            if trigger:
                existing["trigger"] = trigger
            if characteristics:
                existing["characteristics"] = characteristics
        else:
            symptoms.append({"description": desc, "intensity": intensity, "duration": duration,
                             "trigger": trigger, "characteristics": characteristics})

    # Rimozioni esplicite (correzione dell'operatore, es. "la nausea no, era un
    # errore"): senza, un sintomo sbagliato non si poteva piu' togliere.
    # Il modello a volte scrive la voce come oggetto ({"description": "nausea"})
    # invece che come testo (osservato in prova reale): si prende il testo.
    remove = set()
    for x in to_remove:
        if isinstance(x, dict):
            x = x.get("description") or next(iter(x.values()), "")
        if str(x).strip():
            remove.add(str(x).strip().lower())
    if remove:
        symptoms = [s for s in symptoms if s["description"].strip().lower() not in remove]

    merged_dict = current_card.model_dump()
    merged_dict["symptom"]["symptoms"] = symptoms
    try:
        merged_card = PatientCard(**merged_dict)
    except Exception as e:
        # Stessa rete di sicurezza di intake_node: se l'LLM restituisce qualcosa
        # che non rispetta lo schema, non crashiamo - teniamo la scheda precedente.
        print(f"⚠️ REVIEWER: dati non validi dall'LLM, scarto questo aggiornamento: {e}")
        merged_card = current_card

    # 5. Validazione Python
    missing = _missing_fields(merged_card)
    # Come in intake_node: una conferma vale solo se in questo stesso messaggio
    # non e' cambiato nulla ("si' ma la febbre e' da ieri" e' una correzione).
    symptoms_changed = merged_card.symptom.symptoms != current_card.symptom.symptoms
    triage_complete = not missing and confirmed_by_llm and not symptoms_changed

    if triage_complete:
        reply = "Dati clinici confermati."
    else:
        # I sintomi stampati mostrano gia' cosa e' stato capito: la frase del
        # modello ("Ho capito che...") resta solo nel log del terminale.
        reply = _reply_for(merged_card)
        if llm_reply:
            print(f"   REVIEWER (modello): {llm_reply}")

    # 6. Log + output
    print(f"🧐 REVIEWER → confermato={triage_complete} | mancanti={missing}")
    print(f"   Card: {merged_card.model_dump_json()}")
    await cl.Message(content=reply, author=Authors.REVIEWER).send()

    return {
        "patient_card":    merged_card.model_dump(),
        "triage_history":  [AIMessage(content=reply)],
        "general_history": [AIMessage(content=reply)],
        "triage_complete": triage_complete,
        "symptoms_confirmed": triage_complete,
        "next_step": "photography" if triage_complete else "reviewer",
    }


# Riconosce un rifiuto della foto anche con formulazioni diverse dal solo "no"
# esatto (osservato altrove nel progetto: un confronto esatto sull'intero
# messaggio e' troppo fragile, es. "no grazie non ho foto" non veniva
# riconosciuto) - ancorato all'inizio del messaggio per evitare falsi positivi
# su parole comuni che contengono "no" (es. "sono", "buono").
NO_PHOTO_PATTERN = re.compile(
    r"^(no|nessuna|niente|non\s+ho|non\s+serve|non\s+c['’]?\s*[eè]|skip|salta|prosegui|procedi|avanti|senza)\b"
)

PHOTO_REQUEST = (
    "È disponibile una foto della zona interessata (ferita, gonfiore, eruzione cutanea…)? "
    "Allegarla, oppure scrivere \"no\" per proseguire senza foto."
)

# Groq accetta immagini in base64 fino a circa 4 MB: sopra, la chiamata al
# modello di visione fallisce (una foto scattata col telefono li supera
# spesso). Margine sotto il limite reale.
MAX_IMAGE_BASE64_BYTES = 3_500_000
# Lato lungo delle copie ridotte, dal piu' grande al piu' piccolo: si scende
# solo finche' serve, per non perdere dettaglio utile all'analisi.
RESIZE_STEPS = (2048, 1600, 1280, 1024)
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _prepare_image(image_path: str) -> tuple[str, str] | None:
    """(base64, tipo MIME) dell'immagine da mandare al modello di visione, o
    None se il file non si apre.

    Il file originale non viene mai modificato. Se e' gia' entro il limite e
    in un formato supportato parte cosi' com'e', con il suo tipo vero (prima
    era sempre dichiarato JPEG, anche per un PNG). Solo se e' troppo grande
    (o in un formato non supportato) se ne manda una COPIA ridotta in JPEG,
    con il lato lungo il piu' grande possibile entro il limite.
    """
    try:
        with open(image_path, "rb") as f:
            raw = f.read()
    except OSError:
        return None

    mime = mimetypes.guess_type(image_path)[0] or ""
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            mime = Image.MIME.get(probe.format, mime)
    except Exception:
        return None  # non e' un'immagine leggibile

    encoded = base64.b64encode(raw).decode("utf-8")
    if mime in SUPPORTED_IMAGE_TYPES and len(encoded) <= MAX_IMAGE_BASE64_BYTES:
        return encoded, mime

    with Image.open(io.BytesIO(raw)) as original:
        # Rotazione salvata nei metadati (tipica delle foto da telefono):
        # applicata alla copia, cosi' il modello vede la foto dritta.
        img = ImageOps.exif_transpose(original).convert("RGB")
    for side in RESIZE_STEPS:
        copy = img.copy()
        copy.thumbnail((side, side))
        buffer = io.BytesIO()
        copy.save(buffer, format="JPEG", quality=90)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        if len(encoded) <= MAX_IMAGE_BASE64_BYTES:
            print(f"📸 PHOTOGRAPHY: foto ridotta per l'invio ({img.width}x{img.height} -> {copy.width}x{copy.height}), originale invariato")
            return encoded, "image/jpeg"
    return encoded, "image/jpeg"  # ultima riduzione, anche se ancora grande


def _without_photo(card: PatientCard) -> dict:
    """Scheda senza foto: dopo un'analisi non riuscita o non valutabile la foto
    va tolta, altrimenti al messaggio successivo verrebbe analizzata di nuovo
    (o arriverebbe agli specialisti come foto senza descrizione)."""
    updated = card.model_dump()
    updated["symptom"]["photo"] = None
    return updated


# Nodo per l'analisi dell'immagine del danno
async def photography_node(state: MedicalState):
    """Compito puramente osservativo: descrive cosa mostra la foto (tipo di
    lesione, descrizione clinica), senza esprimere un giudizio di gravita' -
    quella valutazione richiede il quadro clinico completo ed e' compito dei
    nodi successivi (supervisore/specialisti/primario), non di chi vede solo
    un'immagine isolata."""

    last_user = state.triage_history[-1] if state.triage_history else None
    ultimo_testo = last_user.content.strip().lower() if last_user and isinstance(last_user, HumanMessage) else ""

    # 1. Foto presente nello stato → analizza (controllo PRIMA del rifiuto testuale:
    # una foto davvero allegata e' un segnale inequivocabile, non deve essere
    # scartata solo perche' la didascalia che la accompagna inizia per caso con
    # una parola tipo "no" - es. "No, non è preoccupante ma eccola comunque",
    # osservato in test reale). Vale anche al primo passaggio, se la foto era
    # gia' stata allegata prima.
    photo: PhotoAnalysis | None = state.patient_card.symptom.photo
    if photo and photo.photo_url:
        image_path = photo.photo_url
        print(f"📸 PHOTOGRAPHY: analisi immagine → {image_path}")

        prepared = _prepare_image(image_path)
        if not prepared:
            msg = "Impossibile aprire l'immagine. Si procede senza foto."
            await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
            return {"patient_card": _without_photo(state.patient_card), "general_history": [AIMessage(content=msg)],
                    "photo_request_shown": True, "next_step": "supervisor"}
        base64_image, mime = prepared

        messages = [
            SystemMessage(content=PHOTO_PROMPT),
            HumanMessage(content=[
                {"type": "text", "text": "Analizza questa immagine clinica e produci il JSON richiesto."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64_image}"}},
            ]),
        ]

        async with cl.Step(name="Analisi foto", type="tool", default_open=False, show_input="text") as step:
            step.input = image_path
            try:
                # Stessa ragione di asyncio.to_thread altrove in questo file:
                # .invoke() e' sincrona/bloccante, non va chiamata direttamente
                # dentro una funzione async. call_with_retry: nuovi tentativi
                # dopo un errore temporaneo dell'API (vedi common.py).
                response = await asyncio.to_thread(call_with_retry, llm_vision.invoke, messages)
                step.output = response.content
            except Exception as e:
                step.output = f"Errore durante la chiamata al modello di visione: {e}"
                print(f"📸 PHOTOGRAPHY: errore chiamata modello → {e}")
                msg = "Errore durante l'analisi della foto. Si procede senza foto."
                await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
                return {"patient_card": _without_photo(state.patient_card), "general_history": [AIMessage(content=msg)],
                        "photo_request_shown": True, "next_step": "supervisor"}

        try:
            # extract_json gestisce anche i modelli "thinking" (come quello di
            # visione attuale) che antepongono al JSON un blocco <think>...</think>
            # (vedi src/llm/calls.py).
            clinical_data = extract_json(response.content)

            tipo  = str(clinical_data.get("lesion_type", "")).strip()
            descr = str(clinical_data.get("description", "")).strip()

            # Foto non chiara o senza lesioni (vedi PHOTO_PROMPT): se ne chiede
            # un'altra invece di proseguire come se l'analisi fosse riuscita.
            if "NON VALUTABILE" in f"{tipo} {descr}".upper() or not (tipo or descr):
                print("📸 PHOTOGRAPHY → foto non valutabile")
                msg = "Foto non valutabile: allegarne un'altra oppure scrivere \"no\" per proseguire senza foto."
                await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
                return {
                    "patient_card":        _without_photo(state.patient_card),
                    "general_history":     [AIMessage(content=msg)],
                    "triage_history":      [AIMessage(content=msg)],
                    "photo_request_shown": True,
                    "next_step":           "photography",
                }

            # Rete di sicurezza: validiamo tramite il modello Pydantic prima di
            # salvare, come gia' fatto per intake/reviewer - se il modello di
            # visione restituisce qualcosa fuori schema, non ci fidiamo alla cieca.
            photo_analysis = PhotoAnalysis(photo_url=image_path, description=descr, injury_type=tipo)

            updated_card = state.patient_card.model_dump()
            updated_card["symptom"]["photo"] = photo_analysis.model_dump()
            print(f"📸 PHOTOGRAPHY → {tipo}")
            print(f"   Card: {json.dumps(updated_card, ensure_ascii=False)}")
            # Stesso stile delle schede di intake/reviewer. Si mostra anche la
            # descrizione, non solo il tipo: e' quello che il modello ha
            # davvero osservato (margini, colore, sanguinamento, ...).
            riepilogo = "**Foto**\n" + " · ".join(
                part for part in (f"**Tipo** {tipo}" if tipo else "", f"**Descrizione** {descr}" if descr else "") if part
            )
            await cl.Message(content=riepilogo, author=Authors.PHOTOGRAPHY).send()

            return {
                "patient_card":        updated_card,
                "general_history":     [AIMessage(content=f"Foto analizzata: {tipo}. {descr}")],
                "photo_request_shown": True,
                "next_step":           "supervisor",
            }

        except Exception as e:
            # JSON illeggibile, errore di validazione di PhotoAnalysis o
            # qualunque altro imprevisto nella lettura della risposta.
            msg = "Errore durante l'analisi della foto. Si procede senza foto."
            print(f"📸 PHOTOGRAPHY: errore nella risposta → {e}")
            await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
            return {"patient_card": _without_photo(state.patient_card), "general_history": [AIMessage(content=msg)],
                    "photo_request_shown": True, "next_step": "supervisor"}

    # 2. Primo passaggio, appena confermati i sintomi (senza pausa, vedi
    # graph.py): l'operatore non ha ancora risposto, si chiede la foto.
    if not state.photo_request_shown:
        print("📸 PHOTOGRAPHY → richiesta foto (primo passaggio)")
        await cl.Message(content=PHOTO_REQUEST, author=Authors.PHOTOGRAPHY).send()
        return {
            "general_history":     [AIMessage(content=PHOTO_REQUEST)],
            "triage_history":      [AIMessage(content=PHOTO_REQUEST)],
            "photo_request_shown": True,
            "next_step":           "photography",
        }

    # 3. Nessuna foto allegata: l'operatore ha rifiutato esplicitamente → salta
    if NO_PHOTO_PATTERN.match(ultimo_testo):
        msg = "Nessuna foto: si procede con la sola descrizione dei sintomi."
        await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
        return {
            "general_history": [AIMessage(content=msg)],
            "next_step": "supervisor",
        }

    # 4. Nessuna foto e nessun rifiuto → si richiede
    await cl.Message(content=PHOTO_REQUEST, author=Authors.PHOTOGRAPHY).send()
    return {
        "general_history": [AIMessage(content=PHOTO_REQUEST)],
        "triage_history":  [AIMessage(content=PHOTO_REQUEST)],
        "next_step": "photography",  # user leggerà questo e tornerà qui
    }
