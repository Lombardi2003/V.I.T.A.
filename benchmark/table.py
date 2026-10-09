"""Builds the benchmark tables from the raw results: progress, one table per step, the conditions side by side, one row per case. No model is called.

Usage, from the project folder:
    python -m benchmark.table

Writes results/TABLE.md (to read), results/table.csv and results/cases.csv (for a spreadsheet or LaTeX).
"""

import csv
import json
from pathlib import Path
import sys

from . import steps
from .cases import CASES
from .metrics import code_error, summarize

RESULTS_DIR = Path(__file__).resolve().parent / "results"  # The tables built here.
RAW_DIR = RESULTS_DIR / "raw"  # Where run.py writes one .jsonl file per model.
TABLE_FILE = RESULTS_DIR / "TABLE.md"  # Rewritten whole at every call, like the two CSV files.
TABLE_CSV = RESULTS_DIR / "table.csv"  # One row per model and step, with every measure.
CASES_CSV = RESULTS_DIR / "cases.csv"  # One row per case run: expected and given code, specialists, cost.
# As shown in the tables, in the order of the steps.
CONDITION_NAMES = {"bare": "Bare model", "rag": "Model with guidelines", "single": "Single agent", "system": "Full system"}
ERROR_COLUMN = "Error (levels, - over, + under)"  # The distance of the given code from the expected one, in cases.csv.
MEASURES = ["Cases", "Records", "Exact", "Within one", "Under", "Over", "No answer", "Kappa", "Stable", "Specialty",
            "Sheet seen", "Invalid answers", "Turns", "Seconds", "Wait", "Calls", "Tokens"]
HEADER = ["Model", "Condition"] + MEASURES
OVER_MARK, UNDER_MARK = "▲", "▼"  # Beside a code more urgent, or less urgent, than expected.
NO_ANSWER, NOT_RUN = "no answer", "-"  # A record without a code, and a case not run yet.
# What each step gives the model, for the title of its table.
STEP_CONTENT = {
    1: "the patient, the names of the codes and of the specialists",
    2: "the same, with the retrieved guidelines",
    3: "the same, with the definition of the codes and the rules of a specialist",
    4: "supervisor, round table and primary",
}


def load(results_dir: Path = RAW_DIR) -> dict[str, list[dict]]:
    """The records of every model, by results file name."""
    return {path.stem: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            for path in sorted(results_dir.glob("*.jsonl"))}


def _number(value, digits=0) -> str:
    """A mean as text, or a dash when it is not available."""
    return "-" if value is None else f"{value:.{digits}f}"


def _markdown(header: list[str], rows: list[list[str]]) -> str:
    """A Markdown table."""
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


def _measures(records: list[dict]) -> list[str]:
    """The measures of a set of records, as the cells of a table row."""
    s = summarize(records)
    n = s["n"]
    stable = f"{s['stable']}/{s['repeated']}" if s["repeated"] else "-"
    return [str(s["cases"]), str(n), f"{s['exact']}/{n}", f"{s['within_one']}/{n}", str(s["under"]), str(s["over"]),
            str(s["no_answer"]), _number(s["kappa"], 2), stable, f"{s['role_ok']}/{n}", f"{s['sheet']}/{n}",
            str(s["invalid_answers"]), _number(s["turns"], 1), _number(s["seconds"]), _number(s["wait"]),
            _number(s["requests"], 1), _number(s["tokens"])]


def step_title(step: int) -> str:
    """The title of one step's table."""
    return f"Step {step} - {steps.STEPS[step][0]}: {STEP_CONTENT[step]}"


def step_groups(results: dict[str, list[dict]], step: int) -> list[tuple[str, str, list[dict]]]:
    """What one step's table shows: for each model that completed the step, (model, condition, its records)."""
    condition = steps.STEPS[step][1]
    return [(model, condition, [r for r in records if r["condition"] == condition])
            for model, records in results.items() if steps.step_reached(records) >= step]


def step_rows(results: dict[str, list[dict]], step: int) -> list[list[str]]:
    """The rows of one step's table: one row for each model that completed the step."""
    return [[model, CONDITION_NAMES[condition]] + _measures(records)
            for model, condition, records in step_groups(results, step)]


def build_step_table(results: dict[str, list[dict]], step: int) -> str:
    """The table of one step, or a note when no model has completed it."""
    rows = step_rows(results, step)
    return _markdown(HEADER, rows) if rows else "*No model has completed this step yet.*"


def comparison_rows(results: dict[str, list[dict]]) -> list[list[str]]:
    """The steps each model completed, one under the other: the same rows as the step tables, model by model."""
    return [[model, CONDITION_NAMES[steps.STEPS[step][1]]]
            + _measures([r for r in records if r["condition"] == steps.STEPS[step][1]])
            for model, records in results.items() for step in range(1, steps.step_reached(records) + 1)]


def build_comparison(results: dict[str, list[dict]]) -> str:
    """The table with the conditions side by side, or a note when no model has completed a step."""
    rows = comparison_rows(results)
    return _markdown(HEADER, rows) if rows else "*No model has completed a step yet.*"


def build_status(results: dict[str, list[dict]]) -> str:
    """For each model: the step it has completed and how many cases each condition has."""
    rows = []
    for model, records in results.items():
        done = steps.done_items(records)
        counts = [f"{sum(1 for _, c in done if c == condition)}/{len(CASES)}" for condition in CONDITION_NAMES]
        rows.append([model, steps.step_label(steps.step_reached(records))] + counts)
    return _markdown(["Model", "Step reached"] + list(CONDITION_NAMES.values()), rows)


