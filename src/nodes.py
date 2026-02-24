# Librerie per LLM e messaggi
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
# Import dei moduli locali
from src.state import MedicalState, SpecialistReport, PatientCard
from src.config import REVIEWER_PROMPT, SUPERVISOR_PROMPT, SPECIALIST_PROMPT, PRIMARY_PROMPT, PHOTO_PROMPT, ALL_SPECIALISTS
from src.database import MedicalDatabase

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

# Database
mdb = MedicalDatabase()

# Nodo per la lettura del database
def read_db_node(state: MedicalState):
    """ Legge i dati del paziente dal database se esistono. """
    codice_fiscale = input("📂 READ_DB: Inserisci il tuo codice fiscale\n💬 USER: ")
    
    if mdb.verify_patient_exists(codice_fiscale):
        record = mdb.read_patient(codice_fiscale)
        print(f"📂 READ_DB: Benvenuto - {record.nome} {record.cognome} - Inserisci i tuoi sintomi")
        return {
            "patient_card": {
                "codice_fiscale": codice_fiscale,
                "nome": record.nome,
                "cognome": record.cognome,
                "eta": record.eta,
                "patologie_precedenti": record.patologie_precedenti
            },
            "patient_exists": True
        }
    else:
        print(f"📂 READ_DB: Benvenuto nuovo paziente - Inserisci i tuoi dati")
        return {
            "patient_card": {
                "codice_fiscale": codice_fiscale,
            },
            "patient_exists": False
        }

# Nodo per il salvataggio nel database
def save_db_node(state: MedicalState):
    """ Salva o aggiorna i dati del paziente nel database. """
    print("💾 SAVE_DB: Avvio salvataggio...")
    
    card = state.get("patient_card", {})
    
    # 1. Controllo di sicurezza sul codice fiscale (Ottimo che tu lo abbia già messo!)
    if "codice_fiscale" not in card or not card["codice_fiscale"]:
        print("❌ SAVE_DB: Codice fiscale mancante, impossibile salvare.")
        return {}
        
    # 2. IL FIX: Assicuriamoci che 'patologie_precedenti' esista e sia una vera Lista!
    if "patologie_precedenti" not in card or not isinstance(card["patologie_precedenti"], list):
        card["patologie_precedenti"] = []
        
    # 3. Estrazione sicura della diagnosi
    diagnosi_obj = state.get("report")
    testo_diagnosi = diagnosi_obj["diagnosi_finale"] if diagnosi_obj else "Nessuna diagnosi specifica"
    
    # 4. Ora possiamo fare l'append in totale sicurezza
    card["patologie_precedenti"].append(testo_diagnosi)
    
    # 5. Invio al database
    mdb.save_patient(card)
    print("✅ SAVE_DB: Dati salvati con successo.")
    
    # Restituiamo la card aggiornata allo stato del grafo
    return {"patient_card": card}

# Nodo per modificare un paziente esistente nel database
def modify_db_node(state: MedicalState):
    """ Modifica i dati di un paziente esistente nel database. """
    print("🔄 MODIFY_DB: Avvio modifica dati...")
    
    card = state.get("patient_card", {})
    
    if "codice_fiscale" not in card or not card["codice_fiscale"]:
        print("❌ MODIFY_DB: Codice fiscale mancante, impossibile modificare.")
        return {}
    
    nuova_patologia = state.get("report", {}).get("diagnosi_finale", "Nessuna diagnosi specifica")
    
    mdb.modify_patology_patient(card, nuova_patologia)
    print("✅ MODIFY_DB: Dati modificati con successo.")
    
    return {"patient_card": card}

# Nodo del revisore
def reviewer_node(state: MedicalState):
    """ Analizza la Patient Card e decide se sono necessarie più informazioni dall'utente. """
    print("\n\n\n\n")
    print(state)    
    print("\n\n\n\n")
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

def user_node(state: MedicalState):
    """ 
    Nodo Utente Ibrido:
    - Funziona con Chainlit (non chiede input se il messaggio c'è già)
    - Funziona col Terminale (chiede input se manca)
    """
    
    print(state["patient_card"])

    history = state.get("triage_history", [])
    
    # Per Chainlit: non chiediamo input, passiamo direttamente al nodo successivo.
    if history and isinstance(history[-1], HumanMessage):
        print("💬 USER: "+history[-1].content)
        return {
            "general_history": [history[-1]], 
            "triage_history": [history[-1]]
        }

    # Per input da terminale
    message = input("💬 USER: ")
    while message == "" or message.isspace():
        print("⚠️ Per favore, fornisci una risposta valida.")
        message = input("💬 USER: ")
        
    return {
        "general_history": [HumanMessage(content=message)], 
        "triage_history": [HumanMessage(content=message)]
    }

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

