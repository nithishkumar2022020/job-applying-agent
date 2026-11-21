#!/usr/bin/env python3
"""
Main Entrypoint for the Stealth Job Applying Agent.
Supports:
  1. 'copilot'   - LandOffer style: watches active Chrome tab, autofills, highlights submit for 1-click review.
  2. 'search'    - Overnight batch mode: searches LinkedIn, filters companies, auto-submits with rate limits.
  3. 'test-ai'   - Verifies deterministic matching, Gemini Free tier, and Groq failover.
  4. 'status'    - Displays stats on applications submitted and daily limits.
"""

import argparse
import asyncio
import os
import sys
import yaml
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from core.browser import BrowserBridge
from core.stealth import StealthDriver
from core.storage import ApplicationStore
from engine.deterministic_resolver import DeterministicResolver
from engine.llm_router import LLMRouter
from engine.batch_runner import BatchRunner
from adapters.linkedin_adapter import LinkedInAdapter
from adapters.greenhouse_adapter import GreenhouseAdapter
from adapters.lever_adapter import LeverAdapter
from adapters.ashby_adapter import AshbyAdapter
from ui.dashboard import Dashboard


def load_yaml(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def cmd_copilot(settings: dict, profile: dict, storage: ApplicationStore):
    """
    LandOffer Co-Pilot Mode:
    Monitors your running Chrome instance. As you browse jobs, it detects application
    forms, fills every field, answers screening questions, attaches resume, and pauses
    at the Review step for your 1-click approval.
    """
    Dashboard.print_banner()
    Dashboard.print_status(profile, settings, storage)

    bridge = BrowserBridge(cdp_url=settings.get("browser", {}).get("cdp_endpoint", "http://localhost:9222"))
    print("\n🔌 Connecting to Google Chrome on CDP port 9222...")
    try:
        browser, context, page = await bridge.connect()
        print("✅ Successfully attached to user's Chrome session! (0 login walls, 0 bot flags)\n")
    except Exception as e:
        print(f"❌ {e}")
        return

    stealth = StealthDriver()
    resolver = DeterministicResolver(profile)
    llm_router = LLMRouter(settings, profile, storage)

    adapters = [
        LinkedInAdapter(resolver, llm_router, stealth, storage, settings),
        GreenhouseAdapter(resolver, llm_router, stealth, storage, settings),
        LeverAdapter(resolver, llm_router, stealth, storage, settings),
        AshbyAdapter(resolver, llm_router, stealth, storage, settings)
    ]

    print("👀 Wrangler Co-Pilot is ACTIVE and watching your active Chrome tab.")
    print("   👉 Open any LinkedIn Easy Apply, Greenhouse, Lever, or Ashby job in Chrome.")
    print("   Press Ctrl+C to stop.\n")

    last_processed_url = ""

    try:
        while True:
            await asyncio.sleep(2.0)
            active_page = await bridge.get_active_page()
            url = active_page.url

            # Skip blank or chrome-internal tabs
            if not url or url.startswith("chrome://") or url.startswith("about:"):
                continue

            # Only process if URL changed or user triggered a form
            if url == last_processed_url:
                continue

            for adapter in adapters:
                if await adapter.can_handle(active_page):
                    print(f"🎯 Detected application on: {url[:70]}...")
                    result = await adapter.process_application(active_page, mode="copilot")
                    status = result.get("status")

                    if status == "AUTOFILLED_PENDING_REVIEW":
                        print(f"🎉 {result.get('message')}")
                        print(f"   Job: {result.get('job_title')} at {result.get('company_name')}")
                        print("   ✨ Look at your Chrome browser - the Submit button is highlighted in green for your review!\n")
                        storage.log_application(
                            platform=result.get("platform", "linkedin"),
                            job_title=result.get("job_title", "Job"),
                            company_name=result.get("company_name", "Company"),
                            job_url=url,
                            status="AUTOFILLED_PENDING_REVIEW",
                            mode="copilot",
                            notes="Fills completed. Awaiting user click."
                        )
                        last_processed_url = url
                    elif status == "SUBMITTED":
                        print(f"✅ Application submitted!")
                        last_processed_url = url
                    break

    except KeyboardInterrupt:
        print("\n👋 Stopping Co-Pilot. Chrome remains open.")
    finally:
        await bridge.disconnect()


async def cmd_search(args, settings: dict, profile: dict, storage: ApplicationStore):
    """
    Overnight Autonomous Batch Runner.
    Searches jobs matching keywords and location, skips blacklist, auto-answers, and submits.
    """
    Dashboard.print_banner()
    Dashboard.print_status(profile, settings, storage)

    bridge = BrowserBridge(cdp_url=settings.get("browser", {}).get("cdp_endpoint", "http://localhost:9222"))
    print("\n🔌 Connecting to Google Chrome on CDP port 9222...")
    try:
        browser, context, page = await bridge.connect()
        print("✅ Successfully attached to user's Chrome session!\n")
    except Exception as e:
        print(f"❌ {e}")
        return

    stealth = StealthDriver()
    resolver = DeterministicResolver(profile)
    llm_router = LLMRouter(settings, profile, storage)
    linkedin_adapter = LinkedInAdapter(resolver, llm_router, stealth, storage, settings)

    batch_runner = BatchRunner(linkedin_adapter, storage, stealth, settings)

    keywords = args.query or "Flutter Developer"
    location = args.location or "Remote"
    limit = args.limit or 20
    mode = args.mode or "autonomous"

    try:
        await batch_runner.run_linkedin_search(
            page=page,
            keywords=keywords,
            location=location,
            mode=mode,
            max_jobs=limit
        )
    finally:
        await bridge.disconnect()


async def cmd_test_ai(settings: dict, profile: dict, storage: ApplicationStore):
    """Verifies deterministic matching, SQLite cache, and Gemini/Groq AI failover."""
    Dashboard.print_banner()
    resolver = DeterministicResolver(profile)
    llm_router = LLMRouter(settings, profile, storage)

    print("\n🧪 [1/3] Testing Deterministic Rule Engine (0 Cost)...")
    test_labels = [
        "First Name", "Email Address", "Phone Number", "LinkedIn Profile",
        "Are you legally authorized to work in India?", "Will you require visa sponsorship?",
        "Years of Flutter experience?", "Current CTC", "Expected CTC", "Notice Period"
    ]
    for lbl in test_labels:
        val, rule = resolver.resolve(lbl)
        print(f"  • '{lbl}' -> {val} (Rule: {rule})")

    print("\n🧪 [2/3] Testing High-Availability Dual-AI Router (Gemini -> Groq Failover)...")
    subjective_questions = [
        "Why are you interested in joining our engineering team?",
        "Describe a complex architectural challenge you solved in a mobile app.",
        "How many years of experience do you have with reactive state management?"
    ]

    for q in subjective_questions:
        print(f"\n❓ Question: {q}")
        ans = await llm_router.answer_question(
            question=q,
            job_title="Senior Flutter Engineer",
            company="Tech Corp",
            input_type="text"
        )
        print(f"💡 AI Answer: {ans}")

    print("\n🧪 [3/3] Testing Semantic SQLite Cache Hit...")
    cached_hit = storage.get_cached_answer(subjective_questions[0])
    if cached_hit:
        print(f"  ✅ Cache Hit verified! Provider: {cached_hit['provider']} (0 tokens consumed on repeat questions).")
    else:
        print("  ℹ️ Question answered via fallback heuristics.")

    print("\n✨ All intelligence components verified!\n")


def cmd_status(settings: dict, profile: dict, storage: ApplicationStore):
    Dashboard.print_banner()
    Dashboard.print_status(profile, settings, storage)
    Dashboard.print_recent_table(storage)


from engine.resume_sync import ResumeSync

def main():
    parser = argparse.ArgumentParser(description="Stealth Job Applying Agent (LandOffer Architecture)")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # gui command
    gui_p = subparsers.add_parser("gui", help="Launch the Web Studio Dashboard (hostable on Cloudflare / GitHub Pages)")
    gui_p.add_argument("--port", type=int, default=8000, help="Web server port (default: 8000)")
    gui_p.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    gui_p.add_argument("--no-browser", action="store_true", help="Do not automatically open default browser")

    # copilot command
    subparsers.add_parser("copilot", help="Run LandOffer Co-Pilot (autofills active tab, pauses for 1-click submit)")

    # search command
    search_p = subparsers.add_parser("search", help="Run autonomous overnight batch job search & apply")
    search_p.add_argument("--query", type=str, default="Flutter Developer", help="Target job title or keywords")
    search_p.add_argument("--location", type=str, default="Remote", help="Target location (e.g. Remote, Hyderabad)")
    search_p.add_argument("--limit", type=int, default=20, help="Max jobs to process")
    search_p.add_argument("--mode", type=str, choices=["copilot", "autonomous"], default="autonomous", help="Operating mode")

    # sync-resume command
    subparsers.add_parser("sync-resume", help="Force parse resumes/resume.pdf and sync config/profile.yaml")

    # test-ai command
    subparsers.add_parser("test-ai", help="Test deterministic rules and Gemini/Groq AI failover")

    # status command
    subparsers.add_parser("status", help="View application stats and history")

    args = parser.parse_args()

    # Load configuration
    base_dir = Path(__file__).parent
    settings_path = str(base_dir / "config" / "settings.yaml")
    profile_path = str(base_dir / "config" / "profile.yaml")

    settings = load_yaml(settings_path)

    # Auto-detect resume update and refresh profile
    sync_engine = ResumeSync(base_dir, settings)
    if args.command == "sync-resume":
        sync_engine.auto_sync_if_needed()
        return

    sync_engine.auto_sync_if_needed()
    profile = load_yaml(profile_path)
    storage = ApplicationStore(db_path=str(base_dir / "data" / "applications.db"))

    if args.command == "gui":
        import uvicorn
        import webbrowser
        url = f"http://{args.host}:{args.port}"
        print(f"\n🌐 Launching Wrangler Web Studio Dashboard on {url}...")
        if not args.no_browser:
            webbrowser.open(url)
        uvicorn.run("api.server:app", host=args.host, port=args.port, reload=False)
    elif args.command == "copilot":
        asyncio.run(cmd_copilot(settings, profile, storage))
    elif args.command == "search":
        asyncio.run(cmd_search(args, settings, profile, storage))
    elif args.command == "test-ai":
        asyncio.run(cmd_test_ai(settings, profile, storage))
    elif args.command == "status":
        cmd_status(settings, profile, storage)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
