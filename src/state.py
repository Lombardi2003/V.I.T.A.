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
# SymptomProfile sotto e reviewer_node in reviewer.py per come si accumulano.
class Symptom(BaseModel):
    """ Un singolo sintomo riferito dal paziente. """
    description: str = ""
    intensity: str = ""
    duration: str = ""
    # Circostanze che scatenano/aggravano/alleviano il sintomo (es. "peggiora
    # quando si alza in piedi", "migliora a riposo") - separato da 'description'
    # perche' e' un'informazione DIVERSA (non "cosa e'" ma "quando/come cambia").
    # Prima di questo campo, il revisore capiva questi dettagli (li ripeteva nel
    # messaggio di conferma all'utente) ma non aveva dove salvarli, quindi
    # sparivano prima di arrivare al supervisore/agli specialisti (osservato in
    # test reale: "vertigini quando mi alzo in piedi" arrivava al tavolo come
    # semplice "vertigini", perdendo l'indizio posturale/cardiovascolare).
    trigger: str = ""
    # Caratteristiche del sintomo: sede precisa, qualita', irradiazione, segni
    # associati (es. "irradiato al braccio sinistro", "a fitte", "ginocchio
    # gonfio e caldo") - diverso da 'description' (COSA e') e da 'trigger'
    # (QUANDO cambia). Prima non c'era dove metterle e sparivano (osservato in
    # prova reale: "dolore al petto che va verso il braccio sinistro" arrivava
    # agli specialisti come semplice "dolore toracico").
    characteristics: str = ""

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

# Classe BaseModel per l'ipotesi diagnostica CONDIVISA dal tavolo degli
# specialisti - sostituisce N referti indipendenti (il vecchio
# SpecialistReport/medical_reports): invece di ognuno per conto proprio, tutti
# gli specialisti coinvolti leggono, confermano o rivedono questo STESSO
# oggetto turno dopo turno (vedi specialist_node/router in specialist.py e
# router.py). Si sovrascrive per intero ad ogni turno (niente reducer, come
# patient_card), MAI accumulato come round_table sotto.
#
# urgency_level usa i codici colore del triage italiano (non la scala ESI):
# e' la stessa scala gia' richiesta da PRIMARY_PROMPT per la diagnosi finale -
# tenerle allineate evita un mismatch che farebbe fallire la validazione
# Pydantic (osservato leggendo il codice, mai girato prima).
class GroupHypothesis(BaseModel):
    """ Ipotesi diagnostica condivisa dal tavolo, rivista turno per turno. """
    diagnosis: str = ""
    urgency_level: Literal["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"] = "BIANCO"
    recommended_exams: List[str] = Field(default_factory=list)
    details: str = ""
    discarded_alternative: str = ""
    discard_reason: str = ""
    last_updated_by: str = ""      # ruolo di chi l'ha proposta/rivista per ultimo
    # Chi ha confermato la versione ATTUALE (si azzera ogni volta che qualcuno
    # la rivede - vedi specialist_node) - il router (router.py) considera la
    # discussione conclusa quando coincide con tutti i needed_specialists.
    confirmed_by: List[str] = Field(default_factory=list)

# Classe BaseModel per un intervento al "tavolo" tra specialisti - non e' piu'
# un'opinione isolata, e' un'azione compiuta sull'ipotesi di gruppo condivisa
# (GroupHypothesis sopra): la propone, la conferma, la rivede, oppure chiama
# in causa (mini-consulto) uno specialista non ancora seduto al tavolo.
class RoundTableEntry(BaseModel):
    """ Un singolo intervento nella discussione tra specialisti. """
    author: str                 # ruolo di chi parla, es. "cardiologist"
    to: Optional[str] = None    # ruolo destinatario, None = rivolto a tutti
    # False quando "to" NON l'ha scelto lo specialista ma e' stato messo in
    # automatico (l'ultimo collega che ha parlato, vedi specialist_node): il
    # router da' una battuta di reazione solo a chi e' stato chiamato in causa
    # davvero - prima la dava quasi dopo ogni conferma, perche' il destinatario
    # automatico sembrava sempre una chiamata in causa (chiamate LLM in piu'
    # anche senza nulla da aggiungere).
    to_explicit: bool = True
    azione: str = ""            # "proponi" | "conferma" | "rivedi" | "consulta"
    content: str = ""
    # Urgenza sostenuta da chi parla in questo intervento (None per "consulta",
    # che e' solo una domanda). Registrata per ogni intervento, non solo
    # nell'ipotesi di gruppo, perche' quella tiene solo l'ULTIMA versione: le
    # urgenze proposte prima e poi riviste andavano perse, e il primario non
    # sapeva che qualcuno al tavolo aveva indicato un codice piu' alto (vedi
    # primary_node in primary.py).
    urgency: Optional[Literal["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"]] = None
    # True se l'intervento e' il turno del giro di verifica finale (vedi
    # MedicalState.verification_queue e router in router.py): non conta nel
    # tetto MAX_SPEAKS_PER_SPECIALIST.
    verification: bool = False

