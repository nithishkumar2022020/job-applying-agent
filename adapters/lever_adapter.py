"""
Lever ATS Adapter.
Handles application forms on jobs.lever.co.
"""

import os
import asyncio
from typing import Dict, Any
from playwright.async_api import Page, Locator
from adapters.base_adapter import BaseAdapter


class LeverAdapter(BaseAdapter):
    async def can_handle(self, page: Page) -> bool:
        url = page.url.lower()
        if "lever.co" in url:
            return True
        form = page.locator("form#application-form, div.application-page").first
        return await form.is_visible()

    async def process_application(self, page: Page, mode: str = "copilot") -> Dict[str, Any]:
        job_title = await self._extract_job_title(page)
        company_name = await self._extract_company_name(page)
        job_url = page.url

        # 1. Attach Resume
        await self._attach_resume(page)

        # 2. Fill Lever Standard Fields
        await self._fill_lever_fields(page, job_title, company_name)

        # 3. Handle Submit Button
        submit_btn = page.locator("button#btn-submit, button:has-text('Submit application')").first
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
                    "platform": "lever",
                    "message": "Wrangler: Lever application autofilled! Ready for 1-click review & submit."
                }
            else:
                await self.stealth.human_click(page, submit_btn)
                await asyncio.sleep(3.0)
                return {
                    "status": "SUBMITTED",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "lever",
                    "message": "Application submitted automatically to Lever."
                }

        return {
            "status": "FORM_INCOMPLETE",
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
            "platform": "lever",
        }

    async def _fill_lever_fields(self, page: Page, job_title: str, company: str):
        # Explicit Lever inputs
        name_input = page.locator("input[name='name']").first
        if await name_input.is_visible() and not (await name_input.input_value()):
            await self.stealth.human_type(name_input, self.resolver.personal.get("full_name", ""))

        email_input = page.locator("input[name='email']").first
        if await email_input.is_visible() and not (await email_input.input_value()):
            await self.stealth.human_type(email_input, self.resolver.personal.get("email", ""))

        phone_input = page.locator("input[name='phone']").first
        if await phone_input.is_visible() and not (await phone_input.input_value()):
            await self.stealth.human_type(phone_input, self.resolver.personal.get("phone", ""))

        # Social URLs
        linkedin_inp = page.locator("input[name*='LinkedIn'], input[name*='urls[LinkedIn]']").first
        if await linkedin_inp.is_visible() and not (await linkedin_inp.input_value()):
            await self.stealth.human_type(linkedin_inp, self.resolver.socials.get("linkedin", ""))

        github_inp = page.locator("input[name*='GitHub'], input[name*='urls[GitHub]']").first
        if await github_inp.is_visible() and not (await github_inp.input_value()):
            await self.stealth.human_type(github_inp, self.resolver.socials.get("github", ""))

        # Custom screening questions
        questions = await page.locator("div.application-question").all()
        for q in questions:
            label_loc = q.locator("div.application-label, label").first
            label = (await label_loc.inner_text()).strip() if await label_loc.is_visible() else ""

            # Check text inputs
            text_inp = q.locator("input[type='text']").first
            if await text_inp.is_visible() and not (await text_inp.input_value()):
                val, _ = self.resolver.resolve(label, input_type="text")
                if val is None:
                    val = await self.llm_router.answer_question(label, job_title, company, input_type="text")
                if val:
                    await self.stealth.human_type(text_inp, val)

            # Check textareas
            ta = q.locator("textarea").first
            if await ta.is_visible() and not (await ta.input_value()):
                val = await self.llm_router.answer_question(label, job_title, company, input_type="text")
                if val:
                    await self.stealth.human_type(ta, val)

    async def _attach_resume(self, page: Page):
        if not os.path.exists(self.resume_path):
            return
        resume_inp = page.locator("input[type='file'][name*='resume'], input[type='file']").first
        if await resume_inp.is_visible():
            try:
                await resume_inp.set_input_files(os.path.abspath(self.resume_path))
                await asyncio.sleep(1.0)
            except Exception:
                pass

    async def _extract_job_title(self, page: Page) -> str:
        loc = page.locator("div.posting-headline h2, h2").first
        if await loc.is_visible():
            return (await loc.inner_text()).strip()
        return "Software Engineer"

    async def _extract_company_name(self, page: Page) -> str:
        loc = page.locator("div.main-header-logo img, a.main-header-logo").first
        if await loc.is_visible():
            alt = await loc.get_attribute("alt")
            if alt:
                return alt.strip()
        return "Company"
