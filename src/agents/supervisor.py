"""Supervisor node: chooses which specialists discuss the case. It gives no diagnosis."""

import asyncio
import json

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState
from .prompts import SUPERVISOR_PROMPT
from .common import extract_json, stream_response
from .authors import Authors
from .roundtable import SPECIALIST_DISPLAY_NAMES, _role_from_name
from src.log import get_logger

log = get_logger("supervisor")

MAX_SELECTED_SPECIALISTS = 3  # More specialists make the discussion long and leave each only a couple of turns.

SECOND_OPINION_ROLE = "general_practitioner"  # Added when a single specialist was chosen.


def _roles_from(value) -> list[str]:
    """Valid roles from the model's list, in order and without duplicates; Italian names are understood."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    roles = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("name") or item.get("role") or item.get("specialist") or next(iter(item.values()), "")
        role = _role_from_name(item)
        if role and role not in roles:
            roles.append(role)
    return roles


def _select_specialists(data: dict) -> list[str]:
    """The specialists to seat: the model's list merged with those named symptom by symptom."""
    final = _roles_from(data.get("specialists"))
    per_symptom = data.get("per_symptom_analysis")
    per_symptom = per_symptom if isinstance(per_symptom, list) else []
    per_symptom_roles = [_roles_from(item.get("specialists")) for item in per_symptom if isinstance(item, dict)]

    candidates = list(final)
    for roles in per_symptom_roles:
        candidates += [r for r in roles if r not in candidates]
    if len(candidates) <= MAX_SELECTED_SPECIALISTS:
        return candidates

    # Above the cap: one specialist per symptom first, so no symptom is left uncovered.
    selected = []
    for roles in per_symptom_roles:
        first = next((r for r in roles if r in final), roles[0] if roles else None)
        if first and first not in selected:
            selected.append(first)
    selected = selected[:MAX_SELECTED_SPECIALISTS]
    selected += [r for r in candidates if r not in selected][:MAX_SELECTED_SPECIALISTS - len(selected)]
    log.info("%s specialists proposed, %s kept: %s", len(candidates), MAX_SELECTED_SPECIALISTS, selected)
    return selected


async def supervisor_node(state: MedicalState):
    """Chooses the specialists, with a fallback to the general practitioner if the choice fails."""
    card = state.patient_card
    photo = card.symptom.photo
    card_str = card.model_dump_json()
    photo_str = photo.model_dump_json() if photo else "Nessuna foto."

    prompt = SUPERVISOR_PROMPT.format(patient_card=card_str, photo_analysis=photo_str)
    selected_specialists = ["general_practitioner"]

    async with cl.Step(name="Smistamento clinico", type="tool", default_open=False, show_input="text") as step:
        step.input = card_str
        try:
            # The model call blocks: run it in a thread so the interface stays responsive.
            content = await asyncio.to_thread(stream_response, prompt)
        # A failed call is handled like an unreadable answer: fall back to the general practitioner.
        except Exception as e:
            log.warning("model call failed, falling back to the general practitioner: %s", e)
            content = ""
        step.output = content

    routing_failed = False
    try:
        data = extract_json(content)

        clean_specs = _select_specialists(data)
        if clean_specs:
            selected_specialists = clean_specs

        log.info("selected: %s", selected_specialists)

    except json.JSONDecodeError:
        routing_failed = True
        log.warning("no readable answer, falling back to the general practitioner")

    names = ", ".join(SPECIALIST_DISPLAY_NAMES.get(s, s) for s in selected_specialists)
    plural = len(selected_specialists) > 1
    verb = "Verranno coinvolti in consulto" if plural else "Verrà coinvolto in consulto"
    msg = f"{verb}: **{names}**."
    if routing_failed:
        msg = f"Smistamento automatico non disponibile per un errore tecnico: {verb.lower()} **{names}**."

    second_opinion_role = ""
    # A lone specialist would only re-read itself: add the general practitioner, and say so in the chat.
    if len(selected_specialists) == 1 and selected_specialists[0] != SECOND_OPINION_ROLE:
        second_opinion_role = SECOND_OPINION_ROLE
        selected_specialists = selected_specialists + [SECOND_OPINION_ROLE]
        log.info("single specialist: %s added for a second opinion", SECOND_OPINION_ROLE)
        msg = (f"Verrà coinvolto in consulto: **{names}**, con "
               f"**{SPECIALIST_DISPLAY_NAMES[SECOND_OPINION_ROLE]}** per un secondo parere.")
    await cl.Message(content=msg, author=Authors.SUPERVISOR).send()

    checklist = {specialist: True for specialist in selected_specialists}
    log.debug("table: %s", checklist)
    return {
        "needed_specialists": checklist,
        "second_opinion_role": second_opinion_role,
        "general_history": [AIMessage(content=msg)],
    }
