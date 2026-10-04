# Nodo del primario: traduce l'ipotesi di gruppo del tavolo nel report di sintesi.
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


# Codice usato solo se il tavolo non ha un'ipotesi E il primario non risponde
# (caso estremo): prudente, perche' per un errore tecnico il codice piu' basso
# (BIANCO, quello di prima) e' la scelta peggiore. Deciso dall'utente.
FALLBACK_URGENCY = "ARANCIONE"


def _fallback_final_diagnosis(gh: GroupHypothesis | None, coinvolti: list[str]) -> FinalDiagnosis:
    """Report di sintesi quando la sintesi del primario non e' disponibile:
    l'ipotesi di gruppo del tavolo, dichiarata come tale."""
    if gh is None:
        return FinalDiagnosis(
            diagnosis=f"{UNDETERMINED_DIAGNOSIS_PREFIX} per un errore tecnico.",
            urgency_level=FALLBACK_URGENCY,
            specialists_involved=coinvolti,
            operational_guidance="Valutazione medica diretta necessaria.",
            recommendations=(f"Ne' il tavolo degli specialisti ne' il primario hanno prodotto una valutazione: "
                             f"codice {FALLBACK_URGENCY} assegnato in via cautelativa."),
        )
    confermata = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in gh.confirmed_by) or "nessuno"
    return FinalDiagnosis(
        diagnosis=gh.diagnosis,
        urgency_level=gh.urgency_level,
        specialists_involved=coinvolti,
        recommended_exams=list(gh.recommended_exams),
        operational_guidance=("Valutazione medica diretta; avviare gli esami indicati dal tavolo."
                              if gh.recommended_exams else "Valutazione medica diretta."),
        recommendations=(f"Sintesi del primario non disponibile per un errore tecnico: si riporta l'ipotesi "
                         f"condivisa dal tavolo degli specialisti (confermata da: {confermata})."
                         + (f" {gh.details}" if gh.details else "")),
    )


def _format_report(final: FinalDiagnosis, gh: GroupHypothesis | None, second_opinion_role: str) -> str:
    """Report di sintesi in chat, nello stile delle schede di anagrafica e
    sintomi: il codice in cima (la cosa piu' importante per il triage), poi le
    sezioni con un titolo ciascuna. Il contenuto NON viene tagliato ne'
    riassunto: cambiano solo ordine e titoli (indicazione dell'utente). Prima
    era "Diagnosi finale" con la motivazione senza titolo e il codice in fondo;
    la terminologia segue la tesi (report di sintesi / ipotesi diagnostica
    preliminare)."""
    def _nome(role: str) -> str:
        nome = SPECIALIST_DISPLAY_NAMES.get(role, role)
        return f"{nome} (secondo parere)" if role == second_opinion_role else nome

    specialisti = ", ".join(_nome(r) for r in final.specialists_involved) or "nessuno"
    righe = [
        "**Report di sintesi**",
        f"**Codice** {final.urgency_level} · **Ipotesi diagnostica preliminare** {final.diagnosis}",
        f"**Specialisti coinvolti** {specialisti}"
        + (f" · **Hanno confermato** {', '.join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in gh.confirmed_by)}"
           if gh and gh.confirmed_by else ""),
    ]
    if final.recommended_exams:
        righe.append(f"**Esami e accertamenti** {'; '.join(final.recommended_exams)}")
    if final.to_verify:
        righe.append(f"**Da verificare** {'; '.join(final.to_verify)}")
    if final.operational_guidance:
        righe.append(f"**Indicazioni operative** {final.operational_guidance}")
    if final.recommendations:
        righe.append(f"**Motivazione** {final.recommendations}")
    return "\n\n".join(righe[:1]) + "\n" + "\n\n".join(righe[1:])


