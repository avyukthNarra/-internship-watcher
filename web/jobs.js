// Shared by the browser (globalThis.JobBoard) and Node tests (module.exports).
// Pure logic only: no DOM access. The published data URL lives only in DATA_URL.

const DATA_URL = "./sample-jobs.json";
const NEW_WINDOW_MS = 24 * 60 * 60 * 1000;
const PAGE_SIZE = 50;
const ROLE_LABELS = ["SWE", "Data", "ML/AI", "Research", "Embedded", "Hardware", "Quant"];
const AVATAR_COLORS = 10;
const SORTS = ["newest", "oldest"];

// Fallback used only when a job has no `roles` array (older exports). It
// mirrors the shipped config.json `alert_channels` title keywords; the export
// is authoritative because it also sees SimplifyJobs categories.
const EMBEDDED_WORDS = [
  "embedded", "firmware", "fpga", "rtl", "asic", "microcontroller", "rtos",
  "device driver", "bare metal", "linux kernel",
];
const ROLE_RULES = [
  {
    label: "SWE",
    roles: ["software", "swe", "backend", "frontend", "full stack", "fullstack", "web",
      "mobile", "devops", "platform", "infrastructure"],
    exclude: EMBEDDED_WORDS,
  },
  { label: "Data", roles: ["data", "analytics", "analyst", "business intelligence"] },
  {
    label: "ML/AI",
    roles: ["machine learning", "ml", "ai", "deep learning", "computer vision", "nlp", "llm",
      "artificial intelligence", "generative"],
  },
  { label: "Research", roles: ["research", "scientist"] },
  { label: "Embedded", roles: EMBEDDED_WORDS },
  {
    label: "Hardware",
    roles: ["hardware", "electrical", "electronics", "circuit", "pcb", "analog", "digital design",
      "verification", "validation", "silicon", "semiconductor", "optical", "photonics", "thermal",
      "rf", "power electronics", "test engineer", "manufacturing"],
    exclude: EMBEDDED_WORDS,
  },
  { label: "Quant", roles: ["quant", "quantitative", "trading", "trader", "market making"] },
];

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Same whole-word rule as job_utils.preference_matches (Python `\b`).
function wordRegex(words) {
  return new RegExp(`\\b(?:${words.map(escapeRegExp).join("|")})\\b`, "i");
}

const COMPILED_RULES = ROLE_RULES.map((rule) => ({
  label: rule.label,
  include: wordRegex(rule.roles),
  exclude: rule.exclude ? wordRegex(rule.exclude) : null,
}));

function asText(value) {
  return typeof value === "string" ? value : "";
}

function toMs(now) {
  if (now instanceof Date) return now.getTime();
  if (typeof now === "number") return now;
  return Date.parse(now);
}

function normalizeQuery(value) {
  return asText(value).trim().toLowerCase();
}

function uniqueSorted(values, compare) {
  const out = [...new Set(values.filter(Boolean))];
  out.sort(compare || ((a, b) => a.localeCompare(b, "en")));
  return out;
}

function isWithinLast(iso, nowMs, windowMs) {
  const then = Date.parse(iso);
  if (!Number.isFinite(then) || !Number.isFinite(nowMs)) return false;
  const delta = nowMs - then;
  return delta >= 0 && delta <= windowMs;
}

function isNew(job, now) {
  return isWithinLast(job && job.first_seen, toMs(now === undefined ? new Date() : now), NEW_WINDOW_MS);
}

function inferRoles(title) {
  const text = asText(title);
  if (!text) return [];
  return COMPILED_RULES
    .filter((rule) => rule.include.test(text) && !(rule.exclude && rule.exclude.test(text)))
    .map((rule) => rule.label);
}

// Exported roles win (unknown labels dropped); otherwise infer from the title.
function jobRoles(job) {
  if (!job || typeof job !== "object") return [];
  if (Array.isArray(job.roles)) {
    const wanted = new Set(job.roles.filter((role) => typeof role === "string"));
    return ROLE_LABELS.filter((label) => wanted.has(label));
  }
  return inferRoles(job.title);
}

function isRemote(location) {
  return /\bremote\b/i.test(asText(location));
}

const SEASON_ORDER = { winter: 0, spring: 1, summer: 2, fall: 3, autumn: 3 };

// Chronological: "Fall 2026" < "Spring 2027" < "Summer 2027"; others after, A-Z.
function compareTerms(a, b) {
  const parse = (term) => {
    const match = /^\s*(winter|spring|summer|fall|autumn)\s+(\d{4})\s*$/i.exec(term);
    return match ? Number(match[2]) * 10 + SEASON_ORDER[match[1].toLowerCase()] : null;
  };
  const ka = parse(a);
  const kb = parse(b);
  if (ka !== null && kb !== null && ka !== kb) return ka - kb;
  if (ka !== null && kb === null) return -1;
  if (ka === null && kb !== null) return 1;
  return a.localeCompare(b, "en");
}

