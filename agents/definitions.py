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
