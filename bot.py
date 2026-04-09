"""Telegram bot que delega cada mensaje a Claude vía claude-agent-sdk.

Funciones:
- Auto-routing del modelo (haiku / sonnet / opus) según complejidad.
- Pensamiento extendido automático cuando la tarea lo requiere.
- Memoria CAG: lee todos los .md de memory/knowledge/ en el system prompt.
- Sesión persistente por chat (memoria entre mensajes y entre reinicios).
- Texto, voz (STT con Whisper), imágenes y documentos.
- Respuesta en voz si el usuario envió voz, o si fuerza con /voice on.
- Confirmación SI/NO por Telegram cuando /safe on.
- Comandos: /start /pwd /cd /reset /voice /safe /think /model
"""
import asyncio
import glob
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ThinkingConfigEnabled,
    ToolPermissionContext,
)
from dotenv import load_dotenv
from openai import AsyncOpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.config import (  # noqa: F401  — import side effects
    ALLOWED_USER_ID,
    DEFAULT_WORKING_DIR,
    OPENAI_API_KEY,
    TTS_VOICE,
    TTS_MODEL,
    STT_MODEL,
    PROJECT_DIR,
    KNOWLEDGE_DIR,
    SESSIONS_FILE,
    GLOBAL_CLAUDE_MD,
    DOWNLOAD_DIR,
)

from core.routing import (
    MODEL_HAIKU,
    MODEL_SONNET,
    MODEL_OPUS,
    DEFAULT_MODEL,
    MODEL_NAME_MAP,
    route_prompt,
    apply_routing,
)

from core.session import (
    ChatSession,
    SESSIONS,
    SESSION_LOCKS,
    SESSIONS_MAP,
    get_session,
    get_session_lock,
    load_sessions_map,
    save_sessions_map,
    get_stored_session_id,
    set_stored_session_id,
    clear_stored_session_id,
)

from core.system_prompt import (
    read_file_safe,
    load_knowledge_blocks,
    build_system_prompt,
)

from core.audio import openai_client, transcribe_audio, synthesize_voice

from handlers.permissions import SAFE_TOOLS, make_can_use_tool

from core.runner import (
    ensure_client,
    close_session,
    close_session_unlocked,
    typing_indicator_loop,
    cleanup_file,
    send_reply,
    run_claude,
)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def is_authorized(update: Update) -> bool:
    user = update.effective_user
    if user is None or user.id != ALLOWED_USER_ID:
        logger.warning("Mensaje rechazado de user_id=%s", user.id if user else None)
        return False
    return True


# ---------- Comandos ---------- #


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "Bot listo. Modelo auto-ruteado (haiku/sonnet/opus) + memoria CAG persistente.\n\n"
        "Puedes enviar:\n"
        "• Texto, audios, fotos, documentos\n\n"
        "Comandos:\n"
        "/cd <ruta> – cambia carpeta de trabajo\n"
        "/pwd – carpeta actual\n"
        "/reset – borra memoria de la conversación actual\n"
        "/voice on|off|auto – modo de respuesta por voz\n"
        "/safe on|off – confirmación manual de herramientas\n"
        "/model auto|haiku|sonnet|opus – modelo (auto = router decide)\n"
        "/think – estado de pensamiento extendido\n"
        "/cost – coste acumulado de esta sesión"
    )


async def cmd_pwd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)
    await update.message.reply_text(f"cwd: {session.cwd}")


async def cmd_cd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Uso: /cd <ruta>")
        return
    new_path = os.path.expanduser(" ".join(context.args))
    if not os.path.isdir(new_path):
        await update.message.reply_text(f"❌ No existe: {new_path}")
        return
    session = get_session(update.effective_chat.id)
    await close_session(session)
    session.cwd = new_path
    await update.message.reply_text(f"✅ cwd → {new_path}\n(Sesión reabierta en la nueva carpeta)")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)
    await close_session(session)
    session.last_session_id = None
    clear_stored_session_id(session.chat_id)
    await update.message.reply_text(
        "✅ Sesión reiniciada (memoria CAG en memory/knowledge/ NO se ha tocado)"
    )


