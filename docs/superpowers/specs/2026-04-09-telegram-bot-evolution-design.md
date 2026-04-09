# Telegram Bot — Evolución a Sistema de Agentes Autónomos

**Fecha:** 2026-04-09
**Autor del spec:** Claude (a partir del PDF "Arquitectura de Agentes Autónomos para Telegram" de Manus AI + decisiones de Lara)
**Estado:** Aprobado por Lara para implementación
**Repositorio:** `/Users/lara/telegram-claude-bot`

---

## 1. Resumen ejecutivo

Evolucionar el bot actual (monolítico, single-user, sin tareas largas) a un sistema de agentes autónomos con:

1. **Procesamiento asíncrono** de mensajes (fin de timeouts en tareas largas).
2. **Credenciales seguras en macOS Keychain** (fin de `.env` con secretos en texto plano).
3. **Multi-instancia clonable**: cada miembro del equipo de Lara tiene su propio bot autónomo en su Mac, con su token, sus credenciales, su memoria CAG, su `cwd`, y puede personalizar el código sin perder mejoras upstream.
4. **Navegación web persistente** vía Playwright (sesiones de login que sobreviven reinicios).
5. **Subagentes especializados** (`web-surfer`, `code-analyst`) usando `AgentDefinition` del SDK.
6. **Modelos OSS híbridos** vía Ollama: Claude sigue siendo el orquestador, los modelos OSS se exponen como herramientas (`@tool def llama_*`) para tareas baratas de gran volumen.
7. **API de Mission Control** local (`/status` en `localhost:8080`) para integrar con un dashboard externo.

El bot actual se rompe en módulos para que sea mantenible y forkeable.

## 2. Restricciones de diseño

Heredadas de `~/.claude/CLAUDE.md` y `memory/knowledge/preferences.md`:

- Diffs mínimos. No refactors oportunistas.
- No inventar APIs, rutas o flags.
- Modo autónomo por defecto (`bypassPermissions`); `/safe on` para confirmaciones.
- Errores reales mostrados al usuario (no `(sin respuesta)`).
- Reintentos automáticos en errores transitorios (529, overloaded, rate limit, timeouts).
- **NUNCA** pedir credenciales pegadas vía nano/sed/echo. Usar `getpass.getpass()` o equivalente seguro.
- Si el scope correcto es mayor al pedido, parar y explicar antes de expandir.

Heredadas de la conversación de brainstorming:

- Multi-tenant **modelo B**: cada miembro del equipo tiene su propio bot, repo, Mac y credenciales. No hay multi-tenant en una sola Mac.
- OSS **modelo 2 (híbrido)**: Claude orquesta, OSS son herramientas. NO se reemplaza Claude por OSS.
- Runtime OSS por defecto: **Ollama** (`brew install ollama`).
- Cada miembro debe poder hacer `git pull` upstream sin perder sus personalizaciones.

## 3. Riesgos resueltos del PDF original

El PDF de Manus AI tiene 3 imprecisiones técnicas que **este spec corrige**:

| # | Imprecisión del PDF | Corrección |
|---|---|---|
| 1 | Propone `TASK_QUEUE` global con un solo worker → serializa todos los chats, regresión vs `concurrent_updates=True` actual | Pool de workers (default 2) consume de la queue. Cada worker respeta `SESSION_LOCKS` por chat. Permite paralelismo entre chats con coste controlado en API. |
| 2 | `app.create_task(...)` antes de `app.run_polling()` → falla porque `run_polling` arranca su propio event loop | Usar `post_init` callback en `ApplicationBuilder`. Ahí se lanzan worker pool y servidor `/status`. |
| 3 | `AgentDefinition` con solo "Nombre, Descripción, Herramientas, Modelo" → omite el campo obligatorio `prompt: str` | Cada `AgentDefinition` lleva un `prompt` propio (system prompt del subagente). Verificado en `claude-agent-sdk-python/src/claude_agent_sdk/types.py:82`. |

## 4. Arquitectura de alto nivel

