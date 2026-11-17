const state = { view: "all", jobs: [], allJobs: [], selected: null, sources: [], filters: null };
function readStored(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch { return fallback; } }
function persist(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { toast("Browser storage unavailable; changes last for this session only."); } }
const decisions = readStored("job-agent-decisions-v1", {});
const applicationKey = job => job.stable_key || job.apply_url;
const statusOf = job => snapshot ? (decisions[applicationKey(job)]?.status || job.status) : job.status;
function safeUrl(value) { try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : ""; } catch { return ""; } }
function readFilters() {
  return {
    companyType: $("#filter-company").value, workModes: $$('[name="work-mode"]:checked').map(input => input.value),
    region: $("#filter-region").value, excludeStates: $("#filter-excluded").checked, maxYears: $("#filter-years").value,
    minSalary: Math.max(0, Number($("#filter-salary").value) || 0), includeUnknownExperience: $("#filter-unknown-years").checked,
    includeUnknownSalary: $("#filter-unknown-pay").checked, includeSenior: $("#filter-senior").checked,
    source: $("#filter-source").value, skill: $("#filter-skill").value, track: $("#track-filter").value
  };
}
function setFilters(value) {
  const filters = { ...JobFilters.defaults, ...value };
  const fields = { "filter-company": "companyType", "filter-region": "region", "filter-years": "maxYears", "filter-salary": "minSalary", "filter-skill": "skill", "track-filter": "track" };
  Object.entries(fields).forEach(([id, key]) => { $("#" + id).value = filters[key]; });
  const checks = { "filter-excluded": "excludeStates", "filter-unknown-years": "includeUnknownExperience", "filter-unknown-pay": "includeUnknownSalary", "filter-senior": "includeSenior" };
  Object.entries(checks).forEach(([id, key]) => { $("#" + id).checked = filters[key]; });
  $$('[name="work-mode"]').forEach(input => { input.checked = filters.workModes.includes(input.value); });
  state.filters = filters;
}
function saveFilters() {
  state.filters = readFilters(); persist("job-agent-filters-v1", state.filters);
  loadJobs(); loadSummary();
}
function matchesPreferences(job) { return JobFilters.matches(job, state.filters || JobFilters.defaults); }
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
  $("#page-title").textContent = {overview:"Overview",jobs:"Job pipeline",sources:"Sources",leads:"Fresher pathways",activity:"Activity",profile:"Search profile"}[id];
  if (id === "jobs") loadJobs();
}

