"""benchmark: the measures are computed correctly and the cases are well formed. No model is called."""
import unittest
from unittest import mock

try:
    from . import helpers  # noqa: F401  (sets up the environment: project path, UTF-8)
except ImportError:
    import helpers  # noqa: F401

from benchmark import metrics, steps, table
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

    def test_time_without_the_waits_and_sheet_delivered(self):
        """TEST summarize: the time is counted without the waits before a retry, which are reported apart; the delivered sheets are counted."""
        s = metrics.summarize([_record("ROSSO", "ROSSO", seconds=250, wait_seconds=190, sheet_delivered=True),
                               _record("ROSSO", "ROSSO", seconds=30, wait_seconds=0, sheet_delivered=False),
                               _record("ROSSO", "ROSSO", seconds=50)])
        self.assertEqual((s["seconds"], s["wait"], s["sheet"]), (140 / 3, 95, 1))

    def test_runs_of_the_same_case(self):
        """TEST summarize: three runs of one case are three records and one case."""
        s = metrics.summarize([_record("ROSSO", "ROSSO", run=n) for n in (1, 2, 3)])
        self.assertEqual((s["n"], s["cases"], s["exact"]), (3, 1, 3))


class TestStability(unittest.TestCase):
    def test_only_repeated_cases_count(self):
        """TEST stability: a case run once is not counted; a repeated case is stable only if every run gave the same code."""
        records = [_record("ROSSO", "ROSSO", case="01", run=1), _record("ROSSO", "ROSSO", case="01", run=2),
                   _record("VERDE", "VERDE", case="10", run=1), _record("VERDE", "AZZURRO", case="10", run=2),
                   _record("BIANCO", "BIANCO", case="13", run=1)]
        self.assertEqual(metrics.stability(records), (1, 2))
        s = metrics.summarize(records)
        self.assertEqual((s["stable"], s["repeated"]), (1, 2))

    def test_a_missing_answer_breaks_stability(self):
        """TEST stability: a run without a code makes the case unstable; the same wrong code every time is stable."""
        self.assertEqual(metrics.stability([_record("ROSSO", "ROSSO", run=1), _record("ROSSO", None, run=2)]), (0, 1))
        self.assertEqual(metrics.stability([_record("VERDE", "ROSSO", run=1), _record("VERDE", "ROSSO", run=2)]), (1, 1))

    def test_no_repetitions(self):
        """TEST stability: with one run per case nothing is repeated."""
        self.assertEqual(metrics.stability([_record("ROSSO", "ROSSO", case="01"), _record("VERDE", "VERDE", case="10")]), (0, 0))


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


class TestReviewSheet(unittest.TestCase):
    def test_one_section_per_core_case(self):
        """TEST review: the sheet has the five core cases, each with the patient; the report is quoted, a missing case is said."""
        from benchmark import review
        records = [_record("ARANCIONE", "ROSSO", case="04", report="**Report di sintesi**\n\n**Codice** ROSSO"),
                   _record("VERDE", "VERDE", case="10", report=None),
                   dict(_record("BIANCO", "VERDE", case="13", report="solo il modello"), condition="baseline"),
                   _record("ROSSO", "ROSSO", case="02", report="caso non del nucleo")]
        text = review.build_review("MODEL_A", records)
        self.assertEqual(text.count("\n## Case "), 5)
        self.assertEqual(text.count("**Patient.**"), 5)
        self.assertIn("> **Report di sintesi**\n>\n> **Codice** ROSSO", text)
        self.assertEqual(text.count("*Not run yet.*"), 3)      # 01, 07 and 13 (13 has only the model alone)
        self.assertEqual(text.count("*No report produced.*"), 1)
        self.assertNotIn("caso non del nucleo", text)
        self.assertEqual(text.count("**Invented details (number):**"), 2)


