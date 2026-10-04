# Live script (NOT a unit test with asserts: the choice is made by the model
# in free form). It checks whether supervisor_node picks ALL the relevant
# specialists when the patient has symptoms from different fields, instead of
# "forgetting" one (per-symptom analysis forced in SUPERVISOR_PROMPT, see
# prompts.py). It also covers the opposite case: two related symptoms (headache
# + blurred vision) that ONE specialist can rightly cover. It USES API QUOTA.
#
# Usage: python -m tests.live.supervisor_selection
import asyncio

from chainlit.context import init_http_context

from src.agents.supervisor import supervisor_node
from src.state import MedicalState, PatientCard, SymptomProfile, Symptom


def _card(first_name, age, sex, *symptoms):
    """HELPER _card: a patient card with the given (description, intensity, duration) symptoms."""
    return PatientCard(first_name=first_name, age=age, sex=sex, symptom=SymptomProfile(
        symptoms=[Symptom(description=d, intensity=i, duration=t) for d, i, t in symptoms]))


CASES = [
    ("CASE 1: unrelated symptoms (2 different specialists expected)",
     _card("Laura", "34", "donna", ("dolore addominale tipo crampi", "forte", "6 ore"),
           ("eruzione cutanea con macchie rosse pruriginose", "moderata", "3 ore"))),
    ("CASE 2: possibly related symptoms (neurology can cover both)",
     _card("Luigi", "50", "uomo", ("mal di testa", "forte", "2 giorni"), ("vista sfocata", "moderata", "da 3 ore"))),
    ("CASE 3: three symptoms from different fields (3 specialists expected)",
     _card("Marco", "45", "uomo", ("dolore al petto", "forte", "2 ore"),
           ("eruzione cutanea con macchie rosse", "lieve", "1 giorno"), ("forte mal di schiena", "forte", "3 giorni"))),
    ("CASE 4: one very specific symptom (urologist expected, plus the GP for the second opinion)",
     _card("Elena", "28", "donna", ("bruciore quando urino", "forte", "1 giorno"))),
    ("CASE 5: vague symptom (general_practitioner expected)",
     _card("Davide", "40", "uomo", ("febbre e stanchezza generale", "moderata", "2 giorni"))),
]


async def main():
    """LIVE supervisor selection: prints the specialists chosen for five fixed cases."""
    init_http_context()
    for title, card in CASES:
        print("=" * 70)
        print(title)
        print("=" * 70)
        result = await supervisor_node(MedicalState(patient_card=card))
        print(f"\n>>> needed_specialists: {list(result.get('needed_specialists', {}))}\n")


if __name__ == "__main__":
    asyncio.run(main())
