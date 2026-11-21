"""
Workday ATS Stealth Adapter.
Supports enterprise MNC career portals (*.myworkdayjobs.com).
Used by Amazon, Adobe, Salesforce, Nvidia, Dell, HP, Walmart, Target, Deloitte, Accenture, etc.
Handles Workday data-automation-id inputs, resume upload, and multi-step steppers.
"""

import os
import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import Page, Locator
from adapters.base_adapter import BaseAdapter


class WorkdayAdapter(BaseAdapter):
    async def can_handle(self, page: Page) -> bool:
        url = page.url.lower()
        if "myworkdayjobs.com" in url or "workday" in url:
            return True
        # Check for Workday DOM signature
        wd_elem = page.locator("[data-automation-id]").first
        return await wd_elem.is_visible()

    async def find_and_click_apply(self, page: Page) -> bool:
        """Finds and clicks Workday's Apply button."""
        apply_selectors = [
            "a[data-automation-id='adventureButton']",
            "button[data-automation-id='apply']",
            "a[data-automation-id='apply']",
            "a:has-text('Apply')",
            "button:has-text('Apply')"
        ]
        for sel in apply_selectors:
            btn = page.locator(sel).first
            if await btn.is_visible():
                await self.stealth.human_click(page, btn)
                await asyncio.sleep(2.0)
                # If "Apply Manually" option appears, click it
                manual_btn = page.locator("a[data-automation-id='applyManually'], button:has-text('Apply Manually')").first
                if await manual_btn.is_visible():
                    await self.stealth.human_click(page, manual_btn)
                    await asyncio.sleep(2.0)
                return True
        return False

    async def process_application(self, page: Page, mode: str = "copilot") -> Dict[str, Any]:
        """
        Processes Workday multi-step application form.
        """
        job_title = await self._extract_job_title(page)
        company_name = await self._extract_company_name(page)
        job_url = page.url

        # Check if apply button needs to be clicked
        form_active = page.locator("div[data-automation-id='formField'], input[data-automation-id*='legalName']").first
        if not await form_active.is_visible():
            opened = await self.find_and_click_apply(page)
            if not opened:
                return {
                    "status": "NO_APPLY_BUTTON",
                    "job_title": job_title,
                    "company_name": company_name,
                    "job_url": job_url,
                    "platform": "workday",
                    "message": "No Workday Apply button available."
                }
            await asyncio.sleep(2.5)

        max_steps = 10
        step = 0

        while step < max_steps:
            step += 1
            await asyncio.sleep(1.0)

            # 1. Fill fields on current Workday step
            await self._fill_workday_fields(page, job_title, company_name)

            # 2. Upload resume if file input is visible
            await self._handle_file_uploads(page)

            # 3. Locate action buttons
            submit_btn = page.locator(
                "button[data-automation-id='bottom-navigation-submit-button'], button:has-text('Submit')"
            ).first

            next_btn = page.locator(
                "button[data-automation-id='bottom-navigation-next-button'], button:has-text('Save and Continue'), button:has-text('Next')"
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
                        "platform": "workday",
                        "step": step,
                        "message": "Wrangler: Workday MNC application autofilled! Ready for 1-click review & submit."
                    }
                else:
                    await self.stealth.human_click(page, submit_btn)
                    await asyncio.sleep(3.0)
                    return {
                        "status": "SUBMITTED",
                        "job_title": job_title,
                        "company_name": company_name,
                        "job_url": job_url,
                        "platform": "workday",
                        "step": step,
                        "message": "Workday application automatically submitted."
                    }

            if await next_btn.is_visible():
                await self.stealth.human_click(page, next_btn)
                await asyncio.sleep(2.0)
                continue

            break

        return {
            "status": "COMPLETED_OR_UNKNOWN",
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
            "platform": "workday",
            "step": step
        }

    async def _fill_workday_fields(self, page: Page, job_title: str, company: str):
        """Fills Workday inputs using data-automation-id and standard selectors."""
        # 1. Specific standard Workday fields
        field_map = {
            "legalNameSection_firstName": self.resolver.personal.get("first_name", ""),
            "legalNameSection_middleName": self.resolver.personal.get("middle_name", ""),
            "legalNameSection_lastName": self.resolver.personal.get("last_name", ""),
            "phone-number": self.resolver.personal.get("phone", ""),
            "addressSection_city": self.resolver.personal.get("city", "Hyderabad"),
            "addressSection_postalCode": self.resolver.personal.get("postal_code", "500081"),
            "addressSection_addressLine1": self.resolver.personal.get("address_line1", "Madhapur"),
        }

        for auto_id, val in field_map.items():
            if not val:
                continue
            inp = page.locator(f"input[data-automation-id='{auto_id}']").first
            if await inp.is_visible():
                curr = await inp.input_value()
                if not curr.strip():
                    await self.stealth.human_type(inp, str(val))

        # 2. General inputs in formField containers
        inputs = await page.locator("input:not([type='hidden']):not([type='file']):not([type='checkbox']):not([type='radio'])").all()
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
                await self.stealth.human_type(inp, str(val))

        # 3. Radio buttons in Workday questionnaires
        radios = await page.locator("div[data-automation-id='formField'] label, fieldset").all()
        for r_container in radios:
            if not await r_container.is_visible():
                continue
            txt = await r_container.inner_text()
            val, _ = self.resolver.resolve(txt, input_type="radio")
            if val:
                choice = "Yes" if "yes" in val.lower() else "No"
                target_radio = r_container.locator(f"label:has-text('{choice}'), input[value='{choice}']").first
                if await target_radio.is_visible():
                    await self.stealth.human_click(page, target_radio)

    async def _handle_file_uploads(self, page: Page):
        if not os.path.exists(self.resume_path):
            return
        file_inputs = await page.locator("input[type='file']").all()
        for f_inp in file_inputs:
            try:
                await f_inp.set_input_files(os.path.abspath(self.resume_path))
                await asyncio.sleep(1.0)
            except Exception:
                pass

    async def _get_label_text(self, page: Page, locator: Locator) -> str:
        auto_id = await locator.get_attribute("data-automation-id")
        if auto_id:
            return auto_id
        aria = await locator.get_attribute("aria-label")
        if aria:
            return aria
        parent = locator.locator("xpath=ancestor::div[contains(@data-automation-id, 'formField')]").first
        if await parent.is_visible():
            txt = await parent.inner_text()
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            if lines:
                return lines[0]
        return "Workday question"

    async def _extract_job_title(self, page: Page) -> str:
        selectors = [
            "h2[data-automation-id='jobPostingHeader']",
            "h1[data-automation-id='jobPostingHeader']",
            "h1",
            "h2"
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return (await loc.inner_text()).strip()
        return "Software Engineer"

    async def _extract_company_name(self, page: Page) -> str:
        url = page.url.lower()
        # Parse company name from subdomain, e.g., amazon.wd5.myworkdayjobs.com -> Amazon
        m = re.search(r'https?://([^.]+)\.(?:wd\d+\.)?myworkdayjobs\.com', url)
        if m:
            return m.group(1).capitalize()
        return "Enterprise MNC"
