"""Live script: do two specialists really discuss a case with two unrelated symptoms? Uses API quota.

Usage: python -m tests.live.round_table
"""

import asyncio

from src.state import PatientCard, SymptomProfile, Symptom

from .common import print_final_state, run_table


async def main():
    """LIVE round table: two unrelated symptoms (abdominal and skin) discussed by two specialists."""
    card = PatientCard(
        first_name="Laura", last_name="Bianchi", age="34", sex="donna",
        symptom=SymptomProfile(symptoms=[
            Symptom(description="dolore addominale tipo crampi", intensity="forte", duration="6 ore"),
            Symptom(description="eruzione cutanea con macchie rosse pruriginose", intensity="moderata", duration="3 ore"),
        ]),
    )
    print("=" * 70)
    print("Round table with 2 pre-selected specialists (gastroenterologist, dermatologist)")
    print("=" * 70)
    state = await run_table(card, ["gastroenterologist", "dermatologist"])
    print_final_state(state)


if __name__ == "__main__":
    asyncio.run(main())
