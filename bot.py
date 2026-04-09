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

from handlers.commands import (
    is_authorized,
    cmd_start,
    cmd_pwd,
    cmd_cd,
    cmd_reset,
    cmd_voice,
    cmd_safe,
    cmd_think,
    cmd_model,
    cmd_cost,
)

from handlers.text import handle_text, handle_pending_decision

from handlers.voice import handle_voice

from handlers.media import handle_photo, handle_document

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- Handlers de mensajes ---------- #


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