def _code_cell(expected: str, records: list[dict]) -> str:
    """The codes a model gave to one case, one per run, each marked when it is not the expected one."""
    if not records:
        return NOT_RUN
    cells = []
    for record in sorted(records, key=lambda r: r["run"]):
        error = code_error(expected, record.get("code"))
        mark = "" if not error else f" {UNDER_MARK if error > 0 else OVER_MARK}"
        cells.append(NO_ANSWER if error is None else record["code"] + mark)
    return " / ".join(cells)


def build_case_table(results: dict[str, list[dict]], condition: str) -> str:
    """One row per case and one column per model, with the code given in one condition."""
    rows = []
    for case in CASES:
        row = [case.id, case.expected_code]
        for records in results.values():
            row.append(_code_cell(case.expected_code,
                                  [r for r in records if r["case"] == case.id and r["condition"] == condition]))
        rows.append(row)
    return _markdown(["Case", "Expected"] + list(results), rows)


def build_document(results: dict[str, list[dict]]) -> str:
    """The whole results document."""
    legend = (f"`{OVER_MARK}` more urgent than expected (over-triage), `{UNDER_MARK}` less urgent than expected "
              f"(under-triage), `{NOT_RUN}` not run yet; several codes in a cell are the runs of that case, in order.")
    parts = ["# Benchmark results", "",
             "Built by `python -m benchmark.table` from the raw results in `raw/`. The steps and the measures are "
             "defined in `benchmark/PROTOCOL.md`, the cases in `benchmark/CASES.md`. The same numbers are in "
             "`table.csv` and, case by case, in `cases.csv`.", "",
             "## Progress", "", build_status(results)]
    for step in steps.STEPS:
        parts += ["", f"## {step_title(step)}", "", build_step_table(results, step)]
    parts += ["", "## The conditions side by side, model by model", "", build_comparison(results)]
    for number, (condition, name) in enumerate(CONDITION_NAMES.items()):
        parts += ["", f"## Case by case: {name.lower()}", ""] + ([legend, ""] if number == 0 else [])
        parts += [build_case_table(results, condition)]
    return "\n".join(parts + [""])


def table_csv_rows(results: dict[str, list[dict]]) -> list[list]:
    """The rows of table.csv: the step tables one after the other, as plain numbers (a cell like 3/15 would be read as a date)."""
    rows = [["Step", "Model", "Condition", "Cases", "Records", "Exact", "Within one", "Under", "Over", "No answer",
             "Kappa", "Stable", "Repeated", "Specialty", "Sheet seen", "Invalid answers", "Turns", "Seconds", "Wait",
             "Calls", "Tokens"]]
    for step in steps.STEPS:
        for model, condition, records in step_groups(results, step):
            s = summarize(records)
            means = [None if s[key] is None else round(s[key], 2)
                     for key in ("kappa", "turns", "seconds", "wait", "requests", "tokens")]
            rows.append([step, model, CONDITION_NAMES[condition], s["cases"], s["n"], s["exact"], s["within_one"],
                         s["under"], s["over"], s["no_answer"], means[0], s["stable"], s["repeated"], s["role_ok"],
                         s["sheet"], s["invalid_answers"]] + means[1:])
    return rows


def cases_csv_rows(results: dict[str, list[dict]]) -> list[list]:
    """The rows of cases.csv: every case run, with what was expected, what was given and what it cost."""
    rows = [["Model", "Case", "Condition", "Run", "Expected code", "Given code", ERROR_COLUMN, "Expected role",
             "Roles", "Role ok", "Sheet delivered", "Invalid answers", "Turns", "Seconds", "Wait seconds", "Calls",
             "Tokens", "Date", "Commit"]]
    order = list(CONDITION_NAMES)
    for model, records in results.items():
        for r in sorted(records, key=lambda r: (order.index(r["condition"]), r["case"], r["run"])):
            roles = r.get("roles") or []
            rows.append([model, r["case"], CONDITION_NAMES[r["condition"]], r["run"],
                         r["expected_code"], r.get("code") or "", code_error(r["expected_code"], r.get("code")),
                         r["expected_role"], ";".join(roles), "yes" if r["expected_role"] in roles else "no",
                         "yes" if r.get("sheet_delivered") else "no", r.get("invalid_answers"), r.get("turns"),
                         r.get("seconds"), r.get("wait_seconds"), r.get("requests"), r.get("total_tokens"),
                         r.get("date"), r.get("commit")])
    return rows


def _write_csv(path: Path, rows: list[list]) -> None:
    """Writes rows as a CSV file a spreadsheet opens directly (UTF-8 with signature)."""
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([["" if cell is None else cell for cell in row] for row in rows])


def main() -> int:
    """Writes the results document and the two CSV files, and prints the document."""
    results = load()
    if not results:
        print("No results yet: run python -m benchmark.run --model <NAME> --step 1 first.")
        return 1
    text = build_document(results)
    TABLE_FILE.write_text(text, encoding="utf-8")
    _write_csv(TABLE_CSV, table_csv_rows(results))
    _write_csv(CASES_CSV, cases_csv_rows(results))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    print(f"Written: {TABLE_FILE.name}, {TABLE_CSV.name}, {CASES_CSV.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