def _upto(step):
    """HELPER _upto: the records of a model that has completed the steps up to this one, every code right."""
    records = []
    for number in range(1, step + 1):
        for case_id, condition in steps.step_items(number):
            case = next(c for c in CASES if c.id == case_id)
            records.append(dict(_record(case.expected_code, case.expected_code, case=case_id, role=case.expected_role,
                                        roles=[case.expected_role], core=case.core), condition=condition))
    return records


class TestModelAlonePrompt(helpers.VitaTestCase):
    def test_same_specialist_list_and_rule_as_the_supervisor(self):
        """TEST model alone: the specialists are asked with the supervisor's own list and rule on names, so the two conditions get the same instruction."""
        from benchmark import baseline
        from src.agents.prompts import SUPERVISOR_PROMPT
        with mock.patch.object(baseline, "retrieve", lambda queries, role=None, k=3: []):
            prompt = baseline.build_prompt(CASES[0])
        listed = [line for line in SUPERVISOR_PROMPT.splitlines() if "->" in line and line.strip()[0].isdigit()]
        self.assertEqual(len(listed), len(ALL_SPECIALISTS))
        for line in listed:
            self.assertIn(line.strip(), prompt)
        self.assertIn("Usa SOLO i nomi esatti tra virgolette nella lista sopra.", prompt)
        self.assertNotIn("(Otorinolaringoiatria)", prompt)   # the form that invited a copy with the label


class TestSteps(unittest.TestCase):
    def test_the_three_steps_cover_everything_once(self):
        """TEST steps: step 1 is the model alone on the 15 cases, step 2 the system on the 5 core cases, step 3 the system on the other 10."""
        self.assertEqual([(steps.STEPS[n][1], len(steps.STEPS[n][2])) for n in (1, 2, 3)],
                         [("baseline", 15), ("system", 5), ("system", 10)])
        system_cases = steps.STEPS[2][2] + steps.STEPS[3][2]
        self.assertEqual(sorted(system_cases), [case.id for case in CASES])
        self.assertEqual(steps.STEPS[2][2], [case.id for case in CASES if case.core])

    def test_step_reached_needs_every_step_before(self):
        """TEST steps: a step counts only with all the ones before it; one missing case keeps a model at the step below."""
        self.assertEqual([steps.step_reached(_upto(n)) for n in (0, 1, 2, 3)], [0, 1, 2, 3])
        self.assertEqual(steps.step_reached(_upto(2)[:-1]), 1)
        only_system = [r for r in _upto(3) if r["condition"] == "system"]
        self.assertEqual(steps.step_reached(only_system), 0)
        self.assertEqual(steps.missing_items(_upto(1), 2), steps.step_items(2))

    def test_a_repetition_does_not_complete_a_step(self):
        """TEST steps: a second run of a case does not stand for its first run."""
        records = _upto(1)[:-1] + [dict(_upto(1)[-1], run=2)]
        self.assertEqual(steps.step_reached(records), 0)


