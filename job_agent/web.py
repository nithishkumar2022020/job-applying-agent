from __future__ import annotations

import argparse
import json
import re
import sqlite3
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .app import connect_database, discover, load_json, now_iso, record_event


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
ALLOWED_STATUSES = {"review", "approved", "rejected", "applied"}
SCAN_LOCK = threading.Lock()


def row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    job["eligible"] = bool(job["eligible"])
    job["reasons"] = json.loads(job.pop("reasons_json"))
    job["warnings"] = json.loads(job.pop("warnings_json"))
    job["description"] = job["description"][:4000]
    return job


def build_snapshot_dashboard(database: Path, profile: Path, sources: Path, output: Path) -> Path:
    handler = object.__new__(DashboardHandler)
    handler.database = database
    handler.profile = profile
    handler.sources = sources
    snapshot = {
        "summary": handler.summary(),
        "jobs": handler.jobs({})["jobs"],
        "sources": handler.source_status(),
        "activity": handler.activity(),
        "profile": handler.safe_profile(),
        "generated_at": now_iso(),
    }
    serialized = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")
    template = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    template = template.replace('href="styles.css"', 'href="web/styles.css"')
    template = template.replace(
        '<script src="app.js"></script>',
        f'<script>window.__JOB_AGENT_SNAPSHOT__={serialized};</script><script src="web/app.js"></script>',
    )
    output.write_text(template, encoding="utf-8")
    return output


