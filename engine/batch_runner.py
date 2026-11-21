"""
Autonomous Multi-Platform Batch & Overnight Job Runner.
Iterates through search results across LinkedIn, Naukri, Indeed, and Wellfound,
filters out blacklisted companies, and applies automatically with human pacing.
"""

import asyncio
import random
import urllib.parse
from typing import Dict, Any, List, Optional, Union
from playwright.async_api import Page
from adapters.base_adapter import BaseAdapter
from adapters.linkedin_adapter import LinkedInAdapter
from core.storage import ApplicationStore
from core.stealth import StealthDriver


class BatchRunner:
    def __init__(
        self,
        adapters: Union[Dict[str, BaseAdapter], LinkedInAdapter],
        storage: ApplicationStore,
        stealth: StealthDriver,
        settings: Dict[str, Any]
    ):
        # Support both single linkedin_adapter (for backward compatibility) and dict of adapters
        if isinstance(adapters, dict):
            self.adapters = adapters
        else:
            self.adapters = {"linkedin": adapters}

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

    async def run_batch_search(
        self,
        page: Page,
        platform: str = "all",
        keywords: str = "Flutter Developer",
        location: str = "Remote",
        mode: str = "autonomous",
        max_jobs: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Runs batch search for a specific platform or distributes across all supported platforms.
        """
        platform = platform.lower().strip()
        all_results = []

        if platform == "all":
            # Smart rotation across supported platforms
            enabled_platforms = ["linkedin", "naukri", "indeed", "wellfound"]
            per_platform = max(1, max_jobs // len(enabled_platforms))

            for plat in enabled_platforms:
                if len(all_results) >= max_jobs:
                    break
                remaining = max_jobs - len(all_results)
                limit = min(per_platform, remaining)
                print(f"\n🔄 [Multi-Platform] Switching to {plat.upper()} batch (Limit: {limit})...")

                if plat == "linkedin":
                    res = await self.run_linkedin_search(page, keywords, location, mode, limit)
                elif plat == "naukri":
                    res = await self.run_naukri_search(page, keywords, location, mode, limit)
                elif plat == "indeed":
                    res = await self.run_indeed_search(page, keywords, location, mode, limit)
                elif plat == "wellfound":
                    res = await self.run_wellfound_search(page, keywords, location, mode, limit)
                else:
                    res = []

                all_results.extend(res)
                await asyncio.sleep(random.uniform(5.0, 10.0))

            return all_results

        elif platform == "naukri":
            return await self.run_naukri_search(page, keywords, location, mode, max_jobs)
        elif platform == "indeed":
            return await self.run_indeed_search(page, keywords, location, mode, max_jobs)
        elif platform == "wellfound":
            return await self.run_wellfound_search(page, keywords, location, mode, max_jobs)
        else:
            return await self.run_linkedin_search(page, keywords, location, mode, max_jobs)

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
        adapter = self.adapters.get("linkedin")
        if not adapter:
            print("⚠️ LinkedIn adapter not registered.")
            return []

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

        page_num = 1
        max_pages = 5

        while page_num <= max_pages and applied_today < self.max_daily and len(results) < max_jobs:
            await self.stealth.smooth_scroll(page, 600)
            await asyncio.sleep(1.5)

            cards = await page.locator("div.job-card-container, li.jobs-search-results__list-item").all()
            print(f"📄 LinkedIn Page {page_num}: Found {len(cards)} job cards.")

            if not cards:
                break

            for card in cards:
                if applied_today >= self.max_daily or len(results) >= max_jobs:
                    break

                try:
                    title_elem = card.locator("a.job-card-list__title, strong, .artdeco-entity-lockup__title").first
                    comp_elem = card.locator("span.job-card-container__primary-description, .artdeco-entity-lockup__subtitle").first

                    title = (await title_elem.inner_text()).strip() if await title_elem.is_visible() else "Job"
                    company = (await comp_elem.inner_text()).strip() if await comp_elem.is_visible() else "Company"

                    if any(b in company.lower() for b in self.blacklist_companies) or any(t in title.lower() for t in self.blacklist_titles):
                        continue

                    print(f"\n👉 [{len(results) + 1}/{max_jobs}] Inspecting LinkedIn: {title} at {company}")
                    await self.stealth.human_click(page, card)
                    await asyncio.sleep(random.uniform(2.0, 3.5))

                    job_url = page.url
                    if self.storage.has_applied(job_url):
                        print("ℹ️ Already applied previously. Skipping.")
                        continue

                    res = await adapter.process_application(page, mode=mode)
                    status = res.get("status", "FAILED")
                    print(f"   Outcome: {status} - {res.get('message', '')}")

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

                    delay = random.uniform(self.min_pause, self.max_pause)
                    print(f"⏳ Human pacing wait: {delay:.1f}s before next application...")
                    await asyncio.sleep(delay)

                except Exception as e:
                    print(f"⚠️ Error handling LinkedIn card: {e}")
                    continue

            next_page_btn = page.locator(f"button[aria-label='Page {page_num + 1}']").first
            if await next_page_btn.is_visible():
                page_num += 1
                await self.stealth.human_click(page, next_page_btn)
                await asyncio.sleep(3.0)
            else:
                break

        return results

    async def run_naukri_search(
        self,
        page: Page,
        keywords: str = "Flutter Developer",
        location: str = "Remote",
        mode: str = "autonomous",
        max_jobs: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Executes a Naukri.com batch search for India tech roles and steps through applications.
        """
        adapter = self.adapters.get("naukri")
        if not adapter:
            print("⚠️ Naukri adapter not registered.")
            return []

        kw_slug = keywords.lower().replace(" ", "-")
        loc_slug = location.lower().replace(" ", "-")
        search_url = f"https://www.naukri.com/{kw_slug}-jobs-in-{loc_slug}?k={urllib.parse.quote_plus(keywords)}"

        print(f"\n🌐 Navigating to Naukri Search: {keywords} ({location})")
        await page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(3.5)

        results = []
        applied_today = self.storage.get_today_application_count()

        if applied_today >= self.max_daily:
            print(f"🛑 Daily limit reached ({applied_today}/{self.max_daily}). Stopping.")
            return results

        # Find Naukri job cards
        card_selectors = "div.srp-jobtuple-wrapper, article.jobTuple, div.cust-job-tuple"
        cards = await page.locator(card_selectors).all()
        print(f"📄 Found {len(cards)} Naukri job listings.")

        for card in cards:
            if applied_today >= self.max_daily or len(results) >= max_jobs:
                break

            try:
                title_elem = card.locator("a.title, [class*='title']").first
                comp_elem = card.locator("a.comp-name, span.comp-name").first

                title = (await title_elem.inner_text()).strip() if await title_elem.is_visible() else "Flutter Developer"
                company = (await comp_elem.inner_text()).strip() if await comp_elem.is_visible() else "Company"

                if any(b in company.lower() for b in self.blacklist_companies) or any(t in title.lower() for t in self.blacklist_titles):
                    continue

                print(f"\n👉 [{len(results) + 1}/{max_jobs}] Inspecting Naukri: {title} at {company}")
                
                # In Naukri, clicking title opens job in new tab or navigates
                async with page.expect_popup() if True else None:
                    pass

                # Click title or open link
                link_href = await title_elem.get_attribute("href")
                if link_href:
                    if self.storage.has_applied(link_href):
                        print("ℹ️ Already applied previously. Skipping.")
                        continue
                    
                    job_page = await page.context.new_page()
                    await job_page.goto(link_href, wait_until="domcontentloaded")
                    await asyncio.sleep(2.0)

                    res = await adapter.process_application(job_page, mode=mode)
                    status = res.get("status", "FAILED")
                    print(f"   Outcome: {status} - {res.get('message', '')}")

                    self.storage.log_application(
                        platform="naukri",
                        job_title=title,
                        company_name=company,
                        job_url=link_href,
                        status=status,
                        mode=mode,
                        notes=res.get("message", "")
                    )

                    results.append(res)
                    if status in ["SUBMITTED", "AUTOFILLED_PENDING_REVIEW"]:
                        applied_today += 1

                    await job_page.close()

                    delay = random.uniform(self.min_pause, self.max_pause)
                    print(f"⏳ Human pacing wait: {delay:.1f}s before next application...")
                    await asyncio.sleep(delay)

            except Exception as e:
                print(f"⚠️ Error handling Naukri card: {e}")
                continue

        return results

    async def run_indeed_search(
        self,
        page: Page,
        keywords: str = "Flutter Developer",
        location: str = "Remote",
        mode: str = "autonomous",
        max_jobs: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Executes an Indeed search (India/Global) and applies to Easily Apply jobs.
        """
        adapter = self.adapters.get("indeed")
        if not adapter:
            print("⚠️ Indeed adapter not registered.")
            return []

        encoded_kw = urllib.parse.quote_plus(keywords)
        encoded_loc = urllib.parse.quote_plus(location)
        search_url = f"https://in.indeed.com/jobs?q={encoded_kw}&l={encoded_loc}&fromage=1"

        print(f"\n🌐 Navigating to Indeed Search: {keywords} ({location})")
        await page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(3.0)

        results = []
        applied_today = self.storage.get_today_application_count()

        if applied_today >= self.max_daily:
            print(f"🛑 Daily limit reached ({applied_today}/{self.max_daily}). Stopping.")
            return results

        cards = await page.locator("div.job_seen_beacon, div.cardOutline").all()
        print(f"📄 Found {len(cards)} Indeed job listings.")

        for card in cards:
            if applied_today >= self.max_daily or len(results) >= max_jobs:
                break

            try:
                title_elem = card.locator("h2.jobTitle span, a.jcs-JobTitle").first
                comp_elem = card.locator("span.companyName, span[data-testid='company-name']").first

                title = (await title_elem.inner_text()).strip() if await title_elem.is_visible() else "Job"
                company = (await comp_elem.inner_text()).strip() if await comp_elem.is_visible() else "Company"

                if any(b in company.lower() for b in self.blacklist_companies) or any(t in title.lower() for t in self.blacklist_titles):
                    continue

                print(f"\n👉 [{len(results) + 1}/{max_jobs}] Inspecting Indeed: {title} at {company}")
                await self.stealth.human_click(page, card)
                await asyncio.sleep(random.uniform(2.0, 3.0))

                job_url = page.url
                if self.storage.has_applied(job_url):
                    print("ℹ️ Already applied previously. Skipping.")
                    continue

                res = await adapter.process_application(page, mode=mode)
                status = res.get("status", "FAILED")
                print(f"   Outcome: {status} - {res.get('message', '')}")

                self.storage.log_application(
                    platform="indeed",
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

                delay = random.uniform(self.min_pause, self.max_pause)
                print(f"⏳ Human pacing wait: {delay:.1f}s before next application...")
                await asyncio.sleep(delay)

            except Exception as e:
                print(f"⚠️ Error handling Indeed card: {e}")
                continue

        return results

    async def run_wellfound_search(
        self,
        page: Page,
        keywords: str = "Flutter Developer",
        location: str = "Remote",
        mode: str = "autonomous",
        max_jobs: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Executes a Wellfound startup job search and applies with tailored pitch notes.
        """
        adapter = self.adapters.get("wellfound")
        if not adapter:
            print("⚠️ Wellfound adapter not registered.")
            return []

        search_url = "https://wellfound.com/jobs"
        print(f"\n🌐 Navigating to Wellfound Startup Search: {keywords}")
        await page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(3.0)

        results = []
        applied_today = self.storage.get_today_application_count()

        if applied_today >= self.max_daily:
            print(f"🛑 Daily limit reached ({applied_today}/{self.max_daily}). Stopping.")
            return results

        cards = await page.locator("div[data-test='JobListingCard'], div[class*='styles_jobListing']").all()
        print(f"📄 Found {len(cards)} Wellfound startup roles.")

        for card in cards:
            if applied_today >= self.max_daily or len(results) >= max_jobs:
                break

            try:
                title_elem = card.locator("a[data-test='JobListingTitle'], h2").first
                comp_elem = card.locator("a[data-test='StartupName']").first

                title = (await title_elem.inner_text()).strip() if await title_elem.is_visible() else "Flutter Developer"
                company = (await comp_elem.inner_text()).strip() if await comp_elem.is_visible() else "Startup"

                if any(b in company.lower() for b in self.blacklist_companies) or any(t in title.lower() for t in self.blacklist_titles):
                    continue

                print(f"\n👉 [{len(results) + 1}/{max_jobs}] Inspecting Wellfound: {title} at {company}")
                await self.stealth.human_click(page, card)
                await asyncio.sleep(random.uniform(2.0, 3.5))

                job_url = page.url
                if self.storage.has_applied(job_url):
                    print("ℹ️ Already applied previously. Skipping.")
                    continue

                res = await adapter.process_application(page, mode=mode)
                status = res.get("status", "FAILED")
                print(f"   Outcome: {status} - {res.get('message', '')}")

                self.storage.log_application(
                    platform="wellfound",
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

                delay = random.uniform(self.min_pause, self.max_pause)
                print(f"⏳ Human pacing wait: {delay:.1f}s before next application...")
                await asyncio.sleep(delay)

            except Exception as e:
                print(f"⚠️ Error handling Wellfound card: {e}")
                continue

        return results
