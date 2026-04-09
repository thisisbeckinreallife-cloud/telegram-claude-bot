"""Núcleo de ejecución: cliente Claude, envío de prompts, respuestas.

Contiene ensure_client, run_claude, close_session y helpers de
ciclo de vida (typing indicator, cleanup, send_reply).
"""
import asyncio
import logging
import os
from typing import Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)
from telegram import Update
from telegram.ext import Application, ContextTypes

from core.audio import get_openai_client, synthesize_voice
from core.config import DOWNLOAD_DIR
from core.routing import MODEL_HAIKU, MODEL_SONNET, apply_routing
from core.session import (
    ChatSession,
    clear_stored_session_id,
    get_session_lock,
    set_stored_session_id,
)
from core.system_prompt import build_system_prompt
from handlers.permissions import make_can_use_tool
from tools import load_all_tools
from agents.definitions import AGENTS

logger = logging.getLogger(__name__)


async def ensure_client(session: ChatSession, app: Application) -> None:
    async with get_session_lock(session.chat_id):
        if session.client is not None:
            return
        session.bot_app = app

        # Fallback: distinto al principal para evitar "Fallback model cannot be the same"
        fallback = MODEL_SONNET if session.current_model == MODEL_HAIKU else MODEL_HAIKU

        options_kwargs = dict(
            cwd=session.cwd,
            permission_mode="default" if session.safe_mode else "bypassPermissions",
            setting_sources=["user", "project", "local"],
            model=session.current_model,
            fallback_model=fallback,
            system_prompt=build_system_prompt(),
            stderr=lambda line: logger.error("CLAUDE_CLI: %s", line),
            tools=load_all_tools(),
            agents=AGENTS,
        )
        if session.safe_mode:
            options_kwargs["can_use_tool"] = make_can_use_tool(session)
        if session.last_session_id:
            options_kwargs["resume"] = session.last_session_id
        if session.current_thinking > 0:
            options_kwargs["thinking"] = {"type": "enabled", "budget_tokens": session.current_thinking}

        options = ClaudeAgentOptions(**options_kwargs)
        session.client = ClaudeSDKClient(options=options)
        try:
            await session.client.connect()
        except Exception as exc:
            # Si la sesión guardada está corrupta o ya no existe, reintenta sin resume
            if session.last_session_id:
                logger.warning("No se pudo resumir sesión %s: %s. Empiezo nueva.", session.last_session_id, exc)
                session.last_session_id = None
                clear_stored_session_id(session.chat_id)
                options_kwargs.pop("resume", None)
                session.client = ClaudeSDKClient(options=ClaudeAgentOptions(**options_kwargs))
                await session.client.connect()
            else:
                raise


async def close_session_unlocked(session: ChatSession) -> None:
    """Cierra el cliente sin adquirir el lock (usar solo si ya lo tienes)."""
    if session.client is not None:
        try:
            await session.client.disconnect()
        except Exception:
            logger.exception("Error cerrando cliente")
    session.client = None


async def close_session(session: ChatSession) -> None:
    """Cierra el cliente de forma thread-safe."""
    async with get_session_lock(session.chat_id):
        await close_session_unlocked(session)


async def typing_indicator_loop(update: Update, stop_event: asyncio.Event) -> None:
    """Envía 'typing' cada 4 segundos hasta que stop_event se activa."""
    while not stop_event.is_set():
        try:
            await update.message.chat.send_action("typing")
            await asyncio.sleep(4)
        except Exception:
            break


