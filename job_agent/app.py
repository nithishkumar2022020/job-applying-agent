from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = ROOT / "profile.json"
DEFAULT_SOURCES = ROOT / "sources.json"
DEFAULT_DATABASE = ROOT / "job_agent.sqlite3"
DEFAULT_DASHBOARD = ROOT / "review_queue.html"
USER_AGENT = "PersonalJobAgent/0.1 (+private candidate tool)"


@dataclass(slots=True)
class Job:
    source: str
    source_kind: str
    external_id: str
    title: str
    company: str
    location: str
    description: str
    apply_url: str
    posted_at: str | None = None
    salary_text: str | None = None
    company_type: str = "unknown"
    company_size: str = "unknown"
    work_mode: str = ""


@dataclass(slots=True)
class Decision:
    eligible: bool
    score: int
    reasons: list[str]
    warnings: list[str]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def clean_text(value: Any) -> str:
    if not value:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    value = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", value).strip()


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, application/xml, text/xml"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def fetch_json(url: str) -> Any:
    return json.loads(request_bytes(url).decode("utf-8"))


def salary_inr_annual(text: str) -> int | None:
    normalized = clean_text(text).lower().replace(",", "")
    if not normalized:
        return None
    lpa = re.search(r"(?:₹|inr|rs\.?\s*)?\s*(\d+(?:\.\d+)?)\s*(?:-|to|–)?\s*(\d+(?:\.\d+)?)?\s*(?:lpa|lakhs?|lacs?)", normalized)
    if lpa:
        low = float(lpa.group(1))
        return int(low * 100000)
    rupees = re.search(r"(?:₹|inr|rs\.?\s*)\s*(\d{5,8})(?:\s*(?:per year|annual|annum|pa))?", normalized)
    if rupees:
        return int(rupees.group(1))
    return None


def explicit_years_required(text: str) -> int | None:
    matches = re.findall(r"(\d+)\s*(?:(?:-|–|—|to)\s*\d+\s*)?(?:\+\s*|or more\s*)?(?:years?|yrs?)", text.lower())
    return max((int(value) for value in matches), default=None)


def canonical_host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def contains_term(text: str, term: str) -> bool:
    normalized_term = term.lower().strip()
    if len(normalized_term) <= 3 and normalized_term.isalnum():
        return re.search(rf"\b{re.escape(normalized_term)}\b", text.lower()) is not None
    return normalized_term in text.lower()


