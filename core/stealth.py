"""
Stealth Input & Human-Mimicry Engine.
Ensures typing cadence, mouse interactions, and scroll motions pass anti-bot heuristics.
"""

import asyncio
import math
import random
from typing import Optional


class StealthDriver:
    def __init__(
        self,
        min_keystroke_ms: int = 45,
        max_keystroke_ms: int = 120,
        punctuation_pause_ms: int = 220,
    ):
        self.min_keystroke_s = min_keystroke_ms / 1000.0
        self.max_keystroke_s = max_keystroke_ms / 1000.0
        self.punct_pause_s = punctuation_pause_ms / 1000.0

    async def human_type(self, locator, text: str):
        """
        Types text with realistic human variance and punctuation micro-pauses.
        """
        # Focus element first with small human delay
        await locator.focus()
        await asyncio.sleep(random.uniform(0.1, 0.25))

        # Clear existing content if any
        await locator.fill("")
        await asyncio.sleep(random.uniform(0.05, 0.15))

        for char in str(text):
            # Normal distribution keystroke delay
            delay = random.uniform(self.min_keystroke_s, self.max_keystroke_s)
            await locator.type(char, delay=int(delay * 1000))

            # Emulate occasional human hesitation
            if random.random() < 0.04:
                await asyncio.sleep(random.uniform(0.15, 0.35))

            # Extra pause after spaces and punctuation
            if char in ' ,.:;!?\n':
                await asyncio.sleep(self.punct_pause_s * random.uniform(0.8, 1.3))

    async def human_click(self, page, locator):
        """
        Moves the mouse smoothly to the element target with randomized coordinate offset.
        """
        box = await locator.bounding_box()
        if not box:
            # Fallback direct click if bounding box unavailable
            await locator.click()
            return

        # Randomize point inside the bounding box (avoiding dead-center robotic clicks)
        target_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
        target_y = box["y"] + box["height"] * random.uniform(0.25, 0.75)

        # Smooth mouse move
        steps = random.randint(5, 12)
        await page.mouse.move(target_x, target_y, steps=steps)
        await asyncio.sleep(random.uniform(0.08, 0.20))

        # Click with natural button-down to button-up interval
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.04, 0.12))
        await page.mouse.up()
        await asyncio.sleep(random.uniform(0.15, 0.35))

    async def smooth_scroll(self, page, distance: int = 400):
        """
        Scrolls down with non-linear increments to simulate trackpad gesture.
        """
        steps = random.randint(4, 8)
        step_distance = distance / steps
        for _ in range(steps):
            jitter = step_distance * random.uniform(0.8, 1.2)
            await page.mouse.wheel(0, jitter)
            await asyncio.sleep(random.uniform(0.05, 0.12))

    async def random_pause(self, min_s: float = 1.0, max_s: float = 2.5):
        """Random pause representing human scanning or reading."""
        await asyncio.sleep(random.uniform(min_s, max_s))
