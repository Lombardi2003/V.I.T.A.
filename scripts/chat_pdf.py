"""The PDF of a chat: the whole conversation read from the archive and laid out as a document to download."""

from datetime import datetime, timezone
from html import escape
import io
import re
import sqlite3

import fitz  # PyMuPDF

from src.agents.roundtable import URGENCY_LEVELS
from src.chat_history import HISTORY_DB, OPERATOR_NAME

PDF_ROUTE = "/vita/pdf/{thread_id}"  # Where public/script.js downloads the document from.
FOOTER = "V.I.T.A. è uno strumento di supporto: verificare sempre le informazioni."

# Author -> colour of the bar beside its messages (the same palette as public/style.css).
AUTHOR_COLOURS = {
    "System": "#00a87a", "Primario": "#00a87a", "Anagrafica": "#ff8d42", "Revisore": "#a78bfa", "Fotografia": "#fbbf24",
    "Supervisore": "#60a5fa", "Cardiologia": "#f87171", "Neurologia": "#818cf8", "Dermatologia": "#f472b6",
    "Ortopedia": "#d6a06e", "Gastroenterologia": "#a3e635", "Pneumologia": "#22d3ee", "Otorinolaringoiatria": "#fb7185",
    "Oftalmologia": "#38bdf8", "Urologia": "#34d399", "Medicina": "#a78bfa",
}
USER_COLOUR = "#0099d6"
AUTHOR_NAMES = {"System": "Sistema"}  # Shown instead of the internal author name.

# Urgency code -> background and text colour of its label in the report.
URGENCY_COLOURS = dict(zip(URGENCY_LEVELS, [("#dc2626", "#ffffff"), ("#f97316", "#ffffff"), ("#0ea5e9", "#ffffff"),
                                            ("#16a34a", "#ffffff"), ("#e5e7eb", "#111827")]))

_CSS = """
body { font-family: sans-serif; font-size: 10pt; color: #1f2937; line-height: 1.35; }
h1 { font-size: 22pt; color: #00a87a; margin: 0; }
.subtitle { font-size: 8pt; color: #4b5563; margin: 0 0 8pt 0; }
.title { font-size: 12pt; font-weight: bold; margin: 0; }
.meta { font-size: 8.5pt; color: #4b5563; margin: 0 0 6pt 0; }
.rule { border-top: 1.2pt solid #00a87a; margin: 0 0 10pt 0; }
.who { font-size: 8pt; font-weight: bold; margin: 9pt 0 2pt 0; }
.user-who { text-align: right; }
.bubble { background-color: #eef8f4; padding: 5pt 8pt 5pt 8pt; margin: 0; }
.user { background-color: #e6f4fb; margin-left: 110pt; }
.bubble p { margin: 0 0 4pt 0; }
.bubble ul { margin: 0 0 4pt 0; padding-left: 14pt; }
.code { font-weight: bold; }
.footer { font-size: 7.5pt; color: #6b7280; text-align: center; margin: 14pt 0 0 0; }
"""

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\*\w])\*([^\*\n]+?)\*(?!\*)")
_CODE = re.compile(r"`([^`\n]+)`")


def _code_label(match: re.Match) -> str:
    """The text between backticks: an urgency code becomes a coloured label, anything else is just bold."""
    text = match.group(1).strip()
    colours = URGENCY_COLOURS.get(text)
    if colours is None:
        return f"<b>{text}</b>"
    return f'<span class="code" style="background-color: {colours[0]}; color: {colours[1]}">&nbsp;{text}&nbsp;</span>'


def _inline(text: str) -> str:
    """One line of a message as HTML: bold, italic and the code label."""
    text = escape(_EMOJI.sub("", text), quote=False)
    text = _CODE.sub(_code_label, text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    return _ITALIC.sub(r"<i>\1</i>", text)


def message_html(text: str) -> str:
    """A message as HTML: paragraphs, line breaks and bulleted lists, as the chat shows them."""
    parts = []
    for block in re.split(r"\n\s*\n", text.strip()):
        paragraph, items = [], []

        def flush():
            if paragraph:
                parts.append("<p>" + "<br/>".join(paragraph) + "</p>")
                paragraph.clear()
            if items:
                parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>")
                items.clear()

        for line in block.split("\n"):
            if line.startswith("- "):
                if paragraph:
                    flush()
                items.append(_inline(line[2:]))
            elif line.strip():
                if items:
                    flush()
                paragraph.append(_inline(line.strip()))
        flush()
    return "".join(parts)


def _local(timestamp: str | None) -> datetime | None:
    """A timestamp of the archive (UTC) as local time, or None if it cannot be read."""
    try:
        return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).astimezone()
    except (TypeError, ValueError):
        return None


