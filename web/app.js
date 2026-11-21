// WRANGLER // Autonomous Stealth Job Hunter - Neo-Retro Dashboard Controller

let API_BASE = localStorage.getItem("wrangler_backend_url");
if (!API_BASE) {
  const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  API_BASE = isLocal ? window.location.origin : "http://localhost:8000";
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

  // Auto-update full name preview when typing in First, Middle, or Last name
  ['profFirstName', 'profMiddleName', 'profLastName'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', updateFullNamePreview);
  });
});

function getApiUrl(path) {
  return `${API_BASE.replace(/\/$/, '')}${path}`;
}

// Tab Switching
function switchTab(tab) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll(".tab-btn").forEach(el => {
    el.classList.remove("bg-[#00ff88]", "text-black", "border-black");
    el.classList.add("bg-[#12151e]", "text-slate-300", "border-[#262c3e]");
  });

  const activeContent = document.getElementById(`tab${tab.charAt(0).toUpperCase() + tab.slice(1)}`);
  const activeBtn = document.getElementById(`tabBtn${tab.charAt(0).toUpperCase() + tab.slice(1)}`);

  if (activeContent) activeContent.classList.remove("hidden");
  if (activeBtn) {
    activeBtn.classList.remove("bg-[#12151e]", "text-slate-300", "border-[#262c3e]");
    activeBtn.classList.add("bg-[#00ff88]", "text-black", "border-black");
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
    console.warn("WebSocket link error:", e);
  }
}

