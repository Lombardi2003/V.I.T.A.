"""Intake node: collects the patient's personal data and has the operator confirm it."""

import asyncio
import json
import re

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState, PatientCard
from .prompts import INTAKE_PROMPT
from .common import stream_response, extract_json, as_list, is_yes, _mentions
from .authors import Authors
from src.log import get_logger

log = get_logger("intake")


def _format_card(card: PatientCard, allergies_addressed: bool, previous_conditions_addressed: bool) -> str:
    """The compact card shown to the operator at every turn."""
    def _list(items: list[str], addressed: bool) -> str:
        """A list as text: "nessuna" if the topic was addressed, "da indicare" otherwise."""
        if items:
            return ", ".join(items)
        return "nessuna" if addressed else "da indicare"

    name = f"{card.first_name.strip()} {card.last_name.strip()}".strip()
    age = card.age.strip()
    if age and age.isdigit():
        age = f"{age} anni"
    parts = [f"**CF** {card.fiscal_code.strip() or '—'}"]
    if name:
        parts.append(f"**Paziente** {name}")
    if age:
        parts.append(f"**Età** {age}")
    if card.sex.strip():
        parts.append(f"**Sesso** {card.sex.strip()}")

    lines = ["**Scheda paziente**", " · ".join(parts)]
    if card.allergies or allergies_addressed or card.previous_conditions or previous_conditions_addressed \
            or len(parts) > 1:
        lines.append(
            f"**Allergie** {_list(card.allergies, allergies_addressed)} · "
            f"**Patologie pregresse** {_list(card.previous_conditions, previous_conditions_addressed)}"
        )
    return "\n".join(lines)


# Accepted spellings for each stored value.
_SEX_VALUES = {
    "uomo": {"m", "maschio", "uomo", "maschile", "male"},
    "donna": {"f", "femmina", "donna", "femminile", "female"},
}


def _capitalize_name(text: str) -> str:
    """Capital initial for every part of a name; mixed-case parts are left as written."""
    def _part(p: str) -> str:
        """One part of the name, capitalised unless already in mixed case."""
        return p.capitalize() if p.islower() or p.isupper() else p
    return re.sub(r"[^\s'\-]+", lambda m: _part(m.group(0)), text.strip())


def _is_minor(age: str) -> bool:
    """True if the age is under 18 or given in months, weeks or days."""
    age = age.strip().lower()
    match = re.match(r"(\d{1,3})", age)
    if not match:
        return False
    return any(u in age for u in ("mes", "giorn", "settiman")) or int(match.group(1)) < 18


def _normalize_card(card: PatientCard) -> PatientCard:
    """Uniform values in the card itself: sex, and capital initials in the names."""
    sex = card.sex.strip()
    for code, words in _SEX_VALUES.items():
        if sex.lower() in words:
            sex = code
    if _is_minor(card.age):
        sex = {"uomo": "maschio", "donna": "femmina"}.get(sex, sex)
    return card.model_copy(update={
        "sex": sex,
        "first_name": _capitalize_name(card.first_name),
        "last_name": _capitalize_name(card.last_name),
    })


