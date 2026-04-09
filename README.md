# telegram-claude-bot

Bot de Telegram que delega cada mensaje a Claude vía `claude-agent-sdk`.
Opera tu Mac mini desde el móvil: archivos, terminal, git, deploys, búsqueda web.

## Qué hace

- Procesa texto, voz (Whisper), imágenes y documentos.
- Auto-routing entre Haiku/Sonnet/Opus según complejidad.
- Memoria CAG: lee `memory/knowledge/*.md` en cada system prompt.
- Modo autónomo por defecto (`bypassPermissions`); `/safe on` pide confirmaciones.
- Task queue asíncrona: mensajes no bloquean handlers, se procesan en worker pool.
- Credenciales en macOS Keychain (no `.env`).
- Multi-instancia: cada miembro del equipo tiene su propio bot, su memoria, sus tools.

## Requisitos

- macOS
- Python 3.10+
- `claude-code` CLI instalado (https://claude.com/claude-code)
- `brew`
- Mac mini o laptop (idealmente 24/7 para estar siempre disponible)

## Instalación rápida

```bash
git clone <repo-url> ~/telegram-claude-bot
cd ~/telegram-claude-bot
./bootstrap.sh
```

El script:
1. Crea un venv y instala dependencias.
2. Instala Playwright Chromium (Fase 4).
3. Bootstrap interactivo del Keychain (pide tus tokens con input oculto).
4. Crea `.env` y `system_prompt.md` desde los examples.
5. Genera un plist launchd con label `com.$(whoami).telegram-claude-bot`.
6. Carga el servicio.

## Personalización por miembro del equipo

Cada uno de estos archivos es personal (ignorado por git, no se pisa con `git pull`):

| Archivo | Para qué |
|---|---|
| `system_prompt.md` | Rol y tono del bot. Empieza copiando `system_prompt.example.md`. |
| `memory/knowledge/*.md` | Memoria persistente: proyectos, gente, decisiones, preferencias. |
| `tools/custom/*.py` | Tus herramientas propias (`@tool` decoradas). Se cargan automáticamente. |
| `.env` | Variables no sensibles (WORKING_DIR, TTS_VOICE, WORKER_COUNT). |

Los secretos (TELEGRAM_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY) viven en
macOS Keychain bajo el servicio `telegram-claude-bot`. Gestionar con
`python setup_credentials.py`.

## Operación

```bash
# Logs
tail -f bot.log

# Reiniciar
launchctl kickstart -k gui/$(id -u)/com.$(whoami).telegram-claude-bot

# Parar
launchctl unload ~/Library/LaunchAgents/com.$(whoami).telegram-claude-bot.plist

# Arrancar
launchctl load ~/Library/LaunchAgents/com.$(whoami).telegram-claude-bot.plist
```

### Comandos del bot

`/start /pwd /cd /reset /voice /safe /think /model /cost`

### Mission Control (Fase 7)

`curl http://localhost:8080/status` → JSON con uptime, queue, sesiones, coste.

## Actualización (`git pull`)

Tus datos personales están en `.gitignore`. `git pull` no los pisa.

```bash
cd ~/telegram-claude-bot
git pull
source venv/bin/activate
pip install -r requirements.txt
# Si hay nuevos secretos a pedir:
python setup_credentials.py
launchctl kickstart -k gui/$(id -u)/com.$(whoami).telegram-claude-bot
```

## Arquitectura

Ver `docs/superpowers/specs/2026-04-09-telegram-bot-evolution-design.md`.
