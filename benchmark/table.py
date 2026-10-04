"""Builds the benchmark table from the raw results: one row per model and condition. No model is called.

Usage, from the project folder:
    python -m benchmark.table
"""

import json
from pathlib import Path
import sys

from .metrics import summarize

RESULTS_DIR = Path(__file__).resolve().parent / "results"  # Where run.py writes one .jsonl file per model.
TABLE_FILE = RESULTS_DIR / "TABLE.md"  # Rewritten whole at every call.
CONDITION_NAMES = {"system": "Full system", "baseline": "Model alone"}  # As shown in the table.
HEADER = ["Model", "Condition", "Cases", "Records", "Exact", "Within one", "Under", "Over", "No answer", "Kappa",
          "Specialty", "Invalid answers", "Turns", "Seconds", "Calls", "Tokens"]


def load(results_dir: Path = RESULTS_DIR) -> dict[str, list[dict]]:
    """The records of every model, by results file name."""
    return {path.stem: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            for path in sorted(results_dir.glob("*.jsonl"))}


def _number(value, digits=0) -> str:
    """A mean as text, or a dash when it is not available."""
    return "-" if value is None else f"{value:.{digits}f}"


def _row(model: str, condition: str, records: list[dict]) -> list[str]:
    """One table row."""
    s = summarize(records)
    n = s["n"]
    return [model, CONDITION_NAMES[condition], str(s["cases"]), str(n), f"{s['exact']}/{n}", f"{s['within_one']}/{n}",
            str(s["under"]), str(s["over"]), str(s["no_answer"]), _number(s["kappa"], 2), f"{s['role_ok']}/{n}",
            str(s["invalid_answers"]), _number(s["turns"], 1), _number(s["seconds"]), _number(s["requests"], 1),
            _number(s["tokens"])]


def build_table(results: dict[str, list[dict]], core_only: bool = False) -> str:
    """The Markdown table, on every case or only on the core ones."""
    rows = []
    for model, records in results.items():
        for condition in CONDITION_NAMES:
            chosen = [r for r in records if r["condition"] == condition and (r.get("core") or not core_only)]
            if chosen:
                rows.append(_row(model, condition, chosen))
    lines = ["| " + " | ".join(HEADER) + " |", "|" + "---|" * len(HEADER)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


def main() -> int:
    """Writes the table file and prints it."""
    results = load()
    if not results:
        print("No results yet: run python -m benchmark.run --model <NAME> first.")
        return 1
    text = ("# Benchmark results\n\nBuilt by `python -m benchmark.table` from the raw results in this folder. "
            "The measures are defined in `benchmark/PROTOCOL.md`.\n\n"
            "## Core cases (five, one per code)\n\n" + build_table(results, core_only=True)
            + "\n\n## All the cases run\n\n" + build_table(results) + "\n")
    TABLE_FILE.write_text(text, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
