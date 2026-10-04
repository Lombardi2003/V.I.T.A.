"""Shared tools for the unit tests: fake model, fake chat, temporary database,
and a "conversation" that drives the real graph the way app.py does."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

# Before importing the project: embedding model from the local cache only, and
# UTF-8 output (at startup the project prints emoji, which on Windows cannot be
# written when the output is redirected to a file).
os.environ.setdefault("HF_HUB_OFFLINE", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chainlit as cl  # noqa: E402
from chainlit.context import init_http_context  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

import src.agents.common as common  # noqa: E402
import src.agents.photography as photography  # noqa: E402
import src.agents.specialist as specialist  # noqa: E402
import src.agents.persistence as persistence  # noqa: E402
import src.graph as graph  # noqa: E402
from src.database import MedicalDatabase, PatientRecord  # noqa: E402
from src.state import MedicalState, PatientCard, PhotoAnalysis  # noqa: E402


def run(coro_fn, *args, **kwargs):
    """HELPER run: runs an async function inside an active Chainlit context."""
    async def _main():
        init_http_context()
        return await coro_fn(*args, **kwargs)
    return asyncio.run(_main())


def as_dict(value):
    """HELPER as_dict: a graph state value as a dict (it is sometimes a Pydantic model)."""
    if value is None or isinstance(value, dict):
        return value
    return value.model_dump()


class FakeLLM:
    """HELPER FakeLLM: text model that returns the queued answers in order (dict, text, exception or function)."""

    def __init__(self):
        self.answers = []
        self.prompts = []

    def __call__(self, prompt, llm=None):
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError("The test did not provide an answer for this model call:\n" + prompt[:300])
        answer = self.answers.pop(0)
        if callable(answer) and not isinstance(answer, Exception):
            answer = answer(prompt)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer)


class FakeVision:
    """HELPER FakeVision: vision model (llm_vision.invoke) that returns the queued answers and records the messages."""

    def __init__(self):
        self.answers = []
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return type("Response", (), {"content": answer if isinstance(answer, str) else json.dumps(answer)})()


class VitaTestCase(unittest.TestCase):
    """HELPER VitaTestCase: fake chat, fake text and vision models, no RAG and a temporary database."""

    def setUp(self):
        self.chat = []
        chat = self.chat

        class FakeMessage:
            def __init__(self, content="", author=None, **kwargs):
                self.content, self.author = content, author

            async def send(self):
                chat.append((self.author, self.content))
                return self

        self.llm = FakeLLM()
        self.vision = FakeVision()
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = MedicalDatabase(str(Path(self._tmp.name) / "test.db"))
        patches = [
            mock.patch.object(cl, "Message", FakeMessage),
            # Every agent calls the text model through common.stream_response, which calls
            # common.stream_text: replacing that one name covers all of them.
            mock.patch.object(common, "stream_text", self.llm),
            mock.patch.object(photography, "llm_vision", self.vision),
            mock.patch.object(specialist, "retrieve", lambda queries, role=None, k=3: []),
            mock.patch.object(persistence, "mdb", self.db),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)

    def messages_from(self, author):
        """HELPER messages_from: chat messages written by one author."""
        return [content for a, content in self.chat if a == author]

    def last_message(self):
        """HELPER last_message: the last chat message ("" if none)."""
        return self.chat[-1][1] if self.chat else ""

    def add_patient(self, **fields):
        """HELPER add_patient: stores a patient in the temporary database."""
        from sqlmodel import Session
        with Session(self.db.engine) as session:
            session.add(PatientRecord(**fields))
            session.commit()


class Conversation:
    """HELPER Conversation: a chat on the real graph; each send() adds the message and resumes the graph."""

    def __init__(self, test: VitaTestCase, app=None):
        self.test = test
        self.app = app or graph.generate_graph()
        self.config = graph.thread_config(str(uuid.uuid4()))
        self.app.update_state(self.config, MedicalState().model_dump())

    def send(self, text, answers=(), photo=None, vision=()):
        """HELPER send: one operator message, with the fake model answers (and optional photo) for this turn."""
        self.test.llm.answers[:] = list(answers)
        self.test.vision.answers[:] = list(vision)
        self.test.chat.clear()
        update = {"general_history": [HumanMessage(content=text)], "triage_history": [HumanMessage(content=text)]}
        if photo:
            card = PatientCard(**as_dict(self.values.get("patient_card")) or {})
            card.symptom.photo = PhotoAnalysis(photo_url=str(photo), description="", injury_type="")
            update["patient_card"] = card.model_dump()
        self.app.update_state(self.config, update)

        async def _go():
            async for _ in self.app.astream_events(None, config=self.config, version="v2"):
                pass
        run(_go)
        return self

    @property
    def values(self):
        return self.app.get_state(self.config).values

    @property
    def card(self):
        return as_dict(self.values.get("patient_card")) or {}

    @property
    def symptoms(self):
        return [(s["description"], s["intensity"], s["duration"]) for s in self.card.get("symptom", {}).get("symptoms", [])]

    @property
    def next_step(self):
        return self.values.get("next_step")

    @property
    def paused_before(self):
        return self.app.get_state(self.config).next


# --- ready-made fake answers for personal data and symptoms ---
# The JSON keys ("conferma", "updated_card", ...) are the real ones of the
# Italian prompts, so they stay as they are.

def intake_answer(confirm=False, remove_allergies=(), remove_conditions=(), **card):
    """HELPER intake_answer: fake intake model answer with the given card fields."""
    base = {"first_name": "", "last_name": "", "age": "", "sex": "", "allergies": [], "previous_conditions": []}
    return {"updated_card": base | card, "allergies_to_remove": list(remove_allergies),
            "previous_conditions_to_remove": list(remove_conditions),
            "allergies_addressed": True, "previous_conditions_addressed": True,
            "conferma": confirm, "message_to_user": "Ho capito."}


def symptoms_answer(*symptoms, confirm=False, remove=()):
    """HELPER symptoms_answer: fake reviewer answer; each symptom is (description, intensity, duration[, trigger[, characteristics]])."""
    keys = ("description", "intensity", "duration", "trigger", "characteristics")
    return {"updated_card": {"symptom": {"symptoms": [dict(zip(keys, s)) for s in symptoms]}},
            "symptoms_to_remove": list(remove), "conferma": confirm, "message_to_user": "Ho capito."}


def go_to_symptoms(conv: Conversation):
    """HELPER go_to_symptoms: test fiscal code, complete personal data and confirmation."""
    conv.send("1234")
    conv.send("Marco Esposito 41 anni uomo nessuna allergia nessuna patologia",
              [intake_answer(first_name="Marco", last_name="Esposito", age="41", sex="uomo")])
    conv.send("confermo", [intake_answer(confirm=True)])
    return conv


def go_to_photo(conv: Conversation):
    """HELPER go_to_photo: go_to_symptoms plus one complete symptom and its confirmation."""
    go_to_symptoms(conv)
    conv.send("tosse forte da 2 giorni", [symptoms_answer(("tosse", "forte", "2 giorni"))])
    conv.send("confermo", [symptoms_answer(confirm=True)])
    return conv
