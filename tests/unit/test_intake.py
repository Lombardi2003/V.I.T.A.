"""intake: personal data card shown every turn, confirmation, corrections, robustness."""
import unittest

try:
    from . import helpers
except ImportError:
    import helpers

from src.agents.intake import _format_card, _normalize_card
from src.state import PatientCard

J = helpers.intake_answer


class TestNormalization(unittest.TestCase):
    def test_sex_and_capital_initials(self):
        """TEST intake normalization: sex becomes uomo/donna and names get capital initials."""
        cases = [(("giulia", "verdi", "donna"), ("Giulia", "Verdi", "donna")),
                 (("MARIO", "DE LUCA", "Maschio"), ("Mario", "De Luca", "uomo")),
                 (("anna maria", "d'angelo", "f"), ("Anna Maria", "D'Angelo", "donna")),
                 (("Kevin", "McKenzie", "m"), ("Kevin", "McKenzie", "uomo")),
                 (("luca", "rossi-bianchi", "non specificato"), ("Luca", "Rossi-Bianchi", "non specificato"))]
        for (fn, ln, sex), expected in cases:
            with self.subTest(name=fn):
                c = _normalize_card(PatientCard(first_name=fn, last_name=ln, sex=sex))
                self.assertEqual((c.first_name, c.last_name, c.sex), expected)

    def test_compact_card(self):
        """TEST intake card: compact bold layout; a brand-new patient shows only the fiscal code."""
        text = _format_card(PatientCard(fiscal_code="1234", first_name="Giulia", last_name="Verdi", age="52", sex="donna",
                                        allergies=["lattice"]), True, False)
        self.assertIn("**Scheda paziente**", text)
        self.assertIn("**CF** 1234 · **Paziente** Giulia Verdi · **Età** 52 anni · **Sesso** donna", text)
        self.assertIn("**Allergie** lattice · **Patologie pregresse** da indicare", text)
        self.assertNotIn("Allergie", _format_card(PatientCard(fiscal_code="1234"), False, False))