async function loadSummary() {
  const data = await api("/api/summary");
  const count = state.allJobs.length ? {
    total: state.allJobs.length,
    shortlisted: state.allJobs.filter(matchesPreferences).length,
    awaiting_review: state.allJobs.filter(job => matchesPreferences(job) && statusOf(job) === "review").length,
    approved: state.allJobs.filter(job => statusOf(job) === "approved").length,
    applied: state.allJobs.filter(job => statusOf(job) === "applied").length
  } : data.counts;
  const metrics = [[count.total, "Jobs available"], [count.shortlisted, "Match your filters"], [count.awaiting_review, "Awaiting review"], [count.approved, "Approved by you"], [count.applied, "Marked applied"]];
  $("#metrics").innerHTML = metrics.map((item, index) => `<div class="metric ${index === 1 ? "highlight" : ""}"><strong>${item[0] || 0}</strong><span>${item[1]}</span></div>`).join("");
  $("#last-scan").textContent = data.latest_scan ? `Last scan: ${formatDate(data.latest_scan.completed_at || data.latest_scan.started_at)}` : "No scan recorded";
  $("#queue-summary").textContent = `${count.approved || 0} approved · ${count.applied || 0} manually marked applied. Opening a form does not submit it.`;
}
function jobRow(job) {
  const url = safeUrl(job.apply_url);
  return `<article class="job-card ${state.selected?.id === job.id ? "active" : ""}">
    <button class="job-title" data-id="${job.id}"><h3>${escapeHtml(job.title)}</h3><p>${escapeHtml(job.company)} · ${escapeHtml(job.location)}</p></button>
    <span class="job-score">${job.score}</span>
    <div class="tags"><span class="tag ${matchesPreferences(job) ? "good" : "bad"}">${matchesPreferences(job) ? "Matches your filters" : "Outside your filters"}</span><span class="tag">${escapeHtml(job.evidence?.fit_level || "Needs review")}</span><span class="tag">${escapeHtml(statusOf(job))}</span></div>
    <div class="card-actions"><button class="text-button" data-id="${job.id}">View full details</button>${url ? `<a class="button primary" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Apply on company site ↗</a>` : "<span>Application link unavailable</span>"}</div>
  </article>`;
}
async function loadJobs() {
  const data = await api("/api/jobs?view=all"); state.allJobs = data.jobs;
  const sourceSelect = $("#filter-source");
  sourceSelect.innerHTML = '<option value="all">All sources</option>' + [...new Set(data.jobs.map(job => job.source))].sort().map(source => `<option value="${escapeHtml(source)}">${escapeHtml(source)}</option>`).join("");
  sourceSelect.value = state.filters.source;
  if (!sourceSelect.value) { sourceSelect.value = "all"; state.filters.source = "all"; }
  const query = ($("#job-search").value || "").toLowerCase();
  const views = {
    shortlisted: job => matchesPreferences(job),
    review: job => matchesPreferences(job) && statusOf(job) === "review",
    approved: job => statusOf(job) === "approved", applied: job => statusOf(job) === "applied",
    filtered: job => !matchesPreferences(job)
  };
  state.jobs = data.jobs.filter(job => (state.view === "filtered" || matchesPreferences(job)) && (!views[state.view] || views[state.view](job)) && (!query || `${job.title} ${job.company} ${job.location} ${job.description}`.toLowerCase().includes(query)));
  $("#filter-count").textContent = `· ${state.jobs.length} shown / ${data.jobs.length} available`;
  $("#jobs-list").innerHTML = state.jobs.length ? state.jobs.map(jobRow).join("") : '<div class="panel empty">No jobs match these selections. Change filters or choose Show all available jobs.</div>';
  $$('[data-id]').forEach(button => button.addEventListener("click", () => selectJob(Number(button.dataset.id))));
  state.selected = state.jobs.find(job => job.id === state.selected?.id) || state.jobs[0] || null;
  renderDetail();
}
function selectJob(id) {
  state.selected = state.allJobs.find(job => job.id === id);
  renderDetail();
  $$(".job-card").forEach(card => card.classList.toggle("active", Number(card.querySelector("[data-id]").dataset.id) === id));
  if (window.innerWidth < 1100) $("#job-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}
function renderDetail() {
  const job = state.selected; const target = $("#job-detail");
  if (!job) { target.innerHTML = '<div class="empty-detail"><h3>No job selected</h3><p>Select a listing to see the full description and application controls.</p></div>'; return; }
  const url = safeUrl(job.apply_url);
  const reasons = job.reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join("");
  const warnings = job.warnings.map(warning => `<li>${escapeHtml(warning)}</li>`).join("");
  target.innerHTML = `<p class="eyebrow">JOB ${job.id} · ORIGINAL FIT SCORE ${job.score}</p><h2>${escapeHtml(job.title)}</h2>
    <p class="detail-meta"><strong>${escapeHtml(job.company)}</strong><br>${escapeHtml(job.location)}<br>${escapeHtml(job.source)}</p>
    <div class="detail-actions sticky-actions">${url ? `<a class="button primary" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Apply on company site ↗</a><button class="button secondary" id="approve-open">Approve & open application</button>` : ""}
    <button class="button secondary" data-status="approved">Approve for my queue</button><button class="button danger" data-status="rejected">Reject</button><button class="button link" data-status="applied">I submitted this application</button></div>
    <p class="action-note">Application forms open on the employer website. You complete and submit the form there. Approval records your decision; it does not submit anything.</p>
    <div class="detail-section"><h4>Listing details</h4><p class="detail-meta">Tracks: ${escapeHtml(job.evidence?.tracks?.join(" · ") || "Unclassified")}<br>Fit: ${escapeHtml(job.evidence?.fit_level || "Needs review")}<br>Resume skills: ${escapeHtml(job.evidence?.skills?.join(" · ") || "No exact skill evidence")}<br>Required experience: ${job.evidence?.years_required == null ? "Not specified" : `${job.evidence.years_required} years minimum detected`}<br>Pay: ${job.evidence?.salary_inr ? formatMoney(job.evidence.salary_inr) + " annually (detected)" : "Not published; confirm before applying"}<br>Work mode: ${escapeHtml(job.evidence?.work_mode || "Unverified")}<br>Source date: ${escapeHtml(job.posted_at || "Not supplied")}<br>Last checked: ${formatDate(job.updated_at)}<br>Application status: ${escapeHtml(statusOf(job))}</p></div>
    <details class="detail-section" open><summary>Full job description</summary><div class="full-description">${escapeHtml(job.description || "Description not supplied by source. Open the original listing.")}</div></details>
    <details class="detail-section"><summary>Original agent assessment</summary><ul>${reasons}</ul><p>Your current filter selections control the results above.</p></details>
    ${warnings ? `<div class="detail-section"><h4>Items to verify</h4><ul>${warnings}</ul></div>` : ""}`;
  $$('[data-status]').forEach(button => button.addEventListener("click", () => updateStatus(job.id, button.dataset.status)));
  $("#approve-open")?.addEventListener("click", () => {
    const opened = window.open(url, "_blank", "noopener,noreferrer");
    updateStatus(job.id, "approved", true);
  });
}


async function updateStatus(id, status, opened = false) {
  const job = state.allJobs.find(item => item.id === id); if (!job) return;
  if (!snapshot) await api(`/api/jobs/${id}/status`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({status}) });
  decisions[applicationKey(job)] = { status, opened, updated_at: new Date().toISOString() };
  persist("job-agent-decisions-v1", decisions);
  job.status = status;
  toast(status === "applied" ? "Recorded your confirmation of submission" : `Job marked ${status}`);
  await loadJobs(); await loadSummary(); await loadActivity();
}
async function approveVisible() {
  for (const job of state.jobs.filter(job => !["applied", "rejected"].includes(statusOf(job)))) {
    if (!snapshot) await api(`/api/jobs/${job.id}/status`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({status: "approved"}) });
    decisions[applicationKey(job)] = {status: "approved", opened: false, updated_at: new Date().toISOString()};
    job.status = "approved";
  }
  persist("job-agent-decisions-v1", decisions);
  await loadJobs(); await loadSummary(); toast("Visible jobs approved. No applications submitted.");
}
function openNext() {
  const job = state.allJobs.find(item => statusOf(item) === "approved" && !decisions[applicationKey(item)]?.opened && safeUrl(item.apply_url));
  if (!job) { toast("No unopened approved jobs. Approve a job first."); return; }
  window.open(safeUrl(job.apply_url), "_blank", "noopener,noreferrer");
  decisions[applicationKey(job)] = {status: "approved", opened: true, updated_at: new Date().toISOString()};
  persist("job-agent-decisions-v1", decisions);
  selectJob(job.id); toast("Employer form opened. Complete and submit it there.");
}

