"""Telegram bot que delega cada mensaje a Claude vía claude-agent-sdk.

Módulos:
- core/       lógica de sesión, routing, runner, system prompt, audio
- handlers/   handlers de Telegram (text, voice, media, comandos)

Este archivo solo arma el Application y arranca el polling.
"""
import logging
import os

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

# Importar core.config primero: carga .env, extiende PATH, crea directorios.
import core.config  # noqa: F401

from core.worker import task_worker_loop
from handlers.commands import (
    cmd_cd,
    cmd_cost,
    cmd_model,
    cmd_pwd,
    cmd_reset,
    cmd_safe,
    cmd_start,
    cmd_think,
    cmd_voice,
)
from handlers.media import handle_document, handle_photo
from handlers.text import handle_text
from handlers.voice import handle_voice

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]


async def on_startup(app: Application) -> None:
    worker_count = int(os.environ.get("WORKER_COUNT", "2"))
    for i in range(worker_count):
        app.create_task(task_worker_loop(i), name=f"worker-{i}")
    logger.info("Lanzados %d workers", worker_count)


def main() -> None:
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .concurrent_updates(True)
        .post_init(on_startup)
        .build()
    )
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