class TestIntake(helpers.VitaTestCase):
    def test_new_patient_data_in_pieces_correction_and_confirmation(self):
        """TEST intake: data given in pieces, an unrequested confirmation ignored, a "yes but" treated as a correction."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        self.assertIn("Mancano: nome, cognome, età, sesso, allergie, patologie pregresse.", self.last_message())

        answer = J(first_name="Luca", last_name="Bianchi", age="30", sex="uomo", confirm=True)
        answer |= {"allergies_addressed": False, "previous_conditions_addressed": False}
        conv.send("Luca Bianchi, 30 anni, uomo", [answer])
        self.assertIn("Mancano: allergie, patologie pregresse.", self.last_message())
        self.assertEqual(conv.next_step, "intake")

        conv.send("non ha allergie ne' patologie pregresse", [J()])
        self.assertIn("Confermi i dati?", self.last_message())

        conv.send("si' ma ha 31 anni", [J(age="31", confirm=True)])
        self.assertIn("**Età** 31 anni", self.last_message())
        self.assertEqual(conv.next_step, "intake")

        conv.send("confermo", [J(confirm=True)])
        self.assertIn("Dati anagrafici confermati.", self.messages_from("Anagrafica"))
        self.assertTrue(conv.values.get("card_confirmed"))
        self.assertIn("Descrivere i sintomi", self.messages_from("Revisore")[0])

    def test_registered_patient_remove_an_allergy(self):
        """TEST intake: an allergy loaded from the database can be removed (case and spaces ignored)."""
        self.add_patient(fiscal_code="MRTMTT25D09F205Z", first_name="Matteo", last_name="Moretti", age="45", sex="M",
                         allergies=["Penicillina"], previous_conditions=["ipertensione"])
        conv = helpers.Conversation(self)
        conv.send("MRTMTT25D09F205Z")
        self.assertIn("**Sesso** uomo", self.last_message())

        conv.send("non e' allergico alla penicillina", [J(remove_allergies=[" penicillina "])])
        self.assertEqual(conv.card["allergies"], [])
        self.assertIn("**Allergie** nessuna", self.last_message())

        conv.send("ok", [J(confirm=True)])
        self.assertTrue(conv.values.get("card_confirmed"))

    def test_registered_without_stored_allergies_asks_for_them(self):
        """TEST intake: a registered patient with no stored allergies is still asked about them."""
        self.add_patient(fiscal_code="RSSMRA80A01H501U", first_name="Mario", last_name="Rossi", age="46", sex="M",
                         allergies=[], previous_conditions=["diabete"])
        conv = helpers.Conversation(self)
        conv.send("RSSMRA80A01H501U")
        self.assertIn("Mancano: allergie.", self.last_message())

    def test_unreadable_answer_during_confirmation_does_not_confirm(self):
        """TEST intake: a truncated model answer during the confirmation never counts as a confirmation."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        conv.send("Luca Bianchi 30 anni uomo nessuna allergia nessuna patologia",
                  [J(first_name="Luca", last_name="Bianchi", age="30", sex="uomo")])
        conv.send("confermo", ["risposta troncata {\"updated"])
        self.assertFalse(conv.values.get("card_confirmed"))
        self.assertIn("Confermi i dati?", self.last_message())

    def test_wrong_shaped_answers_do_not_block_and_fiscal_code_stays(self):
        """TEST intake: null or text updated_card is ignored and the model cannot change the fiscal code."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        conv.send("Luca", [{"updated_card": None}])
        conv.send("Luca", [{"updated_card": "Luca Bianchi"}])
        conv.send("Luca", [J(first_name="Luca", fiscal_code="XXXXXX00X00X000X")])
        self.assertEqual(conv.card["fiscal_code"], "1234")
        self.assertEqual(conv.card["first_name"], "Luca")

    def test_lists_written_as_text_and_duplicates(self):
        """TEST intake: a list written as text is accepted and duplicates are dropped ignoring case."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        conv.send("allergico al lattice", [J(allergies="lattice")])
        conv.send("e alla Penicillina, anzi penicillina", [J(allergies=["Penicillina", "penicillina", "LATTICE"])])
        self.assertEqual(conv.card["allergies"], ["lattice", "Penicillina"])

    def test_confirmation_written_as_text(self):
        """TEST intake: "true" written as text counts as a confirmation."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        conv.send("Luca Bianchi 30 anni uomo nessuna allergia nessuna patologia",
                  [J(first_name="Luca", last_name="Bianchi", age="30", sex="uomo")])
        conv.send("si", [J() | {"conferma": "true"}])
        self.assertTrue(conv.values.get("card_confirmed"))

    # --- anti-invention and safety nets ---
    def test_addressed_flag_never_goes_back_to_false(self):
        """TEST intake: once allergies are addressed, a later model "false" does not reset the flag."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        conv.send("nessuna allergia", [J()])
        conv.send("si chiama Luca", [J(first_name="Luca") | {"allergies_addressed": False}])
        self.assertTrue(conv.values.get("allergies_addressed"))

    def test_allergy_keyword_sets_the_flag_even_if_the_model_misses_it(self):
        """TEST intake: "allerg" in the message marks allergies as addressed even if the model says false."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        conv.send("e' maschio e non ha allergie", [J(sex="uomo") | {"allergies_addressed": False,
                                                                     "previous_conditions_addressed": False}])
        self.assertTrue(conv.values.get("allergies_addressed"))
        self.assertFalse(conv.values.get("previous_conditions_addressed"))

    def test_empty_fields_from_the_model_never_blank_known_data(self):
        """TEST intake: empty strings and lists returned by the model never erase data already in the card."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        conv.send("Luca Bianchi 30 anni", [J(first_name="Luca", last_name="Bianchi", age="30", allergies=["lattice"])])
        conv.send("uomo", [J(sex="uomo", first_name="", last_name="", age="", allergies=[])])
        self.assertEqual((conv.card["first_name"], conv.card["last_name"], conv.card["age"]), ("Luca", "Bianchi", "30"))
        self.assertEqual(conv.card["allergies"], ["lattice"])

    def test_list_items_written_as_objects_are_read(self):
        """TEST intake: list items written as objects ({"name": ...}) become plain text, empty ones are dropped."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        conv.send("allergico a penicillina e lattice",
                  [J(allergies=[{"name": "penicillina"}, {"nome": "lattice"}, "", None])])
        self.assertEqual(conv.card["allergies"], ["penicillina", "lattice"])


if __name__ == "__main__":
    unittest.main()
