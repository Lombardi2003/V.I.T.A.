"""Primary node: turns the table's hypothesis into the summary report for the staff."""

import asyncio

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState, GroupHypothesis, FinalDiagnosis
from .prompts import PRIMARY_PROMPT
from .common import extract_json, stream_response, as_list, as_text
from .authors import Authors
from .persistence import UNDETERMINED_DIAGNOSIS_PREFIX
from .roundtable import (
    SPECIALIST_DISPLAY_NAMES, URGENCY_LEVELS, _format_round_table, _format_urgencies, _parse_urgency,
    _pediatric_note,
)
from src.log import get_logger

log = get_logger("primary")

FALLBACK_URGENCY = "ARANCIONE"  # Used only when neither the table nor the primary gave a code: never the lowest.


def _fallback_final_diagnosis(gh: GroupHypothesis | None, involved: list[str]) -> FinalDiagnosis:
    """The report when the primary's answer is not available: the table's hypothesis, declared as such."""
    if gh is None:
        return FinalDiagnosis(
            diagnosis=f"{UNDETERMINED_DIAGNOSIS_PREFIX} per un errore tecnico.",
            urgency_level=FALLBACK_URGENCY,
            specialists_involved=involved,
            operational_guidance="Valutazione medica diretta necessaria.",
            recommendations=(f"Ne' il tavolo degli specialisti ne' il primario hanno prodotto una valutazione: "
                             f"codice {FALLBACK_URGENCY} assegnato in via cautelativa."),
        )
    confirmed_names = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in gh.confirmed_by) or "nessuno"
    return FinalDiagnosis(
        diagnosis=gh.diagnosis,
        urgency_level=gh.urgency_level,
        specialists_involved=involved,
        recommended_exams=list(gh.recommended_exams),
        operational_guidance=("Valutazione medica diretta; avviare gli esami indicati dal tavolo."
                              if gh.recommended_exams else "Valutazione medica diretta."),
        recommendations=(f"Sintesi del primario non disponibile per un errore tecnico: si riporta l'ipotesi "
                         f"condivisa dal tavolo degli specialisti (confermata da: {confirmed_names})."
                         + (f" {gh.details}" if gh.details else "")),
    )


def _format_report(final: FinalDiagnosis, gh: GroupHypothesis | None, second_opinion_role: str) -> str:
    """The summary report as shown in the chat: code first, then one titled section each."""
    def _display_name(role: str) -> str:
        """Display name of a role, marking the second opinion."""
        name = SPECIALIST_DISPLAY_NAMES.get(role, role)
        return f"{name} (secondo parere)" if role == second_opinion_role else name

    specialists_text = ", ".join(_display_name(r) for r in final.specialists_involved) or "nessuno"
    lines = [
        "**Report di sintesi**",
        f"**Codice** {final.urgency_level} · **Ipotesi diagnostica preliminare** {final.diagnosis}",
        f"**Specialisti coinvolti** {specialists_text}"
        + (f" · **Hanno confermato** {', '.join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in gh.confirmed_by)}"
           if gh and gh.confirmed_by else ""),
    ]
    if final.recommended_exams:
        lines.append(f"**Esami e accertamenti** {'; '.join(final.recommended_exams)}")
    if final.to_verify:
        lines.append(f"**Da verificare** {'; '.join(final.to_verify)}")
    if final.operational_guidance:
        lines.append(f"**Indicazioni operative** {final.operational_guidance}")
    if final.recommendations:
        lines.append(f"**Motivazione** {final.recommendations}")
    return "\n\n".join(lines[:1]) + "\n" + "\n\n".join(lines[1:])


