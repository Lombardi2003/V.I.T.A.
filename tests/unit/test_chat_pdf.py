"""Chat PDF: the messages read from the archive, their layout as a document and the file to download."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers  # noqa: F401
except ImportError:
    import helpers  # noqa: F401

import fitz

from scripts import chat_pdf
from src import chat_history


def archive_with_a_chat(folder: str) -> Path:
    """An archive with one chat of the operator (messages out of order, a step, an empty message) and one without owner."""
    path = Path(folder) / "history.db"
    chat_history.create_tables(path)
    connection = sqlite3.connect(path)
    connection.execute('INSERT INTO threads ("id", "name", "userId") VALUES (?, ?, ?)',
                       ("chat", "Rossi Mario · 08/10 15:32", "user"))
    connection.execute('INSERT INTO threads ("id", "name") VALUES (?, ?)', ("orphan", "senza proprietario"))
    steps = [
        ("3", "assistant_message", "Primario", "2026-10-08T13:42:00.000000Z",
         "**Report di sintesi**\n**Codice** `🟠 ARANCIONE` · **Ipotesi diagnostica preliminare** Asma\n\n"
         "**Esami e accertamenti**\n- RX torace\n- saturazione"),
        ("1", "user_message", "operatore", "2026-10-08T13:32:00.000000Z", "RSSMRA80A01X000X"),
        ("2", "tool", "Ricerca Codice Fiscale", "2026-10-08T13:32:01.000000Z", "{}"),
        ("4", "assistant_message", "System", "2026-10-08T13:43:00.000000Z", "  "),
    ]
    connection.executemany('INSERT INTO steps ("id", "type", "name", "createdAt", "output", "threadId") '
                           "VALUES (?, ?, ?, ?, ?, 'chat')", steps)
    connection.commit()
    connection.close()
    return path


class TestChatPdf(unittest.TestCase):
    def test_messages_are_read_in_order_without_steps_and_empty_ones(self):
        """TEST chat pdf: the chat gives title and messages in time order; steps, empty messages and unknown chats are left out."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path = archive_with_a_chat(folder)
            title, messages = chat_pdf.read_chat("chat", path)
            self.assertEqual(title, "Rossi Mario · 08/10 15:32")
            self.assertEqual([(kind, author) for kind, author, _, _ in messages],
                             [("user_message", "operatore"), ("assistant_message", "Primario")])
            self.assertIsNone(chat_pdf.read_chat("missing", path))
            self.assertIsNone(chat_pdf.read_chat("orphan", path))

    def test_a_message_keeps_its_structure(self):
        """TEST chat pdf: bold, italic, line breaks and lists are kept; the code is a coloured label; symbols a PDF font lacks are dropped."""
        html = chat_pdf.message_html("**Codice** `🔴 ROSSO` · *nota*\nseconda riga <b>\n\n**Esami**\n- uno\n- due")
        self.assertIn("<b>Codice</b>", html)
        self.assertIn(f'background-color: {chat_pdf.URGENCY_COLOURS["ROSSO"][0]}', html)
        self.assertIn("<i>nota</i><br/>seconda riga &lt;b&gt;</p>", html)
        self.assertIn("<p><b>Esami</b></p><ul><li>uno</li><li>due</li></ul>", html)
        self.assertNotIn("🔴", html)

    def test_the_document_holds_the_whole_conversation(self):
        """TEST chat pdf: the PDF has the title, who wrote each message and every message; an unknown chat gives none."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path = archive_with_a_chat(folder)
            title, data = chat_pdf.chat_pdf("chat", path)
            self.assertIsNone(chat_pdf.chat_pdf("missing", path))
        self.assertTrue(data.startswith(b"%PDF"))
        with fitz.open(stream=data, filetype="pdf") as document:
            text = " ".join(page.get_text() for page in document)
        for part in ("V.I.T.A.", "Rossi Mario", chat_history.OPERATOR_NAME, "RSSMRA80A01X000X", "Primario",
                     "Report di sintesi", "ARANCIONE", "RX torace", "saturazione", "strumento di supporto"):
            with self.subTest(part=part):
                self.assertIn(part, text)
        self.assertNotIn("Ricerca Codice Fiscale", text)

    def test_file_name(self):
        """TEST chat pdf: the file is named after the chat, without characters a file name cannot have."""
        self.assertEqual(chat_pdf.file_name("Rossi Mario · 08/10 15:32"), "VITA - Rossi Mario - 08-10 15.32.pdf")
        self.assertEqual(chat_pdf.file_name(""), "VITA.pdf")

    def test_the_download_address_is_added_once_before_chainlit_routes(self):
        """TEST chat pdf: the download address comes first among the server's routes and is not added twice."""
        from chainlit.server import app as server
        chat_pdf.register_route()
        chat_pdf.register_route()
        paths = [getattr(route, "path", None) for route in server.router.routes]
        self.assertEqual(paths.count(chat_pdf.PDF_ROUTE), 1)
        self.assertLess(paths.index(chat_pdf.PDF_ROUTE), paths.index("/{full_path:path}"))


if __name__ == "__main__":
    unittest.main()
