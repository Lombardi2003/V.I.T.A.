"""benchmark: the measures are computed correctly and the cases are well formed. No model is called."""
import unittest

try:
    from . import helpers  # noqa: F401  (sets up the environment: project path, UTF-8)
except ImportError:
    import helpers  # noqa: F401

from benchmark import metrics, table
from benchmark.cases import CASES, CODE_COLOURS, LEVELS, TEST_FISCAL_CODE
from src.agents.persistence import TEST_FISCAL_CODE as APP_TEST_FISCAL_CODE
from src.agents.prompts import ALL_SPECIALISTS
from src.agents.roundtable import URGENCY_LEVELS


def _record(expected, given, case="01", role="cardiologist", roles=("cardiologist",), **extra):
    """HELPER _record: one result record with this expected and given code."""
    return {"case": case, "condition": "system", "run": 1, "expected_code": expected, "code": given,
            "expected_role": role, "roles": list(roles), **extra}


class TestCodeError(unittest.TestCase):
    def test_direction_of_the_error(self):
        """TEST code_error: a less urgent code than expected is positive (under-triage), a more urgent one negative."""
        self.assertEqual(metrics.code_error("ARANCIONE", "ARANCIONE"), 0)
        self.assertEqual(metrics.code_error("ARANCIONE", "VERDE"), 2)
        self.assertEqual(metrics.code_error("BIANCO", "ROSSO"), -4)
        self.assertEqual(metrics.code_error("ROSSO", "BIANCO"), 4)

    def test_no_code(self):
        """TEST code_error: a missing or unknown code gives None."""
        self.assertIsNone(metrics.code_error("AZZURRO", None))
        self.assertIsNone(metrics.code_error("AZZURRO", "GIALLO"))


class TestSummary(unittest.TestCase):
    def test_counts(self):
        """TEST summarize: exact, within one level, under-triage, over-triage and no answer are counted apart."""
        s = metrics.summarize([
            _record("ARANCIONE", "ARANCIONE", case="01"),
            _record("ARANCIONE", "VERDE", case="02"),      # under-triage, two levels
            _record("BIANCO", "ROSSO", case="03"),         # over-triage, four levels
            _record("AZZURRO", "ARANCIONE", case="04"),    # over-triage, one level
            _record("AZZURRO", None, case="05"),           # no report
        ])
        self.assertEqual((s["n"], s["cases"]), (5, 5))
        self.assertEqual((s["exact"], s["within_one"]), (1, 2))
        self.assertEqual((s["under"], s["over"], s["no_answer"]), (1, 2, 1))

    def test_specialty_and_invalid_answers(self):
        """TEST summarize: the expected role must be among those chosen; invalid answers are summed."""
        s = metrics.summarize([
            _record("ROSSO", "ROSSO", roles=["neurologist", "cardiologist"], invalid_answers=2),
            _record("ROSSO", "ROSSO", roles=["neurologist"], invalid_answers=1),
            _record("ROSSO", "ROSSO", roles=[]),
        ])
        self.assertEqual((s["role_ok"], s["invalid_answers"]), (1, 3))

    def test_means_skip_missing_values(self):
        """TEST summarize: a mean uses only the records that have the value, and is None when none has it."""
        s = metrics.summarize([_record("ROSSO", "ROSSO", seconds=10, turns=4), _record("ROSSO", "ROSSO", seconds=30)])
        self.assertEqual((s["seconds"], s["turns"], s["tokens"]), (20, 4, None))

    def test_runs_of_the_same_case(self):
        """TEST summarize: three runs of one case are three records and one case."""
        s = metrics.summarize([_record("ROSSO", "ROSSO", run=n) for n in (1, 2, 3)])
        self.assertEqual((s["n"], s["cases"], s["exact"]), (3, 1, 3))


