const board = globalThis.JobBoard;

const form = document.querySelector("#filters");
const status = document.querySelector("#status");
const retryRow = document.querySelector("#retry-row");
const retry = document.querySelector("#retry");
const results = document.querySelector("#results");
const companySelect = document.querySelector("#company");
const termSelect = document.querySelector("#term");

let jobs = [];
let loaded = false;

function criteriaFromForm() {
  const data = new FormData(form);
  return {
    query: String(data.get("query") || ""),
    company: String(data.get("company") || ""),
    term: String(data.get("term") || ""),
    location: String(data.get("location") || ""),
    newOnly: data.get("newOnly") != null,
    topOnly: data.get("topOnly") != null,
    sort: String(data.get("sort") || "newest"),
  };
}

function fillSelect(select, values, allLabel) {
  const current = select.value;
  select.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = allLabel;
  select.append(all);
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
  if (current && [...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function renderJob(job, now) {
  const item = document.createElement("li");
  item.className = "job";

  const titleText = boardText(job.title) || "Untitled role";
  const companyText = boardText(job.company) || "Unknown company";

  const heading = document.createElement("h2");
  heading.className = "job-title";
  heading.textContent = titleText;

  const company = document.createElement("p");
  company.className = "job-company";
  company.textContent = companyText;

  const location = document.createElement("p");
  location.className = "job-location";
  location.textContent = boardText(job.location) || "Location not listed";

  const terms = document.createElement("ul");
  terms.className = "terms";
  const termList = Array.isArray(job.terms) ? job.terms : [];
  for (const term of termList) {
    const text = boardText(term).trim();
    if (!text) continue;
    const termItem = document.createElement("li");
    termItem.textContent = text;
    terms.append(termItem);
  }

  const seen = document.createElement("p");
  seen.className = "job-seen";
  seen.textContent = board.formatAge(job.first_seen, now);

  item.append(heading, company, location);
  if (terms.childElementCount) item.append(terms);
  if (job.top === true) {
    const badge = document.createElement("p");
    badge.className = "badge";
    badge.textContent = "Top";
    item.append(badge);
  }
  item.append(seen);

  const href = board.sanitizeUrl(job.url);
  if (href) {
    const link = document.createElement("a");
    link.className = "apply";
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Apply";
    link.setAttribute("aria-label", `Apply to ${titleText} at ${companyText}`);
    item.append(link);
  } else {
    const missing = document.createElement("p");
    missing.className = "no-link";
    missing.textContent = "No apply link";
    item.append(missing);
  }

  return item;
}

function boardText(value) {
  return typeof value === "string" ? value : "";
}

function render() {
  if (!loaded) return;
  const now = new Date();
  const criteria = criteriaFromForm();
  const matched = board.sortJobs(board.filterJobs(jobs, criteria, now), criteria.sort);
  status.textContent = board.resultLabel(matched.length, { emptyDataset: jobs.length === 0 });
  retryRow.hidden = true;
  results.replaceChildren(...matched.map((job) => renderJob(job, now)));
}

function showLoading() {
  loaded = false;
  status.textContent = "Loading internships…";
  retryRow.hidden = true;
  results.replaceChildren();
}

function showError() {
  loaded = false;
  jobs = [];
  status.textContent = board.resultLabel(0, { error: true });
  retryRow.hidden = false;
  results.replaceChildren();
}

async function load() {
  showLoading();
  try {
    const response = await fetch(board.DATA_URL);
    if (!response.ok) throw new Error(String(response.status));
    const payload = await response.json();
    const normalized = board.normalizeJobs(payload);
    if (!normalized) throw new Error("invalid jobs payload");
    jobs = normalized;
    loaded = true;
    fillSelect(companySelect, board.listCompanies(jobs), "All companies");
    fillSelect(termSelect, board.listTerms(jobs), "All terms");
    render();
  } catch {
    showError();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  render();
});
form.addEventListener("input", () => {
  render();
});
retry.addEventListener("click", () => {
  load();
});

load();
