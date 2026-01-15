# Librerie per LLM e messaggi
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
# Import dei moduli locali
from state import MedicalState, SpecialistReport, PatientCard
from config import REVIEWER_PROMPT, SUPERVISOR_PROMPT, SPECIALIST_PROMPT, PRIMARY_PROMPT, PHOTO_PROMPT, ALL_SPECIALISTS

# Altre librerie
import json, base64

# Configurazione API Key
with open('api_key.json') as f:
    API_KEY = json.load(f)

# Configurazione del modello LLM
USE_CLOUD_ACCELERATION = True
if USE_CLOUD_ACCELERATION:
    llm_agents = ChatGroq(
        temperature=0, 
        model_name="llama-3.1-8b-instant",
        groq_api_key=API_KEY["groq_api_key"]
    )
    llm_photography = ChatGroq(
        temperature=0,
        model_name="meta-llama/llama-4-maverick-17b-128e-instruct",
        groq_api_key=API_KEY["groq_api_key"],
        model_kwargs={"response_format": {"type": "json_object"}}
    )
else:
    llm_agents = ChatOllama(model="llama3", temperature=0)
    llm_photography = ChatOllama(model="moondream", temperature=0)

# Nodo del revisore
def reviewer_node(state: MedicalState):
    """ Analizza la Patient Card e decide se sono necessarie più informazioni dall'utente. """
    print("🧐 REVIEWER: ", end="", flush=True)
    # Nel reviewer_node
    current_card = state["patient_card"]
    
    history = state.get("triage_history", [])
    if history:
        user_msg = history[-1].content
    else:
        user_msg = "Nessun messaggio utente trovato."
    card_str = json.dumps(current_card, ensure_ascii=False)  
    prompt = REVIEWER_PROMPT.format(patient_card=card_str, user_input=user_msg)    
    content = stream_response(prompt)
    
    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)
        extracted_card = data.get("updated_card", {})
        status = data.get("status", "INSUFFICIENTE").upper()
        reply = data.get("message_to_user")
        current_card.update({k: v for k, v in extracted_card.items() if v}) # aggiorna solo se c'è un valore
        
    except json.JSONDecodeError:
        status = "INSUFFICIENTE"
        reply = "Scusa, non ho capito bene. Puoi ripetere i tuoi dati?"
    
    display_reply = reply if reply else "Perfetto, raccolta dati completa ✨"
    print(f"   -> Status: {status}")
    print(f"   -> Dati attuali: {current_card}")
    print(f"   -> Risposta all'utente: {display_reply}")
    return {
        "patient_card": current_card,          
        "triage_history": [AIMessage(content=display_reply)], 
        "general_history": [AIMessage(content=display_reply)],
        "next_step": "user" if "INSUFFICIENTE" in status else "photography",
        "triage_complete": True if status == "SUFFICIENTE" else False
    }

# Nodo per richiedere più informazioni all'utente
def user_node(state: MedicalState):
    """ Chiede ulteriori informazioni all'utente riguardo ai sintomi. """
    message = input("💬 USER: ")
    while message == "" or message.isspace():
        print("⚠️ Per favore, fornisci una risposta valida.")
        message = input("💬 USER: ")
    return {"general_history": [HumanMessage(content=message)], "triage_history": [HumanMessage(content=message)]}

# Nodo per l'analisi dell'immagine del danno
def photography_node(state: MedicalState):
    """ Analizza l'immagine del danno inviata dall'utente. """
    def encode_image(image_path):
        """Funzione helper per convertire immagine in base64"""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except FileNotFoundError:
            return None
    print("📸 PHOTOGRAPH: ", end="", flush=True)    
    user_choice = input("Vuoi inserire una foto? (Si/No)\n💬 USER: ").strip().lower()
    
    if user_choice not in ['si', 'sì', 'yes', 'y']:
        print("📸 PHOTOGRAPH:  Nessuna foto inserita")
        return {
            "general_history": [AIMessage(content="Il paziente non ha fornito foto della ferita.")],
            "triage_history": [AIMessage(content="Nessuna foto fornita dal paziente.")],
            "photo": None,
            "next_step": "supervisor"
        }

    image_path = input("📸 PHOTOGRAPH: Inserisci il percorso dell'immagine (es. ferita.jpg)\n💬 USER: ").strip()
    base64_image = encode_image(image_path)
    
    if not base64_image:
        print(f"❌ Errore: Immagine '{image_path}' non trovata.")
        return {"general_history": [AIMessage(content="Errore nel caricamento della foto.")]}

    messages = [
        SystemMessage(content=PHOTO_PROMPT),
        HumanMessage(
            content=[
                {"type": "text", "text": "Analizza questa immagine clinica e produci il JSON richiesto."},
                {
                    "type": "image_url", 
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                }
            ]
        )
    ]

    try:
        response = llm_photography.invoke(messages)
        clean_content = response.content.replace("```json", "").replace("```", "").strip()
        clinical_data = json.loads(clean_content)

        print("📸 PHOTOGRAPH: ", end="", flush=True) 
        print(json.dumps(clinical_data, indent=4, ensure_ascii=False))

        return {
            "photo": {
                "photo_url": image_path,
                "descrizione": clinical_data.get("descrizione", "N/A"),
                "tipo_lesione": clinical_data.get("tipo_lesione", "N/A"),
                "gravita_stimata": clinical_data.get("gravita_stimata", "N/A")
            },
            "general_history": [AIMessage(content=f"Foto analizzata: {clinical_data.get('tipo_lesione')} - Gravità {clinical_data.get('gravita_stimata')}")],
            "next_step": "supervisor"
        }

    except json.JSONDecodeError:
        print("❌ Errore: Il modello non ha prodotto un JSON valido.")
        print("Raw output:", response.content)
        return {
            "general_history": [AIMessage(content="Errore tecnico nell'analisi della foto.")],
            "photo": None
        }
    except Exception as e:
        print(f"❌ Errore generico: {e}")
        return {
            "general_history": [AIMessage(content="Errore durante l'elaborazione della foto.")],
            "photo": None
        }

