# Telegram Bot Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the monolithic `bot.py` into a modular, multi-instance, fork-friendly system with task queue, Keychain credentials, persistent Playwright browser, subagents, Ollama hybrid tools, and Mission Control API — across 7 ordered phases.

**Architecture:** Break `bot.py` (961 lines) into `core/`, `handlers/`, `tools/`, `agents/`, `api/` modules. Phase 1 is a pure refactor (zero behavior change) plus task queue foundation. Phases 2-7 stack new features on that foundation, each testable independently.

**Tech Stack:** Python 3.10+, python-telegram-bot 22.7, claude-agent-sdk 0.1.56, keyring (macOS Keychain), playwright, aiohttp, httpx, Ollama (external), launchd (macOS).

**Spec:** `docs/superpowers/specs/2026-04-09-telegram-bot-evolution-design.md`

---

## Pre-flight notes

- **Run from worktree or directly on `main`?** Per spec, implementation runs on `main` of `/Users/lara/telegram-claude-bot`. Each phase ends in a clean commit; user can stop at any phase and have a working bot.
- **Pre-existing bug preserved intentionally:** `bot.py` imports `CallbackQueryHandler` but never registers one, so inline keyboard approvals can never resolve. This plan **does not fix** that bug — scope respect (see CLAUDE.md rule 2-3). Lara can request a separate fix later.
- **Every new Python module starts with:**
  ```python
  import logging
  logger = logging.getLogger(__name__)
  ```
  These two lines are **not shown** in individual task snippets to reduce noise, but **must** be added to every new module. Consider it part of every "create new module" step.
- **Practical additions not in spec:** This plan adds `core/config.py` (constants/env vars) and `core/audio.py` (OpenAI client + STT/TTS) to avoid circular imports. Neither adds behavior — they're extraction helpers.

---

## File structure after Phase 1 (refactor + queue)

```
telegram-claude-bot/
├── bot.py                    # imports + main() only (~60 lines)
├── core/
│   ├── __init__.py           # empty
│   ├── config.py             # env vars, paths, ALLOWED_USER_ID
│   ├── session.py            # ChatSession, SESSIONS, SESSION_LOCKS, persistence
│   ├── routing.py            # MODEL_* constants, MODEL_NAME_MAP, route_prompt, apply_routing
│   ├── system_prompt.py      # read_file_safe, load_knowledge_blocks, build_system_prompt
│   ├── audio.py              # openai_client, transcribe_audio, synthesize_voice
│   ├── runner.py             # ensure_client, run_claude, close_session(_unlocked),
│   │                         # typing_indicator_loop, send_reply, cleanup_file
│   └── worker.py             # TASK_QUEUE, task_worker_loop, enqueue_task
├── handlers/
│   ├── __init__.py           # empty
│   ├── permissions.py        # SAFE_TOOLS, make_can_use_tool
│   ├── commands.py           # cmd_start, cmd_pwd, cmd_cd, cmd_reset, cmd_voice,
│   │                         # cmd_safe, cmd_think, cmd_model, cmd_cost
│   ├── text.py               # handle_text, handle_pending_decision, is_authorized
│   ├── voice.py              # handle_voice
│   └── media.py              # handle_photo, handle_document
```

After Phase 7 additionally adds `tools/`, `agents/`, `api/`, `setup_credentials.py`, `bootstrap.sh`, `com.telegram-claude-bot.plist.template`, `system_prompt.example.md`.

---

# PHASE 1 — Refactor to modules + Task Queue

Zero behavior change for the refactor portion. Bot must work identically to pre-refactor at end of Task 14.

---

### Task 1: Create `core/` and `handlers/` directory skeletons

**Files:**
- Create: `core/__init__.py`
- Create: `handlers/__init__.py`

- [ ] **Step 1: Create empty `core/__init__.py`**

Write: `core/__init__.py` with content:
```python
```
(Empty file — just the package marker.)

- [ ] **Step 2: Create empty `handlers/__init__.py`**

Write: `handlers/__init__.py` with content:
```python
```

- [ ] **Step 3: Verify directories exist**

Run: `ls core/ handlers/`
Expected: both directories listed with their `__init__.py`.

- [ ] **Step 4: Commit**

```bash
git add core/__init__.py handlers/__init__.py
git commit -m "refactor: add core/ and handlers/ package skeletons"
```

---

### Task 2: Create `core/config.py` with constants and env vars

**Files:**
- Create: `core/config.py`
- Modify: `bot.py` (remove the constants being moved; keep only `TELEGRAM_TOKEN` and logger setup)

Source lines in current `bot.py`:
- Env vars: lines 48-60, 62-66
- `os.environ["PATH"]` update: line 68
- `os.makedirs(...)` calls: lines 69-70

- [ ] **Step 1: Create `core/config.py`**

Write: `core/config.py`:
```python
"""Configuración global del bot: env vars, rutas, constantes."""
import os

from dotenv import load_dotenv

load_dotenv()

# Sólo leídas por bot.py / otros módulos del bot — no por este módulo directamente.
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])
DEFAULT_WORKING_DIR = os.environ.get("WORKING_DIR", "/Users/lara/proyectos")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TTS_VOICE = os.environ.get("TTS_VOICE", "nova")
TTS_MODEL = os.environ.get("TTS_MODEL", "tts-1")
STT_MODEL = os.environ.get("STT_MODEL", "whisper-1")

# Rutas
PROJECT_DIR = "/Users/lara/telegram-claude-bot"
KNOWLEDGE_DIR = f"{PROJECT_DIR}/memory/knowledge"
SESSIONS_FILE = f"{PROJECT_DIR}/sessions.json"
GLOBAL_CLAUDE_MD = "/Users/lara/.claude/CLAUDE.md"
DOWNLOAD_DIR = f"{PROJECT_DIR}/downloads"

# PATH extendido para que el subprocess de `claude` encuentre su CLI
os.environ["PATH"] = f"/Users/lara/.local/bin:{os.environ.get('PATH', '')}"

# Asegura directorios
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
```

- [ ] **Step 2: Update `bot.py` to import from `core.config`**

Open `bot.py`. Replace lines 46-70 (from `load_dotenv()` through `os.makedirs(KNOWLEDGE_DIR, exist_ok=True)`) with:

```python
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

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
```

Keep the logging.basicConfig block (lines 72-76) and `logger = logging.getLogger(__name__)` (line 76) in place — they move out in later tasks.

- [ ] **Step 3: Run the bot smoke test**

Run: `python -c "import bot"` from the repo root.
Expected: No import errors. If there's an ImportError, check that `core/__init__.py` exists and `core/config.py` is syntactically valid.

- [ ] **Step 4: Commit**

```bash
git add core/config.py bot.py
git commit -m "refactor: extract config constants to core/config.py"
```

---

### Task 3: Create `core/session.py` with ChatSession + persistence helpers

**Files:**
- Create: `core/session.py`
- Modify: `bot.py` (remove moved functions and dataclass)

Source lines to move from `bot.py`:
- `load_sessions_map` → lines 98-104
- `save_sessions_map` → lines 106-114
- `get_stored_session_id` → lines 116-118
- `set_stored_session_id` → lines 120-124
- `clear_stored_session_id` → lines 126-132
- `ChatSession` dataclass → lines 278-297
- `SESSIONS`, `SESSION_LOCKS` → lines 300-301
- `get_session` → lines 304-311
- `get_session_lock` → lines 314-317

- [ ] **Step 1: Create `core/session.py`**

Write: `core/session.py`:
```python
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
# Move verbatim de bot.py líneas 98-129: escritura atómica con tmp + os.replace,
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
```

- [ ] **Step 2: Delete moved code from `bot.py`**

Open `bot.py`. Delete:
- Lines 95-132 (`# ---------- Persistencia de sesiones ----------` + all 5 persistence functions)
- Lines 278-317 (`ChatSession` dataclass, `SESSIONS`, `SESSION_LOCKS`, `get_session`, `get_session_lock`)

Add at the top of `bot.py` (after existing `from core.config import ...`):
```python
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
```

- [ ] **Step 3: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`. Any ImportError means a circular import — in that case Task 4 (routing) must be done first since session imports DEFAULT_MODEL from routing.

- [ ] **Step 4: Commit**

```bash
git add core/session.py bot.py
git commit -m "refactor: extract session state and persistence to core/session.py"
```

---

### Task 4: Create `core/routing.py` with model constants and routing logic

**Files:**
- Create: `core/routing.py`
- Modify: `bot.py`

Source lines to move from `bot.py`:
- Model constants → lines 57-60 (`MODEL_HAIKU`, `MODEL_SONNET`, `MODEL_OPUS`, `DEFAULT_MODEL`)
- `MODEL_NAME_MAP` → line 206 (check surrounding context to capture the full dict)
- `route_prompt` → lines 213-277
- `apply_routing` → lines 435-456

Note: Task 3 already imports `DEFAULT_MODEL` from here, so create this BEFORE running Task 3's smoke test, or create in this order: Task 4 first, then Task 3. **Recommended: do Task 4 BEFORE committing Task 3.** This plan lists Task 3 first because it's the bigger chunk; if smoke test fails at Task 3 Step 3, do Task 4 then retry.

- [ ] **Step 1: Create `core/routing.py`**

Write: `core/routing.py`:
```python
"""Router heurístico: decide modelo (haiku/sonnet/opus) y thinking budget
para cada prompt. Sin subprocess de Claude — es una clasificación local."""
import logging
import os

logger = logging.getLogger(__name__)

MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_OPUS = "claude-opus-4-6"
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", MODEL_SONNET)

MODEL_NAME_MAP = {
    "haiku": MODEL_HAIKU,
    "sonnet": MODEL_SONNET,
    "opus": MODEL_OPUS,
}


