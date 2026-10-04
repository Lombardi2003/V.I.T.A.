"""Runs the V.I.T.A. tests one after another, by category, and prints a summary.

Usage, from the project folder:
    python -m tests.run                  unit tests (same as "unit")
    python -m tests.run unit             unit tests: fake model, no API quota, pass/fail
    python -m tests.run unit test_intake only some unit test files
    python -m tests.run retrieval        retrieval benchmark: no model, no quota, numbers to compare
    python -m tests.run all              unit + retrieval (everything that uses no quota)
    python -m tests.run live             live scripts with the real model: they USE API QUOTA
    python -m tests.run live correction  only some live scripts

"live" never runs as part of "all": it has to be asked for explicitly.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
CATEGORIES = ("unit", "retrieval", "live")


def _modules(category: str) -> list[str]:
    """HELPER _modules: the runnable script names of a category (every .py except __init__ and common)."""
    return sorted(p.stem for p in (TESTS / category).glob("*.py") if p.stem not in ("__init__", "common"))


def _steps(category: str, names: list[str]) -> list[tuple[str, list[str]]]:
    """HELPER _steps: the (label, command) pairs to run for a category, optionally limited to some names."""
    python = [sys.executable]
    if category == "unit":
        if names:
            return [(f"unit/{n}", python + ["-m", "unittest", "-v", f"tests.unit.{n}"]) for n in names]
        return [("unit", python + ["-m", "unittest", "discover", "-v", "-s", "tests/unit", "-t", "."])]
    available = _modules(category)
    unknown = [n for n in names if n not in available]
    if unknown:
        raise SystemExit(f"Unknown {category} script(s): {', '.join(unknown)}. Available: {', '.join(available)}")
    return [(f"{category}/{n}", python + ["-m", f"tests.{category}.{n}"]) for n in (names or available)]


def main(argv: list[str]) -> int:
    """RUNNER main: runs the chosen category (or all = unit + retrieval) step by step and prints a summary."""
    category = argv[0] if argv else "unit"
    names = argv[1:]
    if category == "all":
        if names:
            raise SystemExit("\"all\" takes no script names.")
        plan = _steps("unit", []) + _steps("retrieval", [])
    elif category in CATEGORIES:
        plan = _steps(category, names)
    else:
        raise SystemExit(__doc__)

    if category == "live":
        print("⚠️  Live scripts call the real model and USE API QUOTA.\n")

    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    results = []
    for label, command in plan:
        print("\n" + "#" * 100 + f"\n# {label}\n" + "#" * 100, flush=True)
        start = time.monotonic()
        code = subprocess.call(command, cwd=ROOT, env=env)
        results.append((label, code, time.monotonic() - start))

    print("\n" + "=" * 100 + "\nSUMMARY\n" + "=" * 100)
    for label, code, seconds in results:
        print(f"{'OK    ' if code == 0 else 'FAILED'} {label:40s} {seconds:7.1f} s")
    if category in ("retrieval", "live"):
        print("\nOK only means the script ran to the end: its numbers or discussion still have to be read.")
    return 0 if all(code == 0 for _, code, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
