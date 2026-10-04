"""Builds the benchmark tables from the raw results: progress, one row per model, one row per case. No model is called.

Usage, from the project folder:
    python -m benchmark.table
"""

import json
from pathlib import Path
import sys

from .cases import CASES
from .metrics import code_error, summarize

RESULTS_DIR = Path(__file__).resolve().parent / "results"  # Where run.py writes one .jsonl file per model.
TABLE_FILE = RESULTS_DIR / "TABLE.md"  # Rewritten whole at every call.
CONDITION_NAMES = {"system": "Full system", "baseline": "Model alone"}  # As shown in the tables.
HEADER = ["Model", "Condition", "Cases", "Records", "Exact", "Within one", "Under", "Over", "No answer", "Kappa",
          "Stable", "Specialty", "Invalid answers", "Turns", "Seconds", "Calls", "Tokens"]
OVER_MARK, UNDER_MARK = "▲", "▼"  # Beside a code more urgent, or less urgent, than expected.
NO_ANSWER, NOT_RUN = "no answer", "-"  # A record without a code, and a case not run yet.


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


def _row(model: str, condition: str, records: list[dict]) -> list[str]:
    """One row of the table of the models."""
    s = summarize(records)
    n = s["n"]
    stable = f"{s['stable']}/{s['repeated']}" if s["repeated"] else "-"
    return [model, CONDITION_NAMES[condition], str(s["cases"]), str(n), f"{s['exact']}/{n}", f"{s['within_one']}/{n}",
            str(s["under"]), str(s["over"]), str(s["no_answer"]), _number(s["kappa"], 2), stable, f"{s['role_ok']}/{n}",
            str(s["invalid_answers"]), _number(s["turns"], 1), _number(s["seconds"]), _number(s["requests"], 1),
            _number(s["tokens"])]


def build_table(results: dict[str, list[dict]], core_only: bool = False) -> str:
    """The table of the models, on every case or only on the core ones."""
    rows = []
    for model, records in results.items():
        for condition in CONDITION_NAMES:
            chosen = [r for r in records if r["condition"] == condition and (r.get("core") or not core_only)]
            if chosen:
                rows.append(_row(model, condition, chosen))
    return _markdown(HEADER, rows)


def build_status(results: dict[str, list[dict]]) -> str:
    """For each model and condition, how many cases are done and which are missing."""
    rows = []
    for model, records in results.items():
        for condition, name in CONDITION_NAMES.items():
            done = {r["case"] for r in records if r["condition"] == condition}
            missing = [case.id for case in CASES if case.id not in done]
            runs = max((r["run"] for r in records if r["condition"] == condition), default=0)
            rows.append([model, name, f"{len(done)}/{len(CASES)}", str(runs), " ".join(missing) or "none"])
    return _markdown(["Model", "Condition", "Cases done", "Runs", "Missing cases"], rows)


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
    return (
        "# Benchmark results\n\nBuilt by `python -m benchmark.table` from the raw results in this folder. "
        "The measures are defined in `benchmark/PROTOCOL.md`, the cases in `benchmark/CASES.md`.\n\n"
        "## Progress\n\n" + build_status(results)
        + "\n\n## Models: core cases (five, one per code)\n\n" + build_table(results, core_only=True)
        + "\n\n## Models: all the cases run\n\n" + build_table(results)
        + "\n\n## Case by case: full system\n\n" + legend + "\n\n" + build_case_table(results, "system")
        + "\n\n## Case by case: model alone\n\n" + build_case_table(results, "baseline") + "\n"
    )


def main() -> int:
    """Writes the results document and prints it."""
    results = load()
    if not results:
        print("No results yet: run python -m benchmark.run --model <NAME> first.")
        return 1
    text = build_document(results)
    TABLE_FILE.write_text(text, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
