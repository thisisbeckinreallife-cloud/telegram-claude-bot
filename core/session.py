"""Gestión de sesiones de chat persistentes.

- ChatSession dataclass: estado por chat (cwd, client, voice, cost, etc.)
- SESSIONS/SESSION_LOCKS: caché en memoria + mutex por chat.
- load/save/get_stored/set_stored/clear_stored: persistencia de session_id
  entre reinicios en sessions.json.
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from claude_agent_sdk import ClaudeSDKClient
from telegram.ext import Application

from core.config import DEFAULT_WORKING_DIR, SESSIONS_FILE

logger = logging.getLogger(__name__)

# DEFAULT_MODEL vive en core/routing.py pero la importación circular es real:
# session.py importa de routing; routing no importa de session. Fino.
from core.routing import DEFAULT_MODEL  # noqa: E402


# ---------- Persistencia en disco ---------- #
# Move verbatim de bot.py: escritura atómica con tmp + os.replace,
# caché en memoria SESSIONS_MAP, y escritura sólo en diff para evitar I/O extra.

def load_sessions_map() -> dict:
    try:
        with open(SESSIONS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_sessions_map(data: dict) -> None:
    tmp = SESSIONS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, SESSIONS_FILE)


SESSIONS_MAP: dict[str, str] = load_sessions_map()


def get_stored_session_id(chat_id: int) -> Optional[str]:
    return SESSIONS_MAP.get(str(chat_id))


def set_stored_session_id(chat_id: int, session_id: str) -> None:
    if SESSIONS_MAP.get(str(chat_id)) != session_id:
        SESSIONS_MAP[str(chat_id)] = session_id
        save_sessions_map(SESSIONS_MAP)


def clear_stored_session_id(chat_id: int) -> None:
    if str(chat_id) in SESSIONS_MAP:
        del SESSIONS_MAP[str(chat_id)]
        save_sessions_map(SESSIONS_MAP)


# ---------- Dataclass + caché en memoria ---------- #

@dataclass
class ChatSession:
    chat_id: int
    cwd: str
    client: Optional[ClaudeSDKClient] = None
    bot_app: Optional[Application] = None
    voice_mode: str = "auto"
    last_session_id: Optional[str] = None
    trusted_tools: set = field(default_factory=set)
    safe_mode: bool = False
    pending_decisions: asyncio.Queue = field(default_factory=asyncio.Queue)
    pending_approvals: dict = field(default_factory=dict)
    _approval_counter: int = 0
    total_cost: float = 0.0

    # Auto-routing
    auto_route: bool = True
    model_override: Optional[str] = None
    current_model: str = DEFAULT_MODEL
    current_thinking: int = 0


SESSIONS: dict[int, ChatSession] = {}
SESSION_LOCKS: dict[int, asyncio.Lock] = {}


def get_session(chat_id: int) -> ChatSession:
    if chat_id not in SESSIONS:
        SESSIONS[chat_id] = ChatSession(
            chat_id=chat_id,
            cwd=DEFAULT_WORKING_DIR,
            last_session_id=get_stored_session_id(chat_id),
        )
    return SESSIONS[chat_id]


def get_session_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in SESSION_LOCKS:
        SESSION_LOCKS[chat_id] = asyncio.Lock()
    return SESSION_LOCKS[chat_id]
