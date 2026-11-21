"""
Rich Terminal Dashboard and Formatter for the Job Applying Agent.
"""

from typing import Dict, Any, List
from core.storage import ApplicationStore


class Dashboard:
    @staticmethod
    def print_banner():
        banner = """
================================================================================
   🎯 WRANGLER // STEALTH JOB APPLYING AGENT (LandOffer & Auto-Apply Architecture)
   Modeled after undetectable Chrome CDP profile automation + Dual Free AI
================================================================================
"""
        print(banner)

    @staticmethod
    def print_status(profile: Dict[str, Any], settings: Dict[str, Any], storage: ApplicationStore):
        stats = storage.get_stats()
        today = stats.get("today_count", 0)
        max_daily = settings.get("limits", {}).get("max_daily_applications", 35)
        name = profile.get("personal", {}).get("full_name", "Candidate")
        target_roles = ", ".join(profile.get("career_details", {}).get("target_roles", []))
        mode = settings.get("app", {}).get("mode", "copilot").upper()

        print("-" * 80)
        print(f"👤 Candidate:      {name}")
        print(f"🎯 Target Roles:   {target_roles}")
        print(f"⚙️ Operating Mode: {mode} (LandOffer Review vs Overnight Batch)")
        print(f"📊 Today's Quota:  {today} / {max_daily} applications submitted")
        print(f"💾 Q&A Cache:      {stats.get('cached_qas', 0)} answers cached locally (0-token hits)")
        print("-" * 80)

    @staticmethod
    def print_recent_table(storage: ApplicationStore):
        recent = storage.get_recent_applications(limit=8)
        if not recent:
            print("\nℹ️ No applications logged yet. Start a copilot or search run!\n")
            return

        print("\n📋 RECENT APPLICATION HISTORY:")
        print(f"{'Platform':<12} | {'Job Title':<28} | {'Company':<18} | {'Status':<20} | {'Time'}")
        print("-" * 95)
        for app in recent:
            status = app['status']
            badge = "🟢 " if "SUBMITTED" in status else ("🟡 " if "PENDING" in status else "⚪ ")
            time_str = app['created_at'][:16] if app.get('created_at') else ""
            print(f"{app['platform']:<12} | {app['job_title'][:26]:<28} | {app['company_name'][:16]:<18} | {badge + status[:17]:<20} | {time_str}")
        print("-" * 95 + "\n")
