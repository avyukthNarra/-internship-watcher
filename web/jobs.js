// Shared by the browser (globalThis.JobBoard) and Node tests (module.exports).
// The published data URL lives only in DATA_URL.

const DATA_URL = "./sample-jobs.json";
const NEW_WINDOW_MS = 24 * 60 * 60 * 1000;

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

function uniqueSorted(values) {
  const seen = new Set();
  const out = [];
  for (const value of values) {
    if (!value || seen.has(value)) continue;
    seen.add(value);
    out.push(value);
  }
  out.sort((a, b) => a.localeCompare(b, "en"));
  return out;
}

function isWithinLast(iso, nowMs, windowMs) {
  const then = Date.parse(iso);
  if (!Number.isFinite(then) || !Number.isFinite(nowMs)) return false;
  const delta = nowMs - then;
  return delta >= 0 && delta <= windowMs;
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
  return uniqueSorted(terms);
}

function normalizeJobs(data) {
  if (!Array.isArray(data)) return null;
  return data.filter((job) => job !== null && typeof job === "object" && !Array.isArray(job));
}

function filterJobs(jobs, criteria, now) {
  const source = Array.isArray(jobs) ? jobs : [];
  const options = criteria && typeof criteria === "object" ? criteria : {};
  const query = normalizeQuery(options.query);
  const company = asText(options.company).trim();
  const term = asText(options.term).trim().toLowerCase();
  const location = normalizeQuery(options.location);
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
    if (newOnly && !isWithinLast(job.first_seen, nowMs, NEW_WINDOW_MS)) return false;
    if (topOnly && job.top !== true) return false;
    return true;
  });
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

function resultLabel(count, state) {
  const mode = state && typeof state === "object" ? state : {};
  if (mode.error) return "Could not load internships.";
  if (mode.emptyDataset) return "No internships are listed yet.";
  if (!Number.isFinite(count) || count <= 0) return "No internships match these filters.";
  if (count === 1) return "1 internship";
  return `${count} internships`;
}

const api = {
  DATA_URL,
  NEW_WINDOW_MS,
  listCompanies,
  listTerms,
  normalizeJobs,
  filterJobs,
  sortJobs,
  sanitizeUrl,
  formatAge,
  resultLabel,
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = api;
}
globalThis.JobBoard = api;
