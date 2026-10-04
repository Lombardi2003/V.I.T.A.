# Nodo del supervisore: sceglie quali specialisti coinvolgere (smistamento).
import asyncio
import json

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState
from .prompts import SUPERVISOR_PROMPT
from .common import extract_json, stream_response
from .authors import Authors
from .roundtable import SPECIALIST_DISPLAY_NAMES, _role_from_name


# Tetto agli specialisti scelti dal supervisore: con 5-6 al tavolo la
# discussione diventa lunghissima (e costosa in token) e, con il freno di
# MAX_TOTAL_TURNS, ognuno avrebbe solo un paio di interventi.
MAX_SELECTED_SPECIALISTS = 3


# Chi si aggiunge al tavolo per un secondo parere quando il supervisore ha
# scelto un solo specialista (vedi supervisor_node): il medico generico, il
# ruolo pensato per la visione d'insieme del paziente.
SECOND_OPINION_ROLE = "general_practitioner"


def _roles_from(value) -> list[str]:
    """Ruoli validi da una lista del modello, in ordine e senza doppioni.
    Accetta anche un testo singolo, elementi scritti come oggetto
    ({"name": "orthopedist"}) e i nomi italiani ("Ortopedia", "il
    dermatologo") - prima un null o un oggetto mandavano in errore il nodo, e
    un nome italiano veniva scartato (verificato con una prova)."""
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
    """Specialisti da mettere al tavolo, dalla risposta del supervisore.

    La lista finale e' l'UNIONE della lista del modello e di quelli indicati
    sintomo per sintomo: il prompt la chiede gia', ma prima nessuno la
    controllava (verificato: con "per_symptom_analysis" che indicava anche il
    dermatologo per l'eruzione e una lista finale con il solo ortopedico, il
    dermatologo andava perso). Oltre il tetto, prima uno specialista per ogni
    sintomo (nessun sintomo resta scoperto), poi gli altri in ordine."""
    final = _roles_from(data.get("specialists"))
    per_symptom = data.get("per_symptom_analysis")
    per_symptom = per_symptom if isinstance(per_symptom, list) else []
    per_symptom_roles = [_roles_from(item.get("specialists")) for item in per_symptom if isinstance(item, dict)]

    candidates = list(final)
    for roles in per_symptom_roles:
        candidates += [r for r in roles if r not in candidates]
    if len(candidates) <= MAX_SELECTED_SPECIALISTS:
        return candidates

    selected = []
    for roles in per_symptom_roles:
        first = next((r for r in roles if r in final), roles[0] if roles else None)
        if first and first not in selected:
            selected.append(first)
    selected = selected[:MAX_SELECTED_SPECIALISTS]
    selected += [r for r in candidates if r not in selected][:MAX_SELECTED_SPECIALISTS - len(selected)]
    print(f"🚦 SUPERVISOR: {len(candidates)} specialisti proposti, tenuti {MAX_SELECTED_SPECIALISTS}: {selected}")
    return selected


# Nodo del supervisore
async def supervisor_node(state: MedicalState):
    """Legge la cartella clinica (e la foto, se presente) e decide quali
    specialisti coinvolgere - compito puramente di smistamento, non emette
    diagnosi ne' giudizi clinici propri."""
    card = state.patient_card
    photo = card.symptom.photo
    card_str = card.model_dump_json()
    photo_str = photo.model_dump_json() if photo else "Nessuna foto."

    prompt = SUPERVISOR_PROMPT.format(patient_card=card_str, photo_analysis=photo_str)
    selected_specialists = ["general_practitioner"]

    async with cl.Step(name="Smistamento clinico", type="tool", default_open=False, show_input="text") as step:
        step.input = card_str
        # stream_response e' sincrona (bloccante): chiamata cosi' dentro una
        # funzione async bloccherebbe l'INTERO ciclo di eventi di Chainlit per
        # tutta la durata della chiamata - impercettibile con Groq (pochi
        # secondi), ma con un modello locale lento (Ollama) l'app sembra
        # completamente ferma (osservato in test reale). asyncio.to_thread la
        # sposta su un thread separato senza bloccare il resto.
        try:
            content = await asyncio.to_thread(stream_response, prompt)
        except Exception as e:
            # Chiamata fallita anche dopo i nuovi tentativi (quota finita,
            # servizio sovraccarico, rete): prima il nodo andava in errore e la
            # conversazione si fermava (osservato in prova reale con la quota
            # giornaliera esaurita). Stesso ripiego della risposta illeggibile.
            print(f"🚦 SUPERVISOR: chiamata al modello fallita ({e}), ripiego sul medico generico")
            content = ""
        step.output = content

    smistamento_fallito = False
    try:
        data = extract_json(content)

        clean_specs = _select_specialists(data)
        if clean_specs:
            selected_specialists = clean_specs

        print(f"🚦 SUPERVISOR → {selected_specialists}")

    except json.JSONDecodeError:
        smistamento_fallito = True
        print("🚦 SUPERVISOR: risposta assente o illeggibile, fallback su medico generale")

    nomi = ", ".join(SPECIALIST_DISPLAY_NAMES.get(s, s) for s in selected_specialists)
    plurale = len(selected_specialists) > 1
    verbo = "Verranno coinvolti in consulto" if plurale else "Verrà coinvolto in consulto"
    msg = f"{verbo}: **{nomi}**."
    if smistamento_fallito:
        # Si dice che non e' una scelta clinica, ma un ripiego per errore tecnico.
        msg = f"Smistamento automatico non disponibile per un errore tecnico: {verbo.lower()} **{nomi}**."

    # Un solo specialista = un monologo: propone e poi, nel giro di verifica,
    # rilegge se stesso, senza che nessuno controlli (osservato nella prova di
    # riferimento sul dolore toracico). Si aggiunge il medico generico per un
    # SECONDO PARERE - regola fissa, nessuna chiamata in piu' al modello - e lo
    # si dichiara nel messaggio, perche' non e' una scelta clinica del
    # supervisore. Se l'unico scelto e' gia' il medico generico, resta da solo.
    second_opinion_role = ""
    if len(selected_specialists) == 1 and selected_specialists[0] != SECOND_OPINION_ROLE:
        second_opinion_role = SECOND_OPINION_ROLE
        selected_specialists = selected_specialists + [SECOND_OPINION_ROLE]
        print(f"🚦 SUPERVISOR: un solo specialista, aggiunto {SECOND_OPINION_ROLE} per un secondo parere")
        msg = (f"Verrà coinvolto in consulto: **{nomi}**, con "
               f"**{SPECIALIST_DISPLAY_NAMES[SECOND_OPINION_ROLE]}** per un secondo parere.")
    await cl.Message(content=msg, author=Authors.SUPERVISOR).send()

    # Il valore booleano non porta piu' informazione propria (vedi commento su
    # needed_specialists in state.py) - resta sempre True, il dizionario serve
    # solo come insieme ordinato di chi e' seduto al tavolo.
    checklist = {specialist: True for specialist in selected_specialists}
    print(f"   Checklist: {checklist}")
    return {
        "needed_specialists": checklist,
        "second_opinion_role": second_opinion_role,
        "general_history": [AIMessage(content=msg)],
    }
