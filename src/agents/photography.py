"""Photography node: asks for a photo of the affected area and has the vision model describe it."""

import asyncio
import json
import base64
import io
import mimetypes
import re

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import chainlit as cl
from PIL import Image, ImageOps

from src.state import MedicalState, PatientCard, PhotoAnalysis
from .prompts import PHOTO_PROMPT
from .common import call_with_retry, extract_json, llm_vision
from .authors import Authors
from src.log import get_logger

log = get_logger("photography")

# A refusal in its usual forms, anchored at the start so words containing "no" do not match.
NO_PHOTO_PATTERN = re.compile(
    r"^(no|nessuna|niente|non\s+ho|non\s+serve|non\s+c['’]?\s*[eè]|skip|salta|prosegui|procedi|avanti|senza)\b"
)

# The request shown to the operator.
PHOTO_REQUEST = (
    "È disponibile una foto della zona interessata (ferita, gonfiore, eruzione cutanea…)? "
    "Allegarla, oppure scrivere \"no\" per proseguire senza foto."
)

MAX_IMAGE_BASE64_BYTES = 3_500_000  # The provider rejects images above about 4 MB in base64; this leaves a margin.

# Longest side of the reduced copies, largest first: stop at the first that fits.
RESIZE_STEPS = (2048, 1600, 1280, 1024)

# Formats that can be sent as they are.
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _prepare_image(image_path: str) -> tuple[str, str] | None:
    """(base64, MIME type) to send, or None if the file cannot be opened; the original is never modified."""
    try:
        with open(image_path, "rb") as f:
            raw = f.read()
    except OSError:
        return None

    mime = mimetypes.guess_type(image_path)[0] or ""
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            mime = Image.MIME.get(probe.format, mime)
    except Exception:
        return None

    encoded = base64.b64encode(raw).decode("utf-8")
    # Within the limit and in a supported format: sent unchanged, with its real type.
    if mime in SUPPORTED_IMAGE_TYPES and len(encoded) <= MAX_IMAGE_BASE64_BYTES:
        return encoded, mime

    with Image.open(io.BytesIO(raw)) as original:
        # Otherwise a reduced JPEG copy, with the rotation stored by phones applied.
        img = ImageOps.exif_transpose(original).convert("RGB")
    for side in RESIZE_STEPS:
        copy = img.copy()
        copy.thumbnail((side, side))
        buffer = io.BytesIO()
        copy.save(buffer, format="JPEG", quality=90)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        if len(encoded) <= MAX_IMAGE_BASE64_BYTES:
            log.info("photo reduced for sending (%sx%s -> %sx%s), original untouched", img.width, img.height, copy.width, copy.height)
            return encoded, "image/jpeg"
    return encoded, "image/jpeg"


def _without_photo(card: PatientCard) -> dict:
    """The card with the photo removed, so a failed photo is not analysed again."""
    updated = card.model_dump()
    updated["symptom"]["photo"] = None
    return updated


