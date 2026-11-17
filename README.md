# Job Applying Agent

A privacy-first Python CLI that discovers jobs, applies deterministic eligibility rules, scores fit, deduplicates listings, and places suitable roles in a human approval queue. It never submits an application automatically.

## Features

- Direct employer discovery from Rubrik, Databricks, Netskope, Okta, Meesho, Sarvam, Sigmoid, CRED, Zeta, Freshworks and Bosch
- Native company-page discovery for a verified AMETEK early-career AI vacancy
- WITCH/graduate pathway research covering TCS, Wipro, Infosys, Cognizant, HCLTech and Tech Mahindra, with dated evidence, salary constraints and next steps
- Direct Greenhouse, Lever, and Ashby employer-board connectors
- GenAI, MNC fresher technical, and two-skill Python/backend/AI stack matching
- Resume skill evidence, detected experience, salary uncertainty, work arrangements and explicit stretch-role warnings
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
python3 -m venv .venv
.venv/bin/python -m pip install '.[discovery]'
source .venv/bin/activate
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

LinkedIn, Wellfound, Foundit and Cutshort remain manual launch links. Naukri and Indeed India also have bounded JobSpy discovery sources, listed separately from their general portal links. Direct employer ATS connectors and company career sites remain highest priority.

Discovery also uses the pinned open-source [JobSpy](https://github.com/speedyapply/JobSpy) and [openroles](https://github.com/aranculleton/openroles) libraries. JobSpy runs bounded public Naukri/Indeed India searches; openroles adds employer ATS systems including Rippling and Workday. Only tested readable boards are enabled. Workday candidates currently blocked by HTTP 429 remain disabled. See [connector research and observed coverage](docs/discovery-research.md) for details. Library support is not the same as verified employer coverage.

## Hosted Dashboard

GitHub Pages publishes a privacy-safe read-only dashboard from `develop`. A scheduled workflow refreshes public sources every four hours and redeploys the result. The hosted build uses `profile.pages.json`, which deliberately excludes resume paths, contact details, local databases, application history, and private candidate files.

The hosted dashboard supports selectable filters, full listing descriptions, direct application links and a browser-local approval queue. Preferences and hosted decisions are stored only in your browser; they are not synchronized across devices or sent to GitHub. On the private local control center, decisions are saved in SQLite. Approve & open application and Open next approved application open employer forms. Only your explicit submission confirmation marks a job applied. No automatic form-submission runner is connected, and GitHub Pages cannot run one; its Auto-apply control displays that state.

Choose company type, work arrangements (including unknown/remote), geography, exclusions, experience, salary, missing-data allowances, seniority, skills, track and source in Job pipeline. These selections filter all imported India listings independently of the original agent eligibility decision. Show all available jobs removes display filters; restore defaults reapplies the initial preferences. Filters change your view and shortlist in this browser, while automated discovery continues checking the configured employer sources. Unavailable jobs or unconnected sources cannot be added by a display filter.

Customize `profile.json` before discovery. The file is ignored by Git because it may contain personal preferences and a local resume path.

Employer boards may return worldwide listings; eligibility requires an Indian location and rejects remote roles. A named Indian city without a published work arrangement is a provisional office match with a confirmation warning. Country-only listings require an explicit hybrid or onsite arrangement. Existing saved jobs are re-evaluated on every scan. Portal links remain manual searches and are not counted as automated coverage.

The Fresher pathways section contains researched program leads, not confirmed open jobs. Evidence dates are shown separately from automated job scan times. TCS's reviewed NQT drive is closed. Degree/batch eligibility and office allocation require checking for each drive; no program is automatically approved. MNC fresher matching requires technical-role and early-career evidence. Established startup matching can also qualify through at least two configured stack skills. One- and two-year minimums are marked as stretch roles against six months of full-time experience; internships are separate.

SmartRecruiters sources paginate up to 1,000 India listings per employer and fetch complete descriptions for technical titles without explicit seniority. Counts represent these imported target roles, not every vacancy at the employer. Career-page sources check only explicitly configured vacancy URLs; missing descriptions fail the source rather than generating a job. An Indian office location without a published arrangement still requires manual hybrid/onsite confirmation. Unpublished pay is never represented as meeting the salary floor.

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