class TestTable(unittest.TestCase):
    def test_a_step_table_lists_only_the_models_that_completed_it(self):
        """TEST table: each step has its table, with only the models that completed the step and the cases of that step."""
        results = {"FULL": _upto(3), "CORE": _upto(2), "ALONE": _upto(1), "STARTED": _upto(1)[:4]}
        models = {step: [row[0] for row in table.step_rows(results, step)] for step in (1, 2, 3)}
        self.assertEqual(models[1], ["FULL", "CORE", "ALONE"])
        self.assertEqual(models[2], ["FULL", "FULL", "CORE", "CORE"])      # full system and model alone, on the core cases
        self.assertEqual(models[3], ["FULL", "FULL"])
        core_rows = table.step_rows(results, 2)
        self.assertEqual([row[1:4] for row in core_rows[:2]], [["Full system", "5", "5"], ["Model alone", "5", "5"]])
        self.assertEqual(table.step_rows(results, 3)[0][1:4], ["Full system", "15", "15"])
        self.assertIn("No model has completed this step yet", table.build_step_table({"ALONE": _upto(1)}, 2))

    def test_status_says_the_step_reached(self):
        """TEST table: the progress gives the step each model completed and the cases done per condition."""
        results = {"FULL": _upto(3), "ALONE": _upto(1), "STARTED": _upto(1)[:13], "HALF": _upto(2)[:-2]}
        rows = {line.split(" | ")[0].strip("| "): line for line in table.build_status(results).splitlines()[2:]}
        self.assertEqual(rows["FULL"], "| FULL | 3 - complete | 15/15 | 15/15 |")
        self.assertEqual(rows["ALONE"], "| ALONE | 1 - minimum | 15/15 | 0/15 |")
        self.assertEqual(rows["STARTED"], "| STARTED | 0 - not started | 13/15 | 0/15 |")
        self.assertEqual(rows["HALF"], "| HALF | 1 - minimum | 15/15 | 3/15 |")

    def test_csv_files_hold_the_same_numbers(self):
        """TEST table csv: table.csv has the rows of the three step tables as plain numbers; cases.csv has one row per case run."""
        results = {"FULL": _upto(3)}
        summary = table.table_csv_rows(results)
        self.assertEqual([row[:3] for row in summary[1:]],
                         [[1, "FULL", "Model alone"], [2, "FULL", "Full system"], [2, "FULL", "Model alone"],
                          [3, "FULL", "Full system"], [3, "FULL", "Model alone"]])
        first = dict(zip(summary[0], summary[1]))
        self.assertEqual((first["Cases"], first["Records"], first["Exact"], first["Within one"], first["Specialty"]),
                         (15, 15, 15, 15, 15))
        self.assertEqual((first["Kappa"], first["Turns"], first["Tokens"]), (1, None, None))
        # No cell is a fraction like 3/15: a spreadsheet would read it as a date.
        self.assertFalse(any("/" in str(cell) for row in summary[1:] for cell in row))
        per_case = table.cases_csv_rows({"A": [_record("ARANCIONE", "VERDE", case="04", roles=["ent"], core=True)]})
        self.assertEqual(len(per_case), 2)
        row = dict(zip(per_case[0], per_case[1]))
        self.assertEqual((row["Model"], row["Case"], row["Condition"], row["Expected code"], row["Given code"],
                          row[table.ERROR_COLUMN], row["Role ok"]),
                         ("A", "04", "Full system", "ARANCIONE", "VERDE", 2, "no"))

    def test_csv_file_opens_in_a_spreadsheet(self):
        """TEST table csv: the file is written with the encoding a spreadsheet reads, and an empty value is an empty cell."""
        import csv
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "t.csv"
            table._write_csv(path, [["Model", "Turns"], ["A · b", None]])
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as f:
                self.assertEqual(list(csv.reader(f)), [["Model", "Turns"], ["A · b", ""]])

    def test_case_table_marks_the_direction(self):
        """TEST table: one row per case; a more urgent code is marked as over-triage, a less urgent one as under-triage."""
        results = {"A": [_record("ARANCIONE", "ROSSO", case="04"), _record("ROSSO", "ROSSO", case="01", run=1),
                         _record("ROSSO", "AZZURRO", case="01", run=2), _record("BIANCO", None, case="13")],
                   "B": [_record("ARANCIONE", "ARANCIONE", case="04")]}
        rows = {line.split(" | ")[0].strip("| "): line for line in table.build_case_table(results, "system").splitlines()[2:]}
        self.assertEqual(len(rows), 15)
        self.assertEqual(rows["04 ★"], "| 04 ★ | ARANCIONE | ROSSO ▲ | ARANCIONE |")
        self.assertEqual(rows["01 ★"], "| 01 ★ | ROSSO | ROSSO / AZZURRO ▼ | - |")
        self.assertEqual(rows["13 ★"], "| 13 ★ | BIANCO | no answer | - |")
        self.assertEqual(rows["02"], "| 02 | ROSSO | - | - |")
        self.assertNotIn("ROSSO", table.build_case_table(results, "baseline").split("| 04 ★ |")[1].splitlines()[0])


if __name__ == "__main__":
    unittest.main()
