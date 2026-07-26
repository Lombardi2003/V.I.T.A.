# Librerie per LLM e messaggi
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
# Import dei moduli locali
from src.state import MedicalState, PatientCard, PhotoAnalysis
from src.config import REVIEWER_PROMPT, SUPERVISOR_PROMPT, SPECIALIST_PROMPT, PRIMARY_PROMPT, PHOTO_PROMPT, ALL_SPECIALISTS
from src.database import MedicalDatabase
from src.settings import get_settings

import chainlit as cl
import re
import asyncio


def stream_response(prompt_current_card):
    full_response = ""
    for chunk in llm_agents.stream(prompt_current_card):
        content = chunk.content
        print(content, end="", flush=True)
        full_response += content
    print("\n")
    return full_response

# Altre librerie
import json, base64

# Configurazione del modello LLM
settings = get_settings()
USE_CLOUD_ACCELERATION = settings.use_cloud_acceleration
if USE_CLOUD_ACCELERATION:
    llm_agents = ChatGroq(
        temperature=0,
        model_name="llama-3.1-8b-instant",
        groq_api_key=settings.groq_api_key
    )
    llm_photography = ChatGroq(
        temperature=0,
        model_name="meta-llama/llama-4-maverick-17b-128e-instruct",
        groq_api_key=settings.groq_api_key,
        model_kwargs={"response_format": {"type": "json_object"}}
    )
else:
    llm_agents = ChatOllama(model="llama3", temperature=0)
    llm_photography = ChatOllama(model="moondream", temperature=0)

# Database
mdb = MedicalDatabase()


# Nodo per la lettura del database
SYSTEM_AUTHOR = "System"


def is_valid_fiscal_code(raw: str) -> bool:
    """Validazione minima del Codice Fiscale: 16 alfanumerici, con bypass di test '1234'."""
    return bool(re.fullmatch(r'[A-Z0-9]{16}', raw)) or raw == "1234"


async def read_db_node(state: MedicalState):
    """Legge il CF, lo valida minimamente e interroga il DB.

    Gira una sola volta per conversazione (nessun ciclo di ritorno nel grafo):
    e' il controllo "il paziente esiste gia'?" fatto all'ingresso, non un loop
    di validazione del CF - per questo i rami di errore sotto non richiedono
    di reinserire il CF, ma procedono comunque con una nuova scheda.
    """

    # 1. Estrazione input
    try:
        raw = state.general_history[-1].content.strip().upper()
    except (IndexError, AttributeError):
        msg = "⚠️ Inserisci il tuo Codice Fiscale."
        await cl.Message(content=msg, author=SYSTEM_AUTHOR).send()
        return {"next_step": "reviewer", "general_history": [AIMessage(content=msg)]}

    # 2. Validazione minima: 16 caratteri alfanumerici
    if not is_valid_fiscal_code(raw):
        msg = (
            "⚠️ Il valore inserito non sembra un Codice Fiscale valido.\n"
            "Procedo comunque creando una nuova scheda: potrai fornirmi i tuoi dati anagrafici tra poco."
        )
        await cl.Message(content=msg, author=SYSTEM_AUTHOR).send()
        return {
            "next_step": "reviewer",
            "general_history": [AIMessage(content=msg)],
        }

    # 3. Query DB (un'unica interrogazione: read_patient restituisce None se non trovato)
    # La ricerca in se' e' un passaggio interno: la mostriamo come Step collassato
    # ("sto pensando..."), non come messaggio di chat - il risultato utile per il
    # paziente arriva subito dopo, come messaggio vero.
    record = None
    db_error = None
    async with cl.Step(name="Ricerca Codice Fiscale", type="tool", default_open=False, show_input="text") as step:
        step.input = raw
        try:
            record = mdb.read_patient(raw)
            step.output = (
                f"Paziente trovato: {record.first_name} {record.last_name}"
                if record else
                "Nessun paziente trovato con questo codice fiscale"
            )
        except Exception as e:
            db_error = e
            step.output = f"Errore di connessione al database: {e}"

    if db_error:
        msg = "⚠️ Errore di connessione al database. Procedo comunque con una nuova scheda."
        await cl.Message(content=msg, author=SYSTEM_AUTHOR).send()
        print(f"READ_DB | Errore DB: {db_error}")
        return {
            "next_step":       "reviewer",
            "general_history": [AIMessage(content=msg)],
        }

    if record:
        msg = (
            f"✅ Bentornato **{record.first_name} {record.last_name}**! "
            "Ho caricato la tua scheda. Descrivimi i tuoi sintomi."
        )
        await cl.Message(content=msg, author=SYSTEM_AUTHOR).send()
        print(f"READ_DB | Paziente trovato: {raw}")
        return {
            "patient_card": {
                "fiscal_code":         raw,
                "first_name":          record.first_name,
                "last_name":           record.last_name,
                "age":                 record.age,
                "sex":                 getattr(record, "sex", ""),
                "allergies":           getattr(record, "allergies", []),
                "previous_conditions": record.previous_conditions,
            },
            "patient_exists": True,
            "next_step":      "reviewer",  # user → reviewer
            "general_history": [AIMessage(content=msg)],
        }

    msg = (
        "📋 CF non trovato nel sistema: verrà creata una nuova scheda.\n"
        "Descrivimi pure i tuoi sintomi."
    )
    await cl.Message(content=msg, author=SYSTEM_AUTHOR).send()
    print(f"READ_DB | Nuovo paziente: {raw}")
    return {
        "patient_card":    {"fiscal_code": raw},
        "patient_exists":  False,
        "next_step":       "reviewer",  # user → reviewer
        "general_history": [AIMessage(content=msg)],
    }

