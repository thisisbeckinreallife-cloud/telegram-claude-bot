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

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

openai_client: Optional[AsyncOpenAI] = (
    AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
)

SAFE_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
    "NotebookRead",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
}




def make_can_use_tool(session: ChatSession):
    async def can_use_tool(
        tool_name: str,
        tool_input: dict,
        context: ToolPermissionContext,
    ):
        if tool_name in SAFE_TOOLS or tool_name in session.trusted_tools:
            return PermissionResultAllow(updated_input=tool_input)

        try:
            preview = ", ".join(f"{k}={str(v)[:120]}" for k, v in tool_input.items())
        except Exception:
            preview = str(tool_input)[:400]
        if len(preview) > 600:
            preview = preview[:600] + "..."

        if session.bot_app is None:
            return PermissionResultDeny(message="Bot no inicializado")

        session._approval_counter += 1
        approval_id = str(session._approval_counter)

        loop = asyncio.get_running_loop()
        decision_future = loop.create_future()
        session.pending_approvals[approval_id] = (tool_name, decision_future)
        await session.pending_decisions.put((tool_name, decision_future))

        msg = (
            f"⚠️ Confirmación requerida\n\n"
            f"Herramienta: {tool_name}\n"
            f"{preview}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ SI", callback_data=f"approve:{session.chat_id}:{approval_id}:allow"),
                InlineKeyboardButton("✅ SIEMPRE", callback_data=f"approve:{session.chat_id}:{approval_id}:always"),
                InlineKeyboardButton("❌ NO", callback_data=f"approve:{session.chat_id}:{approval_id}:deny"),
            ]
        ])
        await session.bot_app.bot.send_message(
            chat_id=session.chat_id, text=msg, reply_markup=keyboard
        )
        try:
            decision = await asyncio.wait_for(decision_future, timeout=300)
        except asyncio.TimeoutError:
            decision = "deny"

        if decision == "always":
            session.trusted_tools.add(tool_name)
            return PermissionResultAllow(updated_input=tool_input)
        if decision == "allow":
            return PermissionResultAllow(updated_input=tool_input)
        return PermissionResultDeny(message="El usuario denegó la acción.")

    return can_use_tool


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


def is_authorized(update: Update) -> bool:
    user = update.effective_user
    if user is None or user.id != ALLOWED_USER_ID:
        logger.warning("Mensaje rechazado de user_id=%s", user.id if user else None)
        return False
    return True


# ---------- Audio: STT y TTS ---------- #


async def transcribe_audio(file_path: str) -> str:
    if openai_client is None:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    with open(file_path, "rb") as f:
        result = await openai_client.audio.transcriptions.create(
            model=STT_MODEL,
            file=f,
        )
    return result.text


async def synthesize_voice(text: str, out_path: str) -> None:
    if openai_client is None:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    text = text[:4000]
    response = await openai_client.audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
        response_format="opus",
    )
    response.write_to_file(out_path)


# ---------- Utilitarios de UI y archivos ---------- #


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


# ---------- Envío de respuesta ---------- #


async def send_reply(update: Update, session: ChatSession, reply: str, source: str) -> None:
    if not reply:
        reply = "(sin respuesta)"

    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i : i + 4000])

    want_voice = (
        session.voice_mode == "on"
        or (session.voice_mode == "auto" and source == "voice")
    )
    if want_voice and openai_client is not None:
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
