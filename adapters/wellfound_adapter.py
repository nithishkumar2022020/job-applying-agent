"""
Wellfound (AngelList Talent) Stealth Adapter.
Supports high-growth tech startups and remote developer hiring.
Generates tailored founder/hiring manager pitch notes, attaches resume,
and handles LandOffer Co-Pilot (pause at submit) and Autonomous Overnight modes.
"""

import os
import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import Page, Locator
from adapters.base_adapter import BaseAdapter


class WellfoundAdapter(BaseAdapter):
    async def can_handle(self, page: Page) -> bool:
        url = page.url.lower()
        if "wellfound.com" in url or "angel.co" in url:
            # Check if on a job page or modal is open
            if "/jobs" in url or "/company" in url:
                return True
            modal = page.locator("div[role='dialog']:has-text('Apply'), textarea[name='note']").first
            return await modal.is_visible()
        return False

    async def find_and_click_apply(self, page: Page) -> bool:
        """Finds and clicks the primary Apply button on a Wellfound job listing."""
        apply_selectors = [
            "button:has-text('Apply to position')",
            "button:has-text('Apply')",
            "button[data-test='JobListingApplyButton']",
            "button[data-test='JobPostApplyButton']",
            "a:has-text('Apply')"
        ]
        for sel in apply_selectors:
            btn = page.locator(sel).first
            if await btn.is_visible():
                await self.stealth.human_click(page, btn)
                await asyncio.sleep(2.0)
                return True
        return False

    async def process_application(self, page: Page, mode: str = "copilot") -> Dict[str, Any]:
        """
        Processes a Wellfound application modal.
        """
        job_title = await self._extract_job_title(page)
        company_name = await self._extract_company_name(page)
        job_url = page.url

        modal = page.locator("div[role='dialog'], div[class*='modal']").first
        if not await modal.is_visible():
            opened = await self.find_and_click_apply(page)
            if not opened:
                return {
                    "status": "NO_APPLY_BUTTON",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "wellfound",
                    "message": "No Apply button found on Wellfound page."
                }
            await asyncio.sleep(2.0)

        # Re-check modal
        modal = page.locator("div[role='dialog'], div[class*='modal']").first
        if not await modal.is_visible():
            modal = page

        # 1. Fill Note / Pitch to the Founder/Hiring Manager
        note_area = modal.locator(
            "textarea[name='note'], textarea[placeholder*='pitch'], textarea[placeholder*='note'], textarea"
        ).first
        if await note_area.is_visible():
            curr_note = await note_area.input_value()
            if not curr_note.strip():
                # Generate high-impact personalized pitch note
                pitch_prompt = (
                    f"Write a concise, professional 3-sentence note to the founder/recruiter at {company_name} "
                    f"for the {job_title} role. Highlight 3 years of Flutter & Dart mobile experience, production "
                    f"architecture (BLoC/Riverpod), and enthusiasm for building their product."
                )
                note_text = await self.llm_router.answer_question(
                    question=pitch_prompt,
                    job_title=job_title,
                    company=company_name,
                    input_type="text"
                )
                if not note_text or "fallback" in note_text.lower():
                    note_text = (
                        f"Hi {company_name} team,\n\n"
                        f"I'm excited to apply for the {job_title} role. With over 3 years of experience building "
                        f"high-performance Flutter applications with scalable state management (BLoC/Riverpod) "
                        f"and smooth 60fps UX, I can immediately contribute to your product engineering. "
                        f"Looking forward to connecting!\n\n"
                        f"Best regards,\nNithish Kumar Reddy"
                    )
                await self.stealth.human_type(note_area, note_text)
                await asyncio.sleep(1.0)

        # 2. Check for salary / compensation expectation inputs
        salary_input = modal.locator("input[name*='salary'], input[placeholder*='salary'], input[type='number']").first
        if await salary_input.is_visible():
            val, _ = self.resolver.resolve("expected ctc inr")
            if val:
                await self.stealth.human_type(salary_input, str(val))

        # 3. Check for resume upload input
        await self._handle_file_uploads(modal)

        # 4. Locate Submit / Send Application Button
        send_selectors = [
            "button:has-text('Send application')",
            "button:has-text('Submit application')",
            "button:has-text('Submit')",
            "button:has-text('Send')",
            "button[type='submit']"
        ]

        submit_btn = None
        for s_sel in send_selectors:
            btn = modal.locator(s_sel).first
            if await btn.is_visible():
                submit_btn = btn
                break

        if submit_btn and await submit_btn.is_visible():
            if mode == "copilot":
                # Highlight submit button for 1-click review
                await submit_btn.evaluate(
                    "el => { el.style.outline = '4px solid #10B981'; el.style.boxShadow = '0 0 15px #10B981'; }"
                )
                return {
                    "status": "AUTOFILLED_PENDING_REVIEW",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "wellfound",
                    "message": "Wrangler: Wellfound pitch note autofilled! Ready for 1-click review & send."
                }
            else:
                await self.stealth.human_click(page, submit_btn)
                await asyncio.sleep(2.5)
                return {
                    "status": "SUBMITTED",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "wellfound",
                    "message": "Application and tailored pitch note submitted on Wellfound."
                }

        return {
            "status": "FORM_INCOMPLETE",
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
            "platform": "wellfound",
            "message": "Could not locate final submit button in Wellfound modal."
        }

    async def _handle_file_uploads(self, container: Locator):
        if not os.path.exists(self.resume_path):
            return
        file_inputs = await container.locator("input[type='file']").all()
        for f_inp in file_inputs:
            try:
                await f_inp.set_input_files(os.path.abspath(self.resume_path))
                await asyncio.sleep(1.0)
            except Exception:
                pass

    async def _extract_job_title(self, page: Page) -> str:
        selectors = [
            "h1[data-test='JobListingTitle']",
            "h1.styles_title__",
            "h1",
            "h2[data-test='JobListingTitle']"
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return (await loc.inner_text()).strip()
        return "Flutter Developer"

    async def _extract_company_name(self, page: Page) -> str:
        selectors = [
            "a[data-test='StartupName']",
            "span[data-test='StartupName']",
            "div.styles_startupName__",
            "header a"
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return (await loc.inner_text()).strip()
        return "Tech Startup"