async def user_node(state: MedicalState):
    """Nodo di passaggio: il messaggio e' gia' nello stato (aggiunto da app.py
    prima che il grafo riprendesse) - qui non va ri-aggiunto, altrimenti si
    duplica nello storico (general_history/triage_history si concatenano con
    operator.add). NON tocchiamo next_step: resta quello impostato dal nodo precedente.
    """
    if state.triage_history and isinstance(state.triage_history[-1], HumanMessage):
        print("💬 USER: " + state.triage_history[-1].content.strip().lower())

    return {}










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

# Nodo per il salvataggio nel database
async def save_db_node(state: MedicalState):
    """ Salva o aggiorna i dati del paziente nel database. """
    print("💾 SAVE_DB: Avvio salvataggio...")

    card = state.get("patient_card", {})

    # 1. Controllo di sicurezza sul codice fiscale (Ottimo che tu lo abbia già messo!)
    if "fiscal_code" not in card or not card["fiscal_code"]:
        print("❌ SAVE_DB: Codice fiscale mancante, impossibile salvare.")
        return {}

    # 2. IL FIX: Assicuriamoci che 'previous_conditions' esista e sia una vera Lista!
    if "previous_conditions" not in card or not isinstance(card["previous_conditions"], list):
        card["previous_conditions"] = []

    # 3. Estrazione sicura della diagnosi
    diagnosi_obj = state.get("report")
    testo_diagnosi = diagnosi_obj["final_diagnosis"] if diagnosi_obj else "Nessuna diagnosi specifica"

    # 4. Ora possiamo fare l'append in totale sicurezza
    card["previous_conditions"].append(testo_diagnosi)

    # 5. Invio al database
    mdb.save_patient(card)
    print("✅ SAVE_DB: Dati salvati con successo.")
    await cl.Message(content=f"✅ I tuoi dati sono stati salvati con la diagnosi: {testo_diagnosi}").send()

    # Restituiamo la card aggiornata allo stato del grafo
    return {"patient_card": card}

# Nodo per modificare un paziente esistente nel database
async def modify_db_node(state: MedicalState):
    """ Modifica i dati di un paziente esistente nel database. """
    print("🔄 MODIFY_DB: Avvio modifica dati...")

    card = state.get("patient_card", {})

    if "fiscal_code" not in card or not card["fiscal_code"]:
        print("❌ MODIFY_DB: Codice fiscale mancante, impossibile modificare.")
        return {}

    nuova_patologia = state.get("report", {}).get("final_diagnosis", "Nessuna diagnosi specifica")

    mdb.update_patient_conditions(card, nuova_patologia)
    print("✅ MODIFY_DB: Dati modificati con successo.")
    await cl.Message(content=f"✅ I tuoi dati sono stati aggiornati con la nuova diagnosi: {nuova_patologia}").send()
    return {"patient_card": card}

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

