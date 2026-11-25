// DOM layer. All job text goes in through textContent; pure logic is in jobs.js.
const board = globalThis.JobBoard;

const $ = (selector) => document.querySelector(selector);
const el = {
  topbar: $("#topbar"),
  searchForm: $("#search-form"),
  search: $("#search"),
  filtersToggle: $("#filters-toggle"),
  filtersCount: $("#filters-count"),
  roleChips: [...document.querySelectorAll(".chip[data-role]")],
  term: $("#term"),
  location: $("#location"),
  remote: $("#remote-only"),
  fresh: $("#new-only"),
  top: $("#top-only"),
  sort: $("#sort"),
  status: $("#status"),
  active: $("#active-filters"),
  clear: $("#clear"),
  results: $("#results"),
  skeleton: $("#skeleton"),
  empty: $("#empty"),
  emptyTitle: $("#empty-title"),
  emptyBody: $("#empty-body"),
  emptyClear: $("#empty-clear"),
  error: $("#error"),
  retry: $("#retry"),
  moreRow: $("#more-row"),
  more: $("#more"),
  moreNote: $("#more-note"),
};

const SVG_NS = "http://www.w3.org/2000/svg";
const STAR = "m10 2.5 2.3 4.7 5.2.8-3.8 3.6.9 5.1L10 14.3l-4.6 2.4.9-5.1L2.5 8l5.2-.8L10 2.5Z";
const ARROW = "M7 13 13 7M8 7h5v5";

let jobs = [];
let matched = [];
let shown = 0;
let loaded = false;
let criteria = board.criteriaFromQuery(location.search);

function icon(d, className, { fill = false } = {}) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  if (className) svg.setAttribute("class", className);
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", d);
  if (fill) {
    path.setAttribute("fill", "currentColor");
  } else {
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.8");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
  }
  svg.append(path);
  return svg;
}

function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

// ---------------------------------------------------------------- controls

function setPressed(button, on) {
  button.setAttribute("aria-pressed", on ? "true" : "false");
}

function syncControls() {
  el.search.value = criteria.query;
  el.location.value = criteria.location;
  ensureOption(el.term, criteria.term);
  el.term.value = criteria.term;
  el.sort.value = criteria.sort;
  setPressed(el.remote, criteria.remoteOnly);
  setPressed(el.fresh, criteria.newOnly);
  setPressed(el.top, criteria.topOnly);
  for (const chip of el.roleChips) setPressed(chip, criteria.roles.includes(chip.dataset.role));
}

// A shared link may name a term that is not in today's data; keep it selectable
// so the view stays honest (it just shows zero results).
function ensureOption(select, value) {
  if (!value || [...select.options].some((option) => option.value === value)) return;
  const option = node("option", "", value);
  option.value = value;
  select.append(option);
}

function fillTerms(terms) {
  el.term.replaceChildren();
  const all = node("option", "", "All terms");
  all.value = "";
  el.term.append(all);
  for (const term of terms) {
    const option = node("option", "", term);
    option.value = term;
    el.term.append(option);
  }
  ensureOption(el.term, criteria.term);
  el.term.value = criteria.term;
}

function setCriteria(changes, { history: mode = "replace" } = {}) {
  criteria = { ...criteria, ...changes };
  syncControls();
  writeUrl(mode);
  update();
}

function writeUrl(mode) {
  const next = `${location.pathname}${board.criteriaToQuery(criteria)}${location.hash}`;
  if (next === `${location.pathname}${location.search}${location.hash}`) return;
  if (mode === "push") history.pushState(null, "", next);
  else history.replaceState(null, "", next);
}

function renderActive() {
  el.active.replaceChildren();
  if (criteria.company) {
    const pill = node("button", "pill");
    pill.type = "button";
    pill.setAttribute("aria-label", `Remove company filter: ${criteria.company}`);
    pill.append(node("span", "pill-key", "Company"), node("span", "pill-value", criteria.company));
    pill.append(icon("M6 6l8 8M14 6l-8 8", "pill-x"));
    pill.addEventListener("click", () => {
      setCriteria({ company: "" }, { history: "push" });
      el.search.focus();
    });
    el.active.append(pill);
  }
  const count = board.activeFilterCount(criteria);
  el.clear.hidden = count === 0 && !criteria.query;
  el.filtersCount.hidden = count === 0;
  el.filtersCount.textContent = count ? String(count) : "";
  el.filtersToggle.setAttribute("aria-label", count ? `Filters, ${count} active` : "Filters");
}

function renderRoleCounts(now) {
  const counts = board.roleCounts(jobs, criteria, now);
  for (const chip of el.roleChips) {
    const count = counts[chip.dataset.role] || 0;
    chip.querySelector(".chip-count").textContent = count.toLocaleString("en-US");
    chip.classList.toggle("is-zero", count === 0);
  }
}

