const state = { view: "all", jobs: [], selected: null, sources: [] };
const snapshot = window.__JOB_AGENT_SNAPSHOT__ || null;
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const formatDate = value => value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Not yet";
const formatMoney = value => value ? new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value) : "Not set";

async function api(path, options) {
  if (snapshot) {
    const url = new URL(path, "https://job-agent.local");
    if (options?.method && options.method !== "GET") throw new Error("Start the live control center to update job status.");
    if (url.pathname === "/api/summary") return snapshot.summary;
    if (url.pathname === "/api/sources") return snapshot.sources;
    if (url.pathname === "/api/activity") return snapshot.activity;
    if (url.pathname === "/api/profile") return snapshot.profile;
    if (url.pathname === "/api/jobs") {
      const view = url.searchParams.get("view") || "all";
      const search = (url.searchParams.get("q") || "").toLowerCase();
      const views = {
        shortlisted: job => job.eligible,
        review: job => job.eligible && job.status === "review",
        approved: job => job.status === "approved",
        applied: job => job.status === "applied",
        filtered: job => !job.eligible,
      };
      return { jobs: snapshot.jobs.filter(job => (!views[view] || views[view](job)) && (!search || `${job.title} ${job.company} ${job.location} ${job.description}`.toLowerCase().includes(search))) };
    }
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || data.message || "Request failed");
  return data;
}

function toast(message) {
  const element = $("#toast"); element.textContent = message; element.classList.add("show");
  setTimeout(() => element.classList.remove("show"), 2600);
}

function showSection(id) {
  $$(".page").forEach(page => page.classList.toggle("active", page.id === id));
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.section === id));
  $("#page-title").textContent = {overview:"Overview",jobs:"Job pipeline",sources:"Sources",activity:"Activity",profile:"Search profile"}[id];
  if (id === "jobs") loadJobs();
}

async function loadSummary() {
  const data = await api("/api/summary");
  const count = data.counts;
  const metrics = [
    [count.total, "Jobs found"], [count.shortlisted, "Shortlisted"], [count.awaiting_review, "Awaiting approval"],
    [count.approved, "Approved"], [count.applied, "Applied"]
  ];
  $("#metrics").innerHTML = metrics.map((item, index) => `<div class="metric ${index === 1 ? "highlight" : ""}"><strong>${item[0] || 0}</strong><span>${item[1]}</span></div>`).join("");
  $("#last-scan").textContent = data.latest_scan ? `Last scan: ${formatDate(data.latest_scan.completed_at || data.latest_scan.started_at)}` : "No scan recorded";
}

function jobRow(job) {
  return `<button class="job-card ${state.selected?.id === job.id ? "active" : ""}" data-id="${job.id}">
    <div><h3>${escapeHtml(job.title)}</h3><p>${escapeHtml(job.company)} · ${escapeHtml(job.location)}</p></div>
    <span class="job-score">${job.score}</span>
    <div class="tags"><span class="tag ${job.eligible ? "good" : "bad"}">${job.eligible ? "Shortlisted" : "Filtered"}</span><span class="tag">${escapeHtml(job.source)}</span><span class="tag">${escapeHtml(job.status)}</span></div>
  </button>`;
}

async function loadJobs() {
  const query = new URLSearchParams({ view: state.view, q: $("#job-search")?.value || "" });
  const data = await api(`/api/jobs?${query}`); state.jobs = data.jobs;
  $("#jobs-list").innerHTML = state.jobs.length ? state.jobs.map(jobRow).join("") : `<div class="panel empty">No jobs in this view.</div>`;
  $$(".job-card").forEach(card => card.addEventListener("click", () => selectJob(Number(card.dataset.id))));
  if (state.selected) { state.selected = state.jobs.find(job => job.id === state.selected.id) || null; renderDetail(); }
}

