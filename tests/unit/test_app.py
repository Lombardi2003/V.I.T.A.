"""app.py: operator error messages and the on_message handler (photo attachment, error then resume)."""
import tempfile
import types
import unittest
import uuid
from pathlib import Path

import httpx
import openai
from PIL import Image

try:
    from . import helpers
except ImportError:
    import helpers

from src.state import MedicalState

_req = httpx.Request("POST", "https://x")
QUOTA = openai.RateLimitError("Rate limit reached ... organization org_XXXX", response=httpx.Response(429, request=_req), body=None)


def _app_module():
    """HELPER _app_module: imports app.py once (on import it builds the graph and loads the guideline index)."""
    import app
    return app


class TestErrorMessages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.msg = staticmethod(_app_module()._operator_error_message)

    def test_quota_exhausted(self):
        """TEST app error message: quota exhausted gives a short message without account identifiers."""
        text = self.msg(QUOTA)
        self.assertIn("limite di utilizzo", text)
        self.assertNotIn("org_", text)

    def test_service_unreachable(self):
        """TEST app error message: a connection error says the service is unreachable."""
        self.assertIn("non è raggiungibile", self.msg(openai.APIConnectionError(request=_req)))

    def test_generic_error(self):
        """TEST app error message: any other error gives a generic message without internal details."""
        text = self.msg(RuntimeError("internal detail"))
        self.assertIn("Si è verificato un errore", text)
        self.assertNotIn("internal detail", text)


class TestOnMessage(helpers.VitaTestCase):
    def setUp(self):
        super().setUp()
        self.module = _app_module()
        self.graph = helpers.graph.generate_graph()
        self.thread = str(uuid.uuid4())
        self.config = helpers.graph.thread_config(self.thread)
        self.graph.update_state(self.config, MedicalState().model_dump())
        session = types.SimpleNamespace(get=lambda key, default=None: self.thread if key == "thread_id" else default)
        for target, name, value in ((self.module, "app", self.graph), (self.module.cl, "user_session", session)):
            p = helpers.mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def on_message(self, text, answers=(), elements=()):
        """HELPER on_message: calls app.main as Chainlit would, with fake model answers for this turn."""
        self.llm.answers[:] = list(answers)
        self.chat.clear()
        helpers.run(self.module.main, types.SimpleNamespace(content=text, elements=list(elements)))

    @property
    def card(self):
        return helpers.as_dict(self.graph.get_state(self.config).values["patient_card"])

    def test_error_mid_flow_then_resume(self):
        """TEST app.main: a model error shows the operator message, and sending the message again resumes the chat."""
        self.on_message("1234")
        self.on_message("Luca Bianchi 30 anni uomo", [QUOTA])
        self.assertIn("limite di utilizzo", self.last_message())
        self.on_message("Luca Bianchi 30 anni uomo", [helpers.intake_answer(first_name="Luca", last_name="Bianchi",
                                                                             age="30", sex="uomo")])
        self.assertIn("**Paziente** Luca Bianchi", self.last_message())
        self.assertEqual(self.card["fiscal_code"], "1234")

    def test_attached_image_changes_only_the_photo(self):
        """TEST app.main: an attached image is stored in the card without erasing personal data; other files are ignored."""
        self.on_message("1234")
        self.on_message("Luca Bianchi", [helpers.intake_answer(first_name="Luca", last_name="Bianchi")])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            photo = Path(d) / "photo.png"
            Image.new("RGB", (50, 50)).save(photo)
            pdf = types.SimpleNamespace(mime="application/pdf", path=str(Path(d) / "doc.pdf"))
            image = types.SimpleNamespace(mime="image/png", path=str(photo))
            self.on_message("30 anni", [helpers.intake_answer(age="30")], elements=[pdf, image])
        self.assertEqual(self.card["symptom"]["photo"]["photo_url"], str(photo))
        self.assertEqual((self.card["fiscal_code"], self.card["first_name"], self.card["age"]), ("1234", "Luca", "30"))


if __name__ == "__main__":
    unittest.main()
