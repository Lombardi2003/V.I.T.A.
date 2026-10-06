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

    def test_leftovers_of_deleted_chats_are_cleared_at_start(self):
        """TEST archive: a chat row without owner, with its messages, is removed when the archive is opened; owned chats stay."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.db"
            chat_history.create_tables(path)
            connection = sqlite3.connect(path)
            connection.execute('INSERT INTO threads ("id", "name", "userId") VALUES (?, ?, ?)', ("kept", "Rossi Mario", "user-1"))
            connection.execute('INSERT INTO threads ("id", "name") VALUES (?, ?)', ("leftover", "1234"))
            connection.executemany('INSERT INTO steps ("id", "threadId") VALUES (?, ?)', [("s1", "kept"), ("s2", "leftover")])
            connection.commit()
            connection.close()
            chat_history.create_tables(path)
            connection = sqlite3.connect(path)
            threads = [row[0] for row in connection.execute('SELECT "id" FROM threads')]
            steps = [row[0] for row in connection.execute('SELECT "id" FROM steps')]
            connection.close()
        self.assertEqual((threads, steps), (["kept"], ["s1"]))

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


class TestStoredTitle(unittest.TestCase):
    def test_the_first_message_is_never_stored_as_a_title(self):
        """TEST archive title: the name Chainlit gives a new chat is replaced by the neutral one; later names are ignored; set_title writes."""
        async def scenario(path):
            archive = chat_history.build_data_layer(path)
            try:
                await archive.update_thread("t1")                                # the row, as a first step creates it
                await archive.update_thread("t1", name="RSSMRA80A01H501U")       # Chainlit: the first message
                first = (await archive.execute_sql('SELECT "name" FROM threads', {}))[0]["name"]
                await archive.update_thread("t1", name="a manual rename")
                second = (await archive.execute_sql('SELECT "name" FROM threads', {}))[0]["name"]
                await archive.set_title("t1", "Rossi Mario · 04/10 21:14")
                third = (await archive.execute_sql('SELECT "name" FROM threads', {}))[0]["name"]
                return first, second, third
            finally:
                await archive.engine.dispose()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder, mock.patch.object(chat_history.log, "info"):
            first, second, third = helpers.run(scenario, Path(folder) / "history.db")
        self.assertTrue(first.startswith("Nuovo triage · "))
        self.assertEqual(second, first)
        self.assertEqual(third, "Rossi Mario · 04/10 21:14")


class TestArchiveTime(unittest.TestCase):
    def test_chat_dates_are_in_utc(self):
        """TEST archive time: a chat is dated with the real UTC time, not with the local time marked as UTC."""
        from datetime import timezone
        archive = chat_history.ChatArchive.__new__(chat_history.ChatArchive)
        stamp = helpers.run(archive.get_current_timestamp)
        self.assertTrue(stamp.endswith("Z"))
        written = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        self.assertLess(abs((datetime.now(timezone.utc) - written).total_seconds()), 5)


class TestChatTitle(unittest.TestCase):
    def test_title_with_surname_name_and_time(self):
        """TEST chat title: surname, name, day and time of the chat."""
        card = {"first_name": "Mario", "last_name": " Rossi "}
        self.assertEqual(chat_history.chat_title(card, datetime(2026, 10, 4, 19, 50)), "Rossi Mario · 04/10 19:50")

    def test_neutral_title_for_a_new_chat(self):
        """TEST chat title: a chat that has no confirmed card yet is titled with a neutral label and its time."""
        self.assertEqual(chat_history.new_chat_title(datetime(2026, 10, 4, 9, 5)), "Nuovo triage · 04/10 09:05")

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

    def test_neutral_title_first_then_the_patient_name(self):
        """TEST chat title in the app: a neutral title from the first message, the patient's name once the card is confirmed, each written once."""
        self.session["chat_started_at"] = datetime(2026, 10, 4, 21, 14)
        self.title()
        self.title()
        self.assertEqual(self.titles, ["Nuovo triage · 04/10 21:14"])
        self.state["card_confirmed"] = True
        self.title()
        self.title()
        self.assertEqual(self.titles, ["Nuovo triage · 04/10 21:14", "Rossi Mario · 04/10 21:14"])

    def test_the_fiscal_code_is_never_a_title(self):
        """TEST chat title in the app: whatever the card holds before confirmation, the title does not contain the fiscal code."""
        self.state["patient_card"] = {"fiscal_code": "RSSMRA80A01H501U", "first_name": "", "last_name": ""}
        self.title()
        self.state["card_confirmed"] = True
        self.title()
        self.assertTrue(self.titles)
        self.assertFalse(any("RSSMRA" in title for title in self.titles))

    def test_a_failure_does_not_disturb_the_triage(self):
        """TEST chat title in the app: if the archive fails the error stays in the log and the chat goes on."""
        self.state["card_confirmed"] = True

        async def broken(title):
            raise RuntimeError("archive unreachable")
        with mock.patch.object(chat_history, "rename_chat", broken), mock.patch.object(self.module.log, "exception"):
            self.title()
        self.assertNotIn("chat_title", self.session)

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
