"""Whole conversations on the real graph, from the fiscal code to the summary report."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

try:
    from . import helpers
except ImportError:
    import helpers

J, S = helpers.intake_answer, helpers.symptoms_answer
SUPERVISOR = {"specialists": ["pulmonologist", "general_practitioner"]}
PROPOSE = {"azione": "proponi", "diagnosi": "Bronchite acuta", "urgenza": "VERDE", "esami_consigliati": ["RX torace"],
           "dettagli": "d", "consulto_utile": "no", "ipotesi_alternativa_scartata": "polmonite", "motivo_scarto": "x",
           "fonti_consultate": "nessuna pertinente"}
CONFIRM = {"azione": "conferma", "valutazione_indipendente": "stessa", "coincide_con_gruppo": "si", "consulto_utile": "no",
           "ipotesi_alternativa_scartata": "polmonite", "motivo_scarto": "x", "fonti_consultate": "nessuna pertinente",
           "motivazione": "d'accordo"}
PRIMARY = {"diagnosis": "Bronchite acuta", "urgency_level": "VERDE", "operational_guidance": "Ambulatorio.",
           "recommendations": "Quadro lieve."}
# Supervisor, then: pulmonologist proposes, GP confirms, both confirm in the verification round, primary.
TABLE = [SUPERVISOR, PROPOSE, CONFIRM, CONFIRM, CONFIRM, PRIMARY]


class TestEndToEnd(helpers.VitaTestCase):
    def test_full_path_from_fiscal_code_to_report(self):
        """TEST end to end: CF, data, symptoms, no photo, table and report, pausing exactly once per operator message."""
        conv = helpers.Conversation(self)
        conv.send("1234")
        self.assertEqual(conv.paused_before, ("user",))
        conv.send("Marco Esposito 41 anni uomo nessuna allergia nessuna patologia",
                  [J(first_name="Marco", last_name="Esposito", age="41", sex="uomo")])
        conv.send("confermo", [J(confirm=True)])
        conv.send("tosse forte da 2 giorni", [S(("tosse", "forte", "2 giorni"))])
        conv.send("confermo", [S(confirm=True)])
        self.assertIn("È disponibile una foto", self.last_message())
        conv.send("no", TABLE)

        self.assertEqual(self.llm.answers, [])           # every planned model call was made
        self.assertEqual(conv.paused_before, ())          # the graph reached END
        final = helpers.as_dict(conv.values["final_diagnosis"])
        self.assertEqual((final["diagnosis"], final["urgency_level"]), ("Bronchite acuta", "VERDE"))
        report = self.last_message()
        self.assertIn("**Report di sintesi**", report)
        self.assertIn("**Specialisti coinvolti** Pneumologia, Medicina", report)

    def test_error_mid_flow_keeps_the_state_and_resumes(self):
        """TEST end to end: a model error during symptoms leaves the card intact and the same message can be sent again."""
        conv = helpers.go_to_symptoms(helpers.Conversation(self))
        with self.assertRaises(RuntimeError):
            conv.send("tosse forte da 2 giorni", [RuntimeError("service down")])
        self.assertEqual(conv.card["first_name"], "Marco")
        conv.send("tosse forte da 2 giorni", [S(("tosse", "forte", "2 giorni"))])
        self.assertEqual(conv.symptoms, [("tosse", "forte", "2 giorni")])
        self.assertIn("Confermi i dati?", self.last_message())

    def test_two_conversations_are_isolated(self):
        """TEST end to end: two chats on the same graph (two threads) never share patient data."""
        app = helpers.graph.generate_graph()
        first, second = helpers.Conversation(self, app), helpers.Conversation(self, app)
        first.send("1234")
        second.send("RSSMRA80A01H501U")
        first.send("Luca Bianchi", [J(first_name="Luca", last_name="Bianchi")])
        second.send("Anna Neri", [J(first_name="Anna", last_name="Neri")])
        self.assertEqual((first.card["fiscal_code"], first.card["first_name"]), ("1234", "Luca"))
        self.assertEqual((second.card["fiscal_code"], second.card["first_name"]), ("RSSMRA80A01H501U", "Anna"))

    def test_photo_attached_early_is_analysed_without_asking(self):
        """TEST end to end: a photo attached while describing symptoms is kept and analysed as soon as the photo step starts."""
        conv = helpers.go_to_symptoms(helpers.Conversation(self))
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            photo = Path(d) / "arm.png"
            Image.new("RGB", (60, 60), (200, 120, 110)).save(photo)
            conv.send("escoriazione al braccio, dolore lieve da ieri", [S(("escoriazione al braccio", "lieve", "da ieri"))],
                      photo=photo)
            self.assertEqual(conv.card["symptom"]["photo"]["photo_url"], str(photo))
            vision = [{"lesion_type": "escoriazione", "description": "Superficiale."}]
            conv.send("confermo", [S(confirm=True)] + TABLE, vision=vision)
        self.assertNotIn("È disponibile una foto", "\n".join(self.messages_from("Fotografia")))
        self.assertEqual(conv.card["symptom"]["photo"]["injury_type"], "escoriazione")
        self.assertEqual(conv.paused_before, ())


if __name__ == "__main__":
    unittest.main()
