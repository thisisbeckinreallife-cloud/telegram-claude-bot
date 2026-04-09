"""Pide las 3 keys por teclado (input oculto) y las escribe en .env."""
import os
from getpass import getpass

ENV_PATH = "/Users/lara/telegram-claude-bot/.env"

print("\n== Configuración del .env ==")
print("Pega cada valor cuando se te pida y pulsa Enter.")
print("La entrada está oculta — no verás lo que pegas, es normal.\n")

tg = getpass("TELEGRAM_TOKEN (de @BotFather): ").strip()
an = getpass("ANTHROPIC_API_KEY (de console.anthropic.com): ").strip()
op = getpass("OPENAI_API_KEY (de platform.openai.com): ").strip()

if not tg or not an or not op:
    print("\n❌ Alguna key estaba vacía. Aborto.")
    raise SystemExit(1)

content = (
    f"TELEGRAM_TOKEN={tg}\n"
    f"ANTHROPIC_API_KEY={an}\n"
    f"OPENAI_API_KEY={op}\n"
    f"ALLOWED_USER_ID=6110475762\n"
    f"WORKING_DIR=/Users/lara/proyectos\n"
)
with open(ENV_PATH, "w") as f:
    f.write(content)
os.chmod(ENV_PATH, 0o600)

print(f"\n✅ Guardado en {ENV_PATH}")
print("Longitudes:")
print(f"  TELEGRAM_TOKEN:    {len(tg)} caracteres")
print(f"  ANTHROPIC_API_KEY: {len(an)} caracteres")
print(f"  OPENAI_API_KEY:    {len(op)} caracteres")