// ---------------------------------------------------------------- rows

function renderJob(job, now) {
  const item = node("li", "job");
  const title = text(job.title) || "Untitled role";
  const company = text(job.company) || "Unknown company";

  const avatar = node("div", `avatar av-${board.avatarColor(company)}`, board.initials(company));
  avatar.setAttribute("aria-hidden", "true");

  const main = node("div", "job-main");
  const head = node("div", "job-head");
  // Title and badges share one inline flow so badges follow the last word.
  head.append(node("h2", "job-title", title));
  if (board.isNew(job, now)) head.append(document.createTextNode(" "), node("span", "badge badge-new", "New"));
  if (job.top === true) {
    const top = node("span", "badge badge-top");
    top.append(icon(STAR, "badge-icon", { fill: true }), document.createTextNode("Top"));
    top.title = "Top company";
    head.append(document.createTextNode(" "), top);
  }

  const meta = node("div", "job-meta");
  const companyButton = node("button", "company", company);
  companyButton.type = "button";
  companyButton.title = `Show only ${company}`;
  companyButton.setAttribute("aria-label", `${company}: show only this company`);
  companyButton.addEventListener("click", () => {
    setCriteria({ company }, { history: "push" });
    window.scrollTo({ top: 0 });
    el.results.focus({ preventScroll: true });
  });
  // The dot is glued to the location with a no-break space so a wrapped
  // company name never leaves it alone on a line.
  const place = node("span", "location");
  const sep = node("span", "sep", "·");
  sep.setAttribute("aria-hidden", "true");
  place.append(sep, document.createTextNode(`\u00a0${text(job.location) || "Location not listed"}`));
  meta.append(companyButton, document.createTextNode(" "), place);

  const tags = node("ul", "tags");
  tags.setAttribute("aria-label", "Tags");
  for (const role of board.jobRoles(job)) tags.append(node("li", "tag tag-role", role));
  for (const term of Array.isArray(job.terms) ? job.terms : []) {
    const value = text(term);
    if (value) tags.append(node("li", "tag tag-term", value));
  }
  main.append(head, meta);

  const side = node("div", "job-side");
  const age = board.formatRelative(job.first_seen, now);
  if (age) {
    const time = node("time", "job-time", age);
    time.dateTime = text(job.first_seen);
    time.title = board.formatAge(job.first_seen, now);
    time.dataset.firstSeen = time.dateTime;
    side.append(time);
  }
  const href = board.sanitizeUrl(job.url);
  if (href) {
    const link = node("a", "apply", "Apply");
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", `Apply to ${title} at ${company} (opens in a new tab)`);
    link.append(icon(ARROW, "apply-icon"));
    side.append(link);
  } else {
    side.append(node("span", "no-link", "No link"));
  }

  item.append(avatar, main);
  if (tags.childElementCount) item.append(tags);
  item.append(side);
  return item;
}

function renderMore() {
  const remaining = matched.length - shown;
  el.moreRow.hidden = remaining <= 0;
  if (remaining > 0) {
    el.more.textContent = `Show ${Math.min(remaining, board.PAGE_SIZE)} more`;
    el.moreNote.textContent = `Showing ${shown.toLocaleString("en-US")} of ${matched.length.toLocaleString("en-US")}`;
  }
}

function appendPage() {
  const now = new Date();
  const next = Math.min(matched.length, shown + board.PAGE_SIZE);
  const fragment = document.createDocumentFragment();
  for (let i = shown; i < next; i += 1) fragment.append(renderJob(matched[i], now));
  el.results.append(fragment);
  shown = next;
  renderMore();
}

// ---------------------------------------------------------------- views

function update() {
  if (!loaded) return;
  const now = new Date();
  matched = board.sortJobs(board.filterJobs(jobs, criteria, now), criteria.sort);
  el.status.textContent = board.resultLabel(matched.length, { emptyDataset: jobs.length === 0 });
  renderActive();
  renderRoleCounts(now);
  el.results.replaceChildren();
  shown = 0;
  const empty = matched.length === 0;
  el.empty.hidden = !empty;
  if (empty) {
    const noData = jobs.length === 0;
    el.emptyTitle.textContent = noData ? "No internships listed yet" : "No internships match";
    el.emptyBody.textContent = noData
      ? "Check back soon. New postings appear here as they are found."
      : "Try removing a filter or searching for something broader.";
    el.emptyClear.hidden = noData;
  }
  appendPage();
}

