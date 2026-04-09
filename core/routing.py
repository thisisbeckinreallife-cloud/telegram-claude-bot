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

    Reglas (idénticas a ROUTER_SYSTEM anterior):
    - haiku + thinking 0 → saludos, chitchat, preguntas triviales, comandos cortos obvios.
    - sonnet + thinking 0 → tareas directas: leer/escribir, buscar, resúmenes, emails, shell simple.
    - sonnet + thinking 8000 → código no trivial, debugging, análisis, refactors, diseño, multi-paso.
    - opus + thinking 16000 → arquitectura, decisiones estratégicas, muchas variables, revisiones, crítico.
    """
    p = prompt.lower()
    length = len(prompt)

    # Opus keywords: estrategia, arquitectura, decisiones, investigación profunda
    opus_keywords = {
        "arquitectura", "estrategia", "decisión", "exhaustivo", "complejo", "crítico",
        "diseño", "análisis competitivo", "roadmap", "plan", "investigar",
        "mejoraría", "optimizar"
    }

    # Sonnet + thinking keywords: código, debugging, análisis, refactoring
    sonnet_thinking_keywords = {
        "código", "debug", "error", "refactor", "función", "clase", "test", "análisis",
        "estructura", "patrón", "algoritmo", "optimiz", "bug", "fallo", "problema"
    }

    # Sonnet keywords: tareas directas sin thinking profundo
    sonnet_keywords = {
        "archivo", "read", "escribir", "crear", "leer", "buscar", "internet", "email",
        "resumen", "traducir", "explicar", "git", "comando"
    }

    # Haiku keywords: trivial, corto, saludo
    # (evitando substrings cortos que generan falsos positivos: "ok" en "book", "no" en "know")
    haiku_keywords = {
        "hola", "hi", "hey", "gracias", "sí", "help", "pwd", "cd"
    }

    # Score opus: alta prioridad para decisiones/arquitectura
    if any(kw in p for kw in opus_keywords):
        logger.info("Router (heurística) → model=opus thinking=16000")
        return (MODEL_OPUS, 16000)

    # Score sonnet + thinking: código, debugging, análisis
    if any(kw in p for kw in sonnet_thinking_keywords):
        logger.info("Router (heurística) → model=sonnet thinking=8000")
        return (MODEL_SONNET, 8000)

    # Score sonnet: tareas directas o prompts largos (>400 chars)
    if length > 400 or any(kw in p for kw in sonnet_keywords):
        logger.info("Router (heurística) → model=sonnet thinking=0")
        return (MODEL_SONNET, 0)

    # Score haiku: saludos O prompts muy cortos (<50 chars)
    if any(kw in p for kw in haiku_keywords) or length < 50:
        logger.info("Router (heurística) → model=haiku thinking=0")
        return (MODEL_HAIKU, 0)

    # Default: sonnet es el fallback sensato
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
