# Live script (NOT a unit test with asserts: the discussion is free text
# written by the model, it cannot be checked by an exact comparison). It checks
# whether the round-table discussion works when MORE than one specialist is
# involved.
#
# Only the supervisor's choice is skipped (two specialists are seated by the
# script); router, specialists and primary are the real code, with real model
# calls - it USES API QUOTA.
#
# Usage: python -m tests.live.round_table
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
