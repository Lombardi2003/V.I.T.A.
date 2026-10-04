"""specialist_node: robust reading of the answer, consults, notes added to the prompt."""
import unittest

try:
    from . import helpers
except ImportError:
    import helpers

from src.agents import roundtable, specialist
from src.rag.retriever import RetrievedChunk
from src.state import MedicalState, PatientCard, SymptomProfile, Symptom, GroupHypothesis, RoundTableEntry

CARD = PatientCard(first_name="Mario", age="40", sex="uomo", symptom=SymptomProfile(symptoms=[
    Symptom(description="tosse", intensity="forte", duration="2 giorni")]))
GH = GroupHypothesis(diagnosis="Bronchite acuta", urgency_level="VERDE", last_updated_by="pulmonologist", confirmed_by=["pulmonologist"])
BASE = {"valutazione_indipendente": "stessa", "ipotesi_alternativa_scartata": "x", "motivo_scarto": "y",
        "fonti_consultate": "nessuna pertinente", "motivazione": "ok"}
CONFIRM = BASE | {"azione": "conferma", "coincide_con_gruppo": "si", "consulto_utile": "no"}


class TestSpecialist(helpers.VitaTestCase):
    def turn(self, answer, role="general_practitioner", card=CARD, gh=GH, round_table=(), **state):
        """HELPER turn: one specialist turn with a fake answer; returns the output and the (action, recipient) pairs."""
        self.llm.answers[:] = [answer]
        st = MedicalState(patient_card=card, group_hypothesis=gh, round_table=list(round_table),
                          needed_specialists={"pulmonologist": True, "general_practitioner": True}, **state)
        out = helpers.run(specialist.specialist_node, st, role)
        actions = [(e.azione, e.to) for e in out.get("round_table", [])]
        return out, actions

    # --- model answers in different shapes ---
    def test_plain_confirmation(self):
        """TEST specialist: a normal confirmation is recorded as "conferma" to everyone."""
        _, actions = self.turn(CONFIRM)
        self.assertEqual(actions, [("conferma", None)])

    def test_matches_group_false_becomes_revise(self):
        """TEST specialist: "conferma" with coincide_con_gruppo=false is treated as a revision."""
        out, actions = self.turn(BASE | {"azione": "conferma", "coincide_con_gruppo": False, "diagnosi": "Polmonite"})
        self.assertEqual(actions[0][0], "rivedi")
        self.assertEqual(out["group_hypothesis"]["diagnosis"], "Polmonite")

    def test_consult_useful_true_or_accented_si(self):
        """TEST specialist: consulto_utile as true or "sì" adds a consult after the confirmation."""
        for value in (True, "sì"):
            with self.subTest(value=value):
                _, actions = self.turn(CONFIRM | {"consulto_utile": value, "collega_da_consultare": "cardiologist",
                                                  "domanda_per_il_collega": "domanda?"})
                self.assertEqual(actions, [("conferma", None), ("consulta", "cardiologist")])

    def test_recipient_and_colleague_written_as_object_or_list(self):
        """TEST specialist: recipient and colleague written as an object or a list are read."""
        _, actions = self.turn(CONFIRM | {"to": {"name": "pulmonologist"}})
        self.assertEqual(actions, [("conferma", "pulmonologist")])
        _, actions = self.turn(CONFIRM | {"consulto_utile": "si", "collega_da_consultare": ["cardiologist"],
                                          "domanda_per_il_collega": "domanda?"})
        self.assertEqual(actions[1], ("consulta", "cardiologist"))

    def test_uppercase_or_null_action(self):
        """TEST specialist: an uppercase or null action with coincide_con_gruppo=si is a confirmation."""
        self.assertEqual(self.turn(BASE | {"azione": "CONFERMA", "coincide_con_gruppo": "si"})[1][0][0], "conferma")
        self.assertEqual(self.turn(BASE | {"azione": None, "coincide_con_gruppo": "si"})[1][0][0], "conferma")

    def test_exams_and_texts_cleaned(self):
        """TEST specialist: exams written as an object and a motivation written as a list become clean text."""
        out, _ = self.turn(BASE | {"azione": "rivedi", "coincide_con_gruppo": "no", "diagnosi": "Polmonite",
                                   "esami_consigliati": {"esame": "RX torace"}, "motivazione": ["a", "b"]})
        self.assertEqual(out["group_hypothesis"]["recommended_exams"], ["RX torace"])
        self.assertTrue(out["round_table"][0].content.startswith("a, b"))

    def test_propose_with_lowercase_urgency(self):
        """TEST specialist: a lowercase urgency in a proposal is accepted."""
        out, actions = self.turn(BASE | {"azione": "proponi", "diagnosi": "Bronchite", "urgenza": "verde"}, gh=None)
        self.assertEqual(actions[0][0], "proponi")
        self.assertEqual(out["group_hypothesis"]["urgency_level"], "VERDE")

    def test_unreadable_answer_is_a_failed_turn(self):
        """TEST specialist: a truncated answer only counts a failed turn, never a confirmation."""
        out, _ = self.turn("risposta troncata {\"azione\": \"conf")
        self.assertEqual(out, {"failed_turns": {"general_practitioner": 1}})

    def test_api_error_is_a_failed_turn(self):
        """TEST specialist: an API error during the call counts a failed turn instead of crashing the graph."""
        out, _ = self.turn(RuntimeError("service unavailable"))
        self.assertEqual(out, {"failed_turns": {"general_practitioner": 1}})

    # --- consults to colleagues that do not exist ---
    def test_consult_to_a_missing_role_goes_to_the_general_practitioner(self):
        """TEST specialist: a consult to a role outside the 10 available is redirected to the GP."""
        _, actions = self.turn(CONFIRM | {"azione": "consulta", "to": "allergologo", "message": "domanda?"}, role="pulmonologist")
        self.assertEqual(actions, [("consulta", "general_practitioner")])

    def test_redirected_consult_says_who_was_asked_for(self):
        """TEST specialist: a consult redirected to the GP says in the chat which missing specialist was asked for."""
        self.turn(CONFIRM | {"consulto_utile": "si", "collega_da_consultare": "ematologo",
                             "domanda_per_il_collega": "servono test della coagulazione?"}, role="pulmonologist")
        self.assertIn('a **Medicina** (richiesta per "ematologo", specialista non disponibile)', self.last_message())
        self.turn(CONFIRM | {"azione": "consulta", "to": "pediatra", "message": "dosi?"}, role="pulmonologist")
        self.assertIn('(richiesta per "pediatra", specialista non disponibile)', self.last_message())
        self.turn(CONFIRM | {"consulto_utile": "si", "collega_da_consultare": "cardiologist",
                             "domanda_per_il_collega": "domanda?"}, role="pulmonologist")
        self.assertNotIn("richiesta per", self.last_message())

    def test_general_practitioner_cannot_consult_itself(self):
        """TEST specialist: the GP asking a missing role cannot be redirected to itself, so it counts as a confirmation."""
        _, actions = self.turn(CONFIRM | {"azione": "consulta", "to": "allergologo", "consulto_utile": "si",
                                          "collega_da_consultare": "allergologo"})
        self.assertEqual(actions[0][0], "conferma")

    def test_role_from_italian_names(self):
        """TEST specialist: roles are recognized from Italian specialty and doctor names with prefixes."""
        cases = {"Dermatologia": "dermatologist", "il dermatologo": "dermatologist", "Dott. Cardiologo": "cardiologist",
                 "oculista": "ophthalmologist", "otorino": "ent", "medico di base": "general_practitioner",
                 "pulmonologist.": "pulmonologist", "allergologo": None, None: None}
        for name, role in cases.items():
            with self.subTest(name=name):
                self.assertEqual(roundtable._role_from_name(name), role)

    # --- notes added to the prompt ---
    def test_pediatric_note_only_for_minors(self):
        """TEST specialist: the PAZIENTE PEDIATRICO note appears for minors (years or months) and not for adults."""
        for age, expected in (("14", True), ("8 mesi", True), ("45", False), ("trenta", False)):
            with self.subTest(age=age):
                self.llm.prompts.clear()
                self.turn(CONFIRM, card=CARD.model_copy(update={"age": age}))
                self.assertEqual("PAZIENTE PEDIATRICO" in self.llm.prompts[0], expected)

    def test_second_opinion_instruction_only_for_the_added_role(self):
        """TEST specialist: the SECONDO PARERE instruction goes only to the role added for the second opinion."""
        self.llm.prompts.clear()
        self.turn(CONFIRM, role="general_practitioner", second_opinion_role="general_practitioner")
        self.turn(CONFIRM, role="pulmonologist", second_opinion_role="general_practitioner")
        self.assertIn("SECONDO PARERE", self.llm.prompts[0])
        self.assertNotIn("SECONDO PARERE", self.llm.prompts[1])

    def test_long_entries_cut_in_the_transcript(self):
        """TEST specialist: a very long entry is cut in the transcript read by colleagues."""
        long_entry = RoundTableEntry(author="pulmonologist", azione="conferma", content="parola " * 1000)
        text = roundtable._format_round_table([long_entry])
        self.assertLess(len(text), roundtable.MAX_ENTRY_CHARS_IN_TRANSCRIPT + 100)
        self.assertTrue(text.endswith("[…]"))

    def test_guideline_chunks_reach_the_prompt_with_citation(self):
        """TEST specialist: retrieved guideline chunks appear in the prompt with document and page."""
        chunk = RetrievedChunk(text="La spirometria e' indicata...", source_file="pneumo_bpco_2023.pdf", page_number=12, score=0.2)
        with helpers.mock.patch.object(specialist, "retrieve", lambda queries, role=None, k=3: [chunk]):
            self.turn(CONFIRM, role="pulmonologist")
        self.assertIn("[pneumo_bpco_2023, p. 12] La spirometria", self.llm.prompts[0])

    def test_consult_text_is_added_to_the_search(self):
        """TEST specialist: a question addressed to this specialist is added to the guideline search queries."""
        searched = []
        question = RoundTableEntry(author="pulmonologist", to="general_practitioner", azione="consulta",
                                   content="serve la profilassi antibiotica?")

        def fake_retrieve(queries, role=None, k=3):
            searched.extend(queries)
            return []
        with helpers.mock.patch.object(specialist, "retrieve", fake_retrieve):
            self.turn(CONFIRM, round_table=[question])
        self.assertIn("Medicina - serve la profilassi antibiotica?", searched)
        self.assertIn("mini-consulto", self.llm.prompts[0])


