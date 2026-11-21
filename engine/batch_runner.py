"""
Autonomous Batch & Overnight Job Runner.
Iterates through search results, filters out blacklisted companies, and applies automatically.
"""

import asyncio
import random
import urllib.parse
from typing import Dict, Any, List
from playwright.async_api import Page
from adapters.linkedin_adapter import LinkedInAdapter
from core.storage import ApplicationStore
from core.stealth import StealthDriver


class BatchRunner:
    def __init__(
        self,
        linkedin_adapter: LinkedInAdapter,
        storage: ApplicationStore,
        stealth: StealthDriver,
        settings: Dict[str, Any]
    ):
        self.adapter = linkedin_adapter
        self.storage = storage
        self.stealth = stealth
        self.settings = settings

        self.limits = settings.get("limits", {})
        self.max_daily = self.limits.get("max_daily_applications", 35)
        self.min_pause = self.limits.get("pause_between_applications_min_sec", 15)
        self.max_pause = self.limits.get("pause_between_applications_max_sec", 30)

        self.filters = settings.get("filters", {})
        self.blacklist_companies = [c.lower() for c in self.filters.get("blacklist_companies", [])]
        self.blacklist_titles = [t.lower() for t in self.filters.get("blacklist_title_keywords", [])]

    async def run_linkedin_search(
        self,
        page: Page,
        keywords: str = "Flutter Developer",
        location: str = "Remote",
        mode: str = "autonomous",
        max_jobs: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Executes a LinkedIn Easy Apply batch search and steps through applications.
        """
        encoded_kw = urllib.parse.quote_plus(keywords)
        encoded_loc = urllib.parse.quote_plus(location)
        search_url = (
            f"https://www.linkedin.com/jobs/search/?"
            f"keywords={encoded_kw}&location={encoded_loc}&f_AL=true&f_TPR=r86400"
        )

        print(f"\n🌐 Navigating to LinkedIn Search: {keywords} ({location}) [Easy Apply, Past 24h]")
        await page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(3.0)

        results = []
        applied_today = self.storage.get_today_application_count()

        if applied_today >= self.max_daily:
            print(f"🛑 Daily limit reached ({applied_today}/{self.max_daily}). Stopping to keep account safe.")
            return results

        # Find job listing cards
        card_selectors = [
            "li.jobs-search-results__list-item",
            "div.job-card-container",
            "div.scaffold-layout__list-item"
        ]

        page_num = 1
        max_pages = 5

        while page_num <= max_pages and applied_today < self.max_daily and len(results) < max_jobs:
            # Scroll down the list view to trigger lazy loading of cards
            await self.stealth.smooth_scroll(page, 600)
            await asyncio.sleep(1.5)

            cards = await page.locator("div.job-card-container, li.jobs-search-results__list-item").all()
            print(f"📄 Page {page_num}: Found {len(cards)} job cards.")

            if not cards:
                print("ℹ️ No more job cards found.")
                break

            for i, card in enumerate(cards):
                if applied_today >= self.max_daily or len(results) >= max_jobs:
                    break

                try:
                    # Extract title and company from the card
                    title_elem = card.locator("a.job-card-list__title, strong, .artdeco-entity-lockup__title").first
                    comp_elem = card.locator("span.job-card-container__primary-description, .artdeco-entity-lockup__subtitle").first

                    title = (await title_elem.inner_text()).strip() if await title_elem.is_visible() else "Job"
                    company = (await comp_elem.inner_text()).strip() if await comp_elem.is_visible() else "Company"

                    # 1. Check Blacklists
                    if any(b in company.lower() for b in self.blacklist_companies):
                        print(f"⏭️ Skipping blacklisted company: {company} ({title})")
                        continue

                    if any(t in title.lower() for t in self.blacklist_titles):
                        print(f"⏭️ Skipping blacklisted title keyword: {title} at {company}")
                        continue

                    # 2. Click job card to view details
                    print(f"\n👉 [{len(results) + 1}/{max_jobs}] Inspecting: {title} at {company}")
                    await self.stealth.human_click(page, card)
                    await asyncio.sleep(random.uniform(2.0, 3.5))

                    job_url = page.url
                    if self.storage.has_applied(job_url):
                        print(f"ℹ️ Already applied to this job previously. Skipping.")
                        continue

                    # 3. Process Easy Apply via Adapter
                    res = await self.adapter.process_application(page, mode=mode)
                    status = res.get("status", "FAILED")
                    print(f"   Outcome: {status} - {res.get('message', '')}")

                    # 4. Log in Database
                    self.storage.log_application(
                        platform="linkedin",
                        job_title=title,
                        company_name=company,
                        job_url=job_url,
                        status=status,
                        mode=mode,
                        notes=res.get("message", "")
                    )

                    results.append(res)
                    if status in ["SUBMITTED", "AUTOFILLED_PENDING_REVIEW"]:
                        applied_today += 1

                    # 5. Natural human pacing delay
                    delay = random.uniform(self.min_pause, self.max_pause)
                    print(f"⏳ Human pacing wait: {delay:.1f}s before next application...")
                    await asyncio.sleep(delay)

                except Exception as e:
                    print(f"⚠️ Error handling job card: {e}")
                    continue

            # Check for next page
            next_page_btn = page.locator(f"button[aria-label='Page {page_num + 1}']").first
            if await next_page_btn.is_visible():
                page_num += 1
                await self.stealth.human_click(page, next_page_btn)
                await asyncio.sleep(3.0)
            else:
                break

        print(f"\n✨ Batch run completed. Total processed: {len(results)}. Today's total: {applied_today}/{self.max_daily}")
        return results