def route_prompt(prompt: str) -> tuple[str, int]:
    """Heurística local: clasifica el prompt sin subprocess de Claude.

    Reglas:
    - haiku + thinking 0    → saludos, chitchat, preguntas triviales, comandos cortos.
    - sonnet + thinking 0   → tareas directas: leer/escribir, buscar, resúmenes, emails.
    - sonnet + thinking 8000 → código no trivial, debugging, análisis, refactors.
    - opus + thinking 16000 → arquitectura, decisiones estratégicas, revisiones críticas.
    """
    p = prompt.lower()
    length = len(prompt)

    opus_keywords = {
        "arquitectura", "estrategia", "decisión", "exhaustivo", "complejo", "crítico",
        "diseño", "análisis competitivo", "roadmap", "plan", "investigar",
        "mejoraría", "optimizar",
    }
    sonnet_thinking_keywords = {
        "código", "debug", "error", "refactor", "función", "clase", "test", "análisis",
        "estructura", "patrón", "algoritmo", "optimiz", "bug", "fallo", "problema",
    }
    sonnet_keywords = {
        "archivo", "read", "escribir", "crear", "leer", "buscar", "internet", "email",
        "resumen", "traducir", "explicar", "git", "comando",
    }
    haiku_keywords = {
        "hola", "hi", "hey", "gracias", "sí", "help", "pwd", "cd",
    }

    if any(kw in p for kw in opus_keywords):
        logger.info("Router (heurística) → model=opus thinking=16000")
        return (MODEL_OPUS, 16000)
    if any(kw in p for kw in sonnet_thinking_keywords):
        logger.info("Router (heurística) → model=sonnet thinking=8000")
        return (MODEL_SONNET, 8000)
    if length > 400 or any(kw in p for kw in sonnet_keywords):
        logger.info("Router (heurística) → model=sonnet thinking=0")
        return (MODEL_SONNET, 0)
    if any(kw in p for kw in haiku_keywords) or length < 50:
        logger.info("Router (heurística) → model=haiku thinking=0")
        return (MODEL_HAIKU, 0)
    logger.info("Router (heurística) → model=sonnet thinking=0 (default)")
    return (MODEL_SONNET, 0)


async def apply_routing(session, prompt: str) -> None:
    """Actualiza current_model y current_thinking para este prompt.

    Si cambian, cierra el cliente actual: la próxima llamada a ensure_client
    lo recreará con los valores nuevos (y el resume preserva la memoria).

    Nota: importa get_session_lock y close_session_unlocked de forma perezosa
    dentro de la función para evitar imports circulares (runner importa de routing).
    """
    from core.runner import close_session_unlocked
    from core.session import get_session_lock

    async with get_session_lock(session.chat_id):
        if session.auto_route:
            target_model, target_thinking = route_prompt(prompt)
        else:
            target_model = session.model_override or DEFAULT_MODEL
            target_thinking = 0

        if target_model != session.current_model or target_thinking != session.current_thinking:
            logger.info(
                "Routing cambia: %s/%d → %s/%d",
                session.current_model, session.current_thinking,
                target_model, target_thinking,
            )
            session.current_model = target_model
            session.current_thinking = target_thinking
            await close_session_unlocked(session)
```

- [ ] **Step 3: Delete moved code from `bot.py`**

Open `bot.py`. Delete:
- Lines 57-60 (model constants)
- Line 206 through end of `MODEL_NAME_MAP`
- Lines 213-277 (`route_prompt`)
- Lines 435-456 (`apply_routing`)

Add to the import block at top of `bot.py`:
```python
from core.routing import (
    MODEL_HAIKU,
    MODEL_SONNET,
    MODEL_OPUS,
    DEFAULT_MODEL,
    MODEL_NAME_MAP,
    route_prompt,
    apply_routing,
)
```

- [ ] **Step 4: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add core/routing.py bot.py
git commit -m "refactor: extract routing logic to core/routing.py"
```

---

### Task 5: Create `core/system_prompt.py` with CAG prompt builder

**Files:**
- Create: `core/system_prompt.py`
- Modify: `bot.py`

Source lines to move from `bot.py`:
- `read_file_safe` → lines 135-141
- `load_knowledge_blocks` → lines 143-151
- `build_system_prompt` → lines 153-205

- [ ] **Step 1: Create `core/system_prompt.py`**

Write: `core/system_prompt.py`:
```python
"""Construcción del system prompt del bot (CAG: Cache-Augmented Generation).

Lee memory/knowledge/*.md + ~/.claude/CLAUDE.md y los inyecta en el prompt.
"""
import glob
import logging
import os

from core.config import GLOBAL_CLAUDE_MD, KNOWLEDGE_DIR

logger = logging.getLogger(__name__)


def read_file_safe(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def load_knowledge_blocks() -> list[tuple[str, str]]:
    """Devuelve [(filename, content)] leyendo todos los .md de KNOWLEDGE_DIR."""
    blocks: list[tuple[str, str]] = []
    for path in sorted(glob.glob(f"{KNOWLEDGE_DIR}/*.md")):
        content = read_file_safe(path).strip()
        if content:
            blocks.append((os.path.basename(path), content))
    return blocks


def build_system_prompt() -> str:
    knowledge = load_knowledge_blocks()
    claude_md = read_file_safe(GLOBAL_CLAUDE_MD).strip()

    parts = [
        "Eres el asistente personal de Lara Aycart, accesible vía Telegram desde su móvil. "
        "Lara trabaja en copywriting, ventas, marca personal y creación de contenido. "
        "Tienes acceso completo a su Mac mini: archivos, terminal, git, deploys, búsqueda en internet, "
        "y skills/MCPs configurados a nivel global.",
        "",
        "Reglas de comunicación:",
        "- Responde SIEMPRE en español, salvo que Lara escriba en otro idioma.",
        "- Sé directo y conciso. Sin preámbulos, sin resúmenes innecesarios al final, sin disclaimers.",
        "- Si una tarea tiene varios pasos, ejecútalos sin pedir permiso (excepto operaciones destructivas, "
        "  donde el sistema te pedirá confirmación automáticamente).",
        "- Cuando no sepas algo, dilo. No inventes APIs, archivos ni rutas.",
        "- Prioriza diffs mínimos al editar código.",
        "",
        "Memoria CAG — cómo funciona:",
        f"- Tus archivos de memoria viven en {KNOWLEDGE_DIR}/*.md.",
        "- Te los inyecto todos abajo en cada conversación (son tu contexto persistente).",
        "- Cuando aprendas algo importante sobre Lara, sus proyectos, personas, preferencias o decisiones, "
        "  ACTUALIZA el archivo correspondiente con Edit/Write:",
        "    · projects.md → estado, decisiones y próximos pasos por proyecto",
        "    · people.md → nuevas personas, clientes, colaboradores",
        "    · preferences.md → reglas de trabajo y comunicación",
        "    · decisions.md → decisiones importantes con contexto y razón",
        "    · MEMORY.md → hechos dinámicos que no encajan en los anteriores",
        "- No guardes cosas triviales, efímeras o derivables del estado actual del repo.",
        "- Usa formato de fecha absoluto (YYYY-MM-DD), nunca relativo.",
    ]

    if knowledge:
        parts += ["", "========= BASE DE CONOCIMIENTO ========="]
        for name, content in knowledge:
            parts += [f"", f"--- {name} ---", content]
        parts += ["", "========= FIN BASE DE CONOCIMIENTO ========="]

    if claude_md:
        parts += [
            "",
            "Reglas de trabajo de Lara (de su CLAUDE.md global, deben respetarse SIEMPRE en tareas de código):",
            "=== CLAUDE.md ===",
            claude_md,
            "=== FIN CLAUDE.md ===",
        ]

    return "\n".join(parts)
```

**Note:** this is a verbatim move from `bot.py` lines 153-200. Do not paraphrase, shorten, or "improve" the prompt text — the CAG memory files and the user's workflow rely on exact wording.

- [ ] **Step 2: Delete moved code from `bot.py`**

Open `bot.py`. Delete lines 135-205 (all three functions including their comment headers).

Add to the import block:
```python
from core.system_prompt import (
    read_file_safe,
    load_knowledge_blocks,
    build_system_prompt,
)
```

- [ ] **Step 3: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Verify the system prompt still builds**

Run: `python -c "from core.system_prompt import build_system_prompt; print(len(build_system_prompt()))"`
Expected: a positive integer (chars of the built prompt). If it's 0, the CAG files aren't being found.

- [ ] **Step 5: Commit**

```bash
git add core/system_prompt.py bot.py
git commit -m "refactor: extract system prompt builder to core/system_prompt.py"
```

---

### Task 6: Create `core/audio.py` with OpenAI client + STT/TTS

**Files:**
- Create: `core/audio.py`
- Modify: `bot.py`

Source lines to move from `bot.py`:
- `openai_client` init → lines 78-80
- `transcribe_audio` → lines 470-478
- `synthesize_voice` → lines 481-491

- [ ] **Step 1: Create `core/audio.py`**

Write: `core/audio.py`:
```python
"""Cliente OpenAI + funciones STT (Whisper) y TTS (tts-1)."""
import logging
from typing import Optional

from openai import AsyncOpenAI

from core.config import OPENAI_API_KEY, STT_MODEL, TTS_MODEL, TTS_VOICE

logger = logging.getLogger(__name__)

openai_client: Optional[AsyncOpenAI] = (
    AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
)


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
```

- [ ] **Step 2: Delete moved code from `bot.py`**

Open `bot.py`. Delete:
- Lines 78-80 (openai_client init)
- Lines 467-491 (audio section header + both functions)

Add to import block:
```python
from core.audio import openai_client, transcribe_audio, synthesize_voice
```

- [ ] **Step 3: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add core/audio.py bot.py
git commit -m "refactor: extract OpenAI client and audio helpers to core/audio.py"
```

---

### Task 7: Create `handlers/permissions.py` with SAFE_TOOLS + make_can_use_tool

**Files:**
- Create: `handlers/permissions.py`
- Modify: `bot.py`

Source lines to move from `bot.py`:
- `SAFE_TOOLS` set → lines 82-92
- `make_can_use_tool` → lines 320-374

- [ ] **Step 1: Create `handlers/permissions.py`**

Write: `handlers/permissions.py`:
```python
"""Construcción del callback can_use_tool para el modo safe.

Envía confirmaciones por Telegram cuando una tool no está en SAFE_TOOLS
y no está en session.trusted_tools.
"""
import asyncio
import logging

from claude_agent_sdk import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.session import ChatSession

logger = logging.getLogger(__name__)

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
```

**Note:** this is a verbatim move from `bot.py` lines 320-374. The closure captures `session` so `pending_approvals`, `pending_decisions`, `trusted_tools`, and `bot_app` are session-scoped.

- [ ] **Step 2: Delete moved code from `bot.py`**

Open `bot.py`. Delete:
- Lines 82-92 (`SAFE_TOOLS` set)
- Lines 320-374 (`make_can_use_tool` function)

Add to import block:
```python
from handlers.permissions import SAFE_TOOLS, make_can_use_tool
```

- [ ] **Step 3: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add handlers/permissions.py bot.py
git commit -m "refactor: extract permission logic to handlers/permissions.py"
```

---

### Task 8: Create `core/runner.py` with runtime core

This is the biggest chunk. It consolidates everything needed to run a Claude prompt from start to finish.

**Files:**
- Create: `core/runner.py`
- Modify: `bot.py`

