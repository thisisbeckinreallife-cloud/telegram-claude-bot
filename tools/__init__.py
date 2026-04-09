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
