"""The chat archive: where Chainlit stores the conversations, so they can be reopened from the sidebar."""

import asyncio
from datetime import datetime, timezone
import sqlite3
import typing

import chainlit as cl
from chainlit.data import get_data_layer
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.step import StepDict

from src.log import get_logger
from src.settings import PROJECT_ROOT

log = get_logger("history")

HISTORY_DB = PROJECT_ROOT / "data" / "chat_history.db"  # Kept out of version control: it holds what was said in the chats.
OPERATOR = "operatore"  # The single user every visitor is signed in as: no login page. The chats belong to this name.
OPERATOR_NAME = "Operatore Sanitario"  # The name shown in the user menu.
NEW_CHAT_LABEL = "Nuovo triage"  # Title of a chat whose patient card is not confirmed yet.
TITLE_REPEAT_SECONDS = 1.5  # Chainlit sends the sidebar its own title for a new chat around the same time: ours is sent again after it.

# Chainlit's archive expects these tables. Its own schema is written for PostgreSQL; this is the SQLite equivalent.
_STEP_TYPES = {"id": "TEXT PRIMARY KEY", "streaming": "BOOLEAN", "waitForAnswer": "BOOLEAN", "isError": "BOOLEAN",
               "defaultOpen": "BOOLEAN", "autoCollapse": "BOOLEAN", "indent": "INTEGER"}
_STEP_COLUMNS = sorted(set(typing.get_type_hints(StepDict)) | set(_STEP_TYPES) | {"tags", "command"})
_TABLES = [
    'CREATE TABLE IF NOT EXISTS users ("id" TEXT PRIMARY KEY, "identifier" TEXT NOT NULL UNIQUE, '
    '"metadata" TEXT NOT NULL, "createdAt" TEXT)',
    'CREATE TABLE IF NOT EXISTS threads ("id" TEXT PRIMARY KEY, "createdAt" TEXT, "name" TEXT, "userId" TEXT, '
    '"userIdentifier" TEXT, "tags" TEXT, "metadata" TEXT)',
    "CREATE TABLE IF NOT EXISTS steps (" + ", ".join(f'"{c}" {_STEP_TYPES.get(c, "TEXT")}' for c in _STEP_COLUMNS) + ")",
    'CREATE TABLE IF NOT EXISTS elements ("id" TEXT PRIMARY KEY, "threadId" TEXT, "type" TEXT, "url" TEXT, '
    '"chainlitKey" TEXT, "name" TEXT, "display" TEXT, "objectKey" TEXT, "size" TEXT, "page" INTEGER, "language" TEXT, '
    '"forId" TEXT, "mime" TEXT, "props" TEXT, "autoPlay" BOOLEAN, "playerConfig" TEXT)',
    'CREATE TABLE IF NOT EXISTS feedbacks ("id" TEXT PRIMARY KEY, "forId" TEXT, "threadId" TEXT, "value" INTEGER, '
    '"comment" TEXT)',
]


class ChatArchive(SQLAlchemyDataLayer):
    """Chainlit's SQL archive, with the user's display name: the archive does not store it, so it is added when the user is read."""

    async def get_user(self, identifier: str):
        """The stored user, with the name to show."""
        user = await super().get_user(identifier)
        if user is not None and user.identifier == OPERATOR:
            user.display_name = OPERATOR_NAME
        return user

    async def update_thread(self, thread_id, name=None, user_id=None, metadata=None, tags=None):
        """Chainlit names a chat after its first message, here the fiscal code: that name is never stored. A chat
        without a title gets the neutral one, a titled chat keeps its own; only set_title changes a title."""
        if name is not None:
            stored = await self.execute_sql('SELECT "name" FROM threads WHERE "id" = :id', {"id": thread_id})
            titled = isinstance(stored, list) and bool(stored) and bool(stored[0].get("name"))
            name = None if titled else new_chat_title()
        await super().update_thread(thread_id, name=name, user_id=user_id, metadata=metadata, tags=tags)

    async def set_title(self, thread_id: str, title: str) -> None:
        """Gives a chat its title: the one way a title is written."""
        await super().update_thread(thread_id, name=title)

    async def get_current_timestamp(self) -> str:
        """The current time in UTC. Chainlit's own writes the local time marked as UTC: east of Greenwich a chat started
        late in the evening was dated the next day, and the sidebar listed it outside "today"."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def create_tables(path=HISTORY_DB) -> None:
    """Creates the archive file and its tables, if they are not there yet, and clears the leftovers of deleted chats."""
    connection = sqlite3.connect(path)
    try:
        for statement in _TABLES:
            connection.execute(statement)
        # Deleting the chat that is open leaves a row without owner when the session closes: it can never be shown.
        connection.execute('DELETE FROM steps WHERE "threadId" IN (SELECT "id" FROM threads WHERE "userId" IS NULL)')
        connection.execute('DELETE FROM threads WHERE "userId" IS NULL')
        connection.commit()
    finally:
        connection.close()


def build_data_layer(path=HISTORY_DB) -> ChatArchive:
    """The archive Chainlit writes every chat to. Attached photos are not stored: no file storage is configured."""
    create_tables(path)
    log.info("chat archive ready: %s", path)
    return ChatArchive(conninfo=f"sqlite+aiosqlite:///{path.as_posix()}")


def _time_label(when: datetime | None) -> str:
    """Day and time as shown in a chat title."""
    return (when or datetime.now()).strftime("%d/%m %H:%M")


def new_chat_title(when: datetime | None = None) -> str:
    """The title a chat has from its first message: neutral, so the sidebar never shows the fiscal code typed first."""
    return f"{NEW_CHAT_LABEL} · {_time_label(when)}"


def chat_title(card: dict, when: datetime | None = None) -> str | None:
    """The title of a chat once the card is confirmed: surname, name, day and time; None without both names."""
    first_name = (card.get("first_name") or "").strip()
    last_name = (card.get("last_name") or "").strip()
    if not (first_name and last_name):
        return None
    return f"{last_name} {first_name} · {_time_label(when)}"


async def rename_chat(title: str) -> bool:
    """Gives the current chat this title, in the archive and in the sidebar; False if there is no archive."""
    data_layer = get_data_layer()
    if data_layer is None:
        return False
    thread_id = cl.context.session.thread_id
    await data_layer.set_title(thread_id, title)
    emitter = cl.context.emitter

    async def show(delay: float = 0) -> None:
        """Tells the sidebar the title, with the event Chainlit itself uses to title a chat."""
        await asyncio.sleep(delay)
        await emitter.emit("first_interaction", {"interaction": title, "thread_id": thread_id})

    await show()
    asyncio.create_task(show(TITLE_REPEAT_SECONDS))
    return True