def read_chat(thread_id: str, path=HISTORY_DB) -> tuple[str, list[tuple[str, str, str, str]]] | None:
    """Title and messages (kind, author, time, text) of a chat, in order; None if the chat is not in the archive."""
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        thread = connection.execute('SELECT "name" FROM threads WHERE "id" = ? AND "userId" IS NOT NULL',
                                    (thread_id,)).fetchone()
        if thread is None:
            return None
        rows = connection.execute(
            'SELECT "type", "name", "createdAt", "output" FROM steps WHERE "threadId" = ? '
            'AND "type" IN (\'user_message\', \'assistant_message\') ORDER BY "createdAt"', (thread_id,)).fetchall()
    finally:
        connection.close()
    return thread[0] or "", [(kind, author or "", created or "", output) for kind, author, created, output in rows
                             if (output or "").strip()]


def chat_html(title: str, messages: list[tuple[str, str, str, str]]) -> str:
    """The document as HTML: heading, then every message with who wrote it and when."""
    started = _local(messages[0][2]) if messages else None
    parts = [
        "<h1>V.I.T.A.</h1>", '<p class="subtitle">VIRTUAL INTELLIGENT TRIAGE ASSISTANT</p>',
        f'<p class="title">{escape(title)}</p>',
        f'<p class="meta">Triage del {started:%d/%m/%Y}, ore {started:%H:%M}</p>' if started else "",
        '<div class="rule"></div>',
    ]
    for kind, author, created, text in messages:
        when = _local(created)
        time_text = f" · {when:%H:%M}" if when else ""
        if kind == "user_message":
            parts.append(f'<p class="who user-who" style="color: {USER_COLOUR}">{OPERATOR_NAME}{time_text}</p>'
                         f'<div class="bubble user" style="border-right: 2.5pt solid {USER_COLOUR}">{message_html(text)}</div>')
        else:
            colour = AUTHOR_COLOURS.get(author, AUTHOR_COLOURS["System"])
            name = escape(AUTHOR_NAMES.get(author, author))
            parts.append(f'<p class="who" style="color: {colour}">{name}{time_text}</p>'
                         f'<div class="bubble" style="border-left: 2.5pt solid {colour}">{message_html(text)}</div>')
    parts.append(f'<p class="footer">{FOOTER}</p>')
    return "".join(parts)


def chat_pdf(thread_id: str, path=HISTORY_DB) -> tuple[str, bytes] | None:
    """Title and PDF of a chat, A4 pages; None if the chat is not in the archive."""
    chat = read_chat(thread_id, path)
    if chat is None:
        return None
    title, messages = chat
    story = fitz.Story(html=chat_html(title, messages), user_css=_CSS)
    page = fitz.paper_rect("a4")
    area = page + (48, 44, -48, -44)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()
    return title, buffer.getvalue()


def register_route() -> None:
    """Adds the download address to Chainlit's web server. It goes before Chainlit's own routes: the last of them
    answers every address with the chat page."""
    from chainlit.server import UserParam, app as server
    from fastapi import HTTPException, Response
    from fastapi.routing import APIRoute

    if any(getattr(route, "path", None) == PDF_ROUTE for route in server.router.routes):
        return  # The app module is loaded again when Chainlit reloads it.

    async def download(thread_id: str, current_user: UserParam) -> Response:
        """The PDF of one chat of the signed-in operator."""
        document = chat_pdf(thread_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Chat non trovata")
        title, data = document
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{file_name(title)}"'})

    server.router.routes.insert(0, APIRoute(PDF_ROUTE, download, methods=["GET"]))


def file_name(title: str) -> str:
    """The name the browser saves the document with: the chat title, without characters a file name cannot have."""
    clean = re.sub(r"[^\w\-. ]+", "", title.replace("/", "-").replace(":", ".").replace("·", "-"), flags=re.ASCII)
    clean = re.sub(r"\s+", " ", clean).strip(" -")
    return f"VITA - {clean}.pdf" if clean else "VITA.pdf"
