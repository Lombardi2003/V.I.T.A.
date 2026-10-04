"""Data model shared by the whole graph: the patient card, the round table and the conversation state."""

from pydantic import BaseModel, Field
from typing import List, Optional, Annotated, Literal
import operator
from langchain_core.messages import BaseMessage


class PhotoAnalysis(BaseModel):
    """What the vision model saw in the photo."""
    photo_url: str = ""  # Path of the uploaded file.
    description: str = ""  # Clinical description of what is visible.
    injury_type: str = ""  # Short classification of the lesion.


class Symptom(BaseModel):
    """One symptom reported by the patient."""
    description: str = ""
    intensity: str = ""  # One of: lieve, moderata, forte, insopportabile.
    duration: str = ""
    trigger: str = ""  # When it changes, or the event that caused it.
    characteristics: str = ""  # How it is: site, quality, radiation.


class SymptomProfile(BaseModel):
    """The patient's symptoms and the optional photo."""
    symptoms: List[Symptom] = Field(default_factory=list)
    photo: Optional[PhotoAnalysis] = None


class PatientCard(BaseModel):
    """The patient's card: personal data, history and symptoms."""
    fiscal_code: str = ""
    first_name: str = ""
    last_name: str = ""
    age: str = ""
    sex: str = ""

    allergies: List[str] = Field(default_factory=list)
    # Declared conditions, plus past triage hypotheses labelled as not confirmed.
    previous_conditions: List[str] = Field(default_factory=list)
    symptom: SymptomProfile = Field(default_factory=SymptomProfile)


class GroupHypothesis(BaseModel):
    """The single hypothesis the specialists share, rewritten whole at every revision."""
    diagnosis: str = ""
    # Italian triage colour codes, the same scale everywhere.
    urgency_level: Literal["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"] = "BIANCO"
    recommended_exams: List[str] = Field(default_factory=list)
    details: str = ""
    discarded_alternative: str = ""
    discard_reason: str = ""
    last_updated_by: str = ""  # Role that proposed or revised it last.
    # Roles that confirmed the current version; cleared at every revision.
    confirmed_by: List[str] = Field(default_factory=list)


class RoundTableEntry(BaseModel):
    """One entry of the specialists' discussion."""
    author: str  # Role of who speaks.
    to: Optional[str] = None  # Role addressed, or None for everyone.
    to_explicit: bool = True  # False when the recipient was filled in by the code, not chosen by the specialist.
    azione: str = ""  # proponi | conferma | rivedi | consulta
    content: str = ""
    # Code supported by the author in this entry (None for a consult).
    urgency: Optional[Literal["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"]] = None
    verification: bool = False  # True for a turn of the final verification round.


class FinalDiagnosis(BaseModel):
    """The primary's summary report; `diagnosis` is a preliminary hypothesis, not a diagnosis."""
    diagnosis: str = ""
    urgency_level: Literal["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"] = "BIANCO"
    specialists_involved: List[str] = Field(default_factory=list)
    recommended_exams: List[str] = Field(default_factory=list)
    to_verify: List[str] = Field(default_factory=list)  # Data the patient did not report, each with how to check it.
    operational_guidance: str = ""  # What the staff should do now.
    recommendations: str = ""  # The clinical reasoning behind hypothesis and code.


class MedicalState(BaseModel):
    """The state of one conversation, read and updated by every node."""
    # Histories are accumulated: nodes return only the new messages.
    general_history: Annotated[list[BaseMessage], operator.add] = Field(default_factory=list)
    triage_history: Annotated[list[BaseMessage], operator.add] = Field(default_factory=list)

    triage_complete: bool = False
    patient_exists: bool = False
    next_step: str = ""  # Name of the node to run next; read by the conditional edges.

    patient_card: PatientCard = Field(default_factory=PatientCard)  # Replaced whole at every update (no merge).

    # Who is seated at the table, in order of arrival (the value is always True).
    needed_specialists: dict[str, bool] = Field(default_factory=dict)
    group_hypothesis: Optional[GroupHypothesis] = None  # None until someone opens the discussion.

    final_diagnosis: FinalDiagnosis = Field(default_factory=FinalDiagnosis)

    # The discussion, accumulated entry by entry.
    round_table: Annotated[list[RoundTableEntry], operator.add] = Field(default_factory=list)
    total_turns: int = 0  # Turns so far; the router stops the table at MAX_TOTAL_TURNS.
    current_turn_index: int = 0  # Whose turn it is when the last entry addressed nobody.
    recruited_specialists_count: int = 0  # Colleagues brought in during the discussion.

    failed_turns: dict[str, int] = Field(default_factory=dict)  # Unreadable or failed turns, per role.
    # Roles moved on without confirming: never counted as agreement.
    passed_without_confirming: list[str] = Field(default_factory=list)
    second_opinion_role: str = ""  # Role added for a second opinion, or "".

    verification_started: bool = False  # The final verification round runs once.
    verification_queue: list[str] = Field(default_factory=list)  # Roles still to take their verification turn.
    verifying_role: str = ""  # Role currently taking its verification turn.

    allergies_addressed: bool = False  # The topic was dealt with, even to deny it (an empty list is ambiguous).
    previous_conditions_addressed: bool = False
    intake_card_shown: bool = False  # First pass done: the node has shown its request without calling the model.
    card_confirmed: bool = False  # The operator confirmed the complete card.
    reviewer_card_shown: bool = False
    symptoms_confirmed: bool = False
    photo_request_shown: bool = False
