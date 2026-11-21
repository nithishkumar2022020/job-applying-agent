"""
LinkedIn Easy Apply Stealth Adapter.
Navigates multi-step modals, auto-attaches resume, answers screening questions,
and handles LandOffer Co-Pilot (pause at review) and Autonomous Overnight modes.
"""

import os
import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import Page, Locator
from adapters.base_adapter import BaseAdapter


class LinkedInAdapter(BaseAdapter):
    async def can_handle(self, page: Page) -> bool:
        url = page.url
        return "linkedin.com" in url

    async def find_and_click_easy_apply(self, page: Page) -> bool:
        """Finds and clicks the Easy Apply button on a LinkedIn job details page."""
        easy_apply_selectors = [
            "button.jobs-apply-button:has-text('Easy Apply')",
            "button:has-text('Easy Apply')",
            "div.jobs-apply-button--top-card button:has-text('Easy Apply')"
        ]
        for sel in easy_apply_selectors:
            btn = page.locator(sel).first
            if await btn.is_visible():
                await self.stealth.human_click(page, btn)
                await asyncio.sleep(1.5)
                return True
        return False

    async def process_application(self, page: Page, mode: str = "copilot") -> Dict[str, Any]:
        """
        Processes an open Easy Apply modal through all steps.
        """
        modal = page.locator("div.jobs-easy-apply-modal, div[role='dialog']:has-text('Easy Apply')").first
        if not await modal.is_visible():
            opened = await self.find_and_click_easy_apply(page)
            if not opened:
                return {"status": "NO_EASY_APPLY_FOUND", "message": "No Easy Apply button available"}
            await asyncio.sleep(1.5)

        # Extract job title and company from page
        job_title = await self._extract_job_title(page)
        company_name = await self._extract_company_name(page)
        job_url = page.url

        max_steps = 8
        step = 0

        while step < max_steps:
            step += 1
            await asyncio.sleep(1.0)

            # Step 1: Fill any visible inputs on current step
            await self._fill_step_inputs(page, job_title, company_name)

            # Step 2: Handle resume upload if requested
            await self._handle_file_uploads(page)

            # Step 3: Check next action button
            submit_btn = page.locator("button[aria-label='Submit application'], button:has-text('Submit application')").first
            review_btn = page.locator("button[aria-label='Review your application'], button:has-text('Review')").first
            next_btn = page.locator("button[aria-label='Continue to next step'], button:has-text('Next')").first

            # Are we on the final review / submit step?
            if await submit_btn.is_visible():
                if mode == "copilot":
                    # Wrangler Co-Pilot: Highlight and pause for user 1-click confirmation
                    await self._highlight_element(page, submit_btn)
                    return {
                        "status": "AUTOFILLED_PENDING_REVIEW",
                        "job_title": job_title,
                        "company_name": company_name,
                        "job_url": job_url,
                        "step": step,
                        "message": "Wrangler: Application autofilled! Ready for 1-click review & submit."
                    }
                else:
                    # Autonomous Mode: Click submit
                    await self.stealth.human_click(page, submit_btn)
                    await asyncio.sleep(2.0)
                    await self._dismiss_done_modal(page)
                    return {
                        "status": "SUBMITTED",
                        "job_title": job_title,
                        "company_name": company_name,
                        "job_url": job_url,
                        "step": step,
                        "message": "Application automatically submitted."
                    }

            if await review_btn.is_visible():
                await self.stealth.human_click(page, review_btn)
                continue

            if await next_btn.is_visible():
                await self.stealth.human_click(page, next_btn)
                continue

            # If no forward button, check if completed
            break

        return {
            "status": "COMPLETED_OR_UNKNOWN",
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
            "step": step
        }

    async def _fill_step_inputs(self, page: Page, job_title: str, company: str):
        """Scans and answers all text, select, and radio questions in the current modal step."""
        modal = page.locator("div.jobs-easy-apply-modal, div[role='dialog']").first

        # 1. Text & Number Inputs
        inputs = await modal.locator("input:not([type='hidden']):not([type='file']):not([type='checkbox']):not([type='radio'])").all()
        for inp in inputs:
            if not await inp.is_visible():
                continue
            curr_val = await inp.input_value()
            if curr_val.strip():  # Already pre-filled by LinkedIn
                continue

            # Find associated label
            label = await self._get_label_for_input(page, inp)
            val, _ = self.resolver.resolve(label, input_type="text")
            if val is None:
                val = await self.llm_router.answer_question(label, job_title, company, input_type="text")
            if val:
                await self.stealth.human_type(inp, val)

        # 2. Textarea elements
        textareas = await modal.locator("textarea").all()
        for ta in textareas:
            if not await ta.is_visible():
                continue
            curr_val = await ta.input_value()
            if curr_val.strip():
                continue
            label = await self._get_label_for_input(page, ta)
            val = await self.llm_router.answer_question(label, job_title, company, input_type="text")
            if val:
                await self.stealth.human_type(ta, val)

        # 3. Dropdowns (<select>)
        selects = await modal.locator("select").all()
        for sel in selects:
            if not await sel.is_visible():
                continue
            label = await self._get_label_for_input(page, sel)
            val, _ = self.resolver.resolve(label, input_type="select")
            if val is None:
                val = await self.llm_router.answer_question(label, job_title, company, input_type="select")
            if val:
                try:
                    await sel.select_option(label=val)
                except Exception:
                    # Try partial match or fallback
                    pass

        # 4. Radio Fieldsets (e.g. Yes/No work auth questions)
        fieldsets = await modal.locator("fieldset").all()
        for fs in fieldsets:
            if not await fs.is_visible():
                continue
            legend = fs.locator("legend").first
            label = await legend.inner_text() if await legend.is_visible() else ""
            if not label:
                continue

            val, _ = self.resolver.resolve(label, input_type="radio")
            if val is None:
                val = await self.llm_router.answer_question(label, job_title, company, input_type="radio")

            if val:
                # Select the radio matching 'Yes' or 'No'
                choice = "Yes" if "yes" in val.lower() else "No"
                radio_btn = fs.locator(f"label:has-text('{choice}'), input[value='{choice}']").first
                if await radio_btn.is_visible():
                    await self.stealth.human_click(page, radio_btn)

    async def _handle_file_uploads(self, page: Page):
        """Attaches the resume PDF if an upload input is present."""
        if not os.path.exists(self.resume_path):
            return

        file_inputs = await page.locator("input[type='file']").all()
        for f_inp in file_inputs:
            try:
                await f_inp.set_input_files(os.path.abspath(self.resume_path))
                await asyncio.sleep(1.0)
            except Exception:
                pass

    async def _get_label_for_input(self, page: Page, input_locator: Locator) -> str:
        """Extracts label text via id/for attribute, aria-label, or preceding text."""
        aria_label = await input_locator.get_attribute("aria-label")
        if aria_label:
            return aria_label.strip()

        input_id = await input_locator.get_attribute("id")
        if input_id:
            label = page.locator(f"label[for='{input_id}']").first
            if await label.is_visible():
                return (await label.inner_text()).strip()

        # Check parent container label
        parent = input_locator.locator("xpath=ancestor::div[contains(@class, 'fb-dash-form-element') or contains(@class, 'jobs-easy-apply-form-element')]").first
        if await parent.is_visible():
            label = parent.locator("label").first
            if await label.is_visible():
                return (await label.inner_text()).strip()

        return "Screening question"

    async def _extract_job_title(self, page: Page) -> str:
        selectors = [
            "h1.job-details-jobs-unified-top-card__job-title",
            "h1.t-24",
            "h2.job-details-jobs-unified-top-card__job-title",
            "div.jobs-unified-top-card h1"
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return (await loc.inner_text()).strip()
        return "Unknown Role"

    async def _extract_company_name(self, page: Page) -> str:
        selectors = [
            "div.job-details-jobs-unified-top-card__company-name a",
            "div.job-details-jobs-unified-top-card__company-name",
            "a.ember-view.t-black--light"
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return (await loc.inner_text()).strip()
        return "Unknown Company"

    async def _dismiss_done_modal(self, page: Page):
        dismiss_btn = page.locator("button[aria-label='Dismiss'], button:has-text('Done')").first
        if await dismiss_btn.is_visible():
            await self.stealth.human_click(page, dismiss_btn)

    async def _highlight_element(self, page: Page, element: Locator):
        """Highlights the submit button with a glowing border on the user's real screen."""
        try:
            await element.evaluate(
                "el => { el.style.outline = '4px solid #10B981'; el.style.boxShadow = '0 0 15px #10B981'; }"
            )
        except Exception:
            pass