Source lines to move from `bot.py`:
- `ensure_client` → lines 377-416
- `close_session_unlocked` → lines 419-426
- `close_session` → lines 429-432
- `typing_indicator_loop` → lines 497-504
- `cleanup_file` → lines 507-513
- `send_reply` → lines 519-539
- `run_claude` → lines 545-652

- [ ] **Step 1: Create `core/runner.py` (skeleton with imports)**

Write: `core/runner.py`:
```python
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

from core.audio import openai_client, synthesize_voice
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

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Add `ensure_client` to `core/runner.py`**

Append to `core/runner.py` the exact body of `ensure_client` from `bot.py` lines 377-416. No changes.

- [ ] **Step 3: Add `close_session_unlocked` and `close_session`**

Append to `core/runner.py`:
```python
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
```

- [ ] **Step 4: Add `typing_indicator_loop`, `cleanup_file`, `send_reply`**

Append to `core/runner.py`:
```python
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
```

- [ ] **Step 5: Add `run_claude`**

Append to `core/runner.py` the exact body of `run_claude` from `bot.py` lines 545-652. No changes. It already references `close_session`, `ensure_client`, `apply_routing`, `typing_indicator_loop`, `send_reply`, `set_stored_session_id` — all now imported at top of module.

- [ ] **Step 6: Delete moved code from `bot.py`**

Open `bot.py`. Delete:
- Lines 377-432 (`ensure_client`, `close_session_unlocked`, `close_session`)
- Lines 494-513 (section header + `typing_indicator_loop`, `cleanup_file`)
- Lines 519-539 (`send_reply`)
- Lines 542-652 (section header + `run_claude`)

Add to import block:
```python
from core.runner import (
    ensure_client,
    close_session,
    close_session_unlocked,
    typing_indicator_loop,
    cleanup_file,
    send_reply,
    run_claude,
)
```

- [ ] **Step 7: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 8: Commit**

```bash
git add core/runner.py bot.py
git commit -m "refactor: extract runtime core to core/runner.py"
```

---

### Task 9: Create `handlers/commands.py` with all `/` commands

**Files:**
- Create: `handlers/commands.py`
- Modify: `bot.py`

Source lines to move from `bot.py`:
- `is_authorized` → lines 459-464
- `cmd_start` → lines 658-676
- `cmd_pwd` → lines 677-682
- `cmd_cd` → lines 684-698
- `cmd_reset` → lines 700-710
- `cmd_voice` → lines 712-727
- `cmd_safe` → lines 729-748
- `cmd_think` → lines 750-763
- `cmd_model` → lines 765-796
- `cmd_cost` → lines 798-812

- [ ] **Step 1: Create `handlers/commands.py`**

Write: `handlers/commands.py`:
```python
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
```

Then append the exact bodies of `cmd_start`, `cmd_pwd`, `cmd_cd`, `cmd_reset`, `cmd_voice`, `cmd_safe`, `cmd_think`, `cmd_model`, `cmd_cost` from `bot.py` lines 658-812. No changes.

- [ ] **Step 2: Delete moved code from `bot.py`**

Open `bot.py`. Delete:
- Lines 459-464 (`is_authorized`)
- Lines 655-812 (section header + all 9 commands)

Add to import block:
```python
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
```

- [ ] **Step 3: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add handlers/commands.py bot.py
git commit -m "refactor: extract slash commands to handlers/commands.py"
```

---

### Task 10: Create `handlers/text.py` with text + pending decision handlers

**Files:**
- Create: `handlers/text.py`
- Modify: `bot.py`

Source lines to move from `bot.py`:
- `handle_pending_decision` → lines 813-835
- `handle_text` → lines 838-845

- [ ] **Step 1: Create `handlers/text.py`**

Write: `handlers/text.py`:
```python
"""Handler de mensajes de texto + resolución de confirmaciones pendientes."""
import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.runner import run_claude
from core.session import ChatSession, get_session
from handlers.commands import is_authorized

logger = logging.getLogger(__name__)
```

Then append the exact bodies of `handle_pending_decision` (lines 813-835) and `handle_text` (lines 838-845).

- [ ] **Step 2: Delete moved code from `bot.py`**

Open `bot.py`. Delete lines 813-845 (both functions).

Add to import block:
```python
from handlers.text import handle_text, handle_pending_decision
```

- [ ] **Step 3: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add handlers/text.py bot.py
git commit -m "refactor: extract text handler to handlers/text.py"
```

---

### Task 11: Create `handlers/voice.py` with voice handler

**Files:**
- Create: `handlers/voice.py`
- Modify: `bot.py`

Source lines to move from `bot.py`:
- `handle_voice` → lines 848-892

- [ ] **Step 1: Create `handlers/voice.py`**

Write: `handlers/voice.py`:
```python
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
from handlers.commands import is_authorized
from handlers.text import handle_pending_decision

logger = logging.getLogger(__name__)
```

Then append the exact body of `handle_voice` from `bot.py` lines 848-892. The body uses `tempfile.NamedTemporaryFile(suffix=suffix, dir=DOWNLOAD_DIR, delete=False)` and calls `handle_pending_decision` before `run_claude`. Both symbols are now imported above — do not paraphrase or drop them. Do NOT import `cleanup_file`; `handle_voice` cleans its temp file inline via `os.remove(local_path)` in a `finally` block *before* calling `run_claude`, so no deferred-cleanup wrapper is needed.

- [ ] **Step 2: Delete moved code from `bot.py`**

Open `bot.py`. Delete lines 848-892.

Add to import block:
```python
from handlers.voice import handle_voice
```

- [ ] **Step 3: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add handlers/voice.py bot.py
git commit -m "refactor: extract voice handler to handlers/voice.py"
```

---

### Task 12: Create `handlers/media.py` with photo + document handlers

**Files:**
- Create: `handlers/media.py`
- Modify: `bot.py`

Source lines to move from `bot.py`:
- `handle_photo` → lines 894-914
- `handle_document` → lines 916-939

- [ ] **Step 1: Create `handlers/media.py`**

Write: `handlers/media.py`:
```python
"""Handlers de fotos y documentos: descarga, pasa ruta a Claude."""
import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from core.config import DOWNLOAD_DIR
from core.runner import cleanup_file, run_claude
from core.session import get_session
from handlers.commands import is_authorized

logger = logging.getLogger(__name__)
```

Then append the exact bodies of `handle_photo` (lines 894-914) and `handle_document` (lines 916-939).

- [ ] **Step 2: Delete moved code from `bot.py`**

Open `bot.py`. Delete lines 894-939.

Add to import block:
```python
from handlers.media import handle_photo, handle_document
```

- [ ] **Step 3: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add handlers/media.py bot.py
git commit -m "refactor: extract media handlers to handlers/media.py"
```

---

### Task 13: Trim `bot.py` to imports + `main()`

After Tasks 2-12, `bot.py` still has a lot of residual imports and module-level statements. This task cleans it up.

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Read current `bot.py` and identify what's left**

Run: `wc -l bot.py`
Expected: far fewer lines than the original 961, but still some cruft.

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 2: Rewrite `bot.py` to its minimal final form**

Write: `bot.py`:
```python
"""Telegram bot que delega cada mensaje a Claude vía claude-agent-sdk.

Módulos:
- core/       lógica de sesión, routing, runner, system prompt, audio
- handlers/   handlers de Telegram (text, voice, media, comandos)

Este archivo solo arma el Application y arranca el polling.
"""
import logging
import os

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

# Importar core.config primero: carga .env, extiende PATH, crea directorios.
import core.config  # noqa: F401

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
```

- [ ] **Step 3: Smoke-test imports and line count**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

Run: `wc -l bot.py`
Expected: roughly 60-70 lines.

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "refactor: trim bot.py to imports and main() only"
```

---

### Task 14: Manual regression test (end of refactor)

No files change. This is a checkpoint.

- [ ] **Step 1: Restart the bot under launchd**

Run: `launchctl kickstart -k gui/$(id -u)/com.telegram-claude-bot || true`
Then: `tail -f /Users/lara/telegram-claude-bot/bot.log` for a few seconds.
Expected: "Bot arrancado" message. No tracebacks.

If launchd label differs (pre-Phase 3), skip this and run directly: `python bot.py` in a terminal, Ctrl-C after confirming startup.

- [ ] **Step 2: Send a text message to the bot via Telegram**

Expected: bot replies normally. No behavior change from pre-refactor.

- [ ] **Step 3: Test a command: `/pwd`**

Expected: bot returns current working directory.

- [ ] **Step 4: Test a cost-tracked query**

Send any prompt, then send `/cost`.
Expected: `/cost` returns a non-zero USD value.

- [ ] **Step 5: No commit (no file changes)**

This is a validation checkpoint only. Refactor is DONE when this passes.

---

### Task 15: Create `core/worker.py` with TASK_QUEUE and worker pool

**Files:**
- Create: `core/worker.py`

- [ ] **Step 1: Write `core/worker.py`**

Write: `core/worker.py`:
```python
"""Task queue y worker pool para procesar mensajes asíncronamente.

- TASK_QUEUE: asyncio.Queue global de Tasks.
- task_worker_loop: corutina consumidora (se lanzan N instancias en bot.py).
- enqueue_task: helper para handlers.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class Task:
    chat_id: int
    handler: Callable[..., Awaitable[None]]
    args: tuple
    kwargs: dict


TASK_QUEUE: asyncio.Queue[Task] = asyncio.Queue()


async def enqueue_task(chat_id: int, handler, *args, **kwargs) -> None:
    await TASK_QUEUE.put(Task(chat_id, handler, args, kwargs))


async def task_worker_loop(worker_id: int) -> None:
    logger.info("Worker %d arrancado", worker_id)
    while True:
        task = await TASK_QUEUE.get()
        try:
            await task.handler(*task.args, **task.kwargs)
        except Exception:
            logger.exception("Worker %d crash en task chat=%d", worker_id, task.chat_id)
        finally:
            TASK_QUEUE.task_done()
```

- [ ] **Step 2: Smoke-test import**

Run: `python -c "from core.worker import enqueue_task, task_worker_loop; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add core/worker.py
git commit -m "feat(worker): add task queue and worker pool"
```

---

### Task 16: Wire workers in `bot.py` via `post_init` callback

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add `on_startup` callback and builder update**

Open `bot.py`. Above `def main() -> None:` add:
```python
from telegram.ext import Application
from core.worker import task_worker_loop


async def on_startup(app: Application) -> None:
    worker_count = int(os.environ.get("WORKER_COUNT", "2"))
    for i in range(worker_count):
        app.create_task(task_worker_loop(i), name=f"worker-{i}")
    logger.info("Lanzados %d workers", worker_count)
```