function appendTerminalLog(message, level = "info") {
  const body = document.getElementById("terminalBody");
  if (!body) return;

  const line = document.createElement("div");
  const time = new Date().toLocaleTimeString();

  let color = "text-slate-300";
  let prefix = "[SYS]";
  if (level === "success") { color = "text-[#00ff88] font-bold"; prefix = "[OK ]"; }
  if (level === "warning") { color = "text-amber-400 font-bold"; prefix = "[WRN]"; }
  if (level === "error") { color = "text-[#ff2a6d] font-bold"; prefix = "[ERR]"; }

  line.className = `flex items-start gap-2 ${color}`;
  line.innerHTML = `<span class="text-slate-600 select-none">[${time}] ${prefix}</span> <span>${escapeHtml(message)}</span>`;

  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function clearTerminal() {
  const body = document.getElementById("terminalBody");
  if (body) {
    body.innerHTML = `<div class="text-[#00ff88] font-bold">// TERMINAL BUFFER CLEARED</div>`;
  }
}

// Status, VU Meter & KPIs
async function fetchStatus() {
  try {
    const res = await fetch(getApiUrl("/api/status"));
    if (!res.ok) throw new Error("Status unreachable");
    const data = await res.json();

    // Chrome CDP Hardware Badge
    const chromeBadge = document.getElementById("chromeBadge");
    if (data.chrome_connected) {
      chromeBadge.className = "flex items-center gap-2 px-3 py-1.5 bg-[#171a24] border-2 border-[#00ff88] text-xs font-mono font-bold text-[#00ff88] shadow-[2px_2px_0px_#000]";
      chromeBadge.innerHTML = `<span class="w-2.5 h-2.5 rounded-full bg-[#00ff88]"></span><span>CDP:9222 [ONLINE]</span>`;
    } else {
      chromeBadge.className = "flex items-center gap-2 px-3 py-1.5 bg-[#171a24] border-2 border-[#ff2a6d] text-xs font-mono font-bold text-[#ff2a6d] shadow-[2px_2px_0px_#000]";
      chromeBadge.innerHTML = `<span class="w-2.5 h-2.5 rounded-full bg-[#ff2a6d] animate-pulse"></span><span>CDP:9222 [OFFLINE]</span>`;
    }

    // Agent Hardware Badge
    const agentBadge = document.getElementById("agentBadge");
    const btnStartCopilot = document.getElementById("btnStartCopilot");
    const btnStartBatch = document.getElementById("btnStartBatch");
    const btnStop = document.getElementById("btnStop");

    if (data.is_running) {
      agentBadge.className = "flex items-center gap-2 px-3 py-1.5 bg-[#171a24] border-2 border-[#00e5ff] text-xs font-mono font-bold text-[#00e5ff] shadow-[2px_2px_0px_#000]";
      agentBadge.innerHTML = `<span class="w-2.5 h-2.5 rounded-full bg-[#00e5ff] animate-ping"></span><span>CORE: [${data.current_mode.toUpperCase()}]</span>`;
      btnStartCopilot.disabled = true;
      btnStartBatch.disabled = true;
      btnStop.disabled = false;
    } else {
      agentBadge.className = "flex items-center gap-2 px-3 py-1.5 bg-[#171a24] border-2 border-[#2a3044] text-xs font-mono font-bold text-slate-400 shadow-[2px_2px_0px_#000]";
      agentBadge.innerHTML = `<span class="w-2.5 h-2.5 rounded-full bg-slate-500"></span><span>CORE: [IDLE]</span>`;
      btnStartCopilot.disabled = false;
      btnStartBatch.disabled = false;
      btnStop.disabled = true;
    }

    // Numeric Counters
    const stats = data.stats || {};
    const today = stats.today_count || 0;
    const maxDaily = data.limits?.max_daily_applications || 35;
    document.getElementById("statTodayCount").textContent = today;
    document.getElementById("statMaxDaily").textContent = `/ ${maxDaily} TARGET`;
    document.getElementById("statTotalCount").textContent = stats.total_processed || 0;
    document.getElementById("statCacheCount").textContent = stats.cached_qas || 0;

    // Segmented VU Meter (10 discrete analog blocks)
    const activeBlocks = Math.min(10, Math.ceil((today / maxDaily) * 10));
    for (let i = 1; i <= 10; i++) {
      const vu = document.getElementById(`vu${i}`);
      if (!vu) continue;
      if (i <= activeBlocks) {
        vu.className = i > 8 ? "h-full flex-1 bg-[#ff2a6d]" : (i > 6 ? "h-full flex-1 bg-amber-400" : "h-full flex-1 bg-[#00ff88]");
      } else {
        vu.className = "h-full flex-1 bg-[#1a202c]";
      }
    }

  } catch (err) {
    const agentBadge = document.getElementById("agentBadge");
    if (agentBadge) {
      agentBadge.className = "flex items-center gap-2 px-3 py-1.5 bg-[#171a24] border-2 border-[#ff2a6d] text-xs font-mono font-bold text-[#ff2a6d] shadow-[2px_2px_0px_#000]";
      agentBadge.innerHTML = `<span class="w-2.5 h-2.5 rounded-full bg-[#ff2a6d]"></span><span>BACKEND: OFFLINE</span>`;
    }
  }
}

// Applications Feed with Industrial Badges
async function fetchApplications() {
  try {
    const res = await fetch(getApiUrl("/api/applications?limit=25"));
    if (!res.ok) return;
    const apps = await res.json();
    const container = document.getElementById("applicationsList");

    if (!apps || apps.length === 0) {
      container.innerHTML = `<div class="p-8 text-center text-slate-500 text-xs font-mono">// NO JOBS RECORDED YET. START CO-PILOT OR BATCH HUNT.</div>`;
      return;
    }

    container.innerHTML = apps.map(app => {
      let statusBadge = "bg-[#171b26] text-slate-400 border border-slate-700";
      if (app.status.includes("SUBMITTED")) statusBadge = "bg-[#00ff88]/15 text-[#00ff88] border-2 border-[#00ff88]";
      if (app.status.includes("PENDING")) statusBadge = "bg-amber-400/15 text-amber-300 border-2 border-amber-400";

      return `
        <div class="p-3 bg-[#0d1017] hover:bg-[#121622] transition-colors border-2 border-[#1c2233] mb-2 flex items-center justify-between gap-4 font-mono">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="font-bold text-xs text-white truncate">[${escapeHtml(app.platform.toUpperCase())}] ${escapeHtml(app.job_title)}</span>
            </div>
            <div class="text-[11px] text-slate-400 truncate mt-1">
              🏢 ${escapeHtml(app.company_name)} &bull; <span class="text-slate-500">${app.created_at ? app.created_at.slice(0, 16) : ''}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-[10px] font-bold px-2.5 py-1 ${statusBadge}">[${escapeHtml(app.status)}]</span>
            ${app.job_url ? `<a href="${app.job_url}" target="_blank" class="p-1 bg-[#171b26] text-slate-400 hover:text-white border border-[#2a3044]"><i data-lucide="external-link" class="w-3.5 h-3.5"></i></a>` : ''}
          </div>
        </div>
      `;
    }).join("");

    lucide.createIcons();
  } catch (err) {
    console.warn("Error fetching applications:", err);
  }
}

// Commands & Actions
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
    alert("Connection error: " + err.message);
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
    alert("Batch error: " + err.message);
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
  statusEl.textContent = "// EXTRACTING CANDIDATE SPECS VIA MULTIMODAL AI...";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(getApiUrl("/api/resume/upload"), {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      let errorMsg = `HTTP_${res.status}`;
      try {
        const errJson = await res.json();
        errorMsg = errJson.message || errorMsg;
      } catch {
        const errText = await res.text();
        if (errText) errorMsg = errText;
      }
      throw new Error(`${errorMsg}. Verify local agent is running on ${API_BASE}`);
    }

    const data = await res.json();
    if (data.status === "ok") {
      statusEl.textContent = "⚡ RESUME PARSED & SYNCED TO DISK!";
      fetchProfile();
      fetchStatus();
    } else {
      statusEl.textContent = "UPLOAD FAILED.";
    }
  } catch (err) {
    statusEl.textContent = "ERR: " + err.message;
  }
}

