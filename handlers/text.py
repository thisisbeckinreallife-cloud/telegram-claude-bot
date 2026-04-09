"""Handler de mensajes de texto + resolución de confirmaciones pendientes."""
import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.runner import run_claude
from core.session import ChatSession, get_session
from handlers.commands import is_authorized

logger = logging.getLogger(__name__)


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
