"""Live script: the four reference cases, from the supervisor to the summary report. Uses API quota.

Usage: python -m tests.live.reference_cases [1 2 3 4] [--groq-key FIELD] [--gemini [FIELD]]
    --groq-key FIELD   the active Groq model with the key in another field of settings.py
    --gemini [FIELD]   the Gemini model instead, with the key in FIELD (default: the one in providers.py)
"""

import argparse
import asyncio
from dataclasses import replace
import logging
import os
import time
import uuid
import warnings

os.environ.setdefault("HF_HUB_OFFLINE", "1")
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

import chainlit as cl  # noqa: E402
from chainlit.context import init_http_context  # noqa: E402

import src.agents.common as common  # noqa: E402
from src.graph import generate_graph, thread_config  # noqa: E402
from src.llm import describe_llm, factory  # noqa: E402
from src.llm.providers import Models  # noqa: E402
from src.state import MedicalState, PatientCard, PhotoAnalysis, Symptom, SymptomProfile  # noqa: E402


def _symptom(description, intensity, duration, characteristics="", trigger=""):
    """HELPER _symptom: one confirmed symptom."""
    return Symptom(description=description, intensity=intensity, duration=duration,
                   characteristics=characteristics, trigger=trigger)


CASES = {
    "1": ("Knee: 14 years old, bike fall, abrasion, unbearable pain",
          PatientCard(fiscal_code="1234", first_name="Mario", last_name="Rossi", age="14", sex="uomo",
                      symptom=SymptomProfile(
                          symptoms=[_symptom("dolore al ginocchio", "insopportabile", "10 ore", "sbucciato",
                                             "dopo una caduta in bici")],
                          photo=PhotoAnalysis(photo_url="images.jpg", injury_type="abrasione cutanea",
                                              description="Lesione cutanea superficiale di forma irregolare, compatibile con "
                                                          "abrasione da sfregamento: eritema diffuso, perdita dell'epidermide, "
                                                          "piccole escoriazioni lineari e puntiformi con croste ematiche. Margini "
                                                          "sfumati, nessun corpo estraneo visibile.")))),
    "2": ("Chest: 63 years old with hypertension, oppressive pain radiating to the left arm + sweating",
          PatientCard(fiscal_code="1234", first_name="Franco", last_name="Russo", age="63", sex="uomo",
                      previous_conditions=["ipertensione"],
                      symptom=SymptomProfile(symptoms=[
                          _symptom("dolore al petto", "forte", "30 minuti", "oppressivo, irradiato al braccio sinistro"),
                          _symptom("sudorazione", "moderata", "20 minuti")]))),
    "3": ("Abdomen + rash: 34 years old",
          PatientCard(fiscal_code="1234", first_name="Anna", last_name="Verdi", age="34", sex="donna",
                      symptom=SymptomProfile(symptoms=[
                          _symptom("dolore addominale tipo crampi", "forte", "6 ore"),
                          _symptom("eruzione cutanea con macchie rosse pruriginose", "moderata", "3 ore")]))),
    "4": ("Palpitations + bruises: 65 years old, known atrial fibrillation",
          PatientCard(fiscal_code="1234", first_name="Giorgio", last_name="Bianchi", age="65", sex="uomo",
                      previous_conditions=["fibrillazione atriale nota"],
                      symptom=SymptomProfile(symptoms=[
                          _symptom("palpitazioni irregolari", "forte", "2 ore"),
                          _symptom("lividi estesi comparsi da soli sulle braccia e sulle gambe", "moderata",
                                   "una settimana", trigger="compaiono senza traumi o urti")]))),
}


def _client_with_key(model, key_field):
    """HELPER _client_with_key: a client for `model` that reads its API key from another settings.py field."""
    return factory.build_llm(replace(model, provider=replace(model.provider, key_field=key_field)))


class RecordedMessage:
    """HELPER RecordedMessage: replaces cl.Message and keeps every chat message, to print the report at the end."""
    sent = []

    def __init__(self, content="", author=None, **kwargs):
        self.content, self.author = content, author

    async def send(self):
        RecordedMessage.sent.append((self.author, self.content))
        return self


async def run_case(number):
    """LIVE reference case: runs one case from the supervisor to the report and prints the whole discussion."""
    init_http_context()
    title, card = CASES[number]
    RecordedMessage.sent.clear()
    app = generate_graph()
    config = thread_config(str(uuid.uuid4()))
    # Personal data and symptoms already confirmed: start from "photo done -> supervisor".
    app.update_state(config, MedicalState(patient_card=card, intake_card_shown=True, card_confirmed=True,
                                          allergies_addressed=True, previous_conditions_addressed=True,
                                          reviewer_card_shown=True, symptoms_confirmed=True,
                                          photo_request_shown=True).model_dump())
    app.update_state(config, {"next_step": "supervisor"}, as_node="photography")
    start = time.time()
    async for _ in app.astream_events(None, config=config, version="v2"):
        pass
    s = app.get_state(config).values

    print("\n" + "#" * 100)
    print(f"CASE {number}: {title}   [{describe_llm(common.llm)}]   time {time.time() - start:.0f} s")
    print("specialists:", list(s.get("needed_specialists", {})), "| second opinion:", s.get("second_opinion_role") or "-")
    for e in s.get("round_table", []):
        tag = (" [VERIFICATION]" if e.verification else "") + (f" urgency={e.urgency}" if e.urgency else "")
        print(f"\n  [{e.author} -> {e.to or 'everyone'}] {e.azione}{tag}\n    {e.content}")
    gh = s.get("group_hypothesis")
    gh = gh if isinstance(gh, dict) or gh is None else gh.model_dump()
    print("\nGROUP HYPOTHESIS:", gh and {k: gh[k] for k in ("diagnosis", "urgency_level", "recommended_exams", "confirmed_by")})
    print("passed without confirming:", s.get("passed_without_confirming"), "| failed turns:", s.get("failed_turns"),
          "| turns:", s.get("total_turns"))
    report = next((text for _, text in reversed(RecordedMessage.sent) if "Report di sintesi" in text), "(none)")
    print("\nREPORT SHOWN IN THE CHAT:\n" + report)


def main():
    """LIVE main: chooses the text model for this run and runs the requested cases one after the other."""
    parser = argparse.ArgumentParser(description="V.I.T.A. reference cases with the real model (uses API quota).")
    parser.add_argument("cases", nargs="*", default=list(CASES), choices=list(CASES))
    parser.add_argument("--groq-key", metavar="FIELD", help="settings.py field of the Groq key to use")
    parser.add_argument("--gemini", nargs="?", const=Models.GEMINI_FLASH.provider.key_field, metavar="FIELD",
                        help="use Gemini, with this settings.py key field")
    args = parser.parse_args()

    if args.gemini:
        common.llm = _client_with_key(Models.GEMINI_FLASH, args.gemini)
    elif args.groq_key:
        common.llm = _client_with_key(factory.TEXT_MODEL, args.groq_key)
    cl.Message = RecordedMessage
    print(f"Text model for this run: {describe_llm(common.llm)}")
    for number in args.cases:
        asyncio.run(run_case(number))


if __name__ == "__main__":
    main()
