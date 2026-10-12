"""The easter egg: a code that, sent as the first message of a chat, shows a few messages by the author of the project
instead of starting a triage. Everything about it is here: the code, who speaks, the messages, the links and the
icons behind the text. No model is called, nothing is stored in the patient database and the chat is kept out of
the history. In that chat the message box is hidden (see "EASTER EGG" in public/style.css)."""

import asyncio

import chainlit as cl

from src import chat_history
from src.log import get_logger

log = get_logger("easter_egg")

CODE = "2810"  # The day of the graduation, 28/10. Change it here to change what triggers the easter egg.
AUTHOR = "Daniele"  # Name shown in the chat; its avatar is the file public/avatars/daniele.* (svg, png or jpg).
GITHUB = "https://github.com/Lombardi2003"
VIDEO = "https://youtu.be/dQw4w9WgXcQ?list=RDdQw4w9WgXcQ"
PAUSE_SECONDS = 0.9  # Between one message and the next, so they arrive as in a conversation.

# Drawn faded behind the text of every message, repeated: computing, Python, sushi, Spike's cactus, Modena.
ICONS = ["💻", "🐍", "🍣", "🌵", "🏎️", "⌨️", "🥟", "🖥️", "🍱", "💛", "🧑‍💻", "💙"]
ICONS_OPACITY = 0.1  # How visible the icons are behind the text: 0 hidden, 1 full.
ICONS_ROUTE = "/vita/easter-egg/icons.svg"  # Where public/style.css takes that drawing from.

# The messages, in order. Markdown as in the rest of the chat; a link written in bold is shown as a large button.
MESSAGES = [
    "**Hai trovato l'easter egg!!!** 🥳\n"
    "Ciao, sono **Daniele Lombardi** e **V.I.T.A.** è il mio progetto di tesi triennale. "
    f"Il codice che hai appena scritto, **{CODE}**, non è un codice fiscale: è il giorno della **mia laurea 🎓**, il **28 ottobre**.",

    "**Qualche numero dietro le quinte**\n"
    "- 10 specialisti che discutono allo stesso tavolo, più un primario che vuole sempre l'ultima parola\n"
    "- 9 modelli messi alla prova nel benchmark, 15 casi ciascuno\n"
    "- più di 240 test automatici, nati perché ogni cosa sistemata ne rompeva un'altra\n"
    "- un numero imprecisato di «limite giornaliero di token raggiunto», di solito alle due di notte\n"
    "- 12 pazienti immaginari in archivio, tutti nati in un comune che non esiste\n"
    "- 5 codici colore, dal rosso al bianco, e nessuno per dire «sto solo scrivendo la tesi»\n"
    "- 1 solo utente, l'Operatore Sanitario, che non ha mai dovuto ricordare una password\n"
    "- 0 diagnosi: soltanto ipotesi preliminari, come la tesi ripete a ogni pagina\n"
    "- 4 anni, 1 tesi e 0 ore di sonno arretrato recuperate\n"
    "- troppe volte «adesso è veramente finito», e questa è l'ultima\n"
    "- 1 codice segreto, e l'hai appena trovato",

    "**Grazie**\n"
    "**A chi mi ha sopportato** in questi anni e **a chi ha fatto finta di capire** cosa fosse un grafo di agenti.\n\n"
    "**A Python** 🐍, che non si è mai lamentato dei miei errori: ci ha pensato l'interprete.\n"
    "**Al Sushi** 🍣, unico vero carburante di questo progetto.\n"
    "**A Modena** 💛💙, tra tortellini, aceto balsamico e motori.\n"
    "**A Spike** 🌵 di Brawl Stars, per tutte le partite «l'ultima e poi studio».\n"
    "**Ai Polaretti** 🧊, senza i quali starei ancora facendo il progetto di Gestione.\n\n"
    f"**✨ Reclami, complimenti e stelline** si lasciano qui: [github.com/Lombardi2003]({GITHUB}).\n "
    "✨Le stelline sono gradite, le segnalazioni di errori un po' meno.",

    "**Un ultimo regalo** 🎁\n"
    "Per chi è arrivato fin qui, il video che riassume meglio questi anni.\n\n"
    f"**[▶ Guardalo qui]({VIDEO})**",
]

# Answer to anything written after the easter egg in the same chat, should the message box be there.
AFTER = "Qui c'è solo l'easter egg. Per un triage, aprire una nuova chat e scrivere il codice fiscale del paziente, così puoi proseguire con il triage."


def is_code(text: str | None) -> bool:
    """True if the message is the easter egg's code and nothing else."""
    return (text or "").strip() == CODE


async def play() -> None:
    """Shows the messages one after the other and keeps the chat out of the history."""
    for position, text in enumerate(MESSAGES):
        if position:
            await asyncio.sleep(PAUSE_SECONDS)
        await cl.Message(content=text, author=AUTHOR).send()
    # Only now: Chainlit stores a new chat while its first message is being answered, and discarding it at once
    # would come before that.
    try:
        await chat_history.discard_chat()
    # The history is a convenience: a failure here changes nothing of what was shown.
    except Exception:
        log.exception("could not discard the easter egg chat")


async def answer_after() -> None:
    """Says that this chat holds only the easter egg."""
    await cl.Message(content=AFTER, author=AUTHOR).send()


def icons_svg(columns: int = 4, cell: int = 64) -> str:
    """The icons as one drawing to repeat behind a message: a grid, every other row shifted, each icon a little turned."""
    turns = (-14, 9, -6, 16)
    rows = -(-len(ICONS) // columns)
    marks = []
    for position, icon in enumerate(ICONS):
        row, column = divmod(position, columns)
        x = cell // 2 + column * cell + (cell // 3 if row % 2 else 0)
        y = cell // 2 + row * cell
        marks.append(f'<text x="{x}" y="{y}" font-size="24" text-anchor="middle" dominant-baseline="central" '
                     f'transform="rotate({turns[position % len(turns)]} {x} {y})">{icon}</text>')
    width, height = columns * cell + cell // 3, rows * cell
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><g opacity="{ICONS_OPACITY}">{"".join(marks)}</g></svg>')


def register_route() -> None:
    """Adds the address of the icons to Chainlit's web server, before Chainlit's own routes: the last of them
    answers every address with the chat page."""
    from chainlit.server import app as server
    from fastapi import Response
    from fastapi.routing import APIRoute

    if any(getattr(route, "path", None) == ICONS_ROUTE for route in server.router.routes):
        return  # The app module is loaded again when Chainlit reloads it.

    async def icons() -> Response:
        """The drawing of the icons."""
        return Response(content=icons_svg(), media_type="image/svg+xml")

    server.router.routes.insert(0, APIRoute(ICONS_ROUTE, icons, methods=["GET"]))