# Nodo del primario
async def primary_node(state: MedicalState):
    """Legge la scheda del paziente e l'ipotesi di gruppo a cui il tavolo degli
    specialisti e' arrivato discutendo insieme (non piu' N referti indipendenti
    da confrontare lui stesso), e la traduce nella diagnosi finale ufficiale
    (FinalDiagnosis).

    Subito dopo, save_db (persistence.py) salva la scheda nel database.
    """
    card = state.patient_card
    gh = state.group_hypothesis
    coinvolti = list(state.needed_specialists.keys())

    card_str = card.model_dump_json()

    if gh is None:
        # Caso limite: il tetto MAX_TOTAL_TURNS e' scattato prima che
        # chiunque aprisse la discussione (non dovrebbe succedere in pratica,
        # il primo turno e' sempre "proponi" - vedi specialist_node).
        hypothesis_text = "Il tavolo non e' arrivato a nessuna ipotesi condivisa."
    else:
        confermato_da = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in gh.confirmed_by) or "nessuno"
        passati = [r for r in state.passed_without_confirming if r not in gh.confirmed_by]
        passati_txt = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in passati) or "nessuno"
        mancano = [r for r in coinvolti if r not in gh.confirmed_by and r not in passati]
        mancano_txt = ", ".join(SPECIALIST_DISPLAY_NAMES.get(r, r) for r in mancano) or "nessuno"
        hypothesis_text = (
            f"Diagnosi: {gh.diagnosis}\n"
            f"Urgenza: {gh.urgency_level}\n"
            f"Esami consigliati: {', '.join(gh.recommended_exams) or 'nessuno indicato'}\n"
            f"Dettagli: {gh.details}\n"
            f"Alternativa considerata e scartata dal tavolo: {gh.discarded_alternative or '(nessuna)'}"
            f"{f' ({gh.discard_reason})' if gh.discard_reason else ''}\n"
            f"Confermata da: {confermato_da}\n"
            f"NON confermata da (hanno finito i loro interventi o le loro risposte non erano "
            f"leggibili, il loro silenzio NON e' un assenso): {passati_txt}\n"
            f"NON (ancora) confermata da: {mancano_txt}"
        )

    round_table_text = _format_round_table(state.round_table)
    urgencies_text = _format_urgencies(state.round_table)

    # Il codice dell'ipotesi di gruppo e' il MINIMO del codice finale: gli
    # specialisti formano insieme la diagnosi comune, il primario la assembla e
    # puo' solo confermarne il codice o alzarlo (ad es. se vede nella
    # discussione, o tra le urgenze espresse, un elemento che pesa di piu') -
    # mai abbassarlo. Chiesto nel prompt e poi garantito in Python piu' sotto,
    # senza affidarsi al fatto che l'LLM obbedisca: in test reale lo stesso
    # caso clinico ha dato codici finali diversi da un'esecuzione all'altra.
    urgency_floor = gh.urgency_level if gh is not None else None
    if urgency_floor:
        piu_alti = URGENCY_LEVELS[:URGENCY_LEVELS.index(urgency_floor)]
        # Di norma si CONFERMA: alzarlo e' un'eccezione da motivare, non un
        # passaggio di routine (indicazione esplicita dell'utente: il primario
        # segue il codice del tavolo e lo alza solo se davvero sicuro).
        urgency_rule = (
            f"il tavolo ha deciso il codice {urgency_floor}. Di norma CONFERMALO: e' la decisione degli "
            "specialisti."
            + (f" Alzalo ({' / '.join(reversed(piu_alti))}) SOLO se un dato preciso dei DATI DEL "
               "PAZIENTE o della discussione lo richiede chiaramente, e spiega quale in \"recommendations\" - "
               "non alzarlo per semplice prudenza." if piu_alti else "")
            + " MAI abbassarlo."
        )
    else:
        urgency_rule = "il tavolo non e' arrivato a un'ipotesi condivisa: decidi tu il codice, motivandolo."

    nota_pediatrica = _pediatric_note(card)
    prompt = PRIMARY_PROMPT.format(
        # La nota (paziente minorenne) va subito dopo i dati del paziente.
        card=f"{card_str}\n\n{nota_pediatrica}" if nota_pediatrica else card_str,
        hypothesis_text=hypothesis_text,
        urgencies_text=urgencies_text,
        round_table_text=round_table_text,
        urgency_rule=urgency_rule,
    )

    async with cl.Step(name="Sintesi finale", type="tool", default_open=False, show_input="text") as step:
        step.input = hypothesis_text
        try:
            # asyncio.to_thread: vedi commento su supervisor_node piu' sopra.
            content = await asyncio.to_thread(stream_response, prompt)
        except Exception as e:
            # Chiamata fallita anche dopo i nuovi tentativi (quota finita,
            # servizio sovraccarico, rete): prima il nodo andava in errore e la
            # diagnosi finale non arrivava mai, buttando il lavoro del tavolo
            # (osservato in prova reale con Gemini). Si ripiega sotto.
            print(f"⚠️ PRIMARIO: chiamata al modello fallita ({e})")
            content = ""
        step.output = content

    try:
        if not content:
            raise ValueError("nessuna risposta dal modello")
        report_data = extract_json(content)
        exams = [t for t in (as_text(e) for e in as_list(report_data.get("recommended_exams"))) if t]
        final = FinalDiagnosis(
            diagnosis=as_text(report_data.get("diagnosis")) or "Ipotesi diagnostica non determinata",
            # Codice mancante o non riconoscibile: si parte dal codice del
            # tavolo invece che dal piu' basso (BIANCO).
            urgency_level=_parse_urgency(report_data.get("urgency_level")) or urgency_floor or "BIANCO",
            specialists_involved=coinvolti,
            # Se il primario non li elenca, quelli concordati dal tavolo.
            recommended_exams=exams or (list(gh.recommended_exams) if gh else []),
            to_verify=[t for t in (as_text(v) for v in as_list(report_data.get("to_verify"))) if t],
            operational_guidance=as_text(report_data.get("operational_guidance")),
            recommendations=as_text(report_data.get("recommendations")),
        )
    except Exception as e:
        # Nessuna risposta o risposta non valida: la diagnosi finale diventa
        # l'ipotesi di gruppo, dichiarata come tale - e' gia' il risultato del
        # tavolo, buttarlo per un errore tecnico non ha senso. Prima era
        # "Diagnosi non determinata" con il solo codice del tavolo.
        print(f"⚠️ PRIMARIO: sintesi non disponibile, si riporta l'ipotesi di gruppo ({e})")
        final = _fallback_final_diagnosis(gh, coinvolti)

    # Regola del minimo, applicata meccanicamente (vedi commento su urgency_floor).
    nota_urgenza = ""
    if urgency_floor and URGENCY_LEVELS.index(final.urgency_level) > URGENCY_LEVELS.index(urgency_floor):
        print(f"🔒 PRIMARIO: codice {final.urgency_level} piu' basso di quello del tavolo -> riportato a {urgency_floor}")
        nota_urgenza = (
            f"\n\n*Codice riportato a {urgency_floor}: il primario aveva indicato {final.urgency_level}, "
            "ma non puo' abbassare il codice deciso dal tavolo degli specialisti.*"
        )
        final = final.model_copy(update={"urgency_level": urgency_floor})

    print(f"👨‍⚕️ PRIMARIO → diagnosi={final.diagnosis!r} | urgenza={final.urgency_level}")

    msg = _format_report(final, gh, state.second_opinion_role) + nota_urgenza
    await cl.Message(content=msg, author=Authors.PRIMARY_PHYSICIAN).send()

    return {
        "final_diagnosis": final.model_dump(),
        "general_history": [AIMessage(content=msg)],
    }
