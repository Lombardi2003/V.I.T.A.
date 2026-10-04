"""Shared by every agent: the model clients, the database and helpers that tidy a model's answer."""

from src.database import MedicalDatabase
from src.settings import get_settings
from src.llm import call_with_retry, describe_llm, extract_json, get_llm, stream_text
from src.log import get_logger

log = get_logger("models")


def stream_response(prompt_current_card, llm_client=None):
    """The model's full answer to this prompt (text model unless another client is given)."""
    return stream_text(prompt_current_card, llm_client or llm)


def as_list(value) -> list:
    """A list, even if the model wrote a single text instead."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def is_yes(value) -> bool:
    """True for true, "si", "sì", "yes" in any form."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "si", "sì", "si'", "yes"}


def is_no(value) -> bool:
    """True for false, "no"."""
    if isinstance(value, bool):
        return not value
    return str(value).strip().lower() in {"false", "no"}


def as_text(value) -> str:
    """Plain text, even if the model wrote a list or an object."""
    if value is None:
        return ""
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return ", ".join(t for t in (as_text(v) for v in value) if t)
    return str(value).strip()


def _mentions(text: str, keywords: list[str]) -> bool:
    """True if the text contains one of the keywords: a check that does not depend on the model."""
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


settings = get_settings()  # Keys and temperature from .env.

llm = get_llm()  # Text model, used by every text agent.
llm_vision = get_llm(vision=True)  # Vision model, used for the photo.

log.info("active models: text = %s | vision = %s", describe_llm(llm), describe_llm(llm_vision))

mdb = MedicalDatabase()  # Patient database.