Inside `main()`, replace:
```python
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
```
with:
```python
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .concurrent_updates(True)
        .post_init(on_startup)
        .build()
    )
```

- [ ] **Step 2: Smoke-test startup**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat(worker): launch worker pool via post_init"
```

---

### Task 17: Update handlers to enqueue `run_claude` instead of calling it directly

**Files:**
- Modify: `handlers/text.py`
- Modify: `handlers/voice.py`
- Modify: `handlers/media.py`

- [ ] **Step 1: Update `handlers/text.py`**

In `handlers/text.py`, add at top of imports:
```python
from core.worker import enqueue_task
```

In `handle_text`, replace:
```python
    await run_claude(update, context, session, text, source="text")
```
with:
```python
    await update.message.reply_text("⏳ Tarea recibida, procesando...")
    await enqueue_task(
        session.chat_id,
        run_claude,
        update, context, session, text, "text",
    )
```

- [ ] **Step 2: Update `handlers/voice.py`**

In `handlers/voice.py`, add import:
```python
from core.worker import enqueue_task
```

Find the call to `run_claude` inside `handle_voice` (the original is around line 886 of pre-refactor `bot.py`, inside the try block after transcription). Replace:
```python
        await run_claude(update, context, session, text, source="voice")
```
with:
```python
        await update.message.reply_text("⏳ Tarea recibida, procesando...")
        await enqueue_task(
            session.chat_id,
            run_claude,
            update, context, session, text, "voice",
        )
```

- [ ] **Step 3: Update `handlers/media.py`**

In `handlers/media.py`, add import:
```python
from core.worker import enqueue_task
```

**Important:** `handle_photo` and `handle_document` both download a file, embed its path in the prompt, and clean up after `run_claude` finishes via a `try/finally` block. In the pre-refactor `bot.py` (lines 911 and 936), both handlers call `run_claude(..., source="text")` — NOT `"photo"` or `"document"`. The `source` kwarg only has three valid values in `send_reply`: `"text"`, `"voice"`, and the auto path keyed off voice. Preserve `"text"` exactly — a wrong label will silently flip voice-mode TTS behavior.

Since `run_claude` is now enqueued, the handler can't `await` it and clean up inline. Wrap it in a closure that runs cleanup in a `finally` block and enqueue the wrapper instead. Apply to both `handle_photo` and `handle_document`:

```python
    paths_to_clean = [local_path]

    async def run_with_cleanup(*args, **kwargs):
        try:
            await run_claude(*args, **kwargs)
        finally:
            for p in paths_to_clean:
                cleanup_file(p)

    await update.message.reply_text("⏳ Tarea recibida, procesando...")
    await enqueue_task(
        session.chat_id,
        run_with_cleanup,
        update, context, session, prompt, "text",
    )
```

Remove the original `try: await run_claude(...) finally: cleanup_file(local_path)` block from both handler bodies — the closure replaces it.

**Do NOT apply this closure to `handle_voice`.** In `bot.py` lines 869-880, `handle_voice` cleans up its temp transcription file in a `finally` block *before* calling `run_claude`, not after. The voice handler is already correct as-is; only Step 2 above (swap `await run_claude(...)` for `await enqueue_task(...)`) applies. Do not remove or move the existing `os.remove(local_path)` in voice.

- [ ] **Step 4: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add handlers/text.py handlers/voice.py handlers/media.py
git commit -m "feat(worker): route all handlers through task queue with deferred cleanup"
```

---

### Task 18: Manual concurrency test (end of Phase 1)

No files change. Validation checkpoint.

- [ ] **Step 1: Restart the bot**

Restart via launchd or direct `python bot.py`. Verify "Lanzados 2 workers" appears in the logs.

- [ ] **Step 2: Send 3 text messages in rapid succession from Telegram**

Expected: each gets an immediate "⏳ Tarea recibida, procesando..." reply. The first 2 process in parallel (2 workers). The 3rd queues and processes when a worker frees up.

- [ ] **Step 3: Send a long-running task: "lee todos los archivos .md en /Users/lara/proyectos y dime cuántos hay"**

Expected: no Telegram timeout. Response arrives when ready (possibly 30-60s later).

- [ ] **Step 4: While the long task runs, send another short message**

Expected: queues up, processes after the long one finishes (SESSION_LOCKS preserves serialization per chat).

- [ ] **Step 5: Phase 1 complete — tag it**

```bash
git tag phase-1-complete
```

---

# PHASE 2 — Credenciales en macOS Keychain

---

### Task 19: Add `keyring` to `requirements.txt`

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append to `requirements.txt`**

Open `requirements.txt`. Append at end (preserving version-pinning style of the file):
```
keyring
```

- [ ] **Step 2: Install the dependency**

Run: `source venv/bin/activate && pip install keyring`
Expected: installation success.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add keyring for macOS Keychain credential storage"
```

---

### Task 20: Create `core/credentials.py`

**Files:**
- Create: `core/credentials.py`

- [ ] **Step 1: Write `core/credentials.py`**

Write: `core/credentials.py`:
```python
"""Lectura/escritura de secretos en macOS Keychain.

Servicio: telegram-claude-bot
Cuentas: TELEGRAM_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY
"""
import logging
import os

import keyring

logger = logging.getLogger(__name__)

SERVICE = "telegram-claude-bot"


def get_secret(name: str) -> str:
    value = keyring.get_password(SERVICE, name)
    if not value:
        raise RuntimeError(
            f"Secret '{name}' no encontrado en Keychain. "
            f"Ejecuta: python setup_credentials.py"
        )
    return value


def set_secret(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)


def export_to_env(*names: str) -> None:
    """Carga secretos del Keychain al os.environ del proceso.

    Necesario para que el subproceso `claude` (CLI) herede
    ANTHROPIC_API_KEY del entorno.
    """
    for name in names:
        os.environ[name] = get_secret(name)
```

- [ ] **Step 2: Smoke-test import**

Run: `python -c "from core.credentials import get_secret, set_secret, export_to_env; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add core/credentials.py
git commit -m "feat(keychain): add credential helpers backed by macOS Keychain"
```

---

### Task 21: Create `setup_credentials.py` bootstrap script

**Files:**
- Create: `setup_credentials.py`

- [ ] **Step 1: Write `setup_credentials.py`**

Write: `setup_credentials.py`:
```python
"""Bootstrap interactivo del Keychain para el bot.

Uso:
    python setup_credentials.py

Pide cada secreto con getpass (input oculto) y lo guarda en macOS Keychain.
Si encuentra un .env legacy con TELEGRAM_TOKEN, ofrece migrar automáticamente.
"""
from getpass import getpass
from pathlib import Path

import keyring