class TestCompactPrompt(unittest.TestCase):
    def test_placeholders_and_required_fields(self):
        """TEST specialist prompt: all placeholders format and every required JSON field is present."""
        from src.agents.prompts import SPECIALIST_PROMPT
        SPECIALIST_PROMPT.format(role_display="X", role="x", card="c", hypothesis="h", round_table="r",
                                 linee_guida="l", consulto_pendente="p")
        for field in ("consulto_utile", "collega_da_consultare", "domanda_per_il_collega", "valutazione_indipendente",
                      "coincide_con_gruppo", "ipotesi_alternativa_scartata", "motivo_scarto", "fonti_consultate",
                      "esami_consigliati", "BREVITA'", "FATTI E IPOTESI", "COLLEGHI DISPONIBILI"):
            with self.subTest(field=field):
                self.assertIn(field, SPECIALIST_PROMPT)
        # the vasculitis examples (almost the answer to one test case) are gone
        self.assertNotIn("porpora palpabile", SPECIALIST_PROMPT)

    def test_not_reported_is_not_absent_rule(self):
        """TEST prompts: specialists and primary are told that a sign not reported is unknown, not absent."""
        from src.agents.prompts import PRIMARY_PROMPT, SPECIALIST_PROMPT
        self.assertIn("un segno non riferito NON e' assente", SPECIALIST_PROMPT)
        self.assertIn("X non riferito, da verificare", SPECIALIST_PROMPT)
        self.assertIn("NON e' assente", PRIMARY_PROMPT)

    def test_available_colleagues_list_every_role(self):
        """TEST specialist prompt: the list of available colleagues names all 10 roles of the system."""
        from src.agents.prompts import ALL_SPECIALISTS, SPECIALIST_PROMPT
        colleagues = SPECIALIST_PROMPT.split("COLLEGHI DISPONIBILI")[1].split("\n")[0]
        for role in ALL_SPECIALISTS:
            with self.subTest(role=role):
                self.assertIn(f"{role} ({roundtable.SPECIALIST_DISPLAY_NAMES[role]})", colleagues)


if __name__ == "__main__":
    unittest.main()
