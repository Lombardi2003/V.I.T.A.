# Live script (NOT a unit test with asserts). It checks whether the
# CORRECTION mechanism works: a specialist facing a clearly WRONG group
# hypothesis in their own field really fixes it with "rivedi", instead of
# confirming it or just adding details (see the rule "PRIORITA' (ipotesi
# scartata nel TUO ambito)" in SPECIALIST_PROMPT).
#
# Here the wrong first entry is INJECTED, not left to the model (in real runs
# this model almost never gets the first turn wrong): "renal colic", urgency
# VERDE, for a textbook acute cholecystitis (right-flank pain that gets worse
# after fatty food) - the discarded explanation falls exactly in the second
# specialist's field (gastroenterologist). Router, specialists and primary are
# the real code with real model calls - it USES API QUOTA.
#
# Usage: python -m tests.live.correction
import asyncio

from src.state import PatientCard, SymptomProfile, Symptom, GroupHypothesis, RoundTableEntry

from .common import print_final_state, print_verdict, run_table


async def main():
    """LIVE correction: the gastroenterologist should overturn an injected wrong "renal colic" hypothesis."""
    card = PatientCard(
        first_name="Elena", last_name="Ferrari", age="45", sex="donna",
        symptom=SymptomProfile(symptoms=[
            Symptom(description="dolore al fianco destro tipo colica", intensity="forte", duration="6 ore",
                    trigger="peggiora dopo aver mangiato cibi grassi"),
            Symptom(description="nausea", intensity="moderata", duration="6 ore"),
        ]),
    )
    wrong_hypothesis = GroupHypothesis(
        diagnosis="Colica renale (verosimile calcolo ureterale destro)",
        urgency_level="VERDE",
        recommended_exams=["Antidolorifico al bisogno", "Idratazione abbondante",
                           "Controllo ambulatoriale tra una settimana se il dolore persiste"],
        details="Dolore al fianco destro di tipo colico: quadro compatibile con colica renale da calcolo ureterale. "
                "Non richiede accertamenti urgenti.",
        discarded_alternative="Colecistite acuta",
        discard_reason="Il dolore e' colico e localizzato al fianco, non tipico di colecistite.",
        last_updated_by="urologist",
        confirmed_by=["urologist"],
    )
    wrong_entry = RoundTableEntry(
        author="urologist", to=None, azione="proponi",
        content="Propongo colica renale da calcolo ureterale destro, gestione ambulatoriale con antidolorifico, urgenza verde.",
    )
    print("=" * 70)
    print("INJECTED hypothesis (wrong on purpose): renal colic, urgency VERDE")
    print("Does the gastroenterologist correct it with 'rivedi'?")
    print("=" * 70)
    # As if the urologist had already spoken first: the router calls the gastroenterologist next.
    state = await run_table(card, ["urologist", "gastroenterologist"], extra_state={
        "round_table": [wrong_entry],
        "group_hypothesis": wrong_hypothesis.model_dump(),
        "total_turns": 1,
    })
    print_final_state(state)

    gh = state.get("group_hypothesis")
    diagnosis = ((gh.get("diagnosis") if isinstance(gh, dict) else getattr(gh, "diagnosis", "")) or "").lower()
    print_verdict("renale" not in diagnosis and "ureterale" not in diagnosis,
                  "CORRECTION happened: the final group hypothesis is no longer 'renal colic'.",
                  "CORRECTION did NOT happen: the final group hypothesis is still 'renal colic'.")


if __name__ == "__main__":
    asyncio.run(main())