class TestKappa(unittest.TestCase):
    def test_perfect_agreement(self):
        """TEST weighted_kappa: every code right gives 1."""
        self.assertEqual(metrics.weighted_kappa([(level, level) for level in LEVELS]), 1)

    def test_always_the_same_code(self):
        """TEST weighted_kappa: a model that always answers the same code gives 0, whatever the code."""
        for fixed in ("ROSSO", "AZZURRO"):
            self.assertAlmostEqual(metrics.weighted_kappa([(level, fixed) for level in LEVELS]), 0)

    def test_reversed_scale(self):
        """TEST weighted_kappa: the scale read upside down gives -1."""
        self.assertAlmostEqual(metrics.weighted_kappa(list(zip(LEVELS, reversed(LEVELS)))), -1)

    def test_known_value(self):
        """TEST weighted_kappa: a small case worked out by hand (observed 0.25, by chance 1.75)."""
        pairs = [("ROSSO", "ROSSO"), ("ROSSO", "ARANCIONE"), ("AZZURRO", "AZZURRO"), ("AZZURRO", "AZZURRO")]
        self.assertAlmostEqual(metrics.weighted_kappa(pairs), 1 - 0.25 / 1.75)

    def test_not_defined(self):
        """TEST weighted_kappa: no pairs, or one single code on both sides, gives None."""
        self.assertIsNone(metrics.weighted_kappa([]))
        self.assertIsNone(metrics.weighted_kappa([("VERDE", "VERDE")] * 3))


class TestCases(unittest.TestCase):
    def test_same_codes_as_the_system(self):
        """TEST cases: the benchmark uses the system's five codes in the same order, and its test fiscal code."""
        self.assertEqual(LEVELS, URGENCY_LEVELS)
        self.assertEqual(CODE_COLOURS, {1: "ROSSO", 2: "ARANCIONE", 3: "AZZURRO", 4: "VERDE", 5: "BIANCO"})
        self.assertEqual(TEST_FISCAL_CODE, APP_TEST_FISCAL_CODE)

    def test_three_cases_per_code_and_one_core_each(self):
        """TEST cases: 15 cases with unique ids, three per code, and one core case per code."""
        self.assertEqual(len({case.id for case in CASES}), len(CASES))
        self.assertEqual(len(CASES), 15)
        for level in LEVELS:
            with self.subTest(level=level):
                of_level = [case for case in CASES if case.expected_code == level]
                self.assertEqual(len(of_level), 3)
                self.assertEqual(sum(case.core for case in of_level), 1)

    def test_every_case_is_a_valid_adult_test_patient(self):
        """TEST cases: known role, adult (the manual is for patients over 16), test fiscal code, no photo, a cited page."""
        for case in CASES:
            with self.subTest(case=case.id):
                self.assertIn(case.expected_role, ALL_SPECIALISTS)
                self.assertGreater(int(case.card.age), 16)
                self.assertEqual(case.card.fiscal_code, TEST_FISCAL_CODE)
                self.assertIsNone(case.card.symptom.photo)
                self.assertTrue(case.card.symptom.symptoms)
                self.assertTrue(case.sheet and case.row and case.page)


class TestCasesDocument(unittest.TestCase):
    def test_document_matches_the_cases(self):
        """TEST cases_doc: CASES.md is what cases.py would write now, so the readable cases are the ones that run."""
        from benchmark import cases_doc
        self.assertEqual(cases_doc.CASES_FILE.read_text(encoding="utf-8"), cases_doc.build_document())


class TestTable(unittest.TestCase):
    def test_one_row_per_model_and_condition(self):
        """TEST table: one row per model and condition, and the core table keeps only the core cases."""
        records = [_record("ROSSO", "ROSSO", case="01", core=True),
                   _record("VERDE", "ROSSO", case="11", core=False),
                   dict(_record("ROSSO", "ARANCIONE", case="01", core=True), condition="baseline")]
        full = table.build_table({"MODEL_A": records}).splitlines()
        core = table.build_table({"MODEL_A": records}, core_only=True).splitlines()
        self.assertEqual(len(full), 4)   # header, separator, two rows
        self.assertIn("| MODEL_A | Full system | 2 | 2 | 1/2 |", full[2])
        self.assertIn("| MODEL_A | Model alone | 1 | 1 | 0/1 | 1/1 | 1 | 0 |", full[3])
        self.assertIn("| MODEL_A | Full system | 1 | 1 | 1/1 |", core[2])


if __name__ == "__main__":
    unittest.main()