class DashboardHandler(BaseHTTPRequestHandler):
    database: Path
    profile: Path
    sources: Path

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_file(self, path: Path) -> None:
        if not path.is_file() or WEB_ROOT not in path.resolve().parents:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(path.suffix, "application/octet-stream")
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        routes = {
            "/api/summary": self.summary,
            "/api/jobs": lambda: self.jobs(parse_qs(parsed.query)),
            "/api/sources": self.source_status,
            "/api/activity": self.activity,
            "/api/profile": self.safe_profile,
        }
        if parsed.path in routes:
            self.send_json(routes[parsed.path]())
        elif parsed.path in {"/", "/index.html"}:
            self.send_file(WEB_ROOT / "index.html")
        else:
            self.send_file(WEB_ROOT / parsed.path.lstrip("/"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/scan":
            self.start_scan()
            return
        match = re.fullmatch(r"/api/jobs/(\d+)/status", parsed.path)
        if match:
            self.update_status(int(match.group(1)))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def connection(self) -> sqlite3.Connection:
        return connect_database(self.database)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 16_384:
            raise ValueError("Request body is too large")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def summary(self) -> dict[str, Any]:
        connection = self.connection()
        row = connection.execute(
            """
            SELECT COUNT(*) total,
                   COALESCE(SUM(eligible), 0) shortlisted,
                   SUM(CASE WHEN eligible=0 THEN 1 ELSE 0 END) filtered,
                   SUM(CASE WHEN eligible=1 AND status='review' THEN 1 ELSE 0 END) awaiting_review,
                   SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) approved,
                   SUM(CASE WHEN status='applied' THEN 1 ELSE 0 END) applied
            FROM jobs
            """
        ).fetchone()
        latest = connection.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
        result = {
            "counts": dict(row),
            "latest_scan": dict(latest) if latest else None,
            "approval_policy": "Every application requires your approval",
            "submission_enabled": False,
        }
        connection.close()
        return result

    def jobs(self, query: dict[str, list[str]]) -> dict[str, Any]:
        view = query.get("view", ["all"])[0]
        search = query.get("q", [""])[0].strip().lower()
        source = query.get("source", [""])[0].strip()
        clauses: list[str] = []
        values: list[Any] = []
        view_clauses = {
            "shortlisted": "eligible=1",
            "review": "eligible=1 AND status='review'",
            "approved": "status='approved'",
            "applied": "status='applied'",
            "filtered": "eligible=0",
        }
        if view in view_clauses:
            clauses.append(view_clauses[view])
        if search:
            clauses.append("LOWER(title || ' ' || company || ' ' || location || ' ' || description) LIKE ?")
            values.append(f"%{search}%")
        if source:
            clauses.append("source=?")
            values.append(source)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        connection = self.connection()
        rows = connection.execute(
            f"SELECT * FROM jobs {where} ORDER BY eligible DESC, score DESC, updated_at DESC LIMIT 500",
            values,
        ).fetchall()
        result = {"jobs": [row_to_job(row) for row in rows]}
        connection.close()
        return result

    def source_status(self) -> dict[str, Any]:
        configured = load_json(self.sources)["sources"]
        connection = self.connection()
        metrics = {
            row["source"]: dict(row)
            for row in connection.execute(
                "SELECT source, COUNT(*) found, COALESCE(SUM(eligible), 0) shortlisted FROM jobs GROUP BY source"
            )
        }
        latest_runs = {
            row["source"]: dict(row)
            for row in connection.execute(
                """
                SELECT sr.* FROM source_runs sr
                JOIN (SELECT source, MAX(id) id FROM source_runs GROUP BY source) latest ON latest.id=sr.id
                """
            )
        }
        result = []
        for source in sorted(configured, key=lambda item: item.get("priority", 0), reverse=True):
            item = dict(source)
            item["metrics"] = metrics.get(source["name"], {"found": 0, "shortlisted": 0})
            item["latest_run"] = latest_runs.get(source["name"])
            result.append(item)
        connection.close()
        return {"sources": result}

    def activity(self) -> dict[str, Any]:
        connection = self.connection()
        scans = [dict(row) for row in connection.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 20")]
        events = [
            dict(row)
            for row in connection.execute(
                """
                SELECT events.*, jobs.title, jobs.company FROM events
                LEFT JOIN jobs ON jobs.id=events.job_id
                WHERE action != 'discovered' ORDER BY events.id DESC LIMIT 50
                """
            )
        ]
        connection.close()
        return {"scans": scans, "events": events}

    def safe_profile(self) -> dict[str, Any]:
        profile = load_json(self.profile)
        search = profile["search"]
        return {
            "country": profile.get("candidate", {}).get("country", "India"),
            "preferred_regions": search.get("preferred_regions", []),
            "excluded_regions": search.get("excluded_regions", []),
            "minimum_salary_inr": search.get("minimum_salary_inr"),
            "approval_required": search.get("approval_required", True),
        }

    def start_scan(self) -> None:
        if not SCAN_LOCK.acquire(blocking=False):
            self.send_json({"started": False, "message": "A scan is already running"}, HTTPStatus.CONFLICT)
            return

        def run() -> None:
            try:
                discover(
                    argparse.Namespace(
                        profile=str(self.profile), sources=str(self.sources), database=str(self.database)
                    )
                )
            finally:
                SCAN_LOCK.release()

        threading.Thread(target=run, daemon=True).start()
        self.send_json({"started": True, "message": "Discovery scan started"}, HTTPStatus.ACCEPTED)

    def update_status(self, job_id: int) -> None:
        try:
            status = self.read_json().get("status")
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if status not in ALLOWED_STATUSES:
            self.send_json({"error": "Invalid status"}, HTTPStatus.BAD_REQUEST)
            return
        connection = self.connection()
        row = connection.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            connection.close()
            self.send_json({"error": "Job not found"}, HTTPStatus.NOT_FOUND)
            return
        connection.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=?", (status, now_iso(), job_id))
        record_event(connection, job_id, status, "Updated from control center")
        connection.commit()
        connection.close()
        self.send_json({"updated": True, "job_id": job_id, "status": status})


def serve(database: Path, profile: Path, sources: Path, host: str, port: int, open_browser: bool) -> None:
    handler = type(
        "ConfiguredDashboardHandler",
        (DashboardHandler,),
        {"database": database, "profile": profile, "sources": sources},
    )
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    print(f"Job Agent Control Center: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping control center")
    finally:
        server.server_close()
