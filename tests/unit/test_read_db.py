"""read_db: fiscal code check and database lookup."""
import unittest

try:
    from . import helpers
except ImportError:
    import helpers

from src.agents.persistence import is_valid_fiscal_code, normalize_fiscal_code


class TestFiscalCode(unittest.TestCase):
    def test_valid_codes(self):
        """TEST fiscal code: real codes and the test code 1234 are accepted."""
        for cf in ("RSSMRA80A01H501U", "MRTMTT25D09F205Z", "1234"):
            with self.subTest(cf=cf):
                self.assertTrue(is_valid_fiscal_code(cf))

    def test_case_and_spaces_are_cleaned(self):
        """TEST fiscal code: lowercase letters, spaces and line breaks are cleaned before the check."""
        self.assertEqual(normalize_fiscal_code("rss mra 80a01 h501u"), "RSSMRA80A01H501U")
        self.assertEqual(normalize_fiscal_code(" RSSMRA80A01\nH501U "), "RSSMRA80A01H501U")
        self.assertTrue(is_valid_fiscal_code(normalize_fiscal_code("rss mra 80a01 h501u")))

    def test_invalid_codes(self):
        """TEST fiscal code: typos, wrong check character, wrong format and wrong length are rejected."""
        for cf in ("RSSMRB80A01H501U",   # one wrong letter
                   "RSSMRA08A01H501U",   # two digits swapped
                   "RSSMRA80A01H501X",   # wrong check character
                   "AAAAAAAAAAAAAAAA",   # 16 characters but wrong format
                   "RSSMRA80Z01H501U",   # month that does not exist
                   "RSSMRA80A01H501",    # 15 characters
                   "BUONGIORNOATUTTI"):
            with self.subTest(cf=cf):
                self.assertFalse(is_valid_fiscal_code(cf))

    def test_omocodia_has_a_single_valid_check_character(self):
        """TEST fiscal code: a code with omocodia letters has exactly one valid check character."""
        valid = [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if is_valid_fiscal_code("RSSMRA80A01H50M" + c)]
        self.assertEqual(valid, ["M"])


class TestReadDb(helpers.VitaTestCase):
    def test_wrong_code_is_asked_again_then_new_patient(self):
        """TEST read_db: a wrong code is asked again; a valid unknown one opens a new card without calling the model."""
        conv = helpers.Conversation(self)
        conv.send("RSSMRB80A01H501U")
        self.assertIn("non costituisce un Codice Fiscale valido", self.last_message())
        self.assertEqual(conv.next_step, "read_db")

        conv.send("rss mra 80a01 h501u")
        self.assertFalse(conv.values.get("patient_exists"))
        self.assertEqual(conv.card.get("fiscal_code"), "RSSMRA80A01H501U")
        self.assertIn("Codice Fiscale non presente", self.messages_from("System")[0])
        self.assertIn("**Scheda paziente**", self.messages_from("Anagrafica")[0])
        self.assertEqual(self.llm.prompts, [])

    def test_registered_patient(self):
        """TEST read_db: a registered patient is loaded with their data and the card is shown for confirmation."""
        self.add_patient(fiscal_code="MRTMTT25D09F205Z", first_name="Matteo", last_name="Moretti", age="45", sex="M",
                         allergies=["Penicillina"], previous_conditions=["ipertensione"])
        conv = helpers.Conversation(self)
        conv.send("MRTMTT25D09F205Z")
        self.assertTrue(conv.values.get("patient_exists"))
        self.assertEqual(conv.card.get("first_name"), "Matteo")
        self.assertEqual(conv.card.get("allergies"), ["Penicillina"])
        self.assertTrue(conv.values.get("allergies_addressed"))
        self.assertIn("Scheda clinica recuperata", self.messages_from("System")[0])
        self.assertIn("Confermi i dati?", self.messages_from("Anagrafica")[0])

    def test_database_error_keeps_the_fiscal_code(self):
        """TEST read_db: a database error does not lose the fiscal code and the patient is treated as new."""
        class BrokenDatabase:
            def read_patient(self, cf):
                raise RuntimeError("database unreachable")

        with helpers.mock.patch.object(helpers.persistence, "mdb", BrokenDatabase()):
            conv = helpers.Conversation(self)
            conv.send("RSSMRA80A01H501U")
        self.assertEqual(conv.card.get("fiscal_code"), "RSSMRA80A01H501U")
        self.assertFalse(conv.values.get("patient_exists"))
        self.assertIn("errore di connessione al database", self.messages_from("System")[0])

    def test_test_code_1234(self):
        """TEST read_db: the test code 1234 goes straight to intake."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        self.assertEqual(conv.card.get("fiscal_code"), "1234")
        self.assertEqual(conv.next_step, "intake")


if __name__ == "__main__":
    unittest.main()