async function loadSources() {
  const data = await api("/api/sources"); state.sources = data.sources;
  $("#lead-cards").innerHTML = (data.leads || []).map(lead => `<article class="source-card"><p class="eyebrow">${escapeHtml(lead.company)} · RESEARCHED ${escapeHtml(lead.reviewed_at)}</p><h3>${escapeHtml(lead.title)}</h3><span class="tag">${escapeHtml(lead.status)}</span><p>${escapeHtml(lead.fit)}</p><p><strong>Pay evidence:</strong> ${escapeHtml(lead.pay)}</p><p><strong>Evidence:</strong> ${escapeHtml(lead.evidence)}</p><p><strong>Your fit:</strong> ${escapeHtml(lead.candidate_fit || "Eligibility unverified")}</p><p><strong>Next step:</strong> ${escapeHtml(lead.next)}</p><p>${escapeHtml(lead.work_mode)}</p><a href="${escapeHtml(lead.url)}" target="_blank" rel="noreferrer">Official source ↗</a></article>`).join("");
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
    ${source.latest_run ? `<p>Last scan: ${escapeHtml(source.latest_run.status)} · ${formatDate(source.latest_run.created_at)}${source.latest_run.error ? `<br>${escapeHtml(source.latest_run.error)}` : ""}</p>` : ""}
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
  $("#profile-content").innerHTML = `<article class="profile-card"><p class="eyebrow">MINIMUM PAY</p><strong>${formatMoney(state.filters.minSalary)}</strong><p>Your selected annual compensation floor.</p></article>
    <article class="profile-card"><p class="eyebrow">WORK AUTHORIZATION</p><strong>India</strong><p>Indian office locations only.</p></article>
    <article class="profile-card"><p class="eyebrow">WORK ARRANGEMENT</p><strong>${escapeHtml(state.filters.workModes.join(" · ") || "None selected")}</strong><p>Change these selections in Job pipeline. Unknown arrangements require confirmation.</p></article>
    <article class="profile-card wide"><p class="eyebrow">CANDIDATE</p><h3>${escapeHtml(profile.candidate_summary || "Early-career applicant")}</h3></article>
    <article class="profile-card wide"><p class="eyebrow">SEARCH ROUTES</p><h3>MNC graduate / junior technology · Python / backend / AI stack</h3><p>1–2 year minimums are marked as stretch roles. Internships are counted separately.</p></article>
    <article class="profile-card wide"><p class="eyebrow">PREFERRED NORTH INDIA</p><h3>${profile.preferred_regions.map(escapeHtml).join(" · ")}</h3></article>
    <article class="profile-card wide"><p class="eyebrow">EXCLUDED LOCATIONS</p><h3>${profile.excluded_regions.map(escapeHtml).join(" · ")}</h3></article>
    <article class="profile-card wide"><p class="eyebrow">APPLICATION POLICY</p><h3>${profile.approval_required ? "Your approval is required for every application" : "Automatic submission enabled"}</h3></article>`;
}