```
┌──────────┐                                ┌──────────────────────┐
│ Telegram │                                │ aiohttp /status       │
│   chat   │                                │ (localhost:8080)      │
└────┬─────┘                                └──────────┬───────────┘
     │ update                                          ▲
     ▼                                                 │ GET
┌──────────────┐                                       │
│  handler     │  enqueue task                         │
│ (handle_text/│ ────────────────────┐                 │
│ voice/photo/ │                     │                 │
│ document)    │                     ▼                 │
└──────────────┘            ┌──────────────────┐       │
                            │  TASK_QUEUE       │       │
                            │ (asyncio.Queue)   │       │
                            └────────┬─────────┘       │
                                     │ get             │
                  ┌──────────────────┼──────────────────┐
                  ▼                  ▼                  ▼
            ┌──────────┐       ┌──────────┐       ┌──────────┐
            │ worker 1 │       │ worker 2 │  ...  │ worker N │
            └────┬─────┘       └────┬─────┘       └────┬─────┘
                 │ acquire SESSION_LOCKS[chat_id]      │
                 ▼                                     │
         ┌─────────────────────────────────────┐       │
         │  ClaudeSDKClient (per session)       │       │
         │                                      │       │
         │  Tools:                              │       │
         │   - Read/Glob/Grep/WebFetch/...      │       │
         │   - browser_navigate/click/...       │       │
         │   - llama_summarize/classify/...     │       │
         │                                      │       │
         │  Subagents:                          │       │
         │   - web-surfer                       │       │
         │   - code-analyst                     │       │
         └──────────────┬───────────────────────┘       │
                        │ updates session.total_cost ───┘
                        ▼
                   reply to user
```

## 5. Estructura del repo

```
telegram-claude-bot/
├── bot.py                                # entrada principal (~150-200 líneas, mucho más fino)
├── core/
│   ├── __init__.py
│   ├── session.py                        # ChatSession, SESSIONS, SESSION_LOCKS, get_session_lock
│   ├── routing.py                        # route_prompt + MODEL_NAME_MAP (sin cambios funcionales)
│   ├── credentials.py                    # get_secret(name) / set_secret(name, value) → Keychain
│   ├── worker.py                         # TASK_QUEUE, task_worker_loop, enqueue_task
│   ├── system_prompt.py                  # build_system_prompt + load_knowledge_blocks
│   └── runner.py                         # run_claude (núcleo de invocación a Claude)
├── tools/
│   ├── __init__.py                       # load_all_tools() — descubre y carga tools dinámicamente
│   ├── browser_tools.py                  # @tool browser_navigate, browser_click, browser_extract
│   ├── ollama_tools.py                   # @tool llama_summarize, llama_classify, llama_translate
│   └── custom/
│       ├── .gitkeep
│       └── README.md                     # cómo añadir tools propias
├── agents/
│   ├── __init__.py
│   └── definitions.py                    # WEB_SURFER, CODE_ANALYST (AgentDefinition objects)
├── api/
│   ├── __init__.py
│   └── status.py                         # aiohttp app + endpoint /status
├── handlers/
│   ├── __init__.py
│   ├── commands.py                       # /start /pwd /cd /reset /voice /safe /think /model /cost
│   ├── text.py                           # handle_text + handle_pending_decision
│   ├── voice.py                          # handle_voice + transcribe_audio
│   ├── media.py                          # handle_photo + handle_document
│   └── permissions.py                    # make_can_use_tool
├── memory/
│   └── knowledge/
│       └── .keep                         # contenido .gitignored
├── system_prompt.example.md              # plantilla; cada miembro la copia a system_prompt.md
├── setup_credentials.py                  # bootstrap interactivo del Keychain
├── bootstrap.sh                          # instalador para clonar en una Mac nueva
├── com.telegram-claude-bot.plist.template # plantilla launchd
├── requirements.txt                      # + keyring, playwright, aiohttp, httpx
├── .env.example                          # solo vars no sensibles (TTS_VOICE, WORKING_DIR, OLLAMA_HOST…)
├── .gitignore                            # ver §6
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-09-telegram-bot-evolution-design.md  # este documento
└── README.md                             # cómo clonar y desplegar en una Mac nueva
```

> **Nota sobre los snippets de código de este spec:** Todos los módulos Python que se muestran a continuación asumen, en su cabecera:
> ```python
> import logging
> logger = logging.getLogger(__name__)
> ```
> Esos imports están omitidos en los snippets por brevedad pero **son obligatorios** en la implementación real (el bot ya usa logging y todos los módulos deben hacer lo mismo).

### 5.1 Por qué romper bot.py en módulos

`bot.py` actual = 961 líneas (handlers + sesiones + routing + run_claude + comandos + main). Añadir 5 fases más lo lleva a ~1700+ líneas. **Es ingobernable** y **bloquea** el escenario "cada miembro adapta su parte sin tocar el resto".

