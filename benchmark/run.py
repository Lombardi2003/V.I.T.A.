"""Runs one model on the benchmark cases, in the two conditions, and appends the raw results. Uses API quota.

Usage, from the project folder:
    python -m benchmark.run --model GPT_OSS_120B                  every case, both conditions, one run
    python -m benchmark.run --model GPT_OSS_120B --cases core     only the five core cases
    python -m benchmark.run --model GPT_OSS_120B --cases 01 04    only some cases
    python -m benchmark.run --model GEMINI_FLASH --condition system --runs 3
    --key-field FIELD   read the API key from another settings.py field
    --no-usage          do not ask the provider for token counts (for a provider that rejects the option)

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

from .baseline import run_baseline  # noqa: E402
from .cases import CASES, CASES_BY_ID, Case  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"  # One .jsonl file per model, one line per case and run.
CONDITIONS = ("system", "baseline")  # The whole table, and the model alone.
# Texts the app shows when a node fell back because the model gave no usable answer.
ROUTING_FAILED_TEXT = "Smistamento automatico non disponibile"
PRIMARY_FALLBACK_TEXTS = ("Sintesi del primario non disponibile", "Ne' il tavolo degli specialisti ne' il primario")
REPORT_TEXT = "Report di sintesi"


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


def _done(path: Path) -> set:
    """The (case, condition, run) already in a results file."""
    if not path.exists():
        return set()
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(r["case"], r["condition"], r["run"]) for r in lines}


def _commit() -> str:
    """The short hash of the current commit, to know which code produced a result."""
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parent)
    return result.stdout.strip()


async def run_all(args, model: Model, model_name: str, cases: list[Case]) -> int:
    """Runs what is still missing, saving each case as soon as it ends; stops at the first error that is not the model's."""
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{model_name}.jsonl"
    done = _done(path)
    conditions = CONDITIONS if args.condition == "both" else (args.condition,)
    plan = [(run, case, condition) for run in range(1, args.runs + 1) for case in cases for condition in conditions
            if (case.id, condition, run) not in done]
    print(f"Model: {describe_llm(common.llm)}   to run: {len(plan)}   already done: {len(done)}   file: {path.name}")
    commit = _commit()
    for run, case, condition in plan:
        meter.reset()
        start = time.monotonic()
        outcome = await (run_system(case) if condition == "system" else run_baseline(case))
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
    print("Done. Table: python -m benchmark.table")
    return 0


def main() -> int:
    """Chooses the model and the cases from the command line and runs them."""
    names = [name for name, value in vars(Models).items() if isinstance(value, Model)]
    parser = argparse.ArgumentParser(description="V.I.T.A. model benchmark (uses API quota).")
    parser.add_argument("--model", required=True, choices=names, help="a model of src/llm/providers.py")
    parser.add_argument("--cases", nargs="+", default=["all"], help="all, core, or case ids (01 ... 15)")
    parser.add_argument("--condition", default="both", choices=CONDITIONS + ("both",))
    parser.add_argument("--runs", type=int, default=1, help="runs per case")
    parser.add_argument("--key-field", metavar="FIELD", help="settings.py field of the API key to use")
    parser.add_argument("--no-usage", action="store_true", help="do not ask the provider for token counts")
    args = parser.parse_args()

    if args.cases == ["all"]:
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
    llm = factory.build_llm(model)
    llm.callbacks = [meter]
    llm.stream_usage = not args.no_usage
    common.llm = llm
    common.stream_text = metered_stream_text
    cl.Message = RecordedMessage
    return asyncio.run(run_all(args, model, args.model, cases))


if __name__ == "__main__":
    sys.exit(main())
