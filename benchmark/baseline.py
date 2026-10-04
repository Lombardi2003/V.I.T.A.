"""The "model alone" condition: one request with the patient card and the guidelines, without the round table."""

import asyncio
import json

import src.agents.common as common
from src.agents.roundtable import SPECIALIST_DISPLAY_NAMES, _parse_urgency
from src.agents.supervisor import _roles_from
from src.rag.retriever import build_queries, retrieve

from .cases import Case

GUIDELINE_ROLE = "general_practitioner"  # The baseline retrieves the guidelines the general practitioner would get.

# In Italian like every prompt of the app; the shared rules are worded as in the specialist prompt.
BASELINE_PROMPT = """Sei un medico di pronto soccorso. Valuta da solo il paziente: formula un'ipotesi diagnostica preliminare, assegna il codice di triage e indica gli specialisti pertinenti.

DATI PAZIENTE:
{card}

LINEE GUIDA RECUPERATE (forse pertinenti, forse no: valutale tu; ogni passaggio ha il suo riferimento [documento, p. pagina]):
{linee_guida}

SPECIALISTI DISPONIBILI (usa SOLO questi nomi): {specialisti}.

REGOLE:
- FATTI E IPOTESI: come fatti usa SOLO i DATI PAZIENTE. Non attribuire al paziente segni, sintomi, durate, terapie o esiti di esami che non ha riferito. Un segno non riferito NON e' assente, e' sconosciuto.
- URGENZA: una tra "ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO" (dal piu' al meno urgente).
- SPECIALISTI: da uno a tre, i piu' pertinenti per i sintomi del paziente.

RISPONDI SOLO CON QUESTO JSON (nessun altro testo):
{{"diagnosis": "la tua ipotesi diagnostica preliminare", "urgency_level": "ROSSO" | "ARANCIONE" | "AZZURRO" | "VERDE" | "BIANCO",
 "specialists": ["specialista 1", "specialista 2"], "motivazione": "il ragionamento clinico, in 2-3 frasi"}}
"""


def build_prompt(case: Case) -> str:
    """The baseline prompt for a case, with the guidelines retrieved as for a specialist turn."""
    display_name = SPECIALIST_DISPLAY_NAMES[GUIDELINE_ROLE]
    queries = build_queries(display_name, [s.description for s in case.card.symptom.symptoms])
    chunks = retrieve(queries, GUIDELINE_ROLE)
    guideline_text = ("\n\n".join(f"- [{chunk.citation}] {chunk.text}" for chunk in chunks)
                      if chunks else "Nessuna linea guida pertinente trovata nel database.")
    return BASELINE_PROMPT.format(
        card=case.card.model_dump_json(),
        linee_guida=guideline_text,
        specialisti=", ".join(f"{role} ({name})" for role, name in SPECIALIST_DISPLAY_NAMES.items()),
    )


async def run_baseline(case: Case) -> dict:
    """One request to the active text model; an unreadable answer gives no code."""
    prompt = await asyncio.to_thread(build_prompt, case)
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
