import json
import tempfile
import unittest
from pathlib import Path

from job_agent.app import Job, clean_text, connect_database, contains_term, evaluate, salary_inr_annual, stable_key, store_job
from job_agent.web import DashboardHandler, build_snapshot_dashboard


PROFILE = {
    "search": {
        "role_keywords": ["genai", "llm", "rag", "ai engineer"],
        "delivery_keywords": ["deployment", "production", "api"],
        "preferred_regions": ["Delhi", "Gurugram", "Noida"],
        "excluded_regions": ["Telangana", "Hyderabad", "Andhra Pradesh"],
        "outside_india_markers": ["United States", "Canada", "Europe"],
        "india_location_markers": ["India", "Delhi", "Gurugram", "Noida", "Bengaluru", "Mumbai"],
        "allow_remote_india": True,
        "minimum_salary_inr": 500000,
        "small_startup_minimum_salary_inr": 700000,
        "maximum_explicit_years_required": 2,
        "preferred_company_types": ["mnc", "enterprise", "mid-size"],
        "mnc_fresher_keywords": ["fresher", "new grad", "graduate engineer", "entry level", "junior"],
        "mnc_fresher_technical_keywords": ["software engineer", "data analyst", "cloud engineer"],
    }
}


def job(**overrides):
    values = {
        "source": "test",
        "source_kind": "fixture",
        "external_id": "1",
        "title": "Junior GenAI Engineer",
        "company": "Example MNC",
        "location": "Gurugram, India",
        "description": "Build RAG and LLM APIs from prototype to production deployment. 0-1 years.",
        "apply_url": "https://example.com/careers/1",
        "salary_text": "INR 6 LPA",
        "company_type": "mnc",
        "company_size": "enterprise",
    }
    values.update(overrides)
    return Job(**values)


class ScoringTests(unittest.TestCase):
    def test_good_genai_role_is_eligible(self):
        decision = evaluate(job(), PROFILE)
        self.assertTrue(decision.eligible)
        self.assertGreaterEqual(decision.score, 85)

    def test_excluded_state_is_rejected(self):
        decision = evaluate(job(location="Hyderabad, Telangana"), PROFILE)
        self.assertFalse(decision.eligible)

    def test_overseas_only_role_is_rejected(self):
        decision = evaluate(job(location="Remote - United States"), PROFILE)
        self.assertFalse(decision.eligible)
        self.assertIn("outside India", decision.reasons[0])

    def test_unlisted_overseas_location_is_rejected(self):
        decision = evaluate(job(location="Bulgaria"), PROFILE)
        self.assertFalse(decision.eligible)
        self.assertIn("not confirmed", decision.reasons[0])

    def test_structured_description_is_cleaned(self):
        value = [{"text": "Build RAG systems", "content": "Deploy APIs"}]
        self.assertIn("Build RAG systems", clean_text(value))

    def test_short_keywords_require_word_boundaries(self):
        self.assertTrue(contains_term("Build a RAG pipeline", "rag"))
        self.assertFalse(contains_term("Manage storage systems", "rag"))
        self.assertFalse(contains_term("Work in Lausanne", "usa"))

    def test_low_salary_is_rejected(self):
        decision = evaluate(job(salary_text="4 LPA"), PROFILE)
        self.assertFalse(decision.eligible)

    def test_mnc_fresher_technical_role_is_eligible(self):
        sample = job(
            title="Graduate Software Engineer",
            description="Entry level software engineer role building enterprise services.",
        )
        decision = evaluate(sample, PROFILE)
        self.assertTrue(decision.eligible)
        self.assertIn("MNC fresher technical role", decision.reasons[0])

    def test_startup_fresher_role_without_genai_is_rejected(self):
        sample = job(
            title="Graduate Software Engineer",
            description="Entry level software engineer role.",
            company_type="startup",
        )
        self.assertFalse(evaluate(sample, PROFILE).eligible)

    def test_senior_role_is_rejected(self):
        decision = evaluate(job(title="Senior GenAI Engineer"), PROFILE)
        self.assertFalse(decision.eligible)

    def test_salary_parser(self):
        self.assertEqual(salary_inr_annual("₹6.5 LPA"), 650000)
        self.assertEqual(salary_inr_annual("INR 900000 per annum"), 900000)


class StorageTests(unittest.TestCase):
    def test_duplicate_jobs_update_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = connect_database(Path(directory) / "jobs.sqlite3")
            sample = job()
            decision = evaluate(sample, PROFILE)
            first_id, first_created = store_job(connection, sample, decision)
            second_id, second_created = store_job(connection, sample, decision)
            self.assertTrue(first_created)
            self.assertFalse(second_created)
            self.assertEqual(first_id, second_id)
            self.assertEqual(stable_key(sample), stable_key(sample))

    def test_dashboard_summary_reports_pipeline_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "jobs.sqlite3"
            connection = connect_database(database)
            sample = job()
            store_job(connection, sample, evaluate(sample, PROFILE))
            connection.commit()
            handler = object.__new__(DashboardHandler)
            handler.database = database
            summary = handler.summary()
            self.assertEqual(summary["counts"]["total"], 1)
            self.assertEqual(summary["counts"]["shortlisted"], 1)
            self.assertFalse(summary["submission_enabled"])

    def test_scan_tables_are_created(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = connect_database(Path(directory) / "jobs.sqlite3")
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            self.assertIn("scan_runs", tables)
            self.assertIn("source_runs", tables)

    def test_snapshot_dashboard_contains_all_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "jobs.sqlite3"
            connection = connect_database(database)
            sample = job()
            store_job(connection, sample, evaluate(sample, PROFILE))
            connection.commit()
            profile = root / "profile.json"
            profile.write_text(json.dumps(PROFILE), encoding="utf-8")
            sources = root / "sources.json"
            sources.write_text('{"sources": []}', encoding="utf-8")
            output = root / "dashboard.html"
            build_snapshot_dashboard(database, profile, sources, output)
            contents = output.read_text(encoding="utf-8")
            self.assertIn("window.__JOB_AGENT_SNAPSHOT__", contents)
            self.assertIn(sample.title, contents)


if __name__ == "__main__":
    unittest.main()
