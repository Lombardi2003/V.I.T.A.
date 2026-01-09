# Librerie per LLM e messaggi
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
# Import dei moduli locali
from state import MedicalState, SpecialistReport, PatientCard
from config import REVIEWER_PROMPT, SUPERVISOR_PROMPT, SPECIALIST_PROMPT, PRIMARY_PROMPT, PHOTO_PROMPT

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
    current_card = state.get("patient_card", PatientCard())
    user_msg = state["triage_history"][-1].content
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
    
    print(f"   -> Status: {status}")
    print(f"   -> Dati attuali: {current_card}")
    print(f"   -> Risposta all'utente: {reply if reply else "Perfetto, raccolta dati completa ✨"}")

    return {
        "patient_card": current_card,          
        "triage_history": [AIMessage(content=reply)], 
        "general_history": [AIMessage(content=reply)],
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
    user_choice = input("Vuoi inserire una foto?\n💬 USER: ").strip().lower()
    
    if user_choice not in ['si', 'sì', 'yes', 'y']:
        print("📸 PHOTOGRAPH:  Nessuna foto inserita")
        return {
            "general_history": [AIMessage(content="Il paziente non ha fornito foto della ferita.")],
            "triage_history": [AIMessage(content="Nessuna foto fornita dal paziente.")],
            "photo": None 
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
    """ Analizza la conversazione e decide chi deve intervenire. Stampa FINISH se la diagnosi è completa. """
    print("🚦 SUPERVISOR: ", end="", flush=True)
    current_card = state["general_history"]
    prompt = [SystemMessage(content=SUPERVISOR_PROMPT)] + current_card
    response = stream_response(prompt)
    decision_text = response.strip().lower()
    next_node = "FINISH"
    if "cardiologo" in decision_text:
        next_node = "cardiologo"
    elif "neurologo" in decision_text:
        next_node = "neurologo"
    return {"next_step": next_node}

# Nodo generico per specialisti
def specialist_node(state: MedicalState, role: str):
    current_reports = state.get("medical_reports", {})
    if not current_reports: current_reports = {}

    patient_card = state.get("patient_card", {})
    card_str = json.dumps(patient_card, ensure_ascii=False)

    prompt_content = SPECIALIST_PROMPT.format(role=role,patient_card=card_str)
    
    # Passiamo la storia generale per fargli leggere il contesto
    messages = [SystemMessage(content=prompt_content)] + state["general_history"]
    
    # 3. Chiamata LLM
    response_str = stream_response(messages)
    
    # 4. Parsing JSON (Logica Robusta)
    new_report = {}
    flags = {}
    
    try:
        # Pulizia JSON (trova le graffe esterne)
        clean_json = response_str.replace("```json", "").replace("```", "").strip()
        start = clean_json.find("{")
        end = clean_json.rfind("}") + 1
        
        if start != -1 and end != -1:
            data = json.loads(clean_json[start:end])
            
            # Estrazione del Report
            raw_report = data.get("medical_report", {})
            
            # Creazione oggetto TypedDict (Validazione)
            new_report: SpecialistReport = {
                "diagnosi_sintetica": raw_report.get("diagnosi_sintetica", "Analisi completata"),
                "dettagli": raw_report.get("dettagli", response_str[:100]), # Fallback sul testo grezzo
                "esami_consigliati": raw_report.get("esami_consigliati", []),
                "livello_urgenza": raw_report.get("livello_urgenza", "MEDIO")
            }
            
        else:
            raise ValueError("JSON non trovato nella risposta")

    except Exception as e:
        print(f"\n❌ ERRORE JSON SPECIALISTA: {e}")
        # Fallback di emergenza per non bloccare il sistema
        new_report = {
            "diagnosi_sintetica": "Errore Formattazione",
            "dettagli": f"Il modello ha risposto: {response_str}",
            "esami_consigliati": [],
            "livello_urgenza": "BASSO"
        }

    # 5. SALVATAGGIO NEL REGISTRO (Cruciale!)
    # Aggiorniamo il dizionario dei report con la chiave del ruolo corrente
    current_reports[role] = new_report
    
    print(f"\n   ✅ Referto salvato per {role}: {new_report['diagnosi_sintetica']}")

    # 6. RETURN
    # Restituiamo medical_reports aggiornato e un messaggio per la chat (così gli altri sanno che ha parlato)
    chat_msg = f"**REFERTO {role.upper()}**: {new_report['diagnosi_sintetica']}\n(Vedi dettagli in cartella clinica)"
    
    return {
        "medical_reports": current_reports,  # <--- Il registro aggiornato
        "general_history": [AIMessage(content=chat_msg)], # <--- La notifica in chat
        # "discussion_board": ... (implementeremo dopo)
        "next_step": "check_board" # O supervisor, a seconda del tuo grafo attuale
    }

# Wrapper per i nodi specifici
def cardiologist_node(state):
    print(f"🫀  CARDIOLOGIT: ", end="", flush=True)
    return specialist_node(state, "cardiologo")

def neurologist_node(state):
    print(f"🧠 NEUROLOGIST: ", end="", flush=True)
    return specialist_node(state, "neurologo")

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