async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text(
            f"Modo voz actual: {session.voice_mode}\nUso: /voice on|off|auto"
        )
        return
    mode = context.args[0].lower()
    if mode not in ("on", "off", "auto"):
        await update.message.reply_text("Uso: /voice on|off|auto")
        return
    session.voice_mode = mode
    await update.message.reply_text(f"✅ Modo voz → {mode}")


async def cmd_safe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text(
            f"Modo seguro: {'ON (pide confirmación)' if session.safe_mode else 'OFF (autónomo)'}\n"
            "Uso: /safe on|off"
        )
        return
    mode = context.args[0].lower()
    if mode not in ("on", "off"):
        await update.message.reply_text("Uso: /safe on|off")
        return
    session.safe_mode = mode == "on"
    await close_session(session)
    await update.message.reply_text(
        f"✅ Modo seguro → {'ON' if session.safe_mode else 'OFF (autónomo)'}"
    )


async def cmd_think(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)
    state = "ON" if session.current_thinking > 0 else "OFF"
    budget = f" ({session.current_thinking} tokens)" if session.current_thinking > 0 else ""
    route = "auto" if session.auto_route else (session.model_override or "manual")
    await update.message.reply_text(
        f"Pensamiento extendido actual: {state}{budget}\n"
        f"Routing: {route}\n"
        "(El pensamiento lo decide el router automáticamente según la tarea. "
        "Usa /model opus para forzar opus con thinking alto.)"
    )


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)

    if not context.args:
        current = session.current_model.replace("claude-", "").split("-")[0]
        route = "auto" if session.auto_route else "manual"
        await update.message.reply_text(
            f"Modo: {route}\n"
            f"Modelo actual: {current}\n"
            f"Thinking: {session.current_thinking} tokens\n\n"
            "Uso: /model auto|haiku|sonnet|opus"
        )
        return

    arg = context.args[0].lower()
    if arg == "auto":
        session.auto_route = True
        session.model_override = None
        await update.message.reply_text("✅ Routing automático activado")
        return
    if arg in MODEL_NAME_MAP:
        session.auto_route = False
        session.model_override = MODEL_NAME_MAP[arg]
        session.current_model = MODEL_NAME_MAP[arg]
        session.current_thinking = 0
        await close_session(session)
        await update.message.reply_text(f"✅ Modelo fijado → {arg} (routing manual)")
        return
    await update.message.reply_text("Uso: /model auto|haiku|sonnet|opus")


async def cmd_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    session = get_session(update.effective_chat.id)
    current = session.current_model.replace("claude-", "").split("-")[0]
    await update.message.reply_text(
        f"💰 Coste de esta sesión: ${session.total_cost:.4f}\n"
        f"Modelo: {current}\n"
        f"/reset para empezar nueva sesión"
    )


# ---------- Handlers de mensajes ---------- #


async def handle_pending_decision(update: Update, session: ChatSession, text: str) -> bool:
    if session.pending_decisions.empty():
        return False
    try:
        tool_name, decision_future = session.pending_decisions.get_nowait()
    except asyncio.QueueEmpty:
        return False

    upper = text.strip().upper()
    if upper in ("SIEMPRE", "ALWAYS", "A"):
        decision_future.set_result("always")
        await update.message.reply_text(f"✅ Permitido SIEMPRE para {tool_name} en esta sesión")
    elif upper in ("SI", "SÍ", "YES", "Y", "OK"):
        decision_future.set_result("allow")
        await update.message.reply_text("✅ Permitido (solo esta vez)")
    elif upper in ("NO", "N"):
        decision_future.set_result("deny")
        await update.message.reply_text("❌ Denegado")
    else:
        await update.message.reply_text(
            "Hay una confirmación pendiente. Responde SI / SIEMPRE / NO."
        )
    return True


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    text = (update.message.text or "").strip()
    session = get_session(update.effective_chat.id)
    if await handle_pending_decision(update, session, text):
        return
    await run_claude(update, context, session, text, source="text")


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

    await run_claude(update, context, session, text, source="voice")


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


def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("pwd", cmd_pwd))
    app.add_handler(CommandHandler("cd", cmd_cd))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("voice", cmd_voice))
    app.add_handler(CommandHandler("safe", cmd_safe))
    app.add_handler(CommandHandler("think", cmd_think))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("cost", cmd_cost))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    logger.info("Bot arrancado. Auto-routing activo. Esperando mensajes...")
    app.run_polling()


if __name__ == "__main__":
    main()