function selectJob(id) { state.selected = state.jobs.find(job => job.id === id); loadJobs(); renderDetail(); }
function renderDetail() {
  const job = state.selected; const target = $("#job-detail");
  if (!job) { target.innerHTML = `<div class="empty-detail"><span>↗</span><h3>Select a job</h3><p>See its score, filtering evidence, warnings and application link.</p></div>`; return; }
  const reasons = job.reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join("");
  const warnings = job.warnings.map(warning => `<li>${escapeHtml(warning)}</li>`).join("");
  target.innerHTML = `<p class="eyebrow">JOB ${job.id} · SCORE ${job.score}</p><h2>${escapeHtml(job.title)}</h2>
    <p class="detail-meta"><strong>${escapeHtml(job.company)}</strong><br>${escapeHtml(job.location)}<br>${escapeHtml(job.source)}</p>
    <div class="detail-section"><h4>${job.eligible ? "Why it was shortlisted" : "Why it was filtered"}</h4><ul>${reasons || "<li>No evidence recorded.</li>"}</ul></div>
    ${warnings ? `<div class="detail-section"><h4>Review warnings</h4><ul>${warnings}</ul></div>` : ""}
    <div class="detail-section"><h4>Description preview</h4><p class="detail-meta">${escapeHtml(job.description).slice(0, 1200)}</p></div>
    <div class="detail-actions">
      <a class="button link" href="${escapeHtml(job.apply_url)}" target="_blank" rel="noreferrer">Open listing</a>
      ${!snapshot && job.eligible && job.status === "review" ? `<button class="button secondary" data-status="approved">Approve</button><button class="button danger" data-status="rejected">Reject</button>` : ""}
      ${!snapshot && job.status === "approved" ? `<button class="button secondary" data-status="applied">Mark applied</button>` : ""}
    </div>`;
  $$('[data-status]').forEach(button => button.addEventListener("click", () => updateStatus(job.id, button.dataset.status)));
}

async function updateStatus(id, status) {
  await api(`/api/jobs/${id}/status`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({status}) });
  toast(`Job marked ${status}`); await Promise.all([loadJobs(), loadSummary(), loadActivity()]);
}

async function loadSources() {
  const data = await api("/api/sources"); state.sources = data.sources;
  const groups = { company_careers: "Direct company careers", company_ats: "Direct employer ATS", india_portal: "India job portals", public_api: "Approved public APIs", public_feed: "Approved public feeds" };
  $("#source-groups").innerHTML = Object.entries(groups).map(([key, label]) => {
    const sources = state.sources.filter(source => source.source_type === key); if (!sources.length) return "";
    return `<div class="source-group"><h3>${label}<span>${sources.length} sources</span></h3><div class="source-grid">${sources.map(sourceCard).join("")}</div></div>`;
  }).join("");
  $("#priority-sources").innerHTML = state.sources.slice(0, 5).map(source => `<div class="compact-row"><span class="compact-icon">${source.priority}</span><div><strong>${escapeHtml(source.name)}</strong><small>${source.access_mode.replaceAll("_", " ")}</small></div><span class="score-pill">${source.metrics.found || 0}</span></div>`).join("");
}

function sourceCard(source) {
  const live = source.enabled && source.access_mode === "automated_discovery";
  return `<article class="source-card"><div class="source-top"><div><p class="eyebrow">PRIORITY ${source.priority || 0}</p><h3>${escapeHtml(source.name)}</h3></div><span class="mode ${live ? "live" : ""}">${live ? "LIVE SCAN" : source.access_mode.replaceAll("_", " ").toUpperCase()}</span></div>
    <p>${escapeHtml(source.note || (live ? "Automatically checked through its public feed or API." : "Candidate-controlled source launch."))}</p>
    ${source.homepage ? `<a href="${escapeHtml(source.homepage)}" target="_blank" rel="noreferrer">Open source ↗</a>` : ""}
    <div class="source-stats"><div><strong>${source.metrics.found || 0}</strong><small>Found</small></div><div><strong>${source.metrics.shortlisted || 0}</strong><small>Shortlisted</small></div></div></article>`;
}

