"""Settings panel: which models can be chosen, changing a model, and the lock once the chat has started."""
import types
import unittest
from unittest import mock

import httpx

try:
    from . import helpers
except ImportError:
    import helpers

import src.agents.common as common
import src.agents.photography as photography
from src import model_choice
from src.llm.providers import Models


def _settings(**keys):
    """HELPER _settings: settings in which only these provider keys are set."""
    values = {"groq_api_key": None, "groq_api_key_2": None, "gemini_api_key": None, "gemini_fra_key": None,
              "huggingface_api_key": None, "cloudflare_api_key": None, "cloudflare_account_id": None}
    return lambda: types.SimpleNamespace(**{**values, **keys}, temperature=0.0)


class PanelCase(unittest.TestCase):
    """HELPER PanelCase: restores the models and clients in use after each test, and never builds a real client."""

    def setUp(self):
        saved = (dict(model_choice.current), common.llm, common.llm_vision, photography.llm_vision)

        def restore():
            model_choice.current.update(saved[0])
            common.llm, common.llm_vision, photography.llm_vision = saved[1:]
        self.addCleanup(restore)
        model_choice.current.update(text=Models.GPT_OSS_120B, vision=Models.QWEN_27B)
        self.built = []
        for name, value in (("build_llm", lambda model: self.built.append(model) or f"client of {model.name}"),
                            ("describe_llm", str)):
            patch = mock.patch.object(model_choice.factory, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def with_keys(self, **keys):
        """HELPER with_keys: makes the panel see only these provider keys."""
        patch = mock.patch.object(model_choice, "get_settings", _settings(**keys))
        patch.start()
        self.addCleanup(patch.stop)


class TestChoices(PanelCase):
    def test_text_and_vision_lists(self):
        """TEST panel choices: text models exclude the vision-only ones, vision models are only those that read images."""
        self.with_keys(groq_api_key_2="k", gemini_fra_key="k", huggingface_api_key="k", cloudflare_api_key="k",
                       cloudflare_account_id="a")
        self.assertEqual([model_choice.label(m) for m in model_choice.choices("text")],
                         ["gpt-oss-120b", "gpt-oss-20b", "llama3.2", "llama3.1:8b", "qwen3:8b", "qwen3:14b", "gemini-3.8-flash",
                          "Llama-3.2-3B-Instruct:featherless-ai", "llama-3.2-3b-instruct", "llama-3.2-1b-instruct",
                          "granite-4.0-h-micro"])
        self.assertEqual([model_choice.label(m) for m in model_choice.choices("vision")],
                         ["qwen3.8-27b", "moondream", "gemini-3.8-flash"])
        self.assertEqual(model_choice.missing_keys_note("text"), "")

    def test_a_model_without_its_key_is_not_offered(self):
        """TEST panel choices: the models of a provider whose key is missing are left out; local models need no key."""
        self.with_keys(groq_api_key_2="k")
        self.assertNotIn(Models.GEMINI_FLASH, model_choice.choices("text"))
        self.assertIn(Models.LLAMA3_2, model_choice.choices("text"))

    def test_the_panel_says_which_models_are_left_out_and_how_to_add_them(self):
        """TEST panel choices: a missing key is named with the models it hides and the command that sets it, never a key."""
        self.with_keys(groq_api_key_2="k")
        note = model_choice.missing_keys_note("text")
        self.assertIn("gemini-3.8-flash", note)
        self.assertIn("setup_env.py --key gemini_fra_key", note)
        self.assertNotIn("gpt-oss", note)

    def test_the_model_in_use_is_always_listed(self):
        """TEST panel choices: the model in use is shown even if its key is no longer set, and is not reported as left out."""
        self.with_keys()
        self.assertEqual(model_choice.choices("text")[0], Models.GPT_OSS_120B)
        self.assertNotIn("gpt-oss-120b", model_choice.missing_keys_note("text"))


class TestChoose(PanelCase):
    def setUp(self):
        super().setUp()
        self.with_keys(groq_api_key_2="k", gemini_fra_key="k")

    def test_text_model_is_replaced_for_every_agent(self):
        """TEST panel choose: a new text model replaces the client every agent reads, and becomes the one in use."""
        self.assertIsNone(model_choice.choose("text", "gpt-oss-20b"))
        self.assertEqual(common.llm, "client of openai/gpt-oss-20b")
        self.assertEqual(model_choice.current["text"], Models.GPT_OSS_20B)
        self.assertEqual(model_choice.current["vision"], Models.QWEN_27B)

    def test_vision_model_is_replaced_for_the_photo_node(self):
        """TEST panel choose: a new vision model replaces the client the photo node uses, not the text one."""
        text_before = common.llm
        self.assertIsNone(model_choice.choose("vision", "gemini-3.8-flash"))
        self.assertEqual(photography.llm_vision, "client of gemini-3.8-flash")
        self.assertEqual(common.llm_vision, "client of gemini-3.8-flash")
        self.assertIs(common.llm, text_before)

    def test_same_model_does_nothing(self):
        """TEST panel choose: confirming the model already in use builds nothing and reports no problem."""
        self.assertIsNone(model_choice.choose("text", "gpt-oss-120b"))
        self.assertEqual(self.built, [])

    def test_unknown_or_unavailable_model_is_refused(self):
        """TEST panel choose: a label that is not among the choices is refused and the model in use stays."""
        self.assertIn("non disponibile", model_choice.choose("text", "moondream"))
        self.assertEqual(model_choice.current["text"], Models.GPT_OSS_120B)

    def test_local_model_that_does_not_answer_is_refused(self):
        """TEST panel choose: a local model whose server is off is refused, with the reason, and the previous one stays."""
        with mock.patch.object(model_choice.httpx, "get", side_effect=httpx.ConnectError("refused")):
            problem = model_choice.choose("text", "llama3.2")
        self.assertIn("non risponde", problem)
        self.assertIn("gpt-oss-120b", problem)
        self.assertEqual(self.built, [])

    def test_local_model_installed_is_accepted(self):
        """TEST panel choose: a local model listed by the local server is accepted; one that is not installed is refused."""
        answer = types.SimpleNamespace(json=lambda: {"data": [{"id": "llama3.2:latest"}]})
        with mock.patch.object(model_choice.httpx, "get", return_value=answer):
            self.assertIsNone(model_choice.choose("text", "llama3.2"))
            problem = model_choice.choose("vision", "moondream")
        self.assertIn("non è installato", problem)

    def test_a_client_that_cannot_be_built_leaves_the_previous_model(self):
        """TEST panel choose: if the new client cannot be built the model in use stays and the problem is reported."""
        with mock.patch.object(model_choice.factory, "build_llm", side_effect=RuntimeError("no key")):
            problem = model_choice.choose("text", "gpt-oss-20b")
        self.assertIn("Resta attivo gpt-oss-120b", problem)
        self.assertEqual(model_choice.current["text"], Models.GPT_OSS_120B)


class TestPanelInTheApp(helpers.VitaTestCase):
    def setUp(self):
        super().setUp()
        import app
        self.module = app
        self.session = {"thread_id": "t", "chat_started": False}
        session = types.SimpleNamespace(get=lambda key, default=None: self.session.get(key, default),
                                        set=self.session.__setitem__)
        self.calls = []
        self.panels = []

        async def fake_panel(locked, problems=None):
            self.panels.append((locked, problems or {}))
        for target, name, value in (
                (self.module.cl, "user_session", session),
                (self.module, "send_panel", fake_panel),
                (model_choice, "choose", lambda kind, label: self.calls.append((kind, label)))):
            patch = mock.patch.object(target, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def update(self, **settings):
        """HELPER update: confirms the panel with these values, as Chainlit would."""
        helpers.run(self.module.settings_update, settings)

    def test_before_the_first_message_the_models_are_applied(self):
        """TEST panel in the app: before the chat starts the chosen models are applied and the panel is shown again; nothing is written in the chat."""
        self.update(text_model="gpt-oss-20b", vision_model="qwen3.8-27b")
        self.assertEqual(self.calls, [("text", "gpt-oss-20b"), ("vision", "qwen3.8-27b")])
        self.assertEqual(self.panels, [(False, {})])
        self.assertEqual(self.chat, [])

    def test_a_refused_choice_is_explained_in_the_panel_not_in_the_chat(self):
        """TEST panel in the app: when a model cannot be selected the reason goes under that choice in the panel; the chat stays empty."""
        refuse = lambda kind, label: "llama3.2 non selezionato: il servizio locale non risponde." if kind == "text" else None
        with mock.patch.object(model_choice, "choose", refuse):
            self.update(text_model="llama3.2", vision_model="qwen3.8-27b")
        self.assertEqual(self.panels, [(False, {"text": "llama3.2 non selezionato: il servizio locale non risponde."})])
        self.assertEqual(self.chat, [])

    def test_after_the_first_message_the_model_cannot_change(self):
        """TEST panel in the app: once the chat has started a model choice is ignored and the panel is shown locked again."""
        self.session["chat_started"] = True
        self.update(text_model="gpt-oss-20b", vision_model="gemini-3.8-flash")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.panels, [(True, {})])
        self.assertEqual(self.chat, [])

    def test_the_first_message_locks_the_panel(self):
        """TEST panel in the app: the first operator message marks the chat as started and shows the panel locked, once."""
        class IdleGraph:
            """A graph that accepts the message and does nothing: only the panel is under test."""
            def update_state(self, *args, **kwargs):
                pass

            def get_state(self, config):
                return types.SimpleNamespace(values={})

            async def astream_events(self, *args, **kwargs):
                return
                yield

        with mock.patch.object(self.module, "app", IdleGraph()):
            message = types.SimpleNamespace(content="1234", elements=[])
            helpers.run(self.module.main, message)
            helpers.run(self.module.main, message)
        self.assertTrue(self.session["chat_started"])
        self.assertEqual(self.panels, [(True, {})])
        self.assertEqual(self.chat, [])

    def test_a_new_chat_starts_unlocked(self):
        """TEST panel in the app: opening a chat shows the panel unlocked, whatever happened in the previous chat."""
        self.session["chat_started"] = True
        graph = types.SimpleNamespace(update_state=lambda *args, **kwargs: None)
        with mock.patch.object(self.module, "app", graph):
            helpers.run(self.module.start)
        self.assertFalse(self.session["chat_started"])
        self.assertEqual(self.panels, [(False, {})])
        self.assertEqual(self.chat, [])


class TestRealPanel(helpers.VitaTestCase):
    def test_the_locked_panel_disables_both_choices(self):
        """TEST panel widgets: the real panel has only the two model choices, both disabled and labelled once the chat has started."""
        import app
        sent = []

        class FakeSettings:
            def __init__(self, widgets):
                sent.append(widgets)

            async def send(self):
                return {}

        # Every key set, whatever the .env of the machine holds: no model is left out, so no note is shown.
        every_key = _settings(groq_api_key_2="k", gemini_fra_key="k", huggingface_api_key="k",
                              cloudflare_api_key="k", cloudflare_account_id="a")
        with mock.patch.object(app.cl, "ChatSettings", FakeSettings), \
                mock.patch.object(model_choice, "get_settings", every_key):
            helpers.run(app.send_panel, False)
            helpers.run(app.send_panel, True)
            helpers.run(app.send_panel, False, {"text": "llama3.2 non selezionato."})
        unlocked, locked, refused = sent
        self.assertEqual([w.description for w in unlocked], [None, None])
        self.assertEqual([w.description for w in refused], ["llama3.2 non selezionato.", None])
        self.assertEqual([w.id for w in unlocked], ["text_model", "vision_model"])
        self.assertEqual([w.disabled for w in unlocked], [False, False])
        self.assertEqual([w.disabled for w in locked], [True, True])
        self.assertTrue(all("non modificabile" in w.label for w in locked))
        self.assertTrue(all(type(w).__name__ == "Select" for w in unlocked + locked))


if __name__ == "__main__":
    unittest.main()
