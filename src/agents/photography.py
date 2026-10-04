# Nodo della foto: chiede la foto della zona interessata e la fa descrivere al
# modello di visione.
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


# Riconosce un rifiuto della foto anche con formulazioni diverse dal solo "no"
# esatto (osservato altrove nel progetto: un confronto esatto sull'intero
# messaggio e' troppo fragile, es. "no grazie non ho foto" non veniva
# riconosciuto) - ancorato all'inizio del messaggio per evitare falsi positivi
# su parole comuni che contengono "no" (es. "sono", "buono").
NO_PHOTO_PATTERN = re.compile(
    r"^(no|nessuna|niente|non\s+ho|non\s+serve|non\s+c['’]?\s*[eè]|skip|salta|prosegui|procedi|avanti|senza)\b"
)


PHOTO_REQUEST = (
    "È disponibile una foto della zona interessata (ferita, gonfiore, eruzione cutanea…)? "
    "Allegarla, oppure scrivere \"no\" per proseguire senza foto."
)


# Groq accetta immagini in base64 fino a circa 4 MB: sopra, la chiamata al
# modello di visione fallisce (una foto scattata col telefono li supera
# spesso). Margine sotto il limite reale.
MAX_IMAGE_BASE64_BYTES = 3_500_000


# Lato lungo delle copie ridotte, dal piu' grande al piu' piccolo: si scende
# solo finche' serve, per non perdere dettaglio utile all'analisi.
RESIZE_STEPS = (2048, 1600, 1280, 1024)


SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _prepare_image(image_path: str) -> tuple[str, str] | None:
    """(base64, tipo MIME) dell'immagine da mandare al modello di visione, o
    None se il file non si apre.

    Il file originale non viene mai modificato. Se e' gia' entro il limite e
    in un formato supportato parte cosi' com'e', con il suo tipo vero (prima
    era sempre dichiarato JPEG, anche per un PNG). Solo se e' troppo grande
    (o in un formato non supportato) se ne manda una COPIA ridotta in JPEG,
    con il lato lungo il piu' grande possibile entro il limite.
    """
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
        return None  # non e' un'immagine leggibile

    encoded = base64.b64encode(raw).decode("utf-8")
    if mime in SUPPORTED_IMAGE_TYPES and len(encoded) <= MAX_IMAGE_BASE64_BYTES:
        return encoded, mime

    with Image.open(io.BytesIO(raw)) as original:
        # Rotazione salvata nei metadati (tipica delle foto da telefono):
        # applicata alla copia, cosi' il modello vede la foto dritta.
        img = ImageOps.exif_transpose(original).convert("RGB")
    for side in RESIZE_STEPS:
        copy = img.copy()
        copy.thumbnail((side, side))
        buffer = io.BytesIO()
        copy.save(buffer, format="JPEG", quality=90)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        if len(encoded) <= MAX_IMAGE_BASE64_BYTES:
            print(f"📸 PHOTOGRAPHY: foto ridotta per l'invio ({img.width}x{img.height} -> {copy.width}x{copy.height}), originale invariato")
            return encoded, "image/jpeg"
    return encoded, "image/jpeg"  # ultima riduzione, anche se ancora grande


def _without_photo(card: PatientCard) -> dict:
    """Scheda senza foto: dopo un'analisi non riuscita o non valutabile la foto
    va tolta, altrimenti al messaggio successivo verrebbe analizzata di nuovo
    (o arriverebbe agli specialisti come foto senza descrizione)."""
    updated = card.model_dump()
    updated["symptom"]["photo"] = None
    return updated