def specialist_node(state: MedicalState, role: str):
    print(f"\n🩺 {role.upper()}: Analisi in corso...", flush=True)
      
    card = state.get("patient_card", {})
    consultation = state.get("inter_consultation")
    card_str = json.dumps(card, ensure_ascii=False)

    messaggi_colleghi = ""
    if consultation:
        if consultation.get("a") == role and not consultation.get("risposta"):
            messaggi_colleghi = f"⚠️ DOMANDA DAL {consultation['da'].upper()}: '{consultation['domanda']}'.\n-> Rispondi nel campo 'dettagli_referto'."
        elif consultation.get("da") == role and consultation.get("risposta"):
            messaggi_colleghi = f"✅ RISPOSTA DAL {consultation['a'].upper()}: '{consultation['risposta']}'.\n-> Usa questa info per concludere il referto. Ora 'necessita_consulto' deve essere FALSE."

    prompt = SPECIALIST_PROMPT.format(role=role, card=card_str, messaggi_colleghi=messaggi_colleghi)
    content = stream_response(prompt)

    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)
        
        print(f"   -> 🧠 Ragionamento: {data.get('ragionamento_iniziale', '')}")
        
        necessita_consulto = data.get("necessita_consulto", False)
        if necessita_consulto and not (consultation and consultation.get("a") == role):
            target = data.get("specialista_da_consultare", "").lower().strip()
            domanda = data.get("domanda_al_collega", "")
            
            if target and target != role:
                print(f"   -> 🔄 PAUSA: Il {role.upper()} chiede un consulto al {target.upper()}!")
                return {
                    "inter_consultation": {"da": role, "a": target, "domanda": domanda, "risposta": None},
                    "next_step": target 
                }
            
        final_report = {
            "diagnosi_sintetica": data.get("diagnosi_sintetica", "Non determinata"),
            "dettagli": data.get("dettagli_referto", "Nessun dettaglio"),
            "esami_consigliati": data.get("esami_consigliati", []),
            "livello_urgenza": data.get("livello_urgenza", "BASSO")
        }
        
    except Exception as e:
        print(f"   -> ❌ Errore Lettura LLM: Procedo con referto di emergenza.")
        final_report = {
            "diagnosi_sintetica": "Errore", "dettagli": "Impossibile leggere i dati.",
            "esami_consigliati": [], "livello_urgenza": "BASSO"
        }

    current_specialist = state.get("needed_specialists", {})
    current_specialist[role] = True 
    
    next_step = "router"
    new_consultation = consultation

    if consultation:
        if consultation.get("a") == role and not consultation.get("risposta"):
            print(f"   -> ✅ Risposta formulata per il {consultation['da'].upper()}")
            new_consultation["risposta"] = final_report["dettagli"]
            next_step = consultation["da"]
        elif consultation.get("da") == role and consultation.get("risposta"):
            print(f"   -> 🏁 {role.upper()} chiude il referto dopo il consulto.")
            new_consultation = None 

    return {
        "medical_reports": {role: final_report},
        "needed_specialists": current_specialist,
        "inter_consultation": new_consultation,
        "next_step": next_step
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
            reports_text += f"Diagnosi: {referto.get('diagnosi_sintetica', '')}\n"
            reports_text += f"Dettagli: {referto.get('dettagli', '')}\n"
            reports_text += f"Urgenza: {referto.get('livello_urgenza', '')}\n"

    # 3. Creiamo il prompt e chiamiamo l'LLM
    prompt = PRIMARY_PROMPT.format(card=card_str, reports_text=reports_text)
    content = stream_response(prompt)
    
    # 4. Estraiamo il JSON come hai fatto negli altri nodi
    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        report_data = json.loads(clean_content)
        
        diagnosi_finale = report_data.get("diagnosi_finale", "Diagnosi non determinata")
        dettagli = report_data.get("dettagli", "")
        livello_urgenza = report_data.get("livello_urgenza", "BIANCO")
        
    except json.JSONDecodeError:
        diagnosi_finale = "Errore nella generazione della diagnosi."
        dettagli = "Errore tecnico."
        livello_urgenza = "BIANCO"
        
    print(f"   -> Urgenza assegnata: {livello_urgenza}")
    
    # 5. Prepariamo un messaggio per l'utente/interfaccia
    messaggio_finale = f"Il Primario ha concluso la valutazione.\nDiagnosi: {diagnosi_finale}\nCodice: {livello_urgenza}"
    
    # 6. Restituiamo i dati aggiornati
    return {
        "diagnosis": diagnosi_finale, # Salviamo la stringa per il DB!
        "general_history": [AIMessage(content=messaggio_finale)],
        "next_step": "save_db"        # Mandiamo il grafo all'ultimo nodo
    }