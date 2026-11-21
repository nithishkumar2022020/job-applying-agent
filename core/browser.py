"""
Chrome DevTools Protocol (CDP) Connection Manager.
Connects directly to your daily Google Chrome instance to bypass bot flags,
inherit login sessions, and eliminate CAPTCHAs.
"""

import asyncio
import os
import subprocess
from typing import Optional, Tuple
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class BrowserBridge:
    def __init__(self, cdp_url: str = "http://localhost:9222", timeout_ms: int = 8000):
        self.cdp_url = cdp_url
        self.timeout_ms = timeout_ms
        self._pw = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def connect(self) -> Tuple[Browser, BrowserContext, Page]:
        """
        Connects over CDP to the running Chrome process.
        Returns (browser, context, active_page).
        """
        self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.connect_over_cdp(
                endpoint_url=self.cdp_url,
                timeout=self.timeout_ms
            )
        except Exception as e:
            await self._pw.stop()
            raise ConnectionError(
                f"Could not connect to Chrome on {self.cdp_url}.\n"
                f"Make sure Chrome was launched with remote debugging enabled:\n"
                f"  Run: bash job_apply_agent/scripts/launch_chrome.sh\n"
                f"Original error: {e}"
            )

        contexts = self._browser.contexts
        if not contexts:
            raise RuntimeError("No browser context found in running Chrome instance.")

        self._context = contexts[0]
        pages = self._context.pages
        page = pages[0] if pages else await self._context.new_page()

        # Bring page to front
        await page.bring_to_front()
        return self._browser, self._context, page

    async def get_active_page(self) -> Page:
        """Finds or returns the current active tab."""
        if not self._context:
            raise RuntimeError("Browser not connected. Call connect() first.")
        pages = self._context.pages
        if not pages:
            return await self._context.new_page()
        # Return the most recently active or last page
        return pages[-1]

    async def disconnect(self):
        """Disconnects Playwright from Chrome without terminating your Chrome browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
