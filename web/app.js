// Wrangler - Clean & Elegant Dashboard Controller

let API_BASE = localStorage.getItem("wrangler_backend_url");
if (!API_BASE) {
  const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  API_BASE = isLocal ? window.location.origin : "http://localhost:8000";
}

let ws = null;
let currentProfile = {};
let currentSettings = {};
let allApplications = [];
let currentStatusFilter = "ALL";

document.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  fetchStatus();
  fetchProfile();
  fetchSettings();
  fetchApplications();
  setInterval(fetchStatus, 3000);

  // Auto-sync full name preview when typing in First, Middle, or Last name
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
    console.warn("WebSocket link error:", e);
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

  line.className = `flex items-start gap-2.5 ${color}`;
  line.innerHTML = `<span class="text-slate-500 font-mono text-[11px] select-none">[${time}]</span> <span>${escapeHtml(message)}</span>`;

  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function clearTerminal() {
  const body = document.getElementById("terminalBody");
  if (body) {
    body.innerHTML = `<div class="text-slate-500 font-mono">// Log buffer cleared.</div>`;
  }
}

// Status & KPIs
async function fetchStatus() {
  try {
    const res = await fetch(getApiUrl("/api/status"));
    if (!res.ok) throw new Error("Status unreachable");
    const data = await res.json();

    // Chrome Connection Badge
    const chromeBadge = document.getElementById("chromeBadge");
    if (data.chrome_connected) {
      chromeBadge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium";
      chromeBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-500"></span><span>Chrome: Connected</span>`;
    } else {
      chromeBadge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 font-medium";
      chromeBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span><span>Chrome: Disconnected</span>`;
    }

    // Agent Running Badge
    const agentBadge = document.getElementById("agentBadge");
    const btnStartCopilot = document.getElementById("btnStartCopilot");
    const btnStartBatch = document.getElementById("btnStartBatch");
    const btnStop = document.getElementById("btnStop");
    const activeActionLabel = document.getElementById("activeActionLabel");

    if (data.is_running) {
      agentBadge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-medium";
      agentBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span><span>Agent: ${data.current_mode.toUpperCase()}</span>`;
      btnStartCopilot.disabled = true;
      btnStartBatch.disabled = true;
      btnStop.disabled = false;
      activeActionLabel.textContent = `Running: ${data.current_mode.toUpperCase()}`;
      activeActionLabel.className = "text-xs font-normal px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300";
    } else {
      agentBadge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/80 text-slate-400 border border-white/5 font-medium";
      agentBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-slate-500"></span><span>Agent: Idle</span>`;
      btnStartCopilot.disabled = false;
      btnStartBatch.disabled = false;
      btnStop.disabled = true;
      activeActionLabel.textContent = "Ready";
      activeActionLabel.className = "text-xs font-normal px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400";
    }

    // Counters
    const stats = data.stats || {};
    const today = stats.today_count || 0;
    const maxDaily = data.limits?.max_daily_applications || 35;
    document.getElementById("statTodayCount").textContent = today;
    document.getElementById("statMaxDaily").textContent = `/ ${maxDaily} limit`;
    document.getElementById("statTotalCount").textContent = stats.total_processed || 0;
    document.getElementById("statCacheCount").textContent = stats.cached_qas || 0;

    const pct = Math.min(100, Math.round((today / maxDaily) * 100));
    document.getElementById("statProgressBar").style.width = `${pct}%`;

  } catch (err) {
    const agentBadge = document.getElementById("agentBadge");
    if (agentBadge) {
      agentBadge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/80 text-rose-400 border border-rose-500/20 font-medium";
      agentBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-500"></span><span>Backend: Offline</span>`;
    }
  }
}

// Applications Tracker Table
async function fetchApplications() {
  try {
    const res = await fetch(getApiUrl("/api/applications?limit=50"));
    if (!res.ok) return;
    allApplications = await res.json();
    renderApplicationsTable();
  } catch (err) {
    console.warn("Error fetching applications:", err);
  }
}

function setStatusFilter(status) {
  currentStatusFilter = status;
  ['filterAll', 'filterPending', 'filterSubmitted'].forEach(id => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.classList.remove("bg-slate-800", "text-white", "font-medium");
    btn.classList.add("text-slate-400");
  });

  if (status === 'ALL') {
    document.getElementById('filterAll').classList.add("bg-slate-800", "text-white", "font-medium");
  } else if (status === 'PENDING') {
    document.getElementById('filterPending').classList.add("bg-slate-800", "text-white", "font-medium");
  } else if (status === 'SUBMITTED') {
    document.getElementById('filterSubmitted').classList.add("bg-slate-800", "text-white", "font-medium");
  }

  renderApplicationsTable();
}