// Profile Dossier (First, Middle, Last Name Handling)
function updateFullNamePreview() {
  const fn = document.getElementById("profFirstName").value.trim();
  const mn = document.getElementById("profMiddleName").value.trim();
  const ln = document.getElementById("profLastName").value.trim();
  const badge = document.getElementById("fullNamePreviewBadge");
  if (badge) {
    const computed = [fn, mn, ln].filter(Boolean).join(" ");
    badge.textContent = `ID: ${computed || "UNNAMED CANDIDATE"}`;
  }
}

async function fetchProfile() {
  try {
    const res = await fetch(getApiUrl("/api/profile"));
    if (!res.ok) return;
    currentProfile = await res.json();

    const p = currentProfile.personal || {};
    const c = currentProfile.career_details || {};
    const s = currentProfile.socials || {};

    // First, Middle, Last Name handling
    document.getElementById("profFirstName").value = p.first_name || "";
    document.getElementById("profMiddleName").value = p.middle_name || "";
    document.getElementById("profLastName").value = p.last_name || "";
    updateFullNamePreview();

    document.getElementById("profEmail").value = p.email || "";
    document.getElementById("profPhone").value = p.phone || "";
    document.getElementById("profLocation").value = `${p.city || ""}, ${p.country || ""}`;
    document.getElementById("profNotice").value = c.current_notice_period_days || 15;
    document.getElementById("profExpectedCTC").value = c.expected_ctc_inr || 1600000;
    document.getElementById("profLinkedIn").value = s.linkedin || "";
    document.getElementById("profGitHub").value = s.github || "";
  } catch (err) {}
}

async function saveProfile() {
  currentProfile.personal = currentProfile.personal || {};
  currentProfile.career_details = currentProfile.career_details || {};
  currentProfile.socials = currentProfile.socials || {};

  const fn = document.getElementById("profFirstName").value.trim();
  const mn = document.getElementById("profMiddleName").value.trim();
  const ln = document.getElementById("profLastName").value.trim();

  currentProfile.personal.first_name = fn;
  currentProfile.personal.middle_name = mn;
  currentProfile.personal.last_name = ln;
  currentProfile.personal.full_name = [fn, mn, ln].filter(Boolean).join(" ");

  currentProfile.personal.email = document.getElementById("profEmail").value.trim();
  currentProfile.personal.phone = document.getElementById("profPhone").value.trim();
  currentProfile.career_details.current_notice_period_days = parseInt(document.getElementById("profNotice").value) || 15;
  currentProfile.career_details.expected_ctc_inr = parseInt(document.getElementById("profExpectedCTC").value) || 1600000;
  currentProfile.socials.linkedin = document.getElementById("profLinkedIn").value.trim();
  currentProfile.socials.github = document.getElementById("profGitHub").value.trim();

  try {
    const res = await fetch(getApiUrl("/api/profile"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentProfile)
    });
    if (res.ok) {
      alert("✅ Dossier specs successfully saved to disk!");
      updateFullNamePreview();
    }
  } catch (err) {
    alert("Save error: " + err.message);
  }
}

// Settings & Guardrails
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

  const comps = document.getElementById("settBlacklistCompanies").value.split(",").map(s => s.trim()).filter(Boolean);
  const titles = document.getElementById("settBlacklistTitles").value.split(",").map(s => s.trim()).filter(Boolean);

  currentSettings.filters.blacklist_companies = comps;
  currentSettings.filters.blacklist_title_keywords = titles;

  try {
    const res = await fetch(getApiUrl("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentSettings)
    });
    if (res.ok) alert("✅ Guardrail parameters updated!");
  } catch (err) {
    alert("Save error: " + err.message);
  }
}

// Hardware Link Modal
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
    localStorage.setItem("wrangler_backend_url", url);
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
