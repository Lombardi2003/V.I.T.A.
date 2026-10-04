"""Specialist node: one turn at the round table, and the ten nodes that call it."""

import asyncio
import json

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState, RoundTableEntry, GroupHypothesis
from .prompts import SPECIALIST_PROMPT
from .common import extract_json, stream_response, as_list, as_text, is_no, is_yes
from .authors import Authors
from .roundtable import (
    SPECIALIST_DISPLAY_NAMES, _format_round_table, _parse_urgency, _pediatric_note, _role_from_name,
)
from src.rag.retriever import build_queries, retrieve
from src.log import get_logger

log = get_logger("specialist")


def _failed_turn(state: MedicalState, role: str) -> dict:
    """State update for a failed turn: only the failure count changes."""
    failed = dict(state.failed_turns)
    failed[role] = failed.get(role, 0) + 1
    return {"failed_turns": failed}


def _format_group_hypothesis(gh: GroupHypothesis | None) -> str:
    """The current group hypothesis, in full, as text for the prompt."""
    if gh is None:
        return (
            'Nessuna ipotesi ancora proposta - sei il primo a parlare. Usa "azione": "proponi" '
            'per aprire tu la discussione, oppure "consulta" se preferisci un parere di un '
            "collega assente PRIMA di sbilanciarti con una tua ipotesi."
        )
    confirmed_names = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in gh.confirmed_by) or "nessuno ancora"
    return (
        f"Diagnosi: {gh.diagnosis}\n"
        f"Urgenza: {gh.urgency_level}\n"
        f"Esami consigliati: {', '.join(gh.recommended_exams) or 'nessuno indicato'}\n"
        f"Dettagli: {gh.details}\n"
        f"Alternativa considerata e scartata dal tavolo: {gh.discarded_alternative or '(nessuna)'}"
        f"{f' ({gh.discard_reason})' if gh.discard_reason else ''}\n"
        f"Proposta/rivista per ultimo da: {SPECIALIST_DISPLAY_NAMES.get(gh.last_updated_by, gh.last_updated_by)}\n"
        f"Confermata finora da: {confirmed_names}"
    )


# Answer fields that must be plain text.
_SPECIALIST_TEXT_FIELDS = (
    "azione", "diagnosi", "dettagli", "motivazione", "message", "valutazione_indipendente",
    "ipotesi_alternativa_scartata", "motivo_scarto", "domanda_per_il_collega", "fonti_consultate", "urgenza",
)


