"""Builds the benchmark tables from the raw results: progress, one table per step, one row per case. No model is called.

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

RESULTS_DIR = Path(__file__).resolve().parent / "results"  # Where run.py writes one .jsonl file per model.
TABLE_FILE = RESULTS_DIR / "TABLE.md"  # Rewritten whole at every call, like the two CSV files.
TABLE_CSV = RESULTS_DIR / "table.csv"  # One row per model, step and condition, with every measure.
CASES_CSV = RESULTS_DIR / "cases.csv"  # One row per case run: expected and given code, specialists, cost.
CONDITION_NAMES = {"system": "Full system", "baseline": "Model alone"}  # As shown in the tables.
MEASURES = ["Cases", "Records", "Exact", "Within one", "Under", "Over", "No answer", "Kappa", "Stable", "Specialty",
            "Invalid answers", "Turns", "Seconds", "Calls", "Tokens"]
HEADER = ["Model", "Condition"] + MEASURES
OVER_MARK, UNDER_MARK = "▲", "▼"  # Beside a code more urgent, or less urgent, than expected.
NO_ANSWER, NOT_RUN = "no answer", "-"  # A record without a code, and a case not run yet.
CORE_IDS = [case.id for case in CASES if case.core]
ALL_IDS = [case.id for case in CASES]
# Step -> (title, the cases compared, the conditions shown). A table lists only the models that completed the step.
STEP_TABLES = {
    1: ("Step 1 - minimum: the model alone, on the 15 cases", ALL_IDS, ["baseline"]),
    2: ("Step 2 - intermediate: full system and model alone, on the 5 core cases", CORE_IDS, ["system", "baseline"]),
    3: ("Step 3 - complete: full system and model alone, on the 15 cases", ALL_IDS, ["system", "baseline"]),
}


def load(results_dir: Path = RESULTS_DIR) -> dict[str, list[dict]]:
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
            str(s["no_answer"]), _number(s["kappa"], 2), stable, f"{s['role_ok']}/{n}", str(s["invalid_answers"]),
            _number(s["turns"], 1), _number(s["seconds"]), _number(s["requests"], 1), _number(s["tokens"])]


def step_groups(results: dict[str, list[dict]], step: int) -> list[tuple[str, str, list[dict]]]:
    """What one step's table compares: for each model that completed the step, (model, condition, its records)."""
    _, case_ids, conditions = STEP_TABLES[step]
    return [(model, condition, [r for r in records if r["condition"] == condition and r["case"] in case_ids])
            for model, records in results.items() if steps.step_reached(records) >= step
            for condition in conditions]


def step_rows(results: dict[str, list[dict]], step: int) -> list[list[str]]:
    """The rows of one step's table: for each model that completed the step, one row per condition."""
    return [[model, CONDITION_NAMES[condition]] + _measures(records)
            for model, condition, records in step_groups(results, step)]


def build_step_table(results: dict[str, list[dict]], step: int) -> str:
    """The table of one step, or a note when no model has completed it."""
    rows = step_rows(results, step)
    return _markdown(HEADER, rows) if rows else "*No model has completed this step yet.*"


def build_status(results: dict[str, list[dict]]) -> str:
    """For each model: the step it has completed, how many cases each condition has, and what the next step lacks."""
    rows = []
    for model, records in results.items():
        done = steps.done_items(records)
        reached = steps.step_reached(records)
        counts = [f"{sum(1 for _, c in done if c == condition)}/{len(CASES)}" for condition in ("baseline", "system")]
        following = reached + 1
        missing = steps.missing_items(records, following) if following in steps.STEPS else []
        rows.append([model, steps.step_label(reached)] + counts
                    + [f"step {following}: {' '.join(case_id for case_id, _ in missing)}" if missing else "none"])
    return _markdown(["Model", "Step reached", "Model alone", "Full system", "Still to run"], rows)


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
        row = [case.id + (" ★" if case.core else ""), case.expected_code]
        for records in results.values():
            row.append(_code_cell(case.expected_code,
                                  [r for r in records if r["case"] == case.id and r["condition"] == condition]))
        rows.append(row)
    return _markdown(["Case", "Expected"] + list(results), rows)


def build_document(results: dict[str, list[dict]]) -> str:
    """The whole results document."""
    legend = (f"`{OVER_MARK}` more urgent than expected (over-triage), `{UNDER_MARK}` less urgent than expected "
              f"(under-triage), `{NOT_RUN}` not run yet; several codes in a cell are the runs of that case, in order. "
              "★ marks the core cases.")
    parts = ["# Benchmark results", "",
             "Built by `python -m benchmark.table` from the raw results in this folder. The steps and the measures are "
             "defined in `benchmark/PROTOCOL.md`, the cases in `benchmark/CASES.md`. The same numbers are in "
             "`table.csv` and, case by case, in `cases.csv`.", "",
             "## Progress", "", build_status(results)]
    for step, (title, _, _) in STEP_TABLES.items():
        parts += ["", f"## {title}", "", build_step_table(results, step)]
    parts += ["", "## Case by case: model alone", "", legend, "", build_case_table(results, "baseline"),
              "", "## Case by case: full system", "", build_case_table(results, "system"), ""]
    return "\n".join(parts)


def table_csv_rows(results: dict[str, list[dict]]) -> list[list]:
    """The rows of table.csv: the three step tables one after the other, as plain numbers (a cell like 3/15 would be read as a date)."""
    rows = [["Step", "Model", "Condition", "Cases", "Records", "Exact", "Within one", "Under", "Over", "No answer",
             "Kappa", "Stable", "Repeated", "Specialty", "Invalid answers", "Turns", "Seconds", "Calls", "Tokens"]]
    for step in STEP_TABLES:
        for model, condition, records in step_groups(results, step):
            s = summarize(records)
            means = [None if s[key] is None else round(s[key], 2) for key in ("kappa", "turns", "seconds", "requests", "tokens")]
            rows.append([step, model, CONDITION_NAMES[condition], s["cases"], s["n"], s["exact"], s["within_one"],
                         s["under"], s["over"], s["no_answer"], means[0], s["stable"], s["repeated"], s["role_ok"],
                         s["invalid_answers"]] + means[1:])
    return rows


def cases_csv_rows(results: dict[str, list[dict]]) -> list[list]:
    """The rows of cases.csv: every case run, with what was expected, what was given and what it cost."""
    rows = [["Model", "Case", "Core", "Condition", "Run", "Expected code", "Code", "Error (levels)", "Expected role",
             "Roles", "Role ok", "Invalid answers", "Turns", "Seconds", "Calls", "Tokens", "Date", "Commit"]]
    for model, records in results.items():
        for r in sorted(records, key=lambda r: (r["condition"], r["case"], r["run"])):
            roles = r.get("roles") or []
            rows.append([model, r["case"], "yes" if r.get("core") else "no", r["condition"], r["run"],
                         r["expected_code"], r.get("code") or "", code_error(r["expected_code"], r.get("code")),
                         r["expected_role"], ";".join(roles), "yes" if r["expected_role"] in roles else "no",
                         r.get("invalid_answers"), r.get("turns"), r.get("seconds"), r.get("requests"),
                         r.get("total_tokens"), r.get("date"), r.get("commit")])
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
