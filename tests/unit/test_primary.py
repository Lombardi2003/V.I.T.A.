"""primary_node: the table's urgency code, fallbacks on errors, summary report."""
import unittest

import httpx
import openai

try:
    from . import helpers
except ImportError:
    import helpers

from src.agents import clinical
from src.state import MedicalState, PatientCard, SymptomProfile, Symptom, GroupHypothesis, RoundTableEntry

_req = httpx.Request("POST", "https://x")
QUOTA = openai.RateLimitError("tokens per day", response=httpx.Response(429, request=_req), body=None)
OVERLOADED = openai.InternalServerError("high demand", response=httpx.Response(503, request=_req), body=None)
CARD = PatientCard(age="34", sex="donna", symptom=SymptomProfile(symptoms=[Symptom(description="tosse", intensity="forte", duration="2 giorni")]))
GH = GroupHypothesis(diagnosis="Bronchite acuta", urgency_level="VERDE", recommended_exams=["RX torace", "emocromo"],
                     details="Tosse produttiva senza segni di gravita'.", last_updated_by="pulmonologist",
                     confirmed_by=["pulmonologist", "general_practitioner"])
SEATED = {"pulmonologist": True, "general_practitioner": True}


def answer(urgency="VERDE", **extra):
    """HELPER answer: a fake primary answer with the given urgency."""
    return {"diagnosis": "Bronchite acuta", "urgency_level": urgency, "operational_guidance": "x", "recommendations": "y"} | extra


def said(author, urgency, action="proponi"):
    """HELPER said: a round-table entry carrying an urgency."""
    return RoundTableEntry(author=author, azione=action, content="x", urgency=urgency)


class TestPrimary(helpers.VitaTestCase):
    def primary(self, ans, gh=GH, **state):
        """HELPER primary: runs primary_node with one fake answer and returns the final diagnosis."""
        self.llm.answers[:] = [ans]
        out = helpers.run(clinical.primary_node, MedicalState(patient_card=CARD, group_hypothesis=gh, needed_specialists=SEATED, **state))
        return out["final_diagnosis"]

    def test_confirms_the_table_code(self):
        """TEST primary: the table's code is kept and the prompt says to confirm it, not raise it out of caution."""
        self.assertEqual(self.primary(answer())["urgency_level"], "VERDE")
        rule = self.llm.prompts[0].split("REGOLA SUL LIVELLO DI URGENZA: ")[1]
        self.assertIn("Di norma CONFERMALO", rule)
        self.assertIn("non alzarlo per semplice prudenza", rule)

    def test_cannot_lower_the_code(self):
        """TEST primary: a lower code than the table's is replaced by the table's code, with a note."""
        fd = self.primary(answer("BIANCO"))
        self.assertEqual(fd["urgency_level"], "VERDE")
        self.assertIn("non puo' abbassare il codice", self.last_message())

    def test_can_raise_the_code(self):
        """TEST primary: a higher code than the table's is accepted."""
        self.assertEqual(self.primary(answer("AZZURRO"))["urgency_level"], "AZZURRO")

    def test_model_errors_report_the_table_hypothesis(self):
        """TEST primary: quota, overload or a broken answer report the table's hypothesis, declared as a fallback."""
        for ans in (QUOTA, OVERLOADED, "risposta troncata {\"diag"):
            with self.subTest(error=type(ans).__name__):
                fd = self.primary(ans)
                self.assertEqual((fd["diagnosis"], fd["urgency_level"]), ("Bronchite acuta", "VERDE"))
                self.assertEqual(fd["recommended_exams"], ["RX torace", "emocromo"])
                self.assertIn("Sintesi del primario non disponibile per un errore tecnico", fd["recommendations"])

    def test_no_hypothesis_and_no_primary_gives_a_cautious_code(self):
        """TEST primary: with no table hypothesis and a failed primary, the cautious code ARANCIONE is used."""
        fd = self.primary(QUOTA, gh=None)
        self.assertEqual(fd["urgency_level"], "ARANCIONE")
        self.assertIn("non determinata", fd["diagnosis"])

    def test_complete_summary_report(self):
        """TEST primary: the report shows code, preliminary hypothesis, specialists, exams, checks, guidance and motivation."""
        fd = self.primary(answer(
            "VERDE", recommended_exams=["RX torace", "saturazione"], to_verify=["chiedere se fuma"],
            operational_guidance="Ambulatorio a bassa complessita'.", recommendations="Ragionamento completo."),
            second_opinion_role="general_practitioner")
        self.assertEqual(fd["to_verify"], ["chiedere se fuma"])
        report = self.last_message()
        for part in ("**Report di sintesi**", "**Codice** VERDE · **Ipotesi diagnostica preliminare** Bronchite acuta",
                     "**Specialisti coinvolti** Pneumologia, Medicina (secondo parere)", "**Hanno confermato**",
                     "**Esami e accertamenti** RX torace; saturazione", "**Da verificare** chiedere se fuma",
                     "**Indicazioni operative** Ambulatorio", "**Motivazione** Ragionamento completo."):
            with self.subTest(part=part):
                self.assertIn(part, report)
        self.assertNotIn("Diagnosi finale", report)  # thesis terminology

    def test_table_exams_used_if_the_primary_lists_none(self):
        """TEST primary: if the primary lists no exams, the table's exams are used."""
        self.assertEqual(self.primary(answer())["recommended_exams"], ["RX torace", "emocromo"])

    def test_prompt_for_staff_and_pediatric_note(self):
        """TEST primary: the prompt is written for staff and carries the pediatric note for a child."""
        self.primary(answer())
        self.assertIn("NON scrivere \"recarsi al pronto soccorso\"", self.llm.prompts[0])
        self.llm.prompts.clear()
        self.llm.answers[:] = [answer()]
        helpers.run(clinical.primary_node, MedicalState(patient_card=CARD.model_copy(update={"age": "9"}), group_hypothesis=GH,
                                                         needed_specialists=SEATED))
        self.assertIn("PAZIENTE PEDIATRICO (9 anni)", self.llm.prompts[0])

    def test_discordant_urgencies_are_flagged_to_the_primary(self):
        """TEST primary: when the table disagreed on the urgency, the prompt warns and names the highest code."""
        self.primary(answer(), round_table=[said("pulmonologist", "VERDE"), said("general_practitioner", "ARANCIONE", "rivedi")])
        self.assertIn("il tavolo NON e' stato concorde sull'urgenza - la piu' alta espressa e' ARANCIONE", self.llm.prompts[0])

    def test_concordant_urgencies_have_no_warning(self):
        """TEST primary: when every urgency expressed is the same, no disagreement warning is added."""
        text = clinical._format_urgencies([said("pulmonologist", "VERDE"), said("general_practitioner", "VERDE", "conferma")])
        self.assertNotIn("NON e' stato concorde", text)
        self.assertIn("- VERDE: Pneumologia (intervento 1, proponi)", text)
        self.assertEqual(clinical._format_urgencies([]), "Nessuna urgenza espressa esplicitamente al tavolo.")


if __name__ == "__main__":
    unittest.main()
