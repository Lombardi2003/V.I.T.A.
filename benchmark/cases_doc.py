"""Writes CASES.md, the readable version of the benchmark cases, from cases.py. No model is called.

Usage, from the project folder:
    python -m benchmark.cases_doc
"""

from pathlib import Path
import sys

from src.agents.roundtable import SPECIALIST_DISPLAY_NAMES

from .cases import CASES, MANUAL, Case

CASES_FILE = Path(__file__).resolve().parent / "CASES.md"  # Rewritten whole at every call.

INTRO = f"""<div align="center">

# 🩺 V.I.T.A. model benchmark: the cases

</div>

<div align="justify">

The 15 patients of the benchmark, as the models receive them, each with what is expected. This file is written by `python -m benchmark.cases_doc` from `cases.py`: it is not edited by hand. The rules used to write the cases and the measures are in `PROTOCOL.md`.

Every expected code comes from one row of the regional triage manual (`data/guidelines/{MANUAL}`); the page is the one printed on the manual. The patient texts are in Italian, the language of the app. The cases marked ★ are the core set, one per code: their reports are the ones read by hand (`python -m benchmark.review`).

</div>
"""


def _cell(text: str) -> str:
    """A table cell: a dash when empty."""
    return text or "-"


def patient_lines(case: Case) -> list[str]:
    """The patient as the models receive it: personal data, history and the table of symptoms."""
    card = case.card
    lines = [
        f"**Patient.** {card.sex}, {card.age} anni. Previous conditions: "
        f"{', '.join(card.previous_conditions) or 'none'}. Allergies: {', '.join(card.allergies) or 'none'}.",
        "",
        "| Symptom | Intensity | Duration | Characteristics | Trigger |",
        "|---|---|---|---|---|",
    ]
    return lines + [f"| {s.description} | {_cell(s.intensity)} | {_cell(s.duration)} | {_cell(s.characteristics)} | "
                    f"{_cell(s.trigger)} |" for s in card.symptom.symptoms]


def case_section(case: Case) -> str:
    """The section of one case: the patient, the symptoms, what is expected."""
    role = SPECIALIST_DISPLAY_NAMES[case.expected_role]
    lines = [f"## Case {case.id}{' ★' if case.core else ''}: {case.title}", ""] + patient_lines(case) + [
        "",
        "| Expected | |",
        "|---|---|",
        f"| Code | **{case.expected_code}** (code {case.manual_code} of the manual) |",
        f"| Specialty | **{role}**" + ("" if case.role_from_sheet else " (assigned by hand: the sheet names none)") + " |",
        f"| Manual sheet | {case.sheet} |",
        f"| Manual row | {case.row} |",
        f"| Manual page | {case.page} |",
    ]
    return "\n".join(lines)


def build_document() -> str:
    """The whole document."""
    return INTRO + "\n" + "\n\n".join(case_section(case) for case in CASES) + "\n"


def main() -> int:
    """Writes the file."""
    CASES_FILE.write_text(build_document(), encoding="utf-8")
    print(f"Written {CASES_FILE.name}: {len(CASES)} cases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
