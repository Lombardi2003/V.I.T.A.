# Nodi della fase di valutazione clinica: smistamento (supervisor), consulti
# specialistici (specialist_node + i 10 wrapper), sintesi finale (primario).
import json

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState, RoundTableEntry, SpecialistReport, FinalDiagnosis
from .prompts import SUPERVISOR_PROMPT, SPECIALIST_PROMPT, PRIMARY_PROMPT, ALL_SPECIALISTS
from .common import stream_response, llm_specialist
from .authors import Authors

# Numero massimo di giri completi del tavolo prima che chi resta sia
# obbligato a depositare la diagnosi - garantisce che si arrivi sempre al
# primario, anche nel caso peggiore di una discussione che non converge.
MAX_ROUNDS = 3


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


def _format_round_table(entries: list[RoundTableEntry]) -> str:
    """Rende leggibile la discussione finora per il prompt dello specialista
    di turno - ognuno vede l'intera trascrizione, non solo l'ultimo scambio."""
    if not entries:
        return "Nessun intervento precedente - sei il primo a parlare."
    righe = []
    for e in entries:
        chi_parla = SPECIALIST_DISPLAY_NAMES.get(e.author, e.author)
        destinatario = SPECIALIST_DISPLAY_NAMES.get(e.to, e.to) if e.to else "tutti"
        righe.append(f"{chi_parla} (a {destinatario}): {e.content}")
    return "\n".join(righe)


