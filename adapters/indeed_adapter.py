"""
Indeed & Indeed India Stealth Adapter.
Supports "Easily apply" and "Apply now" flows on in.indeed.com and indeed.com.
Handles multi-step wizards, custom screening questions, resume upload,
and LandOffer Co-Pilot (pause at review) and Autonomous Overnight batch modes.
"""

import os
import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import Page, Locator, Frame
from adapters.base_adapter import BaseAdapter


class IndeedAdapter(BaseAdapter):
    async def can_handle(self, page: Page) -> bool:
        url = page.url.lower()
        if "indeed.com" in url or "indeed.co.in" in url:
            if "viewjob" in url or "jobs" in url:
                return True
            apply_btn = page.locator(
                "button#indeedApplyButton, button[data-testid='indeedApplyButton'], button:has-text('Apply now'), button:has-text('Easily apply')"
            ).first
            return await apply_btn.is_visible()
        return False

    async def find_and_click_apply(self, page: Page) -> bool:
        """Finds and clicks Indeed's Easily Apply / Apply Now button."""
        apply_selectors = [
            "button#indeedApplyButton",
            "button[data-testid='indeedApplyButton']",
            "button:has-text('Apply now')",
            "button:has-text('Easily apply')",
            "div.jobsearch-IndeedApplyButton button",
            "span:has-text('Apply now')"
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
        Processes an Indeed Apply multi-step modal or iframe.
        """
        job_title = await self._extract_job_title(page)
        company_name = await self._extract_company_name(page)
        job_url = page.url

        # Check if already applied
        applied_badge = page.locator("div:has-text('You applied to this job'), span:has-text('Applied')").first
        if await applied_badge.is_visible():
            return {
                "status": "ALREADY_APPLIED",
                "job_title": job_title,
                "company_name": company_name,
                "job_url": job_url,
                "platform": "indeed",
                "message": "Already applied to this job on Indeed."
            }

        # Look for open modal or trigger click
        modal = page.locator("div.ia-JobApplication, div[role='dialog'], div.jobsearch-Modal").first
        if not await modal.is_visible():
            opened = await self.find_and_click_apply(page)
            if not opened:
                return {
                    "status": "NO_EASY_APPLY_FOUND",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "indeed",
                    "message": "No Indeed Apply button available on this job."
                }
            await asyncio.sleep(2.0)

        # Indeed Apply may render inside an iframe or directly in a modal
        context_target = page
        for frame in page.frames:
            if "indeed" in frame.url and ("apply" in frame.url or "post-apply" in frame.url):
                context_target = frame
                break

        max_steps = 8
        step = 0

        while step < max_steps:
            step += 1
            await asyncio.sleep(1.0)

            # 1. Fill current step inputs
            await self._fill_step_inputs(context_target, page, job_title, company_name)

            # 2. Attach resume if file input is visible
            await self._handle_file_uploads(context_target)

            # 3. Locate action buttons
            submit_selectors = [
                "button:has-text('Submit your application')",
                "button:has-text('Submit application')",
                "button:has-text('Submit')",
                "button[data-testid='submit-application-button']"
            ]
            review_selectors = [
                "button:has-text('Review your application')",
                "button:has-text('Review')"
            ]
            continue_selectors = [
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "button[data-testid='continue-button']"
            ]

            submit_btn = None
            for s in submit_selectors:
                b = context_target.locator(s).first
                if await b.is_visible():
                    submit_btn = b
                    break

            if submit_btn and await submit_btn.is_visible():
                if mode == "copilot":
                    await submit_btn.evaluate(
                        "el => { el.style.outline = '4px solid #10B981'; el.style.boxShadow = '0 0 15px #10B981'; }"
                    )
                    return {
                        "status": "AUTOFILLED_PENDING_REVIEW",
                        "job_title": job_title,
                        "company_name": company_name,
                        "job_url": job_url,
                        "platform": "indeed",
                        "step": step,
                        "message": "Wrangler: Indeed application autofilled! Ready for 1-click review & submit."
                    }
                else:
                    await self.stealth.human_click(page, submit_btn)
                    await asyncio.sleep(2.5)
                    return {
                        "status": "SUBMITTED",
                        "job_title": job_title,
                        "company_name": company_name,
                        "job_url": job_url,
                        "platform": "indeed",
                        "step": step,
                        "message": "Indeed application automatically submitted."
                    }

            # Check review button
            for r in review_selectors:
                rb = context_target.locator(r).first
                if await rb.is_visible():
                    await self.stealth.human_click(page, rb)
                    await asyncio.sleep(1.5)
                    continue

            # Check continue / next button
            clicked_next = False
            for c in continue_selectors:
                cb = context_target.locator(c).first
                if await cb.is_visible():
                    await self.stealth.human_click(page, cb)
                    clicked_next = True
                    await asyncio.sleep(1.5)
                    break

            if not clicked_next:
                break

        return {
            "status": "COMPLETED_OR_UNKNOWN",
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
            "platform": "indeed",
            "step": step
        }

    async def _fill_step_inputs(self, ctx, page: Page, job_title: str, company: str):
        """Fills text, radio, and select inputs in Indeed Apply."""
        # 1. Inputs
        inputs = await ctx.locator("input:not([type='hidden']):not([type='file']):not([type='checkbox']):not([type='radio'])").all()
        for inp in inputs:
            if not await inp.is_visible():
                continue
            curr_val = await inp.input_value()
            if curr_val.strip():
                continue

            label = await self._get_label_text(ctx, inp)
            val, _ = self.resolver.resolve(label, input_type="text")
            if val is None:
                val = await self.llm_router.answer_question(label, job_title, company, input_type="text")

            if val:
                await self.stealth.human_type(inp, str(val))

        # 2. Textareas
        tas = await ctx.locator("textarea").all()
        for ta in tas:
            if not await ta.is_visible():
                continue
            curr_val = await ta.input_value()
            if curr_val.strip():
                continue
            label = await self._get_label_text(ctx, ta)
            val = await self.llm_router.answer_question(label, job_title, company, input_type="text")
            if val:
                await self.stealth.human_type(ta, str(val))

        # 3. Radio groups
        fieldsets = await ctx.locator("fieldset").all()
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
                choice = "Yes" if "yes" in val.lower() else "No"
                radio_btn = fs.locator(f"label:has-text('{choice}'), input[value*='{choice.lower()}']").first
                if await radio_btn.is_visible():
                    await self.stealth.human_click(page, radio_btn)

    async def _handle_file_uploads(self, ctx):
        if not os.path.exists(self.resume_path):
            return
        file_inputs = await ctx.locator("input[type='file']").all()
        for f_inp in file_inputs:
            try:
                await f_inp.set_input_files(os.path.abspath(self.resume_path))
                await asyncio.sleep(1.0)
            except Exception:
                pass

    async def _get_label_text(self, ctx, locator: Locator) -> str:
        aria = await locator.get_attribute("aria-label")
        if aria:
            return aria.strip()
        input_id = await locator.get_attribute("id")
        if input_id:
            lbl = ctx.locator(f"label[for='{input_id}']").first
            if await lbl.is_visible():
                return (await lbl.inner_text()).strip()
        parent = locator.locator("xpath=ancestor::div[contains(@class, 'ia-') or contains(@class, 'css-')]").first
        if await parent.is_visible():
            txt = await parent.inner_text()
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            if lines:
                return lines[0]
        return "Indeed question"

    async def _extract_job_title(self, page: Page) -> str:
        selectors = [
            "h1.jobsearch-JobInfoHeader-title",
            "h2.jobTitle",
            "h1[data-testid='jobsearch-JobInfoHeader-title']",
            "h1"
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return (await loc.inner_text()).strip()
        return "Flutter Developer"

    async def _extract_company_name(self, page: Page) -> str:
        selectors = [
            "div[data-company-name='true']",
            "div.jobsearch-CompanyInfoContainer a",
            "span.companyName",
            "div.company_name"
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return (await loc.inner_text()).strip()
        return "Company"
