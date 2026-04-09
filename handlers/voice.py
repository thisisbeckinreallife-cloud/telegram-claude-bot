"""Handler de mensajes de voz: descarga, STT, luego delega a run_claude."""
import logging
import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from core.audio import openai_client, transcribe_audio
from core.config import DOWNLOAD_DIR
from core.runner import run_claude
from core.session import get_session
from core.worker import enqueue_task
from handlers.commands import is_authorized
from handlers.text import handle_pending_decision

logger = logging.getLogger(__name__)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)

    if openai_client is None:
        await update.message.reply_text(
            "⚠️ OPENAI_API_KEY no configurada — no puedo transcribir audio."
        )
        return

    voice = update.message.voice or update.message.audio
    if voice is None:
        return

    await update.message.chat.send_action("typing")

    file = await context.bot.get_file(voice.file_id)
    suffix = ".ogg" if update.message.voice else ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, dir=DOWNLOAD_DIR, delete=False) as tmp:
        local_path = tmp.name
    try:
        await file.download_to_drive(local_path)
        text = await transcribe_audio(local_path)
    except Exception as exc:
        logger.exception("Error transcribiendo")
        await update.message.reply_text(f"⚠️ Error transcribiendo: {exc}")
        return
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass

    if not text.strip():
        await update.message.reply_text("(audio vacío)")
        return

    await update.message.reply_text(f"🎙 «{text}»")

    if await handle_pending_decision(update, session, text):
        return

    await update.message.reply_text("⏳ Tarea recibida, procesando...")
    await enqueue_task(
        session.chat_id,
        run_claude,
        update, context, session, text, "voice",
    )