Esto cumple regla 6 del CLAUDE.md de Lara: el refactor a módulos NO es opcional, es **prerrequisito real** del scope multi-instancia + 5 fases. Por eso es Fase 1 del plan, no un opcional.

## 6. .gitignore propuesto

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

## 7. Fases de implementación (orden)

Orden decidido: **B** (reordenado por valor para el equipo). Cada miembro debe poder usar SU bot lo antes posible y recibir mejoras como `git pull`.

| Fase | Nombre | Habilita |
|---|---|---|
| 1 | Refactor a módulos + Task Queue + Background Worker | Cimiento técnico de todo lo demás |
| 2 | Credenciales en macOS Keychain + setup_credentials.py | Prerequisito de bootstrap multi-instancia |
| 3 | Multi-instancia: bootstrap.sh + plist template + README | **Equipo puede empezar a usar el bot** |
| 4 | Playwright persistente + browser_tools.py | Navegación web autónoma |
| 5 | Subagentes con AgentDefinition | Paralelismo y especialización |
| 6 | OSS híbrido: ollama_tools.py | Inferencia local barata para tareas masivas |
| 7 | API Mission Control /status | Telemetría para dashboard externo |

---

## Fase 1 — Refactor a módulos + Task Queue + Background Worker

### 1.1 Refactor a módulos

Mover el código de `bot.py` actual a la estructura de §5 **sin cambios funcionales**. Cada función va al módulo que le corresponde. `bot.py` queda solo con el `main()` que arma el `Application`, registra handlers y arranca el polling.

Criterio de validación: tras el refactor, el bot debe arrancar y comportarse exactamente igual que antes. Cero cambios visibles para el usuario.

### 1.2 Task Queue + Worker Pool

**Nuevo módulo `core/worker.py`:**

```python
import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable

@dataclass
class Task:
    chat_id: int
    handler: Callable[..., Awaitable[None]]
    args: tuple
    kwargs: dict

TASK_QUEUE: asyncio.Queue[Task] = asyncio.Queue()
DEFAULT_WORKER_COUNT = 2  # configurable via env WORKER_COUNT

async def enqueue_task(chat_id: int, handler, *args, **kwargs) -> None:
    await TASK_QUEUE.put(Task(chat_id, handler, args, kwargs))

async def task_worker_loop(worker_id: int) -> None:
    while True:
        task = await TASK_QUEUE.get()
        try:
            await task.handler(*task.args, **task.kwargs)
        except Exception:
            logger.exception("Worker %d crash en task chat=%d", worker_id, task.chat_id)
        finally:
            TASK_QUEUE.task_done()
```

**Cambios en handlers (`handlers/text.py`, `handlers/voice.py`, `handlers/media.py`):**

Antes:
```python
await run_claude(update, context, session, text, source="text")
```

Después:
```python
await update.message.reply_text("⏳ Tarea recibida, procesando...")
await enqueue_task(
    chat_id=session.chat_id,
    handler=run_claude,
    update=update, context=context, session=session, prompt=text, source="text",
)
```

**Cambios en `bot.py` `main()`:**

```python
async def on_startup(app: Application) -> None:
    worker_count = int(os.environ.get("WORKER_COUNT", "2"))
    for i in range(worker_count):
        app.create_task(task_worker_loop(i), name=f"worker-{i}")

app = (
    ApplicationBuilder()
    .token(TELEGRAM_TOKEN)
    .concurrent_updates(True)
    .post_init(on_startup)
    .build()
)
```

### 1.3 Preservación de invariantes

- `SESSION_LOCKS` se mantiene: cada `run_claude` adquiere el lock del chat antes de tocar la sesión. Garantiza serialización por chat.
- `concurrent_updates=True` se mantiene: handlers son no-bloqueantes (solo encolan).
- `typing_indicator_loop` se mantiene dentro de `run_claude`.
- Reintentos transitorios (529, timeouts) se mantienen.
- Cost tracking se mantiene.

### 1.4 Tests (Fase 1)

- Test manual: enviar 3 mensajes simultáneos al bot → los 3 deben recibir "⏳ recibido" inmediatamente, y procesarse en paralelo (hasta WORKER_COUNT).
- Test manual: tarea larga (ej. "lee todos los .md de mi proyecto y resúmelos") → no debe causar timeout en Telegram.
- Test manual: el bot puede recibir un nuevo mensaje mientras procesa otro del mismo chat → el nuevo se encola y se procesa después (gracias a SESSION_LOCKS).

---

## Fase 2 — Credenciales en macOS Keychain

### 2.1 Diseño

