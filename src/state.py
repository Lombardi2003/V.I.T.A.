import operator
from typing import Annotated, List, TypedDict, Optional
from langchain_core.messages import BaseMessage

# Classe TypedDict per la cartella clinica del paziente
class PatientCard(TypedDict):
    """ Cartella clinica del paziente. """
    codice_fiscale: str
    nome: str
    cognome: str
    eta: str
    patologie_precedenti: List[str]

    sintomo_principale: str
    intensita: str
    durata: str

class PhotoAnalysis(TypedDict):
    """Output dell'analisi visiva per il Triage"""
    photo_url: str
    descrizione: str      # Dettagli clinici visivi (es. "Ferita profonda su...")
    tipo_lesione: str     # Classificazione breve (es. "Lacerazione")
    gravita_stimata: str  # Scala: "Bassa", "Media", "Alta"

# Classe TypedDict per il report dello specialista
class SpecialistReport(TypedDict):
    """ Report di diagnosi e consigli di uno specialista. """
    diagnosi_sintetica: str
    dettagli: str
    esami_consigliati: List[str]
    livello_urgenza: str  # es. "ALTO", "MEDIO", "BASSO"

class Report(TypedDict):
    """ Report finale del primario, che sintetizza tutto. """
    diagnosi_finale: str
    dettagli: str
    esami_consigliati: List[str]
    livello_urgenza: str  # ROSSO, ARANCIONE, AZZURRO, VERDE, BIANCO

# Classe TypedDict che rappresenta lo stato minimale del grafo, cioè le informazioni che devono essere mantenute tra i nodi
class MedicalState(TypedDict):
    """ Stato minimale del grafo. """
    general_history: Annotated[list[BaseMessage], operator.add] # CRONOLOGIA GENERALE: Qui finiscono tutti i messaggi generati durante la consultazione
    triage_history: Annotated[list[BaseMessage], operator.add]  # CRONOLOGIA TRIAGE: Qui finiscono tutti i messaggi relativi al triage iniziale
    triage_complete: bool                                       # FLAG DI COMPLETAMENTO TRIAGE: indica se il triage è completo       
    report: Report                                              # DIAGNOSI FINALE: il testo della diagnosi finale generata dal primario   
    next_step: str  
                                                # PROSSIMO PASSO: indica quale specialista deve intervenire o se finire il processo
    
    patient_card: PatientCard                                   # CARTELLA CLINICA: i dati strutturati del paziente
    photo: Optional[PhotoAnalysis]                              # FOTO ANALISI: dati relativi alla foto del danno del paziente
    patient_exists: bool

    needed_specialists: dict[str, bool]                         # SPECIALISTI NECESSARI: elenco degli specialisti richiesti per la consultazione
    medical_reports: dict[str, SpecialistReport]                # REPORT SPECIALISTICI: i report generati dagli specialisti coinvolti
    inter_consultation: Optional[dict]

def get_empty_patient_card() -> PatientCard:
    return {
        "codice_fiscale": "",
        "nome": "",
        "cognome": "",
        "eta": "",
        "patologie_precedenti": [],
        "sintomo_principale": "",
        "intensita": "",
        "durata": ""
    }

def get_initial_state() -> MedicalState:
    """ Crea lo stato iniziale pulito per il grafo. """
    return {
        "general_history": [],
        "triage_history": [],
        "triage_complete": False,
        "diagnosis": "",
        "next_step": "triage",
        "patient_exists": False,
        
        "patient_card": get_empty_patient_card(),
        "photo": None,
        
        "medical_reports": {},
        "needed_specialists": {},
    }