"""Lectura/escritura de secretos en macOS Keychain.

Servicio: telegram-claude-bot
Cuentas: TELEGRAM_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY
"""
import logging
import os

import keyring

logger = logging.getLogger(__name__)

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


def export_to_env(*names: str) -> None:
    """Carga secretos del Keychain al os.environ del proceso.

    Necesario para que el subproceso `claude` (CLI) herede
    ANTHROPIC_API_KEY del entorno.
    """
    for name in names:
        os.environ[name] = get_secret(name)