SERVICE = "telegram-claude-bot"
SECRETS = ["TELEGRAM_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]


def maybe_migrate_from_env() -> dict[str, str]:
    """Si existe .env con secretos legacy, los lee para migrar al Keychain."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return {}
    legacy = {}
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            if k.strip() in SECRETS:
                legacy[k.strip()] = v.strip()
    return legacy


def main() -> None:
    print("\n== Bootstrap del Keychain (telegram-claude-bot) ==\n")
    legacy = maybe_migrate_from_env()
    if legacy:
        print(f"Encontrados {len(legacy)} secretos en .env legacy.")
        ans = input("¿Migrar al Keychain? [Y/n]: ").strip().lower()
        if ans in ("", "y", "yes"):
            for name, value in legacy.items():
                keyring.set_password(SERVICE, name, value)
                print(f"  ✅ {name} migrado ({len(value)} chars)")
            print("\nMigración completa. Recuerda borrar las líneas sensibles del .env.")
            return

    # Bootstrap interactivo
    for name in SECRETS:
        existing = keyring.get_password(SERVICE, name)
        if existing:
            ans = input(f"{name} ya existe en Keychain. ¿Sobrescribir? [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                continue
        value = getpass(f"{name}: ").strip()
        if not value:
            print(f"  ⚠️  {name} vacío, saltado.")
            continue
        keyring.set_password(SERVICE, name, value)
        print(f"  ✅ {name} guardado ({len(value)} chars)")

    print("\n✅ Keychain configurado. Ya puedes arrancar el bot.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it (interactive — Lara does this manually)**

Run: `python setup_credentials.py`
Expected: either "migrated" message (if `.env` has legacy secrets) or interactive prompts. Verify in Keychain Access app that `telegram-claude-bot` service has 3 entries.

- [ ] **Step 3: Commit**

```bash
git add setup_credentials.py
git commit -m "feat(keychain): add setup_credentials.py bootstrap with .env migration"
```

---

### Task 22: Switch `bot.py` to read secrets from Keychain

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Update `bot.py` to use Keychain**

Open `bot.py`. Replace:
```python
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
```
with:
```python
from core.credentials import export_to_env, get_secret

# Exporta los secretos del Keychain al os.environ para que el subproceso
# `claude` (Claude Code CLI) herede ANTHROPIC_API_KEY.
export_to_env("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
TELEGRAM_TOKEN = get_secret("TELEGRAM_TOKEN")
```

**Also update `core/audio.py`** to read `OPENAI_API_KEY` from the now-populated `os.environ` (it already does, because it reads from `core.config.OPENAI_API_KEY` which is `os.environ.get("OPENAI_API_KEY")`). **Order matters:** `core.config` is imported before `export_to_env` runs. To fix, change `core/audio.py` to read lazily:

Open `core/audio.py`. Replace:
```python
openai_client: Optional[AsyncOpenAI] = (
    AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
)
```
with:
```python
def _build_openai_client() -> Optional[AsyncOpenAI]:
    key = os.environ.get("OPENAI_API_KEY") or OPENAI_API_KEY
    return AsyncOpenAI(api_key=key) if key else None


openai_client: Optional[AsyncOpenAI] = None  # inicializado por get_openai_client()


def get_openai_client() -> Optional[AsyncOpenAI]:
    """Devuelve el cliente, inicializándolo perezosamente al primer uso.

    Necesario porque Keychain export_to_env() corre después del import de config.
    """
    global openai_client
    if openai_client is None:
        openai_client = _build_openai_client()
    return openai_client
```

And add `import os` at the top of `core/audio.py` if missing.

Update `transcribe_audio` and `synthesize_voice` to call `get_openai_client()` instead of referencing module-level `openai_client`:

```python
async def transcribe_audio(file_path: str) -> str:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    with open(file_path, "rb") as f:
        result = await client.audio.transcriptions.create(model=STT_MODEL, file=f)
    return result.text


async def synthesize_voice(text: str, out_path: str) -> None:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    text = text[:4000]
    response = await client.audio.speech.create(
        model=TTS_MODEL, voice=TTS_VOICE, input=text, response_format="opus",
    )
    response.write_to_file(out_path)
```

**Also update `core/runner.py`** — `send_reply` checks `openai_client is not None` at the top. Fix both the runtime check AND the import line:

Open `core/runner.py`. Replace the import line:
```python
from core.audio import openai_client, transcribe_audio, synthesize_voice
```
with:
```python
from core.audio import get_openai_client, transcribe_audio, synthesize_voice
```
(drop `openai_client`; keep `transcribe_audio` and `synthesize_voice`.)

Then inside `send_reply`, replace every `openai_client is not None` check with `get_openai_client() is not None`, and every bare `openai_client` call-site with a fresh `get_openai_client()` call (typically only 1–2 lines — verify with `grep -n openai_client core/runner.py`).

**Also update `handlers/voice.py`** — same pattern. Replace the import line:
```python
from core.audio import openai_client, transcribe_audio
```
with:
```python
from core.audio import get_openai_client, transcribe_audio
```
and swap any `openai_client` reference in the body for a fresh `get_openai_client()` call. Verify with `grep -n openai_client handlers/voice.py` — expect zero matches after the edit.

**Load-bearing contract (document this in a comment at the top of `core/audio.py`):**

```python
# IMPORTANT: this module is imported BEFORE core/credentials.export_to_env runs.
# That means the module-level `OPENAI_API_KEY` imported from core.config is
# bound to the PRE-Keychain environment and may be empty. Never bind
# `OPENAI_API_KEY` by name at module scope in any consumer module — always
# call `get_openai_client()` (which re-reads os.environ at first use) or
# `os.environ.get("OPENAI_API_KEY")` at runtime. The same applies to any
# future secret that gets exported from Keychain in bot.py startup.
```

No other module in the codebase may bind `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `TELEGRAM_TOKEN` at module scope after Phase 2 — these are only safe to read from `os.environ` at runtime, inside functions, because the Keychain export in `bot.py` runs after module imports have already resolved.

- [ ] **Step 2: Smoke-test imports**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`. If `RuntimeError: Secret 'TELEGRAM_TOKEN' no encontrado`, run `python setup_credentials.py` first.

- [ ] **Step 3: Run the bot briefly**

Run: `python bot.py` and Ctrl-C after "Bot arrancado".
Expected: clean startup, no Keychain errors.

- [ ] **Step 4: Clean secrets from `.env`**

Open `.env`. Remove (or comment out) the lines:
- `TELEGRAM_TOKEN=...`
- `ANTHROPIC_API_KEY=...`
- `OPENAI_API_KEY=...`

Keep the non-sensitive vars (`ALLOWED_USER_ID`, `WORKING_DIR`, `TTS_VOICE`, etc.).

Run again: `python bot.py` — confirm it still starts without the `.env` secrets.

- [ ] **Step 5: Commit**

```bash
git add bot.py core/audio.py core/runner.py handlers/voice.py .env
git commit -m "feat(keychain): read TELEGRAM/ANTHROPIC/OPENAI from Keychain instead of .env"
```

---

### Task 23: Phase 2 validation + tag

- [ ] **Step 1: Verify Keychain has all 3 secrets**

Run: `security find-generic-password -s telegram-claude-bot -a TELEGRAM_TOKEN -w | wc -c`
Expected: a non-zero byte count.

- [ ] **Step 2: Run bot and send a test message**

Expected: bot responds normally. Confirms both Telegram connection (TELEGRAM_TOKEN) and Claude (ANTHROPIC_API_KEY) work from Keychain.

- [ ] **Step 3: Tag**

```bash
git tag phase-2-complete
```

---

# PHASE 3 — Multi-instance bootstrap (bootstrap.sh + plist + README)

---

### Task 24: Create `tools/` package skeleton with autoloader

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/custom/.gitkeep`
- Create: `tools/custom/README.md`

- [ ] **Step 1: Create `tools/__init__.py` with autoloader**

Write: `tools/__init__.py`:
```python
"""Autoloader de tools.

Descubre automáticamente todas las @tool decoradas en:
- tools/browser_tools.py (Fase 4)
- tools/ollama_tools.py  (Fase 6)
- tools/custom/*.py       (cada usuario, sin tocar el repo común)

Devuelve una lista de tool objects para inyectar en ClaudeAgentOptions.
"""
import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_all_tools() -> list:
    tools = []
    pkg_dir = Path(__file__).parent

    # Tools nativas (browser, ollama) — aún no existen en Fase 3
    for module_name in ("browser_tools", "ollama_tools"):
        try:
            mod = importlib.import_module(f"tools.{module_name}")
            tools.extend(getattr(mod, "TOOLS", []))
        except ImportError:
            logger.debug("tools.%s no disponible aún", module_name)

    # Tools custom del usuario
    custom_dir = pkg_dir / "custom"
    if custom_dir.exists():
        for path in sorted(custom_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"tools.custom.{path.stem}")
                tools.extend(getattr(mod, "TOOLS", []))
            except Exception:
                logger.exception("Error cargando tools.custom.%s", path.stem)

    logger.info("Autoloader cargó %d tools", len(tools))
    return tools
```

- [ ] **Step 2: Create placeholders for the custom directory**

Write: `tools/custom/.gitkeep` with empty content.

Write: `tools/custom/README.md`:
```markdown
# Tools personalizadas

Coloca aquí tus herramientas propias. El bot las descubre y carga
automáticamente al arrancar.

## Ejemplo: `tools/custom/mi_tool.py`

```python
from claude_agent_sdk import tool

@tool(
    name="mi_tool",
    description="Hace algo útil para mi flujo de trabajo.",
    input_schema={"type": "object", "properties": {"texto": {"type": "string"}}},
)
async def mi_tool(texto: str) -> str:
    return f"procesé: {texto}"

TOOLS = [mi_tool]
```

El autoloader en `tools/__init__.py` busca una constante `TOOLS` en
cada módulo del directorio `tools/custom/`.

Reinicia el bot con:
`launchctl kickstart -k gui/$(id -u)/com.$(whoami).telegram-claude-bot`

Tu tool aparecerá disponible para Claude automáticamente.
```

- [ ] **Step 3: Create `tools/custom/__init__.py`**

Write: `tools/custom/__init__.py` with empty content (so Python treats it as a package).

- [ ] **Step 4: Smoke-test**

Run: `python -c "from tools import load_all_tools; print(load_all_tools())"`
Expected: `Autoloader cargó 0 tools` in logs, returns `[]`.

- [ ] **Step 5: Commit**

```bash
git add tools/__init__.py tools/custom/__init__.py tools/custom/.gitkeep tools/custom/README.md
git commit -m "feat(tools): add tools/ package with autoloader and custom/ directory"
```

---

### Task 25: Wire `load_all_tools()` into `core/runner.py` options_kwargs

**Files:**
- Modify: `core/runner.py`

- [ ] **Step 1: Update `ensure_client` to pass `tools=` kwarg**

Open `core/runner.py`. Add import at top:
```python
from tools import load_all_tools
```

Inside `ensure_client`, find the `options_kwargs = dict(...)` block and add a `tools=` entry:
```python
        options_kwargs = dict(
            cwd=session.cwd,
            permission_mode="default" if session.safe_mode else "bypassPermissions",
            setting_sources=["user", "project", "local"],
            model=session.current_model,
            fallback_model=fallback,
            system_prompt=build_system_prompt(),
            stderr=lambda line: logger.error("CLAUDE_CLI: %s", line),
            tools=load_all_tools(),            # ← NUEVO
        )
```

**Note:** in Phase 3 this is a no-op (returns `[]`). Fases 4 y 6 añadirán módulos y estas líneas se activan solas sin volver a tocar `runner.py`.

- [ ] **Step 2: Smoke-test**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add core/runner.py
git commit -m "feat(tools): wire autoloader into runner options_kwargs"
```

---

### Task 26: Create `system_prompt.example.md` template

**Files:**
- Create: `system_prompt.example.md`

- [ ] **Step 1: Write `system_prompt.example.md`**

Write: `system_prompt.example.md`:
```markdown
# System prompt del bot

Soy el asistente personal de [TU NOMBRE], accesible vía Telegram desde mi móvil.
[TU NOMBRE] trabaja en [TU ÁREA: copywriting, marketing, ingeniería, diseño…].

Tengo acceso a su Mac mini: archivos, terminal, git, deploys, búsqueda en internet,
y skills/MCPs configurados a nivel global.

## Reglas de comunicación
- Responder SIEMPRE en español, salvo que [TU NOMBRE] escriba en otro idioma.
- Directo y conciso. Sin preámbulos, sin resúmenes innecesarios al final.
- Si una tarea tiene varios pasos, ejecutarlos sin pedir permiso (excepto operaciones destructivas).
- Cuando no sepa algo, decirlo. No inventar APIs, archivos ni rutas.
- Diffs mínimos al editar código.

[Añade aquí lo que quieras: tu rol específico, tu tono, herramientas que prefieres, etc.]
```

- [ ] **Step 2: Update `core/system_prompt.py` to load the intro from a file**

Open `core/system_prompt.py`. Add `PROJECT_DIR` to the config import and replace the entire `build_system_prompt` body so the intro paragraph comes from a file instead of being hardcoded. The CAG injection and global `CLAUDE.md` injection stay exactly as they were in Task 5 — only the intro source changes.

Replace the existing import line:
```python
from core.config import GLOBAL_CLAUDE_MD, KNOWLEDGE_DIR
```
with:
```python
from core.config import GLOBAL_CLAUDE_MD, KNOWLEDGE_DIR, PROJECT_DIR
```

Then replace the **entire** `build_system_prompt` function body with this exact code:

```python
def build_system_prompt() -> str:
    knowledge = load_knowledge_blocks()
    claude_md = read_file_safe(GLOBAL_CLAUDE_MD).strip()

    intro_path = f"{PROJECT_DIR}/system_prompt.md"
    fallback_path = f"{PROJECT_DIR}/system_prompt.example.md"
    intro = read_file_safe(intro_path).strip() or read_file_safe(fallback_path).strip()

    parts: list[str] = []
    if intro:
        parts.append(intro)
    parts += [
        "",
        "Memoria CAG — cómo funciona:",
        f"- Tus archivos de memoria viven en {KNOWLEDGE_DIR}/*.md.",
        "- Te los inyecto todos abajo en cada conversación (son tu contexto persistente).",
        "- Cuando aprendas algo importante sobre el dueño del bot, sus proyectos, personas, preferencias o decisiones, "
        "  ACTUALIZA el archivo correspondiente con Edit/Write:",
        "    · projects.md → estado, decisiones y próximos pasos por proyecto",
        "    · people.md → nuevas personas, clientes, colaboradores",
        "    · preferences.md → reglas de trabajo y comunicación",
        "    · decisions.md → decisiones importantes con contexto y razón",
        "    · MEMORY.md → hechos dinámicos que no encajan en los anteriores",
        "- No guardes cosas triviales, efímeras o derivables del estado actual del repo.",
        "- Usa formato de fecha absoluto (YYYY-MM-DD), nunca relativo.",
    ]

    if knowledge:
        parts += ["", "========= BASE DE CONOCIMIENTO ========="]
        for name, content in knowledge:
            parts += [f"", f"--- {name} ---", content]
        parts += ["", "========= FIN BASE DE CONOCIMIENTO ========="]

    if claude_md:
        parts += [
            "",
            "Reglas de trabajo (del CLAUDE.md global, deben respetarse SIEMPRE en tareas de código):",
            "=== CLAUDE.md ===",
            claude_md,
            "=== FIN CLAUDE.md ===",
        ]

    return "\n".join(parts)
```

**Notes on the diff against Task 5:**
- The hardcoded "Eres el asistente personal de Lara Aycart…" plus "Reglas de comunicación…" block is gone. Those lines now live in `system_prompt.md` / `system_prompt.example.md` (see Step 1).
- The CAG-memory instructions, the CAG-block injection, and the CLAUDE.md injection are preserved verbatim, only the opening string `Reglas de trabajo de Lara` becomes the generic `Reglas de trabajo` so Task 31's fork scenario reads cleanly.
- Phase 3 does not touch `DOWNLOAD_DIR`, `SESSIONS_FILE`, or any other symbol — only this function body and the `core.config` import line.

- [ ] **Step 3: Smoke-test**

Run: `python -c "from core.system_prompt import build_system_prompt; p = build_system_prompt(); print('len:', len(p)); assert 'asistente personal' in p or '[TU NOMBRE]' in p"`
Expected: `len: <positive number>`, no assertion error.

- [ ] **Step 4: Commit**

```bash
git add system_prompt.example.md core/system_prompt.py
git commit -m "feat(multi-instance): add system_prompt.example.md template and loader fallback"
```

---

### Task 27: Create `.gitignore` for personal data

**Files:**
- Create or Modify: `.gitignore`

- [ ] **Step 1: Check current `.gitignore`**

Run: `cat .gitignore 2>/dev/null || echo "no .gitignore"`

- [ ] **Step 2: Write the final `.gitignore`**

Write: `.gitignore`:
```
# Datos personales del dueño del bot — NUNCA al repo común
.env
sessions.json
memory/knowledge/*.md
!memory/knowledge/.keep
system_prompt.md
tools/custom/*
!tools/custom/.gitkeep
!tools/custom/README.md
!tools/custom/__init__.py
*.plist
!*.plist.template

# Logs
*.log
*.err.log
bot.log*

# Python
__pycache__/
*.pyc
.venv/
venv/

# Playwright user data
.playwright_user_data/

# Downloads temporales
downloads/*
!downloads/.keep
```

- [ ] **Step 3: Create `memory/knowledge/.keep` and `downloads/.keep`**

Run: `touch memory/knowledge/.keep downloads/.keep`
(Use the Write tool with empty content if Bash touch is unavailable.)

- [ ] **Step 4: Untrack personal files that may have been committed previously**

Run: `git rm --cached sessions.json .env 2>/dev/null || true`
Run: `git rm --cached memory/knowledge/*.md 2>/dev/null || true`

Expected: files remain on disk, just untracked from git.

- [ ] **Step 5: Verify**

Run: `git status`
Expected: `.gitignore` is new/modified, and the previously-tracked personal files show as deleted from the index (but still exist on disk).

- [ ] **Step 6: Commit**

```bash
git add .gitignore memory/knowledge/.keep downloads/.keep
git commit -m "chore: add .gitignore protecting personal data (keychain-friendly)"
```

---

### Task 28: Create `com.telegram-claude-bot.plist.template`

**Files:**
- Create: `com.telegram-claude-bot.plist.template`

- [ ] **Step 1: Write the template**

Write: `com.telegram-claude-bot.plist.template`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>__LABEL__</string>

    <key>ProgramArguments</key>
    <array>
        <string>__PYTHON__</string>
        <string>__BOT_PY__</string>
    </array>

    <key>WorkingDirectory</key>
    <string>__WORKING_DIR__</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/Users/__USER__/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>__WORKING_DIR__/bot.log</string>
    <key>StandardErrorPath</key>
    <string>__WORKING_DIR__/bot.err.log</string>
</dict>
</plist>
```

- [ ] **Step 2: Commit**

```bash
git add com.telegram-claude-bot.plist.template
git commit -m "feat(multi-instance): add plist template for launchd"
```

---

### Task 29: Create `bootstrap.sh`

**Files:**
- Create: `bootstrap.sh`

- [ ] **Step 1: Write `bootstrap.sh`**

Write: `bootstrap.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# bootstrap.sh — instala el telegram-claude-bot en una Mac nueva.
# Requiere: macOS, Python 3.10+, brew, claude-code CLI ya instalado.
# Uso: ./bootstrap.sh

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_LABEL="com.$(whoami).telegram-claude-bot"
PLIST_TARGET="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
PLIST_TEMPLATE="${REPO_DIR}/com.telegram-claude-bot.plist.template"

echo "==> Bootstrap telegram-claude-bot en $REPO_DIR"
echo "==> Usuario macOS: $(whoami)"
echo

# 1. Verificar dependencias del sistema
command -v python3 >/dev/null || { echo "❌ Falta python3"; exit 1; }
command -v claude >/dev/null || { echo "❌ Falta claude-code CLI. Instala desde https://claude.com/claude-code"; exit 1; }
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo "❌ Python 3.10+ requerido (tienes $PY_VER)"
    exit 1
fi

# 2. Crear venv
if [[ ! -d "$REPO_DIR/venv" ]]; then
    echo "==> Creando venv"
    python3 -m venv "$REPO_DIR/venv"
fi
# shellcheck disable=SC1091
source "$REPO_DIR/venv/bin/activate"

# 3. Instalar requirements
echo "==> Instalando requirements"
pip install --upgrade pip
pip install -r "$REPO_DIR/requirements.txt"

# 4. Instalar Playwright Chromium (Fase 4 — opcional)
if grep -q '^playwright' "$REPO_DIR/requirements.txt"; then
    echo "==> Instalando Playwright Chromium"
    python -m playwright install chromium || echo "⚠️  Playwright install falló (Fase 4 no funcionará)"
fi

# 5. Bootstrap del Keychain
if ! python -c "import keyring; assert keyring.get_password('telegram-claude-bot', 'TELEGRAM_TOKEN')" 2>/dev/null; then
    echo "==> Configurando Keychain"
    python "$REPO_DIR/setup_credentials.py"
else
    echo "==> Keychain ya configurado"
fi

# 6. Crear .env desde .env.example si no existe
if [[ ! -f "$REPO_DIR/.env" && -f "$REPO_DIR/.env.example" ]]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    echo "==> .env creado desde .env.example. Edítalo si quieres cambiar WORKING_DIR, TTS, etc."
fi

# 7. Copiar system_prompt.md desde example si no existe
if [[ ! -f "$REPO_DIR/system_prompt.md" ]]; then
    cp "$REPO_DIR/system_prompt.example.md" "$REPO_DIR/system_prompt.md"
    echo "==> system_prompt.md creado. Edítalo para personalizar el rol del bot."
fi

# 8. Generar plist desde template
sed \
    -e "s|__LABEL__|${PLIST_LABEL}|g" \
    -e "s|__PYTHON__|${REPO_DIR}/venv/bin/python|g" \
    -e "s|__BOT_PY__|${REPO_DIR}/bot.py|g" \
    -e "s|__WORKING_DIR__|${REPO_DIR}|g" \
    -e "s|__USER__|$(whoami)|g" \
    "$PLIST_TEMPLATE" > "$PLIST_TARGET"
echo "==> plist generado en $PLIST_TARGET"

# 9. Cargar launchd
launchctl unload "$PLIST_TARGET" 2>/dev/null || true
launchctl load "$PLIST_TARGET"
echo "==> Bot cargado en launchd. Verifica con: tail -f $REPO_DIR/bot.log"

echo
echo "✅ Bootstrap completo."
echo "   Logs: $REPO_DIR/bot.log"
echo "   Personaliza: system_prompt.md, memory/knowledge/, tools/custom/"
echo "   Mission Control: http://localhost:8080/status"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x bootstrap.sh`

- [ ] **Step 3: Validate shellcheck (if available)**

Run: `command -v shellcheck && shellcheck bootstrap.sh || echo "shellcheck skipped"`
Expected: either no findings or "skipped".

- [ ] **Step 4: Commit**

```bash
git add bootstrap.sh
git commit -m "feat(multi-instance): add bootstrap.sh installer for clean Mac setup"
```

---

### Task 30: Write a `.env.example`

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Write `.env.example`**

Write: `.env.example`:
```bash
# Vars NO sensibles del bot. Los secretos (TELEGRAM_TOKEN, ANTHROPIC_API_KEY,
# OPENAI_API_KEY) viven en macOS Keychain — usa setup_credentials.py.

# ID del usuario de Telegram autorizado (entero). Abrir @userinfobot para obtenerlo.
ALLOWED_USER_ID=123456789

# Directorio raíz de trabajo del bot.
WORKING_DIR=/Users/lara/proyectos

# Audio (OpenAI TTS/STT)
TTS_VOICE=nova
TTS_MODEL=tts-1
STT_MODEL=whisper-1

# Pool de workers que consumen la task queue
WORKER_COUNT=2

# Ollama (Fase 6) — cambiar si corres ollama en otro host/puerto
# OLLAMA_HOST=http://localhost:11434
# OLLAMA_DEFAULT_MODEL=llama3.1:8b

# Mission Control (Fase 7)
# MISSION_CONTROL_PORT=8080
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add .env.example with non-sensitive config template"
```

---

### Task 31: Update `README.md` with multi-instance docs

**Files:**
- Modify (or create): `README.md`

- [ ] **Step 1: Check current README**

Run: `ls README.md 2>/dev/null && cat README.md || echo "no README"`

- [ ] **Step 2: Write the new README**

Write: `README.md`:
```markdown
# telegram-claude-bot

Bot de Telegram que delega cada mensaje a Claude vía `claude-agent-sdk`.
Opera tu Mac mini desde el móvil: archivos, terminal, git, deploys, búsqueda web.

## Qué hace

- Procesa texto, voz (Whisper), imágenes y documentos.
- Auto-routing entre Haiku/Sonnet/Opus según complejidad.
- Memoria CAG: lee `memory/knowledge/*.md` en cada system prompt.
- Modo autónomo por defecto (`bypassPermissions`); `/safe on` pide confirmaciones.
- Task queue asíncrona: mensajes no bloquean handlers, se procesan en worker pool.
- Credenciales en macOS Keychain (no `.env`).
- Multi-instancia: cada miembro del equipo tiene su propio bot, su memoria, sus tools.

## Requisitos

- macOS
- Python 3.10+
- `claude-code` CLI instalado (https://claude.com/claude-code)
- `brew`
- Mac mini o laptop (idealmente 24/7 para estar siempre disponible)

## Instalación rápida

```bash
git clone <repo-url> ~/telegram-claude-bot
cd ~/telegram-claude-bot
./bootstrap.sh
```

El script:
1. Crea un venv y instala dependencias.
2. Instala Playwright Chromium (Fase 4).
3. Bootstrap interactivo del Keychain (pide tus tokens con input oculto).
4. Crea `.env` y `system_prompt.md` desde los examples.
5. Genera un plist launchd con label `com.$(whoami).telegram-claude-bot`.
6. Carga el servicio.

## Personalización por miembro del equipo

Cada uno de estos archivos es personal (ignorado por git, no se pisa con `git pull`):

| Archivo | Para qué |
|---|---|
| `system_prompt.md` | Rol y tono del bot. Empieza copiando `system_prompt.example.md`. |
| `memory/knowledge/*.md` | Memoria persistente: proyectos, gente, decisiones, preferencias. |
| `tools/custom/*.py` | Tus herramientas propias (`@tool` decoradas). Se cargan automáticamente. |
| `.env` | Variables no sensibles (WORKING_DIR, TTS_VOICE, WORKER_COUNT). |

Los secretos (TELEGRAM_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY) viven en
macOS Keychain bajo el servicio `telegram-claude-bot`. Gestionar con
`python setup_credentials.py`.

## Operación

```bash
# Logs
tail -f bot.log

# Reiniciar
launchctl kickstart -k gui/$(id -u)/com.$(whoami).telegram-claude-bot

# Parar
launchctl unload ~/Library/LaunchAgents/com.$(whoami).telegram-claude-bot.plist

# Arrancar
launchctl load ~/Library/LaunchAgents/com.$(whoami).telegram-claude-bot.plist
```

### Comandos del bot

`/start /pwd /cd /reset /voice /safe /think /model /cost`

### Mission Control (Fase 7)

`curl http://localhost:8080/status` → JSON con uptime, queue, sesiones, coste.

## Actualización (`git pull`)

Tus datos personales están en `.gitignore`. `git pull` no los pisa.

```bash
cd ~/telegram-claude-bot
git pull
source venv/bin/activate
pip install -r requirements.txt
# Si hay nuevos secretos a pedir:
python setup_credentials.py
launchctl kickstart -k gui/$(id -u)/com.$(whoami).telegram-claude-bot
```

## Arquitectura

Ver `docs/superpowers/specs/2026-04-09-telegram-bot-evolution-design.md`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with multi-instance install and operation docs"
```

---

### Task 32: Phase 3 validation + tag

- [ ] **Step 1: Test `bootstrap.sh` on a clean copy**

Copy the repo to a temp location:
```bash
mkdir -p /tmp/bootstrap-test
cp -r /Users/lara/telegram-claude-bot/. /tmp/bootstrap-test/
# Remove state from the copy:
rm -rf /tmp/bootstrap-test/venv /tmp/bootstrap-test/.env /tmp/bootstrap-test/sessions.json
cd /tmp/bootstrap-test
./bootstrap.sh
```

Expected: walks through venv creation, pip install, Keychain already configured message (Keychain is global, shared between copies), plist generated at `~/Library/LaunchAgents/com.lara.telegram-claude-bot.plist`. If a plist already exists for Lara's main bot, this step collides — use a test user or skip this validation.

**Alternative (safer):** dry-run only: `bash -n bootstrap.sh && echo "syntax ok"` — verifies shell syntax without execution.

- [ ] **Step 2: Verify memory files aren't accidentally committed**

Run: `git status --ignored | head -30`
Expected: `memory/knowledge/*.md`, `system_prompt.md`, `sessions.json`, `.env` all listed as ignored.

- [ ] **Step 3: Tag**

```bash
git tag phase-3-complete
```

---

# PHASE 4 — Playwright persistent browser

---

### Task 33: Add `playwright` to requirements and install Chromium

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append to requirements**

Open `requirements.txt`. Append:
```
playwright
```

- [ ] **Step 2: Install**

Run: `source venv/bin/activate && pip install playwright && python -m playwright install chromium`
Expected: Chromium downloads to `~/Library/Caches/ms-playwright/`.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add playwright for persistent web navigation"
```

---

### Task 34: Create `tools/browser_tools.py`

**Files:**
- Create: `tools/browser_tools.py`

- [ ] **Step 1: Write `tools/browser_tools.py`**

Write: `tools/browser_tools.py`:
```python
"""Tools de navegación web persistente para el bot.

Usa Playwright en modo asíncrono con launch_persistent_context
para mantener sesiones de login entre reinicios.
"""
import asyncio
import logging
import os
from typing import Optional

from claude_agent_sdk import tool
from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

USER_DATA_DIR = os.environ.get(
    "PLAYWRIGHT_USER_DATA",
    os.path.expanduser("~/.playwright_user_data"),
)


class BrowserManager:
    _instance: Optional["BrowserManager"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.context: Optional[BrowserContext] = None
        self.playwright = None

    @classmethod
    async def get(cls) -> "BrowserManager":
        async with cls._lock:
            if cls._instance is None:
                cls._instance = BrowserManager()
                await cls._instance._init()
            return cls._instance

    async def _init(self):
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=True,
            viewport={"width": 1280, "height": 800},
        )

    async def new_page(self) -> Page:
        if not self.context:
            await self._init()
        return await self.context.new_page()

    async def shutdown(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()


@tool(
    name="browser_navigate",
    description=(
        "Navega a una URL y devuelve el texto visible de la página. "
        "Mantiene cookies y sesiones de login entre llamadas."
    ),
    input_schema={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
async def browser_navigate(url: str) -> str:
    bm = await BrowserManager.get()
    page = await bm.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        text = await page.evaluate("() => document.body.innerText")
        return text[:8000]
    finally:
        await page.close()


@tool(
    name="browser_click",
    description=(
        "Hace clic en un selector CSS de una URL y devuelve el texto resultante."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "selector": {"type": "string"},
        },
        "required": ["url", "selector"],
    },
)
async def browser_click(url: str, selector: str) -> str:
    bm = await BrowserManager.get()
    page = await bm.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.click(selector, timeout=10000)
        await page.wait_for_load_state("networkidle", timeout=10000)
        text = await page.evaluate("() => document.body.innerText")
        return text[:8000]
    finally:
        await page.close()


@tool(
    name="browser_extract",
    description="Extrae el contenido de un selector CSS específico de una URL.",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "selector": {"type": "string"},
        },
        "required": ["url", "selector"],
    },
)
async def browser_extract(url: str, selector: str) -> str:
    bm = await BrowserManager.get()
    page = await bm.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        elements = await page.query_selector_all(selector)
        texts = [await el.inner_text() for el in elements]
        return "\n---\n".join(texts)[:8000]
    finally:
        await page.close()


TOOLS = [browser_navigate, browser_click, browser_extract]
```

- [ ] **Step 2: Smoke-test import**

Run: `python -c "from tools.browser_tools import TOOLS; print(len(TOOLS))"`
Expected: `3`.

- [ ] **Step 3: Verify autoloader picks them up**

Run: `python -c "from tools import load_all_tools; print(len(load_all_tools()))"`
Expected: `3` (and `Autoloader cargó 3 tools` in logs).

- [ ] **Step 4: Commit**

```bash
git add tools/browser_tools.py
git commit -m "feat(browser): add persistent Playwright browser tools"
```

---

### Task 35: Phase 4 validation + tag

- [ ] **Step 1: Restart the bot**

Run: `launchctl kickstart -k gui/$(id -u)/com.$(whoami).telegram-claude-bot` (or direct `python bot.py`).
Expected: `Autoloader cargó 3 tools` in logs.

- [ ] **Step 2: Test navigation**

Send to the bot: `ve a https://es.wikipedia.org/wiki/Portada y dame el primer titular`
Expected: bot replies with actual content from Wikipedia, demonstrating `browser_navigate` worked.

- [ ] **Step 3: Tag**

```bash
git tag phase-4-complete
```

---

# PHASE 5 — Subagents with AgentDefinition

---

### Task 36: Create `agents/definitions.py`

**Files:**
- Create: `agents/__init__.py`
- Create: `agents/definitions.py`

- [ ] **Step 1: Create `agents/__init__.py`**

Write: `agents/__init__.py` empty.

- [ ] **Step 2: Write `agents/definitions.py`**

Write: `agents/definitions.py`:
```python
"""Definiciones de subagentes especializados.

Usados por el orquestador (ClaudeSDKClient principal) para delegar
tareas específicas a contextos aislados.
"""
from claude_agent_sdk import AgentDefinition

WEB_SURFER = AgentDefinition(
    description=(
        "Especialista en navegación web. Úsalo para buscar información en internet, "
        "investigar competidores, scrapear páginas, extraer datos estructurados de sitios, "
        "o cualquier tarea que requiera abrir múltiples URLs."
    ),
    prompt=(
        "Eres un agente especializado en navegación web. Tu trabajo es usar las herramientas "
        "browser_navigate, browser_click y browser_extract para investigar páginas web a fondo. "
        "Cuando termines, devuelve un resumen estructurado de lo que encontraste, citando URLs. "
        "No inventes información: si una página no carga o no tiene lo que buscas, dilo."
    ),
    tools=[
        "browser_navigate", "browser_click", "browser_extract",
        "WebFetch", "WebSearch", "Read",
    ],
    model="sonnet",
)

CODE_ANALYST = AgentDefinition(
    description=(
        "Especialista en análisis de código y procesamiento de grandes cantidades de texto. "
        "Úsalo para analizar repositorios, encontrar patrones, hacer auditorías de código, "
        "o procesar archivos largos sin saturar el contexto del orquestador."
    ),
    prompt=(
        "Eres un agente especializado en análisis estático de código y texto. Tu trabajo es "
        "usar Read, Grep y Glob para explorar archivos y encontrar lo que el orquestador te pida. "
        "Devuelve respuestas concisas y estructuradas. No edites archivos — solo lectura."
    ),
    tools=["Read", "Grep", "Glob"],
    model="sonnet",
)

AGENTS = {
    "web-surfer": WEB_SURFER,
    "code-analyst": CODE_ANALYST,
}
```

- [ ] **Step 3: Smoke-test import**

Run: `python -c "from agents.definitions import AGENTS; print(list(AGENTS))"`
Expected: `['web-surfer', 'code-analyst']`. If `AttributeError: no attribute AgentDefinition`, the installed SDK version is too old. Check with `pip show claude-agent-sdk` and upgrade if needed.

- [ ] **Step 4: Verify SDK supports `agents=` kwarg (pre-flight check)**

Run: `python -c "from claude_agent_sdk import ClaudeAgentOptions; import inspect; print('agents' in inspect.signature(ClaudeAgentOptions).parameters)"`
Expected: `True`. If `False`, stop and upgrade `claude-agent-sdk` before proceeding to Task 37.

- [ ] **Step 5: Commit**

```bash
git add agents/__init__.py agents/definitions.py
git commit -m "feat(agents): add web-surfer and code-analyst subagent definitions"
```

---

### Task 37: Wire `agents=AGENTS` into `core/runner.py`

**Files:**
- Modify: `core/runner.py`

- [ ] **Step 1: Import AGENTS and add to options_kwargs**

Open `core/runner.py`. Add import at top:
```python
from agents.definitions import AGENTS
```

Inside `ensure_client`, update `options_kwargs`:
```python
        options_kwargs = dict(
            cwd=session.cwd,
            permission_mode="default" if session.safe_mode else "bypassPermissions",
            setting_sources=["user", "project", "local"],
            model=session.current_model,
            fallback_model=fallback,
            system_prompt=build_system_prompt(),
            stderr=lambda line: logger.error("CLAUDE_CLI: %s", line),
            tools=load_all_tools(),
            agents=AGENTS,                     # ← NUEVO en Fase 5
        )
```

- [ ] **Step 2: Smoke-test**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add core/runner.py
git commit -m "feat(agents): wire subagents into ClaudeAgentOptions"
```

---

### Task 38: Phase 5 validation + tag

- [ ] **Step 1: Restart bot and delegate a web task**

Restart. Send: `investiga 3 competidores de @Lara_regi_bot en internet (bots de Telegram que integren Claude) y compara sus features`.

Expected: orchestrator delegates to `web-surfer`, which uses `browser_navigate` (or WebFetch). Reply contains structured comparison.

- [ ] **Step 2: Delegate a code task**

Send: `audita todos los .py de /Users/lara/telegram-claude-bot/core y dime cuáles tienen más de 100 líneas`.

Expected: orchestrator delegates to `code-analyst`, which uses Grep/Glob/Read. Reply lists files.

- [ ] **Step 3: Tag**

```bash
git tag phase-5-complete
```

---

# PHASE 6 — Ollama hybrid tools

---

### Task 39: Add `httpx` to requirements (if not already transitive)

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Check if httpx is already installed**

Run: `python -c "import httpx; print(httpx.__version__)"`
Expected: if it prints a version, no change needed; if ImportError, add to requirements.

- [ ] **Step 2: Append to requirements.txt (only if needed)**

If httpx is not already installed:
```
httpx
```

- [ ] **Step 3: Install if needed**

Run: `source venv/bin/activate && pip install httpx`
Expected: success (or "already satisfied").

- [ ] **Step 4: Commit (only if requirements.txt changed)**

```bash
git add requirements.txt
git commit -m "deps: ensure httpx is explicit for Ollama client"
```

If requirements.txt wasn't modified, skip the commit.

---

### Task 40: Create `tools/ollama_tools.py`

**Files:**
- Create: `tools/ollama_tools.py`

- [ ] **Step 1: Write `tools/ollama_tools.py`**

Write: `tools/ollama_tools.py`:
```python
"""Tools de inferencia local vía Ollama.

Permite a Claude delegar tareas baratas y de gran volumen a modelos OSS
corriendo en localhost (Llama 3.1, Mistral, etc.) sin gastar tokens de Anthropic.
"""
import logging
import os

import httpx
from claude_agent_sdk import tool

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_DEFAULT_MODEL", "llama3.1:8b")
TIMEOUT = 120  # seg, modelos locales pueden ser lentos


async def _ollama_generate(prompt: str, model: str = DEFAULT_MODEL) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            r.raise_for_status()
            return r.json()["response"].strip()
        except httpx.ConnectError:
            return (
                f"⚠️ Ollama no responde en {OLLAMA_HOST}. "
                "Arranca con `ollama serve` o instala con `brew install ollama`."
            )
        except Exception as e:
            return f"⚠️ Error Ollama: {e}"


@tool(
    name="llama_summarize",
    description=(
        "Resume un texto largo usando un modelo local (Llama 3.1). Útil cuando "
        "tienes mucho texto y solo necesitas la idea principal — no gasta tokens de Anthropic."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "max_words": {"type": "integer", "default": 200},
        },
        "required": ["text"],
    },
)
async def llama_summarize(text: str, max_words: int = 200) -> str:
    prompt = (
        f"Resume el siguiente texto en máximo {max_words} palabras. "
        f"Sé directo, sin preámbulo:\n\n{text}"
    )
    return await _ollama_generate(prompt)


@tool(
    name="llama_classify",
    description=(
        "Clasifica un texto en una de varias categorías. Útil para triaging de "
        "mensajes, emails, tickets, etc., sin gastar tokens de Anthropic."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "categories": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["text", "categories"],
    },
)
async def llama_classify(text: str, categories: list[str]) -> str:
    cats = ", ".join(categories)
    prompt = (
        f"Clasifica el siguiente texto en UNA de estas categorías: {cats}.\n"
        f"Responde SOLO con el nombre exacto de la categoría, sin explicación.\n\n"
        f"Texto: {text}"
    )
    return await _ollama_generate(prompt)


@tool(
    name="llama_translate",
    description="Traduce un texto a otro idioma usando un modelo local.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "target_lang": {"type": "string"},
        },
        "required": ["text", "target_lang"],
    },
)
async def llama_translate(text: str, target_lang: str) -> str:
    prompt = (
        f"Traduce el siguiente texto a {target_lang}. "
        f"Responde SOLO con la traducción, sin explicación:\n\n{text}"
    )
    return await _ollama_generate(prompt)


TOOLS = [llama_summarize, llama_classify, llama_translate]
```

- [ ] **Step 2: Smoke-test**

Run: `python -c "from tools.ollama_tools import TOOLS; print(len(TOOLS))"`
Expected: `3`.

Run: `python -c "from tools import load_all_tools; print(len(load_all_tools()))"`
Expected: `6` (3 browser + 3 ollama).

- [ ] **Step 3: Commit**

```bash
git add tools/ollama_tools.py
git commit -m "feat(ollama): add local llama_summarize/classify/translate tools"
```

---

### Task 41: Phase 6 validation + tag

- [ ] **Step 1: Install Ollama (Lara, manual)**

If not already installed:
```bash
brew install ollama
brew services start ollama
ollama pull llama3.1:8b
```

Verify: `curl http://localhost:11434/api/tags`
Expected: JSON listing installed models.

- [ ] **Step 2: Restart bot and test summarization**

Send to the bot: `resume este texto: [paste ~500 words]`. 
Expected: orchestrator invokes `llama_summarize`, returns concise summary.

- [ ] **Step 3: Test graceful Ollama failure**

Stop Ollama: `brew services stop ollama`. Send the same request.
Expected: tool returns the `⚠️ Ollama no responde` message, orchestrator retries with its own summarization. No crash.

Restart: `brew services start ollama`.

- [ ] **Step 4: Tag**

```bash
git tag phase-6-complete
```

---

# PHASE 7 — Mission Control API

---

### Task 42: Add `aiohttp` to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append**

Open `requirements.txt`. Append:
```
aiohttp
```

- [ ] **Step 2: Install**

Run: `source venv/bin/activate && pip install aiohttp`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add aiohttp for Mission Control HTTP server"
```

---

### Task 43: Create `api/status.py`

**Files:**
- Create: `api/__init__.py`
- Create: `api/status.py`

- [ ] **Step 1: Create `api/__init__.py`**

Write: `api/__init__.py` empty.

- [ ] **Step 2: Write `api/status.py`**

Write: `api/status.py`:
```python
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
```

- [ ] **Step 3: Smoke-test import**

Run: `python -c "from api.status import start_web_server; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add api/__init__.py api/status.py
git commit -m "feat(mission-control): add localhost /status endpoint"
```

---

### Task 44: Launch web server from `on_startup`

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Import and launch**

Open `bot.py`. Add import:
```python
from api.status import start_web_server
```

Update `on_startup`:
```python
async def on_startup(app: Application) -> None:
    worker_count = int(os.environ.get("WORKER_COUNT", "2"))
    for i in range(worker_count):
        app.create_task(task_worker_loop(i), name=f"worker-{i}")
    app.create_task(start_web_server(), name="mission-control")
    logger.info("Lanzados %d workers + mission-control", worker_count)
```

- [ ] **Step 2: Smoke-test**

Run: `python -c "import bot; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat(mission-control): launch /status server via post_init"
```

---

### Task 45: Phase 7 validation + final tag

- [ ] **Step 1: Restart the bot**

Restart. Verify `Mission Control en http://127.0.0.1:8080/status` in logs.

- [ ] **Step 2: Query the endpoint**

Run: `curl -s http://127.0.0.1:8080/status | python -m json.tool`
Expected: JSON with `uptime_seconds`, `queue_size`, `active_sessions`, `total_cost_usd`, `sessions`.

- [ ] **Step 3: Trigger activity and re-query**

Send 2-3 messages to the bot, then re-query.
Expected: `active_sessions >= 1`, `total_cost_usd > 0`, `sessions[0].model` reflects current model.

- [ ] **Step 4: Final tag**

```bash
git tag phase-7-complete
git tag evolution-complete
```

---

## Global post-flight

After Task 45:

- [ ] **Run safe-review skill** on the entire diff series (if the user wants a final audit):
  ```
  /safe-review
  ```
  Or manually: compare the spec's "Definición de hecho" checklist (spec section 13) against reality.

- [ ] **Document any deviations from the spec** in a new `docs/superpowers/specs/2026-04-09-telegram-bot-evolution-design.md` appendix or as a separate retro file.

- [ ] **Lara personalizes her memory files** (`memory/knowledge/*.md`) — out of scope for this plan, her existing files remain in place because `.gitignore` protects them.
