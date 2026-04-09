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
