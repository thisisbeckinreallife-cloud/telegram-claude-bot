"""Prueba directa del SDK sin Telegram para diagnosticar fallos."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv("/Users/lara/telegram-claude-bot/.env")
os.environ["PATH"] = f"/Users/lara/.local/bin:{os.environ.get('PATH', '')}"

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)


async def main():
    options = ClaudeAgentOptions(
        cwd="/Users/lara/proyectos",
        permission_mode="bypassPermissions",
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
        stderr=lambda line: print(f"[CLI] {line}"),
    )
    print(f">>> model: {options.model}")
    print(">>> connecting...")
    client = ClaudeSDKClient(options=options)
    await client.connect()
    print(">>> sending: hola, di solo OK")
    await client.query("hola, di solo OK")
    print(">>> receiving...")
    async for msg in client.receive_response():
        print(f"  type={type(msg).__name__}")
        if isinstance(msg, AssistantMessage):
            for b in msg.content or []:
                print(f"    block={type(b).__name__} text={getattr(b, 'text', None)[:200] if getattr(b, 'text', None) else None}")
        elif isinstance(msg, ResultMessage):
            print(f"    is_error={msg.is_error} subtype={msg.subtype} result={msg.result!r}")
    await client.disconnect()
    print(">>> done")


asyncio.run(main())
