(function (root) {
  const defaults = {
    companyType: "all", workModes: ["hybrid", "onsite", "unknown"], region: "all",
    excludeStates: true, maxYears: "2", minSalary: 500000, includeUnknownExperience: true,
    includeUnknownSalary: true, includeSenior: false, source: "all", skill: "", track: "all"
  };
  function workMode(job) {
    const text = `${job.work_mode || ""} ${job.location || ""}`.toLowerCase();
    if (/\bhybrid\b/.test(text)) return "hybrid";
    if (/\b(remote|wfh|work from home)\b/.test(text) || /\b(fully remote|remote.only|100% remote)\b/i.test(job.description || "")) return "remote";
    if (/\b(on.?site|in.office)\b/.test(text)) return "onsite";
    return "unknown";
  }
  function matches(job, filters) {
    const location = (job.location || "").toLowerCase();
    if (!filters.workModes.includes(workMode(job))) return false;
    if (filters.excludeStates && /telangana|hyderabad|andhra|vijayawada|visakhapatnam|vizag|tirupati/.test(location)) return false;
    if (filters.region === "north" && !/delhi|ncr|gurugram|gurgaon|noida|chandigarh|punjab|haryana|uttar pradesh|rajasthan|uttarakhand|himachal|jammu|kashmir/.test(location)) return false;
    if (filters.companyType !== "all" && job.company_type !== filters.companyType) return false;
    if (filters.source !== "all" && job.source !== filters.source) return false;
    if (!filters.includeSenior && /\b(senior|sr|staff|principal|lead|manager|director|head|architect)\b/i.test(job.title)) return false;
    const years = job.evidence?.years_required;
    if (years == null && !filters.includeUnknownExperience) return false;
    if (years != null && filters.maxYears !== "all" && years > Number(filters.maxYears)) return false;
    const salary = job.evidence?.salary_inr;
    if (salary == null && !filters.includeUnknownSalary) return false;
    if (salary != null && salary < Number(filters.minSalary || 0)) return false;
    if (filters.track !== "all" && !(job.evidence?.tracks || [job.evidence?.track]).includes(filters.track)) return false;
    if (filters.skill && !filters.skill.toLowerCase().split(",").map(value => value.trim()).filter(Boolean).every(value => `${job.title} ${job.description}`.toLowerCase().includes(value))) return false;
    return true;
  }
  const exports = { defaults, matches, workMode };
  if (typeof module !== "undefined" && module.exports) module.exports = exports;
  else root.JobFilters = exports;
})(typeof window === "undefined" ? globalThis : window);
