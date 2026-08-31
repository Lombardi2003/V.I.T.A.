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

# Classe BaseModel per un singolo sintomo riferito dal paziente - un paziente
# puo' presentarne piu' di uno in sistemi diversi (es. mal di testa + vista
# offuscata), ognuno con la propria intensita'/durata (osservato in test reale:
# durate diverse per sintomi diversi nello stesso messaggio) - vedi
# SymptomProfile sotto e reviewer_node in intake.py per come si accumulano.
class Symptom(BaseModel):
    """ Un singolo sintomo riferito dal paziente. """
    description: str = ""
    intensity: str = ""
    duration: str = ""

# Classe BaseModel per il profilo dei sintomi del paziente
class SymptomProfile(BaseModel):
    """ Profilo dei sintomi del paziente. """
    symptoms: List[Symptom] = Field(default_factory=list)
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
#
# urgency_level usa i codici colore del triage italiano (non la scala ESI):
# e' la stessa scala gia' richiesta da PRIMARY_PROMPT per la diagnosi finale -
# tenerle allineate qui evita un mismatch che farebbe fallire la validazione
# Pydantic al primo referto (osservato leggendo il codice, mai girato prima).
class SpecialistReport(BaseModel):
    """ Report di diagnosi e consigli di uno specialista. """
    summary_diagnosis: str = ""
    details: str = ""
    recommended_exams: List[str] = Field(default_factory=list)
    urgency_level: Literal["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"] = "BIANCO"

# Classe BaseModel per un intervento al "tavolo" tra specialisti (domanda,
# obiezione o commento) - non e' una diagnosi finale, quella resta su
# SpecialistReport/medical_reports.
#
# "posizione" costringe lo specialista a PRENDERE POSIZIONE rispetto a quanto
# detto dai colleghi finora, invece di limitarsi ad accumulare la propria
# ipotesi in parallelo senza mai confrontarsi con quella altrui (osservato in
# test reale: senza un campo obbligatorio dedicato, la discussione restava
# educata ma non convergeva mai - vedi SPECIALIST_PROMPT in prompts.py).
class RoundTableEntry(BaseModel):
    """ Un singolo intervento nella discussione tra specialisti. """
    author: str                    # ruolo di chi parla, es. "cardiologist"
    to: Optional[str] = None       # ruolo destinatario, None = rivolto a tutti
    tipo: Optional[str] = None       # "ipotesi" | "obiezione" | None (apertura discussione) - niente domande a vuoto, vedi SPECIALIST_PROMPT
    posizione: Optional[str] = None  # "d'accordo" | "parzialmente d'accordo" | "in disaccordo" | None (apertura discussione)
    content: str = ""

# Classe BaseModel per la diagnosi finale e le raccomandazioni
#
# urgency_level usa la stessa scala di colori italiana di SpecialistReport
# (non piu' la scala ESI) - erano disallineate: il primario avrebbe potuto
# ricevere dall'LLM un colore valido per SpecialistReport/PRIMARY_PROMPT ma
# rifiutato qui dalla validazione Pydantic (mai girato prima, trovato leggendo
# il codice mentre si ricollegava il primario al grafo).
class FinalDiagnosis(BaseModel):
    diagnosis: str = ""
    urgency_level: Literal["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"] = "BIANCO"
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
    next_step: str = ""

    # Oggetti complessi: diciamo a Pydantic di istanziarli vuoti in automatico
    patient_card: PatientCard = Field(default_factory=PatientCard)

    # Dizionari: usiamo default_factory=dict
    needed_specialists: dict[str, bool] = Field(default_factory=dict)
    medical_reports: dict[str, SpecialistReport] = Field(default_factory=dict)

    final_diagnosis: FinalDiagnosis = Field(default_factory=FinalDiagnosis)

    # Discussione tra gli specialisti selezionati dal supervisore ("tavola
    # rotonda"): ogni intervento si accumula (operator.add, come le cronologie
    # sopra) - chi entra in scena vede tutta la trascrizione, non solo l'ultimo
    # scambio.
    round_table: Annotated[list[RoundTableEntry], operator.add] = Field(default_factory=list)
    # Contatore assoluto di battute (speak + finalize insieme) dall'inizio
    # della discussione - non e' un traguardo da raggiungere (ogni specialista
    # puo' concludere subito), solo il freno di emergenza se non convergono da
    # soli. Ha sostituito il vecchio concetto di "giri di una lista fissa":
    # ora la lista di needed_specialists puo' crescere durante la discussione
    # (vedi recruited_specialists_count sotto), quindi contare i "giri" non
    # avrebbe piu' avuto un limite stabile. Gestito solo dal router.
    total_turns: int = 0
    # Indice di turno nell'ordine di ingresso al tavolo di needed_specialists
    # (supervisore + eventuali specialisti coinvolti durante la discussione) -
    # usato SOLO come ripiego quando l'ultimo intervento non aveva un
    # destinatario specifico (round_table da solo non basta per sapere "di chi
    # e' il turno dopo", perche' registra solo chi interviene a voce, non chi
    # deposita direttamente la diagnosi senza parlare). Gestito solo dal router.
    current_turn_index: int = 0
    # Quanti specialisti sono stati coinvolti DURANTE la discussione (non dalla
    # selezione iniziale del supervisore) - tetto massimo gestito dal router,
    # vedi MAX_RECRUITED_SPECIALISTS in clinical.py.
    recruited_specialists_count: int = 0

    # Contabilita' di conversazione per intake_node: true quando l'argomento e' stato
    # affrontato (anche per negarlo), non dato clinico -> non sta su PatientCard.
    allergies_addressed: bool = False
    previous_conditions_addressed: bool = False
