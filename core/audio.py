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