async def intake_node(state: MedicalState):
    """One intake turn: read the answer, update the card, ask what is missing or for confirmation."""
    def _missing_fields(card: PatientCard, allergies_addressed: bool, previous_conditions_addressed: bool) -> list[str]:
        """What still has to be asked."""
        missing = []
        if not card.first_name.strip():
            missing.append("nome")
        if not card.last_name.strip():
            missing.append("cognome")
        if not card.age.strip():
            missing.append("età")
        if not card.sex.strip():
            missing.append("sesso")
        if not allergies_addressed:
            missing.append("allergie")
        if not previous_conditions_addressed:
            missing.append("patologie pregresse")
        return missing

    def _merge(base: dict, update: dict) -> dict:
        """Applies the new values to the card, ignoring empty ones."""
        for k, v in update.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = _merge(base[k], v)
            # An empty value from the model never erases what is already known.
            elif v not in (None, "", []):
                base[k] = v
        return base

    def _sanitize_string_list(value):
        """List items as plain text, even if the model wrote objects."""
        if not isinstance(value, list):
            return value
        cleaned = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    cleaned.append(item)
            elif isinstance(item, dict):
                text = item.get("name") or item.get("nome") or item.get("value") or next(iter(item.values()), None)
                if text:
                    cleaned.append(str(text))
            elif item is not None:
                cleaned.append(str(item))
        return cleaned

    # Safety net: these words mark the topic as addressed even when the model misses it.
    ALLERGY_KEYWORDS = ["allerg"]
    CONDITION_KEYWORDS = ["patolog", "pregress", "malatt"]

    CONFIRM_REQUEST = "Confermi i dati? Altrimenti indicare cosa correggere."

    def _reply_for(card: PatientCard, allergies_addressed: bool, previous_conditions_addressed: bool) -> str:
        """The card plus what is missing, or the confirmation request."""
        missing = _missing_fields(card, allergies_addressed, previous_conditions_addressed)
        card_text = _format_card(card, allergies_addressed, previous_conditions_addressed)
        if missing:
            return f"{card_text}\n\nMancano: {', '.join(missing)}."
        return f"{card_text}\n\n{CONFIRM_REQUEST}"

    current_card: PatientCard = _normalize_card(state.patient_card)

    # First pass, right after read_db: nothing was written yet, so show the card without calling the model.
    if not state.intake_card_shown:
        reply = _reply_for(current_card, state.allergies_addressed, state.previous_conditions_addressed)
        log.info("card shown (first pass, no model call)")
        await cl.Message(content=reply, author=Authors.INTAKE).send()
        return {
            "patient_card":      current_card.model_dump(),
            "triage_history":    [AIMessage(content=reply)],
            "general_history":   [AIMessage(content=reply)],
            "intake_card_shown": True,
            "next_step":         "intake",
        }

    # The card was already complete: this message answers the confirmation request.
    awaiting_confirmation = not _missing_fields(
        current_card, state.allergies_addressed, state.previous_conditions_addressed
    )
    user_msg = state.triage_history[-1].content if state.triage_history else ""
    allergies_mentioned = _mentions(user_msg, ALLERGY_KEYWORDS)
    previous_conditions_mentioned = _mentions(user_msg, CONDITION_KEYWORDS)

    prompt = INTAKE_PROMPT.format(
        patient_card=current_card.model_dump_json(),
        allergies_addressed=state.allergies_addressed,
        previous_conditions_addressed=state.previous_conditions_addressed,
        awaiting_confirmation=awaiting_confirmation,
        user_input=user_msg,
    )
    async with cl.Step(name="Analisi dati anagrafici", type="tool", default_open=False, show_input="text") as step:
        step.input = user_msg
        # The model call blocks: run it in a thread so the interface stays responsive.
        content = await asyncio.to_thread(stream_response, prompt)
        step.output = content

    # The model may change these fields only: never the fiscal code or the symptoms.
    EDITABLE_FIELDS = ("first_name", "last_name", "age", "sex", "allergies", "previous_conditions")

    try:
        data = extract_json(content)
        extracted = data.get("updated_card")
        if not isinstance(extracted, dict):
            extracted = {}
        extracted = {k: v for k, v in extracted.items() if k in EDITABLE_FIELDS}
        if "allergies" in extracted:
            extracted["allergies"] = _sanitize_string_list(as_list(extracted["allergies"]))
        if "previous_conditions" in extracted:
            extracted["previous_conditions"] = _sanitize_string_list(as_list(extracted["previous_conditions"]))
        llm_reply: str = data.get("message_to_user", "")
        # Once addressed, always addressed, whatever the model says later.
        allergies_addressed = state.allergies_addressed or bool(data.get("allergies_addressed", False)) or allergies_mentioned
        previous_conditions_addressed = state.previous_conditions_addressed or bool(data.get("previous_conditions_addressed", False)) or previous_conditions_mentioned
        # A confirmation counts only if it had been asked for.
        confirmed_by_llm = awaiting_confirmation and is_yes(data.get("conferma"))
        to_remove = {
            "allergies": _sanitize_string_list(as_list(data.get("allergies_to_remove"))),
            "previous_conditions": _sanitize_string_list(as_list(data.get("previous_conditions_to_remove"))),
        }
    except json.JSONDecodeError:
        extracted = {}
        llm_reply = ""
        allergies_addressed = state.allergies_addressed or allergies_mentioned
        previous_conditions_addressed = state.previous_conditions_addressed or previous_conditions_mentioned
        confirmed_by_llm = False
        to_remove = {"allergies": [], "previous_conditions": []}

    # Lists accumulate across turns (duplicates dropped ignoring case); single values are replaced.
    for list_field in ("allergies", "previous_conditions"):
        new_items = extracted.get(list_field)
        if isinstance(new_items, list) and new_items:
            existing_items = getattr(current_card, list_field)
            seen = {str(x).strip().lower() for x in existing_items}
            added = []
            for x in new_items:
                key = str(x).strip().lower()
                if key not in seen:
                    seen.add(key)
                    added.append(x)
            extracted[list_field] = existing_items + added

    merged_dict = _merge(current_card.model_dump(), extracted)

    # Explicit removals: lists accumulate, so a wrong entry could not be taken out otherwise.
    for list_field, items in to_remove.items():
        remove = {str(x).strip().lower() for x in items if str(x).strip()}
        if remove and isinstance(merged_dict.get(list_field), list):
            merged_dict[list_field] = [x for x in merged_dict[list_field] if str(x).strip().lower() not in remove]
    try:
        merged_card = _normalize_card(PatientCard(**merged_dict))
    except Exception as e:
        log.warning("invalid data from the model, update discarded: %s", e)
        # Invalid data from the model: keep the previous card.
        merged_card = current_card

    missing = _missing_fields(merged_card, allergies_addressed, previous_conditions_addressed)
    intake_complete = len(missing) == 0
    # A confirmation with a change in the same message ("yes, but...") is a correction, not a confirmation.
    card_changed = merged_card.model_dump() != current_card.model_dump()
    card_confirmed = intake_complete and confirmed_by_llm and not card_changed

    if card_confirmed:
        reply = "Dati anagrafici confermati."
    else:
        reply = _reply_for(merged_card, allergies_addressed, previous_conditions_addressed)
        if llm_reply:
            log.debug("model said: %s", llm_reply)

    log.info("complete=%s | confirmed=%s | missing=%s", intake_complete, card_confirmed, missing)
    log.debug("card: %s", merged_card.model_dump_json())
    await cl.Message(content=reply, author=Authors.INTAKE).send()

    return {
        "patient_card":    merged_card.model_dump(),
        "triage_history":  [AIMessage(content=reply)],
        "general_history": [AIMessage(content=reply)],
        "allergies_addressed": allergies_addressed,
        "previous_conditions_addressed": previous_conditions_addressed,
        "card_confirmed": card_confirmed,
        "next_step": "reviewer" if card_confirmed else "intake",
    }