# Nodo per l'analisi dell'immagine del danno
async def photography_node(state: MedicalState):
    """Compito puramente osservativo: descrive cosa mostra la foto (tipo di
    lesione, descrizione clinica), senza esprimere un giudizio di gravita' -
    quella valutazione richiede il quadro clinico completo ed e' compito dei
    nodi successivi (supervisore/specialisti/primario), non di chi vede solo
    un'immagine isolata."""

    last_user = state.triage_history[-1] if state.triage_history else None
    ultimo_testo = last_user.content.strip().lower() if last_user and isinstance(last_user, HumanMessage) else ""

    # 1. Foto presente nello stato → analizza (controllo PRIMA del rifiuto testuale:
    # una foto davvero allegata e' un segnale inequivocabile, non deve essere
    # scartata solo perche' la didascalia che la accompagna inizia per caso con
    # una parola tipo "no" - es. "No, non è preoccupante ma eccola comunque",
    # osservato in test reale). Vale anche al primo passaggio, se la foto era
    # gia' stata allegata prima.
    photo: PhotoAnalysis | None = state.patient_card.symptom.photo
    if photo and photo.photo_url:
        image_path = photo.photo_url
        print(f"📸 PHOTOGRAPHY: analisi immagine → {image_path}")

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
                # Stessa ragione di asyncio.to_thread altrove in questo file:
                # .invoke() e' sincrona/bloccante, non va chiamata direttamente
                # dentro una funzione async. call_with_retry: nuovi tentativi
                # dopo un errore temporaneo dell'API (vedi common.py).
                response = await asyncio.to_thread(call_with_retry, llm_vision.invoke, messages)
                step.output = response.content
            except Exception as e:
                step.output = f"Errore durante la chiamata al modello di visione: {e}"
                print(f"📸 PHOTOGRAPHY: errore chiamata modello → {e}")
                msg = "Errore durante l'analisi della foto. Si procede senza foto."
                await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
                return {"patient_card": _without_photo(state.patient_card), "general_history": [AIMessage(content=msg)],
                        "photo_request_shown": True, "next_step": "supervisor"}

        try:
            # extract_json gestisce anche i modelli "thinking" (come quello di
            # visione attuale) che antepongono al JSON un blocco <think>...</think>
            # (vedi src/llm/calls.py).
            clinical_data = extract_json(response.content)

            tipo  = str(clinical_data.get("lesion_type", "")).strip()
            descr = str(clinical_data.get("description", "")).strip()

            # Foto non chiara o senza lesioni (vedi PHOTO_PROMPT): se ne chiede
            # un'altra invece di proseguire come se l'analisi fosse riuscita.
            if "NON VALUTABILE" in f"{tipo} {descr}".upper() or not (tipo or descr):
                print("📸 PHOTOGRAPHY → foto non valutabile")
                msg = "Foto non valutabile: allegarne un'altra oppure scrivere \"no\" per proseguire senza foto."
                await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
                return {
                    "patient_card":        _without_photo(state.patient_card),
                    "general_history":     [AIMessage(content=msg)],
                    "triage_history":      [AIMessage(content=msg)],
                    "photo_request_shown": True,
                    "next_step":           "photography",
                }

            # Rete di sicurezza: validiamo tramite il modello Pydantic prima di
            # salvare, come gia' fatto per intake/reviewer - se il modello di
            # visione restituisce qualcosa fuori schema, non ci fidiamo alla cieca.
            photo_analysis = PhotoAnalysis(photo_url=image_path, description=descr, injury_type=tipo)

            updated_card = state.patient_card.model_dump()
            updated_card["symptom"]["photo"] = photo_analysis.model_dump()
            print(f"📸 PHOTOGRAPHY → {tipo}")
            print(f"   Card: {json.dumps(updated_card, ensure_ascii=False)}")
            # Stesso stile delle schede di intake/reviewer. Si mostra anche la
            # descrizione, non solo il tipo: e' quello che il modello ha
            # davvero osservato (margini, colore, sanguinamento, ...).
            riepilogo = "**Foto**\n" + " · ".join(
                part for part in (f"**Tipo** {tipo}" if tipo else "", f"**Descrizione** {descr}" if descr else "") if part
            )
            await cl.Message(content=riepilogo, author=Authors.PHOTOGRAPHY).send()

            return {
                "patient_card":        updated_card,
                "general_history":     [AIMessage(content=f"Foto analizzata: {tipo}. {descr}")],
                "photo_request_shown": True,
                "next_step":           "supervisor",
            }

        except Exception as e:
            # JSON illeggibile, errore di validazione di PhotoAnalysis o
            # qualunque altro imprevisto nella lettura della risposta.
            msg = "Errore durante l'analisi della foto. Si procede senza foto."
            print(f"📸 PHOTOGRAPHY: errore nella risposta → {e}")
            await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
            return {"patient_card": _without_photo(state.patient_card), "general_history": [AIMessage(content=msg)],
                    "photo_request_shown": True, "next_step": "supervisor"}

    # 2. Primo passaggio, appena confermati i sintomi (senza pausa, vedi
    # graph.py): l'operatore non ha ancora risposto, si chiede la foto.
    if not state.photo_request_shown:
        print("📸 PHOTOGRAPHY → richiesta foto (primo passaggio)")
        await cl.Message(content=PHOTO_REQUEST, author=Authors.PHOTOGRAPHY).send()
        return {
            "general_history":     [AIMessage(content=PHOTO_REQUEST)],
            "triage_history":      [AIMessage(content=PHOTO_REQUEST)],
            "photo_request_shown": True,
            "next_step":           "photography",
        }

    # 3. Nessuna foto allegata: l'operatore ha rifiutato esplicitamente → salta
    if NO_PHOTO_PATTERN.match(ultimo_testo):
        msg = "Nessuna foto: si procede con la sola descrizione dei sintomi."
        await cl.Message(content=msg, author=Authors.PHOTOGRAPHY).send()
        return {
            "general_history": [AIMessage(content=msg)],
            "next_step": "supervisor",
        }

    # 4. Nessuna foto e nessun rifiuto → si richiede
    await cl.Message(content=PHOTO_REQUEST, author=Authors.PHOTOGRAPHY).send()
    return {
        "general_history": [AIMessage(content=PHOTO_REQUEST)],
        "triage_history":  [AIMessage(content=PHOTO_REQUEST)],
        "next_step": "photography",  # user leggerà questo e tornerà qui
    }
