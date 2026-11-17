(function (root) {
  const stateAliases = {
    "Andaman and Nicobar Islands": ["andaman", "nicobar", "port blair"],
    "Andhra Pradesh": ["andhra", "vijayawada", "visakhapatnam", "vizag", "tirupati", "guntur"],
    "Arunachal Pradesh": ["arunachal", "itanagar"], "Assam": ["assam", "guwahati"],
    "Bihar": ["bihar", "patna"], "Chandigarh": ["chandigarh"],
    "Chhattisgarh": ["chhattisgarh", "raipur"],
    "Dadra and Nagar Haveli and Daman and Diu": ["dadra", "nagar haveli", "daman", "diu", "silvassa"],
    "Delhi": ["delhi", "new delhi"], "Goa": ["goa", "panaji"],
    "Gujarat": ["gujarat", "ahmedabad", "gandhinagar", "surat", "vadodara", "sanand"],
    "Haryana": ["haryana", "gurugram", "gurgaon", "faridabad", "panchkula"],
    "Himachal Pradesh": ["himachal", "shimla"], "Jammu and Kashmir": ["jammu", "kashmir", "srinagar"],
    "Jharkhand": ["jharkhand", "ranchi", "jamshedpur"],
    "Karnataka": ["karnataka", "bengaluru", "bangalore", "mysuru", "mysore", "mangaluru"],
    "Kerala": ["kerala", "kochi", "cochin", "thiruvananthapuram", "trivandrum", "kozhikode"],
    "Ladakh": ["ladakh", "leh"], "Lakshadweep": ["lakshadweep", "kavaratti"],
    "Madhya Pradesh": ["madhya pradesh", "indore", "bhopal"],
    "Maharashtra": ["maharashtra", "mumbai", "bombay", "pune", "nagpur", "nashik", "thane"],
    "Manipur": ["manipur", "imphal"], "Meghalaya": ["meghalaya", "shillong"],
    "Mizoram": ["mizoram", "aizawl"], "Nagaland": ["nagaland", "kohima", "dimapur"],
    "Odisha": ["odisha", "orissa", "bhubaneswar", "cuttack"],
    "Puducherry": ["puducherry", "pondicherry"], "Punjab": ["punjab", "mohali", "ludhiana", "amritsar"],
    "Rajasthan": ["rajasthan", "jaipur", "jodhpur", "udaipur"], "Sikkim": ["sikkim", "gangtok"],
    "Tamil Nadu": ["tamil nadu", "tamilnadu", "chennai", "madras", "coimbatore", "hosur", "madurai"],
    "Telangana": ["telangana", "hyderabad", "secunderabad"], "Tripura": ["tripura", "agartala"],
    "Uttar Pradesh": ["uttar pradesh", "noida", "ghaziabad", "lucknow", "kanpur"],
    "Uttarakhand": ["uttarakhand", "uttaranchal", "dehradun"], "West Bengal": ["west bengal", "kolkata", "calcutta"]
  };
  const stateCodes = { AP:"Andhra Pradesh", AR:"Arunachal Pradesh", AS:"Assam", BR:"Bihar", CH:"Chandigarh", CG:"Chhattisgarh", CT:"Chhattisgarh", DL:"Delhi", GA:"Goa", GJ:"Gujarat", HR:"Haryana", HP:"Himachal Pradesh", JH:"Jharkhand", JK:"Jammu and Kashmir", KA:"Karnataka", KL:"Kerala", LA:"Ladakh", LD:"Lakshadweep", MP:"Madhya Pradesh", MH:"Maharashtra", MN:"Manipur", ML:"Meghalaya", MZ:"Mizoram", NL:"Nagaland", OD:"Odisha", OR:"Odisha", PB:"Punjab", PY:"Puducherry", RJ:"Rajasthan", SK:"Sikkim", TN:"Tamil Nadu", TG:"Telangana", TS:"Telangana", TR:"Tripura", UP:"Uttar Pradesh", UK:"Uttarakhand", UT:"Uttarakhand", WB:"West Bengal", AN:"Andaman and Nicobar Islands", DN:"Dadra and Nagar Haveli and Daman and Diu", DD:"Dadra and Nagar Haveli and Daman and Diu" };
  const states = [...Object.keys(stateAliases).sort(), "Unknown / not specified"];
  const northStates = ["Delhi", "Haryana", "Uttar Pradesh", "Punjab", "Chandigarh", "Rajasthan", "Uttarakhand", "Himachal Pradesh", "Jammu and Kashmir", "Ladakh"];
  function locationStates(location = "") {
    const text = location.toLowerCase();
    const found = Object.entries(stateAliases).filter(([, aliases]) => aliases.some(alias => new RegExp(`\\b${alias}\\b`, "i").test(text))).map(([name]) => name);
    if (/\bindia\b/i.test(location)) for (const code of location.match(/\b[A-Z]{2}\b/g) || []) if (stateCodes[code]) found.push(stateCodes[code]);
    return found.length ? [...new Set(found)] : ["Unknown / not specified"];
  }
  function normalize(filters = {}) {
    if (Array.isArray(filters.states)) return { ...defaults, ...filters, states: filters.states.filter(name => states.includes(name)) };
    let selected = filters.region === "north" ? [...northStates] : [...states];
    if (filters.excludeStates !== false) selected = selected.filter(name => !["Telangana", "Andhra Pradesh"].includes(name));
    return { ...defaults, ...filters, states: selected };
  }
  const defaults = {
    companyType: "all", workModes: ["hybrid", "onsite", "unknown"], region: "all",
    excludeStates: true, maxYears: "2", minSalary: 500000, includeUnknownExperience: true,
    includeUnknownSalary: true, includeSenior: false, source: "all", skill: "", track: "all",
    states: states.filter(name => !["Telangana", "Andhra Pradesh"].includes(name))
  };
  function workMode(job) {
    const text = `${job.work_mode || ""} ${job.location || ""}`.toLowerCase();
    if (/\bhybrid\b/.test(text)) return "hybrid";
    if (/\b(remote|wfh|work from home)\b/.test(text) || /\b(fully remote|remote.only|100% remote)\b/i.test(job.description || "")) return "remote";
    if (/\b(on.?site|in.office)\b/.test(text)) return "onsite";
    return "unknown";
  }
  function matches(job, filters) {
    if (!filters.workModes.includes(workMode(job))) return false;
    const selectedStates = normalize(filters).states;
    if (!locationStates(job.location).some(name => selectedStates.includes(name))) return false;
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
  const exports = { defaults, matches, workMode, states, locationStates, normalize };
  if (typeof module !== "undefined" && module.exports) module.exports = exports;
  else root.JobFilters = exports;
})(typeof window === "undefined" ? globalThis : window);