async function loadActivity() {
  const data = await api("/api/activity");
  $("#scan-history").innerHTML = data.scans.length ? data.scans.map(scan => `<div class="timeline-row"><strong>${scan.status.replaceAll("_", " ")}</strong><small>${formatDate(scan.started_at)} · ${scan.fetched} fetched · ${scan.eligible} eligible · ${scan.failure_count} failures</small></div>`).join("") : `<p class="empty">No scans recorded.</p>`;
  $("#event-history").innerHTML = data.events.length ? data.events.map(event => `<div class="timeline-row"><strong>${escapeHtml(event.action)} · ${escapeHtml(event.title || "Job")}</strong><small>${escapeHtml(event.company || "")} · ${formatDate(event.created_at)}</small></div>`).join("") : `<p class="empty">No approval decisions yet.</p>`;
}

async function loadProfile() {
  const profile = await api("/api/profile");
  $("#profile-content").innerHTML = `<article class="profile-card"><p class="eyebrow">MINIMUM PAY</p><strong>${formatMoney(profile.minimum_salary_inr)}</strong><p>Annual compensation floor.</p></article>
    <article class="profile-card"><p class="eyebrow">WORK AUTHORIZATION</p><strong>India</strong><p>Indian office locations only.</p></article>
    <article class="profile-card"><p class="eyebrow">WORK ARRANGEMENT</p><strong>Hybrid or onsite</strong><p>Remote roles excluded. Office arrangements need confirmation before approval.</p></article>
    <article class="profile-card wide"><p class="eyebrow">PREFERRED NORTH INDIA</p><h3>${profile.preferred_regions.map(escapeHtml).join(" · ")}</h3></article>
    <article class="profile-card wide"><p class="eyebrow">EXCLUDED LOCATIONS</p><h3>${profile.excluded_regions.map(escapeHtml).join(" · ")}</h3></article>
    <article class="profile-card wide"><p class="eyebrow">APPLICATION POLICY</p><h3>${profile.approval_required ? "Your approval is required for every application" : "Automatic submission enabled"}</h3></article>`;
}

async function loadLatest() {
  const data = await api("/api/jobs?view=all");
  $("#latest-jobs").innerHTML = data.jobs.slice(0, 5).map(job => `<div class="compact-row"><span class="compact-icon">${job.score}</span><div><strong>${escapeHtml(job.title)}</strong><small>${escapeHtml(job.company)} · ${escapeHtml(job.location)}</small></div><span class="tag ${job.eligible ? "good" : "bad"}">${job.eligible ? "Shortlist" : "Filtered"}</span></div>`).join("") || `<p class="empty">No jobs loaded.</p>`;
}

async function runScan() {
  if (snapshot) { toast("Open the live control center to run a new scan"); return; }
  const button = $("#scan-button"); button.disabled = true; button.textContent = "Scan running…";
  try { await api("/api/scan", { method: "POST" }); toast("Live scan started"); setTimeout(refresh, 4500); }
  catch (error) { toast(error.message); }
  finally { setTimeout(() => { button.disabled = false; button.textContent = "Run scan now"; }, 5000); }
}

async function refresh() { await Promise.all([loadSummary(), loadLatest(), loadSources(), loadActivity(), loadProfile()]); if ($("#jobs").classList.contains("active")) await loadJobs(); }

$$('.nav-item').forEach(item => item.addEventListener("click", () => showSection(item.dataset.section)));
$$('[data-jump]').forEach(item => item.addEventListener("click", () => showSection(item.dataset.jump)));
$$('#job-tabs button').forEach(button => button.addEventListener("click", () => { state.view = button.dataset.view; $$('#job-tabs button').forEach(item => item.classList.toggle("active", item === button)); loadJobs(); }));
let searchTimer; $("#job-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadJobs, 250); });
$("#scan-button").addEventListener("click", runScan);
if (snapshot) {
  $("#scan-button").textContent = location.protocol === "file:" ? "Offline snapshot" : "Auto-updated snapshot";
  $("#last-scan").title = "Use the private local control center for live actions";
}
refresh().catch(error => toast(error.message));