Servicio Keychain: `telegram-claude-bot`
Cuentas:
- `TELEGRAM_TOKEN`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`

Vars **no sensibles** que siguen en `.env` (porque son configuración, no secretos):
- `ALLOWED_USER_ID`
- `WORKING_DIR`
- `TTS_VOICE`, `TTS_MODEL`, `STT_MODEL`
- `WORKER_COUNT`
- `OLLAMA_HOST` (default `http://localhost:11434`)
- `MISSION_CONTROL_PORT` (default `8080`)

### 2.2 Nuevo módulo `core/credentials.py`

```python
import keyring

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
```

### 2.3 Refactor de `bot.py` (lectura de secretos)

Antes:
```python
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
```

Después:
```python
from core.credentials import get_secret
TELEGRAM_TOKEN = get_secret("TELEGRAM_TOKEN")
```

Idem para `ANTHROPIC_API_KEY` y `OPENAI_API_KEY`.

**Importante:** `ANTHROPIC_API_KEY` debe estar también en el `os.environ` del proceso del bot, porque el subproceso `claude` (Claude Code CLI) lo lee de ahí. `core/credentials.py` debe exportar al env al cargarse:

```python
def export_to_env(*names: str) -> None:
    """Carga secretos del Keychain al os.environ del proceso."""
    for name in names:
        os.environ[name] = get_secret(name)
```

Y en `bot.py`:
```python
from core.credentials import export_to_env
export_to_env("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
```

### 2.4 `setup_credentials.py`

Reemplaza el `setup_env.py` actual. Es bootstrap interactivo:

```python
"""Bootstrap interactivo del Keychain para el bot.

Uso:
    python setup_credentials.py

Pide cada secreto con getpass (input oculto) y lo guarda en macOS Keychain.
Si encuentra un .env legacy con TELEGRAM_TOKEN, ofrece migrar automáticamente.
"""
import os
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

### 2.5 `requirements.txt`

Añadir: `keyring`

### 2.6 Tests (Fase 2)

- Test manual: borrar todos los secretos del Keychain (`security delete-generic-password -s telegram-claude-bot ...`), correr `setup_credentials.py` → guarda los 3.
- Test manual: arrancar bot con Keychain vacío → debe fallar con mensaje claro pidiendo ejecutar `setup_credentials.py`.
- Test manual: arrancar bot con Keychain configurado → debe arrancar normal.

---

## Fase 3 — Multi-instancia: bootstrap.sh + plist template + README

### 3.1 `bootstrap.sh`

Instalador idempotente que cualquier miembro del equipo puede correr en su Mac nueva:

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
source "$REPO_DIR/venv/bin/activate"

# 3. Instalar requirements
echo "==> Instalando requirements"
pip install --upgrade pip
pip install -r "$REPO_DIR/requirements.txt"

# 4. Instalar Playwright Chromium (para Fase 4 — opcional pero recomendado)
echo "==> Instalando Playwright Chromium"
playwright install chromium || echo "⚠️  Playwright install falló (Fase 4 no funcionará)"

# 5. Bootstrap del Keychain
if ! python -c "import keyring; assert keyring.get_password('telegram-claude-bot', 'TELEGRAM_TOKEN')" 2>/dev/null; then
    echo "==> Configurando Keychain"
    python "$REPO_DIR/setup_credentials.py"
else
    echo "==> Keychain ya configurado"
fi

# 6. Crear .env desde .env.example si no existe
if [[ ! -f "$REPO_DIR/.env" ]]; then
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

### 3.2 `com.telegram-claude-bot.plist.template`

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

### 3.3 `system_prompt.example.md`

Plantilla base que cada miembro copia y personaliza:

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

`build_system_prompt()` en `core/system_prompt.py` carga `system_prompt.md` si existe; si no, usa el `system_prompt.example.md`. La memoria CAG se sigue inyectando como hoy.

### 3.4 `tools/custom/README.md`

Mini-guía: cómo añadir una `@tool` propia en `tools/custom/mi_tool.py`. El loader de `tools/__init__.py` la descubre automáticamente al arrancar el bot.

```markdown
# Tools personalizadas

Coloca aquí tus herramientas propias. El bot las descubre y carga automáticamente al arrancar.

## Ejemplo: tools/custom/mi_tool.py

```python
from claude_agent_sdk import tool

@tool(
    name="mi_tool",
    description="Hace algo útil para mi flujo de trabajo.",
    input_schema={"type": "object", "properties": {"texto": {"type": "string"}}},
)
async def mi_tool(texto: str) -> str:
    return f"procesé: {texto}"
```

