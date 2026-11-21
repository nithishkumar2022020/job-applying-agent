"""
Naukri.com Stealth Adapter.
Supports India's #1 tech and MNC job portal.
Handles Quick Apply, chatbot screening drawers, CTC/Notice Period inputs,
and LandOffer Co-Pilot (pause at submit) and Autonomous Overnight batch modes.
"""

import os
import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import Page, Locator
from adapters.base_adapter import BaseAdapter


class NaukriAdapter(BaseAdapter):
    async def can_handle(self, page: Page) -> bool:
        url = page.url.lower()
        if "naukri.com" in url:
            # Check if viewing a job listing or apply drawer is open
            if "job-listings" in url or "jobs" in url:
                return True
            apply_btn = page.locator("button.apply-button, button:has-text('Apply'), div.drawer-wrapper").first
            return await apply_btn.is_visible()
        return False

    async def find_and_click_apply(self, page: Page) -> Dict[str, Any]:
        """Locates and clicks the Apply or Quick Apply button on Naukri."""
        # 1. Check if an external apply button ("Apply on Company Site") exists
        company_site_btn = page.locator("button:has-text('Apply on company site'), a:has-text('Apply on company site')").first
        if await company_site_btn.is_visible():
            return {"type": "EXTERNAL", "button": company_site_btn}

        # 2. Check for internal Quick Apply button
        apply_selectors = [
            "button.apply-button:has-text('Apply')",
            "button.apply-button",
            "button:has-text('Quick Apply')",
            "button:has-text('Apply')",
            "div.apply-button-container button",
            "a.apply-button"
        ]
        for sel in apply_selectors:
            btn = page.locator(sel).first
            if await btn.is_visible():
                await self.stealth.human_click(page, btn)
                await asyncio.sleep(2.0)
                return {"type": "INTERNAL", "button": btn}

        return {"type": "NONE", "button": None}

    async def process_application(self, page: Page, mode: str = "copilot") -> Dict[str, Any]:
        """
        Processes a Naukri job application.
        """
        job_title = await self._extract_job_title(page)
        company_name = await self._extract_company_name(page)
        job_url = page.url

        # Check if already applied on page
        already_applied = page.locator("button:has-text('Already Applied'), span:has-text('Applied')").first
        if await already_applied.is_visible():
            return {
                "status": "ALREADY_APPLIED",
                "job_title": job_title,
                "company_name": company_name,
                "job_url": job_url,
                "platform": "naukri",
                "message": "Already applied to this job on Naukri."
            }

        # Check if drawer/questionnaire is already open, or trigger click
        drawer = page.locator("div.drawer-wrapper, div.chatbot_drawer, div[class*='drawer'], div.layer-content").first
        if not await drawer.is_visible():
            click_res = await self.find_and_click_apply(page)
            if click_res["type"] == "NONE":
                return {
                    "status": "NO_APPLY_BUTTON",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "naukri",
                    "message": "No Apply button found on page."
                }
            elif click_res["type"] == "EXTERNAL":
                return {
                    "status": "EXTERNAL_REDIRECT",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "naukri",
                    "message": "Requires applying directly on external company site."
                }

        await asyncio.sleep(1.5)

        # Check if one-click applied immediately without questionnaire
        success_indicators = [
            "div.apply-message:has-text('applied successfully')",
            "div:has-text('You have successfully applied')",
            "span:has-text('Applied successfully')",
            "div.success-msg"
        ]
        for sel in success_indicators:
            succ = page.locator(sel).first
            if await succ.is_visible():
                return {
                    "status": "SUBMITTED",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "naukri",
                    "message": "Applied successfully via Naukri Quick Apply."
                }

        # If a questionnaire or chatbot drawer appeared, fill it step by step
        max_steps = 6
        step = 0

        while step < max_steps:
            step += 1
            await asyncio.sleep(1.0)

            # Fill visible inputs in the questionnaire
            await self._fill_drawer_inputs(page, job_title, company_name)

            # Look for submit/save button
            submit_selectors = [
                "button:has-text('Save & Apply')",
                "button:has-text('Submit and Apply')",
                "button:has-text('Submit')",
                "button:has-text('Send')",
                "button.send-btn",
                "button[id*='submit']",
                "button:has-text('Apply')"
            ]

            submit_btn = None
            for s_sel in submit_selectors:
                btn = page.locator(s_sel).first
                if await btn.is_visible():
                    submit_btn = btn
                    break

            if submit_btn and await submit_btn.is_visible():
                if mode == "copilot":
                    # Highlight submit button for 1-click confirmation
                    await submit_btn.evaluate(
                        "el => { el.style.outline = '4px solid #10B981'; el.style.boxShadow = '0 0 15px #10B981'; }"
                    )
                    return {
                        "status": "AUTOFILLED_PENDING_REVIEW",
                        "job_title": job_title,
                        "company_name": company_name,
                        "job_url": job_url,
                        "platform": "naukri",
                        "step": step,
                        "message": "Wrangler: Naukri application autofilled! Ready for 1-click review & submit."
                    }
                else:
                    await self.stealth.human_click(page, submit_btn)
                    await asyncio.sleep(2.0)
                    return {
                        "status": "SUBMITTED",
                        "job_title": job_title,
                        "company_name": company_name,
                        "job_url": job_url,
                        "platform": "naukri",
                        "step": step,
                        "message": "Naukri application automatically submitted."
                    }

            # Check for next/continue button
            next_btn = page.locator("button:has-text('Next'), button:has-text('Continue')").first
            if await next_btn.is_visible():
                await self.stealth.human_click(page, next_btn)
                continue

            break

        return {
            "status": "SUBMITTED",
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
            "platform": "naukri",
            "message": "Naukri application completed."
        }

    async def _fill_drawer_inputs(self, page: Page, job_title: str, company: str):
        """Answers screening questions in the chatbot/drawer."""
        drawer = page.locator("div.drawer-wrapper, div.chatbot_drawer, div[class*='drawer'], div.layer-content").first
        if not await drawer.is_visible():
            drawer = page

        # 1. Radio / Pill questions (Notice period, CTC range, Experience)
        pills = await drawer.locator("div.chip, span.chip, div.radio-btn, label.radio").all()
        for p in pills:
            try:
                txt = (await p.inner_text()).strip()
                # Check notice period matches (e.g. "15 Days or less", "Immediate")
                if "15" in txt or "immediate" in txt.lower() or "1 month" in txt.lower():
                    await self.stealth.human_click(page, p)
                    await asyncio.sleep(0.5)
            except Exception:
                pass

        # 2. Text / Number inputs
        inputs = await drawer.locator("input:not([type='hidden']):not([type='file'])").all()
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
                await self.stealth.human_type(inp, str(val))

        # 3. Textareas
        textareas = await drawer.locator("textarea").all()
        for ta in textareas:
            if not await ta.is_visible():
                continue
            curr_val = await ta.input_value()
            if curr_val.strip():
                continue
            label = await self._get_label_text(page, ta)
            val = await self.llm_router.answer_question(label, job_title, company, input_type="text")
            if val:
                await self.stealth.human_type(ta, str(val))

    async def _get_label_text(self, page: Page, locator: Locator) -> str:
        # Check placeholder or aria-label
        ph = await locator.get_attribute("placeholder")
        if ph:
            return ph.strip()
        aria = await locator.get_attribute("aria-label")
        if aria:
            return aria.strip()

        # Check label above or sibling
        parent = locator.locator("xpath=ancestor::div[contains(@class, 'form-group') or contains(@class, 'bot-msg') or contains(@class, 'input-container')]").first
        if await parent.is_visible():
            txt = await parent.inner_text()
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            if lines:
                return lines[0]
        return "Naukri question"

    async def _extract_job_title(self, page: Page) -> str:
        selectors = [
            "h1.styles_jd-header-title__rZwM1",
            "h1.title",
            "h1[class*='header-title']",
            "header h1",
            "h1"
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return (await loc.inner_text()).strip()
        return "Flutter Developer"

    async def _extract_company_name(self, page: Page) -> str:
        selectors = [
            "div.styles_jd-header-comp-name__MvqAI a",
            "div.styles_jd-header-comp-name__MvqAI",
            "a.comp-name",
            "div[class*='comp-name']",
            "span.comp-name"
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return (await loc.inner_text()).strip()
        return "Tech Company"
