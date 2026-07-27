# Nodi di acquisizione dati dal/sul paziente: passaggio del messaggio utente,
# raccolta anagrafica, raccolta sintomi, analisi foto.
import json
import base64

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import chainlit as cl

from src.state import MedicalState, PatientCard, PhotoAnalysis
from src.prompts import INTAKE_PROMPT, REVIEWER_PROMPT, PHOTO_PROMPT
from .common import stream_response, SYSTEM_AUTHOR, llm_photography


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
            missing.append("allergie (anche 'nessuna' se non ne hai)")
        if not previous_conditions_addressed:
            missing.append("patologie pregresse (anche 'nessuna' se non ne hai)")
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

    # Rete di sicurezza indipendente dall'LLM: se il messaggio contiene una di
    # queste parole chiave, l'argomento e' stato quantomeno toccato - non sostituisce
    # l'estrazione del contenuto (quella resta all'LLM), serve solo a confermare il
    # flag "addressed" anche quando il modello lo sottovaluta in una frase composta
    # (osservato in test reale: "e' maschio e non ha allergie" -> l'LLM ha colto
    # "maschio" ma non "non ha allergie" nello stesso messaggio).
    def _mentions(text: str, keywords: list[str]) -> bool:
        lowered = text.lower()
        return any(kw in lowered for kw in keywords)

    ALLERGY_KEYWORDS = ["allerg"]  # allergia/allergie/allergico/allergica
    CONDITION_KEYWORDS = ["patolog", "pregress", "malatt"]  # patologia/e, pregressa/e, malattia/e

    # 1. Stato attuale
    current_card: PatientCard = state.patient_card
    user_msg = state.triage_history[-1].content if state.triage_history else ""
    allergies_mentioned = _mentions(user_msg, ALLERGY_KEYWORDS)
    previous_conditions_mentioned = _mentions(user_msg, CONDITION_KEYWORDS)

    # 2. Chiamata LLM
    prompt = INTAKE_PROMPT.format(
        patient_card=current_card.model_dump_json(),
        allergies_addressed=state.allergies_addressed,
        previous_conditions_addressed=state.previous_conditions_addressed,
        user_input=user_msg,
    )
    content = stream_response(prompt)

    # 3. Parsing + merge
    try:
        clean = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        extracted: dict = data.get("updated_card", {})
        if "allergies" in extracted:
            extracted["allergies"] = _sanitize_string_list(extracted["allergies"])
        if "previous_conditions" in extracted:
            extracted["previous_conditions"] = _sanitize_string_list(extracted["previous_conditions"])
        llm_reply: str = data.get("message_to_user", "")
        # L'LLM a volte "dimentica" lo stato gia' true quando il messaggio corrente
        # non tocca l'argomento (osservato in test reale) - una volta true, Python
        # non lo lascia piu' tornare false qualunque cosa dica il modello. Idem se
        # la parola chiave e' presente nel messaggio ma l'LLM non l'ha colta.
        allergies_addressed = state.allergies_addressed or bool(data.get("allergies_addressed", False)) or allergies_mentioned
        previous_conditions_addressed = state.previous_conditions_addressed or bool(data.get("previous_conditions_addressed", False)) or previous_conditions_mentioned
    except json.JSONDecodeError:
        extracted = {}
        llm_reply = ""
        allergies_addressed = state.allergies_addressed or allergies_mentioned
        previous_conditions_addressed = state.previous_conditions_addressed or previous_conditions_mentioned

    # Le liste si accumulano tra turni invece di sostituirsi (a differenza dei campi
    # scalari come l'eta', dove l'ultimo valore detto e' la correzione giusta): se
    # il paziente cita un'allergia in un turno e un'altra in un turno successivo,
    # non vogliamo perdere la prima (osservato in test reale senza questo fix).
    for list_field in ("allergies", "previous_conditions"):
        new_items = extracted.get(list_field)
        if isinstance(new_items, list) and new_items:
            existing_items = getattr(current_card, list_field)
            extracted[list_field] = existing_items + [x for x in new_items if x not in existing_items]

    merged_dict = _merge(current_card.model_dump(), extracted)
    try:
        merged_card = PatientCard(**merged_dict)
    except Exception as e:
        # Ultima rete di sicurezza: se l'LLM ha restituito qualcosa che non rispetta
        # comunque lo schema (nonostante la normalizzazione sopra), non facciamo
        # crashare il nodo - manteniamo la scheda precedente e richiediamo di nuovo.
        print(f"⚠️ INTAKE: dati non validi dall'LLM, scarto questo aggiornamento: {e}")
        merged_card = current_card

    # 4. Validazione Python
    missing = _missing_fields(merged_card, allergies_addressed, previous_conditions_addressed)
    intake_complete = len(missing) == 0

    if intake_complete:
        reply = llm_reply or "✨ Perfetto, ho tutti i dati anagrafici necessari."
    else:
        elenco = "\n".join(f"  • {campo}" for campo in missing)
        reply = f"Per completare la scheda anagrafica ho ancora bisogno di:\n{elenco}\nPuoi fornirmi queste informazioni?"

    # 5. Log + output
    print(f"🪪 INTAKE → completo={intake_complete} | mancanti={missing}")
    print(f"   Card: {merged_card.model_dump_json()}")
    await cl.Message(content=f"🪪 {reply}", author=SYSTEM_AUTHOR).send()

    return {
        "patient_card":    merged_card.model_dump(),
        "triage_history":  [AIMessage(content=reply)],
        "general_history": [AIMessage(content=reply)],
        "allergies_addressed": allergies_addressed,
        "previous_conditions_addressed": previous_conditions_addressed,
        "next_step": "reviewer" if intake_complete else "intake",
    }


