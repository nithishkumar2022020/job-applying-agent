// LandOffer Stealth Agent - Web Dashboard Frontend Controller

let API_BASE = localStorage.getItem("landoffer_backend_url") || window.location.origin;
if (API_BASE.startsWith("http://127.0.0.1") || API_BASE.startsWith("http://localhost")) {
  // Good local address
} else if (window.location.protocol === "file:" || window.location.hostname.includes("github.io") || window.location.hostname.includes("pages.dev")) {
  API_BASE = localStorage.getItem("landoffer_backend_url") || "http://localhost:8000";
}

let ws = null;
let currentProfile = {};
let currentSettings = {};

document.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  fetchStatus();
  fetchProfile();
  fetchSettings();
  fetchApplications();
  setInterval(fetchStatus, 3000);
});

function getApiUrl(path) {
  return `${API_BASE.replace(/\/$/, '')}${path}`;
}

// Tab Switching
function switchTab(tab) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll(".tab-btn").forEach(el => {
    el.classList.remove("text-emerald-400", "border-emerald-400");
    el.classList.add("text-slate-400", "border-transparent");
  });

  const activeContent = document.getElementById(`tab${tab.charAt(0).toUpperCase() + tab.slice(1)}`);
  const activeBtn = document.getElementById(`tabBtn${tab.charAt(0).toUpperCase() + tab.slice(1)}`);

  if (activeContent) activeContent.classList.remove("hidden");
  if (activeBtn) {
    activeBtn.classList.remove("text-slate-400", "border-transparent");
    activeBtn.classList.add("text-emerald-400", "border-emerald-400");
  }
}

// WebSocket Live Telemetry
function initWebSocket() {
  try {
    const wsUrl = API_BASE.replace(/^http/, "ws") + "/ws/logs";
    ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      appendTerminalLog(data.message, data.level);
    };

    ws.onclose = () => {
      setTimeout(initWebSocket, 4000);
    };
  } catch (e) {
    console.warn("WebSocket init error:", e);
  }
}

