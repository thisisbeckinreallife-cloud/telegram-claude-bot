"""Comandos slash del bot: /start /pwd /cd /reset /voice /safe /think /model /cost."""
import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from core.config import ALLOWED_USER_ID
from core.routing import DEFAULT_MODEL, MODEL_NAME_MAP
from core.runner import close_session
from core.session import clear_stored_session_id, get_session

logger = logging.getLogger(__name__)


def is_authorized(update: Update) -> bool:
    user = update.effective_user
    if user is None or user.id != ALLOWED_USER_ID:
        logger.warning("Mensaje rechazado de user_id=%s", user.id if user else None)
        return False
    return True


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
