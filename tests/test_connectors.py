import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from job_agent.app import explicit_years_required, fetch_jobspy, fetch_openroles, normalize_india_location


class DiscoveryConnectorTests(unittest.TestCase):
    def test_jobspy_india_salary_experience_and_missing_values(self):
        row = {"id": "one", "title": "Python Developer", "company": "Infosys", "location": "DL, India",
               "description": "Python FastAPI services", "experience_range": "0-2", "skills": "Python",
               "min_amount": 50000, "interval": "monthly", "currency": "INR", "is_remote": False,
               "job_url": "https://in.indeed.com/viewjob?jk=one", "job_url_direct": float("nan"), "date_posted": None}
        calls = []

        def scrape(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(to_dict=lambda **ignored: [row])

        modules = {"jobspy": SimpleNamespace(scrape_jobs=scrape), "pandas": SimpleNamespace(isna=lambda value: value != value)}
        with patch.dict(sys.modules, modules):
            job = fetch_jobspy({"name": "Indeed", "site": "indeed", "query": "Python", "results_wanted": 999})[0]
        self.assertEqual(calls[0]["country_indeed"], "India")
        self.assertEqual(calls[0]["results_wanted"], 100)
        self.assertNotIn("proxies", calls[0])
        self.assertEqual(job.location, "Delhi, India")
        self.assertEqual(job.salary_text, "INR 600000 per annum")
        self.assertEqual(job.apply_url, row["job_url"])
        self.assertEqual(explicit_years_required(job.description), 0)
        self.assertEqual(job.company_type, "mnc")

    def test_foreign_salary_is_not_treated_as_rupees(self):
        row = {"title": "Developer", "location": "KA, India", "currency": "USD", "min_amount": 50000,
               "interval": "yearly", "is_remote": True, "job_url": "https://example.com/job"}
        modules = {"jobspy": SimpleNamespace(scrape_jobs=lambda **ignored: SimpleNamespace(to_dict=lambda **ignored: [row])),
                   "pandas": SimpleNamespace(isna=lambda value: value != value)}
        with patch.dict(sys.modules, modules):
            job = fetch_jobspy({"name": "Naukri", "site": "naukri", "query": "Python"})[0]
        self.assertIsNone(job.salary_text)
        self.assertEqual(job.work_mode, "remote")

    def test_india_state_normalization_preserves_overseas_locations(self):
        self.assertEqual(normalize_india_location("TS, India"), "Telangana, India")
        self.assertEqual(normalize_india_location("AP, India"), "Andhra Pradesh, India")
        self.assertEqual(normalize_india_location("London, UK"), "London, UK")

    def test_openroles_details_are_bounded_and_remote_is_preserved(self):
        items = [SimpleNamespace(id=str(index), title="Python Engineer", location="Bengaluru, India", description="Python FastAPI",
                                 url=f"https://example.com/jobs/{index}", workplace="remote", remote=True, posted="2026-11-17", compensation="")
                 for index in range(3)]
        calls = []

        def fetch(target, **kwargs):
            calls.append(kwargs)
            return [item for item in items if kwargs["details"](item)]

        module = SimpleNamespace(configure=lambda **ignored: None, fetch=fetch, BoardError=RuntimeError)
        with patch.dict(sys.modules, {"openroles": module}):
            jobs = fetch_openroles({"name": "Employer", "company": "Employer", "target": "https://ats.rippling.com/employer", "detail_limit": 1})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(calls[0]["country"], "India")
        self.assertEqual(jobs[0].work_mode, "remote")

    def test_blocked_employer_is_reported_as_failure(self):
        def fetch(*args, **kwargs):
            raise RuntimeError("HTTP 429")

        module = SimpleNamespace(configure=lambda **ignored: None, fetch=fetch, BoardError=RuntimeError)
        with patch.dict(sys.modules, {"openroles": module}):
            with self.assertRaisesRegex(ValueError, "429"):
                fetch_openroles({"name": "Employer", "company": "Employer", "target": "workday:employer"})


if __name__ == "__main__":
    unittest.main()
