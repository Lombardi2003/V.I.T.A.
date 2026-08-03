# Nodi della fase di valutazione clinica: smistamento (supervisor), consulti
# specialistici (specialist_node + i 10 wrapper), sintesi finale (primario).
import json

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState
from .prompts import SUPERVISOR_PROMPT, SPECIALIST_PROMPT, PRIMARY_PROMPT, ALL_SPECIALISTS
from .common import stream_response
from .authors import Authors


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
    "general_practitioner": "Medicina Generale",
}


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
        content = stream_response(prompt)
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

    checklist = {specialist: False for specialist in selected_specialists}
    print(f"   Checklist: {checklist}")
    return {
        "needed_specialists": checklist,
        "general_history": [AIMessage(content=msg)],
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
