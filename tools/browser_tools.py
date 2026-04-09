"""Tools de navegación web persistente para el bot.

Usa Playwright en modo asíncrono con launch_persistent_context
para mantener sesiones de login entre reinicios.
"""
import asyncio
import logging
import os
from typing import Optional

from claude_agent_sdk import tool
from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

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
        return text[:8000]
    finally:
        await page.close()


@tool(
    name="browser_click",
    description=(
        "Hace clic en un selector CSS de una URL y devuelve el texto resultante."
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
