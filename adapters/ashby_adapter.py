"""
Ashby ATS Adapter.
Handles applications on jobs.ashbyhq.com and Ashby embedded widgets.
"""

import os
import asyncio
from typing import Dict, Any
from playwright.async_api import Page, Locator
from adapters.base_adapter import BaseAdapter


class AshbyAdapter(BaseAdapter):
    async def can_handle(self, page: Page) -> bool:
        url = page.url.lower()
        if "ashbyhq.com" in url:
            return True
        form = page.locator("div[data-testid='application-form'], form[action*='ashby']").first
        return await form.is_visible()

    async def process_application(self, page: Page, mode: str = "copilot") -> Dict[str, Any]:
        job_title = await self._extract_job_title(page)
        company_name = await self._extract_company_name(page)
        job_url = page.url

        # 1. Attach Resume
        await self._attach_resume(page)

        # 2. Fill Fields
        await self._fill_fields(page, job_title, company_name)

        # 3. Locate Submit Button
        submit_btn = page.locator("button[type='submit']:has-text('Submit'), button:has-text('Submit Application')").first
        if await submit_btn.is_visible():
            await self.stealth.smooth_scroll(page, 400)
            if mode == "copilot":
                await submit_btn.evaluate(
                    "el => { el.style.outline = '4px solid #10B981'; el.style.boxShadow = '0 0 15px #10B981'; }"
                )
                return {
                    "status": "AUTOFILLED_PENDING_REVIEW",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "ashby",
                    "message": "Wrangler: Ashby application autofilled! Ready for 1-click review & submit."
                }
            else:
                await self.stealth.human_click(page, submit_btn)
                await asyncio.sleep(3.0)
                return {
                    "status": "SUBMITTED",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "ashby",
                    "message": "Application submitted automatically to Ashby."
                }

        return {
            "status": "FORM_INCOMPLETE",
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
            "platform": "ashby",
        }

    async def _fill_fields(self, page: Page, job_title: str, company: str):
        inputs = await page.locator("input:not([type='hidden']):not([type='file'])").all()
        for inp in inputs:
            if not await inp.is_visible():
                continue
            curr = await inp.input_value()
            if curr.strip():
                continue

            label = await self._get_label_text(page, inp)
            val, _ = self.resolver.resolve(label, input_type="text")
            if val is None:
                val = await self.llm_router.answer_question(label, job_title, company, input_type="text")
            if val:
                await self.stealth.human_type(inp, val)

    async def _attach_resume(self, page: Page):
        if not os.path.exists(self.resume_path):
            return
        inp = page.locator("input[type='file']").first
        if await inp.is_visible():
            try:
                await inp.set_input_files(os.path.abspath(self.resume_path))
                await asyncio.sleep(1.0)
            except Exception:
                pass

    async def _get_label_text(self, page: Page, locator: Locator) -> str:
        aria = await locator.get_attribute("aria-label")
        if aria:
            return aria.strip()
        name = await locator.get_attribute("name")
        if name:
            return name.replace("_", " ")
        return "Field"

    async def _extract_job_title(self, page: Page) -> str:
        loc = page.locator("h1, h2").first
        if await loc.is_visible():
            return (await loc.inner_text()).strip()
        return "Software Engineer"

    async def _extract_company_name(self, page: Page) -> str:
        loc = page.locator("meta[property='og:site_name']").first
        if await loc.count() > 0:
            content = await loc.get_attribute("content")
            if content:
                return content.strip()
        return "Company"