Reinicia el bot con `launchctl kickstart -k gui/$(id -u)/com.$(whoami).telegram-claude-bot`.
Tu tool aparecerá disponible para Claude automáticamente.
```

### 3.5 `tools/__init__.py` — autoloader

```python
"""Autoloader de tools.

Descubre automáticamente todas las @tool decoradas en:
- tools/browser_tools.py (Fase 4)
- tools/ollama_tools.py (Fase 6)
- tools/custom/*.py (cada usuario)

Devuelve una lista de tool objects para inyectar en ClaudeAgentOptions.
"""
import importlib
import pkgutil
from pathlib import Path

def load_all_tools() -> list:
    tools = []
    pkg_dir = Path(__file__).parent

    # Tools nativas (browser, ollama)
    for module_name in ("browser_tools", "ollama_tools"):
        try:
            mod = importlib.import_module(f"tools.{module_name}")
            tools.extend(getattr(mod, "TOOLS", []))
        except ImportError as e:
            logger.warning("No se pudo cargar %s: %s", module_name, e)

    # Tools custom del usuario
    custom_dir = pkg_dir / "custom"
    if custom_dir.exists():
        for path in custom_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue
            mod = importlib.import_module(f"tools.custom.{path.stem}")
            tools.extend(getattr(mod, "TOOLS", []))

    return tools
```

Cada módulo de tools expone una constante `TOOLS = [tool_function_1, tool_function_2, ...]` que el loader recoge.

### 3.5.1 Wiring del autoloader en `core/runner.py`

Añadir en Fase 3, junto con el autoloader, el enganche en `options_kwargs` de `ensure_client`:

```python
from tools import load_all_tools

