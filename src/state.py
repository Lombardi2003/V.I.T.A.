from pydantic import BaseModel, Field
from typing import List, Optional, Annotated
import operator
from langchain_core.messages import BaseMessage

# Classe BaseModel per l'analisi della foto del danno del paziente
class PhotoAnalysis(BaseModel):
    """Output dell'analisi visiva per il Triage"""
    photo_url: str = ""        # URL o percorso della foto
    descrizione: str = ""      # Dettagli clinici visivi (es. "Ferita profonda su...")
    tipo_danno: str = ""       # Classificazione breve (es. "Lacerazione")
    gravita_stimata: str = ""  # Scala: "Bassa", "Media", "Alta"

# Classe BaseModel per il profilo dei sintomi del paziente
class SymptomProfile(BaseModel):
    """ Profilo dei sintomi del paziente. """
    sintomo_principale: str = ""
    intensita: str = ""
    durata: str = ""
    photo: Optional[PhotoAnalysis] = None     # Opzionali: diciamo che di base partono come None 

# Classe BaseModel per la cartella clinica del paziente
class PatientCard(BaseModel):
    """ Cartella clinica del paziente. """
    # Anagrafica
    codice_fiscale: str = ""
    nome: str = ""
    cognome: str = ""
    eta: str = ""
    # Storia clinica
    patologie_precedenti: List[str] = Field(default_factory=list)
    # Dati medici
    symptom: SymptomProfile = Field(default_factory=SymptomProfile)

# Classe BaseModel per il report dello specialista
class SpecialistReport(BaseModel):
    """ Report di diagnosi e consigli di uno specialista. """
    diagnosi_sintetica: str = ""
    dettagli: str = ""
    esami_consigliati: List[str] = Field(default_factory=list) # CORRETTO QUI
    livello_urgenza: str = ""               # es. "ALTO", "MEDIO", "BASSO"

# Classe BaseModel che rappresenta lo stato minimale del grafo
class MedicalState(BaseModel):
    """ Stato minimale del grafo. """
    # Liste: usiamo default_factory per creare liste separate per ogni conversazione
    general_history: Annotated[list[BaseMessage], operator.add] = Field(default_factory=list)
    triage_history: Annotated[list[BaseMessage], operator.add] = Field(default_factory=list)
    
    triage_complete: bool = False                                      
    diagnosis: str = ""                                                
    next_step: str = ""                                                
    
    # Oggetti complessi: diciamo a Pydantic di istanziarli vuoti in automatico
    patient_card: PatientCard = Field(default_factory=PatientCard)                               

    # Dizionari: usiamo default_factory=dict
    needed_specialists: dict[str, bool] = Field(default_factory=dict)
    medical_reports: dict[str, SpecialistReport] = Field(default_factory=dict)