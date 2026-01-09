import operator
from typing import Annotated, List, TypedDict
from langchain_core.messages import BaseMessage

# Classe TypedDict per la cartella clinica del paziente
class PatientCard(TypedDict):
    """ Cartella clinica del paziente. """
    nome: str
    eta: str
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

# Classe TypedDict per la bacheca di discussione tra specialisti
class DiscussionBoard(TypedDict):
    """ Bacheca di discussione tra specialisti. """
    cardiologo_active: bool  # True = Deve intervenire/replicare
    neurologo_active: bool   # True = Deve intervenire/replicare
    turn_count: int          # Contatore di sicurezza (anti-loop infinito)

# Classe TypedDict che rappresenta lo stato minimale del grafo, cioè le informazioni essenziali che devono essere mantenute tra i nodi
class MedicalState(TypedDict):
    """ Stato minimale del grafo. """
    general_history: Annotated[list[BaseMessage], operator.add] # CRONOLOGIA GENERALE: Qui finiscono tutti i messaggi generati durante la consultazione
    triage_history: Annotated[list[BaseMessage], operator.add]  # CRONOLOGIA TRIAGE: Qui finiscono tutti i messaggi relativi al triage iniziale
    triage_complete: bool                                       # FLAG DI COMPLETAMENTO TRIAGE: indica se il triage è completo       
    diagnosis: str                                              # DIAGNOSI FINALE: il testo della diagnosi finale generata dal primario   
    next_step: str                                              # PROSSIMO PASSO: indica quale specialista deve intervenire o se finire il processo
    
    patient_card: PatientCard                                   # CARTELLA CLINICA: i dati strutturati del paziente
    photo: PhotoAnalysis                                        # FOTO ANALISI: dati relativi alla foto del danno del paziente
    medical_reports: dict[str, SpecialistReport]                # REPORT SPECIALISTICI: i report generati dagli specialisti coinvolti

    def __init__(self):
        self.general_history = list()
        self.triage_history = list()
        self.triage_complete = False
        self.diagnosis = ""
        self.next_step = ""
        self.patient_card = PatientCard(
            nome="",
            eta="",
            sintomo_principale="",
            intensita="",
            durata=""
        )
        self.photo = PhotoAnalysis(
            photo_url="",
            descrizione="",
            tipo_lesione="",
            gravita_stimata=""
        )
        self.medical_reports = dict()