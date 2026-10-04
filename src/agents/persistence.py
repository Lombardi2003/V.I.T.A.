"""Nodes that use the patient database: read_db at the start, save_db at the end, and the fiscal code check."""

import re
from datetime import datetime

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState
from .common import mdb
from .authors import Authors
from src.log import get_logger

log = get_logger("persistence")

# Fiscal code layout; letters LMNPQRSTUV may replace digits (omocodia).
_CF_FORMAT = re.compile(
    r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]"
)
# Check-character value of each symbol in an odd position.
_CF_ODD_VALUES = dict(zip(
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    [1, 0, 5, 7, 9, 13, 15, 17, 19, 21,
     1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23],
))

TEST_FISCAL_CODE = "1234"  # Development code: always a new patient, never saved.
# Start of the diagnosis written when the triage produced no hypothesis.
UNDETERMINED_DIAGNOSIS_PREFIX = "Ipotesi diagnostica non determinata"


def _cf_even_value(char: str) -> int:
    """Check-character value of a symbol in an even position."""
    return int(char) if char.isdigit() else ord(char) - ord("A")


def normalize_fiscal_code(raw: str) -> str:
    """Upper case, with every space removed."""
    return re.sub(r"\s+", "", raw or "").upper()


def is_valid_fiscal_code(cf: str) -> bool:
    """True if format and check character are right (or it is the test code)."""
    if cf == TEST_FISCAL_CODE:
        return True
    if not _CF_FORMAT.fullmatch(cf):
        return False
    total = sum(
        _CF_ODD_VALUES[c] if i % 2 == 0 else _cf_even_value(c)
        for i, c in enumerate(cf[:15])
    )
    return cf[15] == chr(ord("A") + total % 26)


async def read_db_node(state: MedicalState):
    """Validates the fiscal code and loads the patient, or opens a new card."""
    try:
        raw = normalize_fiscal_code(state.general_history[-1].content)
    except (IndexError, AttributeError):
        msg = "Inserire il proprio Codice Fiscale per procedere."
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        return {"next_step": "read_db", "general_history": [AIMessage(content=msg)]}

    if not is_valid_fiscal_code(raw):
        msg = (
            "Il valore inserito non costituisce un Codice Fiscale valido.\n"
            "Deve essere composto da 16 caratteri (formato e carattere di controllo corretti). "
            "Si prega di reinserirlo."
        )
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        return {
            "next_step": "read_db",
            "general_history": [AIMessage(content=msg)],
        }

    record = None
    db_error = None
    async with cl.Step(name="Ricerca Codice Fiscale", type="tool", default_open=False, show_input="text") as step:
        step.input = raw
        try:
            record = mdb.read_patient(raw)
            step.output = (
                f"Paziente trovato: {record.first_name} {record.last_name}"
                if record else
                "Nessun paziente trovato con questo codice fiscale"
            )
        except Exception as e:
            db_error = e
            step.output = f"Errore di connessione al database: {e}"

    # A database error does not loop: go on with a new card, keeping the validated code.
    if db_error:
        msg = "Si è verificato un errore di connessione al database. La procedura prosegue con la creazione di una nuova scheda."
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        log.error("read failed, continuing with a new card: %s", db_error)
        return {
            "patient_card":    {"fiscal_code": raw},
            "patient_exists":  False,
            "next_step":       "intake",
            "general_history": [AIMessage(content=msg)],
        }

    if record:
        msg = f"Scheda clinica recuperata per **{record.first_name} {record.last_name}**."
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        log.info("registered patient found")
        loaded_allergies = getattr(record, "allergies", [])
        loaded_conditions = record.previous_conditions
        return {
            "patient_card": {
                "fiscal_code":         raw,
                "first_name":          record.first_name,
                "last_name":           record.last_name,
                "age":                 record.age,
                "sex":                 getattr(record, "sex", ""),
                "allergies":           loaded_allergies,
                "previous_conditions": loaded_conditions,
            },
            "patient_exists": True,
            # A stored non-empty list counts as addressed; an empty one is ambiguous and is asked again.
            "allergies_addressed":            bool(loaded_allergies),
            "previous_conditions_addressed":  bool(loaded_conditions),
            "next_step":      "intake",
            "general_history": [AIMessage(content=msg)],
        }

    msg = "Codice Fiscale non presente nel sistema: verrà creata una nuova scheda clinica."
    await cl.Message(content=msg, author=Authors.SYSTEM).send()
    log.info("new patient")
    return {
        "patient_card":    {"fiscal_code": raw},
        "patient_exists":  False,
        "next_step":       "intake",
        "general_history": [AIMessage(content=msg)],
    }


async def save_db_node(state: MedicalState):
    """Saves the confirmed card after the report, adding the hypothesis labelled as not confirmed."""
    card = state.patient_card.model_dump()
    cf = card.get("fiscal_code", "").strip()

    if cf == TEST_FISCAL_CODE:
        # The test code is never written to the database.
        msg = "Codice di prova: nessun salvataggio nel database."
        log.info("test code: nothing saved")
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        return {"general_history": [AIMessage(content=msg)]}
    if not cf:
        log.error("no fiscal code: cannot save")
        return {}

    entry = _triage_entry(state)
    conditions = list(card.get("previous_conditions") or [])
    # The same entry is never added twice.
    if entry and entry.lower() not in {str(c).strip().lower() for c in conditions}:
        conditions.append(entry)
    card["previous_conditions"] = conditions

    try:
        # A database error must not lose the report already shown: warn and stop.
        created = mdb.upsert_patient(card)
    except Exception as e:
        msg = ("Salvataggio non riuscito per un errore del database: "
               "la scheda e l'ipotesi di questo accesso non sono state registrate.")
        log.error("save failed: %s", e)
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        return {"general_history": [AIMessage(content=msg)]}

    msg = "Scheda paziente salvata." if created else "Scheda paziente aggiornata."
    if entry:
        msg += " Ipotesi di questo accesso registrata tra le patologie pregresse come non confermata."
    log.info("card %s%s", "created" if created else "updated", ", hypothesis recorded" if entry else "")
    await cl.Message(content=msg, author=Authors.SYSTEM).send()
    return {"patient_card": card, "patient_exists": True, "general_history": [AIMessage(content=msg)]}


def _triage_entry(state: MedicalState) -> str:
    """The entry recording this visit's hypothesis, or "" if there is none."""
    final = state.final_diagnosis
    diagnosis = final.diagnosis.strip().rstrip(".").strip()
    if not diagnosis or diagnosis.startswith(UNDETERMINED_DIAGNOSIS_PREFIX):
        return ""
    today = datetime.now().strftime("%d/%m/%Y")
    return f"Ipotesi al triage del {today}: {diagnosis} (codice {final.urgency_level}, non confermata)"
