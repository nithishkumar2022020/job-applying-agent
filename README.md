# 🎯 Stealth Job Applying Agent (LandOffer & Auto-Apply Architecture)

An undetectable, high-availability, zero-cost job application assistant designed for software engineers. Modeled after **LandOffer.ai** and the stealth browser automation framework.

---

## ⚡ Key Highlights

1. **Undetectable (No Robot Browser):** Connects to your **genuine Google Chrome instance via Chrome DevTools Protocol (CDP)** using your everyday profile. All active logins (LinkedIn, Google, Naukri, Greenhouse) and anti-bot trust scores are preserved—zero CAPTCHAs and zero login screens.
2. **Humanized Typing & Motion:** Gaussian keystroke jitter (45–120ms), punctuation micro-pauses, smooth trackpad-style scrolling, and randomized click offsets.
3. **High-Availability Zero-Cost AI Layer:**
   - **85% Deterministic Rules (0 tokens):** First/last name, phone, email, links, work auth, CTC, experience years mapped with 100% precision without making any API calls.
   - **Dual Free-Tier Failover:** Uses **Google Gemini 2.0 Flash** (15 RPM / 1M TPM free) as primary, with automatic failover to **Groq Cloud Llama 3.3 70B** (30 RPM free).
   - **Semantic SQLite Q&A Cache:** Answers to repeated screening questions are saved locally, ensuring zero redundant API calls.
4. **Dual Operating Modes:**
   - **LandOffer Co-Pilot Mode:** As you browse jobs, it detects application forms, autofills everything, attaches your resume, and **pauses with the Submit button highlighted in green** for your 1-click review.
   - **Overnight Autonomous Batch Mode:** Searches LinkedIn for matching titles, filters out blacklisted companies, steps through applications, respects daily limits (e.g., 35/day), and logs everything.
5. **Multi-Platform Support:**
   - LinkedIn Easy Apply (multi-step stepper)
   - Greenhouse ATS (`boards.greenhouse.io`)
   - Lever ATS (`jobs.lever.co`)
   - Ashby ATS (`jobs.ashbyhq.com`)

---

## 🚀 Quickstart Guide

### Step 1: Install Dependencies
Create/activate your virtual environment and install dependencies:
```bash
cd job_apply_agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Step 2: Set Free AI API Keys (Optional but Recommended)
Set your free tier API keys in your terminal or `.zshrc` / `.bashrc`:
```bash
# Get free key from https://aistudio.google.com/
export GEMINI_API_KEY="your-gemini-api-key"

# (Optional fallback) Get free key from https://console.groq.com/
export GROQ_API_KEY="your-groq-api-key"
```
*(Note: If no API keys are provided, the agent falls back to deterministic rules + smart profile heuristics!)*

### Step 3: Add Your Resume
Place your PDF resume inside the `resumes/` folder:
```bash
cp /path/to/my_resume.pdf job_apply_agent/resumes/resume.pdf
```

### Step 4: Launch Chrome with Remote Debugging
Run the launcher script to open your genuine Chrome profile with CDP enabled on port 9222:
```bash
bash scripts/launch_chrome.sh
```
Log in to LinkedIn or your target job portals in this window if not already logged in.

---

## 💻 Running the Agent

### Mode A: LandOffer Co-Pilot (Autofill & 1-Click Review)
Watches your active Chrome tab. When you navigate to any LinkedIn Easy Apply, Greenhouse, Lever, or Ashby job, it automatically fills the form and highlights the Submit button:
```bash
python main.py copilot
```

### Mode B: Overnight Autonomous Batch Mode
Searches LinkedIn for fresh jobs, filters recruiters, fills answers, and submits automatically:
```bash
python main.py search --query "Flutter Developer" --location "Remote" --limit 25
```
Or for local roles:
```bash
python main.py search --query "Mobile Engineer" --location "Hyderabad" --limit 20
```

### Check Application History & Stats
```bash
python main.py status
```

### Test Intelligence Engine & AI Failover
```bash
python main.py test-ai
```

---

## 🛠️ Configuration

Edit `config/profile.yaml` to update your personal details, target roles, experience numbers, and CTC expectations.
Edit `config/settings.yaml` to adjust daily application limits, pacing delays, and company blacklists.