# Nodo del supervisore
def supervisor_node(state: MedicalState):
    """ Analizza la conversazione e decide chi deve intervenire."""
    print("🚦 SUPERVISOR: ", end="", flush=True)
    card = state["patient_card"]
    photo = state.get("photo")
    card_str = json.dumps(card, ensure_ascii=False)
    photo_str = json.dumps(photo, ensure_ascii=False) if photo else "Nessuna foto."

    prompt = SUPERVISOR_PROMPT.format(patient_card=card_str, photo_analysis=photo_str)
    content = stream_response(prompt)
    selected_specialists = ["medico_generale"]

    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)
        
        specs = data.get("specialists", [])
        
        clean_specs = [s.lower() for s in specs if s.lower() in ALL_SPECIALISTS]
        
        if clean_specs:
            selected_specialists = clean_specs
            
        print(f"-> Scelti: {selected_specialists}")

    except json.JSONDecodeError:
        print("-> Errore lettura JSON. Fallback su Medico Generale.")
    
    checklist = {nome: False for nome in selected_specialists}
    print("Checklist specialisti necessari:", checklist)
    return {
        "needed_specialists": checklist
    }

# Nodo generico per specialisti
def specialist_node(state: MedicalState, role: str):
    """ Funzione generica che esegue l'analisi per qualsiasi specialista. """
      
    card = state["patient_card"]
    photo = state.get("photo")
    card_str = json.dumps(card, ensure_ascii=False)
    photo_str = json.dumps(photo, ensure_ascii=False) if photo else "Nessuna foto."

    prompt = SPECIALIST_PROMPT.format(
        role=role,
        card=card_str,
        photo=photo_str
    )

    content = stream_response(prompt)
    
    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        report_data = json.loads(clean_content)
        
        final_report: SpecialistReport = {
            "diagnosi_sintetica": report_data.get("diagnosi_sintetica", "Non determinata"),
            "dettagli": report_data.get("dettagli", "Nessun dettaglio"),
            "esami_consigliati": report_data.get("esami_consigliati", []),
            "livello_urgenza": report_data.get("livello_urgenza", "BASSO")
        }
        
    except json.JSONDecodeError:
        final_report = {
            "diagnosi_sintetica": "Errore Tecnico",
            "dettagli": "Impossibile generare report strutturato.",
            "esami_consigliati": ["Visita di controllo"],
            "livello_urgenza": "BASSO"
        }
    current_specialist = state["needed_specialists"]
    current_specialist[role] = True
    return {
        "medical_reports": {role: final_report},
        "needed_specialists": current_specialist
    }

# Wrapper per i nodi specifici (versione con emoji)
def cardiologist_node(state):
    print(f"🫀 CARDIOLOGO: ", end="", flush=True)
    return specialist_node(state, "cardiologo")


def neurologist_node(state):
    print(f"🧠 NEUROLOGO: ", end="", flush=True)
    return specialist_node(state, "neurologo")


def orthopedic_node(state):
    print(f"🦴 ORTOPEDICO: ", end="", flush=True)
    return specialist_node(state, "ortopedico")


def gastroenterologist_node(state):
    print(f"🍽️ GASTROENTEROLOGO: ", end="", flush=True)
    return specialist_node(state, "gastroenterologo")


def dermatologist_node(state):
    print(f"🧴 DERMATOLOGO: ", end="", flush=True)
    return specialist_node(state, "dermatologo")


def pneumologist_node(state):
    print(f"🫁 PNEUMOLOGO: ", end="", flush=True)
    return specialist_node(state, "pneumologo")


def ent_node(state):  # Otorino (Ear Nose Throat)
    print(f"👂 OTORINO: ", end="", flush=True)
    return specialist_node(state, "otorino")


def ophthalmologist_node(state):
    print(f"👁️ OCULISTA: ", end="", flush=True)
    return specialist_node(state, "oculista")


def urologist_node(state):
    print(f"🚻 UROLOGO: ", end="", flush=True)
    return specialist_node(state, "urologo")


def general_practitioner_node(state):
    print(f"👨‍⚕️ MEDICO GENERALE: ", end="", flush=True)
    return specialist_node(state, "medico_generale")

# Nodo del primario
def primary_node(state: MedicalState):
    """ Nodo finale che genera il report conclusivo. """
    print("🏥 PRIMARIO: ", end="", flush=True)
    current_card = state["general_history"]
    prompt = [SystemMessage(content=PRIMARY_PROMPT)] + current_card
    full_response = stream_response(prompt)
    return {"diagnosis": AIMessage(content=full_response), "general_history": [AIMessage(content=full_response)]}

# Funzione per lo streaming della risposta dei vari nodi
def stream_response(prompt_current_card):
    full_response = ""
    for chunk in llm_agents.stream(prompt_current_card):
        content = chunk.content
        print(content, end="", flush=True)
        full_response += content
    print("\n")
    return full_response