"""The two single-call conditions: one request to the model, without the round table.

    baseline  the "model alone": the patient card, the retrieved guidelines, the specialists with their areas and the rules
    bare      the bare model: the patient card, the names of the codes and of the specialists, and the answer format
"""

import asyncio
import json

import src.agents.common as common
from src.agents.prompts import SUPERVISOR_PROMPT, TRIAGE_CODES
from src.agents.roundtable import SPECIALIST_DISPLAY_NAMES, _parse_urgency
from src.agents.supervisor import _roles_from
from src.rag.retriever import build_queries, retrieve

from .cases import LEVELS, Case

GUIDELINE_ROLE = "general_practitioner"  # The baseline retrieves the guidelines the general practitioner would get.

# The specialists and the rule on their names are copied from the supervisor's prompt, not rewritten: the model alone
# chooses them from the same list, with the same instruction, as the supervisor does in the full system.
_LIST_TITLE = "LISTA SPECIALISTI E AMBITI DI COMPETENZA:"
SPECIALIST_LIST = SUPERVISOR_PROMPT.split(_LIST_TITLE)[1].split("RESTITUISCI SOLO UN JSON")[0].strip()
NAMES_RULE = next(line.strip("- ").strip() for line in SUPERVISOR_PROMPT.splitlines() if "Usa SOLO i nomi esatti" in line)

# In Italian like every prompt of the app; the shared rules and the code definitions are those of the specialist prompt.
BASELINE_PROMPT = """Sei un medico di pronto soccorso. Valuta da solo il paziente: formula un'ipotesi diagnostica preliminare, assegna il codice di triage e indica gli specialisti pertinenti.

DATI PAZIENTE:
{card}

LINEE GUIDA RECUPERATE (forse pertinenti, forse no: valutale tu; ogni passaggio ha il suo riferimento [documento, p. pagina]):
{linee_guida}

LISTA SPECIALISTI E AMBITI DI COMPETENZA:
{specialisti}

REGOLE:
- FATTI E IPOTESI: come fatti usa SOLO i DATI PAZIENTE. Non attribuire al paziente segni, sintomi, durate, terapie o esiti di esami che non ha riferito. Un segno non riferito NON e' assente, e' sconosciuto.
- URGENZA: [TRIAGE_CODES]
- SPECIALISTI: da uno a tre, i piu' pertinenti per i sintomi del paziente. {regola_nomi}

RISPONDI SOLO CON QUESTO JSON (nessun altro testo):
{{"diagnosis": "la tua ipotesi diagnostica preliminare", "urgency_level": "ROSSO" | "ARANCIONE" | "AZZURRO" | "VERDE" | "BIANCO",
 "specialists": ["specialista 1", "specialista 2"], "motivazione": "il ragionamento clinico, in 2-3 frasi"}}
""".replace("[TRIAGE_CODES]", TRIAGE_CODES)


# The bare model is given only what an answer needs to be compared with the others: the patient, the names of the five
# codes and the names of the specialists. No guideline, no definition of the codes, no rule on the facts.
SPECIALIST_NAMES = "\n".join(f'- "{role}" -> {name}' for role, name in SPECIALIST_DISPLAY_NAMES.items())
BARE_PROMPT = """Sei un medico di pronto soccorso. Valuta da solo il paziente: formula un'ipotesi diagnostica preliminare, assegna il codice di triage e indica gli specialisti pertinenti.

DATI PAZIENTE:
{card}

CODICI DI TRIAGE, dal piu' al meno urgente: {codici}.

SPECIALISTI DISPONIBILI:
{specialisti}
Indicane da uno a tre, i piu' pertinenti per i sintomi del paziente. {regola_nomi}

RISPONDI SOLO CON QUESTO JSON (nessun altro testo):
{{"diagnosis": "la tua ipotesi diagnostica preliminare", "urgency_level": "ROSSO" | "ARANCIONE" | "AZZURRO" | "VERDE" | "BIANCO",
 "specialists": ["specialista 1", "specialista 2"], "motivazione": "il ragionamento clinico, in 2-3 frasi"}}
"""


def build_bare_prompt(case: Case) -> str:
    """The bare-model prompt for a case: nothing is retrieved."""
    return BARE_PROMPT.format(card=case.card.model_dump_json(), codici=", ".join(LEVELS),
                              specialisti=SPECIALIST_NAMES, regola_nomi=NAMES_RULE)


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
        specialisti=SPECIALIST_LIST,
        regola_nomi=NAMES_RULE,
    )


async def run_single_call(case: Case, condition: str) -> dict:
    """One request to the active text model, with the prompt of the condition; an unreadable answer gives no code."""
    prompt = await asyncio.to_thread(build_bare_prompt if condition == "bare" else build_prompt, case)
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
