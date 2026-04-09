"""Construcción del callback can_use_tool para el modo safe.

Envía confirmaciones por Telegram cuando una tool no está en SAFE_TOOLS
y no está en session.trusted_tools.
"""
import asyncio
import logging

from claude_agent_sdk import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.session import ChatSession

logger = logging.getLogger(__name__)

SAFE_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
    "NotebookRead",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
}


def make_can_use_tool(session: ChatSession):
    async def can_use_tool(
        tool_name: str,
        tool_input: dict,
        context: ToolPermissionContext,
    ):
        if tool_name in SAFE_TOOLS or tool_name in session.trusted_tools:
            return PermissionResultAllow(updated_input=tool_input)

        try:
            preview = ", ".join(f"{k}={str(v)[:120]}" for k, v in tool_input.items())
        except Exception:
            preview = str(tool_input)[:400]
        if len(preview) > 600:
            preview = preview[:600] + "..."

        if session.bot_app is None:
            return PermissionResultDeny(message="Bot no inicializado")

        session._approval_counter += 1
        approval_id = str(session._approval_counter)

        loop = asyncio.get_running_loop()
        decision_future = loop.create_future()
        session.pending_approvals[approval_id] = (tool_name, decision_future)
        await session.pending_decisions.put((tool_name, decision_future))

        msg = (
            f"⚠️ Confirmación requerida\n\n"
            f"Herramienta: {tool_name}\n"
            f"{preview}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ SI", callback_data=f"approve:{session.chat_id}:{approval_id}:allow"),
                InlineKeyboardButton("✅ SIEMPRE", callback_data=f"approve:{session.chat_id}:{approval_id}:always"),
                InlineKeyboardButton("❌ NO", callback_data=f"approve:{session.chat_id}:{approval_id}:deny"),
            ]
        ])
        await session.bot_app.bot.send_message(
            chat_id=session.chat_id, text=msg, reply_markup=keyboard
        )
        try:
            decision = await asyncio.wait_for(decision_future, timeout=300)
        except asyncio.TimeoutError:
            decision = "deny"

        if decision == "always":
            session.trusted_tools.add(tool_name)
            return PermissionResultAllow(updated_input=tool_input)
        if decision == "allow":
            return PermissionResultAllow(updated_input=tool_input)
        return PermissionResultDeny(message="El usuario denegó la acción.")

    return can_use_tool
