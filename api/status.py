"""Servidor HTTP local para telemetría del bot.

Endpoint: GET http://localhost:8080/status
"""
import logging
import os
import time

from aiohttp import web

from core.session import SESSIONS
from core.worker import TASK_QUEUE

logger = logging.getLogger(__name__)

START_TIME = time.time()
PORT = int(os.environ.get("MISSION_CONTROL_PORT", "8080"))


async def status_handler(request: web.Request) -> web.Response:
    total_cost = sum(s.total_cost for s in SESSIONS.values())
    sessions_info = [
        {
            "chat_id": s.chat_id,
            "cwd": s.cwd,
            "cost_usd": round(s.total_cost, 4),
            "model": s.current_model,
            "thinking": s.current_thinking,
            "voice_mode": s.voice_mode,
            "safe_mode": s.safe_mode,
        }
        for s in SESSIONS.values()
    ]
    return web.json_response({
        "uptime_seconds": int(time.time() - START_TIME),
        "queue_size": TASK_QUEUE.qsize(),
        "active_sessions": len(SESSIONS),
        "total_cost_usd": round(total_cost, 4),
        "sessions": sessions_info,
    })


async def start_web_server() -> None:
    app = web.Application()
    app.router.add_get("/status", status_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=PORT)
    await site.start()
    logger.info("Mission Control en http://127.0.0.1:%d/status", PORT)