function filterApplications() {
  renderApplicationsTable();
}

function renderApplicationsTable() {
  const container = document.getElementById("applicationsTableBody");
  if (!container) return;

  const searchKeyword = (document.getElementById("trackerSearch")?.value || "").toLowerCase().trim();

  let filtered = allApplications.filter(app => {
    // Status Filter
    if (currentStatusFilter === "PENDING" && !app.status.includes("PENDING")) return false;
    if (currentStatusFilter === "SUBMITTED" && !app.status.includes("SUBMITTED")) return false;

    // Search Keyword Filter
    if (searchKeyword) {
      const titleMatch = (app.job_title || "").toLowerCase().includes(searchKeyword);
      const companyMatch = (app.company_name || "").toLowerCase().includes(searchKeyword);
      const platformMatch = (app.platform || "").toLowerCase().includes(searchKeyword);
      if (!titleMatch && !companyMatch && !platformMatch) return false;
    }

    return true;
  });

  if (!filtered || filtered.length === 0) {
    container.innerHTML = `
      <tr>
        <td colspan="5" class="py-12 text-center text-slate-500 text-xs">
          No matching applications found.
        </td>
      </tr>
    `;
    return;
  }

  container.innerHTML = filtered.map(app => {
    let statusPill = "bg-slate-800/80 text-slate-400 border border-slate-700";
    let statusLabel = app.status;

    if (app.status.includes("SUBMITTED")) {
      statusPill = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
      statusLabel = "Submitted";
    } else if (app.status.includes("PENDING")) {
      statusPill = "bg-amber-500/10 text-amber-400 border border-amber-500/20";
      statusLabel = "Needs Review";
    }

    const companyInitial = (app.company_name || "C").charAt(0).toUpperCase();
    const formattedDate = app.created_at ? app.created_at.replace("T", " ").slice(0, 16) : "Just now";

    return `
      <tr class="hover:bg-white/[0.02] transition-colors">
        <td class="py-3 px-4">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-slate-800 border border-white/5 flex items-center justify-center font-semibold text-slate-300 text-xs flex-shrink-0">
              ${companyInitial}
            </div>
            <div class="min-w-0">
              <div class="font-medium text-white truncate max-w-xs sm:max-w-md">${escapeHtml(app.job_title)}</div>
              <div class="text-xs text-slate-400 truncate">${escapeHtml(app.company_name)}</div>
            </div>
          </div>
        </td>
        <td class="py-3 px-4">
          <span class="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-300 border border-white/5 uppercase">
            ${escapeHtml(app.platform)}
          </span>
        </td>
        <td class="py-3 px-4">
          <span class="px-2.5 py-1 rounded-full text-xs font-medium ${statusPill}">
            ${escapeHtml(statusLabel)}
          </span>
        </td>
        <td class="py-3 px-4 text-slate-400 text-xs font-mono">
          ${formattedDate}
        </td>
        <td class="py-3 px-4 text-right">
          ${app.job_url ? `
            <a href="${app.job_url}" target="_blank" class="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors text-xs">
              <span>View</span>
              <i data-lucide="external-link" class="w-3 h-3"></i>
            </a>
          ` : '<span class="text-slate-600">—</span>'}
        </td>
      </tr>
    `;
  }).join("");

  lucide.createIcons();
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
  statusEl.textContent = "Extracting candidate details via AI...";

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
      throw new Error(`${errorMsg}. Please verify the local agent backend is running on ${API_BASE}`);
    }

    const data = await res.json();
    if (data.status === "ok") {
      statusEl.textContent = "✓ Resume parsed & synced successfully!";
      fetchProfile();
      fetchStatus();
    } else {
      statusEl.textContent = "Upload failed.";
    }
  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
  }
}

// Profile Dossier
function updateFullNamePreview() {
  const fn = document.getElementById("profFirstName")?.value.trim() || "";
  const mn = document.getElementById("profMiddleName")?.value.trim() || "";
  const ln = document.getElementById("profLastName")?.value.trim() || "";
  const badge = document.getElementById("fullNamePreviewBadge");
  if (badge) {
    const computed = [fn, mn, ln].filter(Boolean).join(" ");
    badge.textContent = computed || "Unnamed Candidate";
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
      alert("Profile saved successfully!");
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
    if (res.ok) alert("Safety settings updated successfully!");
  } catch (err) {
    alert("Save error: " + err.message);
  }
}

// Backend Modal
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
