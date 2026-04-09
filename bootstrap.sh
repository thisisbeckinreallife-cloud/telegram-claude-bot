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
# shellcheck disable=SC1091
source "$REPO_DIR/venv/bin/activate"

# 3. Instalar requirements
echo "==> Instalando requirements"
pip install --upgrade pip
pip install -r "$REPO_DIR/requirements.txt"

# 4. Instalar Playwright Chromium (Fase 4 — opcional)
if grep -q '^playwright' "$REPO_DIR/requirements.txt"; then
    echo "==> Instalando Playwright Chromium"
    python -m playwright install chromium || echo "⚠️  Playwright install falló (Fase 4 no funcionará)"
fi

# 5. Bootstrap del Keychain
if ! python -c "import keyring; assert keyring.get_password('telegram-claude-bot', 'TELEGRAM_TOKEN')" 2>/dev/null; then
    echo "==> Configurando Keychain"
    python "$REPO_DIR/setup_credentials.py"
else
    echo "==> Keychain ya configurado"
fi

# 6. Crear .env desde .env.example si no existe
if [[ ! -f "$REPO_DIR/.env" && -f "$REPO_DIR/.env.example" ]]; then
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
