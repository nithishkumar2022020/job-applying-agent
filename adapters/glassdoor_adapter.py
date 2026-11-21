"""
Glassdoor Stealth Adapter.
Supports "Easy Apply" flows on glassdoor.com and glassdoor.co.in.
Handles embedded application overlays, resume attachments, and screening questions.
"""

import os
import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import Page, Locator
from adapters.base_adapter import BaseAdapter


class GlassdoorAdapter(BaseAdapter):
    async def can_handle(self, page: Page) -> bool:
        url = page.url.lower()
        if "glassdoor.com" in url or "glassdoor.co.in" in url:
            if "job" in url or "Job" in url:
                return True
            easy_btn = page.locator("button[data-test='easyApply'], button:has-text('Easy Apply')").first
            return await easy_btn.is_visible()
        return False

    async def find_and_click_easy_apply(self, page: Page) -> bool:
        selectors = [
            "button[data-test='easyApply']",
            "button:has-text('Easy Apply')",
            "button:has-text('Easily apply')",
            "div.JobDetails_applyButtonContainer__ button"
        ]
        for sel in selectors:
            btn = page.locator(sel).first
            if await btn.is_visible():
                await self.stealth.human_click(page, btn)
                await asyncio.sleep(2.0)
                return True
        return False

    async def process_application(self, page: Page, mode: str = "copilot") -> Dict[str, Any]:
        job_title = await self._extract_job_title(page)
        company_name = await self._extract_company_name(page)
        job_url = page.url

        modal = page.locator("div[data-test='modal-content'], div[role='dialog']").first
        if not await modal.is_visible():
            opened = await self.find_and_click_easy_apply(page)
            if not opened:
                return {
                    "status": "NO_EASY_APPLY_FOUND",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "glassdoor",
                    "message": "No Easy Apply button available on Glassdoor."
                }
            await asyncio.sleep(2.0)

        modal = page.locator("div[data-test='modal-content'], div[role='dialog']").first
        if not await modal.is_visible():
            modal = page

        # Check for inputs
        inputs = await modal.locator("input:not([type='hidden']):not([type='file'])").all()
        for inp in inputs:
            if not await inp.is_visible():
                continue
            curr = await inp.input_value()
            if curr.strip():
                continue
            label = await inp.get_attribute("aria-label") or await inp.get_attribute("placeholder") or "Glassdoor Field"
            val, _ = self.resolver.resolve(label, input_type="text")
            if val is None:
                val = await self.llm_router.answer_question(label, job_title, company_name, input_type="text")
            if val:
                await self.stealth.human_type(inp, str(val))

        # Check for file upload
        if os.path.exists(self.resume_path):
            file_inps = await modal.locator("input[type='file']").all()
            for f_inp in file_inps:
                try:
                    await f_inp.set_input_files(os.path.abspath(self.resume_path))
                    await asyncio.sleep(1.0)
                except Exception:
                    pass

        # Locate submit button
        submit_btn = modal.locator(
            "button:has-text('Submit your application'), button:has-text('Submit'), button:has-text('Send application')"
        ).first
        if await submit_btn.is_visible():
            if mode == "copilot":
                await submit_btn.evaluate(
                    "el => { el.style.outline = '4px solid #10B981'; el.style.boxShadow = '0 0 15px #10B981'; }"
                )
                return {
                    "status": "AUTOFILLED_PENDING_REVIEW",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "glassdoor",
                    "message": "Wrangler: Glassdoor application autofilled! Ready for 1-click review & submit."
                }
            else:
                await self.stealth.human_click(page, submit_btn)
                await asyncio.sleep(2.5)
                return {
                    "status": "SUBMITTED",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "glassdoor",
                    "message": "Glassdoor application automatically submitted."
                }

        return {
            "status": "COMPLETED_OR_UNKNOWN",
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
            "platform": "glassdoor"
        }

    async def _extract_job_title(self, page: Page) -> str:
        loc = page.locator("h1[data-test='job-title'], h1.heading_Heading__").first
        if await loc.is_visible():
            return (await loc.inner_text()).strip()
        return "Flutter Developer"

    async def _extract_company_name(self, page: Page) -> str:
        loc = page.locator("span[data-test='employer-name'], div.JobDetails_employerName__").first
        if await loc.is_visible():
            return (await loc.inner_text()).strip()
        return "Company"
