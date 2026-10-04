"""What the round table shares: specialist names, limits, urgency codes, the transcript and the paediatric note."""

import re

from src.state import PatientCard, RoundTableEntry
from .prompts import ALL_SPECIALISTS

MAX_TOTAL_TURNS = 12  # Emergency brake: the table always reaches the primary.

MAX_FAILED_TURNS = 2  # Unreadable or failed turns before a specialist is moved on instead of being called again.

MAX_RECRUITED_SPECIALISTS = 1  # Colleagues that can be brought in during the discussion.

MAX_SPEAKS_PER_SPECIALIST = 3  # Turns per specialist (verification excluded) before being moved on.

# Role (also the node name) -> name shown in the chat.
SPECIALIST_DISPLAY_NAMES = {
    "cardiologist": "Cardiologia",
    "neurologist": "Neurologia",
    "dermatologist": "Dermatologia",
    "orthopedist": "Ortopedia",
    "gastroenterologist": "Gastroenterologia",
    "pulmonologist": "Pneumologia",
    "ent": "Otorinolaringoiatria",
    "ophthalmologist": "Oftalmologia",
    "urologist": "Urologia",
    "general_practitioner": "Medicina",
}

# Other names the model uses for a colleague.
_ITALIAN_DOCTOR_NAMES = {
    "cardiologist": ["cardiologo", "cardiologa"],
    "neurologist": ["neurologo", "neurologa"],
    "dermatologist": ["dermatologo", "dermatologa"],
    "orthopedist": ["ortopedico", "ortopedica", "ortopedia e traumatologia", "traumatologo"],
    "gastroenterologist": ["gastroenterologo", "gastroenterologa"],
    "pulmonologist": ["pneumologo", "pneumologa"],
    "ent": ["otorinolaringoiatra", "otorino", "orl"],
    "ophthalmologist": ["oftalmologo", "oftalmologa", "oculista", "oculistica"],
    "urologist": ["urologo", "urologa"],
    "general_practitioner": ["medico di base", "medico generico", "medico di medicina generale",
                             "medicina generale", "mmg"],
}

# Every accepted name -> role.
_DISPLAY_NAME_TO_ROLE = {name.lower(): role for role, name in SPECIALIST_DISPLAY_NAMES.items()}

_DISPLAY_NAME_TO_ROLE.update(
    {name: role for role, names in _ITALIAN_DOCTOR_NAMES.items() for name in names}
)

# Articles and titles dropped before matching a name.
_NAME_PREFIX = re.compile(r"^(il|lo|la|l'|al|allo|alla|dott\.?|dr\.?|dottor|dottoressa)\s*", re.IGNORECASE)


def _role_from_name(raw) -> str | None:
    """The role meant by a name written by the model, or None if it is not one of the ten."""
    text = str(raw or "").strip().lower().rstrip(".,;:!?")
    text = _NAME_PREFIX.sub("", text).strip()
    if text in ALL_SPECIALISTS:
        return text
    return _DISPLAY_NAME_TO_ROLE.get(text)


# Italian triage colour codes, most urgent first.
URGENCY_LEVELS = ["ROSSO", "ARANCIONE", "AZZURRO", "VERDE", "BIANCO"]


def _parse_urgency(value) -> str | None:
    """One of the five codes, or None if missing or not recognised."""
    text = str(value or "").strip().upper()
    return text if text in URGENCY_LEVELS else None


# Longer entries are cut in the transcript (not in the chat) to keep the prompt small.
MAX_ENTRY_CHARS_IN_TRANSCRIPT = 1200


def _format_round_table(entries: list[RoundTableEntry]) -> str:
    """The whole discussion so far, as text for the prompt."""
    if not entries:
        return "Nessun intervento precedente - sei il primo a parlare."
    lines = []
    for e in entries:
        content = e.content
        if len(content) > MAX_ENTRY_CHARS_IN_TRANSCRIPT:
            content = content[:MAX_ENTRY_CHARS_IN_TRANSCRIPT].rsplit(" ", 1)[0] + " […]"
        speaker = SPECIALIST_DISPLAY_NAMES.get(e.author, e.author)
        recipient = SPECIALIST_DISPLAY_NAMES.get(e.to, e.to) if e.to else "tutti"
        tag = ", ".join(t for t in (
            "GIRO DI VERIFICA" if e.verification else "",
            e.azione.upper(),
            f"urgenza {e.urgency}" if e.urgency else "",
        ) if t)
        action_tag = f" [{tag}]" if tag else ""
        lines.append(f"{speaker} (a {recipient}){action_tag}: {content}")
    return "\n".join(lines)


def _format_urgencies(entries: list[RoundTableEntry]) -> str:
    """Every urgency code stated at the table, with a warning if they differ."""
    lines = []
    for position, e in enumerate(entries, 1):
        if e.urgency:
            author_name = SPECIALIST_DISPLAY_NAMES.get(e.author, e.author)
            lines.append(f"- {e.urgency}: {author_name} (intervento {position}, {e.azione})")
    if not lines:
        return "Nessuna urgenza espressa esplicitamente al tavolo."
    levels = {e.urgency for e in entries if e.urgency}
    if len(levels) > 1:
        highest = min(levels, key=URGENCY_LEVELS.index)
        lines.append(f"ATTENZIONE: il tavolo NON e' stato concorde sull'urgenza - la piu' alta espressa e' {highest}.")
    return "\n".join(lines)


def _pediatric_note(card: PatientCard) -> str:
    """A note for the prompt when the patient is a minor (the guidelines are for adults), else ""."""
    age = card.age.strip().lower()
    match = re.match(r"(\d{1,3})", age)
    if not match:
        return ""
    in_months_or_days = any(u in age for u in ("mes", "giorn", "settiman"))
    if not in_months_or_days and int(match.group(1)) >= 18:
        return ""
    age_text = age if in_months_or_days else f"{match.group(1)} anni"
    return (
        f"PAZIENTE PEDIATRICO ({age_text}): le linee guida recuperate sono pensate per adulti. Tienine conto: "
        "criteri di gravita', esami, dosaggi e codici di urgenza possono essere diversi in eta' pediatrica; "
        "segnala quando serve una valutazione pediatrica."
    )
