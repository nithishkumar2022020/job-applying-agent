# Job Applying Agent

A privacy-first Python CLI that discovers jobs, applies deterministic eligibility rules, scores fit, deduplicates listings, and places suitable roles in a human approval queue. It never submits an application automatically.

## Features

- Direct employer discovery from Rubrik, Databricks, Netskope, Okta, and Meesho
- Direct Greenhouse, Lever, and Ashby employer-board connectors
- GenAI and relevant MNC fresher-role matching
- Indian office location validation, hybrid/onsite matching, and configurable exclusions
- Remote/global feeds disabled; remote roles rejected, including structured ATS work arrangements
- Salary, experience, seniority, startup-size, and URL safeguards
- SQLite history, deduplication, approval states, and HTML dashboard
- Local control center showing all discoveries, filtered jobs, shortlists, approvals, scans, and source health
- Candidate-controlled launch links for LinkedIn, Indeed India, Naukri, Wellfound, Foundit, and Cutshort
- High-priority direct career links for Microsoft, Google, Amazon, IBM, and Accenture
- Four-hour macOS scheduling template

## Setup

```bash
git clone https://github.com/nithishkumar2022020/job-applying-agent.git
cd job-applying-agent
cp profile.example.json profile.json
python3 -m unittest discover -s tests -v
python3 -m job_agent discover
python3 -m job_agent list
python3 -m job_agent dashboard
```

## Control Center

Start the private local website:

```bash
./start_ui.sh
```

Or run it directly:

```bash
python3 -m job_agent serve --host 127.0.0.1 --port 8765 --open
```

The control center runs only on your computer. It shows every discovered job, filtering evidence, shortlisted roles, approval state, scan history, source health, and your active search rules. The **Run scan now** button performs discovery; it never submits an application.

Popular portals that do not expose an approved public interface are included as manual launch links rather than scraped. Direct employer ATS connectors and company career sites remain the highest-priority source class.

## Hosted Dashboard

GitHub Pages publishes a privacy-safe read-only dashboard from `develop`. A scheduled workflow refreshes public sources every four hours and redeploys the result. The hosted build uses `profile.pages.json`, which deliberately excludes resume paths, contact details, local databases, application history, and private candidate files.

Approvals, status updates, and application actions remain available only in the private local control center.

Customize `profile.json` before discovery. The file is ignored by Git because it may contain personal preferences and a local resume path.

Employer boards may return worldwide listings; eligibility requires an Indian location and rejects remote roles. A named Indian city without a published work arrangement is a provisional office match with a confirmation warning. Country-only listings require an explicit hybrid or onsite arrangement. Existing saved jobs are re-evaluated on every scan. Portal links remain manual searches and are not counted as automated coverage.

## Approval Workflow

```bash
python3 -m job_agent show JOB_ID
python3 -m job_agent approve JOB_ID --open
python3 -m job_agent mark-applied JOB_ID --note "Submitted after review"
```

Approval records the decision and opens the source listing or employer application. The candidate still reviews and submits the form manually.

## Scheduling

`run_discovery.sh` discovers jobs, rebuilds `review_queue.html`, and writes `logs/discovery.log`. For macOS, copy the launchd template and replace `/ABSOLUTE/PATH/TO` before loading it.

## Privacy

Never commit `profile.json`, resumes, candidate evidence, SQLite databases, dashboards, logs, credentials, identity documents, or application history. These paths are covered by `.gitignore`.

## Safety

- Never invent candidate claims or application answers.
- Never bypass CAPTCHAs, access controls, or rate limits.
- Never automate LinkedIn access or applications.
- Never submit without explicit candidate approval.