function listCompanies(jobs) {
  return uniqueSorted(
    (Array.isArray(jobs) ? jobs : []).map((job) => asText(job && job.company).trim())
  );
}

function listTerms(jobs) {
  const terms = [];
  for (const job of Array.isArray(jobs) ? jobs : []) {
    if (!job || !Array.isArray(job.terms)) continue;
    for (const term of job.terms) {
      const text = asText(term).trim();
      if (text) terms.push(text);
    }
  }
  return uniqueSorted(terms, compareTerms);
}

function normalizeJobs(data) {
  if (!Array.isArray(data)) return null;
  return data.filter((job) => job !== null && typeof job === "object" && !Array.isArray(job));
}

// Adds resolved `roles` once at load so filtering 3,000+ rows stays cheap.
// Returns new objects; the payload is not mutated.
function prepareJobs(jobs) {
  return (Array.isArray(jobs) ? jobs : []).map((job) => ({ ...job, roles: jobRoles(job) }));
}

function filterJobs(jobs, criteria, now) {
  const source = Array.isArray(jobs) ? jobs : [];
  const options = criteria && typeof criteria === "object" ? criteria : {};
  const query = normalizeQuery(options.query);
  const company = asText(options.company).trim();
  const term = asText(options.term).trim().toLowerCase();
  const location = normalizeQuery(options.location);
  const roles = Array.isArray(options.roles) ? options.roles.filter((r) => ROLE_LABELS.includes(r)) : [];
  const remoteOnly = Boolean(options.remoteOnly);
  const newOnly = Boolean(options.newOnly);
  const topOnly = Boolean(options.topOnly);
  const nowMs = toMs(now === undefined ? new Date() : now);

  return source.filter((job) => {
    if (!job || typeof job !== "object") return false;
    if (query) {
      const haystack = [job.company, job.title, job.location]
        .map(asText)
        .join("\u0000")
        .toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (company && asText(job.company).trim() !== company) return false;
    if (term) {
      const terms = Array.isArray(job.terms) ? job.terms : [];
      const matched = terms.some((item) => asText(item).trim().toLowerCase() === term);
      if (!matched) return false;
    }
    if (location && !asText(job.location).toLowerCase().includes(location)) return false;
    if (remoteOnly && !isRemote(job.location)) return false;
    if (roles.length) {
      const own = jobRoles(job);
      if (!roles.some((role) => own.includes(role))) return false;
    }
    if (newOnly && !isWithinLast(job.first_seen, nowMs, NEW_WINDOW_MS)) return false;
    if (topOnly && job.top !== true) return false;
    return true;
  });
}

// Counts per role among jobs matching every filter except the role filter,
// so each chip shows how many results selecting it would add.
function roleCounts(jobs, criteria, now) {
  const counts = Object.fromEntries(ROLE_LABELS.map((label) => [label, 0]));
  const base = filterJobs(jobs, { ...(criteria || {}), roles: [] }, now);
  for (const job of base) {
    for (const role of jobRoles(job)) counts[role] += 1;
  }
  return counts;
}

function sortJobs(jobs, order) {
  const source = Array.isArray(jobs) ? jobs : [];
  const direction = order === "oldest" ? 1 : -1;
  return source.slice().sort((a, b) => {
    const aTime = Date.parse(a && a.first_seen);
    const bTime = Date.parse(b && b.first_seen);
    const aOk = Number.isFinite(aTime);
    const bOk = Number.isFinite(bTime);
    if (aOk && bOk && aTime !== bTime) return (aTime - bTime) * direction;
    if (aOk && bOk) return 0;
    if (!aOk && !bOk) return 0;
    return aOk ? -1 : 1;
  });
}

function sanitizeUrl(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    return null;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
  return parsed.href;
}

// Long form, used for tooltips and screen-reader text.
function formatAge(iso, now) {
  const then = Date.parse(iso);
  const nowMs = toMs(now === undefined ? new Date() : now);
  if (!Number.isFinite(then) || !Number.isFinite(nowMs)) return "First seen date unknown";
  const delta = nowMs - then;
  if (delta < 0) {
    return delta > -60 * 1000 ? "First seen just now" : "First seen in the future";
  }
  const seconds = Math.floor(delta / 1000);
  if (seconds < 60) return "First seen just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return minutes === 1 ? "First seen 1 minute ago" : `First seen ${minutes} minutes ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return hours === 1 ? "First seen 1 hour ago" : `First seen ${hours} hours ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 365) {
    if (days < 30) {
      return days === 1 ? "First seen 1 day ago" : `First seen ${days} days ago`;
    }
    const months = Math.floor(days / 30);
    return months === 1 ? "First seen 1 month ago" : `First seen ${months} months ago`;
  }
  const years = Math.floor(days / 365);
  return years === 1 ? "First seen 1 year ago" : `First seen ${years} years ago`;
}