def stable_key(job: Job) -> str:
    basis = "|".join(
        [job.company.lower().strip(), job.title.lower().strip(), job.location.lower().strip(), canonical_host(job.apply_url)]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def fetch_greenhouse(source: dict[str, Any]) -> list[Job]:
    slug = source["slug"]
    data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    jobs = []
    for item in data.get("jobs", []):
        jobs.append(
            Job(
                source=source["name"],
                source_kind="greenhouse",
                external_id=str(item.get("id", "")),
                title=clean_text(item.get("title")),
                company=clean_text(source.get("company", source["name"])),
                location=clean_text((item.get("location") or {}).get("name")),
                description=clean_text(item.get("content")),
                apply_url=item.get("absolute_url", ""),
                posted_at=item.get("updated_at"),
                company_type=source.get("company_type", "unknown"),
                company_size=source.get("company_size", "unknown"),
            )
        )
    return jobs


def fetch_lever(source: dict[str, Any]) -> list[Job]:
    slug = source["slug"]
    data = fetch_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    jobs = []
    for item in data:
        categories = item.get("categories") or {}
        description = " ".join(
            clean_text(part)
            for part in [item.get("descriptionPlain"), item.get("additionalPlain"), item.get("lists")]
        )
        jobs.append(
            Job(
                source=source["name"],
                source_kind="lever",
                external_id=str(item.get("id", "")),
                title=clean_text(item.get("text")),
                company=clean_text(source.get("company", source["name"])),
                location=clean_text(categories.get("location")),
                work_mode=clean_text(item.get("workplaceType")),
                description=description,
                apply_url=item.get("applyUrl") or item.get("hostedUrl") or "",
                posted_at=str(item.get("createdAt") or ""),
                company_type=source.get("company_type", "unknown"),
                company_size=source.get("company_size", "unknown"),
            )
        )
    return jobs


def fetch_ashby(source: dict[str, Any]) -> list[Job]:
    slug = source["slug"]
    data = fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    jobs = []
    for item in data.get("jobs", []):
        compensation = item.get("compensation") or {}
        salary_text = clean_text(json.dumps(compensation)) if compensation else None
        jobs.append(
            Job(
                source=source["name"],
                source_kind="ashby",
                external_id=str(item.get("id") or item.get("jobUrl") or ""),
                title=clean_text(item.get("title")),
                company=clean_text(source.get("company", source["name"])),
                location=clean_text(item.get("location")),
                work_mode=clean_text(item.get("workplaceType")) or ("remote" if item.get("isRemote") else ""),
                description=clean_text(item.get("descriptionPlain") or item.get("descriptionHtml")),
                apply_url=item.get("applyUrl") or item.get("jobUrl") or "",
                posted_at=item.get("publishedAt"),
                salary_text=salary_text,
                company_type=source.get("company_type", "unknown"),
                company_size=source.get("company_size", "unknown"),
            )
        )
    return jobs


def fetch_remotive(source: dict[str, Any]) -> list[Job]:
    data = fetch_json(source.get("url", "https://remotive.com/api/remote-jobs"))
    return [
        Job(
            source=source["name"], source_kind="remotive", external_id=str(item.get("id", "")),
            title=clean_text(item.get("title")), company=clean_text(item.get("company_name")),
            location=clean_text(item.get("candidate_required_location")) or "Remote",
            description=clean_text(item.get("description")), apply_url=item.get("url", ""),
            posted_at=item.get("publication_date"), salary_text=clean_text(item.get("salary")) or None,
            company_type=source.get("company_type", "unknown"), company_size=source.get("company_size", "unknown"),
        )
        for item in data.get("jobs", [])
    ]


def fetch_arbeitnow(source: dict[str, Any]) -> list[Job]:
    data = fetch_json(source.get("url", "https://www.arbeitnow.com/api/job-board-api"))
    return [
        Job(
            source=source["name"], source_kind="arbeitnow", external_id=str(item.get("slug", "")),
            title=clean_text(item.get("title")), company=clean_text(item.get("company_name")),
            location=clean_text(item.get("location")) or ("Remote" if item.get("remote") else "Unknown"),
            description=clean_text(item.get("description")), apply_url=item.get("url", ""),
            posted_at=str(item.get("created_at") or ""), company_type=source.get("company_type", "unknown"),
            company_size=source.get("company_size", "unknown"),
        )
        for item in data.get("data", [])
    ]


def fetch_jobicy(source: dict[str, Any]) -> list[Job]:
    data = fetch_json(source.get("url", "https://jobicy.com/api/v2/remote-jobs?count=50&tag=ai"))
    return [
        Job(
            source=source["name"], source_kind="jobicy", external_id=str(item.get("id", "")),
            title=clean_text(item.get("jobTitle")), company=clean_text(item.get("companyName")),
            location=clean_text(item.get("jobGeo")) or "Remote",
            description=" ".join([clean_text(item.get("jobExcerpt")), clean_text(item.get("jobDescription"))]).strip(),
            apply_url=item.get("url", ""), posted_at=item.get("pubDate"),
            salary_text=" ".join(clean_text(item.get(key)) for key in ("annualSalaryMin", "annualSalaryMax", "salaryCurrency")).strip() or None,
            company_type=source.get("company_type", "unknown"), company_size=source.get("company_size", "unknown"),
        )
        for item in data.get("jobs", [])
    ]


def fetch_rss(source: dict[str, Any]) -> list[Job]:
    root = ET.fromstring(request_bytes(source["url"]))
    jobs = []
    for item in root.findall("./channel/item"):
        fields = {child.tag.split("}")[-1]: clean_text(child.text) for child in item}
        title = fields.get("title", "")
        company = fields.get("companyName", "")
        if not company and " at " in title:
            title, company = title.rsplit(" at ", 1)
        link = fields.get("link", "")
        jobs.append(
            Job(
                source=source["name"],
                source_kind="rss",
                external_id=fields.get("guid") or link,
                title=title,
                company=company or source["name"],
                location=fields.get("locationRestriction") or fields.get("location") or "Remote",
                description=fields.get("content") or fields.get("description", ""),
                apply_url=link,
                posted_at=fields.get("pubDate"),
                salary_text=fields.get("salary"),
                company_type=source.get("company_type", "unknown"),
                company_size=source.get("company_size", "unknown"),
            )
        )
    return jobs


def fetch_smartrecruiters(source: dict[str, Any]) -> list[Job]:
    slug = source["slug"]
    listings = []
    for page in range(int(source.get("max_pages", 10))):
        data = fetch_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?country=in&limit=100&offset={page * 100}")
        listings.extend(data.get("content", []))
        if (page + 1) * 100 >= data.get("totalFound", 0):
            break
    targets = [
        item for item in listings
        if (item.get("location") or {}).get("country", "").lower() == "in"
        and re.search(r"engineer|developer|analyst|trainee|graduate|scientist|python|devops|machine learning|artificial intelligence", item.get("name", ""), re.I)
        and not re.search(r"\b(senior|sr|staff|principal|lead|manager|director|architect)\b", item.get("name", ""), re.I)
    ]

    def detail_job(item: dict[str, Any]) -> Job:
        detail = fetch_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{item['id']}")
        location = detail.get("location") or {}
        sections = (detail.get("jobAd") or {}).get("sections") or {}
        description = " ".join(clean_text(sections.get(key, {}).get("text")) for key in ("jobDescription", "qualifications", "additionalInformation"))
        level = clean_text((detail.get("experienceLevel") or {}).get("label"))
        bare_years = re.search(r"\b(\d{1,2}\s*(?:(?:-|–|to)\s*\d{1,2})?\+?)\s*$", description)
        if bare_years:
            description += " Required experience: " + bare_years.group(1) + " years."
        return Job(
            source=source["name"], source_kind="smartrecruiters", external_id=str(item["id"]),
            title=clean_text(detail.get("name")), company=source.get("company", source["name"]),
            location=clean_text(location.get("fullLocation")) or clean_text(location.get("city")) + ", India",
            work_mode="hybrid" if location.get("hybrid") else "remote" if location.get("remote") else "",
            description=description + " Experience level: " + level,
            apply_url=detail.get("applyUrl") or detail.get("postingUrl") or "",
            posted_at=detail.get("releasedDate"), company_type=source.get("company_type", "unknown"),
            company_size=source.get("company_size", "unknown"),
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        return list(executor.map(detail_job, targets))


class CareerDescriptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self.depth or "jobdescription" in (attributes.get("class") or "").split():
            if tag not in {"br", "hr", "img", "input", "meta", "link", "wbr"}:
                self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth and tag not in {"br", "hr", "img", "input", "meta", "link", "wbr"}:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)


def fetch_career_pages(source: dict[str, Any]) -> list[Job]:
    jobs = []
    for lead in source.get("listings", []):
        parser = CareerDescriptionParser()
        parser.feed(request_bytes(lead["url"]).decode("utf-8"))
        description = clean_text(" ".join(parser.parts))
        if not description:
            raise ValueError("Job description missing; listing may be closed or page structure changed")
        jobs.append(Job(
            source=source["name"], source_kind="career_pages", external_id=lead["url"],
            title=lead["title"], company=source["company"], location=lead["location"],
            description=description, apply_url=lead["url"], posted_at=lead.get("posted_at"),
            company_type=source.get("company_type", "unknown"), company_size=source.get("company_size", "unknown"),
        ))
    return jobs


def fetch_openroles(source: dict[str, Any]) -> list[Job]:
    try:
        import openroles
    except ImportError as error:
        raise ValueError("Install discovery extras: pip install '.[discovery]'") from error
    openroles.configure(user_agent=USER_AGENT)
    detail_count = 0

    def needs_details(item: Any) -> bool:
        nonlocal detail_count
        title = item.title.lower()
        location = item.location.lower()
        if detail_count >= int(source.get("detail_limit", 40)):
            return False
        if not any(term in location for term in ("india", "bengaluru", "bangalore", "delhi", "gurugram", "noida", "mumbai", "pune", "hyderabad", "chennai")):
            return False
        if not re.search(r"engineer|developer|scientist|analyst|trainee|graduate|python", title):
            return False
        if re.search(r"\b(senior|sr|staff|principal|manager|director|lead|architect)\b", title.replace("_", " ")):
            return False
        detail_count += 1
        return True

    report: dict[str, Any] = {}
    try:
        listings = openroles.fetch(source["target"], country="India", details=needs_details,
                                   workday_queries=source.get("queries"), report=report)
    except openroles.BoardError as error:
        raise ValueError(str(error)) from error
    errors = [str(value) for value in report.values() if value.get("error") or value.get("listing_errors") or value.get("detail_errors")]
    if errors:
        raise ValueError("Incomplete employer feed: " + "; ".join(errors)[:1000])
    return [Job(
        source=source["name"], source_kind="openroles", external_id=item.id, title=clean_text(item.title),
        company=source["company"], location=clean_text(item.location), description=clean_text(item.description),
        apply_url=item.url, work_mode=item.workplace or ("remote" if item.remote is True else ""),
        posted_at=item.posted or None, salary_text=item.compensation or None,
        company_type=source.get("company_type", "unknown"), company_size=source.get("company_size", "unknown"),
    ) for item in listings if item.description][:int(source.get("max_jobs", 150))]


def normalize_india_location(location: str) -> str:
    if not contains_term(location, "india"):
        return location
    states = {"DL": "Delhi", "HR": "Haryana", "UP": "Uttar Pradesh", "KA": "Karnataka", "KL": "Kerala",
              "MH": "Maharashtra", "MP": "Madhya Pradesh", "TN": "Tamil Nadu", "GJ": "Gujarat", "RJ": "Rajasthan",
              "WB": "West Bengal", "PB": "Punjab", "CH": "Chandigarh", "UK": "Uttarakhand", "OD": "Odisha",
              "BR": "Bihar", "JH": "Jharkhand", "AS": "Assam", "GA": "Goa", "CG": "Chhattisgarh",
              "AP": "Andhra Pradesh", "TS": "Telangana", "TG": "Telangana"}
    return re.sub(r"\b[A-Z]{2}\b", lambda match: states.get(match.group(), match.group()), location)


def fetch_jobspy(source: dict[str, Any]) -> list[Job]:
    try:
        import pandas as pd
        from jobspy import scrape_jobs
    except ImportError as error:
        raise ValueError("Install discovery extras: pip install '.[discovery]'") from error
    site = source.get("site")
    if site not in {"naukri", "indeed"}:
        raise ValueError("This connector is configured for Naukri and Indeed India discovery only")
    data = scrape_jobs(site_name=[site], search_term=source["query"], location=source.get("location", "India"),
                       country_indeed="India", results_wanted=min(int(source.get("results_wanted", 30)), 100),
                       hours_old=int(source.get("hours_old", 168)), fetch_description=True,
                       is_remote=None, verbose=0)
    if getattr(data, "empty", False):
        raise ValueError("JobSpy returned no results: query may be empty or blocked; coverage is unconfirmed")
    jobs = []
    for row in data.to_dict(orient="records"):
        def value(key: str) -> Any:
            item = row.get(key)
            if item is None or isinstance(item, (list, dict, tuple)):
                return item
            return None if pd.isna(item) else item

        salary = None
        amount = value("min_amount")
        currency = clean_text(value("currency"))
        interval = clean_text(value("interval")).lower()
        if amount is not None and currency.upper() == "INR":
            multiplier = {"yearly": 1, "annual": 1, "monthly": 12}.get(interval)
            if multiplier:
                salary = f"INR {int(float(amount) * multiplier)} per annum"
        description = clean_text(value("description"))
        experience = clean_text(value("experience_range"))
        if experience:
            description += " Required experience: " + experience + ("" if re.search(r"years?|yrs?", experience, re.I) else " years") + "."
        skills = clean_text(value("skills"))
        if skills:
            description += " Reported skills: " + skills
        mode_text = clean_text(value("work_from_home_type")).lower()
        mode = "hybrid" if "hybrid" in mode_text else "remote" if value("is_remote") == True else "onsite" if "office" in mode_text else ""
        company = clean_text(value("company"))
        mncs = {"tcs", "tata consultancy services", "wipro", "infosys", "cognizant", "hcltech", "tech mahindra", "accenture", "ibm", "capgemini", "ltimindtree"}
        jobs.append(Job(
            source=source["name"], source_kind="jobspy", external_id=str(value("id") or value("job_url") or ""),
            title=clean_text(value("title")), company=company,
            location=normalize_india_location(clean_text(value("location"))), description=description,
            apply_url=clean_text(value("job_url_direct") or value("job_url")), work_mode=mode,
            posted_at=str(value("date_posted") or "") or None, salary_text=salary,
            company_type="mnc" if company.lower() in mncs else "unknown", company_size="unknown",
        ))
    return jobs


CONNECTORS = {
    "openroles": fetch_openroles,
    "jobspy": fetch_jobspy,
    "career_pages": fetch_career_pages,
    "smartrecruiters": fetch_smartrecruiters,
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "remotive": fetch_remotive,
    "arbeitnow": fetch_arbeitnow,
    "jobicy": fetch_jobicy,
    "rss": fetch_rss,
}


def evaluate(job: Job, profile: dict[str, Any]) -> Decision:
    search = profile["search"]
    candidate = profile.get("candidate", {})
    combined = " ".join([job.title, job.description, job.location, job.salary_text or ""]).lower()
    title_lower = job.title.lower()
    location_lower = job.location.lower()
    reasons: list[str] = []
    warnings: list[str] = []

    for excluded in search["excluded_regions"]:
        if contains_term(location_lower, excluded):
            return Decision(False, 0, [f"Excluded location: {excluded}"], warnings)

    for outside_india in search.get("outside_india_markers", []):
        if contains_term(location_lower, outside_india) and "india" not in location_lower:
            return Decision(False, 0, [f"Location is outside India: {outside_india}"], warnings)

    india_location = any(
        re.search(rf"\b{re.escape(marker.lower())}\b", location_lower)
        for marker in search.get("india_location_markers", [])
    )
    if not india_location:
        return Decision(False, 0, ["Location is not confirmed as India"], warnings)

    mode = job.work_mode.lower()
    hybrid = bool(re.search(r"\bhybrid\b", mode + " " + location_lower))
    onsite = bool(re.search(r"\b(on[- ]?site|in[- ]office)\b", mode + " " + location_lower))
    remote = bool(re.search(r"\b(remote|work from home|wfh)\b", mode + " " + location_lower))
    remote_only = bool(re.search(r"\b(fully remote|remote[- ]only|100% remote|fully work from home)\b", combined))
    remote_feed = job.source_kind in {"remotive", "jobicy"} or job.source == "Himalayas Remote Jobs"
    if remote_feed or remote_only or (remote and not (hybrid or onsite)):
        return Decision(False, 0, ["Remote role excluded: hybrid or onsite in India required"], warnings)
    physical_location = any(
        marker.lower() != "india" and contains_term(location_lower, marker)
        for marker in search.get("india_location_markers", [])
    )
    if not (hybrid or onsite or physical_location):
        return Decision(False, 0, ["Hybrid or onsite office location is not confirmed"], warnings)
    if not (hybrid or onsite):
        warnings.append("Indian office location listed; confirm onsite/hybrid arrangement before approval")

    role_hits = [keyword for keyword in search["role_keywords"] if contains_term(combined, keyword)]
    fresher_hits = [keyword for keyword in search.get("mnc_fresher_keywords", []) if contains_term(combined, keyword)]
    technical_hits = [
        keyword for keyword in search.get("mnc_fresher_technical_keywords", []) if contains_term(combined, keyword)
    ]
    company_type = job.company_type.lower()
    preferred_company = any(value in company_type for value in search["preferred_company_types"])
    title_technical = any(contains_term(title_lower, keyword) for keyword in search.get("mnc_fresher_technical_keywords", []))
    if not title_technical and not any(contains_term(title_lower, keyword) for keyword in search["role_keywords"]):
        role_hits = []
    junior_title = bool(re.search(r"\b(trainee|graduate|fresher|junior|entry[- ]level|associate|sde[- ]?1|engineer[- ]?i)\b", title_lower))
    years = explicit_years_required(combined)
    mnc_company = company_type in {"mnc", "enterprise"}
    explicit_fresher = [hit for hit in fresher_hits if hit != "associate"]
    mnc_fresher_match = mnc_company and title_technical and (junior_title or bool(explicit_fresher) or years is not None and years <= 1)
    stack_hits = [keyword for keyword in search.get("stack_match_keywords", []) if contains_term(combined, keyword)]
    stack_match = title_technical and len(stack_hits) >= 2
    if not role_hits and not mnc_fresher_match and not stack_match:
        return Decision(False, 0, ["No GenAI, MNC fresher, or two-skill technical stack match"], warnings)

    if re.search(r"\b(senior|sr|staff|principal|lead|manager|director|head|architect)\b", title_lower):
        return Decision(False, 0, ["Title is explicitly senior for the current experience level"], warnings)

    years = explicit_years_required(combined)
    maximum_years = int(search["maximum_explicit_years_required"])
    if years is not None and years > maximum_years:
        return Decision(False, 0, [f"Role explicitly requires {years} years"], warnings)

    salary = salary_inr_annual(job.salary_text or combined)
    minimum_salary = int(search["minimum_salary_inr"])
    if salary is not None and salary < minimum_salary:
        return Decision(False, 0, [f"Salary below ₹{minimum_salary:,}"], warnings)

    small_startup = company_type == "startup" and job.company_size.lower() in {"small", "1-10", "11-50", "unknown"}
    if small_startup:
        startup_floor = int(search["small_startup_minimum_salary_inr"])
        if salary is None or salary < startup_floor:
            return Decision(False, 0, ["Small startup without verified premium compensation"], warnings)

    score = 40
    if role_hits:
        reasons.append("GenAI role match: " + ", ".join(role_hits[:4]))
    elif mnc_fresher_match:
        reasons.append("MNC fresher technical role: " + ", ".join((fresher_hits + technical_hits)[:5]))
    else:
        reasons.append("Stack-matched technical role: " + ", ".join(stack_hits[:5]))

    delivery_hits = [keyword for keyword in search["delivery_keywords"] if contains_term(combined, keyword)]
    if delivery_hits:
        score += min(15, 3 * len(delivery_hits))
        reasons.append("End-to-end delivery match: " + ", ".join(delivery_hits[:4]))

    skill_hits = [keyword for keyword in candidate.get("skill_keywords", []) if contains_term(combined, keyword)]
    if skill_hits:
        score += min(10, 2 * len(skill_hits))
        reasons.append("Resume-backed skills: " + ", ".join(skill_hits[:5]))

    preferred_location = next(
        (region for region in search["preferred_regions"] if contains_term(location_lower, region)),
        None,
    )
    if preferred_location:
        score += 15
        reasons.append(f"Preferred North India location: {preferred_location}")
    else:
        score += 5
        warnings.append("Location is allowed but not a North India preference match")

    if years is None:
        score += 8
        warnings.append("Experience requirement is not explicit")
    elif years <= 1:
        score += 15
        reasons.append("Experience requirement fits an early-career profile")
    else:
        score += 8
        reasons.append(f"Experience requirement is within configured maximum: {years} years")
    full_time_years = candidate.get("full_time_months", 6) / 12
    if years is not None and years > full_time_years:
        warnings.append(f"Stretch role: asks for {years} years versus {full_time_years:g} years full-time; internships are separate")

    if salary is None:
        score += 4
        warnings.append("Salary is unknown and must be checked before approval")
    else:
        score += 10
        reasons.append(f"Salary evidence meets threshold: approximately ₹{salary:,} annually")

    if preferred_company:
        score += 5
        reasons.append(f"Preferred company type: {job.company_type}")

    if canonical_host(job.apply_url) in {"", "bit.ly", "tinyurl.com"}:
        return Decision(False, 0, ["Application URL is missing or uses a shortened domain"], warnings)

    return Decision(True, min(score, 100), reasons, warnings)


def connect_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            stable_key TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            apply_url TEXT NOT NULL,
            posted_at TEXT,
            salary_text TEXT,
            company_type TEXT NOT NULL,
            company_size TEXT NOT NULL,
            eligible INTEGER NOT NULL,
            score INTEGER NOT NULL,
            reasons_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'review',
            discovered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            action TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            fetched INTEGER NOT NULL DEFAULT 0,
            created INTEGER NOT NULL DEFAULT 0,
            eligible INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'running'
        );
        CREATE TABLE IF NOT EXISTS source_runs (
            id INTEGER PRIMARY KEY,
            scan_run_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            fetched INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id)
        );
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
    if "work_mode" not in columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN work_mode TEXT NOT NULL DEFAULT ''")
    return connection


