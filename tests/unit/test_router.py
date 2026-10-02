"""Specialists' round table: the router alone, and the real graph (router + specialists + primary)."""
import json
import unittest

try:
    from . import helpers
except ImportError:
    import helpers

from src.agents import clinical
from src.graph import router
from src.state import MedicalState, PatientCard, SymptomProfile, Symptom, GroupHypothesis, RoundTableEntry

BASE = {"consulto_utile": "no", "to": None, "ipotesi_alternativa_scartata": "alt", "motivo_scarto": "x",
        "fonti_consultate": "nessuna pertinente", "message": ""}
PROPOSE = BASE | {"azione": "proponi", "diagnosi": "Vasculite IgA", "urgenza": "ARANCIONE", "esami_consigliati": [], "dettagli": "d"}
CONFIRM = BASE | {"azione": "conferma", "valutazione_indipendente": "stessa", "coincide_con_gruppo": "si", "motivazione": "d'accordo"}
REVISE = BASE | {"azione": "rivedi", "valutazione_indipendente": "allergia", "coincide_con_gruppo": "no",
                 "diagnosi": "Reazione allergica", "urgenza": "ROSSO", "motivazione": "cambio idea dopo i colleghi"}
PRIMARY = {"diagnosis": "finale", "urgency_level": "ARANCIONE", "operational_guidance": "x", "recommendations": "x"}
BROKEN = "risposta troncata {\"azione\": \"conf"

GASTRO, DERMA, GP = "gastroenterologist", "dermatologist", "general_practitioner"


def entry(author, action="conferma", to=None, explicit=True, verification=False):
    """HELPER entry: one round-table entry."""
    return RoundTableEntry(author=author, azione=action, to=to, to_explicit=explicit, content="x", verification=verification)


def table(roles, confirmed=(), entries=(), **state):
    """HELPER table: a state with these roles seated, the hypothesis confirmed by `confirmed` and these entries."""
    gh = GroupHypothesis(diagnosis="d", urgency_level="VERDE", confirmed_by=list(confirmed))
    return MedicalState(needed_specialists={r: True for r in roles}, group_hypothesis=gh, round_table=list(entries), **state)


class TestRouter(unittest.TestCase):
    def test_total_turn_cap_goes_to_the_primary(self):
        """TEST router: at MAX_TOTAL_TURNS the discussion ends and the primary speaks, whatever the state."""
        out = router(table([GASTRO, DERMA], total_turns=clinical.MAX_TOTAL_TURNS))
        self.assertEqual(out["next_step"], "chief_physician")

    def test_at_most_one_recruited_colleague(self):
        """TEST router: a consult to an absent colleague recruits them only while the recruitment cap is not full."""
        consult = entry(GASTRO, "consulta", to="cardiologist")
        out = router(table([GASTRO, DERMA], confirmed=[GASTRO], entries=[consult]))
        self.assertEqual(out["next_step"], "cardiologist")
        self.assertEqual(out["recruited_specialists_count"], 1)
        self.assertIn("cardiologist", out["needed_specialists"])

        full = router(table([GASTRO, DERMA], confirmed=[GASTRO], entries=[consult],
                            recruited_specialists_count=clinical.MAX_RECRUITED_SPECIALISTS))
        self.assertEqual(full["next_step"], DERMA)
        self.assertNotIn("cardiologist", full["needed_specialists"])

    def test_reaction_reopening_when_called_by_name(self):
        """TEST router: when everyone confirmed but the last entry names a seated colleague, that colleague reacts once."""
        out = router(table([GASTRO, DERMA], confirmed=[GASTRO, DERMA],
                           entries=[entry(GASTRO), entry(DERMA, to=GASTRO)]))
        self.assertEqual(out["next_step"], GASTRO)
        self.assertEqual(out["verifying_role"], "")

    def test_no_reopening_for_an_automatic_recipient_or_exhausted_speaker(self):
        """TEST router: no reaction turn if the recipient was set automatically or has no turns left."""
        automatic = router(table([GASTRO, DERMA], confirmed=[GASTRO, DERMA],
                                 entries=[entry(GASTRO), entry(DERMA, to=GASTRO, explicit=False)]))
        self.assertTrue(automatic.get("verification_started"))
        exhausted = router(table([GASTRO, DERMA], confirmed=[GASTRO, DERMA],
                                 entries=[entry(GASTRO)] * clinical.MAX_SPEAKS_PER_SPECIALIST + [entry(DERMA, to=GASTRO)]))
        self.assertTrue(exhausted.get("verification_started"))

    def test_open_consult_keeps_the_table_open(self):
        """TEST router: a lone specialist who confirmed but asked an absent colleague does not close the table."""
        out = router(table([GASTRO], confirmed=[GASTRO], entries=[entry(GASTRO, "proponi"), entry(GASTRO, "consulta", to=DERMA)]))
        self.assertEqual(out["next_step"], DERMA)

    def test_verification_round_skips_roles_with_failed_turns(self):
        """TEST router: the final verification round skips whoever used up their failed turns."""
        out = router(table([GASTRO, DERMA], confirmed=[GASTRO], entries=[entry(GASTRO, "proponi")],
                           failed_turns={DERMA: clinical.MAX_FAILED_TURNS}))
        self.assertEqual(out["passed_without_confirming"], [DERMA])
        self.assertEqual((out["next_step"], out["verification_queue"]), (GASTRO, []))

    def test_action_and_consult_in_the_same_turn_count_once(self):
        """TEST router: a confirmation followed by a consult in the same turn counts as one turn, not two."""
        from src.graph import _turns_spoken
        entries = [entry(GASTRO, "proponi"), entry(GASTRO, "consulta", to=DERMA), entry(DERMA),
                   entry(GASTRO, verification=True)]
        self.assertEqual(_turns_spoken(entries, GASTRO), 1)
        self.assertEqual(_turns_spoken(entries, DERMA), 1)


