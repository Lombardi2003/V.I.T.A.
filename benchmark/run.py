"""Runs one model on the benchmark cases, one step at a time, and appends the raw results. Uses API quota.

Usage, from the project folder:
    python -m benchmark.run --model GPT_OSS_120B --check     one tiny request: is the key valid, does the model exist, are tokens counted
    python -m benchmark.run --model GPT_OSS_120B --step 1    minimum: the model alone, on the 15 cases
    python -m benchmark.run --model GPT_OSS_120B --step 2    intermediate: the full system, on the 5 core cases
    python -m benchmark.run --model GPT_OSS_120B --step 3    complete: the full system, on the other 10 cases
    python -m benchmark.run --model GPT_OSS_120B             the three steps, one after the other
    --key-field FIELD   read the API key from another settings.py field
    --no-usage          do not ask the provider for token counts (for a provider that rejects the option)
    --cases / --condition / --runs   run chosen cases outside the steps (trials, repetitions)

Every model goes through the same steps in the same order: a step starts only when the one before is complete.
A case already in the results file is skipped: after a daily limit, run the same command again.
"""

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
import warnings

os.environ.setdefault("HF_HUB_OFFLINE", "1")
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import chainlit as cl  # noqa: E402
from chainlit.context import init_http_context  # noqa: E402
from langchain_core.callbacks import BaseCallbackHandler  # noqa: E402

import src.agents.common as common  # noqa: E402
from src.graph import generate_graph, thread_config  # noqa: E402
from src.llm import describe_llm, factory  # noqa: E402
from src.llm.providers import Model, Models  # noqa: E402
from src.state import MedicalState  # noqa: E402

from . import steps  # noqa: E402
from .baseline import run_baseline  # noqa: E402
from .cases import CASES, CASES_BY_ID, Case  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"  # One .jsonl file per model, one line per case and run.
CONDITIONS = ("system", "baseline")  # The whole table, and the model alone.
# Texts the app shows when a node fell back because the model gave no usable answer.
ROUTING_FAILED_TEXT = "Smistamento automatico non disponibile"
PRIMARY_FALLBACK_TEXTS = ("Sintesi del primario non disponibile", "Ne' il tavolo degli specialisti ne' il primario")
REPORT_TEXT = "Report di sintesi"
CHECK_PROMPT = 'Rispondi solo con questo JSON, senza altro testo: {"ok": true}'  # The request sent by --check.
_SECRETS = re.compile(r"(org_|gsk_|sk-|xai-|AIza)[A-Za-z0-9_-]+")  # Account ids and keys, never printed.


class Meter(BaseCallbackHandler):
    """What one case costs: model calls, characters, tokens when the provider reports them, calls that failed for good."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Back to zero, before a case."""
        self.requests = self.prompt_chars = self.answer_chars = 0
        self.input_tokens = self.output_tokens = 0
        self.usage_seen = False
        self.escaped = []  # Errors that survived the retries: quota, connection, rejected request.

    def on_llm_end(self, response, **kwargs):
        """Adds the token counts of one answer, if the provider sent them."""
        for generations in response.generations:
            for generation in generations:
                usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if usage:
                    self.usage_seen = True
                    self.input_tokens += usage.get("input_tokens", 0)
                    self.output_tokens += usage.get("output_tokens", 0)


meter = Meter()
_stream_text = common.stream_text  # The app's own call, wrapped below.


def metered_stream_text(prompt, llm):
    """The app's model call, counted; an error that survives the retries is remembered and raised again."""
    meter.requests += 1
    meter.prompt_chars += len(prompt)
    try:
        answer = _stream_text(prompt, llm)
    except Exception as e:
        meter.escaped.append(f"{type(e).__name__}: {e}"[:300])
        raise
    meter.answer_chars += len(answer)
    return answer


class RecordedMessage:
    """Replaces cl.Message and keeps every chat message of the case."""
    sent = []

    def __init__(self, content="", author=None, **kwargs):
        self.content, self.author = content, author

    async def send(self):
        """Records the message instead of showing it."""
        RecordedMessage.sent.append((self.author, self.content))
        return self


def _plain(value):
    """A state value as plain data."""
    return value.model_dump() if hasattr(value, "model_dump") else value


