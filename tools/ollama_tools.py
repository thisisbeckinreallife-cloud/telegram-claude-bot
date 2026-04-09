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
