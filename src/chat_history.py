"""The chat archive: where Chainlit stores the conversations, so they can be reopened from the sidebar."""

from datetime import datetime
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


def create_tables(path=HISTORY_DB) -> None:
    """Creates the archive file and its tables, if they are not there yet."""
    connection = sqlite3.connect(path)
    try:
        for statement in _TABLES:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def build_data_layer(path=HISTORY_DB) -> ChatArchive:
    """The archive Chainlit writes every chat to. Attached photos are not stored: no file storage is configured."""
    create_tables(path)
    log.info("chat archive ready: %s", path)
    return ChatArchive(conninfo=f"sqlite+aiosqlite:///{path.as_posix()}")


def chat_title(card: dict, when: datetime | None = None) -> str | None:
    """The title of a chat in the sidebar: surname, name, day and time; None until the patient has both names."""
    first_name = (card.get("first_name") or "").strip()
    last_name = (card.get("last_name") or "").strip()
    if not (first_name and last_name):
        return None
    return f"{last_name} {first_name} · {(when or datetime.now()).strftime('%d/%m %H:%M')}"


async def rename_chat(title: str) -> bool:
    """Gives the current chat this title, in the archive and in the sidebar; False if there is no archive."""
    data_layer = get_data_layer()
    if data_layer is None:
        return False
    thread_id = cl.context.session.thread_id
    await data_layer.update_thread(thread_id=thread_id, name=title)
    # The same event Chainlit sends when it titles a chat with its first message: the sidebar shows the new title.
    await cl.context.emitter.emit("first_interaction", {"interaction": title, "thread_id": thread_id})
    return True
