"""The benchmark cases: 15 adult patients, three per triage code, each built from one row of the regional triage manual."""

from dataclasses import dataclass

from src.state import PatientCard, Symptom, SymptomProfile

MANUAL = "generale_fvg_manuale_triage_adulto_2018.pdf"  # Source of every expected code (data/guidelines).
LEVELS = ["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"]  # The system's codes, most urgent first.
CODE_COLOURS = dict(zip(range(1, 6), LEVELS))  # The manual numbers its codes 1-5: 1 is the most urgent.
TEST_FISCAL_CODE = "1234"  # The app's test code: these patients are never saved in the database.


@dataclass(frozen=True)
class Case:
    """One patient, with the manual row that gives the expected code."""
    id: str
    title: str
    card: PatientCard
    manual_code: int  # The code of the row, 1-5.
    expected_role: str  # The specialist the supervisor should choose.
    sheet: str  # The triage sheet of the manual.
    row: str  # The row of the sheet, as written in the manual.
    page: int  # Page number printed on the manual.
    core: bool = False  # True for the five cases also run by the models with little quota.
    role_from_sheet: bool = True  # False when the sheet names no specialty and the role was assigned by hand.

    @property
    def expected_code(self) -> str:
        """The expected colour code."""
        return CODE_COLOURS[self.manual_code]


def _symptom(description, intensity, duration, characteristics="", trigger=""):
    """One confirmed symptom."""
    return Symptom(description=description, intensity=intensity, duration=duration,
                   characteristics=characteristics, trigger=trigger)


def _card(first_name, last_name, age, sex, symptoms, previous_conditions=()):
    """A confirmed patient card, without photo."""
    return PatientCard(fiscal_code=TEST_FISCAL_CODE, first_name=first_name, last_name=last_name, age=str(age), sex=sex,
                       previous_conditions=list(previous_conditions), symptom=SymptomProfile(symptoms=symptoms))


