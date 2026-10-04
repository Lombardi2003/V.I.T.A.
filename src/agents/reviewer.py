# Nodo del revisore: raccoglie e fa confermare i sintomi.
import asyncio
import json
import re

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState, PatientCard
from .prompts import REVIEWER_PROMPT
from .common import stream_response, extract_json, as_list, is_yes, _mentions
from .authors import Authors


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