function appendTerminalLog(message, level = "info") {
  const body = document.getElementById("terminalBody");
  if (!body) return;

  const line = document.createElement("div");
  const time = new Date().toLocaleTimeString();

  let color = "text-slate-300";
  if (level === "success") color = "text-emerald-400";
  if (level === "warning") color = "text-amber-400";
  if (level === "error") color = "text-rose-400";

  line.className = `flex items-start gap-2 ${color}`;
  line.innerHTML = `<span class="text-slate-600 select-none">[${time}]</span> <span>${escapeHtml(message)}</span>`;

  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function clearTerminal() {
  const body = document.getElementById("terminalBody");
  if (body) body.innerHTML = "";
}

// Status & KPIs
async function fetchStatus() {
  try {
    const res = await fetch(getApiUrl("/api/status"));
    if (!res.ok) throw new Error("Status failed");
    const data = await res.json();

    // Badges
    const chromeBadge = document.getElementById("chromeBadge");
    if (data.chrome_connected) {
      chromeBadge.className = "flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
      chromeBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-500"></span><span>Chrome: Port 9222 Active</span>`;
    } else {
      chromeBadge.className = "flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20";
      chromeBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span><span>Chrome: Disconnected</span>`;
    }

    const agentBadge = document.getElementById("agentBadge");
    const btnStartCopilot = document.getElementById("btnStartCopilot");
    const btnStartBatch = document.getElementById("btnStartBatch");
    const btnStop = document.getElementById("btnStop");
    const activeActionLabel = document.getElementById("activeActionLabel");

    if (data.is_running) {
      agentBadge.className = "flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
      agentBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span><span>Agent: ${data.current_mode.toUpperCase()}</span>`;
      btnStartCopilot.disabled = true;
      btnStartBatch.disabled = true;
      btnStop.disabled = false;
      activeActionLabel.textContent = `Running: ${data.current_mode.toUpperCase()}`;
      activeActionLabel.className = "text-xs font-normal px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300";
    } else {
      agentBadge.className = "flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700";
      agentBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-slate-500"></span><span>Agent: IDLE</span>`;
      btnStartCopilot.disabled = false;
      btnStartBatch.disabled = false;
      btnStop.disabled = true;
      activeActionLabel.textContent = "Idle";
      activeActionLabel.className = "text-xs font-normal px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400";
    }

    // Counters
    const stats = data.stats || {};
    const today = stats.today_count || 0;
    const maxDaily = data.limits?.max_daily_applications || 35;
    document.getElementById("statTodayCount").textContent = today;
    document.getElementById("statMaxDaily").textContent = `/ ${maxDaily} cap`;
    document.getElementById("statTotalCount").textContent = stats.total_processed || 0;
    document.getElementById("statCacheCount").textContent = stats.cached_qas || 0;

    const pct = Math.min(100, Math.round((today / maxDaily) * 100));
    document.getElementById("statProgressBar").style.width = `${pct}%`;

  } catch (err) {
    // Backend offline
    const agentBadge = document.getElementById("agentBadge");
    agentBadge.className = "flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-500 border border-slate-700";
    agentBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-slate-600"></span><span>Backend: Offline</span>`;
  }
}

// Applications Feed
async function fetchApplications() {
  try {
    const res = await fetch(getApiUrl("/api/applications?limit=20"));
    if (!res.ok) return;
    const apps = await res.json();
    const container = document.getElementById("applicationsList");

    if (!apps || apps.length === 0) {
      container.innerHTML = `<div class="p-8 text-center text-slate-500 text-sm">No applications recorded yet. Start a run!</div>`;
      return;
    }

    container.innerHTML = apps.map(app => {
      let badge = "bg-slate-800 text-slate-400";
      if (app.status.includes("SUBMITTED")) badge = "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
      if (app.status.includes("PENDING")) badge = "bg-amber-500/20 text-amber-300 border border-amber-500/30";

      return `
        <div class="p-4 hover:bg-white/[0.02] transition-colors flex items-center justify-between gap-4">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="font-semibold text-sm text-white truncate">${escapeHtml(app.job_title)}</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded uppercase font-mono bg-white/5 text-slate-400">${escapeHtml(app.platform)}</span>
            </div>
            <div class="text-xs text-slate-400 truncate mt-0.5">${escapeHtml(app.company_name)} &bull; <span class="font-mono text-slate-500">${app.created_at ? app.created_at.slice(0, 16) : ''}</span></div>
          </div>
          <div class="flex items-center gap-3">
            <span class="text-xs font-medium px-2.5 py-1 rounded-full ${badge}">${escapeHtml(app.status)}</span>
            ${app.job_url ? `<a href="${app.job_url}" target="_blank" class="text-slate-500 hover:text-white"><i data-lucide="external-link" class="w-4 h-4"></i></a>` : ''}
          </div>
        </div>
      `;
    }).join("");

    lucide.createIcons();
  } catch (err) {
    console.warn("Failed fetching applications:", err);
  }
}

// Run Actions
async function startCopilot() {
  try {
    const res = await fetch(getApiUrl("/api/run/copilot"), { method: "POST" });
    const data = await res.json();
    if (data.status === "ok") {
      fetchStatus();
    } else {
      alert(data.message);
    }
  } catch (err) {
    alert("Could not reach backend: " + err.message);
  }
}

function openBatchModal() {
  document.getElementById("batchModal").classList.remove("hidden");
  document.getElementById("batchModal").classList.add("flex");
}

function closeBatchModal() {
  document.getElementById("batchModal").classList.add("hidden");
  document.getElementById("batchModal").classList.remove("flex");
}

async function confirmStartBatch() {
  const query = document.getElementById("batchQuery").value;
  const location = document.getElementById("batchLocation").value;
  const limit = parseInt(document.getElementById("batchLimit").value) || 20;

  try {
    const res = await fetch(getApiUrl("/api/run/search"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, location, limit, mode: "autonomous" })
    });
    const data = await res.json();
    closeBatchModal();
    if (data.status === "ok") {
      fetchStatus();
    } else {
      alert(data.message);
    }
  } catch (err) {
    alert("Failed starting batch: " + err.message);
  }
}

async function stopAgent() {
  try {
    await fetch(getApiUrl("/api/stop"), { method: "POST" });
    fetchStatus();
  } catch (err) {
    alert("Error stopping agent: " + err.message);
  }
}

// Resume Upload & Auto-Sync
async function handleResumeUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const statusEl = document.getElementById("uploadStatusText");
  statusEl.textContent = "Uploading & extracting via AI...";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(getApiUrl("/api/resume/upload"), {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (data.status === "ok") {
      statusEl.textContent = "✨ Auto-synced from latest resume!";
      fetchProfile();
      fetchStatus();
    } else {
      statusEl.textContent = "Upload failed.";
    }
  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
  }
}

