"""Reviewer node: collects the symptoms and has the operator confirm them."""

import asyncio
import json
import re

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState, PatientCard
from .prompts import REVIEWER_PROMPT
from .common import stream_response, extract_json, as_list, is_yes, _mentions
from .authors import Authors
from src.log import get_logger

log = get_logger("reviewer")


def _format_symptoms(card: PatientCard) -> str:
    """The symptoms shown to the operator at every turn, one block each."""
    blocks = []
    for i, s in enumerate(card.symptom.symptoms, start=1):
        parts = [
            s.description.strip() or "—",
            f"**Intensità** {s.intensity.strip() or 'da indicare'}",
            f"**Durata** {s.duration.strip() or 'da indicare'}",
        ]
        if s.characteristics.strip():
            parts.append(f"**Caratteristiche** {s.characteristics.strip()}")
        if s.trigger.strip():
            parts.append(f"**Circostanze** {s.trigger.strip()}")
        blocks.append(f"**Sintomo {i}**\n" + " - ".join(parts))
    return "\n".join(blocks)


async def reviewer_node(state: MedicalState):
    """One reviewer turn: read the answer, update the symptoms, ask what is missing or for confirmation."""
    # A list, not a set: the order is shown to the operator.
    VALID_INTENSITY_VALUES = ["lieve", "moderata", "forte", "insopportabile"]

    # Anti-invention check: an intensity or duration with no matching word in the message is discarded.
    INTENSITY_KEYWORDS = ["liev", "legger", "modest", "moderat", "fort", "intens", "insopportabil", "grave", "acut"]
    DURATION_PATTERN = re.compile(
        r"\b(giorn\w*|settiman\w*|minut\w*|mes[ei]|or[ae]|ann[oi]|\d+\s*h|"
        r"stanotte|stamattina|stamani|stasera|stamane|ieri|oggi|adesso|poco|"
        r"mattina|pomeriggio|sera|notte|da quando)\b",
        re.IGNORECASE,
    )

    def _is_complete(s: dict) -> bool:
        """True if the symptom has a valid intensity and a duration."""
        return s["intensity"].strip().lower() in VALID_INTENSITY_VALUES and bool(s["duration"].strip())

    def _symptom_mentioned(description: str, text_lower: str) -> bool:
        """True if the message contains a word of this symptom's description."""
        words = [w for w in re.findall(r"\w+", description.lower()) if len(w) >= 4]
        if not words:
            # Description too short for a reliable check.
            return True
        return any(w in text_lower for w in words)

    def _missing_fields(card: PatientCard) -> list[str]:
        """What still has to be asked."""
        missing = []
        if not card.symptom.symptoms:
            missing.append("almeno un sintomo")
        for s in card.symptom.symptoms:
            if s.intensity.strip().lower() not in VALID_INTENSITY_VALUES:
                missing.append(f'intensità di "{s.description}"')
            if not s.duration.strip():
                missing.append(f'durata di "{s.description}"')
        return missing

    CONFIRM_REQUEST = "Confermi i dati? Altrimenti indicare cosa correggere."

    def _reply_for(card: PatientCard) -> str:
        """The symptoms plus what is missing, or the confirmation request."""
        missing = _missing_fields(card)
        if not card.symptom.symptoms:
            return "Descrivere i sintomi: natura del disturbo, intensità e durata."
        symptoms_text = _format_symptoms(card)
        if missing:
            reply = f"{symptoms_text}\n\nMancano: {', '.join(missing)}."
            if any(m.startswith("intensità") for m in missing):
                reply += f"\nIntensità: {', '.join(VALID_INTENSITY_VALUES[:-1])} o {VALID_INTENSITY_VALUES[-1]}."
            return reply
        return f"{symptoms_text}\n\n{CONFIRM_REQUEST}"

    current_card: PatientCard = state.patient_card

    # First pass, right after intake: nothing was written yet, so ask for the symptoms without calling the model.
    if not state.reviewer_card_shown:
        reply = _reply_for(current_card)
        log.info("symptoms requested (first pass, no model call)")
        await cl.Message(content=reply, author=Authors.REVIEWER).send()
        return {
            "triage_history":      [AIMessage(content=reply)],
            "general_history":     [AIMessage(content=reply)],
            "reviewer_card_shown": True,
            "next_step":           "reviewer",
        }

    # The symptoms were already complete: this message answers the confirmation request.
    awaiting_confirmation = not _missing_fields(current_card)
    user_msg = state.triage_history[-1].content if state.triage_history else ""

    prompt = REVIEWER_PROMPT.format(
        patient_card=current_card.model_dump_json(indent=2),
        awaiting_confirmation=awaiting_confirmation,
        user_input=user_msg
    )
    async with cl.Step(name="Analisi sintomi", type="tool", default_open=False, show_input="text") as step:
        step.input = user_msg
        content = await asyncio.to_thread(stream_response, prompt)
        step.output = content

    try:
        data = extract_json(content)
        # Only the symptoms are read; any level may be null or a text, which means no update.
        updated_card = data.get("updated_card")
        symptom = updated_card.get("symptom") if isinstance(updated_card, dict) else None
        extracted_list = symptom.get("symptoms") if isinstance(symptom, dict) else None
        if not isinstance(extracted_list, list):
            extracted_list = []
        llm_reply: str = data.get("message_to_user", "")
        confirmed_by_llm = awaiting_confirmation and is_yes(data.get("conferma"))
        to_remove = as_list(data.get("symptoms_to_remove"))
    except json.JSONDecodeError:
        extracted_list = []
        llm_reply = ""
        confirmed_by_llm = False
        to_remove = []

    symptoms = [s.model_dump() for s in current_card.symptom.symptoms]
    incomplete_before = [s["description"].strip().lower() for s in symptoms if not _is_complete(s)]
    user_msg_lower = user_msg.lower()

    # An item updates the symptom with the same description, otherwise it is a new symptom.
    for item in extracted_list:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description", "")).strip()
        if not desc:
            continue

        intensity = str(item.get("intensity", "")).strip()
        duration = str(item.get("duration", "")).strip()
        trigger = str(item.get("trigger", "")).strip()
        characteristics = str(item.get("characteristics", "")).strip()

        if intensity.lower() == "moderato":
            intensity = "moderata"
        if intensity and not _mentions(user_msg, INTENSITY_KEYWORDS):
            log.warning("intensity discarded: no matching word in the message")
            intensity = ""
        if duration and not DURATION_PATTERN.search(user_msg):
            log.warning("duration discarded: no matching word in the message")
            duration = ""

        existing = next((s for s in symptoms if s["description"].strip().lower() == desc.lower()), None)
        if existing:
            # With several symptoms, an update must name its symptom, or it could land on the wrong one.
            is_only_incomplete = incomplete_before == [desc.lower()]
            is_only_symptom = len(current_card.symptom.symptoms) == 1
            if not (is_only_incomplete or is_only_symptom) and not _symptom_mentioned(desc, user_msg_lower):
                log.warning("update discarded: the message does not name the symptom and there are others")
                continue
            if intensity:
                existing["intensity"] = intensity
            if duration:
                existing["duration"] = duration
            if trigger:
                existing["trigger"] = trigger
            if characteristics:
                existing["characteristics"] = characteristics
        else:
            symptoms.append({"description": desc, "intensity": intensity, "duration": duration,
                             "trigger": trigger, "characteristics": characteristics})

    # Explicit removals; the model may write an entry as an object instead of a text.
    remove = set()
    for x in to_remove:
        if isinstance(x, dict):
            x = x.get("description") or next(iter(x.values()), "")
        if str(x).strip():
            remove.add(str(x).strip().lower())
    if remove:
        symptoms = [s for s in symptoms if s["description"].strip().lower() not in remove]

    merged_dict = current_card.model_dump()
    merged_dict["symptom"]["symptoms"] = symptoms
    try:
        merged_card = PatientCard(**merged_dict)
    except Exception as e:
        log.warning("invalid data from the model, update discarded: %s", e)
        # Invalid data from the model: keep the previous card.
        merged_card = current_card

    missing = _missing_fields(merged_card)
    # A confirmation with a change in the same message ("yes, but...") is a correction, not a confirmation.
    symptoms_changed = merged_card.symptom.symptoms != current_card.symptom.symptoms
    triage_complete = not missing and confirmed_by_llm and not symptoms_changed

    if triage_complete:
        reply = "Dati clinici confermati."
    else:
        reply = _reply_for(merged_card)
        if llm_reply:
            log.debug("model said: %s", llm_reply)

    log.info("confirmed=%s | missing=%s", triage_complete, len(missing))
    log.debug("card: %s", merged_card.model_dump_json())
    await cl.Message(content=reply, author=Authors.REVIEWER).send()

    return {
        "patient_card":    merged_card.model_dump(),
        "triage_history":  [AIMessage(content=reply)],
        "general_history": [AIMessage(content=reply)],
        "triage_complete": triage_complete,
        "symptoms_confirmed": triage_complete,
        "next_step": "photography" if triage_complete else "reviewer",
    }