options_kwargs = dict(
    cwd=session.cwd,
    ...
    tools=load_all_tools(),                 # ← NUEVO en Fase 3
)
```

En Fase 3 `load_all_tools()` devuelve `[]` (aún no hay módulos de tools). Ese valor es inocuo — el bot se comporta idéntico al actual. El wiring se hace ahora para que las fases siguientes (4, 6, y `tools/custom/*` de cada miembro) **no requieran tocar `core/runner.py` de nuevo**. Así cumple el objetivo fork-friendly: un miembro añade un archivo en `tools/custom/` y reinicia; no toca código compartido.

### 3.6 README.md

Documenta:

1. **Qué es el bot** (3 líneas)
2. **Requisitos** (Python 3.10+, claude-code CLI, brew, Mac mini idealmente 24/7)
3. **Instalación rápida**:
   ```bash
   git clone <repo>
   cd telegram-claude-bot
   ./bootstrap.sh
   ```
4. **Personalización**:
   - `system_prompt.md` → tu rol
   - `memory/knowledge/*.md` → tu memoria persistente (proyectos, gente, decisiones)
   - `tools/custom/*.py` → tus herramientas propias
   - `.env` → variables no sensibles
5. **Operación**:
   - Logs: `tail -f bot.log`
   - Reiniciar: `launchctl kickstart -k gui/$(id -u)/com.$(whoami).telegram-claude-bot`
   - Comandos del bot: `/start /pwd /cd /reset /voice /safe /think /model /cost`
6. **Actualización (`git pull`)**:
   - Tus datos personales están en `.gitignore`, no se pisan.
   - Si hay nuevas dependencias: `source venv/bin/activate && pip install -r requirements.txt`.
   - Si hay nuevos secretos: `python setup_credentials.py`.

### 3.7 Tests (Fase 3)

- Test manual: clonar el repo en una segunda Mac (o en otra carpeta), correr `bootstrap.sh`, verificar que el bot arranca con credenciales nuevas, su propio plist con label `com.<user>.telegram-claude-bot`, y responde mensajes en Telegram.
- Test manual: editar `system_prompt.md` con un rol distinto → reiniciar bot → verificar que el system prompt cambia (preguntar al bot "quién eres" debe reflejar el cambio).
- Test manual: añadir una tool en `tools/custom/hello.py` → reiniciar bot → preguntarle al bot "¿qué tools tienes?" debe listar la nueva.

---

## Fase 4 — Playwright persistente

### 4.1 Diseño

`tools/browser_tools.py` crea un `BrowserManager` singleton que mantiene un único `browser_context` persistente con `launch_persistent_context`. Las sesiones de login (Instagram, LinkedIn, GitHub, etc.) se preservan entre reinicios porque viven en `~/.playwright_user_data`.

### 4.2 `tools/browser_tools.py`

```python
"""Tools de navegación web persistente para el bot.

Usa Playwright en modo asíncrono con launch_persistent_context para mantener
sesiones de login entre reinicios.
"""
import asyncio
import os
from typing import Optional

from claude_agent_sdk import tool
from playwright.async_api import async_playwright, BrowserContext, Page

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
        return text[:8000]  # cap a 8k chars para no saturar contexto
    finally:
        await page.close()

@tool(
    name="browser_click",
    description=(
        "Hace clic en un selector CSS de la página actualmente abierta y "
        "devuelve el texto resultante."
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

### 4.3 Notas

- Las tools de browser **leen credenciales del Keychain** vía `get_secret(...)` cuando necesitan login (ej. una tool futura `browser_login_instagram` que use `get_secret("INSTAGRAM_PASSWORD")`).
- En Fase 4 incluimos solo `browser_navigate`, `browser_click`, `browser_extract`. Tools de login específicas (Instagram, LinkedIn) se añaden en `tools/custom/` por cada miembro según necesite.
- `BrowserManager` es singleton global del proceso. El primer uso lanza el Chromium; las siguientes llamadas reutilizan el contexto. **Una sola Mac, un solo bot, un solo navegador persistente.**
- Cap de 8000 chars en el output: evita saturar el contexto de Claude. Si Claude necesita más, puede pedir extracción más específica.

### 4.4 `requirements.txt`

Añadir: `playwright`

### 4.5 Tests (Fase 4)

- Test manual: pedirle al bot "ve a https://es.wikipedia.org y dame el primer párrafo del artículo destacado" → debe usar `browser_navigate` y devolver el texto.
- Test manual: pedirle "loguéate en mi cuenta de X" (manual): abrir el navegador en modo no-headless por una vez, hacer login manual, cerrar; las cookies persisten en `~/.playwright_user_data`. Siguiente llamada `browser_navigate` ya está logueada.

---

## Fase 5 — Subagentes con AgentDefinition

### 5.1 `agents/definitions.py`

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
    model="sonnet",  # alias del SDK
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

### 5.2 Cambios en `core/runner.py` (donde vive `ensure_client`)

Antes (en `options_kwargs`):
```python
options_kwargs = dict(
    cwd=session.cwd,
    permission_mode="default" if session.safe_mode else "bypassPermissions",
    setting_sources=["user", "project", "local"],
    model=session.current_model,
    fallback_model=fallback,
    system_prompt=build_system_prompt(),
    stderr=lambda line: logger.error("CLAUDE_CLI: %s", line),
)
```

Después:
```python
from agents.definitions import AGENTS

options_kwargs = dict(
    cwd=session.cwd,
    permission_mode="default" if session.safe_mode else "bypassPermissions",
    setting_sources=["user", "project", "local"],
    model=session.current_model,
    fallback_model=fallback,
    system_prompt=build_system_prompt(),
    stderr=lambda line: logger.error("CLAUDE_CLI: %s", line),
    tools=load_all_tools(),                 # ya estaba desde Fase 3
    agents=AGENTS,                          # ← NUEVO en Fase 5
)
```

### 5.3 Notas

- Los subagentes **heredan** el `permission_mode` del orquestador. Si el orquestador está en `bypassPermissions`, los subagentes también.
- Cada subagente tiene contexto **limpio**: si necesita info de la memoria CAG, el orquestador debe pasársela en el prompt de delegación.
- La invocación es automática: Claude decide cuándo delegar a `web-surfer` o `code-analyst` según las descripciones.

### 5.4 Tests (Fase 5)

- Test manual: pedir "investiga 3 competidores de mi producto X en internet y compara precios" → el orquestador debe delegar a `web-surfer`.
- Test manual: pedir "audita todos los .py de mi proyecto Y buscando uso de print() y reemplázalos por logging" → el orquestador debe delegar a `code-analyst` para encontrar los archivos y luego usar Edit (que lo hará el orquestador, no el subagente, porque code-analyst no tiene Edit).

---

## Fase 6 — OSS híbrido vía Ollama

### 6.1 `tools/ollama_tools.py`

```python
"""Tools de inferencia local vía Ollama.

Permite a Claude delegar tareas baratas y de gran volumen a modelos OSS
corriendo en localhost (Llama 3.1, Mistral, etc.) sin gastar tokens de Anthropic.
"""
import os
from typing import Optional

import httpx
from claude_agent_sdk import tool

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

### 6.2 Notas

- Ollama **no requiere** auth en localhost por defecto.
- Si Ollama no está corriendo, las tools devuelven mensaje claro pidiendo `ollama serve`. **No** crashean el bot.
- El modelo default es `llama3.1:8b` (rápido, suficiente para resúmenes/clasificación). Configurable vía `OLLAMA_DEFAULT_MODEL` env var.
- README incluye paso opcional: `brew install ollama && ollama pull llama3.1:8b && ollama serve` (o `brew services start ollama`).
- **Las tools OSS son adicionales**, no reemplazan nada. Claude las invoca cuando le conviene (= cuando el ahorro de tokens vale la pena vs la calidad).

### 6.3 `requirements.txt`

Añadir: `httpx` (probable que ya esté como dep transitiva del openai SDK; verificar y solo añadir explícito si no).

### 6.4 Tests (Fase 6)

- Test manual: arrancar Ollama (`ollama serve`), pedir al bot "resume este texto largo: [texto]" → debe usar `llama_summarize`.
- Test manual: parar Ollama, pedir lo mismo → la tool debe devolver el mensaje de error claro y Claude debe degradar a procesar el texto él mismo.
- Test manual: "clasifica este email en spam/important/newsletter: [texto]" → `llama_classify`.

---

## Fase 7 — API de Mission Control

### 7.1 `api/status.py`

```python
"""Servidor HTTP local para telemetría del bot.

Endpoint: GET http://localhost:8080/status
"""
import os
import time
from aiohttp import web

from core.session import SESSIONS
from core.worker import TASK_QUEUE

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

### 7.2 Cambios en `bot.py` `on_startup`

```python
async def on_startup(app: Application) -> None:
    worker_count = int(os.environ.get("WORKER_COUNT", "2"))
    for i in range(worker_count):
        app.create_task(task_worker_loop(i), name=f"worker-{i}")
    app.create_task(start_web_server(), name="mission-control")
```

### 7.3 Notas

- El servidor solo escucha en `127.0.0.1` (localhost). **No** se expone al exterior. Eso es seguridad por diseño: el dashboard de Mission Control debe correr en la misma Mac o usar SSH tunnel.
- No hay auth en el endpoint. Suficiente porque solo es localhost.
- `MISSION_CONTROL_PORT` configurable: si un miembro del equipo tiene otro proceso en 8080, lo cambia en `.env`.

### 7.4 `requirements.txt`

Añadir: `aiohttp`

### 7.5 Tests (Fase 7)

- Test manual: arrancar el bot, hacer `curl http://localhost:8080/status` → JSON con uptime, queue, sesiones, coste.
- Test manual: encolar 5 tareas largas → ver `queue_size` en el endpoint.

---

## 8. Cambios consolidados a `requirements.txt`

```
# Existentes (no se tocan, mantener versiones del lockfile actual)
annotated-types==0.7.0
anyio==4.13.0
... (todo lo existente)

# Nuevos (Fases 2, 4, 6, 7)
keyring          # Fase 2: Keychain
playwright       # Fase 4: navegación persistente
httpx            # Fase 6: cliente Ollama (verificar si ya es transitiva)
aiohttp          # Fase 7: servidor /status
```

Pin de versiones: usar las latest stables del momento de implementación, fijadas explícitamente en el plan.

## 9. Operación post-deploy

### Para Lara (su bot)

```bash
cd /Users/lara/telegram-claude-bot
git pull
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium  # solo primera vez tras Fase 4
python setup_credentials.py  # solo si hay nuevos secretos
launchctl kickstart -k gui/$(id -u)/com.lara.telegram-claude-bot
tail -f bot.log
```

### Para un miembro nuevo del equipo

```bash
git clone <url-del-repo> ~/telegram-claude-bot
cd ~/telegram-claude-bot
./bootstrap.sh
# Editar system_prompt.md con su rol
# Editar memory/knowledge/*.md con su info
# Reiniciar:
launchctl kickstart -k gui/$(id -u)/com.$(whoami).telegram-claude-bot
```

## 10. Decisiones técnicas tomadas (sin consultar)

| Decisión | Valor | Razón |
|---|---|---|
| Worker pool size default | 2 | Permite paralelismo entre chats sin saturar la API. Configurable vía `WORKER_COUNT`. |
| Cap de output de browser tools | 8000 chars | Evita saturar contexto de Claude. Subagent web-surfer puede pedir extracción más fina. |
| Cap de timeout en `_ollama_generate` | 120 s | Modelos locales pueden ser lentos en Mac mini sin GPU. |
| Modelo Ollama default | `llama3.1:8b` | Equilibrio velocidad/calidad para tareas auxiliares. Configurable. |
| Puerto Mission Control | 8080 (localhost) | Estándar de facto para dashboards locales. Configurable. |
| `setup_credentials.py` migra del .env legacy | Sí, automático | Friction-less para Lara que ya tiene .env. |
| `system_prompt.md` vs `system_prompt.example.md` | Example va al repo, real va al .gitignore | Permite personalización por miembro sin pisarse con upstream. |
| Tools custom: descubrimiento automático | Sí, vía `pkgutil` en `tools/__init__.py` | Sin que el miembro tenga que registrar nada manualmente. |
| Subagentes en `bypassPermissions` | Heredan del orquestador | Coherente con la preferencia de Lara de modo autónomo. |
| `agents=` se pasa siempre, incluso en Fase 1-4 | No: solo desde Fase 5 | Antes no tiene tools de browser ni necesidad de delegación. |
| TASK_QUEUE persistencia entre reinicios | No (KISS) | Tareas son interactivas; el usuario las repite si reinicia el bot. |
| Errores de Ollama | Mensaje claro en el output de la tool, no crash | Claude debe poder degradar a hacerlo él mismo. |
| Label del plist | `com.<whoami>.telegram-claude-bot` | Único por miembro del equipo, evita colisiones. |

## 11. Lo que NO está en este plan (out of scope explícito)

- **Multi-tenant en una sola Mac**: descartado en favor del modelo B (instancia por persona).
- **Reemplazar Claude por OSS como cerebro**: descartado en favor del modelo híbrido (OSS son tools).
- **LiteLLM proxy**: descartado por incompatibilidad con subagentes.
- **Persistencia de TASK_QUEUE**: KISS.
- **Auth en `/status`**: localhost only es suficiente.
- **CI/CD del repo**: el proyecto es personal/equipo pequeño, no necesita pipeline.
- **Tests automatizados**: el bot se valida manualmente. Tests unitarios de algunas funciones puras (route_prompt, get_secret) son bienvenidos pero no bloquean el plan.
- **Migración del bot que está corriendo en producción**: el plist actual apunta a `/Users/lara/proyectos/telegram-claude-bot` (ruta vieja que ya no existe). El plan asume implementación en `/Users/lara/telegram-claude-bot` y nuevo plist generado por `bootstrap.sh`.

## 12. Riesgos abiertos (a vigilar durante implementación)

1. **Versión del SDK** — el `requirements.txt` actual fija `claude-agent-sdk==0.1.56`. La verificación de `AgentDefinition` la hice contra el `main` del repo upstream. Si la versión 0.1.56 es muy vieja, puede que la API haya cambiado. Plan: en Fase 5, primero probar con un script mínimo que `agents={}` no crashee, antes de meter las definiciones reales.
2. **Playwright headless en macOS launchd** — los procesos lanzados por launchd no siempre tienen permisos para abrir ventanas (incluso headless). Si falla, plan: arrancar el bot con `LaunchAgents` más permisivo o usar `aux` mode.
3. **Cwd del bot vs cwd de las tools** — Playwright crea archivos en `~/.playwright_user_data`, que es absoluto, así que está bien. Pero las tools que escriban en disco deben usar paths absolutos.
4. **Concurrencia de BrowserManager** — el singleton tiene un lock para inicialización, pero los `new_page()` concurrentes desde N workers pueden saturar Chromium. Si pasa, añadir un semáforo de N=4 páginas concurrentes max.
5. **Coste de Ollama en Mac mini sin GPU** — puede ser muy lento con `llama3.1:8b`. Plan: si la latencia es inaceptable, recomendar `llama3.2:3b` en `.env.example`.

## 13. Checklist de "definición de hecho" por fase

Cada fase se considera completada cuando:

- [ ] El código está en su módulo correcto según §5.
- [ ] El bot arranca sin errores.
- [ ] Los tests manuales de la fase pasan.
- [ ] El comportamiento existente NO está roto (regresión cero).
- [ ] `safe-review` skill ha sido ejecutado y sus findings atendidos (regla 14 del CLAUDE.md).
- [ ] El commit de la fase tiene mensaje claro y descriptivo.

## 14. Próximo paso

Generar el **plan de implementación detallado** (paso por paso, archivo por archivo, con criterios de verificación) usando el `superpowers:writing-plans` skill, basado en este spec.
