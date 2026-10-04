"""Router of the round table: decides who speaks next and when the discussion ends. It calls no model."""

from src.state import MedicalState
from .roundtable import MAX_TOTAL_TURNS, MAX_RECRUITED_SPECIALISTS, MAX_SPEAKS_PER_SPECIALIST, MAX_FAILED_TURNS
from src.log import get_logger

log = get_logger("router")


def _turns_spoken(round_table, role: str) -> int:
    """How many turns a specialist has had, verification excluded."""
    turns = 0
    for i, entry in enumerate(round_table):
        if entry.author != role or entry.verification:
            continue
        # A consult right after the same author's action belongs to the same turn.
        same_turn_consult = (
            entry.azione == "consulta" and i > 0
            and round_table[i - 1].author == role and round_table[i - 1].azione != "consulta"
        )
        if not same_turn_consult:
            turns += 1
    return turns


def _can_speak(state: MedicalState, role: str) -> bool:
    """True if the specialist still has turns and has not used up the failed ones."""
    return (_turns_spoken(state.round_table, role) < MAX_SPEAKS_PER_SPECIALIST
            and state.failed_turns.get(role, 0) < MAX_FAILED_TURNS)


def router(state: MedicalState):
    """The next node: a specialist, or the primary when the table has agreed or a limit is reached."""
    # Emergency brake: go to the primary with the hypothesis as it is.
    if state.total_turns >= MAX_TOTAL_TURNS:
        log.info("turn cap (%s) reached -> primary", MAX_TOTAL_TURNS)
        return {"next_step": "chief_physician"}

    needed = dict(state.needed_specialists)
    gh = state.group_hypothesis
    confirmed = set(gh.confirmed_by) if gh else set()

    # Out of turns without confirming: moved on, and never counted among those who confirmed.
    passed = [role for role in needed if role not in confirmed and not _can_speak(state, role)]
    for role in passed:
        if role in state.passed_without_confirming:
            continue
        if state.failed_turns.get(role, 0) >= MAX_FAILED_TURNS:
            log.info("%s had %s failed turns: moved on without confirming", role, MAX_FAILED_TURNS)
        else:
            log.info("%s used its %s turns: moved on without confirming", role, MAX_SPEAKS_PER_SPECIALIST)

    update = {}
    if passed != state.passed_without_confirming:
        update["passed_without_confirming"] = passed

    pending = {role for role in needed if role not in confirmed and role not in passed}

    # Reaction turn: everyone confirmed, but the last entry explicitly names a seated colleague.
    reopen_role = None
    if not pending and state.round_table:
        last_entry = state.round_table[-1]
        last_to = last_entry.to
        if last_to and last_entry.to_explicit and last_to in needed and last_to != last_entry.author:
            if _can_speak(state, last_to):
                reopen_role = last_to
                log.info("%s was named after confirming: one reaction turn", last_to)

    # A consult to a colleague not yet seated keeps the table open.
    open_consult = False
    if state.round_table:
        last_entry = state.round_table[-1]
        open_consult = (
            last_entry.azione == "consulta"
            and bool(last_entry.to)
            and last_entry.to not in needed
            and state.recruited_specialists_count < MAX_RECRUITED_SPECIALISTS
        )

    if not needed or (not pending and not reopen_role and not open_consult):
        outcome = f"confirmed by all except those moved on ({', '.join(passed)})" if passed else "confirmed by all"
        # Final verification round, once: one turn each, skipping whoever used up the failed turns.
        queue = list(state.verification_queue)
        if needed and not state.verification_started:
            queue = list(needed.keys())
            update["verification_started"] = True
            log.info("hypothesis %s -> final verification round", outcome)
        queue = [r for r in queue if state.failed_turns.get(r, 0) < MAX_FAILED_TURNS]
        if needed and queue:
            next_role = queue.pop(0)
            total_turns = state.total_turns + 1
            log.info("verification turn: %s (%s/%s)", next_role, total_turns, MAX_TOTAL_TURNS)
            return {
                **update,
                "next_step": next_role,
                "verifying_role": next_role,
                "verification_queue": queue,
                "total_turns": total_turns,
            }
        log.info("hypothesis %s -> primary", outcome)
        return {**update, "next_step": "chief_physician", "verifying_role": ""}

    recruited_count = state.recruited_specialists_count
    next_role = reopen_role

    # 1. Whoever was addressed by the last entry speaks first, and may be recruited.
    if next_role is None and state.round_table:
        last_entry = state.round_table[-1]
        last_to = last_entry.to
        if last_to:
            if last_to in pending:
                next_role = last_to
            elif (last_to in needed and last_entry.to_explicit and last_to != last_entry.author
                  and _can_speak(state, last_to)):
                next_role = last_to
            elif last_to not in needed and recruited_count < MAX_RECRUITED_SPECIALISTS:
                needed[last_to] = True
                recruited_count += 1
                next_role = last_to
                log.info("%s brought in at a colleague's request", last_to)

    # 2. Otherwise the next specialist who has not confirmed, in order of arrival.
    order = list(needed.keys())
    n = len(order)
    if not next_role:
        idx = state.current_turn_index % n
        for _ in range(n):
            if order[idx] in pending:
                next_role = order[idx]
                break
            idx = (idx + 1) % n

    next_idx = (order.index(next_role) + 1) % n
    total_turns = state.total_turns + 1

    log.info("turn: %s (%s/%s)", next_role, total_turns, MAX_TOTAL_TURNS)
    return {
        **update,
        "next_step": next_role,
        "verifying_role": "",
        "current_turn_index": next_idx,
        "total_turns": total_turns,
        "needed_specialists": needed,
        "recruited_specialists_count": recruited_count,
    }
