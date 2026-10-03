"""save_db: the patient card saved after the report, and the triage hypothesis stored as "not confirmed"."""
import unittest
from datetime import datetime

try:
    from . import helpers
except ImportError:
    import helpers

from src.agents import persistence
from src.state import FinalDiagnosis, MedicalState, PatientCard, Symptom, SymptomProfile

CF = "RSSMRA80A01H501U"
TODAY = datetime.now().strftime("%d/%m/%Y")
ENTRY = f"Ipotesi al triage del {TODAY}: Bronchite acuta (codice VERDE, non confermata)"
FINAL = FinalDiagnosis(diagnosis="Bronchite acuta.", urgency_level="VERDE")
J, S = helpers.intake_answer, helpers.symptoms_answer


def card(**fields):
    """HELPER card: a confirmed patient card with one symptom."""
    base = dict(fiscal_code=CF, first_name="Mario", last_name="Rossi", age="46", sex="uomo", allergies=["lattice"],
                previous_conditions=["diabete"],
                symptom=SymptomProfile(symptoms=[Symptom(description="tosse", intensity="forte", duration="2 giorni")]))
    return PatientCard(**(base | fields))


class TestSaveDb(helpers.VitaTestCase):
    def save(self, patient=None, final=FINAL):
        """HELPER save: runs save_db_node on a finished triage and returns the record now in the database."""
        patient = patient or card()
        helpers.run(persistence.save_db_node, MedicalState(patient_card=patient, final_diagnosis=final))
        return self.db.read_patient(patient.fiscal_code)

    def test_new_patient_saved_in_full(self):
        """TEST save_db: a new patient is created with every field, including sex and allergies."""
        record = self.save()
        self.assertEqual((record.first_name, record.last_name, record.age, record.sex), ("Mario", "Rossi", "46", "uomo"))
        self.assertEqual(record.allergies, ["lattice"])
        self.assertIn("Scheda paziente salvata.", self.last_message())

    def test_hypothesis_stored_as_not_confirmed(self):
        """TEST save_db: the hypothesis goes into previous conditions with date, code and "non confermata", after the real ones."""
        record = self.save()
        self.assertEqual(record.previous_conditions, ["diabete", ENTRY])
        self.assertIn("registrata tra le patologie pregresse come non confermata", self.last_message())

    def test_returning_patient_is_updated_with_corrections(self):
        """TEST save_db: for a registered patient the corrected card replaces the stored one."""
        self.add_patient(fiscal_code=CF, first_name="Mario", last_name="Rosi", age="45", sex="M",
                         allergies=["Penicillina"], previous_conditions=["diabete"])
        record = self.save()
        self.assertEqual((record.last_name, record.age, record.sex, record.allergies), ("Rossi", "46", "uomo", ["lattice"]))
        self.assertEqual(record.previous_conditions, ["diabete", ENTRY])
        self.assertIn("Scheda paziente aggiornata.", self.last_message())

    def test_test_code_is_never_saved(self):
        """TEST save_db: the test code 1234 is never written to the database."""
        self.assertIsNone(self.save(card(fiscal_code="1234")))
        self.assertIn("Codice di prova: nessun salvataggio", self.last_message())

    def test_database_error_does_not_crash(self):
        """TEST save_db: a database error is reported to the operator instead of crashing the graph."""
        class BrokenDatabase:
            def upsert_patient(self, patient_card):
                raise RuntimeError("disk full")

        with helpers.mock.patch.object(persistence, "mdb", BrokenDatabase()):
            out = helpers.run(persistence.save_db_node, MedicalState(patient_card=card(), final_diagnosis=FINAL))
        self.assertIn("Salvataggio non riuscito", self.last_message())
        self.assertNotIn("patient_card", out)

    def test_undetermined_diagnosis_adds_no_entry(self):
        """TEST save_db: when the triage produced no hypothesis (technical fallback) the card is saved without an entry."""
        final = FinalDiagnosis(diagnosis=f"{persistence.UNDETERMINED_DIAGNOSIS_PREFIX} per un errore tecnico.",
                               urgency_level="ARANCIONE")
        self.assertEqual(self.save(final=final).previous_conditions, ["diabete"])
        self.assertEqual(self.last_message(), "Scheda paziente salvata.")

    def test_same_entry_is_not_duplicated(self):
        """TEST save_db: saving the same hypothesis twice on the same day keeps a single entry."""
        self.save()
        record = self.save(card(previous_conditions=["diabete", ENTRY]))
        self.assertEqual(record.previous_conditions, ["diabete", ENTRY])

    def test_upsert_tells_created_from_updated(self):
        """TEST database: upsert_patient returns True when it creates the patient and False when it updates it."""
        data = card().model_dump()
        self.assertTrue(self.db.upsert_patient(data))
        self.assertFalse(self.db.upsert_patient(data | {"age": "47"}))
        self.assertEqual(self.db.read_patient(CF).age, "47")


class TestReturningPatient(helpers.VitaTestCase):
    SUPERVISOR = {"specialists": ["general_practitioner"]}
    PROPOSE = {"azione": "proponi", "diagnosi": "Bronchite acuta", "urgenza": "VERDE", "esami_consigliati": [],
               "dettagli": "d", "consulto_utile": "no", "ipotesi_alternativa_scartata": "polmonite", "motivo_scarto": "x",
               "fonti_consultate": "nessuna pertinente"}
    CONFIRM = {"azione": "conferma", "valutazione_indipendente": "stessa", "coincide_con_gruppo": "si",
               "consulto_utile": "no", "ipotesi_alternativa_scartata": "polmonite", "motivo_scarto": "x",
               "fonti_consultate": "nessuna pertinente", "motivazione": "ok"}
    PRIMARY = {"diagnosis": "Bronchite acuta", "urgency_level": "VERDE", "operational_guidance": "x", "recommendations": "y"}

    def test_second_visit_shows_the_hypothesis_and_the_operator_can_remove_it(self):
        """TEST end to end: a whole first visit is saved; at the second visit the hypothesis is in the card and can be removed."""
        first = helpers.Conversation(self)
        first.send(CF)
        first.send("Mario Rossi 46 anni uomo nessuna allergia, ha il diabete",
                   [J(first_name="Mario", last_name="Rossi", age="46", sex="uomo", previous_conditions=["diabete"])])
        first.send("confermo", [J(confirm=True)])
        first.send("tosse forte da 2 giorni", [S(("tosse", "forte", "2 giorni"))])
        first.send("confermo", [S(confirm=True)])
        first.send("no", [self.SUPERVISOR, self.PROPOSE, self.CONFIRM, self.PRIMARY])
        self.assertEqual(first.paused_before, ())
        self.assertIn("**Report di sintesi**", "\n".join(self.messages_from("Primario")))
        self.assertEqual(self.db.read_patient(CF).previous_conditions, ["diabete", ENTRY])

        second = helpers.Conversation(self)
        second.send(CF)
        self.assertIn("Scheda clinica recuperata", self.messages_from("System")[0])
        self.assertIn(f"**Patologie pregresse** diabete, {ENTRY}", self.last_message())
        second.send("togli l'ipotesi del triage, era sbagliata", [J(remove_conditions=[ENTRY])])
        self.assertEqual(second.card["previous_conditions"], ["diabete"])


if __name__ == "__main__":
    unittest.main()
