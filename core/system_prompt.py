"""Construcción del system prompt con memoria CAG.

El prompt incluye:
- Reglas de comunicación.
- Bloque de memoria CAG con todos los .md de memory/knowledge/.
- CLAUDE.md global de Lara (si existe).
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