// Compact form for the list: "now", "5m ago", "2h ago", "3d ago", "2mo ago", "1y ago".
function formatRelative(iso, now) {
  const then = Date.parse(iso);
  const nowMs = toMs(now === undefined ? new Date() : now);
  if (!Number.isFinite(then) || !Number.isFinite(nowMs)) return "";
  const delta = nowMs - then;
  if (delta < 60 * 1000) return delta > -60 * 1000 ? "now" : "";
  const minutes = Math.floor(delta / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

function resultLabel(count, state) {
  const mode = state && typeof state === "object" ? state : {};
  if (mode.error) return "Could not load internships.";
  if (mode.emptyDataset) return "No internships are listed yet.";
  if (!Number.isFinite(count) || count <= 0) return "No internships match these filters.";
  if (count === 1) return "1 internship";
  return `${count.toLocaleString("en-US")} internships`;
}

// "Northwind Robotics" -> "NR", "Acme" -> "A", "3M Labs" -> "3L". Letters and
// digits only; "?" when nothing usable remains.
function initials(company) {
  const words = asText(company)
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean);
  if (!words.length) return "?";
  const first = [...words[0]][0];
  const second = words.length > 1 ? [...words[1]][0] : "";
  return (first + second).toUpperCase();
}

// Deterministic FNV-1a hash -> one of AVATAR_COLORS palette slots.
function avatarColor(company) {
  const text = asText(company).trim().toLowerCase();
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash % AVATAR_COLORS;
}

const DEFAULT_CRITERIA = Object.freeze({
  query: "",
  company: "",
  term: "",
  location: "",
  roles: [],
  remoteOnly: false,
  newOnly: false,
  topOnly: false,
  sort: "newest",
});

// URL query <-> criteria. Short keys keep shared links readable:
// ?q=robot&role=SWE,ML/AI&term=Summer+2027&loc=austin&remote=1&new=1&top=1&company=X&sort=oldest
function criteriaFromQuery(search) {
  let params;
  try {
    params = new URLSearchParams(typeof search === "string" ? search : "");
  } catch {
    params = new URLSearchParams();
  }
  const flag = (key) => params.get(key) === "1";
  const roleParam = params.get("role") || "";
  const roles = ROLE_LABELS.filter((label) =>
    roleParam.split(",").map((part) => part.trim().toLowerCase()).includes(label.toLowerCase())
  );
  const sort = params.get("sort");
  return {
    query: (params.get("q") || "").slice(0, 200),
    company: (params.get("company") || "").slice(0, 200),
    term: (params.get("term") || "").slice(0, 100),
    location: (params.get("loc") || "").slice(0, 200),
    roles,
    remoteOnly: flag("remote"),
    newOnly: flag("new"),
    topOnly: flag("top"),
    sort: SORTS.includes(sort) ? sort : "newest",
  };
}

function criteriaToQuery(criteria) {
  const c = { ...DEFAULT_CRITERIA, ...(criteria || {}) };
  const params = new URLSearchParams();
  const text = (key, value) => {
    const trimmed = asText(value).trim();
    if (trimmed) params.set(key, trimmed);
  };
  text("q", c.query);
  const roles = ROLE_LABELS.filter((label) => Array.isArray(c.roles) && c.roles.includes(label));
  if (roles.length) params.set("role", roles.join(","));
  text("term", c.term);
  text("loc", c.location);
  if (c.remoteOnly) params.set("remote", "1");
  if (c.newOnly) params.set("new", "1");
  if (c.topOnly) params.set("top", "1");
  text("company", c.company);
  if (c.sort === "oldest") params.set("sort", "oldest");
  const out = params.toString();
  return out ? `?${out}` : "";
}

// Number of narrowing filters in use (search and sort excluded).
function activeFilterCount(criteria) {
  const c = { ...DEFAULT_CRITERIA, ...(criteria || {}) };
  return (
    (Array.isArray(c.roles) ? c.roles.length : 0) +
    [c.term, c.location, c.company].filter((v) => asText(v).trim()).length +
    [c.remoteOnly, c.newOnly, c.topOnly].filter(Boolean).length
  );
}

// "/" focuses search unless the person is already typing somewhere.
function isSearchShortcut(event) {
  if (!event || event.key !== "/") return false;
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  const target = event.target || {};
  if (target.isContentEditable) return false;
  const tag = asText(target.tagName).toUpperCase();
  return !["INPUT", "TEXTAREA", "SELECT"].includes(tag);
}

const api = {
  DATA_URL,
  NEW_WINDOW_MS,
  PAGE_SIZE,
  ROLE_LABELS,
  AVATAR_COLORS,
  DEFAULT_CRITERIA,
  listCompanies,
  listTerms,
  compareTerms,
  normalizeJobs,
  prepareJobs,
  inferRoles,
  jobRoles,
  isRemote,
  isNew,
  filterJobs,
  roleCounts,
  sortJobs,
  sanitizeUrl,
  formatAge,
  formatRelative,
  resultLabel,
  initials,
  avatarColor,
  criteriaFromQuery,
  criteriaToQuery,
  activeFilterCount,
  isSearchShortcut,
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = api;
}
globalThis.JobBoard = api;