def cleanup_file(path: str) -> None:
    """Borra un archivo con manejo seguro de errores."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        logger.warning("No se pudo borrar archivo: %s", path)


async def send_reply(update: Update, session: ChatSession, reply: str, source: str) -> None:
    if not reply:
        reply = "(sin respuesta)"

    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i : i + 4000])

    want_voice = (
        session.voice_mode == "on"
        or (session.voice_mode == "auto" and source == "voice")
    )
    if want_voice and get_openai_client() is not None:
        try:
            out_path = os.path.join(DOWNLOAD_DIR, f"reply_{update.message.message_id}.ogg")
            await synthesize_voice(reply, out_path)
            with open(out_path, "rb") as f:
                await update.message.reply_voice(f)
            os.remove(out_path)
        except Exception as exc:
            logger.exception("Error generando voz")
            await update.message.reply_text(f"⚠️ Error TTS: {exc}")


# ---------- Núcleo: enviar prompt a Claude ---------- #


async def run_claude(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: ChatSession,
    prompt: str,
    source: str,
) -> None:
    await update.message.chat.send_action("typing")

    # Auto-routing: decide modelo y thinking para este prompt
    await apply_routing(session, prompt)

    chunks: list[str] = []
    captured_session_id: Optional[str] = None
    result_error: Optional[str] = None
    msg_types: list[str] = []

    MAX_RETRIES = 3
    BACKOFFS = [5, 15, 30]

    # Inicia loop de typing indicator
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(typing_indicator_loop(update, stop_typing))

    try:
        for attempt in range(MAX_RETRIES):
            chunks = []
            result_error = None
            msg_types = []

            async def _stream_once():
                nonlocal captured_session_id, result_error
                await ensure_client(session, context.application)
                await session.client.query(prompt)
                async for message in session.client.receive_response():
                    msg_types.append(type(message).__name__)
                    sid = getattr(message, "session_id", None)
                    if sid:
                        captured_session_id = sid
                    if isinstance(message, AssistantMessage):
                        for block in message.content or []:
                            bname = type(block).__name__
                            logger.info("Block: %s", bname)
                            if isinstance(block, TextBlock) and block.text:
                                if block.text.startswith("API Error:"):
                                    result_error = block.text
                                else:
                                    chunks.append(block.text)
                    elif isinstance(message, ResultMessage):
                        logger.info(
                            "ResultMessage: subtype=%s is_error=%s result=%r cost=%s",
                            message.subtype, message.is_error, message.result,
                            message.total_cost_usd,
                        )
                        if message.total_cost_usd:
                            session.total_cost += message.total_cost_usd
                        if message.is_error:
                            result_error = message.result or f"subtype={message.subtype}"
                        elif not chunks and message.result:
                            chunks.append(str(message.result))

            try:
                await asyncio.wait_for(_stream_once(), timeout=180)
                logger.info("Stream attempt=%d model=%s thinking=%d msg_types=%s chunks=%d error=%s",
                            attempt, session.current_model, session.current_thinking,
                            msg_types, len(chunks), bool(result_error))
            except asyncio.TimeoutError:
                logger.warning("Timeout esperando respuesta de Claude (intento %d)", attempt)
                await close_session(session)
                result_error = "timeout: sin respuesta del modelo en 180s"
            except Exception as exc:
                logger.exception("Error ejecutando Claude (intento %d)", attempt)
                await close_session(session)
                result_error = f"Excepción: {exc}"

            transient = result_error and any(
                s in result_error for s in (
                    "529", "overloaded", "rate_limit", "500", "502", "503", "504", "timeout"
                )
            )
            if not result_error or not transient or attempt == MAX_RETRIES - 1:
                break

            wait = BACKOFFS[attempt]
            logger.warning("Error transitorio, reintentando en %ss (intento %d/%d)",
                           wait, attempt + 1, MAX_RETRIES)
            await update.message.chat.send_action("typing")
            await asyncio.sleep(wait)
            await close_session(session)
    finally:
        stop_typing.set()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    if captured_session_id:
        session.last_session_id = captured_session_id
        set_stored_session_id(session.chat_id, captured_session_id)

    if result_error and not chunks:
        await update.message.reply_text(f"⚠️ Error: {result_error}")
        return

    reply = "\n".join(chunks).strip()
    if not reply and result_error:
        reply = f"⚠️ Error de Claude: {result_error}"
    await send_reply(update, session, reply, source)
