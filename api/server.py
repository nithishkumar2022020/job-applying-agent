"""
FastAPI Server & Background Automation Controller for Web GUI.
Serves the web dashboard and provides REST + WebSocket endpoints for real-time telemetry.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yaml

base_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(base_dir))

from core.browser import BrowserBridge
from core.stealth import StealthDriver
from core.storage import ApplicationStore
from engine.deterministic_resolver import DeterministicResolver
from engine.llm_router import LLMRouter
from engine.batch_runner import BatchRunner
from engine.resume_sync import ResumeSync
from adapters.linkedin_adapter import LinkedInAdapter
from adapters.naukri_adapter import NaukriAdapter
from adapters.wellfound_adapter import WellfoundAdapter
from adapters.indeed_adapter import IndeedAdapter
from adapters.glassdoor_adapter import GlassdoorAdapter
from adapters.workday_adapter import WorkdayAdapter
from adapters.greenhouse_adapter import GreenhouseAdapter
from adapters.lever_adapter import LeverAdapter
from adapters.ashby_adapter import AshbyAdapter

app = FastAPI(title="Wrangler Stealth Job Applying Agent API", version="1.0.0")

# Enable CORS for local & cloud hosting (GitHub Pages / Cloudflare Pages)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State
class AgentState:
    def __init__(self):
        self.is_running = False
        self.current_mode = "idle"
        self.active_task: Optional[asyncio.Task] = None
        self.websocket_clients = set()
        self.log_history = []

state = AgentState()
storage = ApplicationStore(db_path=str(base_dir / "data" / "applications.db"))


def load_settings() -> dict:
    with open(base_dir / "config" / "settings.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_profile() -> dict:
    with open(base_dir / "config" / "profile.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def broadcast_log(message: str, level: str = "info"):
    entry = {"message": message, "level": level, "timestamp": asyncio.get_event_loop().time()}
    state.log_history.append(entry)
    if len(state.log_history) > 200:
        state.log_history.pop(0)

    disconnected = set()
    for ws in state.websocket_clients:
        try:
            await ws.send_json(entry)
        except Exception:
            disconnected.add(ws)
    state.websocket_clients -= disconnected


@app.get("/api/status")
async def get_status():
    settings = load_settings()
    profile = load_profile()
    stats = storage.get_stats()

    # Check Chrome CDP port 9222 availability
    chrome_connected = False
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:9222/json/version")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                chrome_connected = True
    except Exception:
        chrome_connected = False

    return {
        "is_running": state.is_running,
        "current_mode": state.current_mode,
        "chrome_connected": chrome_connected,
        "stats": stats,
        "limits": settings.get("limits", {}),
        "candidate_name": profile.get("personal", {}).get("full_name", ""),
        "target_roles": profile.get("career_details", {}).get("target_roles", [])
    }


@app.get("/api/profile")
async def get_profile():
    return load_profile()


@app.post("/api/profile")
async def update_profile(updated: dict):
    profile_path = base_dir / "config" / "profile.yaml"
    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(updated, f, sort_keys=False, allow_unicode=True)
    await broadcast_log("Candidate profile successfully updated.", level="success")
    return {"status": "ok", "message": "Profile updated"}


@app.get("/api/settings")
async def get_settings():
    return load_settings()


@app.post("/api/settings")
async def update_settings(updated: dict):
    settings_path = base_dir / "config" / "settings.yaml"
    with open(settings_path, "w", encoding="utf-8") as f:
        yaml.dump(updated, f, sort_keys=False, allow_unicode=True)
    await broadcast_log("Settings updated successfully.", level="success")
    return {"status": "ok", "message": "Settings updated"}


@app.get("/api/applications")
async def get_applications(limit: int = 25):
    return storage.get_recent_applications(limit=limit)


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    resume_dest = base_dir / "resumes" / "resume.pdf"
    resume_dest.parent.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    with open(resume_dest, "wb") as f:
        f.write(contents)

    await broadcast_log(f"New resume PDF received ({len(contents)} bytes). Triggering auto-sync...", level="info")

    settings = load_settings()
    sync_engine = ResumeSync(base_dir, settings)
    synced = sync_engine.auto_sync_if_needed()

    if synced:
        await broadcast_log("Profile automatically extracted & synced from new resume!", level="success")
    else:
        await broadcast_log("Resume saved at resumes/resume.pdf.", level="info")

    return {"status": "ok", "synced": synced}


class SearchRequest(BaseModel):
    platform: str = "all"
    query: str = "Flutter Developer"
    location: str = "Remote"
    limit: int = 20
    mode: str = "autonomous"


@app.post("/api/run/copilot")
async def start_copilot(background_tasks: BackgroundTasks):
    if state.is_running:
        return {"status": "error", "message": "Agent is already running"}

    state.is_running = True
    state.current_mode = "copilot"
    background_tasks.add_task(run_copilot_loop)
    await broadcast_log("🚀 Wrangler Co-Pilot started. Watching active Chrome tabs across LinkedIn, Naukri, Wellfound, Indeed, MNCs...", level="success")
    return {"status": "ok", "mode": "copilot"}


@app.post("/api/run/search")
async def start_search(req: SearchRequest, background_tasks: BackgroundTasks):
    if state.is_running:
        return {"status": "error", "message": "Agent is already running"}

    state.is_running = True
    state.current_mode = "search"
    background_tasks.add_task(run_search_loop, req.platform, req.query, req.location, req.limit, req.mode)
    await broadcast_log(f"🚀 Batch Apply started on [{req.platform.upper()}]: '{req.query}' in '{req.location}' (Limit: {req.limit})", level="success")
    return {"status": "ok", "mode": "search"}


@app.post("/api/stop")
async def stop_agent():
    if not state.is_running:
        return {"status": "ok", "message": "Agent was not running"}

    state.is_running = False
    state.current_mode = "idle"
    if state.active_task and not state.active_task.done():
        state.active_task.cancel()

    await broadcast_log("🛑 Agent stopped by user.", level="warning")
    return {"status": "ok", "message": "Agent stopped"}


async def run_copilot_loop():
    settings = load_settings()
    profile = load_profile()
    bridge = BrowserBridge(cdp_url=settings.get("browser", {}).get("cdp_endpoint", "http://localhost:9222"))

    try:
        browser, context, page = await bridge.connect()
        await broadcast_log("Connected to Google Chrome on CDP port 9222.", level="success")
    except Exception as e:
        await broadcast_log(f"Failed to connect to Chrome: {e}", level="error")
        state.is_running = False
        state.current_mode = "idle"
        return

    stealth = StealthDriver()
    resolver = DeterministicResolver(profile)
    llm_router = LLMRouter(settings, profile, storage)

    adapters = [
        LinkedInAdapter(resolver, llm_router, stealth, storage, settings),
        NaukriAdapter(resolver, llm_router, stealth, storage, settings),
        WellfoundAdapter(resolver, llm_router, stealth, storage, settings),
        IndeedAdapter(resolver, llm_router, stealth, storage, settings),
        GlassdoorAdapter(resolver, llm_router, stealth, storage, settings),
        WorkdayAdapter(resolver, llm_router, stealth, storage, settings),
        GreenhouseAdapter(resolver, llm_router, stealth, storage, settings),
        LeverAdapter(resolver, llm_router, stealth, storage, settings),
        AshbyAdapter(resolver, llm_router, stealth, storage, settings)
    ]

    last_url = ""
    try:
        while state.is_running:
            await asyncio.sleep(2.0)
            active_page = await bridge.get_active_page()
            url = active_page.url

            if not url or url.startswith("chrome://") or url.startswith("about:"):
                continue

            if url == last_url:
                continue

            for adapter in adapters:
                if await adapter.can_handle(active_page):
                    await broadcast_log(f"Detected job application on: {url[:60]}...", level="info")
                    result = await adapter.process_application(active_page, mode="copilot")
                    status = result.get("status")

                    if status == "AUTOFILLED_PENDING_REVIEW":
                        await broadcast_log(f"🎉 Autofilled: {result.get('job_title')} at {result.get('company_name')}! Check Chrome to Submit.", level="success")
                        storage.log_application(
                            platform=result.get("platform", "linkedin"),
                            job_title=result.get("job_title", "Job"),
                            company_name=result.get("company_name", "Company"),
                            job_url=url,
                            status="AUTOFILLED_PENDING_REVIEW",
                            mode="copilot",
                            notes="Autofilled via GUI Co-Pilot"
                        )
                        last_url = url
                    elif status == "SUBMITTED":
                        await broadcast_log(f"✅ Submitted application: {result.get('job_title')}", level="success")
                        last_url = url
                    break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await broadcast_log(f"Co-Pilot error: {e}", level="error")
    finally:
        await bridge.disconnect()
        state.is_running = False
        state.current_mode = "idle"
        await broadcast_log("Co-Pilot disconnected cleanly.", level="info")


async def run_search_loop(platform: str, query: str, location: str, limit: int, mode: str):
    settings = load_settings()
    profile = load_profile()
    bridge = BrowserBridge(cdp_url=settings.get("browser", {}).get("cdp_endpoint", "http://localhost:9222"))

    try:
        browser, context, page = await bridge.connect()
        await broadcast_log(f"Connected to Chrome for Batch Search on {platform.upper()}.", level="success")
    except Exception as e:
        await broadcast_log(f"Failed to connect to Chrome: {e}", level="error")
        state.is_running = False
        state.current_mode = "idle"
        return

    stealth = StealthDriver()
    resolver = DeterministicResolver(profile)
    llm_router = LLMRouter(settings, profile, storage)

    adapters_dict = {
        "linkedin": LinkedInAdapter(resolver, llm_router, stealth, storage, settings),
        "naukri": NaukriAdapter(resolver, llm_router, stealth, storage, settings),
        "wellfound": WellfoundAdapter(resolver, llm_router, stealth, storage, settings),
        "indeed": IndeedAdapter(resolver, llm_router, stealth, storage, settings),
        "glassdoor": GlassdoorAdapter(resolver, llm_router, stealth, storage, settings),
        "workday": WorkdayAdapter(resolver, llm_router, stealth, storage, settings),
        "greenhouse": GreenhouseAdapter(resolver, llm_router, stealth, storage, settings),
        "lever": LeverAdapter(resolver, llm_router, stealth, storage, settings),
        "ashby": AshbyAdapter(resolver, llm_router, stealth, storage, settings)
    }

    batch_runner = BatchRunner(adapters_dict, storage, stealth, settings)

    try:
        await batch_runner.run_batch_search(
            page=page,
            platform=platform,
            keywords=query,
            location=location,
            mode=mode,
            max_jobs=limit
        )
        await broadcast_log(f"Batch apply run completed for {platform.upper()}.", level="success")
    except asyncio.CancelledError:
        await broadcast_log("Batch run cancelled by user.", level="warning")
    except Exception as e:
        await broadcast_log(f"Batch run error: {e}", level="error")
    finally:
        await bridge.disconnect()
        state.is_running = False
        state.current_mode = "idle"


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    state.websocket_clients.add(websocket)
    try:
        # Send history
        for entry in state.log_history[-40:]:
            await websocket.send_json(entry)
        while True:
            # Keep alive ping
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.websocket_clients.remove(websocket)


# Mount static web directory
web_dir = base_dir / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="static")
