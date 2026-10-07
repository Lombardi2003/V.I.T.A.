"""src/llm and shared helpers: retries, limits, JSON reading, clients, needed keys."""
import json
import types
import unittest
from unittest import mock

import httpx
import openai

try:
    from . import helpers  # noqa: F401  (sets up the environment: project path, UTF-8)
except ImportError:
    import helpers  # noqa: F401

from scripts import setup_env
from src.agents.common import as_list, as_text, is_no, is_yes
from src.llm import calls, factory
from src.llm.providers import GEMINI, GROQ, Models

_req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _rate(msg):
    """HELPER _rate: a 429 rate-limit error with the given message."""
    return openai.RateLimitError(msg, response=httpx.Response(429, request=_req), body=None)


class TestRetries(unittest.TestCase):
    def call(self, errors):
        """HELPER call: runs call_with_retry on a function that raises these errors first; returns (result, calls, waits)."""
        queue, count, waits = list(errors), [0], []

        def fn():
            count[0] += 1
            if queue:
                raise queue.pop(0)
            return "ok"
        with mock.patch.object(calls.time, "sleep", lambda s: waits.append(s)):
            try:
                result = calls.call_with_retry(fn)
            except Exception as e:
                result = type(e).__name__
        return result, count[0], waits

    def test_per_minute_limit_waits_and_succeeds(self):
        """TEST retries: a per-minute limit waits the time suggested by the provider (+1 s) and succeeds."""
        result, n, waits = self.call([_rate("Please try again in 44.2s")])
        self.assertEqual((result, n), ("ok", 2))
        self.assertAlmostEqual(waits[0], 45.2, places=1)

    def test_daily_limit_stops_at_once(self):
        """TEST retries: a wait of minutes (daily limit) is not waited, the error is raised at once."""
        result, n, waits = self.call([_rate("Please try again in 4m52.03s")])
        self.assertEqual((result, n, waits), ("RateLimitError", 1, []))

    def test_wait_with_minutes_under_the_cap_is_waited(self):
        """TEST retries: "1m2.5s" is read as 62.5 s and, being under the 65 s cap, is waited."""
        result, n, waits = self.call([_rate("Please try again in 1m2.5s")])
        self.assertEqual((result, n), ("ok", 2))
        self.assertAlmostEqual(waits[0], 63.5, places=1)

    def test_at_most_two_retries(self):
        """TEST retries: after two retries the error is raised."""
        result, n, _ = self.call([_rate("try again in 5s")] * 3)
        self.assertEqual((result, n), ("RateLimitError", 3))

    def test_unreachable_server(self):
        """TEST retries: a connection error is retried."""
        result, n, waits = self.call([openai.APIConnectionError(request=_req)])
        self.assertEqual((result, n), ("ok", 2))

    def test_non_temporary_error_is_not_retried(self):
        """TEST retries: a non-temporary error is raised at the first attempt."""
        result, n, _ = self.call([ValueError("bad request")])
        self.assertEqual((result, n), ("ValueError", 1))

    def test_stream_restart_does_not_duplicate_partial_output(self):
        """TEST streaming: an error halfway through the stream restarts from scratch, without repeating the partial text."""
        attempts = []

        class FakeClient:
            openai_api_base = ""   # no known provider: no token limit
            max_tokens = 4096

            def stream(self, prompt):
                attempts.append(1)
                yield types.SimpleNamespace(content='{"a": ')
                if len(attempts) == 1:
                    raise openai.APIConnectionError(request=_req)
                yield types.SimpleNamespace(content="1}")
        with mock.patch.object(calls.time, "sleep", lambda s: None):
            self.assertEqual(calls.stream_text("prompt", FakeClient()), '{"a": 1}')
        self.assertEqual(len(attempts), 2)


