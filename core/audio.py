"""Cliente OpenAI + funciones STT (Whisper) y TTS (tts-1).

# IMPORTANT: this module is imported BEFORE core/credentials.export_to_env runs.
# That means the module-level `OPENAI_API_KEY` imported from core.config is
# bound to the PRE-Keychain environment and may be empty. Never bind
# `OPENAI_API_KEY` by name at module scope in any consumer module — always
# call `get_openai_client()` (which re-reads os.environ at first use) or
# `os.environ.get("OPENAI_API_KEY")` at runtime. The same applies to any
# future secret that gets exported from Keychain in bot.py startup.
"""
import logging
import os
from typing import Optional

from openai import AsyncOpenAI

from core.config import OPENAI_API_KEY, STT_MODEL, TTS_MODEL, TTS_VOICE

logger = logging.getLogger(__name__)


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


async def transcribe_audio(file_path: str) -> str:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    with open(file_path, "rb") as f:
        result = await client.audio.transcriptions.create(
            model=STT_MODEL,
            file=f,
        )
    return result.text


async def synthesize_voice(text: str, out_path: str) -> None:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    text = text[:4000]
    response = await client.audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
        response_format="opus",
    )
    response.write_to_file(out_path)