async function loadLatest() {
  const data = await api("/api/jobs?view=all");
  $("#latest-jobs").innerHTML = data.jobs.filter(matchesPreferences).slice(0, 5).map(job => `<div class="compact-row"><span class="compact-icon">${job.score}</span><div><button class="text-button" data-overview-job="${job.id}">${escapeHtml(job.title)}</button><small>${escapeHtml(job.company)} · ${escapeHtml(job.location)}</small></div><a href="${escapeHtml(safeUrl(job.apply_url))}" target="_blank" rel="noopener noreferrer">Apply ↗</a></div>`).join("") || '<p class="empty">No jobs match your filters. Open Job pipeline to adjust them.</p>';
  $$("[data-overview-job]").forEach(button => button.addEventListener("click", async () => { showSection("jobs"); await loadJobs(); selectJob(Number(button.dataset.overviewJob)); }));
}

async function runScan() {
  if (snapshot) { toast("Open the live control center to run a new scan"); return; }
  const button = $("#scan-button"); button.disabled = true; button.textContent = "Scan running…";
  try { await api("/api/scan", { method: "POST" }); toast("Live scan started"); setTimeout(refresh, 4500); }
  catch (error) { toast(error.message); }
  finally { setTimeout(() => { button.disabled = false; button.textContent = "Run scan now"; }, 5000); }
}

async function refresh() { await loadJobs(); await Promise.all([loadSummary(), loadLatest(), loadSources(), loadActivity(), loadProfile()]); }

$$('.nav-item').forEach(item => item.addEventListener("click", () => showSection(item.dataset.section)));
$$('[data-jump]').forEach(item => item.addEventListener("click", () => showSection(item.dataset.jump)));
$$('#job-tabs button').forEach(button => button.addEventListener("click", () => { state.view = button.dataset.view; $$('#job-tabs button').forEach(item => item.classList.toggle("active", item === button)); loadJobs(); }));
let searchTimer; $("#job-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadJobs, 250); });
$("#scan-button").addEventListener("click", runScan);
$("#track-filter").addEventListener("change", saveFilters);
$$(".filter-panel input, .filter-panel select").forEach(input => input.addEventListener("change", saveFilters));
$("#reset-filters").addEventListener("click", () => { setFilters(JobFilters.defaults); $("#filter-source").value = "all"; saveFilters(); });
$("#clear-filters").addEventListener("click", () => {
  setFilters({ companyType:"all",workModes:["hybrid","onsite","unknown","remote"],region:"all",excludeStates:false,maxYears:"all",minSalary:0,includeUnknownExperience:true,includeUnknownSalary:true,includeSenior:true,source:"all",skill:"",track:"all" });
  $("#filter-source").value = "all"; $("#job-search").value = ""; state.view = "all";
  $$("#job-tabs button").forEach(button => button.classList.toggle("active", button.dataset.view === "all")); saveFilters();
});
$("#approve-visible").addEventListener("click", () => approveVisible().catch(error => toast(error.message)));
$("#open-next").addEventListener("click", openNext);
setFilters(readStored("job-agent-filters-v1", JobFilters.defaults));
$("#application-mode").textContent = snapshot ? "Apply on the employer website. Approvals are saved only in this browser; they do not submit applications. Automatic submission needs a connected application runner." : "Approvals are saved to your private database. Open each approved employer form to complete the application. No submission runner is connected.";
if (snapshot) {
  $("#scan-button").textContent = location.protocol === "file:" ? "Offline snapshot" : "Auto-updated snapshot";
  $("#last-scan").title = "Use the private local control center for live actions";
}
refresh().catch(error => toast(error.message));