# Nodo del revisore
async def reviewer_node(state: MedicalState):
    """Il modello estrae i dati → Python valida → Python decide se continuare."""

    VALID_INTENSITY_VALUES = {"lieve", "moderata", "forte", "insopportabile"}

    def _missing_fields(card: PatientCard) -> list[str]:
        missing = []
        if not card.first_name.strip():
            missing.append("nome")
        if not card.age.strip():
            missing.append("età")
        if not card.symptom.main_symptom.strip():
            missing.append("sintomo principale")
        if card.symptom.intensity.strip().lower() not in VALID_INTENSITY_VALUES:
            missing.append(f"intensità (valori: {', '.join(VALID_INTENSITY_VALUES)})")
        if not card.symptom.duration.strip():
            missing.append("durata del sintomo")
        return missing

    def _merge(base: dict, update: dict) -> dict:
        for k, v in update.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = _merge(base[k], v)
            elif v not in (None, "", []):
                base[k] = v
        return base

    # 1. Stato attuale
    current_card: PatientCard = state.patient_card
    user_msg = state.triage_history[-1].content if state.triage_history else ""

    # 2. Chiamata LLM
    prompt = REVIEWER_PROMPT.format(
        patient_card=current_card.model_dump_json(indent=2),
        user_input=user_msg
    )
    content = stream_response(prompt)
    # 3. Parsing + merge
    try:
        clean = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        extracted: dict = data.get("updated_card", {})
        llm_reply: str = data.get("message_to_user", "")
    except json.JSONDecodeError:
        extracted = {}
        llm_reply = ""

    merged_dict = _merge(current_card.model_dump(), extracted)
    merged_card = PatientCard(**merged_dict)  # ricostruisce il Pydantic model

    # 4. Validazione Python
    missing = _missing_fields(merged_card)
    triage_complete = len(missing) == 0

    if triage_complete:
        reply = llm_reply or "✨ Perfetto, ho tutti i dati necessari. Procedo con il triage."
    else:
        elenco = "\n".join(f"  • {campo}" for campo in missing)
        reply = f"Per completare la scheda ho ancora bisogno di:\n{elenco}\nPuoi fornirmi queste informazioni?"

    # 5. Log + output
    print(f"🧐 REVIEWER → completo={triage_complete} | mancanti={missing}")
    print(f"   Card: {merged_card.model_dump_json()}")
    await cl.Message(content=f"🧐 {reply}").send()

    return {
        "patient_card":    merged_card.model_dump(),
        "triage_history":  [AIMessage(content=reply)],
        "general_history": [AIMessage(content=reply)],
        "triage_complete": triage_complete,
        "next_step": "photography" if triage_complete else "reviewer",
    }


