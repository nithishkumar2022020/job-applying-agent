# Job Applying Agent

A privacy-first Python CLI that discovers jobs, applies deterministic eligibility rules, scores fit, deduplicates listings, and places suitable roles in a human approval queue. It never submits an application automatically.

## Features

- Himalayas RSS, Remotive, Arbeitnow, and Jobicy connectors
- Direct Greenhouse, Lever, and Ashby employer-board connectors
- GenAI and relevant MNC fresher-role matching
- India-compatible location validation and configurable exclusions
- Salary, experience, seniority, startup-size, and URL safeguards
- SQLite history, deduplication, approval states, and HTML dashboard
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

Customize `profile.json` before discovery. The file is ignored by Git because it may contain personal preferences and a local resume path.

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
