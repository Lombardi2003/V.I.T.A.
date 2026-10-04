# Nodo dell'anagrafica: raccoglie e fa confermare i dati anagrafici del paziente
# (non i sintomi, quelli sono del revisore in reviewer.py).
import asyncio
import json
import re

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState, PatientCard
from .prompts import INTAKE_PROMPT
from .common import stream_response, extract_json, as_list, is_yes, _mentions
from .authors import Authors


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


def _is_minor(age: str) -> bool:
    """Eta' sotto i 18 anni, o scritta in mesi/giorni/settimane (stesso criterio
    della nota pediatrica in roundtable.py). False se l'eta' non si legge."""
    age = age.strip().lower()
    match = re.match(r"(\d{1,3})", age)
    if not match:
        return False
    return any(u in age for u in ("mes", "giorn", "settiman")) or int(match.group(1)) < 18


def _normalize_card(card: PatientCard) -> PatientCard:
    """Dati uniformi nella scheda stessa (non solo nella stampa), cosi' anche
    nel database finiscono uguali: sesso "uomo"/"donna", oppure "maschio"/
    "femmina" per un minorenne ("Sesso uomo" per un bambino di 10 anni suonava
    strano, osservato nella prova reale dell'app; se non riconosciuto resta
    com'e'), nome e cognome con l'iniziale maiuscola."""
    sex = card.sex.strip()
    for code, words in _SEX_VALUES.items():
        if sex.lower() in words:
            sex = code
    if _is_minor(card.age):
        sex = {"uomo": "maschio", "donna": "femmina"}.get(sex, sex)
    return card.model_copy(update={
        "sex": sex,
        "first_name": _capitalize_name(card.first_name),
        "last_name": _capitalize_name(card.last_name),
    })


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