class TestClient(unittest.TestCase):
    def test_single_retry_layer_and_timeout_per_provider(self):
        """TEST client: no retries inside the client, 120 s timeout for Groq and no timeout for Ollama."""
        groq = factory.build_llm(Models.GPT_OSS_120B)
        self.assertEqual(groq.max_retries, 0)
        self.assertEqual(groq.request_timeout, GROQ.request_timeout)
        ollama = factory.build_llm(Models.LLAMA3_2_LOCAL)
        self.assertEqual(ollama.max_retries, 0)
        self.assertIsNone(ollama.request_timeout)

    def test_address_with_the_account_id(self):
        """TEST client: a provider whose address holds the account id gets it from the settings, and needs both fields."""
        from src.llm.providers import CLOUDFLARE
        fake = types.SimpleNamespace(cloudflare_api_key="k", cloudflare_account_id="abc", temperature=0.0)
        with mock.patch.object(factory, "get_settings", lambda: fake):
            client = factory.build_llm(Models.LLAMA3_2_CF)
            self.assertEqual(str(client.openai_api_base), "https://api.cloudflare.com/client/v4/accounts/abc/ai/v1")
            self.assertEqual(factory.provider_of(client), "cloudflare")
        fake.cloudflare_account_id = None
        with mock.patch.object(factory, "get_settings", lambda: fake):
            with self.assertRaisesRegex(RuntimeError, "CLOUDFLARE_ACCOUNT_ID"):
                factory.build_llm(Models.LLAMA3_2_CF)
        self.assertEqual(GROQ.account_field, None)
        self.assertEqual({CLOUDFLARE.key_field, CLOUDFLARE.account_field} <= setup_env._KEY_FIELDS, True)

    def test_max_tokens_within_the_per_minute_limit(self):
        """TEST client: max_tokens shrinks as the prompt grows and is not set for Ollama."""
        groq = factory.build_llm(Models.GPT_OSS_120B)
        short = calls.max_tokens_for("x" * 300, groq)
        long = calls.max_tokens_for("x" * 20000, groq)
        self.assertLessEqual(short, 4096)
        self.assertLess(long, short)
        self.assertIsNone(calls.max_tokens_for("x", factory.build_llm(Models.LLAMA3_2_LOCAL)))

    def test_max_tokens_never_below_the_floor(self):
        """TEST client: even with a huge prompt, max_tokens never drops below the minimum for a complete JSON."""
        groq = factory.build_llm(Models.GPT_OSS_120B)
        self.assertEqual(calls.max_tokens_for("x" * 100_000, groq), calls._MIN_RESPONSE_TOKENS)

    def test_unknown_model_gives_a_clear_error(self):
        """TEST client: a name that is not a model of providers.py raises an error that says where to add it."""
        with self.assertRaises(ValueError) as ctx:
            factory.build_llm("modello-inesistente")
        self.assertIn("src/llm/providers.py", str(ctx.exception))

    def test_missing_key_gives_a_clear_error(self):
        """TEST client: a provider key missing from .env raises an error naming the key field and how to set it."""
        no_key = types.SimpleNamespace(**{GROQ.key_field: "", "temperature": 0})
        with mock.patch.object(factory, "get_settings", lambda: no_key):
            with self.assertRaises(RuntimeError) as ctx:
                factory.build_llm(Models.GPT_OSS_120B)
        self.assertIn(GROQ.key_field.upper(), str(ctx.exception))
        self.assertIn("setup_env.py", str(ctx.exception))

    def test_provider_and_description(self):
        """TEST client: the provider is read from the client address and shown in the model description."""
        groq = factory.build_llm(Models.GPT_OSS_120B)
        self.assertEqual(factory.provider_of(groq), "groq")
        self.assertEqual(factory.describe_llm(groq), "groq/openai/gpt-oss-120b (ragionamento low)")
        self.assertEqual(factory.tokens_per_minute_limit(groq), GROQ.tokens_per_minute)
        self.assertEqual(factory.tokens_per_minute_limit(factory.build_llm(Models.LLAMA3_2_LOCAL)), None)


