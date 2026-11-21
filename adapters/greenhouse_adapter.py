"""
Greenhouse ATS Adapter.
Handles application forms on boards.greenhouse.io and custom-hosted Greenhouse portals.
"""

import os
import asyncio
from typing import Dict, Any
from playwright.async_api import Page, Locator
from adapters.base_adapter import BaseAdapter


class GreenhouseAdapter(BaseAdapter):
    async def can_handle(self, page: Page) -> bool:
        url = page.url.lower()
        if "greenhouse.io" in url or "gh_jid" in url:
            return True
        # Check for greenhouse form presence on page
        form = page.locator("form#application_form, form[action*='greenhouse']").first
        return await form.is_visible()

    async def process_application(self, page: Page, mode: str = "copilot") -> Dict[str, Any]:
        job_title = await self._extract_job_title(page)
        company_name = await self._extract_company_name(page)
        job_url = page.url

        # 1. Attach Resume PDF
        await self._attach_resume(page)

        # 2. Fill standard text & custom inputs
        await self._fill_fields(page, job_title, company_name)

        # 3. Locate Submit Button
        submit_btn = page.locator("input#submit_app, button#submit_app, button:has-text('Submit Application')").first
        if await submit_btn.is_visible():
            await self.stealth.smooth_scroll(page, 400)
            if mode == "copilot":
                # LandOffer Style: Highlight and pause for user 1-click review
                await submit_btn.evaluate(
                    "el => { el.style.outline = '4px solid #10B981'; el.style.boxShadow = '0 0 15px #10B981'; }"
                )
                return {
                    "status": "AUTOFILLED_PENDING_REVIEW",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "greenhouse",
                    "message": "Wrangler: Greenhouse application autofilled! Ready for 1-click review & submit."
                }
            else:
                await self.stealth.human_click(page, submit_btn)
                await asyncio.sleep(3.0)
                return {
                    "status": "SUBMITTED",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "greenhouse",
                    "message": "Application submitted automatically to Greenhouse."
                }

        return {
            "status": "FORM_INCOMPLETE",
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
            "platform": "greenhouse",
        }

    async def _fill_fields(self, page: Page, job_title: str, company: str):
        inputs = await page.locator("form#application_form input:not([type='hidden']):not([type='submit']):not([type='file'])").all()
        for inp in inputs:
            if not await inp.is_visible():
                continue
            curr_val = await inp.input_value()
            if curr_val.strip():
                continue

            label = await self._get_label_text(page, inp)
            val, _ = self.resolver.resolve(label, input_type="text")
            if val is None:
                val = await self.llm_router.answer_question(label, job_title, company, input_type="text")
            if val:
                await self.stealth.human_type(inp, val)

        # Textareas (cover letters, subjective questions)
        textareas = await page.locator("form#application_form textarea").all()
        for ta in textareas:
            if not await ta.is_visible():
                continue
            curr_val = await ta.input_value()
            if curr_val.strip():
                continue
            label = await self._get_label_text(page, ta)
            val = await self.llm_router.answer_question(label, job_title, company, input_type="text")
            if val:
                await self.stealth.human_type(ta, val)

        # Select dropdowns
        selects = await page.locator("form#application_form select").all()
        for sel in selects:
            if not await sel.is_visible():
                continue
            label = await self._get_label_text(page, sel)
            val, _ = self.resolver.resolve(label, input_type="select")
            if val:
                try:
                    await sel.select_option(label=val)
                except Exception:
                    pass

    async def _attach_resume(self, page: Page):
        if not os.path.exists(self.resume_path):
            return
        resume_inputs = await page.locator("input[type='file']").all()
        for inp in resume_inputs:
            try:
                await inp.set_input_files(os.path.abspath(self.resume_path))
                await asyncio.sleep(1.0)
                break
            except Exception:
                pass

    async def _get_label_text(self, page: Page, locator: Locator) -> str:
        inp_id = await locator.get_attribute("id")
        if inp_id:
            label = page.locator(f"label[for='{inp_id}']").first
            if await label.is_visible():
                return (await label.inner_text()).strip()
        aria = await locator.get_attribute("aria-label")
        if aria:
            return aria.strip()
        return "Application Field"

    async def _extract_job_title(self, page: Page) -> str:
        loc = page.locator("h1.app-title, .job-name, h1").first
        if await loc.is_visible():
            return (await loc.inner_text()).strip()
        return "Software Engineer"

    async def _extract_company_name(self, page: Page) -> str:
        loc = page.locator(".company-name, span.company, a.company").first
        if await loc.is_visible():
            return (await loc.inner_text()).strip()
        return "Company"