# Nodo per l'analisi dell'immagine del danno
async def photography_node(state: MedicalState):

    def encode_image(image_path: str) -> str | None:
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except FileNotFoundError:
            return None

    last_user = state.triage_history[-1] if state.triage_history else None
    ultimo_testo = last_user.content.strip().lower() if last_user and isinstance(last_user, HumanMessage) else ""

    # 1. Utente ha scritto 'no' → salta foto
    if ultimo_testo in {"no", "nessuna", "non ho", "skip"}:
        msg = "📸 Nessuna foto fornita, procedo con la sola descrizione dei sintomi."
        await cl.Message(content=msg).send()
        return {
            "general_history": [AIMessage(content=msg)],
            "next_step": "supervisor",
        }

    # 2. Foto presente nello stato → analizza
    photo: PhotoAnalysis | None = state.patient_card.symptom.photo
    if photo and photo.photo_url:
        image_path = photo.photo_url
        print(f"📸 PHOTOGRAPHY: analisi immagine → {image_path}")
        await cl.Message(content="📸 Immagine ricevuta, analisi in corso...").send()

        base64_image = encode_image(image_path)
        if not base64_image:
            msg = f"❌ Impossibile aprire l'immagine. Procedo senza foto."
            await cl.Message(content=msg).send()
            return {"general_history": [AIMessage(content=msg)], "next_step": "supervisor"}

        messages = [
            SystemMessage(content=PHOTO_PROMPT),
            HumanMessage(content=[
                {"type": "text", "text": "Analizza questa immagine clinica e produci il JSON richiesto."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
            ]),
        ]

        try:
            response = llm_photography.invoke(messages)
            clean = response.content.replace("```json", "").replace("```", "").strip()
            clinical_data = json.loads(clean)

            tipo    = clinical_data.get("lesion_type", "N/A")
            gravita = clinical_data.get("estimated_severity", "N/A")
            descr   = clinical_data.get("description", "N/A")

            print(f"📸 PHOTOGRAPHY: {tipo} | gravità {gravita}")
            await cl.Message(content=f"📸 Analisi completata: **{tipo}** — gravità stimata **{gravita}**.").send()

            updated_card = state.patient_card.model_dump()
            updated_card["symptom"]["photo"] = {
                "photo_url":    image_path,
                "description":  descr,
                "injury_type":  tipo,
            }
            return {
                "patient_card":    updated_card,
                "general_history": [AIMessage(content=f"Foto analizzata: {tipo} — gravità {gravita}. {descr}")],
                "next_step":       "supervisor",
            }

        except json.JSONDecodeError:
            msg = "❌ Errore tecnico nell'analisi della foto. Procedo con la sola descrizione."
            await cl.Message(content=msg).send()
            return {"general_history": [AIMessage(content=msg)], "next_step": "supervisor"}

        except Exception as e:
            msg = "❌ Errore durante l'elaborazione della foto. Procedo comunque."
            print(f"📸 PHOTOGRAPHY: errore generico → {e}")
            await cl.Message(content=msg).send()
            return {"general_history": [AIMessage(content=msg)], "next_step": "supervisor"}

    # 3. Nessuna foto e nessun 'no' → chiedi all'utente
    msg = (
        "📸 Se hai una foto della zona interessata (ferita, gonfiore, eruzioni, ecc.) "
        "inviala ora per una valutazione più accurata.\n"
        "Altrimenti scrivi **'no'** per continuare senza foto."
    )
    await cl.Message(content=msg).send()
    return {
        "general_history": [AIMessage(content=msg)],
        "triage_history":  [AIMessage(content=msg)],
        "next_step": "photography",  # user leggerà questo e tornerà qui
    }