async def photography_node(state: MedicalState):
    """Requests the photo and stores its description; it never judges severity."""
    last_user = state.triage_history[-1] if state.triage_history else None
    last_text = last_user.content.strip().lower() if last_user and isinstance(last_user, HumanMessage) else ""

    photo: PhotoAnalysis | None = state.patient_card.symptom.photo
    # An attached photo is checked before the text refusal: a caption starting with "no" must not discard it.
    if photo and photo.photo_url:
        image_path = photo.photo_url
        log.info("analysing the photo")

        prepared = _prepare_image(image_path)
        if not prepared:
            msg = "Impossibile aprire l'immagine. Si procede senza foto."
            await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
            return {"patient_card": _without_photo(state.patient_card), "general_history": [AIMessage(content=msg)],
                    "photo_request_shown": True, "next_step": "supervisor"}
        base64_image, mime = prepared

        messages = [
            SystemMessage(content=PHOTO_PROMPT),
            HumanMessage(content=[
                {"type": "text", "text": "Analizza questa immagine clinica e produci il JSON richiesto."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64_image}"}},
            ]),
        ]

        async with cl.Step(name="Analisi foto", type="tool", default_open=False, show_input="text") as step:
            step.input = image_path
            try:
                # The call blocks: run it in a thread, with retries after a temporary error.
                response = await asyncio.to_thread(call_with_retry, llm_vision.invoke, messages)
                step.output = response.content
            except Exception as e:
                step.output = f"Errore durante la chiamata al modello di visione: {e}"
                log.error("vision model call failed: %s", e)
                msg = "Errore durante l'analisi della foto. Si procede senza foto."
                await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
                return {"patient_card": _without_photo(state.patient_card), "general_history": [AIMessage(content=msg)],
                        "photo_request_shown": True, "next_step": "supervisor"}

        try:
            clinical_data = extract_json(response.content)

            lesion_type  = str(clinical_data.get("lesion_type", "")).strip()
            description = str(clinical_data.get("description", "")).strip()

            # An unusable photo is removed and another one is requested.
            if "NON VALUTABILE" in f"{lesion_type} {description}".upper() or not (lesion_type or description):
                log.info("photo not assessable: another one requested")
                msg = "Foto non valutabile: allegarne un'altra oppure scrivere \"no\" per proseguire senza foto."
                await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
                return {
                    "patient_card":        _without_photo(state.patient_card),
                    "general_history":     [AIMessage(content=msg)],
                    "triage_history":      [AIMessage(content=msg)],
                    "photo_request_shown": True,
                    "next_step":           "photography",
                }

            photo_analysis = PhotoAnalysis(photo_url=image_path, description=description, injury_type=lesion_type)

            updated_card = state.patient_card.model_dump()
            updated_card["symptom"]["photo"] = photo_analysis.model_dump()
            log.info("photo described: %s", lesion_type)
            log.debug("card: %s", json.dumps(updated_card, ensure_ascii=False))
            summary = "**Foto**\n" + " · ".join(
                part for part in (f"**Tipo** {lesion_type}" if lesion_type else "", f"**Descrizione** {description}" if description else "") if part
            )
            await cl.Message(content=summary, author=Authors.PHOTOGRAPHY).send()

            return {
                "patient_card":        updated_card,
                "general_history":     [AIMessage(content=f"Foto analizzata: {lesion_type}. {description}")],
                "photo_request_shown": True,
                "next_step":           "supervisor",
            }

        except Exception as e:
            msg = "Errore durante l'analisi della foto. Si procede senza foto."
            log.error("unusable vision answer: %s", e)
            await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
            return {"patient_card": _without_photo(state.patient_card), "general_history": [AIMessage(content=msg)],
                    "photo_request_shown": True, "next_step": "supervisor"}

    # First pass, right after the symptoms: ask for the photo.
    if not state.photo_request_shown:
        log.info("photo requested (first pass)")
        await cl.Message(content=PHOTO_REQUEST, author=Authors.PHOTOGRAPHY).send()
        return {
            "general_history":     [AIMessage(content=PHOTO_REQUEST)],
            "triage_history":      [AIMessage(content=PHOTO_REQUEST)],
            "photo_request_shown": True,
            "next_step":           "photography",
        }

    # Explicit refusal: go on without a photo.
    if NO_PHOTO_PATTERN.match(last_text):
        msg = "Nessuna foto: si procede con la sola descrizione dei sintomi."
        await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
        return {
            "general_history": [AIMessage(content=msg)],
            "next_step": "supervisor",
        }

    await cl.Message(content=PHOTO_REQUEST, author=Authors.PHOTOGRAPHY).send()
    return {
        "general_history": [AIMessage(content=PHOTO_REQUEST)],
        "triage_history":  [AIMessage(content=PHOTO_REQUEST)],
        "next_step": "photography",
    }