CASES = [
    # ROSSO (code 1)
    Case("01", "Facial droop, weak arm and speech trouble for one hour",
         _card("Aldo", "Ferri", 68, "uomo", [
             _symptom("bocca storta verso destra", "forte", "1 ora",
                      "comparsa all'improvviso, ora di esordio certa; non assume anticoagulanti"),
             _symptom("mancanza di forza al braccio destro", "forte", "1 ora"),
             _symptom("difficoltà a parlare", "forte", "1 ora", "parole biascicate")],
             previous_conditions=["ipertensione"]),
         1, "neurologist", "Disturbi neurologici",
         "Alterazione di mimica facciale / motilità arti / disturbi del linguaggio entro le 5 ore", 36, core=True),
    Case("02", "Asthmatic who cannot speak, blue lips",
         _card("Carla", "Monti", 45, "donna", [
             _symptom("difficoltà a respirare", "insopportabile", "40 minuti",
                      "non riesce a parlare per la fatica a respirare, labbra bluastre")],
             previous_conditions=["asma"]),
         1, "pulmonologist", "Compromissione respiratoria", "Severa", 15, role_from_sheet=False),
    Case("03", "Deep knife wound to the thigh, heavy bleeding",
         _card("Luca", "Serra", 30, "uomo", [
             _symptom("ferita profonda alla coscia sinistra", "forte", "20 minuti",
                      "ferita penetrante, sanguinamento abbondante", "colpo di coltello")]),
         1, "orthopedist", "Trauma: arti", "Ferita penetrante inguine / coscia", 25, role_from_sheet=False),

    # ARANCIONE (code 2)
    Case("04", "Oppressive chest pain radiating to the left arm, with sweating",
         _card("Franco", "Russo", 63, "uomo", [
             _symptom("dolore al petto", "forte", "30 minuti", "oppressivo, irradiato al braccio sinistro"),
             _symptom("sudorazione", "moderata", "20 minuti")],
             previous_conditions=["ipertensione"]),
         2, "cardiologist", "Dolore toracico", "Dolore toracico in atto", 28, core=True, role_from_sheet=False),
    Case("05", "One episode of dark blood in the vomit, now only weak",
         _card("Pietro", "Gallo", 55, "uomo", [
             _symptom("vomito con sangue scuro", "moderata", "2 ore",
                      "un solo episodio, sangue scuro tipo fondo di caffè"),
             _symptom("debolezza", "lieve", "2 ore")]),
         2, "gastroenterologist", "Emorragie non traumatiche", "Ematemesi / vomito caffeano", 41,
         role_from_sheet=False),
    Case("06", "Sudden painless loss of sight in one eye",
         _card("Rosa", "Villa", 70, "donna", [
             _symptom("perdita della vista dall'occhio sinistro", "forte", "1 ora",
                      "improvvisa, completa, senza dolore")]),
         2, "ophthalmologist", "Problema specifico - Oculistico", "Cecità monoculare improvvisa", 49),

    # AZZURRO (code 3)
    Case("07", "Unable to pass urine for eight hours",
         _card("Mario", "Conti", 72, "uomo", [
             _symptom("impossibilità a urinare", "moderata", "8 ore", "tensione moderata al basso ventre")],
             previous_conditions=["ipertrofia prostatica"]),
         3, "urologist", "Problema specifico - Urologico", "Ritenzione acuta d'urina", 53, core=True),
    Case("08", "Swollen painful wrist after a fall at home, no deformity",
         _card("Elena", "Costa", 50, "donna", [
             _symptom("dolore al polso destro", "forte", "3 ore",
                      "polso gonfio, non riesce a muoverlo, nessuna deformità visibile",
                      "caduta in casa sulla mano")]),
         3, "orthopedist", "Trauma: arti", "Sospetta frattura", 25, role_from_sheet=False),
    Case("09", "Usual migraine attack that does not respond to the usual drug",
         _card("Sara", "Greco", 38, "donna", [
             _symptom("mal di testa", "forte", "6 ore",
                      "uguale alle crisi di emicrania abituali, non passa con il farmaco abituale")],
             previous_conditions=["emicrania"]),
         3, "neurologist", "Cefalea", "Crisi di cefalea nota o senza criteri di priorità", 35),

    # VERDE (code 4)
    Case("10", "Nausea, vomiting and diarrhoea for one day, no fever",
         _card("Paolo", "Riva", 28, "uomo", [
             _symptom("nausea e vomito", "moderata", "1 giorno",
                      "temperatura 36,8 °C, nessun dolore addominale importante"),
             _symptom("diarrea", "moderata", "1 giorno", "senza sangue")]),
         4, "gastroenterologist", "Problema specifico - Chirurgico / Gastrointestinale",
         "Nausea / vomito / diarrea", 54, core=True),
    Case("11", "Feeling of a fish bone in the throat, swallows and breathes normally",
         _card("Giulia", "Fontana", 40, "donna", [
             _symptom("sensazione di lisca di pesce in gola", "lieve", "2 ore",
                      "deglutisce e respira normalmente", "dopo aver mangiato pesce")]),
         4, "ent", "Problema specifico - Otoiatrico", "Corpo estraneo orecchio / naso / gola", 50),
    Case("12", "Low back pain for two days after an effort",
         _card("Marco", "Leone", 45, "uomo", [
             _symptom("mal di schiena lombare", "moderata", "2 giorni",
                      "non irradiato, nessun disturbo urinario", "dopo uno sforzo, peggiora con i movimenti")]),
         4, "orthopedist", "Problema specifico - Muscolo-scheletrico", "Lombalgia", 55),

    # BIANCO (code 5)
    Case("13", "Ear pain for two days, temperature 37.5",
         _card("Giorgio", "Marchi", 58, "uomo", [
             _symptom("dolore all'orecchio destro", "moderata", "2 giorni"),
             _symptom("febbre", "lieve", "1 giorno", "temperatura 37,5 °C")]),
         5, "ent", "Problema specifico - Otoiatrico",
         "Otalgia / otorragia (with: Alterazione della temperatura < 38 °C, p. 29)", 50, core=True),
    Case("14", "Ingrown toenail, red and sore for a week",
         _card("Anna", "Rinaldi", 25, "donna", [
             _symptom("unghia incarnita all'alluce destro", "moderata", "1 settimana",
                      "arrossata e dolente, temperatura 36,6 °C")]),
         5, "dermatologist", "Problema specifico - Cute e tessuti molli",
         "Lesione cutanea non traumatica / tumefazione", 48),
    Case("15", "Cough and blocked nose for four days, no fever",
         _card("Davide", "Sala", 35, "uomo", [
             _symptom("tosse", "lieve", "4 giorni"),
             _symptom("naso chiuso", "lieve", "4 giorni", "temperatura 36,7 °C, respira bene")]),
         5, "general_practitioner", "Problema specifico - Medicina generale",
         "Tosse, rinite ed altri sintomi aspecifici delle prime vie aeree", 46, role_from_sheet=False),
]

CASES_BY_ID = {case.id: case for case in CASES}  # For choosing cases from the command line.