# Nodo del supervisore
async def supervisor_node(state: MedicalState):
    """ Analizza la conversazione e decide chi deve intervenire."""
    print("🚦 SUPERVISOR: ", end="", flush=True)
    card = state.patient_card
    photo = state.get.photo_analysis
    card_str = json.dumps(card, ensure_ascii=False)
    photo_str = json.dumps(photo, ensure_ascii=False) if photo else "Nessuna foto."

    prompt = SUPERVISOR_PROMPT.format(patient_card=card_str, photo_analysis=photo_str)
    content = stream_response(prompt)
    selected_specialists = ["general_practitioner"]

    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)

        specs = data.get("specialists", [])

        clean_specs = [s.lower() for s in specs if s.lower() in ALL_SPECIALISTS]

        if clean_specs:
            selected_specialists = clean_specs

        print(f"-> Scelti: {selected_specialists}")
        await cl.Message(content=f"🚦 SUPERVISOR: ho deciso di coinvolgere: {', '.join(selected_specialists).upper()}").send()

    except json.JSONDecodeError:
        print("-> Errore lettura JSON. Fallback su Medico Generale.")

    checklist = {specialist: False for specialist in selected_specialists}
    print("Checklist specialisti necessari:", checklist)
    return {
        "needed_specialists": checklist
    }

async def specialist_node(state: MedicalState, role: str):
    print(f"\n🩺 {role.upper()}: Analisi in corso...", flush=True)

    card = state.get("patient_card", {})
    consultation = state.get("inter_consultation")
    card_str = json.dumps(card, ensure_ascii=False)

    messaggi_colleghi = ""
    if consultation:
        if consultation.get("a") == role and not consultation.get("risposta"):
            messaggi_colleghi = f"⚠️ DOMANDA DAL {consultation['da'].upper()}: '{consultation['domanda']}'.\n-> Rispondi nel campo 'details_report'."
        elif consultation.get("da") == role and consultation.get("risposta"):
            messaggi_colleghi = f"✅ RISPOSTA DAL {consultation['a'].upper()}: '{consultation['risposta']}'.\n-> Usa questa info per concludere il referto. Ora 'needs_consultation' deve essere FALSE."

    prompt = SPECIALIST_PROMPT.format(role=role, card=card_str, messaggi_colleghi=messaggi_colleghi)
    content = stream_response(prompt)

    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)

        print(f"   -> 🧠 Ragionamento: {data.get('initial_reasoning', '')}")

        needs_consultation = data.get("needs_consultation", False)
        if needs_consultation and not (consultation and consultation.get("a") == role):
            target = data.get("specialist_to_consult", "").lower().strip()
            domanda = data.get("question_for_colleague", "")

            if target and target != role:
                print(f"   -> 🔄 PAUSA: Il {role.upper()} chiede un consulto al {target.upper()}!")
                return {
                    "inter_consultation": {"da": role, "a": target, "domanda": domanda, "risposta": None},
                    "next_step": target
                }

        final_report = {
            "summary_diagnosis": data.get("summary_diagnosis", "Non determinata"),
            "details": data.get("details_report", "Nessun dettaglio"),
            "recommended_exams": data.get("recommended_exams", []),
            "urgency_level": data.get("urgency_level", "BASSO")
        }

    except Exception as e:
        print(f"   -> ❌ Errore Lettura LLM: Procedo con referto di emergenza.")
        final_report = {
            "summary_diagnosis": "Errore", "details": "Impossibile leggere i dati.",
            "recommended_exams": [], "urgency_level": "BASSO"
        }

    current_specialist = state.get("needed_specialists", {})
    current_specialist[role] = True

    next_step = "router"
    new_consultation = consultation

    if consultation:
        if consultation.get("a") == role and not consultation.get("risposta"):
            print(f"   -> ✅ Risposta formulata per il {consultation['da'].upper()}")
            new_consultation["risposta"] = final_report["details"]
            next_step = consultation["da"]
        elif consultation.get("da") == role and consultation.get("risposta"):
            print(f"   -> 🏁 {role.upper()} chiude il referto dopo il consulto.")
            new_consultation = None

    await cl.Message(content=f"✅ Referto del {role.upper()} pronto. {final_report}").send()

    return {
        "medical_reports": {role: final_report},
        "needed_specialists": current_specialist,
        "inter_consultation": new_consultation,
        "next_step": next_step
    }

# Wrapper per i nodi specifici (versione con emoji)
async def cardiologist_node(state):
    print(f"🫀 CARDIOLOGO: ", end="", flush=True)
    await cl.Message(content="🫀 CARDIOLOGO: ").send()
    return await specialist_node(state, "cardiologist")


async def neurologist_node(state):
    print(f"🧠 NEUROLOGO: ", end="", flush=True)
    await cl.Message(content="🧠 NEUROLOGO: ").send()
    return await specialist_node(state, "neurologist")


