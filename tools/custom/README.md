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
