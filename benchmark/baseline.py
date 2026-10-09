"""The three single-call conditions: one request to the model, without the round table.

    bare    the patient card, the names of the codes and the names of the specialists
    rag     the same, with the guidelines retrieved for the patient
    single  the same, with the definition of the codes and the rules a specialist of the table is given

Each condition adds one thing to the one before, and nothing else changes: same opening, same patient, same list
of specialists, same answer format.
"""

import asyncio
import json

import src.agents.common as common
from src.agents.prompts import SUPERVISOR_PROMPT, TRIAGE_CODES
from src.agents.roundtable import SPECIALIST_DISPLAY_NAMES, _parse_urgency
from src.agents.supervisor import _roles_from
from src.rag.retriever import build_queries, retrieve

from .cases import LEVELS, Case

SINGLE_CALL_CONDITIONS = ("bare", "rag", "single")  # From the least to the most informed.
GUIDELINE_ROLE = "general_practitioner"  # The guidelines are those the general practitioner of the table would get.

# The rule on the names is the supervisor's own, and the names are written as in its list (in quotes, then an arrow):
# a name copied with its label would not be recognised by the app. The areas of competence are left out: they are
# what the supervisor is given, not a specialist.
NAMES_RULE = next(line.strip("- ").strip() for line in SUPERVISOR_PROMPT.splitlines() if "Usa SOLO i nomi esatti" in line)
SPECIALIST_NAMES = "\n".join(f'- "{role}" -> {name}' for role, name in SPECIALIST_DISPLAY_NAMES.items())
CHOICE_RULE = f"da uno a tre, i piu' pertinenti per i sintomi del paziente. {NAMES_RULE}"

# In Italian like every prompt of the app.
OPENING = ("Sei un medico di pronto soccorso. Valuta da solo il paziente: formula un'ipotesi diagnostica preliminare, "
           "assegna il codice di triage e indica gli specialisti pertinenti.")
GUIDELINES_TITLE = ("LINEE GUIDA RECUPERATE (forse pertinenti, forse no: valutale tu; ogni passaggio ha il suo "
                    "riferimento [documento, p. pagina]):")
NO_GUIDELINES = "Nessuna linea guida pertinente trovata nel database."
CODE_NAMES = f"CODICI DI TRIAGE, dal piu' al meno urgente: {', '.join(LEVELS)}."
SPECIALISTS = f"SPECIALISTI DISPONIBILI:\n{SPECIALIST_NAMES}"
# The rules and the code definitions are those of the specialist prompt.
RULES = f"""REGOLE:
- FATTI E IPOTESI: come fatti usa SOLO i DATI PAZIENTE. Non attribuire al paziente segni, sintomi, durate, terapie o esiti di esami che non ha riferito. Un segno non riferito NON e' assente, e' sconosciuto.
- URGENZA: {TRIAGE_CODES}
- SPECIALISTI: {CHOICE_RULE}"""
ANSWER = """RISPONDI SOLO CON QUESTO JSON (nessun altro testo):
{"diagnosis": "la tua ipotesi diagnostica preliminare", "urgency_level": "ROSSO" | "ARANCIONE" | "AZZURRO" | "VERDE" | "BIANCO",
 "specialists": ["specialista 1", "specialista 2"], "motivazione": "il ragionamento clinico, in 2-3 frasi"}"""


def guidelines_for(case: Case) -> str:
    """The guidelines of a case, retrieved as for a turn of the general practitioner."""
    display_name = SPECIALIST_DISPLAY_NAMES[GUIDELINE_ROLE]
    queries = build_queries(display_name, [s.description for s in case.card.symptom.symptoms])
    chunks = retrieve(queries, GUIDELINE_ROLE)
    return "\n\n".join(f"- [{chunk.citation}] {chunk.text}" for chunk in chunks) if chunks else NO_GUIDELINES


def build_prompt(case: Case, condition: str) -> str:
    """The prompt of one single-call condition for a case; only "rag" and "single" retrieve the guidelines."""
    sections = [OPENING, f"DATI PAZIENTE:\n{case.card.model_dump_json()}"]
    if condition != "bare":
        sections.append(f"{GUIDELINES_TITLE}\n{guidelines_for(case)}")
    if condition == "single":
        sections += [SPECIALISTS, RULES]
    else:
        sections += [CODE_NAMES, f"{SPECIALISTS}\nIndicane {CHOICE_RULE}"]
    return "\n\n".join(sections + [ANSWER]) + "\n"


async def run_single_call(case: Case, condition: str) -> dict:
    """One request to the active text model; an unreadable answer gives no code."""
    prompt = await asyncio.to_thread(build_prompt, case, condition)
    content = await asyncio.to_thread(common.stream_response, prompt)
    try:
        data = common.extract_json(content)
    except json.JSONDecodeError:
        return {"code": None, "roles": [], "invalid_answers": 1, "raw_answer": content}
    code = _parse_urgency(data.get("urgency_level"))
    return {
        "code": code,
        "roles": _roles_from(data.get("specialists")),
        "invalid_answers": 0 if code else 1,
        "diagnosis": common.as_text(data.get("diagnosis")),
        "reasoning": common.as_text(data.get("motivazione")),
        "raw_answer": content,
    }
