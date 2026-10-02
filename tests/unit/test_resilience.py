"""Resilience: random malformed model answers never crash a node, and the same inputs give the same result."""
import json
import random
import unittest

from langchain_core.messages import HumanMessage

try:
    from . import helpers
except ImportError:
    import helpers

from src.agents import clinical, intake
from src.state import GroupHypothesis, MedicalState, PatientCard, Symptom, SymptomProfile

ROUNDS = 25
CARD = PatientCard(fiscal_code="1234", first_name="Mario", last_name="Rossi", age="40", sex="uomo", symptom=SymptomProfile(
    symptoms=[Symptom(description="tosse", intensity="forte", duration="2 giorni")]))
GH = GroupHypothesis(diagnosis="Bronchite", urgency_level="VERDE", confirmed_by=["pulmonologist"])
KEYS = {
    "intake": ["updated_card", "allergies_to_remove", "previous_conditions_to_remove", "allergies_addressed",
               "previous_conditions_addressed", "conferma", "message_to_user"],
    "reviewer": ["updated_card", "symptoms_to_remove", "conferma", "message_to_user"],
    "supervisor": ["specialists", "per_symptom_analysis"],
    "specialist": ["azione", "to", "diagnosi", "urgenza", "esami_consigliati", "dettagli", "motivazione", "message",
                   "coincide_con_gruppo", "consulto_utile", "collega_da_consultare", "domanda_per_il_collega",
                   "valutazione_indipendente", "ipotesi_alternativa_scartata", "motivo_scarto", "fonti_consultate"],
    "primary": ["diagnosis", "urgency_level", "recommended_exams", "to_verify", "operational_guidance", "recommendations"],
}


def random_value(rng, depth=0):
    """HELPER random_value: a random JSON value of any type, sometimes nested."""
    simple = [None, "", "testo", "ROSSO", "si", "no", 0, 7, -1.5, True, False, [], {}, ["a", None, 3], {"name": None}]
    if depth < 2 and rng.random() < 0.3:
        return rng.choice([[random_value(rng, depth + 1) for _ in range(rng.randint(0, 3))],
                           {k: random_value(rng, depth + 1) for k in rng.sample(["symptom", "symptoms", "description",
                                                                                 "first_name", "allergies", "x"], 2)}])
    return rng.choice(simple)


def random_answer(rng, node):
    """HELPER random_answer: a random model answer for a node: real keys with random values, or text that is not JSON."""
    if rng.random() < 0.15:
        return rng.choice(["", "nessun json", "{\"troncato\": ", "[1, 2]", "null", "<think>...</think>"])
    return json.dumps({k: random_value(rng) for k in rng.sample(KEYS[node], rng.randint(0, len(KEYS[node])))})


class TestRandomAnswers(helpers.VitaTestCase):
    def survive(self, node, call):
        """HELPER survive: feeds ROUNDS random answers to a node and checks it always returns a state update."""
        rng = random.Random(node)
        for i in range(ROUNDS):
            answer = random_answer(rng, node)
            with self.subTest(round=i, answer=answer[:120]):
                self.llm.answers[:] = [answer]
                self.assertIsInstance(call(), dict)

    def test_intake_never_crashes(self):
        """TEST resilience: intake_node survives random malformed answers."""
        state = MedicalState(patient_card=CARD, intake_card_shown=True, triage_history=[HumanMessage(content="dati")])
        self.survive("intake", lambda: helpers.run(intake.intake_node, state))

    def test_reviewer_never_crashes(self):
        """TEST resilience: reviewer_node survives random malformed answers."""
        state = MedicalState(patient_card=CARD, reviewer_card_shown=True,
                             triage_history=[HumanMessage(content="tosse forte da 2 giorni")])
        self.survive("reviewer", lambda: helpers.run(intake.reviewer_node, state))

    def test_supervisor_never_crashes(self):
        """TEST resilience: supervisor_node survives random malformed answers and always seats someone."""
        def call():
            out = helpers.run(clinical.supervisor_node, MedicalState(patient_card=CARD))
            self.assertTrue(out["needed_specialists"])
            return out
        self.survive("supervisor", call)

    def test_specialist_never_crashes(self):
        """TEST resilience: specialist_node survives random malformed answers."""
        state = MedicalState(patient_card=CARD, group_hypothesis=GH,
                             needed_specialists={"pulmonologist": True, "general_practitioner": True})
        self.survive("specialist", lambda: helpers.run(clinical.specialist_node, state, "general_practitioner"))

    def test_primary_never_crashes(self):
        """TEST resilience: primary_node survives random malformed answers and always gives a valid urgency code."""
        def call():
            out = helpers.run(clinical.primary_node, MedicalState(patient_card=CARD, group_hypothesis=GH,
                                                                  needed_specialists={"pulmonologist": True}))
            self.assertIn(helpers.as_dict(out["final_diagnosis"])["urgency_level"], clinical.URGENCY_LEVELS)
            return out
        self.survive("primary", call)


class TestDeterminism(helpers.VitaTestCase):
    def test_same_conversation_gives_the_same_result(self):
        """TEST determinism: the same messages and model answers give the same card and the same chat, twice."""
        results = []
        for _ in range(2):
            conv = helpers.go_to_symptoms(helpers.Conversation(self))
            conv.send("tosse forte da 2 giorni e febbre", [helpers.symptoms_answer(("tosse", "forte", "2 giorni"),
                                                                                  ("febbre", "", ""))])
            results.append((conv.card, list(self.chat)))
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