def store_job(connection: sqlite3.Connection, job: Job, decision: Decision) -> tuple[int, bool]:
    key = stable_key(job)
    timestamp = now_iso()
    existing = connection.execute("SELECT id FROM jobs WHERE stable_key = ?", (key,)).fetchone()
    values = (
        job.source,
        job.source_kind,
        job.external_id,
        job.title,
        job.company,
        job.location,
        job.description,
        job.apply_url,
        job.posted_at,
        job.salary_text,
        job.company_type,
        job.company_size,
        int(decision.eligible),
        decision.score,
        json.dumps(decision.reasons),
        json.dumps(decision.warnings),
        timestamp,
    )
    if existing:
        connection.execute(
            """
            UPDATE jobs SET source=?, source_kind=?, external_id=?, title=?, company=?, location=?,
                description=?, apply_url=?, posted_at=?, salary_text=?, company_type=?, company_size=?,
                eligible=?, score=?, reasons_json=?, warnings_json=?, updated_at=?
            WHERE stable_key=?
            """,
            values + (key,),
        )
        job_id = int(existing["id"])
        created = False
    else:
        cursor = connection.execute(
            """
            INSERT INTO jobs (
                stable_key, source, source_kind, external_id, title, company, location, description,
                apply_url, posted_at, salary_text, company_type, company_size, eligible, score,
                reasons_json, warnings_json, discovered_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (key,) + values[:-1] + (timestamp, timestamp),
        )
        job_id = int(cursor.lastrowid)
        created = True
    connection.execute("UPDATE jobs SET work_mode=? WHERE id=?", (job.work_mode, job_id))
    return job_id, created


def record_event(connection: sqlite3.Connection, job_id: int | None, action: str, details: str) -> None:
    connection.execute(
        "INSERT INTO events (job_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (job_id, action, details, now_iso()),
    )


def discover(args: argparse.Namespace) -> int:
    profile = load_json(Path(args.profile))
    sources = load_json(Path(args.sources))["sources"]
    connection = connect_database(Path(args.database))
    for row in connection.execute("SELECT * FROM jobs").fetchall():
        existing = Job(**{field: row[field] for field in Job.__dataclass_fields__ if field in row.keys()})
        decision = evaluate(existing, profile)
        connection.execute(
            "UPDATE jobs SET eligible=?, score=?, reasons_json=?, warnings_json=? WHERE id=?",
            (decision.eligible, decision.score, json.dumps(decision.reasons), json.dumps(decision.warnings), row["id"]),
        )
    run_cursor = connection.execute(
        "INSERT INTO scan_runs (started_at, status) VALUES (?, 'running')",
        (now_iso(),),
    )
    scan_run_id = int(run_cursor.lastrowid)
    connection.commit()
    fetched = created = eligible = 0
    failures = []
    for source in sources:
        if not source.get("enabled"):
            continue
        kind = source.get("kind")
        connector = CONNECTORS.get(kind)
        if connector is None:
            failures.append(f"{source['name']}: unsupported connector {kind}")
            connection.execute(
                "INSERT INTO source_runs (scan_run_id, source, source_kind, status, error, created_at) VALUES (?, ?, ?, 'failed', ?, ?)",
                (scan_run_id, source["name"], str(kind), f"Unsupported connector: {kind}", now_iso()),
            )
            continue
        try:
            jobs = connector(source)
            india_markers = profile["search"].get("india_location_markers", []) + profile["search"]["excluded_regions"]
            jobs = [
                job for job in jobs
                if any(re.search(rf"\b{re.escape(marker.lower())}\b", job.location.lower()) for marker in india_markers)
            ]
            fetched += len(jobs)
            for job in jobs:
                decision = evaluate(job, profile)
                eligible += int(decision.eligible)
                job_id, is_new = store_job(connection, job, decision)
                created += int(is_new)
                if is_new:
                    record_event(connection, job_id, "discovered", f"score={decision.score}; eligible={decision.eligible}")
            connection.execute(
                "INSERT INTO source_runs (scan_run_id, source, source_kind, fetched, status, created_at) VALUES (?, ?, ?, ?, 'complete', ?)",
                (scan_run_id, source["name"], str(kind), len(jobs), now_iso()),
            )
            connection.commit()
            print(f"{source['name']}: {len(jobs)} jobs fetched")
        except (OSError, ValueError, KeyError, ET.ParseError, urllib.error.URLError) as error:
            failures.append(f"{source['name']}: {error}")
            connection.execute(
                "INSERT INTO source_runs (scan_run_id, source, source_kind, status, error, created_at) VALUES (?, ?, ?, 'failed', ?, ?)",
                (scan_run_id, source["name"], str(kind), str(error), now_iso()),
            )
            connection.commit()
    run_status = "failed" if failures and fetched == 0 else "complete_with_warnings" if failures else "complete"
    connection.execute(
        """
        UPDATE scan_runs
        SET completed_at=?, fetched=?, created=?, eligible=?, failure_count=?, status=?
        WHERE id=?
        """,
        (now_iso(), fetched, created, eligible, len(failures), run_status, scan_run_id),
    )
    connection.commit()
    print(f"Fetched {fetched}; new {created}; eligible {eligible}")
    for failure in failures:
        print(f"WARNING: {failure}", file=sys.stderr)
    return 1 if failures and fetched == 0 else 0


def query_jobs(connection: sqlite3.Connection, status: str | None, minimum_score: int) -> list[sqlite3.Row]:
    clauses = ["eligible = 1", "score >= ?"]
    values: list[Any] = [minimum_score]
    if status:
        clauses.append("status = ?")
        values.append(status)
    return list(
        connection.execute(
            f"SELECT * FROM jobs WHERE {' AND '.join(clauses)} ORDER BY score DESC, discovered_at DESC",
            values,
        )
    )


def list_jobs(args: argparse.Namespace) -> int:
    connection = connect_database(Path(args.database))
    rows = query_jobs(connection, args.status, args.minimum_score)
    if not rows:
        print("No matching jobs in the queue. Run discover first.")
        return 0
    print(f"{'ID':>4}  {'Score':>5}  {'Status':<9}  {'Title':<38}  {'Company':<24}  Location")
    for row in rows[: args.limit]:
        print(
            f"{row['id']:>4}  {row['score']:>5}  {row['status']:<9}  "
            f"{row['title'][:38]:<38}  {row['company'][:24]:<24}  {row['location'][:32]}"
        )
    return 0


def show_job(args: argparse.Namespace) -> int:
    connection = connect_database(Path(args.database))
    row = connection.execute("SELECT * FROM jobs WHERE id = ?", (args.job_id,)).fetchone()
    if not row:
        print(f"Job {args.job_id} not found", file=sys.stderr)
        return 1
    print(f"[{row['score']}] {row['title']} at {row['company']}")
    print(f"Location: {row['location']}")
    print(f"Status: {row['status']}")
    print(f"Source: {row['source']}")
    print(f"Apply: {row['apply_url']}")
    print("Reasons:")
    for reason in json.loads(row["reasons_json"]):
        print(f"  + {reason}")
    warnings = json.loads(row["warnings_json"])
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  ! {warning}")
    print("Description:")
    print(clean_text(row["description"])[:2500])
    return 0


def change_status(args: argparse.Namespace, status: str) -> int:
    connection = connect_database(Path(args.database))
    row = connection.execute("SELECT * FROM jobs WHERE id = ?", (args.job_id,)).fetchone()
    if not row:
        print(f"Job {args.job_id} not found", file=sys.stderr)
        return 1
    connection.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), args.job_id))
    record_event(connection, args.job_id, status, args.note or "")
    connection.commit()
    print(f"Job {args.job_id} marked {status}")
    if status == "approved" and args.open:
        webbrowser.open(row["apply_url"])
    return 0


def open_job(args: argparse.Namespace) -> int:
    connection = connect_database(Path(args.database))
    row = connection.execute("SELECT apply_url FROM jobs WHERE id = ?", (args.job_id,)).fetchone()
    if not row:
        print(f"Job {args.job_id} not found", file=sys.stderr)
        return 1
    webbrowser.open(row["apply_url"])
    print(row["apply_url"])
    return 0


def write_dashboard(args: argparse.Namespace) -> int:
    from .web import build_snapshot_dashboard

    output = build_snapshot_dashboard(
        database=Path(args.database),
        profile=Path(args.profile),
        sources=Path(args.sources),
        output=Path(args.output),
    )
    print(output.resolve())
    return 0


def serve_dashboard(args: argparse.Namespace) -> int:
    from .web import serve

    serve(
        database=Path(args.database),
        profile=Path(args.profile),
        sources=Path(args.sources),
        host=args.host,
        port=args.port,
        open_browser=args.open,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Private job discovery and approval queue")
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Fetch and score jobs from enabled sources")
    discover_parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    discover_parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    discover_parser.set_defaults(handler=discover)

    list_parser = subparsers.add_parser("list", help="List the approval queue")
    list_parser.add_argument("--status", default="review")
    list_parser.add_argument("--minimum-score", type=int, default=65)
    list_parser.add_argument("--limit", type=int, default=30)
    list_parser.set_defaults(handler=list_jobs)

    show_parser = subparsers.add_parser("show", help="Show one scored job")
    show_parser.add_argument("job_id", type=int)
    show_parser.set_defaults(handler=show_job)

    for command, status in (("approve", "approved"), ("reject", "rejected"), ("mark-applied", "applied")):
        status_parser = subparsers.add_parser(command)
        status_parser.add_argument("job_id", type=int)
        status_parser.add_argument("--note")
        status_parser.add_argument("--open", action="store_true")
        status_parser.set_defaults(handler=lambda args, value=status: change_status(args, value))

    open_parser = subparsers.add_parser("open", help="Open the official application URL")
    open_parser.add_argument("job_id", type=int)
    open_parser.set_defaults(handler=open_job)

    dashboard_parser = subparsers.add_parser("dashboard", help="Write a static HTML review queue")
    dashboard_parser.add_argument("--output", default=str(DEFAULT_DASHBOARD))
    dashboard_parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    dashboard_parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    dashboard_parser.set_defaults(handler=write_dashboard)

    serve_parser = subparsers.add_parser("serve", help="Run the local monitoring and approval control center")
    serve_parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    serve_parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--open", action="store_true")
    serve_parser.set_defaults(handler=serve_dashboard)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.handler(args))


if __name__ == "__main__":
    main()