# Classe BaseModel per la diagnosi finale e le raccomandazioni
#
# urgency_level usa la stessa scala di colori italiana di SpecialistReport
# (non piu' la scala ESI) - erano disallineate: il primario avrebbe potuto
# ricevere dall'LLM un colore valido per SpecialistReport/PRIMARY_PROMPT ma
# rifiutato qui dalla validazione Pydantic (mai girato prima, trovato leggendo
# il codice mentre si ricollegava il primario al grafo).
class FinalDiagnosis(BaseModel):
    """Report di sintesi del primario. "diagnosis" e' l'IPOTESI DIAGNOSTICA
    PRELIMINARE (terminologia della tesi: non una diagnosi definitiva)."""
    diagnosis: str = ""
    urgency_level: Literal["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"] = "BIANCO"
    specialists_involved: List[str] = Field(default_factory=list)
    # Esami/accertamenti da avviare e dati NON riferiti da verificare: prima
    # finivano (se ci finivano) mescolati nel testo delle indicazioni.
    recommended_exams: List[str] = Field(default_factory=list)
    to_verify: List[str] = Field(default_factory=list)
    # Indicazioni per il PERSONALE del pronto soccorso (non per il paziente).
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
    # needed_specialists: chi e' seduto al tavolo (selezione del supervisore +
    # eventuali reclutati durante la discussione, vedi router in router.py) - il
    # valore booleano non porta piu' informazione propria (era "ha depositato
    # il referto" nel vecchio disegno a referti indipendenti), resta True per
    # tutti, il dizionario serve solo come insieme ordinato di ruoli.
    needed_specialists: dict[str, bool] = Field(default_factory=dict)
    # Ipotesi diagnostica condivisa dal tavolo - None finche' nessuno ha ancora
    # aperto la discussione (vedi GroupHypothesis sopra).
    group_hypothesis: Optional[GroupHypothesis] = None

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
    # vedi MAX_RECRUITED_SPECIALISTS in roundtable.py.
    recruited_specialists_count: int = 0

    # Giro di verifica finale (router in router.py): quando tutti hanno
    # confermato, prima del primario, ogni specialista al tavolo ha un ultimo
    # turno per dire se, letti i colleghi, la sua valutazione e' cambiata - la
    # sola regola "tutti confermano, si chiude" premiava chi confermava subito,
    # senza un momento in cui ciascuno ripensa alla luce degli altri.
    # verification_started: il giro e' gia' partito (si fa UNA volta sola).
    # verification_queue: chi deve ancora fare il suo turno di verifica.
    # verifying_role: a chi il router ha appena dato un turno di verifica
    # (specialist_node lo legge per aggiungere l'istruzione al prompt).
    # Turni FALLITI per specialista (risposta illeggibile, errore dell'API):
    # il router fa passare oltre chi ne accumula MAX_FAILED_TURNS (roundtable.py)
    # invece di richiamarlo all'infinito.
    failed_turns: dict[str, int] = Field(default_factory=dict)
    # Chi il router ha fatto passare oltre senza che confermasse la versione
    # attuale dell'ipotesi (interventi o turni falliti esauriti): tenuto
    # separato da group_hypothesis.confirmed_by, cosi' il primario non legge
    # un consenso che non c'e' stato.
    passed_without_confirming: list[str] = Field(default_factory=list)
    # Chi il supervisore ha aggiunto al tavolo per un SECONDO PARERE (oggi il
    # medico generico, quando era stato scelto un solo specialista): il suo
    # prompt riceve un'istruzione dedicata (specialist_node). "" = nessuno.
    second_opinion_role: str = ""

    verification_started: bool = False
    verification_queue: list[str] = Field(default_factory=list)
    verifying_role: str = ""

    # Contabilita' di conversazione per intake_node: true quando l'argomento e' stato
    # affrontato (anche per negarlo), non dato clinico -> non sta su PatientCard.
    allergies_addressed: bool = False
    previous_conditions_addressed: bool = False
    # intake_node: la scheda anagrafica e' gia' stata mostrata all'operatore (il
    # primo passaggio, appena arrivati da read_db, non chiama il modello), e la
    # scheda completa e' stata confermata (solo allora si passa ai sintomi).
    intake_card_shown: bool = False
    card_confirmed: bool = False
    # reviewer_node: stessa cosa per i sintomi (il primo passaggio, appena
    # confermata l'anagrafica, chiede i sintomi senza chiamare il modello).
    reviewer_card_shown: bool = False
    symptoms_confirmed: bool = False
    # photography_node: la richiesta della foto e' gia' stata fatta (il primo
    # passaggio, appena confermati i sintomi, chiede la foto senza aspettare).
    photo_request_shown: bool = False
