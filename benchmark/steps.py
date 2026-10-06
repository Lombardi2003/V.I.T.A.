"""The three steps every model goes through, in the same order: each one adds to the one before."""

from .cases import CASES

# Step -> (name, condition, the cases it runs). A model stops at the step its quota allows.
STEPS = {
    1: ("minimum", "baseline", [case.id for case in CASES]),  # The model alone, on every case: one call each.
    2: ("intermediate", "system", [case.id for case in CASES if case.core]),  # The full system, on the core cases.
    3: ("complete", "system", [case.id for case in CASES if not case.core]),  # The full system, on the other cases.
}
CALLS_PER_CASE = {"baseline": 1, "system": 7}  # Model calls of one case, to announce what a step will use (system: measured mean).
FIRST_RUN = 1  # The steps are made of first runs; repetitions, if any, come after them.


def step_items(step: int) -> list[tuple[str, str]]:
    """The (case, condition) pairs a step is made of."""
    _, condition, case_ids = STEPS[step]
    return [(case_id, condition) for case_id in case_ids]


def done_items(records: list[dict]) -> set[tuple[str, str]]:
    """The (case, condition) pairs already in a model's results."""
    return {(r["case"], r["condition"]) for r in records if r.get("run", FIRST_RUN) == FIRST_RUN}


def missing_items(records: list[dict], step: int) -> list[tuple[str, str]]:
    """What a model still has to run to complete a step."""
    done = done_items(records)
    return [item for item in step_items(step) if item not in done]


def step_reached(records: list[dict]) -> int:
    """The last step a model has completed, with every step before it: 0 if not even the first."""
    reached = 0
    for step in sorted(STEPS):
        if missing_items(records, step):
            break
        reached = step
    return reached


def step_label(step: int) -> str:
    """A step as shown in the tables."""
    return f"{step} - {STEPS[step][0]}" if step else "0 - not started"
