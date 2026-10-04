"""Chat history: the archive tables, the automatic user, the chat title and the session secret."""
import os
import sqlite3
import tempfile
import types
import typing
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

try:
    from . import helpers
except ImportError:
    import helpers

import chainlit.data
from chainlit.step import StepDict

from scripts import setup_env
from src import chat_history


class TestArchive(unittest.TestCase):
    def test_tables_are_created_once_and_fit_what_chainlit_writes(self):
        """TEST archive: the five tables are created, twice without error, and the steps table has every field of a step."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.db"
            chat_history.create_tables(path)
            chat_history.create_tables(path)
            connection = sqlite3.connect(path)
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            columns = {row[1]: row[2] for row in connection.execute("PRAGMA table_info(steps)")}
            connection.close()
        self.assertEqual(tables, {"users", "threads", "steps", "elements", "feedbacks"})
        self.assertLessEqual(set(typing.get_type_hints(StepDict)), set(columns))
        # Flags must come back as numbers: read as text, "0" would count as true in the interface.
        self.assertEqual({columns[c] for c in ("streaming", "isError", "waitForAnswer")}, {"BOOLEAN"})

    def test_the_tests_never_reach_the_real_archive(self):
        """TEST archive: inside the tests Chainlit finds no archive, so nothing is written to the real file."""
        self.assertIsNone(chainlit.data.get_data_layer())
        self.assertFalse(helpers.run(chat_history.rename_chat, "x"))


class TestOperatorName(unittest.TestCase):
    def test_the_stored_user_is_shown_with_its_display_name(self):
        """TEST archive user: the user read back from the archive carries the name to show, which the archive does not store."""
        from chainlit.user import User

        async def round_trip(path):
            archive = chat_history.build_data_layer(path)
            try:
                await archive.create_user(User(identifier=chat_history.OPERATOR))
                return await archive.get_user(chat_history.OPERATOR), await archive.get_user("someone else")
            finally:
                await archive.engine.dispose()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder, mock.patch.object(chat_history.log, "info"):
            operator, unknown = helpers.run(round_trip, Path(folder) / "history.db")
        self.assertEqual(operator.identifier, "operatore")
        self.assertEqual(operator.display_name, "Operatore Sanitario")
        self.assertIsNone(unknown)


class TestChatTitle(unittest.TestCase):
    def test_title_with_surname_name_and_time(self):
        """TEST chat title: surname, name, day and time of the chat."""
        card = {"first_name": "Mario", "last_name": " Rossi "}
        self.assertEqual(chat_history.chat_title(card, datetime(2026, 10, 4, 19, 50)), "Rossi Mario · 04/10 19:50")

    def test_no_title_until_both_names_are_known(self):
        """TEST chat title: without the name or the surname there is no title, and the fiscal code is never used."""
        for card in ({}, {"first_name": "Mario"}, {"last_name": "Rossi", "first_name": ""}, {"fiscal_code": "RSSMRA80A01H501U"}):
            self.assertIsNone(chat_history.chat_title(card))


class TestTitleInTheApp(helpers.VitaTestCase):
    def setUp(self):
        super().setUp()
        import app
        self.module = app
        self.session = {}
        session = types.SimpleNamespace(get=lambda key, default=None: self.session.get(key, default),
                                        set=self.session.__setitem__)
        self.titles = []

        async def rename(title):
            self.titles.append(title)
            return True
        self.state = {"card_confirmed": False, "patient_card": {"first_name": "Mario", "last_name": "Rossi"}}
        graph = types.SimpleNamespace(get_state=lambda config: types.SimpleNamespace(values=self.state))
        for target, name, value in ((self.module.cl, "user_session", session), (self.module, "app", graph),
                                    (chat_history, "rename_chat", rename)):
            patch = mock.patch.object(target, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def title(self):
        """HELPER title: runs the titling step as app.py does after every message."""
        helpers.run(self.module._title_chat, {})

    def test_titled_once_when_the_card_is_confirmed(self):
        """TEST chat title in the app: no title while the card is being filled in, one title once it is confirmed, never again."""
        self.title()
        self.assertEqual(self.titles, [])
        self.state["card_confirmed"] = True
        self.title()
        self.title()
        self.assertEqual(len(self.titles), 1)
        self.assertTrue(self.titles[0].startswith("Rossi Mario · "))

    def test_a_failure_does_not_disturb_the_triage(self):
        """TEST chat title in the app: if the archive fails the error stays in the log and the chat goes on."""
        self.state["card_confirmed"] = True

        async def broken(title):
            raise RuntimeError("archive unreachable")
        with mock.patch.object(chat_history, "rename_chat", broken), mock.patch.object(self.module.log, "exception"):
            self.title()
        self.assertNotIn("chat_titled", self.session)

    def test_every_visitor_is_the_same_operator(self):
        """TEST automatic user: whoever opens the app is signed in as the single operator, without credentials."""
        user = self.module.automatic_user({})
        self.assertEqual(user.identifier, chat_history.OPERATOR)
        self.assertEqual(user.display_name, "Operatore Sanitario")


class TestSessionSecret(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.env = Path(self._tmp.name) / ".env"
        self.env.write_text("GROQ_API_KEY_2=some-key\n", encoding="utf-8")
        for patch in (mock.patch.object(setup_env, "ENV_PATH", self.env), mock.patch.dict(os.environ)):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop(setup_env.SESSION_SECRET, None)

    def lines(self):
        """HELPER lines: the lines of the temporary .env."""
        return self.env.read_text(encoding="utf-8").splitlines()

    def test_generated_once_and_kept(self):
        """TEST session secret: generated the first time beside the other values, then read back unchanged."""
        setup_env.ensure_session_secret()
        first = os.environ[setup_env.SESSION_SECRET]
        self.assertEqual(len(first), 64)
        self.assertEqual(self.lines(), ["GROQ_API_KEY_2=some-key", f"{setup_env.SESSION_SECRET}={first}"])
        os.environ.pop(setup_env.SESSION_SECRET)
        setup_env.ensure_session_secret()
        self.assertEqual(os.environ[setup_env.SESSION_SECRET], first)
        self.assertEqual(len(self.lines()), 2)

    def test_nothing_is_written_if_the_secret_is_already_in_the_environment(self):
        """TEST session secret: with the secret already in the environment the file is left as it is."""
        os.environ[setup_env.SESSION_SECRET] = "from-the-environment"
        setup_env.ensure_session_secret()
        self.assertEqual(self.lines(), ["GROQ_API_KEY_2=some-key"])

    def test_the_secret_is_never_asked_as_a_key(self):
        """TEST session secret: it is not a field of the settings, so setup_env never asks the operator for it."""
        self.assertNotIn(setup_env.SESSION_SECRET.lower(), setup_env.Settings.model_fields)
        self.assertNotIn(setup_env.SESSION_SECRET.lower(), setup_env._KEY_FIELDS)


if __name__ == "__main__":
    unittest.main()