def _one_name(value) -> str:
    """A single name, even if the model wrote a list or an object."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("name") or value.get("role") or value.get("specialist") or next(iter(value.values()), "")
    return as_text(value)


def _normalize_specialist_answer(data: dict) -> dict:
    """The answer with every field brought back to the type the node expects."""
    data = dict(data)
    for field in _SPECIALIST_TEXT_FIELDS:
        if field in data:
            data[field] = as_text(data[field])
    for field in ("consulto_utile", "coincide_con_gruppo"):
        if field in data:
            value = data[field]
            data[field] = "si" if is_yes(value) else "no" if is_no(value) else as_text(value).lower()
    for field in ("to", "collega_da_consultare"):
        if field in data:
            data[field] = _one_name(data[field]) or None
    if "esami_consigliati" in data:
        exams = data["esami_consigliati"]
        if isinstance(exams, dict):
            exams = list(exams.values())
        data["esami_consigliati"] = [t for t in (as_text(e) for e in as_list(exams)) if t]
    return data


async def specialist_node(state: MedicalState, role: str):
    """One turn: propose, confirm or revise the group hypothesis, or ask a colleague for a consult."""
    display_name = SPECIALIST_DISPLAY_NAMES.get(role, role)
    author = getattr(Authors, role.upper(), Authors.SYSTEM)

    card_str = state.patient_card.model_dump_json()
    table_text = _format_round_table(state.round_table)
    hypothesis_text = _format_group_hypothesis(state.group_hypothesis)

    pending_consult = ""
    if state.round_table:
        last = state.round_table[-1]
        # The last entry addressed this specialist: the turn must answer it first.
        if last.to == role:
            asker = SPECIALIST_DISPLAY_NAMES.get(last.author, last.author)
            is_question = last.azione == "consulta"
            pending_consult = (
                f'ATTENZIONE: {asker} ti ha appena rivolto '
                f'{"un mini-consulto con una domanda SPECIFICA" if is_question else "una considerazione specifica, indirizzata a te"}: '
                f'"{last.content}". Il tuo turno DEVE rispondere '
                f'ESPLICITAMENTE e per primo a questo punto (nel campo "dettagli"/"message"), '
                f"prima di qualsiasi altra cosa."
            )

    # Final verification round: say whether reading the colleagues changed the assessment.
    is_verification = state.verifying_role == role
    verification_instruction = ""
    if is_verification:
        verification_instruction = (
            "GIRO DI VERIFICA FINALE: tutti gli specialisti al tavolo hanno confermato l'ipotesi di "
            "gruppo attuale. Prima della chiusura, rileggi con attenzione TUTTA la discussione qui "
            "sopra, in particolare cio' che hanno detto i colleghi dopo il tuo ultimo intervento. "
            "Alla luce dei loro interventi, la tua valutazione e' cambiata? Se si', usa \"rivedi\" "
            "e spiega in \"motivazione\" quale intervento di quale collega ti ha fatto cambiare idea. "
            "Se no, usa \"conferma\" e in \"motivazione\" indica quale punto sollevato dai colleghi "
            "hai considerato e perche' non cambia la tua valutazione - non limitarti a ripetere "
            "che sei d'accordo."
        )

    second_opinion_instruction = ""
    # Seated for a second opinion: the prompt says why.
    if role == state.second_opinion_role:
        colleague = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in state.needed_specialists if r != role)
        second_opinion_instruction = (
            f"SECONDO PARERE: sei al tavolo per un secondo parere, perche' per questo caso era stato "
            f"scelto un solo specialista ({colleague}). Rileggi il caso nel suo insieme (eta', patologie "
            "pregresse, tutti i sintomi) e controlla che l'ipotesi del collega sia sostenuta dai DATI "
            "PAZIENTE: se lo e', confermala spiegando perche'; se no (un dato non riferito dato per "
            "acquisito, un codice di urgenza non giustificato, una spiegazione piu' semplice trascurata), "
            "usa \"rivedi\"."
        )

    # Retrieval always runs: one query per symptom, plus the question addressed to this specialist.
    queries = build_queries(
        display_name,
        [s.description for s in state.patient_card.symptom.symptoms],
        extra=state.round_table[-1].content if pending_consult and state.round_table else "",
    )
    guideline_chunks = await asyncio.to_thread(retrieve, queries, role)
    guideline_text = (
        "\n\n".join(f"- [{chunk.citation}] {chunk.text}" for chunk in guideline_chunks)
        if guideline_chunks
        else "Nessuna linea guida pertinente trovata nel database."
    )
    log.info("%s: %s guideline chunks retrieved", role, len(guideline_chunks))
    for i, chunk in enumerate(guideline_chunks, 1):
        log.debug("  %s. [%s] %s...", i, chunk.citation, chunk.text[:150])

    prompt = SPECIALIST_PROMPT.format(
        role_display=display_name,
        role=role,
        card=card_str,
        round_table=table_text,
        hypothesis=hypothesis_text,
        consulto_pendente="\n\n".join(t for t in (_pediatric_note(state.patient_card), pending_consult,
                                                    second_opinion_instruction, verification_instruction) if t),
        linee_guida=guideline_text,
    )

    try:
        async with cl.Step(name=display_name, type="tool", default_open=False, show_input="text") as step:
            step.input = table_text
            # The model call blocks: run it in a thread so the interface stays responsive.
            content = await asyncio.to_thread(stream_response, prompt)
            step.output = content
    except Exception as e:
        # An API error that survives the retries is a failed turn, not a crash.
        log.warning("%s: API error, failed turn: %s", role, e)
        return _failed_turn(state, role)

    try:
        data = _normalize_specialist_answer(extract_json(content))
        action = str(data.get("azione", "")).lower().strip()
    # An unreadable answer is a failed turn: it must never be read as a confirmation.
    except json.JSONDecodeError:
        log.warning("%s: unreadable answer, failed turn", role)
        return _failed_turn(state, role)

    requested_for = ""
    # Mandatory field: if an absent colleague's opinion would help, a consult is added to this turn.
    consult_useful = str(data.get("consulto_utile", "")).strip().lower() == "si"
    raw_colleague = str(data.get("collega_da_consultare") or "").strip().lower()
    colleague = _role_from_name(raw_colleague)
    if colleague == role:
        colleague = None
    # A role the system does not have: the question goes to the general practitioner.
    if consult_useful and raw_colleague and not colleague:
        log.info("%s: consult asked to %r (not available) -> general_practitioner", role, raw_colleague)
        colleague = "general_practitioner" if role != "general_practitioner" else None
        if colleague:
            requested_for = str(data.get("collega_da_consultare") or "").strip()
    forced_consult_to = None
    # The consult is added to the specialist's own action, it does not replace it.
    if consult_useful and colleague and action != "consulta":
        log.info("%s: consult to %s, added to its own action", role, colleague)
        forced_consult_to = colleague

    if action == "consulta":
        raw_to = str(data.get("to") or "").strip()
        # Same redirection for an explicit consult; if impossible, the answer counts as a normal turn.
        consult_target = _role_from_name(raw_to)
        if not consult_target or consult_target == role:
            if raw_to and role != "general_practitioner":
                log.info("%s: consult asked to %r (not available) -> general_practitioner", role, raw_to)
                data = {**data, "to": "general_practitioner"}
                requested_for = raw_to
            else:
                action = "conferma" if state.group_hypothesis is not None else "proponi"
                log.info("%s: consult with no possible recipient: the answer counts as %r", role, action)
                if action == "proponi" and not str(data.get("diagnosi", "")).strip():
                    log.warning("%s: nothing to propose, failed turn", role)
                    return _failed_turn(state, role)

    # An action that does not fit the context falls back to the only valid one.
    has_hypothesis = state.group_hypothesis is not None
    if action not in ("proponi", "conferma", "rivedi", "consulta"):
        action = "conferma" if has_hypothesis else "proponi"
    elif action == "proponi" and has_hypothesis:
        action = "conferma"
    elif action in ("conferma", "rivedi") and not has_hypothesis:
        action = "proponi"

    independent_assessment = str(data.get("valutazione_indipendente", "")).strip()
    # Anti-anchoring: an independent assessment that differs turns a confirmation into a revision.
    if str(data.get("coincide_con_gruppo", "")).strip().lower() == "no" and action == "conferma":
        log.info("%s: independent assessment differs -> turned into a revision", role)
        action = "rivedi"
        if not str(data.get("diagnosi", "")).strip() and independent_assessment:
            data = {**data, "diagnosi": independent_assessment}

    # With no diagnosis to propose, the turn stays a plain consult.
    if forced_consult_to and action == "proponi" and not str(data.get("diagnosi", "")).strip():
        action = "consulta"
        data = {**data, "to": forced_consult_to, "message": data.get("domanda_per_il_collega") or ""}
        forced_consult_to = None

    target = _role_from_name(data.get("to"))
    if target == role:
        target = None

    reasoning = str(data.get("motivazione", "")).strip()
    message = str(data.get("message", "")).strip()
    alternative = str(data.get("ipotesi_alternativa_scartata", "")).strip()
    discard_reason = str(data.get("motivo_scarto", "")).strip()

    if action == "consulta":
        if not target:
            log.warning("%s: consult with no valid recipient, failed turn", role)
            return _failed_turn(state, role)
        entry, msg_text = await _send_consult(
            role, display_name, author, target, message or reasoning or "(nessuna domanda specificata)",
            requested_for,
        )
        return {
            "round_table": [entry],
            "general_history": [AIMessage(content=msg_text)],
        }

    if state.round_table:
        last = state.round_table[-1]
        # The answer to a consult always goes back to whoever asked.
        if last.azione == "consulta" and last.to == role and last.author != role:
            target = last.author
    # No recipient given: address the last colleague who spoke, marked as not explicit.
    target_explicit = bool(target)
    if not target:
        for prev in reversed(state.round_table):
            if prev.author != role:
                target = prev.author
                break

    parts = []
    if reasoning:
        parts.append(reasoning)
    if message:
        parts.append(message)
    if alternative:
        discard_text = f" ({discard_reason})" if discard_reason else ""
        parts.append(f"Ho considerato anche '{alternative}' ma l'ho esclusa{discard_text}.")
    content_msg = " — ".join(parts)

    prev_gh = state.group_hypothesis
    stated_urgency = _parse_urgency(data.get("urgenza"))
    exams = data.get("esami_consigliati") or []
    if isinstance(exams, str):
        exams = [exams]
    exams = [str(e) for e in exams if str(e).strip()]
    data = {**data, "esami_consigliati": exams}
    if action == "proponi":
        gh = GroupHypothesis(
            diagnosis=str(data.get("diagnosi", "")).strip() or "Diagnosi non determinata",
            urgency_level=stated_urgency or "BIANCO",
            recommended_exams=data.get("esami_consigliati", []),
            details=str(data.get("dettagli", "")).strip(),
            discarded_alternative=alternative,
            discard_reason=discard_reason,
            last_updated_by=role,
            confirmed_by=[role],
        )
        content_msg = content_msg or gh.diagnosis
    # A revision clears the confirmations: the others must confirm the new version.
    elif action == "rivedi":
        gh = GroupHypothesis(
            diagnosis=str(data.get("diagnosi", "")).strip() or prev_gh.diagnosis,
            urgency_level=stated_urgency or prev_gh.urgency_level,
            recommended_exams=data.get("esami_consigliati") or prev_gh.recommended_exams,
            details=str(data.get("dettagli", "")).strip() or prev_gh.details,
            discarded_alternative=alternative or prev_gh.discarded_alternative,
            discard_reason=discard_reason or prev_gh.discard_reason,
            last_updated_by=role,
            confirmed_by=[role],
        )
    else:
        already = set(prev_gh.confirmed_by)
        already.add(role)
        gh = prev_gh.model_copy(update={"confirmed_by": sorted(already)})

    if not content_msg:
        content_msg = "(nessun commento aggiuntivo)"

    # The urgency this specialist supported, kept even when the turn became a confirmation.
    entry_urgency = gh.urgency_level if action in ("proponi", "rivedi") else (stated_urgency or gh.urgency_level)
    entry = RoundTableEntry(
        author=role, to=target, to_explicit=target_explicit,
        azione=action, content=content_msg, urgency=entry_urgency, verification=is_verification,
    )
    recipient = SPECIALIST_DISPLAY_NAMES.get(target, target) if target else "tutti"
    action_label = {"proponi": "apre la discussione", "conferma": "conferma", "rivedi": "rivede l'ipotesi"}[action]
    msg_text = f"**{display_name}** {action_label} (a {recipient}): {content_msg}"
    if is_verification:
        msg_text = "*Giro di verifica finale* — " + msg_text
    if action in ("proponi", "rivedi"):
        msg_text += f"\n\n*Ipotesi di gruppo aggiornata: {gh.diagnosis} (urgenza {gh.urgency_level})*"
    elif entry_urgency != gh.urgency_level:
        msg_text += f"\n\n*Urgenza indicata da {display_name}: {entry_urgency} (ipotesi di gruppo: {gh.urgency_level})*"
    await cl.Message(content=msg_text, author=author).send()

    entries = [entry]
    messages = [AIMessage(content=msg_text)]
    # The consult goes last, so the router gives the word to the colleague asked.
    if forced_consult_to:
        question = str(data.get("domanda_per_il_collega") or "").strip() or "(nessuna domanda specificata)"
        consult_entry, consult_text = await _send_consult(role, display_name, author, forced_consult_to, question,
                                                            requested_for)
        entries.append(consult_entry)
        messages.append(AIMessage(content=consult_text))

    return {
        "round_table": entries,
        "group_hypothesis": gh.model_dump(),
        "general_history": messages,
    }


async def _send_consult(role: str, display_name: str, author: str, target: str, question: str,
                        requested_for: str = ""):
    """Records a consult and shows it in the chat, saying if it was meant for a missing specialist."""
    entry = RoundTableEntry(author=role, to=target, azione="consulta", content=question)
    recipient = SPECIALIST_DISPLAY_NAMES.get(target, target)
    note = f" (richiesta per \"{requested_for}\", specialista non disponibile)" if requested_for else ""
    msg_text = f"**{display_name}** chiede un mini-consulto a **{recipient}**{note}: {question}"
    await cl.Message(content=msg_text, author=author).send()
    return entry, msg_text


async def cardiologist_node(state):
    """A turn of the cardiologist."""
    return await specialist_node(state, "cardiologist")


async def neurologist_node(state):
    """A turn of the neurologist."""
    return await specialist_node(state, "neurologist")


async def orthopedic_node(state):
    """A turn of the orthopaedist."""
    return await specialist_node(state, "orthopedist")


async def gastroenterologist_node(state):
    """A turn of the gastroenterologist."""
    return await specialist_node(state, "gastroenterologist")


async def dermatologist_node(state):
    """A turn of the dermatologist."""
    return await specialist_node(state, "dermatologist")


async def pneumologist_node(state):
    """A turn of the pulmonologist."""
    return await specialist_node(state, "pulmonologist")


async def ent_node(state):
    """A turn of the otorhinolaryngologist."""
    return await specialist_node(state, "ent")


async def ophthalmologist_node(state):
    """A turn of the ophthalmologist."""
    return await specialist_node(state, "ophthalmologist")


async def urologist_node(state):
    """A turn of the urologist."""
    return await specialist_node(state, "urologist")


async def general_practitioner_node(state):
    """A turn of the general practitioner."""
    return await specialist_node(state, "general_practitioner")