// Profile & Settings
async function fetchProfile() {
  try {
    const res = await fetch(getApiUrl("/api/profile"));
    if (!res.ok) return;
    currentProfile = await res.json();

    const p = currentProfile.personal || {};
    const c = currentProfile.career_details || {};
    const s = currentProfile.socials || {};

    document.getElementById("profFullName").value = p.full_name || "";
    document.getElementById("profEmail").value = p.email || "";
    document.getElementById("profPhone").value = p.phone || "";
    document.getElementById("profLocation").value = `${p.city || ""}, ${p.country || ""}`;
    document.getElementById("profNotice").value = c.current_notice_period_days || 15;
    document.getElementById("profExpectedCTC").value = c.expected_ctc_inr || 1600000;
    document.getElementById("profLinkedIn").value = s.linkedin || "";
  } catch (err) {}
}

async function saveProfile() {
  currentProfile.personal = currentProfile.personal || {};
  currentProfile.career_details = currentProfile.career_details || {};
  currentProfile.socials = currentProfile.socials || {};

  currentProfile.personal.full_name = document.getElementById("profFullName").value;
  currentProfile.personal.email = document.getElementById("profEmail").value;
  currentProfile.personal.phone = document.getElementById("profPhone").value;
  currentProfile.career_details.current_notice_period_days = parseInt(document.getElementById("profNotice").value) || 15;
  currentProfile.career_details.expected_ctc_inr = parseInt(document.getElementById("profExpectedCTC").value) || 1600000;
  currentProfile.socials.linkedin = document.getElementById("profLinkedIn").value;

  try {
    const res = await fetch(getApiUrl("/api/profile"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentProfile)
    });
    if (res.ok) alert("Profile saved successfully!");
  } catch (err) {
    alert("Failed saving profile: " + err.message);
  }
}

async function fetchSettings() {
  try {
    const res = await fetch(getApiUrl("/api/settings"));
    if (!res.ok) return;
    currentSettings = await res.json();

    const l = currentSettings.limits || {};
    const f = currentSettings.filters || {};

    document.getElementById("settMaxDaily").value = l.max_daily_applications || 35;
    document.getElementById("settMinDelay").value = l.pause_between_applications_min_sec || 14;
    document.getElementById("settMaxDelay").value = l.pause_between_applications_max_sec || 32;
    document.getElementById("settBlacklistCompanies").value = (f.blacklist_companies || []).join(", ");
    document.getElementById("settBlacklistTitles").value = (f.blacklist_title_keywords || []).join(", ");
  } catch (err) {}
}

async function saveSettings() {
  currentSettings.limits = currentSettings.limits || {};
  currentSettings.filters = currentSettings.filters || {};

  currentSettings.limits.max_daily_applications = parseInt(document.getElementById("settMaxDaily").value) || 35;
  currentSettings.limits.pause_between_applications_min_sec = parseInt(document.getElementById("settMinDelay").value) || 14;
  currentSettings.limits.pause_between_applications_max_sec = parseInt(document.getElementById("settMaxDelay").value) || 32;

  const comps = document.getElementById("settBlacklistCompanies").value.split(",").map(s => s.strip ? s.strip() : s.trim()).filter(Boolean);
  const titles = document.getElementById("settBlacklistTitles").value.split(",").map(s => s.strip ? s.strip() : s.trim()).filter(Boolean);

  currentSettings.filters.blacklist_companies = comps;
  currentSettings.filters.blacklist_title_keywords = titles;

  try {
    const res = await fetch(getApiUrl("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentSettings)
    });
    if (res.ok) alert("Settings saved successfully!");
  } catch (err) {
    alert("Failed saving settings: " + err.message);
  }
}

// Backend Modal Configuration
function toggleBackendModal() {
  const modal = document.getElementById("backendModal");
  modal.classList.toggle("hidden");
  modal.classList.toggle("flex");
  document.getElementById("backendUrlInput").value = API_BASE;
}

function saveBackendUrl() {
  const url = document.getElementById("backendUrlInput").value.trim();
  if (url) {
    API_BASE = url;
    localStorage.setItem("landoffer_backend_url", url);
    toggleBackendModal();
    fetchStatus();
    initWebSocket();
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
