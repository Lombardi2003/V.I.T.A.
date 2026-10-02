"""reviewer: symptoms shown every turn, confirmation, corrections, anti-invention, robustness."""
import unittest

try:
    from . import helpers
except ImportError:
    import helpers

S = helpers.symptoms_answer


class TestReviewer(helpers.VitaTestCase):
    def setUp(self):
        super().setUp()
        self.conv = helpers.go_to_symptoms(helpers.Conversation(self))

    def test_first_pass_asks_for_symptoms_without_the_model(self):
        """TEST reviewer: right after the personal data, symptoms are requested without a model call."""
        self.assertIn("Descrivere i sintomi: natura del disturbo, intensità e durata.", self.messages_from("Revisore"))

    def test_durations_like_this_morning_and_one_hour_are_kept(self):
        """TEST reviewer: durations such as "da stamattina" and "un'ora" are not discarded."""
        self.conv.send("vedo sfocato da stamattina, in modo lieve", [S(("vista sfocata", "lieve", "da stamattina"))])
        self.conv.send("ho anche vertigini forti da un'ora", [S(("vertigini", "forte", "un'ora"))])
        self.assertEqual(self.conv.symptoms, [("vista sfocata", "lieve", "da stamattina"), ("vertigini", "forte", "un'ora")])

    def test_missing_intensity_then_confirmation(self):
        """TEST reviewer: a missing intensity is asked with the allowed values, then the confirmation leads to the photo."""
        self.conv.send("mal di gola da 2 giorni", [S(("mal di gola", "", "2 giorni"))])
        self.assertIn('Mancano: intensità di "mal di gola".', self.last_message())
        self.assertIn("Intensità: lieve, moderata, forte o insopportabile.", self.last_message())
        self.conv.send("e' forte", [S(("mal di gola", "forte", ""))])
        self.assertIn("Confermi i dati?", self.last_message())
        self.conv.send("confermo", [S(confirm=True)])
        self.assertIn("Dati clinici confermati.", self.messages_from("Revisore"))
        self.assertEqual(self.conv.values.get("photo_request_shown"), True)

    def test_yes_with_a_change_does_not_confirm_and_removal(self):
        """TEST reviewer: "yes but..." is a correction, not a confirmation; a symptom can be removed."""
        self.conv.send("tosse secca moderata da 3 giorni e nausea lieve da ieri",
                       [S(("tosse secca", "moderata", "3 giorni"), ("nausea", "lieve", "da ieri"))])
        self.conv.send("si ma la tosse e' forte", [S(("tosse secca", "forte", ""), confirm=True)])
        self.assertEqual(self.conv.next_step, "reviewer")
        self.assertEqual(self.conv.symptoms[0], ("tosse secca", "forte", "3 giorni"))
        self.conv.send("la nausea no, era un errore", [S(remove=["Nausea"])])
        self.assertEqual([s[0] for s in self.conv.symptoms], ["tosse secca"])

    def test_removal_written_as_object_or_text(self):
        """TEST reviewer: symptoms_to_remove works when written as objects or as plain text."""
        self.conv.send("tosse forte da 2 giorni e febbre forte da ieri",
                       [S(("tosse", "forte", "2 giorni"), ("febbre", "forte", "da ieri"))])
        self.conv.send("togli la febbre", [S() | {"symptoms_to_remove": [{"description": "febbre"}]}])
        self.assertEqual([s[0] for s in self.conv.symptoms], ["tosse"])
        self.conv.send("togli la tosse", [S() | {"symptoms_to_remove": "tosse"}])
        self.assertEqual(self.conv.symptoms, [])

    def test_unnamed_correction_with_a_single_symptom(self):
        """TEST reviewer: with one symptom, a correction that does not name it is applied."""
        self.conv.send("mal di gola forte da 2 giorni", [S(("mal di gola", "forte", "2 giorni"))])
        self.conv.send("no, e' moderata", [S(("mal di gola", "moderata", ""))])
        self.assertEqual(self.conv.symptoms, [("mal di gola", "moderata", "2 giorni")])

    def test_unnamed_correction_with_two_symptoms_is_discarded(self):
        """TEST reviewer: with two complete symptoms, a correction that names neither is discarded."""
        self.conv.send("tosse forte da 2 giorni e febbre forte da ieri",
                       [S(("tosse", "forte", "2 giorni"), ("febbre", "forte", "da ieri"))])
        self.conv.send("no, e' moderata", [S(("tosse", "moderata", ""))])
        self.assertEqual(self.conv.symptoms[0], ("tosse", "forte", "2 giorni"))

    def test_characteristics_are_shown(self):
        """TEST reviewer: characteristics are shown in the "Sintomo N" block."""
        self.conv.send("dolore al petto forte da 30 minuti che va verso il braccio sinistro",
                       [S(("dolore toracico", "forte", "30 minuti", "", "irradiato al braccio sinistro"))])
        self.assertIn("**Caratteristiche** irradiato al braccio sinistro", self.last_message())
        self.assertIn("**Sintomo 1**", self.last_message())

    def test_unrequested_confirmation_ignored_and_broken_json_does_not_confirm(self):
        """TEST reviewer: a confirmation before the data is complete, or a broken JSON, never confirms."""
        self.conv.send("mal di gola", [S(("mal di gola", "", ""), confirm=True)])
        self.assertEqual(self.conv.next_step, "reviewer")
        self.conv.send("forte, da 2 giorni", [S(("mal di gola", "forte", "2 giorni"))])
        self.conv.send("confermo", ["risposta troncata {\"upd"])
        self.assertEqual(self.conv.next_step, "reviewer")
        self.conv.send("confermo", [S(confirm="si")])
        self.assertTrue(self.conv.values.get("symptoms_confirmed"))

    def test_wrong_shaped_answers_do_not_block(self):
        """TEST reviewer: null updated_card or symptom does not break the node."""
        self.conv.send("tosse", [{"updated_card": None}])
        self.conv.send("tosse", [{"updated_card": {"symptom": None}}])
        self.assertEqual(self.conv.next_step, "reviewer")

    # --- anti-invention ---
    def test_invented_intensity_is_discarded(self):
        """TEST reviewer: an intensity not supported by any word in the message is discarded."""
        self.conv.send("mal di testa da 2 giorni", [S(("mal di testa", "forte", "2 giorni"))])
        self.assertEqual(self.conv.symptoms, [("mal di testa", "", "2 giorni")])

    def test_invented_duration_is_discarded(self):
        """TEST reviewer: a duration not supported by any time word in the message is discarded."""
        self.conv.send("mal di testa forte", [S(("mal di testa", "forte", "3 ore"))])
        self.assertEqual(self.conv.symptoms, [("mal di testa", "forte", "")])

    def test_update_to_the_wrong_symptom_is_rejected(self):
        """TEST reviewer: with two incomplete symptoms, an update to the one the message does not name is rejected."""
        self.conv.send("tosse e febbre", [S(("tosse", "", ""), ("febbre", "", ""))])
        self.conv.send("la febbre e' forte", [S(("tosse", "forte", ""))])
        self.assertEqual(self.conv.symptoms, [("tosse", "", ""), ("febbre", "", "")])

    def test_moderato_becomes_moderata(self):
        """TEST reviewer: the masculine "moderato" is normalized to the allowed value "moderata"."""
        self.conv.send("dolore moderato da ieri", [S(("dolore lombare", "moderato", "da ieri"))])
        self.assertEqual(self.conv.symptoms, [("dolore lombare", "moderata", "da ieri")])
        self.assertIn("Confermi i dati?", self.last_message())

    def test_items_without_description_or_not_objects_are_ignored(self):
        """TEST reviewer: symptom items without a description, or that are not objects, are ignored."""
        answer = {"updated_card": {"symptom": {"symptoms": [{"intensity": "forte", "duration": "2 giorni"}, "tosse", None,
                                                            {"description": "tosse", "intensity": "forte",
                                                             "duration": "2 giorni"}]}}}
        self.conv.send("tosse forte da 2 giorni", [answer])
        self.assertEqual(self.conv.symptoms, [("tosse", "forte", "2 giorni")])


if __name__ == "__main__":
    unittest.main()