async def run_system(case: Case) -> dict:
    """The real graph from the supervisor to the report, on a card already confirmed and without photo."""
    init_http_context()
    RecordedMessage.sent.clear()
    app = generate_graph()
    config = thread_config(str(uuid.uuid4()))
    app.update_state(config, MedicalState(patient_card=case.card, intake_card_shown=True, card_confirmed=True,
                                          allergies_addressed=True, previous_conditions_addressed=True,
                                          reviewer_card_shown=True, symptoms_confirmed=True,
                                          photo_request_shown=True).model_dump())
    app.update_state(config, {"next_step": "supervisor"}, as_node="photography")
    async for _ in app.astream_events(None, config=config, version="v2"):
        pass
    state = app.get_state(config).values

    texts = [text for _, text in RecordedMessage.sent]
    report = next((text for text in reversed(texts) if REPORT_TEXT in text), None)
    final = _plain(state.get("final_diagnosis")) or {}
    hypothesis = _plain(state.get("group_hypothesis"))
    second_opinion = state.get("second_opinion_role") or ""
    # The table as the supervisor seated it: the oldest saved state that has one.
    first_table = next((list(s.values["needed_specialists"]) for s in reversed(list(app.get_state_history(config)))
                        if s.values.get("needed_specialists")), [])
    routing_failed = any(ROUTING_FAILED_TEXT in text for text in texts)
    primary_fallback = any(t in (final.get("recommendations") or "") for t in PRIMARY_FALLBACK_TEXTS)
    failed_turns = sum((state.get("failed_turns") or {}).values())
    return {
        "code": final.get("urgency_level") if report else None,
        "roles": [role for role in first_table if role != second_opinion],
        "invalid_answers": failed_turns + routing_failed + primary_fallback,
        "turns": state.get("total_turns"),
        "seated": list(state.get("needed_specialists") or {}),
        "second_opinion": second_opinion,
        "routing_failed": routing_failed,
        "primary_fallback": primary_fallback,
        "failed_turns": failed_turns,
        "passed_without_confirming": list(state.get("passed_without_confirming") or []),
        "table_code": hypothesis and hypothesis.get("urgency_level"),
        "confirmed_by": hypothesis and hypothesis.get("confirmed_by"),
        "diagnosis": final.get("diagnosis"),
        "to_verify": final.get("to_verify"),
        "round_table": [_plain(entry) for entry in state.get("round_table") or []],
        "report": report,
    }


def _check_once() -> tuple[bool, str]:
    """One tiny request through the same path as the benchmark: (it worked, what happened)."""
    meter.reset()
    start = time.monotonic()
    try:
        answer = common.stream_response(CHECK_PROMPT)
    except Exception as e:
        return False, _SECRETS.sub(lambda m: m.group(1) + "REDACTED", f"{type(e).__name__}: {e}")[:400]
    try:
        common.extract_json(answer)
        readable = "yes"
    except json.JSONDecodeError:
        readable = f"no (the model wrote: {answer[:80]!r})"
    tokens = (f"yes ({meter.input_tokens} in, {meter.output_tokens} out)" if meter.usage_seen
              else "no: the table will show time and calls only")
    return True, f"answer in {time.monotonic() - start:.1f} s | readable JSON: {readable} | token counts: {tokens}"


def check_model() -> int:
    """Says whether the model can be reached and whether its tokens are counted, before a real run."""
    print(f"Checking {describe_llm(common.llm)}")
    ok, message = _check_once()
    if not ok and common.llm.stream_usage:
        # Some providers reject the option that asks for token counts: try once more without it.
        first_error = message
        common.llm.stream_usage = False
        ok, message = _check_once()
        if ok:
            print("  OK only without token counts: run this model with --no-usage.")
            print(f"  {message}")
            print(f"  (with token counts: {first_error})")
            return 0
    print(f"  {'OK' if ok else 'FAILED'}: {message}")
    if not ok:
        print("  Usual causes: wrong or missing key (401), wrong model name (404), no quota left (429), a setting the "
              "provider does not accept (400), a server that cannot be reached (connection error: a local model "
              "needs Ollama running).")
    return 0 if ok else 1


