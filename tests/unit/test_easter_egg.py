"""Easter egg: the code that triggers it, its messages, and the app keeping that chat away from the triage."""
import types
from unittest import mock

try:
    from . import helpers
except ImportError:
    import helpers

import app as vita_app
from scripts import easter_egg
from src.agents.persistence import TEST_FISCAL_CODE


class TestEasterEgg(helpers.VitaTestCase):
    def setUp(self):
        super().setUp()
        self.session = {}
        self.discarded = []

        async def discard_chat():
            self.discarded.append(True)
            return True
        user_session = types.SimpleNamespace(get=self.session.get, set=self.session.__setitem__)
        for patch in (mock.patch.object(vita_app.cl, "user_session", user_session),
                      mock.patch.object(easter_egg.chat_history, "discard_chat", discard_chat),
                      mock.patch.object(easter_egg, "PAUSE_SECONDS", 0)):
            patch.start()
            self.addCleanup(patch.stop)

    def send(self, text):
        """Sends one operator message to the app."""
        helpers.run(vita_app.main, types.SimpleNamespace(content=text, elements=[]))

    def test_only_the_exact_code_triggers_it(self):
        """TEST easter egg: the code alone triggers it, spaces around it allowed; nothing else does, the test fiscal code included."""
        self.assertTrue(easter_egg.is_code(f"  {easter_egg.CODE}\n"))
        for text in ("", None, easter_egg.CODE + "0", f"codice {easter_egg.CODE}", TEST_FISCAL_CODE):
            with self.subTest(text=text):
                self.assertFalse(easter_egg.is_code(text))

    def test_the_code_as_first_message_shows_the_messages_and_no_triage(self):
        """TEST easter egg: as first message the code shows every message by its author, ending with the link; the chat is
        discarded, the triage does not start and what is written afterwards gets one fixed answer."""
        with mock.patch.object(vita_app.app, "update_state") as triage:
            self.send(easter_egg.CODE)
            self.assertEqual(self.chat, [(easter_egg.AUTHOR, text) for text in easter_egg.MESSAGES])
            self.assertIn(easter_egg.VIDEO, self.last_message())
            self.assertEqual(self.discarded, [True])
            self.assertFalse(self.session.get("chat_started"))
            self.send("RSSMRA80A01H501U")
            self.assertEqual(self.chat[-1], (easter_egg.AUTHOR, easter_egg.AFTER))
            triage.assert_not_called()

    def test_the_links_and_the_icons_come_from_the_same_file(self):
        """TEST easter egg: the messages carry the two links, the video one in bold; the drawing behind them has every icon
        and its address is added once, before Chainlit's routes."""
        from chainlit.server import app as server
        text = "\n".join(easter_egg.MESSAGES)
        self.assertIn(f"]({easter_egg.GITHUB})", text)
        self.assertRegex(text, r"\*\*\[[^\]]+\]\(" + easter_egg.VIDEO.replace("?", r"\?") + r"\)\*\*")
        drawing = easter_egg.icons_svg()
        self.assertTrue(drawing.startswith("<svg "))
        for icon in easter_egg.ICONS:
            with self.subTest(icon=icon):
                self.assertIn(icon, drawing)
        easter_egg.register_route()
        easter_egg.register_route()
        paths = [getattr(route, "path", None) for route in server.router.routes]
        self.assertEqual(paths.count(easter_egg.ICONS_ROUTE), 1)
        self.assertLess(paths.index(easter_egg.ICONS_ROUTE), paths.index("/{full_path:path}"))

    def test_the_code_in_a_started_chat_is_an_ordinary_message(self):
        """TEST easter egg: once a chat has started, the code is passed to the triage like any other message."""
        self.session["chat_started"] = True
        with mock.patch.object(easter_egg, "play") as play, \
                mock.patch.object(vita_app.app, "update_state", side_effect=RuntimeError("reached the triage")):
            with self.assertRaises(RuntimeError):
                self.send(easter_egg.CODE)
            play.assert_not_called()


if __name__ == "__main__":
    import unittest
    unittest.main()
