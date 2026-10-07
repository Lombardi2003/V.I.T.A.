"""The settings panel's logic: which models can be chosen, and changing the model while the app runs."""

import httpx

import src.agents.common as common
import src.agents.photography as photography
from src.llm import factory
from src.llm.providers import Model, Models, Provider
from src.log import get_logger
from src.settings import get_settings

log = get_logger("panel")

VISION_ONLY = {Models.QWEN_27B, Models.MOONDREAM}  # Vision models that are not offered as text models.
LOCAL_CHECK_TIMEOUT_SECONDS = 3  # Longest wait to see whether a local server answers.

# The models the app is using now: they start as the ones chosen in factory.py and change only from the panel.
current = {"text": factory.TEXT_MODEL, "vision": factory.VISION_MODEL}


def label(model: Model) -> str:
    """The name shown in the panel: the model without the provider's prefix."""
    return model.name.split("/")[-1].removesuffix(":latest")


def provider_label(provider: Provider) -> str:
    """The provider's name as shown in the panel."""
    return provider.name.capitalize()


def _has_key(provider: Provider) -> bool:
    """True if the provider needs no key, or its key (and its account id, when it has one) is set."""
    fields = [field for field in (provider.key_field, provider.account_field) if field]
    return all(getattr(get_settings(), field) for field in fields)


def _of_kind(kind: str) -> list[Model]:
    """Every model of the catalogue that can be a text model, or a vision model."""
    catalogue = [m for m in vars(Models).values() if isinstance(m, Model)]
    return [m for m in catalogue if (m.vision if kind == "vision" else m not in VISION_ONLY)]


def choices(kind: str) -> list[Model]:
    """The models that can be chosen as text or vision model: those whose provider has its key set, or needs none."""
    usable = [m for m in _of_kind(kind) if _has_key(m.provider)]
    # The model in use is always listed, so the panel can show it.
    return usable if current[kind] in usable else [current[kind]] + usable


def missing_keys_note(kind: str) -> str:
    """A line naming the models left out because their provider's key is not set, and how to set it; "" if none."""
    missing = {}
    for model in _of_kind(kind):
        if not _has_key(model.provider) and model != current[kind]:
            missing.setdefault(model.provider, []).append(label(model))
    return " ".join(
        f"Non in elenco: {', '.join(labels)} (manca la chiave {provider_label(provider)}: "
        f"python scripts/setup_env.py --key {provider.key_field})."
        for provider, labels in missing.items())


def _local_problem(model: Model) -> str | None:
    """Why a local model cannot be used right now, or None; asks the local server for its models."""
    try:
        response = httpx.get(model.provider.base_url + "/models", timeout=LOCAL_CHECK_TIMEOUT_SECONDS)
        names = [m.get("id", "") for m in response.json().get("data", [])]
    except Exception:
        return f"il servizio locale {provider_label(model.provider)} non risponde: va avviato"
    if not any(name == model.name or name.split(":")[0] == model.name.split(":")[0] for name in names):
        return f"il modello non è installato in {provider_label(model.provider)}"
    return None


def _apply(kind: str, model: Model) -> None:
    """Replaces the client the agents use; they read it at every call, so the change is immediate."""
    client = factory.build_llm(model)
    if kind == "text":
        common.llm = client
    else:
        common.llm_vision = client
        photography.llm_vision = client
    current[kind] = model
    log.info("%s model changed from the panel: %s", kind, factory.describe_llm(client))


def choose(kind: str, chosen_label: str) -> str | None:
    """Changes the text or vision model to the one with this label; returns why it could not, or None when done."""
    model = next((m for m in choices(kind) if label(m) == chosen_label), None)
    if model is None:
        return f"Modello non disponibile: {chosen_label}."
    if model == current[kind]:
        return None
    if not model.provider.key_field:
        problem = _local_problem(model)
        if problem:
            return f"{label(model)} non selezionato: {problem}. Resta attivo {label(current[kind])}."
    try:
        _apply(kind, model)
    except Exception as e:
        log.warning("model change failed: %s", e)
        return f"{label(model)} non selezionato. Resta attivo {label(current[kind])}."
    return None
