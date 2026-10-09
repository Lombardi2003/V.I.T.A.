"""The four steps every model goes through, in the same order: each one adds something to the one before."""

from .cases import CASES

ALL_CASES = [case.id for case in CASES]  # Every step runs the 15 cases, in this order.
# Step -> (name, condition, the cases it runs). A model stops at the step its quota allows.
STEPS = {
    1: ("bare model", "bare", ALL_CASES),  # The patient, the names of the codes and of the specialists.
    2: ("model with guidelines", "rag", ALL_CASES),  # The same, with the retrieved guidelines.
    3: ("single agent", "single", ALL_CASES),  # The same, with the code definitions and the rules of a specialist.
    4: ("full system", "system", ALL_CASES),  # Supervisor, round table and primary.
}
CONDITIONS = tuple(condition for _, condition, _ in STEPS.values())  # In the order of the steps.
CALLS_PER_CASE = {"bare": 1, "rag": 1, "single": 1, "system": 7}  # Model calls of one case, to announce what a step will use (system: measured mean).
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