def _records(path: Path) -> list[dict]:
    """The records already in a results file."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _done(path: Path) -> set:
    """The (case, condition, run) already in a results file."""
    return {(r["case"], r["condition"], r["run"]) for r in _records(path)}


def step_plan(records: list[dict], step: int | None) -> tuple[list, str | None]:
    """What to run for one step, or for every step in order: (plan, why it cannot start)."""
    wanted = [step] if step else sorted(steps.STEPS)
    plan = []
    for number in wanted:
        before = [n for n in sorted(steps.STEPS) if n < number and steps.missing_items(records, n)]
        # Asked for alone, a step needs the ones before it; in a full run they are in the plan already.
        if step and before:
            return [], (f"Step {number} starts only when step {before[0]} is complete: "
                        f"run --step {before[0]} first ({len(steps.missing_items(records, before[0]))} cases missing).")
        plan += [(steps.FIRST_RUN, CASES_BY_ID[case_id], condition)
                 for case_id, condition in steps.missing_items(records, number)]
    return plan, None


def _commit() -> str:
    """The short hash of the current commit, to know which code produced a result."""
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parent)
    return result.stdout.strip()


async def run_all(args, model: Model, model_name: str, cases: list[Case] | None) -> int:
    """Runs what is still missing of a step (or of the chosen cases), saving each case as it ends; stops at the first error that is not the model's."""
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{model_name}.jsonl"
    done = _done(path)
    if cases is None:
        plan, problem = step_plan(_records(path), args.step)
        if problem:
            print(problem)
            return 1
    else:
        conditions = CONDITIONS if args.condition in (None, "both") else (args.condition,)
        plan = [(run, case, condition) for run in range(1, args.runs + 1) for case in cases
                for condition in conditions if (case.id, condition, run) not in done]
    calls = sum(steps.CALLS_PER_CASE[condition] for _, _, condition in plan)
    what = f"step {args.step}" if args.step else "all the steps" if cases is None else "chosen cases"
    print(f"Model: {describe_llm(common.llm)}   {what}   to run: {len(plan)} (about {calls} model calls)   "
          f"already done: {len(done)}   file: {path.name}")
    if not plan:
        print("Nothing to run: already complete.")
        return 0
    commit = _commit()
    for run, case, condition in plan:
        meter.reset()
        start = time.monotonic()
        try:
            outcome = await (run_system(case) if condition == "system" else run_baseline(case))
        except Exception:
            # The model alone has no node that absorbs a failed call: it arrives here and is handled just below.
            if not meter.escaped:
                raise
        seconds = time.monotonic() - start
        if meter.escaped:
            print(f"\nSTOPPED at case {case.id} ({condition}): a model call failed for a reason that is not the "
                  f"model's answer, so the case is not saved.\n  {meter.escaped[0]}\n"
                  "If it is a daily limit, run the same command again later: it restarts from this case.")
            return 2
        record = {
            "case": case.id, "condition": condition, "run": run,
            "expected_code": case.expected_code, "expected_role": case.expected_role, "core": case.core,
            "model": model.name, "provider": model.provider.name, "reasoning_effort": model.reasoning_effort,
            "temperature": common.settings.temperature, "date": datetime.now().isoformat(timespec="seconds"),
            "commit": commit, "seconds": round(seconds, 1), "requests": meter.requests,
            "prompt_chars": meter.prompt_chars, "answer_chars": meter.answer_chars,
            "input_tokens": meter.input_tokens if meter.usage_seen else None,
            "output_tokens": meter.output_tokens if meter.usage_seen else None,
            "total_tokens": meter.input_tokens + meter.output_tokens if meter.usage_seen else None,
            **outcome,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"  {case.id} {condition:8s} run {run}  expected {case.expected_code:9s} got {str(record['code']):9s} "
              f"roles {record['roles']}  {seconds:.0f} s  {meter.requests} calls"
              + (f"  {record['total_tokens']} tokens" if meter.usage_seen else ""))
    reached = steps.step_reached(_records(path))
    print(f"Done. This model has completed step: {steps.step_label(reached)}. Tables: python -m benchmark.table")
    return 0


def main() -> int:
    """Chooses the model and the cases from the command line and runs them."""
    names = [name for name, value in vars(Models).items() if isinstance(value, Model)]
    parser = argparse.ArgumentParser(description="V.I.T.A. model benchmark (uses API quota).")
    parser.add_argument("--model", required=True, choices=names, help="a model of src/llm/providers.py")
    parser.add_argument("--step", type=int, choices=sorted(steps.STEPS),
                        help="1 minimum (model alone, 15 cases), 2 intermediate (system, 5 core cases), "
                             "3 complete (system, the other 10); without it, the three in order")
    parser.add_argument("--cases", nargs="+", help="outside the steps: all, core, or case ids (01 ... 15)")
    parser.add_argument("--condition", choices=CONDITIONS + ("both",), help="outside the steps: which condition")
    parser.add_argument("--runs", type=int, default=1, help="outside the steps: runs per case")
    parser.add_argument("--key-field", metavar="FIELD", help="settings.py field of the API key to use")
    parser.add_argument("--no-usage", action="store_true", help="do not ask the provider for token counts")
    parser.add_argument("--check", action="store_true", help="one tiny request instead of the cases")
    args = parser.parse_args()

    manual = args.cases is not None or args.condition is not None or args.runs != 1
    if manual and args.step:
        parser.error("--step cannot be combined with --cases, --condition or --runs")
    if not manual:
        cases = None  # The steps decide what runs.
    elif args.cases in (None, ["all"]):
        cases = CASES
    elif args.cases == ["core"]:
        cases = [case for case in CASES if case.core]
    else:
        unknown = [c for c in args.cases if c not in CASES_BY_ID]
        if unknown:
            parser.error(f"unknown case(s): {', '.join(unknown)}")
        cases = [CASES_BY_ID[c] for c in args.cases]

    model = getattr(Models, args.model)
    if args.key_field:
        model = replace(model, provider=replace(model.provider, key_field=args.key_field))
    try:
        llm = factory.build_llm(model)
    except RuntimeError as e:
        print(f"{e}\nFor a model the app does not use: python scripts/setup_env.py --key {model.provider.key_field}")
        return 1
    llm.callbacks = [meter]
    llm.stream_usage = not args.no_usage
    common.llm = llm
    common.stream_text = metered_stream_text
    cl.Message = RecordedMessage
    if args.check:
        return check_model()
    return asyncio.run(run_all(args, model, args.model, cases))


if __name__ == "__main__":
    sys.exit(main())