class Script:
    """HELPER Script: fake model for the table, answering by the role found in the prompt and recording the turn order."""

    def __init__(self, answers):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.turns = []
        self.primary_prompt = ""

    def __call__(self, prompt, llm=None):
        if "Medico Primario" in prompt:
            self.turns.append("PRIMARY")
            self.primary_prompt = prompt
            return json.dumps(PRIMARY)
        for role, name in clinical.SPECIALIST_DISPLAY_NAMES.items():
            if f"Sei uno specialista in {name} ({role})" in prompt:
                self.turns.append(role + (" [VERIFY]" if "GIRO DI VERIFICA FINALE: tutti" in prompt else ""))
                item = self.answers[role].pop(0)
                return item if isinstance(item, str) else json.dumps(item)
        raise AssertionError("prompt not recognized")


class TestRoundTable(helpers.VitaTestCase):
    def discussion(self, seated, answers):
        """HELPER discussion: runs the table from the supervisor onwards (the seated roles are chosen by the test)."""
        script = Script(answers)
        with helpers.mock.patch.object(clinical, "stream_response", script):
            app = helpers.graph.generate_graph()
            config = {"configurable": {"thread_id": "t"}}
            card = PatientCard(first_name="X", age="34", sex="donna", symptom=SymptomProfile(symptoms=[
                Symptom(description="dolore addominale", intensity="forte", duration="6 ore")]))
            app.update_state(config, MedicalState(patient_card=card).model_dump())
            app.update_state(config, {"needed_specialists": {r: True for r in seated}}, as_node="supervisor")

            async def _go():
                async for _ in app.astream_events(None, config=config, version="v2"):
                    pass
            helpers.run(_go)
        s = app.get_state(config).values
        return script, s, helpers.as_dict(s["group_hypothesis"])

    def test_everyone_confirms_also_in_the_verification_round(self):
        """TEST round table: proposal, confirmation, one verification turn each, then the primary."""
        c, s, gh = self.discussion([GASTRO, DERMA], {GASTRO: [PROPOSE, CONFIRM], DERMA: [CONFIRM, CONFIRM]})
        self.assertEqual(c.turns, [GASTRO, DERMA, f"{GASTRO} [VERIFY]", f"{DERMA} [VERIFY]", "PRIMARY"])
        self.assertEqual(sorted(gh["confirmed_by"]), [DERMA, GASTRO])

    def test_revision_in_the_verification_round_reopens_the_discussion(self):
        """TEST round table: a revision during verification forces the others to confirm the new version."""
        c, s, gh = self.discussion([GASTRO, DERMA], {GASTRO: [PROPOSE, CONFIRM, CONFIRM], DERMA: [CONFIRM, REVISE]})
        self.assertEqual(c.turns[-2:], [GASTRO, "PRIMARY"])
        self.assertEqual(gh["diagnosis"], "Reazione allergica")
        self.assertEqual(sorted(gh["confirmed_by"]), [DERMA, GASTRO])

    def test_a_single_specialist_still_does_the_verification(self):
        """TEST round table: a specialist alone at the table still has the verification turn."""
        c, s, gh = self.discussion([GASTRO], {GASTRO: [PROPOSE, CONFIRM]})
        self.assertEqual(c.turns, [GASTRO, f"{GASTRO} [VERIFY]", "PRIMARY"])

    def test_two_failed_turns_pass_without_counting_as_confirmed(self):
        """TEST round table: after two failed turns a specialist passes, is not counted as confirming, and the primary is told."""
        c, s, gh = self.discussion([GASTRO, DERMA], {GASTRO: [PROPOSE, CONFIRM, CONFIRM], DERMA: [BROKEN] * 5})
        self.assertEqual(s["failed_turns"], {DERMA: 2})
        self.assertEqual(gh["confirmed_by"], [GASTRO])
        self.assertEqual(s["passed_without_confirming"], [DERMA])
        self.assertIn("il loro silenzio NON e' un assenso): Dermatologia", c.primary_prompt)

    def test_who_runs_out_of_turns_then_confirms_in_verification(self):
        """TEST round table: after three revisions each, both still confirm in the verification round."""
        c, s, gh = self.discussion([GASTRO, DERMA], {GASTRO: [PROPOSE, REVISE, REVISE, CONFIRM, CONFIRM],
                                                     DERMA: [REVISE, REVISE, REVISE, CONFIRM, CONFIRM]})
        self.assertEqual(sorted(gh["confirmed_by"]), [DERMA, GASTRO])
        self.assertEqual(s["passed_without_confirming"], [])

    def test_consult_to_a_missing_colleague_answered_by_the_general_practitioner(self):
        """TEST round table: a consult to a missing role recruits the GP, whose answer goes back to the asker."""
        allergo = {"consulto_utile": "si", "collega_da_consultare": "allergologo", "domanda_per_il_collega": "quali test?"}
        gp_answer = CONFIRM | allergo | {"azione": "consulta", "to": "allergologo", "motivazione": "RISPOSTA AL DERMATOLOGO"}
        c, s, gh = self.discussion([GASTRO, DERMA], {GASTRO: [PROPOSE, CONFIRM, CONFIRM, CONFIRM],
                                                     DERMA: [REVISE | allergo, CONFIRM, CONFIRM, CONFIRM],
                                                     GP: [gp_answer, gp_answer, CONFIRM, CONFIRM]})
        self.assertNotIn(GP, s["failed_turns"])
        gp_entries = [e for e in s["round_table"] if e.author == GP and not e.verification]
        self.assertEqual((gp_entries[0].azione, gp_entries[0].to), ("conferma", DERMA))
        self.assertIn(GP, gh["confirmed_by"])

    def test_endless_disagreement_stops_at_the_turn_cap(self):
        """TEST round table: two specialists who keep revising never exceed MAX_TOTAL_TURNS model calls."""
        c, s, gh = self.discussion([GASTRO, DERMA, GP], {GASTRO: [PROPOSE] + [REVISE] * 10,
                                                         DERMA: [REVISE] * 10, GP: [REVISE] * 10})
        self.assertLessEqual(len(c.turns) - 1, clinical.MAX_TOTAL_TURNS)
        self.assertEqual(c.turns[-1], "PRIMARY")


if __name__ == "__main__":
    unittest.main()
