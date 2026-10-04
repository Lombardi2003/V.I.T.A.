"""The benchmark measures, computed from the raw result records. No model and no project code is needed here."""

from collections import Counter

from .cases import LEVELS


def code_error(expected: str, given: str | None) -> int | None:
    """Levels between the given code and the expected one: positive is under-triage, negative over-triage, None no code."""
    if given not in LEVELS:
        return None
    return LEVELS.index(given) - LEVELS.index(expected)


def weighted_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Quadratic weighted Cohen's kappa between expected and given codes; None when it is not defined."""
    n = len(pairs)
    if not n:
        return None
    observed = sum((LEVELS.index(e) - LEVELS.index(g)) ** 2 for e, g in pairs) / n
    expected_counts = Counter(e for e, _ in pairs)
    given_counts = Counter(g for _, g in pairs)
    by_chance = sum(expected_counts[a] * given_counts[b] * (LEVELS.index(a) - LEVELS.index(b)) ** 2
                    for a in expected_counts for b in given_counts) / n ** 2
    return None if by_chance == 0 else 1 - observed / by_chance


def stability(records: list[dict]) -> tuple[int, int]:
    """Among the cases run more than once, how many gave the same code every time: (stable, repeated)."""
    codes_by_case = {}
    for r in records:
        codes_by_case.setdefault(r["case"], []).append(r.get("code"))
    repeated = [codes for codes in codes_by_case.values() if len(codes) > 1]
    return sum(len(set(codes)) == 1 for codes in repeated), len(repeated)


def _mean(values: list) -> float | None:
    """The mean of the values that are present, or None."""
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def summarize(records: list[dict]) -> dict:
    """The measures of one model in one condition, over its records (one per case and run)."""
    errors = [code_error(r["expected_code"], r.get("code")) for r in records]
    answered = [(r["expected_code"], r["code"]) for r, e in zip(records, errors) if e is not None]
    stable, repeated = stability(records)
    return {
        "n": len(records),
        "cases": len({r["case"] for r in records}),
        "exact": sum(e == 0 for e in errors),
        "within_one": sum(e is not None and abs(e) <= 1 for e in errors),
        "under": sum(e is not None and e > 0 for e in errors),  # Less urgent than expected: the dangerous error.
        "over": sum(e is not None and e < 0 for e in errors),
        "no_answer": sum(e is None for e in errors),  # Counted as wrong, in neither direction.
        "kappa": weighted_kappa(answered),
        "stable": stable,  # Cases whose runs all gave the same code...
        "repeated": repeated,  # ...out of the cases run more than once.
        "role_ok": sum(r["expected_role"] in (r.get("roles") or []) for r in records),
        "invalid_answers": sum(r.get("invalid_answers") or 0 for r in records),
        "turns": _mean([r.get("turns") for r in records]),
        "seconds": _mean([r.get("seconds") for r in records]),
        "requests": _mean([r.get("requests") for r in records]),
        "tokens": _mean([r.get("total_tokens") for r in records]),
    }
