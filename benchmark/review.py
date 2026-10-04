"""Writes the sheet for counting by hand the invented details of one model: patient and report of each core case.

Usage, from the project folder:
    python -m benchmark.review --model GPT_OSS_120B
    --force   write the sheet again, losing the counts already written in it

No model is called.
"""

import argparse
from pathlib import Path
import sys

from .cases import CASES
from .cases_doc import patient_lines
from .table import RESULTS_DIR, load

RULES = """Count, for each case, the statements of the report about **this patient** that are not in the patient card and are not in the "Da verificare" list.

**Counts as invented:** a sign, symptom, duration, therapy, exam result or past event stated as a fact that the card does not contain; the absence of something the card does not mention ("assenza di febbre" when no temperature is in the card).

**Does not count:** what is listed under "Da verificare"; the exams and the actions recommended; general medical knowledge that is not about this patient; a hypothesis presented as such ("possibile", "da escludere").

Write the number and the statements found under each case. The sheet is not written again once it exists, so the counts are not lost."""


def review_path(model_name: str) -> Path:
    """The sheet of a model."""
    return RESULTS_DIR / f"REVIEW_{model_name}.md"


def build_review(model_name: str, records: list[dict]) -> str:
    """The sheet: for each core case, the patient as the model received it and the report of the first run."""
    parts = [f"# Invented details: {model_name}", "", RULES]
    for case in (c for c in CASES if c.core):
        runs = sorted((r for r in records if r["case"] == case.id and r["condition"] == "system"),
                      key=lambda r: r["run"])
        parts += ["", f"## Case {case.id}: {case.title}", ""] + patient_lines(case) + [""]
        if not runs:
            parts += ["*Not run yet.*"]
            continue
        report = runs[0].get("report")
        parts += [f"**Report** (run {runs[0]['run']}, code {runs[0].get('code') or 'none'}):", ""]
        parts += [f"> {line}" if line else ">" for line in report.splitlines()] if report else ["*No report produced.*"]
        parts += ["", "**Invented details (number):**", "", "**Which:**"]
    return "\n".join(parts) + "\n"


def main() -> int:
    """Writes the sheet of one model, unless it already exists."""
    parser = argparse.ArgumentParser(description="Sheet for counting the invented details of one model.")
    parser.add_argument("--model", required=True, help="the name used with benchmark.run")
    parser.add_argument("--force", action="store_true", help="write the sheet again, losing the counts in it")
    args = parser.parse_args()

    records = load().get(args.model)
    if records is None:
        print(f"No results for {args.model}: run python -m benchmark.run --model {args.model} first.")
        return 1
    path = review_path(args.model)
    if path.exists() and not args.force:
        print(f"{path.name} already exists and may hold your counts: it is left as it is (use --force to rewrite it).")
        return 1
    path.write_text(build_review(args.model, records), encoding="utf-8")
    print(f"Written {path.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