function showSkeleton(on) {
  if (on && !el.skeleton.childElementCount) {
    for (let i = 0; i < 8; i += 1) {
      const row = node("li", "job");
      row.append(node("div", "sk sk-avatar"));
      const main = node("div", "job-main");
      main.append(node("div", "sk sk-line sk-title"), node("div", "sk sk-line sk-meta"));
      row.append(main, node("div", "sk sk-button"));
      el.skeleton.append(row);
    }
  }
  el.skeleton.hidden = !on;
}

function showLoading() {
  loaded = false;
  el.status.textContent = "Loading internships…";
  el.error.hidden = true;
  el.empty.hidden = true;
  el.moreRow.hidden = true;
  el.results.replaceChildren();
  for (const chip of el.roleChips) {
    chip.querySelector(".chip-count").textContent = "";
    chip.classList.remove("is-zero");
  }
  showSkeleton(true);
}

function showError() {
  loaded = false;
  jobs = [];
  showSkeleton(false);
  el.status.textContent = board.resultLabel(0, { error: true });
  el.error.hidden = false;
}

async function load() {
  showLoading();
  try {
    const response = await fetch(board.DATA_URL, { credentials: "omit" });
    if (!response.ok) throw new Error(String(response.status));
    const normalized = board.normalizeJobs(await response.json());
    if (!normalized) throw new Error("invalid jobs payload");
    jobs = board.prepareJobs(normalized);
    loaded = true;
    showSkeleton(false);
    fillTerms(board.listTerms(jobs));
    update();
  } catch {
    showError();
  }
}

function clearAll() {
  setCriteria({ ...board.DEFAULT_CRITERIA, sort: criteria.sort }, { history: "push" });
  el.search.focus();
}

// ---------------------------------------------------------------- events

let searchTimer = 0;
el.search.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    criteria = { ...criteria, query: el.search.value };
    writeUrl("replace");
    update();
  }, 120);
});
el.search.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (el.search.value) {
    el.search.value = "";
    setCriteria({ query: "" });
  } else {
    el.search.blur();
  }
});
el.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  clearTimeout(searchTimer);
  setCriteria({ query: el.search.value });
  if (matched.length) el.results.focus();
});

let locationTimer = 0;
el.location.addEventListener("input", () => {
  clearTimeout(locationTimer);
  locationTimer = setTimeout(() => {
    criteria = { ...criteria, location: el.location.value };
    writeUrl("replace");
    update();
  }, 120);
});

for (const chip of el.roleChips) {
  chip.addEventListener("click", () => {
    const role = chip.dataset.role;
    const roles = criteria.roles.includes(role)
      ? criteria.roles.filter((item) => item !== role)
      : [...criteria.roles, role];
    setCriteria({ roles });
  });
}
el.remote.addEventListener("click", () => setCriteria({ remoteOnly: !criteria.remoteOnly }));
el.fresh.addEventListener("click", () => setCriteria({ newOnly: !criteria.newOnly }));
el.top.addEventListener("click", () => setCriteria({ topOnly: !criteria.topOnly }));
el.term.addEventListener("change", () => setCriteria({ term: el.term.value }));
el.sort.addEventListener("change", () => setCriteria({ sort: el.sort.value }));
el.clear.addEventListener("click", clearAll);
el.emptyClear.addEventListener("click", clearAll);
el.retry.addEventListener("click", () => load());
el.more.addEventListener("click", () => appendPage());

el.filtersToggle.addEventListener("click", () => {
  const open = el.filtersToggle.getAttribute("aria-expanded") !== "true";
  el.filtersToggle.setAttribute("aria-expanded", open ? "true" : "false");
  el.topbar.classList.toggle("is-open", open);
});

document.addEventListener("keydown", (event) => {
  if (!board.isSearchShortcut(event)) return;
  event.preventDefault();
  el.search.focus();
  el.search.select();
});

window.addEventListener("popstate", () => {
  criteria = board.criteriaFromQuery(location.search);
  syncControls();
  update();
});

// Load the next page before the person reaches the button.
if ("IntersectionObserver" in window) {
  new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting) && loaded && shown < matched.length) {
      appendPage();
    }
  }, { rootMargin: "600px 0px" }).observe(el.moreRow);
}

// Keep relative times honest on a tab left open.
setInterval(() => {
  const now = new Date();
  for (const time of el.results.querySelectorAll("time[data-first-seen]")) {
    time.textContent = board.formatRelative(time.dataset.firstSeen, now) || time.textContent;
    time.title = board.formatAge(time.dataset.firstSeen, now);
  }
}, 60 * 1000);

// The full placeholder truncates on phones.
const narrow = window.matchMedia("(max-width: 720px)");
const setPlaceholder = () => {
  el.search.placeholder = narrow.matches ? "Search" : "Search company, title, location";
};
setPlaceholder();
narrow.addEventListener("change", setPlaceholder);

syncControls();
load();
