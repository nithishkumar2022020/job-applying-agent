from __future__ import annotations

import argparse
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
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


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
    matches = re.findall(r"(\d+)\s*(?:\+\s*)?(?:years?|yrs?)", text.lower())
    return min((int(value) for value in matches), default=None)


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


CONNECTORS = {
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
        contains_term(location_lower, marker) for marker in search.get("india_location_markers", [])
    )
    unrestricted_remote = location_lower.strip(" .,-") in {"remote", "worldwide", "anywhere", "global"}
    regional_remote = contains_term(location_lower, "asia") or contains_term(location_lower, "apac")
    if not (india_location or unrestricted_remote or regional_remote):
        return Decision(False, 0, ["Location is not confirmed as India-compatible"], warnings)

    role_hits = [keyword for keyword in search["role_keywords"] if contains_term(combined, keyword)]
    fresher_hits = [keyword for keyword in search.get("mnc_fresher_keywords", []) if contains_term(combined, keyword)]
    technical_hits = [
        keyword for keyword in search.get("mnc_fresher_technical_keywords", []) if contains_term(combined, keyword)
    ]
    company_type = job.company_type.lower()
    preferred_company = any(value in company_type for value in search["preferred_company_types"])
    mnc_fresher_match = preferred_company and fresher_hits and technical_hits
    if not role_hits and not mnc_fresher_match:
        return Decision(False, 0, ["No GenAI match or relevant MNC fresher-role evidence"], warnings)

    if re.search(r"\b(senior|staff|principal|lead|manager|director|head|architect)\b", title_lower):
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
    else:
        reasons.append("MNC fresher technical role: " + ", ".join((fresher_hits + technical_hits)[:5]))

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
    remote_india = search.get("allow_remote_india") and "remote" in location_lower and (
        "india" in location_lower or location_lower.strip() == "remote"
    )
    if preferred_location:
        score += 15
        reasons.append(f"Preferred North India location: {preferred_location}")
    elif remote_india:
        score += 12
        reasons.append("Remote role available from India")
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
        """
    )
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
    fetched = created = eligible = 0
    failures = []
    for source in sources:
        if not source.get("enabled"):
            continue
        kind = source.get("kind")
        connector = CONNECTORS.get(kind)
        if connector is None:
            failures.append(f"{source['name']}: unsupported connector {kind}")
            continue
        try:
            jobs = connector(source)
            fetched += len(jobs)
            for job in jobs:
                decision = evaluate(job, profile)
                eligible += int(decision.eligible)
                job_id, is_new = store_job(connection, job, decision)
                created += int(is_new)
                if is_new:
                    record_event(connection, job_id, "discovered", f"score={decision.score}; eligible={decision.eligible}")
            connection.commit()
            print(f"{source['name']}: {len(jobs)} jobs fetched")
        except (OSError, ValueError, KeyError, ET.ParseError, urllib.error.URLError) as error:
            failures.append(f"{source['name']}: {error}")
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
    connection = connect_database(Path(args.database))
    rows = query_jobs(connection, args.status, args.minimum_score)[: args.limit]
    cards = []
    for row in rows:
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in json.loads(row["reasons_json"]))
        warnings = "".join(f"<li>{html.escape(warning)}</li>" for warning in json.loads(row["warnings_json"]))
        cards.append(
            f"""
            <article>
              <div class="score">{row['score']}</div>
              <h2>{html.escape(row['title'])}</h2>
              <p class="meta">{html.escape(row['company'])} · {html.escape(row['location'])} · {html.escape(row['source'])}</p>
              <p><strong>Status:</strong> {html.escape(row['status'])} · <strong>ID:</strong> {row['id']}</p>
              <h3>Why it matched</h3><ul>{reasons}</ul>
              {f'<h3>Review before approval</h3><ul>{warnings}</ul>' if warnings else ''}
              <p><a href="{html.escape(row['apply_url'])}" target="_blank" rel="noreferrer">Open source listing</a></p>
              <code>python -m job_agent approve {row['id']} --open</code>
            </article>
            """
        )
    output = Path(args.output)
    output.write_text(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job approval queue</title><style>
body{{font-family:Arial,sans-serif;background:#f4f7fb;color:#172033;margin:0;padding:32px}}main{{max-width:980px;margin:auto}}
h1{{margin:0 0 8px}}.sub{{color:#5d6779;margin-bottom:28px}}article{{position:relative;background:#fff;border:1px solid #dce2eb;border-radius:14px;padding:24px;margin:18px 0;box-shadow:0 4px 18px #15233a12}}
.score{{position:absolute;right:22px;top:20px;background:#17365d;color:white;border-radius:999px;width:48px;height:48px;display:grid;place-items:center;font-weight:700}}
h2{{margin:0 60px 6px 0}}h3{{font-size:15px;margin-bottom:5px}}.meta{{color:#5d6779}}a{{color:#174f87;font-weight:700}}code{{display:inline-block;background:#eef2f7;padding:8px 10px;border-radius:7px}}
</style></head><body><main><h1>Job approval queue</h1><p class="sub">Generated {now_iso()}. Approval is required before every application.</p>{''.join(cards) or '<p>No matching jobs.</p>'}</main></body></html>""",
        encoding="utf-8",
    )
    print(output.resolve())
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
    dashboard_parser.add_argument("--status", default="review")
    dashboard_parser.add_argument("--minimum-score", type=int, default=65)
    dashboard_parser.add_argument("--limit", type=int, default=50)
    dashboard_parser.set_defaults(handler=write_dashboard)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.handler(args))


if __name__ == "__main__":
    main()
