"""Bootstrap interactivo del Keychain para el bot.

Uso:
    python setup_credentials.py

Pide cada secreto con getpass (input oculto) y lo guarda en macOS Keychain.
Si encuentra un .env legacy con TELEGRAM_TOKEN, ofrece migrar automáticamente.
"""
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
