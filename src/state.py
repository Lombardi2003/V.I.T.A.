from pydantic import BaseModel, Field
from typing import List, Optional, Annotated, Literal
import operator
from langchain_core.messages import BaseMessage

# Classe BaseModel per l'analisi della foto del danno del paziente
class PhotoAnalysis(BaseModel):
    """Output dell'analisi visiva per il Triage"""
    photo_url: str = ""        # URL o percorso della foto
    description: str = ""      # Dettagli clinici visivi (es. "Ferita profonda su...")
    injury_type: str = ""      # Classificazione breve (es. "Lacerazione")

# Classe BaseModel per il profilo dei sintomi del paziente
class SymptomProfile(BaseModel):
    """ Profilo dei sintomi del paziente. """
    main_symptom: str = ""
    intensity: str = ""
    duration: str = ""
    photo: Optional[PhotoAnalysis] = None     # Opzionali: diciamo che di base partono come None

# Classe BaseModel per la cartella clinica del paziente
class PatientCard(BaseModel):
    """ Cartella clinica del paziente. """
    # Anagrafica
    fiscal_code: str = ""
    first_name: str = ""
    last_name: str = ""
    age: str = ""
    sex: str = ""

    # Allergie
    allergies: List[str] = Field(default_factory=list)
    # Storia clinica
    previous_conditions: List[str] = Field(default_factory=list)
    # Dati medici
    symptom: SymptomProfile = Field(default_factory=SymptomProfile)

# Classe BaseModel per il report dello specialista
class SpecialistReport(BaseModel):
    """ Report di diagnosi e consigli di uno specialista. """
    summary_diagnosis: str = ""
    details: str = ""
    recommended_exams: List[str] = Field(default_factory=list)
    urgency_level: Literal["ESI-1", "ESI-2", "ESI-3", "ESI-4", "ESI-5"] = "ESI-5"

# Classe BaseModel per la diagnosi finale e le raccomandazioni
class FinalDiagnosis(BaseModel):
    diagnosis: str = ""
    urgency_level: Literal["ESI-1", "ESI-2", "ESI-3", "ESI-4", "ESI-5"] = "ESI-5"
    specialists_involved: List[str] = Field(default_factory=list)
    operational_guidance: str = ""
    recommendations: str = ""

# Classe BaseModel che rappresenta lo stato minimale del grafo
class MedicalState(BaseModel):
    """ Stato minimale del grafo. """
    # Liste: usiamo default_factory per creare liste separate per ogni conversazione
    general_history: Annotated[list[BaseMessage], operator.add] = Field(default_factory=list)
    triage_history: Annotated[list[BaseMessage], operator.add] = Field(default_factory=list)

    triage_complete: bool = False
    patient_exists: bool = False
    iteration_count: int = 0        # Ricontrollare questo!!!
    next_step: str = ""

    # Oggetti complessi: diciamo a Pydantic di istanziarli vuoti in automatico
    patient_card: PatientCard = Field(default_factory=PatientCard)

    # Dizionari: usiamo default_factory=dict
    needed_specialists: dict[str, bool] = Field(default_factory=dict)
    medical_reports: dict[str, SpecialistReport] = Field(default_factory=dict)

    final_diagnosis: FinalDiagnosis = Field(default_factory=FinalDiagnosis)

    # Consulto tra specialisti in corso: {"da": str, "a": str, "domanda": str, "risposta": Optional[str]}
    inter_consultation: Optional[dict] = None

    # Contabilita' di conversazione per intake_node: true quando l'argomento e' stato
    # affrontato (anche per negarlo), non dato clinico -> non sta su PatientCard.
    allergies_addressed: bool = False
    previous_conditions_addressed: bool = False
