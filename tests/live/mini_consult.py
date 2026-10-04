"""Live script: does a lone cardiologist call in a colleague before recommending an anticoagulant? Uses API quota.

Usage: python -m tests.live.mini_consult
"""

import asyncio

from src.state import PatientCard, SymptomProfile, Symptom

from .common import print_final_state, print_verdict, run_table


async def main():
    """LIVE mini-consult: a lone cardiologist should call in a colleague before recommending an anticoagulant."""
    card = PatientCard(
        first_name="Giorgio", last_name="Bianchi", age="65", sex="uomo",
        previous_conditions=["fibrillazione atriale nota"],
        symptom=SymptomProfile(symptoms=[
            Symptom(description="palpitazioni irregolari", intensity="forte", duration="2 ore"),
            Symptom(description="lividi estesi comparsi da soli sulle braccia e sulle gambe", intensity="moderata",
                    duration="una settimana", trigger="compaiono senza traumi o urti"),
        ]),
    )
    print("=" * 70)
    print("Round table with ONE pre-selected specialist (cardiologist)")
    print("Does it call in a colleague with a mini-consult? (anticoagulant + unexplained bruises)")
    print("=" * 70)
    state = await run_table(card, ["cardiologist"])
    print_final_state(state)
    print_verdict(state.get("recruited_specialists_count", 0) > 0,
                  "MINI-CONSULT triggered: a second specialist was called in during the discussion.",
                  "MINI-CONSULT NOT triggered in this run: the cardiologist did not call anyone in.")


if __name__ == "__main__":
    asyncio.run(main())