async def orthopedic_node(state):
    print(f"🦴 ORTOPEDICO: ", end="", flush=True)
    await cl.Message(content="🦴 ORTOPEDICO: ").send()
    return await specialist_node(state, "orthopedist")


async def gastroenterologist_node(state):
    print(f"🍽️ GASTROENTEROLOGO: ", end="", flush=True)
    await cl.Message(content="🍽️ GASTROENTEROLOGO: ").send()
    return await specialist_node(state, "gastroenterologist")


async def dermatologist_node(state):
    print(f"🧴 DERMATOLOGO: ", end="", flush=True)
    await cl.Message(content="🧴 DERMATOLOGO: ").send()
    return await specialist_node(state, "dermatologist")


async def pneumologist_node(state):
    print(f"🫁 PNEUMOLOGO: ", end="", flush=True)
    await cl.Message(content="🫁 PNEUMOLOGO: ").send()
    return await specialist_node(state, "pulmonologist")


async def ent_node(state):  # Otorino (Ear Nose Throat)
    print(f"👂 OTORINO: ", end="", flush=True)
    await cl.Message(content="👂 OTORINO: ").send()
    return await specialist_node(state, "ent")


async def ophthalmologist_node(state):
    print(f"👁️ OCULISTA: ", end="", flush=True)
    await cl.Message(content="👁️ OCULISTA: ").send()
    return await specialist_node(state, "ophthalmologist")


async def urologist_node(state):
    print(f"🚻 UROLOGO: ", end="", flush=True)
    await cl.Message(content="🚻 UROLOGO: ").send()
    return await specialist_node(state, "urologist")


async def general_practitioner_node(state):
    print(f"👨‍⚕️ MEDICO GENERALE: ", end="", flush=True)
    await cl.Message(content="👨‍⚕️ MEDICO GENERALE: ").send()
    return await specialist_node(state, "general_practitioner")

# Nodo del primario
async def primary_node(state: MedicalState):
    """ Analizza tutti i referti specialistici e redige il report finale. """
    print("👨‍⚕️ PRIMARIO: Analisi dei referti in corso...", flush=True)

    # 1. Recuperiamo i dati
    card = state.get("patient_card", {})
    reports_dict = state.get("medical_reports", {})

    card_str = json.dumps(card, ensure_ascii=False)

    # 2. Trasformiamo il dizionario dei referti in un testo leggibile
    reports_text = ""
    if not reports_dict:
        reports_text = "Nessun referto specialistico generato."
    else:
        for specialista, referto in reports_dict.items():
            reports_text += f"\n--- REFERTO {specialista.upper()} ---\n"
            reports_text += f"Diagnosi: {referto.get('summary_diagnosis', '')}\n"
            reports_text += f"Dettagli: {referto.get('details', '')}\n"
            reports_text += f"Urgenza: {referto.get('urgency_level', '')}\n"

    # 3. Creiamo il prompt e chiamiamo l'LLM
    prompt = PRIMARY_PROMPT.format(card=card_str, reports_text=reports_text)
    content = stream_response(prompt)

    # 4. Estraiamo il JSON come hai fatto negli altri nodi
    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        report_data = json.loads(clean_content)

        diagnosi_finale = report_data.get("final_diagnosis", "Diagnosi non determinata")
        dettagli = report_data.get("details", "")
        livello_urgenza = report_data.get("urgency_level", "BIANCO")

    except json.JSONDecodeError:
        diagnosi_finale = "Errore nella generazione della diagnosi."
        dettagli = "Errore tecnico."
        livello_urgenza = "BIANCO"

    print(f"   -> Urgenza assegnata: {livello_urgenza}")
    await cl.Message(content=f"👨‍⚕️ PRIMARIO: Diagnosi finale - {diagnosi_finale} \n Dettagli: {dettagli}\nUrgenza: {livello_urgenza}").send()
    # 5. Prepariamo un messaggio per l'utente/interfaccia
    messaggio_finale = f"Il Primario ha concluso la valutazione.\nDiagnosi: {diagnosi_finale}\nCodice: {livello_urgenza}"

    # 6. Restituiamo i dati aggiornati
    return {
        "diagnosis": diagnosi_finale, # Salviamo la stringa per il DB!
        "general_history": [AIMessage(content=messaggio_finale)],
        "next_step": "save_db"        # Mandiamo il grafo all'ultimo nodo
    }