async def primary_node(state: MedicalState):
    """Writes the summary report; it may confirm or raise the table's code, never lower it."""
    card = state.patient_card
    gh = state.group_hypothesis
    involved = list(state.needed_specialists.keys())

    card_str = card.model_dump_json()

    if gh is None:
        # Edge case: the turn cap was reached before anyone opened the discussion.
        hypothesis_text = "Il tavolo non e' arrivato a nessuna ipotesi condivisa."
    else:
        confirmed_names = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in gh.confirmed_by) or "nessuno"
        passed = [r for r in state.passed_without_confirming if r not in gh.confirmed_by]
        passed_text = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in passed) or "nessuno"
        unconfirmed = [r for r in involved if r not in gh.confirmed_by and r not in passed]
        unconfirmed_text = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in unconfirmed) or "nessuno"
        hypothesis_text = (
            f"Diagnosi: {gh.diagnosis}\n"
            f"Urgenza: {gh.urgency_level}\n"
            f"Esami consigliati: {', '.join(gh.recommended_exams) or 'nessuno indicato'}\n"
            f"Dettagli: {gh.details}\n"
            f"Alternativa considerata e scartata dal tavolo: {gh.discarded_alternative or '(nessuna)'}"
            f"{f' ({gh.discard_reason})' if gh.discard_reason else ''}\n"
            f"Confermata da: {confirmed_names}\n"
            f"NON confermata da (hanno finito i loro interventi o le loro risposte non erano "
            f"leggibili, il loro silenzio NON e' un assenso): {passed_text}\n"
            f"NON (ancora) confermata da: {unconfirmed_text}"
        )

    round_table_text = _format_round_table(state.round_table)
    urgencies_text = _format_urgencies(state.round_table)

    # The table's code is the floor of the final code.
    urgency_floor = gh.urgency_level if gh is not None else None
    if urgency_floor:
        higher_codes = URGENCY_LEVELS[:URGENCY_LEVELS.index(urgency_floor)]
        urgency_rule = (
            f"il tavolo ha deciso il codice {urgency_floor}. Di norma CONFERMALO: e' la decisione degli "
            "specialisti."
            + (f" Alzalo ({' / '.join(reversed(higher_codes))}) SOLO se un dato preciso dei DATI DEL "
               "PAZIENTE o della discussione lo richiede chiaramente, e spiega quale in \"recommendations\" - "
               "non alzarlo per semplice prudenza." if higher_codes else "")
            + " MAI abbassarlo."
        )
    else:
        urgency_rule = "il tavolo non e' arrivato a un'ipotesi condivisa: decidi tu il codice, motivandolo."

    pediatric_note = _pediatric_note(card)
    prompt = PRIMARY_PROMPT.format(
        card=f"{card_str}\n\n{pediatric_note}" if pediatric_note else card_str,
        hypothesis_text=hypothesis_text,
        urgencies_text=urgencies_text,
        round_table_text=round_table_text,
        urgency_rule=urgency_rule,
    )

    async with cl.Step(name="Sintesi finale", type="tool", default_open=False, show_input="text") as step:
        step.input = hypothesis_text
        try:
            # The model call blocks: run it in a thread so the interface stays responsive.
            content = await asyncio.to_thread(stream_response, prompt)
        except Exception as e:
            log.warning("model call failed: %s", e)
            content = ""
        step.output = content

    try:
        if not content:
            raise ValueError("nessuna risposta dal modello")
        report_data = extract_json(content)
        exams = [t for t in (as_text(e) for e in as_list(report_data.get("recommended_exams"))) if t]
        final = FinalDiagnosis(
            diagnosis=as_text(report_data.get("diagnosis")) or "Ipotesi diagnostica non determinata",
            urgency_level=_parse_urgency(report_data.get("urgency_level")) or urgency_floor or "BIANCO",
            specialists_involved=involved,
            # No exams listed by the primary: use the table's.
            recommended_exams=exams or (list(gh.recommended_exams) if gh else []),
            to_verify=[t for t in (as_text(v) for v in as_list(report_data.get("to_verify"))) if t],
            operational_guidance=as_text(report_data.get("operational_guidance")),
            recommendations=as_text(report_data.get("recommendations")),
        )
    except Exception as e:
        log.warning("no usable answer, reporting the table's hypothesis: %s", e)
        # No usable answer: report the table's hypothesis.
        final = _fallback_final_diagnosis(gh, involved)

    urgency_note = ""
    # The floor is enforced in code, not left to the model.
    if urgency_floor and URGENCY_LEVELS.index(final.urgency_level) > URGENCY_LEVELS.index(urgency_floor):
        log.warning("code %s is lower than the table's: set back to %s", final.urgency_level, urgency_floor)
        urgency_note = (
            f"\n\n*Codice riportato a {urgency_floor}: il primario aveva indicato {final.urgency_level}, "
            "ma non puo' abbassare il codice deciso dal tavolo degli specialisti.*"
        )
        final = final.model_copy(update={"urgency_level": urgency_floor})

    log.info("report ready, code %s", final.urgency_level)

    msg = _format_report(final, gh, state.second_opinion_role) + urgency_note
    await cl.Message(content=msg, author=Authors.PRIMARY_PHYSICIAN).send()

    return {
        "final_diagnosis": final.model_dump(),
        "general_history": [AIMessage(content=msg)],
    }
