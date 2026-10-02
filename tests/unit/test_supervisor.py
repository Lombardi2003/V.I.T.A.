"""supervisor: choice of specialists, cap, second opinion, robustness."""
import unittest

import httpx
import openai

try:
    from . import helpers
except ImportError:
    import helpers

from src.agents.clinical import _select_specialists, supervisor_node
from src.state import MedicalState, PatientCard, PhotoAnalysis, SymptomProfile, Symptom

QUOTA = openai.RateLimitError("tokens per day", response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None)
CARD = PatientCard(first_name="Mario", age="40", sex="uomo", symptom=SymptomProfile(symptoms=[
    Symptom(description="dolore al ginocchio", intensity="forte", duration="10 ore"),
    Symptom(description="eruzione cutanea", intensity="lieve", duration="2 giorni")]))


class TestSpecialistSelection(unittest.TestCase):
    def test_plain_list(self):
        """TEST specialist selection: a plain list of roles is kept as it is."""
        self.assertEqual(_select_specialists({"specialists": ["orthopedist", "dermatologist"]}), ["orthopedist", "dermatologist"])

    def test_italian_names_duplicates_and_case(self):
        """TEST specialist selection: Italian names are mapped to roles, duplicates and case are handled."""
        self.assertEqual(_select_specialists({"specialists": ["Ortopedia", "il dermatologo", "ORTHOPEDIST"]}),
                         ["orthopedist", "dermatologist"])

    def test_symptom_forgotten_in_the_final_list(self):
        """TEST specialist selection: a specialist named for a symptom but missing from the final list is added."""
        data = {"per_symptom_analysis": [{"symptom": "ginocchio", "specialists": ["orthopedist"]},
                                         {"symptom": "eruzione", "specialists": ["dermatologist"]}],
                "specialists": ["orthopedist"]}
        self.assertEqual(_select_specialists(data), ["orthopedist", "dermatologist"])

    def test_wrong_shapes(self):
        """TEST specialist selection: text, null and objects instead of a list of names are handled."""
        self.assertEqual(_select_specialists({"specialists": "orthopedist"}), ["orthopedist"])
        self.assertEqual(_select_specialists({"specialists": None}), [])
        self.assertEqual(_select_specialists({"specialists": [{"name": "orthopedist"}, "dermatologist"]}),
                         ["orthopedist", "dermatologist"])

    def test_cap_of_three_with_every_symptom_covered(self):
        """TEST specialist selection: at most three specialists, and every symptom keeps at least one."""
        data = {"per_symptom_analysis": [{"symptom": "ginocchio", "specialists": ["orthopedist", "general_practitioner"]},
                                         {"symptom": "eruzione", "specialists": ["dermatologist"]}],
                "specialists": ["general_practitioner", "neurologist", "cardiologist", "orthopedist", "dermatologist"]}
        chosen = _select_specialists(data)
        self.assertEqual(len(chosen), 3)
        self.assertIn("orthopedist", chosen)
        self.assertIn("dermatologist", chosen)

    def test_unknown_roles_are_dropped(self):
        """TEST specialist selection: roles outside the 10 available (e.g. allergologo) are dropped."""
        self.assertEqual(_select_specialists({"specialists": ["allergologo", "dermatologist", "radiologist"]}),
                         ["dermatologist"])


class TestSupervisor(helpers.VitaTestCase):
    def supervise(self, answer, card=CARD):
        """HELPER supervise: runs supervisor_node with one fake model answer."""
        self.llm.answers[:] = [answer]
        return helpers.run(supervisor_node, MedicalState(patient_card=card))

    def test_two_specialists(self):
        """TEST supervisor: two specialists, no second opinion, plural message."""
        out = self.supervise({"specialists": ["orthopedist", "dermatologist"]})
        self.assertEqual(list(out["needed_specialists"]), ["orthopedist", "dermatologist"])
        self.assertEqual(out["second_opinion_role"], "")
        self.assertIn("Verranno coinvolti in consulto: **Ortopedia, Dermatologia**.", self.last_message())

    def test_one_specialist_adds_the_second_opinion(self):
        """TEST supervisor: a single specialist gets the general practitioner for a second opinion."""
        out = self.supervise({"specialists": ["orthopedist"]})
        self.assertEqual(list(out["needed_specialists"]), ["orthopedist", "general_practitioner"])
        self.assertEqual(out["second_opinion_role"], "general_practitioner")
        self.assertIn("**Ortopedia**, con **Medicina** per un secondo parere", self.last_message())

    def test_general_practitioner_alone_stays_alone(self):
        """TEST supervisor: if the only choice is the general practitioner, nobody is added."""
        out = self.supervise({"specialists": ["general_practitioner"]})
        self.assertEqual(list(out["needed_specialists"]), ["general_practitioner"])
        self.assertEqual(out["second_opinion_role"], "")

    def test_broken_json_and_quota_fall_back_to_the_general_practitioner(self):
        """TEST supervisor: a broken answer or an API error falls back to the GP and says it is a technical fallback."""
        for answer in ("risposta troncata {\"spec", QUOTA):
            with self.subTest(answer=type(answer).__name__):
                out = self.supervise(answer)
                self.assertEqual(list(out["needed_specialists"]), ["general_practitioner"])
                self.assertIn("Smistamento automatico non disponibile per un errore tecnico", self.last_message())

    def test_only_unknown_roles_gives_the_general_practitioner_without_error_message(self):
        """TEST supervisor: a readable answer with only unknown roles gives the GP, without the technical-error text."""
        out = self.supervise({"specialists": ["allergologo"]})
        self.assertEqual(list(out["needed_specialists"]), ["general_practitioner"])
        self.assertNotIn("errore tecnico", self.last_message())

    def test_photo_analysis_reaches_the_prompt(self):
        """TEST supervisor: the photo analysis is included in the supervisor prompt."""
        card = CARD.model_copy(deep=True)
        card.symptom.photo = PhotoAnalysis(photo_url="x.png", description="Pomfi diffusi", injury_type="orticaria")
        self.supervise({"specialists": ["dermatologist", "orthopedist"]}, card=card)
        self.assertIn("orticaria", self.llm.prompts[0])


if __name__ == "__main__":
    unittest.main()