class TestNeededKeys(unittest.TestCase):
    def needed(self, text_model, vision_model):
        """HELPER needed: key fields setup_env would ask for with these two models chosen."""
        with mock.patch.object(factory, "TEXT_MODEL", text_model), mock.patch.object(factory, "VISION_MODEL", vision_model):
            return setup_env._needed_key_fields()

    def test_keys_asked_only_for_the_providers_in_use(self):
        """TEST setup_env: Ollama needs no key, a Groq model needs the Groq key, a Gemini model the Gemini key."""
        self.assertEqual(self.needed(Models.LLAMA3_2_LOCAL, Models.MOONDREAM), set())
        self.assertEqual(self.needed(Models.GPT_OSS_120B, Models.QWEN_27B), {GROQ.key_field})
        self.assertEqual(self.needed(Models.GEMINI_FLASH, Models.MOONDREAM), {GEMINI.key_field})
        self.assertEqual(self.needed(Models.GEMINI_FLASH, Models.QWEN_27B), {GEMINI.key_field, GROQ.key_field})

    def test_every_key_field_of_the_settings_is_recognised(self):
        """TEST setup_env: every provider key field of the settings is treated as a key, and each provider's exists."""
        from src.llm.providers import PROVIDERS
        from src.settings import Settings
        self.assertEqual(setup_env._KEY_FIELDS, {"groq_api_key", "groq_api_key_2", "gemini_api_key", "gemini_fra_key",
                                                   "huggingface_api_key", "cloudflare_api_key",
                                                   "cloudflare_account_id"})
        for provider in PROVIDERS:
            with self.subTest(provider=provider.name):
                self.assertTrue(provider.key_field is None or provider.key_field in Settings.model_fields)

    def test_one_key_can_be_set_even_if_no_active_model_needs_it(self):
        """TEST setup_env: --key asks for that key only, writes it and keeps the other values; an unknown name is refused."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("GROQ_API_KEY_2=first-value\nTEMPERATURE=0.0\n", encoding="utf-8")
            asked = []
            with mock.patch.object(setup_env, "ENV_PATH", env), \
                 mock.patch("builtins.input", lambda prompt: asked.append(prompt) or "new-value"), \
                 mock.patch("builtins.print"):
                setup_env.set_key("GEMINI_API_KEY")
                with self.assertRaises(SystemExit):
                    setup_env.set_key("not_a_key")
            self.assertEqual(len(asked), 1)
            self.assertIn("GEMINI_API_KEY", asked[0])
            self.assertEqual(env.read_text(encoding="utf-8").splitlines(),
                             ["GROQ_API_KEY_2=first-value", "TEMPERATURE=0.0", "GEMINI_API_KEY=new-value"])

    def test_every_model_belongs_to_a_known_provider(self):
        """TEST providers: every model of the catalogue points to one of the listed providers, with a unique address."""
        from src.llm.providers import Model, PROVIDERS
        models = [m for m in vars(Models).values() if isinstance(m, Model)]
        self.assertTrue(models)
        self.assertTrue(all(m.provider in PROVIDERS for m in models))
        self.assertEqual(len({p.base_url for p in PROVIDERS}), len(PROVIDERS))


class TestJsonReading(unittest.TestCase):
    def test_think_block_and_fences(self):
        """TEST extract_json: <think> blocks, ```json fences and surrounding text are removed."""
        self.assertEqual(calls.extract_json("<think>ragiono</think>```json\n{\"a\": 1}\n```"), {"a": 1})
        self.assertEqual(calls.extract_json("Ecco: {\"a\": 2} fine"), {"a": 2})

    def test_not_an_object_or_empty(self):
        """TEST extract_json: a list, an empty text or no JSON raise JSONDecodeError."""
        for text in ("[1, 2]", "", "nessun json", None):
            with self.subTest(text=text):
                with self.assertRaises(json.JSONDecodeError):
                    calls.extract_json(text)


class TestSharedHelpers(unittest.TestCase):
    def test_yes_no(self):
        """TEST is_yes/is_no: Italian and English yes/no in many spellings; anything else is neither."""
        for v in (True, "si", "sì", "si'", "true", "yes", " SI "):
            self.assertTrue(is_yes(v), v)
        for v in (False, "no", "false"):
            self.assertTrue(is_no(v), v)
        self.assertFalse(is_yes("forse"))
        self.assertFalse(is_no("forse"))

    def test_lists_and_texts(self):
        """TEST as_list/as_text: single values become lists, lists and objects become readable text."""
        self.assertEqual(as_list("penicillina"), ["penicillina"])
        self.assertEqual(as_list(None), [])
        self.assertEqual(as_list(["a"]), ["a"])
        self.assertEqual(as_text(["a", "b"]), "a, b")
        self.assertEqual(as_text({"esame": "RX torace"}), "RX torace")
        self.assertEqual(as_text(None), "")


if __name__ == "__main__":
    unittest.main()
