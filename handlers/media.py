"""Handlers de fotos y documentos: descarga, pasa ruta a Claude."""
import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from core.config import DOWNLOAD_DIR
from core.runner import cleanup_file, run_claude
from core.session import get_session
from handlers.commands import is_authorized

logger = logging.getLogger(__name__)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    local_path = os.path.join(DOWNLOAD_DIR, f"photo_{update.message.message_id}.jpg")
    await file.download_to_drive(local_path)

    caption = (update.message.caption or "Analiza esta imagen.").strip()
    prompt = (
        f"{caption}\n\n"
        f"La imagen está en disco en: {local_path}\n"
        f"Léela con la herramienta Read y descríbela / contesta a la petición."
    )
    try:
        await run_claude(update, context, session, prompt, source="text")
    finally:
        cleanup_file(local_path)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)

    doc = update.message.document
    if doc is None:
        return
    file = await context.bot.get_file(doc.file_id)
    safe_name = doc.file_name or f"doc_{update.message.message_id}"
    local_path = os.path.join(DOWNLOAD_DIR, f"{update.message.message_id}_{safe_name}")
    await file.download_to_drive(local_path)

    caption = (update.message.caption or f"Procesa este documento: {safe_name}").strip()
    prompt = (
        f"{caption}\n\n"
        f"El documento está en disco en: {local_path}\n"
        f"Ábrelo con la herramienta Read y haz lo que te pido."
    )
    try:
        await run_claude(update, context, session, prompt, source="text")
    finally:
        cleanup_file(local_path)