async def specialist_node(state: MedicalState, role: str):
    """Un turno di uno specialista al tavolo: legge cartella clinica, foto e
    l'intera discussione finora, poi sceglie se intervenire (domanda/obiezione/
    commento) o depositare la sua diagnosi finale ed uscire dal giro. Il router
    (graph.py) decide chi parla dopo - questo nodo non lo decide da solo."""
    display_name = SPECIALIST_DISPLAY_NAMES.get(role, role)
    author = getattr(Authors, role.upper(), Authors.SYSTEM)

    card_str = state.patient_card.model_dump_json()
    table_text = _format_round_table(state.round_table)
    finalizzati = [SPECIALIST_DISPLAY_NAMES.get(r, r) for r, done in state.needed_specialists.items() if done]
    finalized_text = ", ".join(finalizzati) if finalizzati else "Nessuno ancora."

    force_final = state.round_count >= MAX_ROUNDS
    istruzione_obbligo = (
        "ATTENZIONE: il tempo per la discussione e' terminato. Questo turno DEVI "
        'usare esclusivamente "action": "finalize", basandoti su quanto discusso '
        'finora - "action": "speak" non e\' piu\' permesso.'
        if force_final else ""
    )

    prompt = SPECIALIST_PROMPT.format(
        role_display=display_name,
        role=role,
        card=card_str,
        round_table=table_text,
        finalized=finalized_text,
        istruzione_obbligo=istruzione_obbligo,
    )

    async with cl.Step(name=display_name, type="tool", default_open=False, show_input="text") as step:
        step.input = table_text
        content = stream_response(prompt, llm=llm_specialist)
        step.output = content

    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)
        action = str(data.get("action", "")).lower().strip()
    except json.JSONDecodeError:
        print(f"⚠️ {role}: errore lettura JSON, fallback su finalize")
        action = "finalize"
        data = {}

    # 1. Interviene al tavolo (solo se non e' scaduto il tempo)
    if action == "speak" and not force_final:
        raw_target = str(data.get("to") or "").strip().lower()
        target = raw_target if raw_target in ALL_SPECIALISTS else _DISPLAY_NAME_TO_ROLE.get(raw_target)
        if not target or target == role:
            target = None
        message = str(data.get("message", "")).strip()

        if not message:
            # Rete di sicurezza: un intervento vuoto non serve a nessuno -
            # il router lo richiamera' comunque al prossimo giro.
            print(f"⚠️ {role}: 'speak' senza messaggio, ignorato")
            return {}

        entry = RoundTableEntry(author=role, to=target, content=message)
        destinatario = SPECIALIST_DISPLAY_NAMES.get(target, target) if target else "tutti"
        msg_text = f"**{display_name}** (a {destinatario}): {message}"
        await cl.Message(content=msg_text, author=author).send()

        return {
            "round_table": [entry],
            "general_history": [AIMessage(content=msg_text)],
        }

    # 2. Deposita la diagnosi finale (azione scelta, o fallback/tempo scaduto)
    try:
        report = SpecialistReport(
            summary_diagnosis=data.get("summary_diagnosis", "Non determinata"),
            details=data.get("details_report", ""),
            recommended_exams=data.get("recommended_exams", []),
            urgency_level=data.get("urgency_level", "BIANCO"),
        )
    except Exception as e:
        print(f"⚠️ {role}: referto non valido, fallback su BIANCO ({e})")
        report = SpecialistReport(
            summary_diagnosis="Diagnosi non determinata",
            details="Errore nella formulazione del referto.",
        )

    checklist = dict(state.needed_specialists)
    checklist[role] = True

    # medical_reports non ha un reducer di merge (vedi state.py) - scrivere solo
    # {role: report} sostituirebbe l'INTERO dizionario, cancellando i referti
    # gia' depositati dagli altri specialisti (stesso bug gia' visto altrove in
    # questo file per patient_card, corretto qui con lo stesso pattern
    # leggi-tutto/aggiorna-un-campo/riscrivi-tutto usato per needed_specialists
    # due righe sopra).
    reports = dict(state.medical_reports)
    reports[role] = report.model_dump()

    msg_text = f"**{display_name}** ha depositato la diagnosi: {report.summary_diagnosis}"
    await cl.Message(content=msg_text, author=author).send()

    return {
        "medical_reports": reports,
        "needed_specialists": checklist,
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
    """Legge la scheda del paziente e tutti i referti specialistici depositati
    al tavolo, e li sintetizza in un'unica diagnosi finale (FinalDiagnosis).

    NOTA: per ora chief_physician->END e' un punto di osservazione temporaneo
    (vedi graph.py) - il salvataggio su DB (save_db/modify_db) non e' ancora
    ricollegato, verra' fatto in un passo successivo.
    """
    card = state.patient_card
    reports_dict = state.medical_reports

    card_str = card.model_dump_json()

    # Trasformiamo il dizionario dei referti in un testo leggibile per il prompt.
    # NOTA: Pydantic ricostruisce i valori di questo dict come veri oggetti
    # SpecialistReport (non i dict restituiti da specialist_node) perche' cosi'
    # e' tipizzato il campo in state.py - accesso ad attributo, non .get()
    # (osservato in test reale: .get() crashava il nodo con AttributeError).
    reports_text = ""
    if not reports_dict:
        reports_text = "Nessun referto specialistico generato."
    else:
        for ruolo, referto in reports_dict.items():
            nome = SPECIALIST_DISPLAY_NAMES.get(ruolo, ruolo)
            esami = ", ".join(referto.recommended_exams) or "nessuno indicato"
            reports_text += f"\n--- REFERTO {nome.upper()} ---\n"
            reports_text += f"Diagnosi: {referto.summary_diagnosis}\n"
            reports_text += f"Dettagli: {referto.details}\n"
            reports_text += f"Esami consigliati: {esami}\n"
            reports_text += f"Urgenza secondo {nome}: {referto.urgency_level}\n"

    prompt = PRIMARY_PROMPT.format(card=card_str, reports_text=reports_text)

    async with cl.Step(name="Sintesi finale", type="tool", default_open=False, show_input="text") as step:
        step.input = reports_text
        content = stream_response(prompt)
        step.output = content

    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        report_data = json.loads(clean_content)
        final = FinalDiagnosis(
            diagnosis=report_data.get("diagnosis", "Diagnosi non determinata"),
            urgency_level=report_data.get("urgency_level", "BIANCO"),
            specialists_involved=list(reports_dict.keys()),
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
            specialists_involved=list(reports_dict.keys()),
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
