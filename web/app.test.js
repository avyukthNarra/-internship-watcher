const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
  DATA_URL,
  NEW_WINDOW_MS,
  PAGE_SIZE,
  ROLE_LABELS,
  AVATAR_COLORS,
  DEFAULT_CRITERIA,
  inferRoles,
  jobRoles,
  prepareJobs,
  isRemote,
  isNew,
  roleCounts,
  formatRelative,
  initials,
  avatarColor,
  criteriaFromQuery,
  criteriaToQuery,
  activeFilterCount,
  isSearchShortcut,
  compareTerms,
  filterJobs,
  sortJobs,
  sanitizeUrl,
  formatAge,
  resultLabel,
  listCompanies,
  listTerms,
  normalizeJobs,
} = require("./jobs.js");

const NOW = new Date("2026-11-25T00:00:00.000Z");

function job(overrides) {
  return {
    id: "id",
    company: "Northwind Robotics",
    title: "Software Intern",
    location: "Austin, TX",
    url: "https://example.com/jobs/1",
    terms: ["Summer 2026"],
    source: "greenhouse",
    first_seen: "2026-11-24T12:00:00.000Z",
    top: false,
    ...overrides,
  };
}

test("DATA_URL is the sample file", () => {
  assert.equal(DATA_URL, "./sample-jobs.json");
  assert.equal(NEW_WINDOW_MS, 24 * 60 * 60 * 1000);
});

test("search matches company, title, and location only", () => {
  const jobs = [
    job({ id: "1", company: "Cedar Circuit", title: "PCB Intern", location: "Boulder, CO" }),
    job({ id: "2", title: "Robotics Intern", company: "Other Lab", location: "Seattle, WA" }),
    job({ id: "3", company: "Harborline", title: "Analyst", location: "Remote, US" }),
    job({
      id: "4",
      company: "Plain Co",
      title: "Writer",
      location: "Boston, MA",
      source: "remote-feed",
      terms: ["Remote Term"],
    }),
  ];

  assert.deepEqual(filterJobs(jobs, { query: "cedar" }, NOW).map((item) => item.id), ["1"]);
  assert.deepEqual(filterJobs(jobs, { query: "ROBOT" }, NOW).map((item) => item.id), ["2"]);
  assert.deepEqual(filterJobs(jobs, { query: "  remote " }, NOW).map((item) => item.id), ["3"]);
  assert.deepEqual(filterJobs(jobs, { query: "remote-feed" }, NOW).map((item) => item.id), []);
  assert.deepEqual(filterJobs(jobs, { query: "Remote Term" }, NOW).map((item) => item.id), []);
  assert.deepEqual(filterJobs(jobs, { query: "a+b?" }, NOW).map((item) => item.id), []);
});

test("company, term, and location filters combine", () => {
  const jobs = [
    job({ id: "1", company: "Northwind Robotics", terms: ["Summer 2026", "Fall 2026"], location: "Austin, TX" }),
    job({ id: "2", company: "Northwind Robotics ", terms: ["Fall 2026"], location: "New York, NY" }),
    job({ id: "3", company: "Other", terms: ["Summer 2026"], location: "Austin, TX" }),
    job({ id: "4", company: "Northwind Robotics", terms: [], location: "Austin, TX" }),
  ];

  assert.deepEqual(
    filterJobs(jobs, { company: "Northwind Robotics", term: "summer 2026", location: "austin" }, NOW).map((item) => item.id),
    ["1"]
  );
  assert.deepEqual(filterJobs(jobs, { term: "Fall 2026" }, NOW).map((item) => item.id), ["1", "2"]);
  assert.deepEqual(listCompanies(jobs), ["Northwind Robotics", "Other"]);
  assert.deepEqual(listTerms(jobs), ["Summer 2026", "Fall 2026"]); // chronological
});

test("new and top filters use first_seen and boolean top", () => {
  const jobs = [
    job({ id: "edge", first_seen: "2026-11-24T00:00:00.000Z", top: true }),
    job({ id: "inside", first_seen: "2026-11-24T00:00:00.001Z", top: false }),
    job({ id: "old", first_seen: "2026-11-23T23:59:59.999Z", top: true }),
    job({ id: "future", first_seen: "2026-11-25T00:00:00.001Z", top: true }),
    job({ id: "bad", first_seen: "nope", top: true }),
    job({ id: "string-top", first_seen: "2026-11-24T12:00:00.000Z", top: "true" }),
    job({ id: "missing", first_seen: undefined, top: true }),
  ];

  assert.deepEqual(filterJobs(jobs, { newOnly: true }, NOW).map((item) => item.id), ["edge", "inside", "string-top"]);
  assert.deepEqual(filterJobs(jobs, { topOnly: true }, NOW).map((item) => item.id), ["edge", "old", "future", "bad", "missing"]);
  assert.deepEqual(
    filterJobs(jobs, { newOnly: true, topOnly: true }, NOW).map((item) => item.id),
    ["edge"]
  );
});

test("filter does not mutate the input and ignores non-objects", () => {
  const jobs = [job({ id: "1" }), null, "nope", job({ id: "2" })];
  const snapshot = JSON.parse(JSON.stringify(jobs));
  const matched = filterJobs(jobs, { query: "" }, NOW);
  assert.deepEqual(jobs, snapshot);
  assert.notEqual(matched, jobs);
  assert.deepEqual(matched.map((item) => item.id), ["1", "2"]);
});

test("sort is newest first by default and keeps invalid dates last", () => {
  const jobs = [
    job({ id: "mid", first_seen: "2026-06-01T00:00:00.000Z" }),
    job({ id: "new", first_seen: "2026-11-01T00:00:00.000Z" }),
    job({ id: "tie-a", first_seen: "2026-01-01T00:00:00.000Z" }),
    job({ id: "bad", first_seen: "" }),
    job({ id: "tie-b", first_seen: "2026-01-01T00:00:00.000Z" }),
    job({ id: "old", first_seen: "2025-01-01T00:00:00.000Z" }),
  ];

  assert.deepEqual(sortJobs(jobs).map((item) => item.id), ["new", "mid", "tie-a", "tie-b", "old", "bad"]);
  assert.deepEqual(sortJobs(jobs, "newest").map((item) => item.id), ["new", "mid", "tie-a", "tie-b", "old", "bad"]);
  assert.deepEqual(sortJobs(jobs, "oldest").map((item) => item.id), ["old", "tie-a", "tie-b", "mid", "new", "bad"]);
  assert.equal(jobs[0].id, "mid");
});

test("sanitizeUrl allows only http and https", () => {
  assert.equal(sanitizeUrl("https://example.com/jobs/1"), "https://example.com/jobs/1");
  assert.equal(sanitizeUrl("  http://example.com/a?b=1&c=2  "), "http://example.com/a?b=1&c=2");
  assert.equal(sanitizeUrl("HTTPS://example.com/ok"), "https://example.com/ok");
  assert.equal(sanitizeUrl("javascript:alert(1)"), null);
  assert.equal(sanitizeUrl("data:text/html,hi"), null);
  assert.equal(sanitizeUrl("ftp://example.com/file"), null);
  assert.equal(sanitizeUrl("//example.com/jobs"), null);
  assert.equal(sanitizeUrl("not a url"), null);
  assert.equal(sanitizeUrl(""), null);
  assert.equal(sanitizeUrl("   "), null);
  assert.equal(sanitizeUrl(null), null);
  assert.equal(sanitizeUrl(undefined), null);
  assert.equal(sanitizeUrl(12), null);
});

test("formatAge uses relative buckets", () => {
  assert.equal(formatAge("2026-11-25T00:00:00.000Z", NOW), "First seen just now");
  assert.equal(formatAge("2026-11-24T23:59:30.000Z", NOW), "First seen just now");
  assert.equal(formatAge("2026-11-24T23:58:00.000Z", NOW), "First seen 2 minutes ago");
  assert.equal(formatAge("2026-11-24T23:00:00.000Z", NOW), "First seen 1 hour ago");
  assert.equal(formatAge("2026-11-24T21:00:00.000Z", NOW), "First seen 3 hours ago");
  assert.equal(formatAge("2026-11-24T00:00:00.000Z", NOW), "First seen 1 day ago");
  assert.equal(formatAge("2026-11-20T00:00:00.000Z", NOW), "First seen 5 days ago");
  assert.equal(formatAge("2026-10-25T00:00:00.000Z", NOW), "First seen 1 month ago");
  assert.equal(formatAge("2026-08-25T00:00:00.000Z", NOW), "First seen 3 months ago");
  assert.equal(formatAge("2025-11-25T00:00:00.000Z", NOW), "First seen 1 year ago");
  assert.equal(
    formatAge(new Date(NOW.getTime() - 360 * 24 * 60 * 60 * 1000).toISOString(), NOW),
    "First seen 12 months ago"
  );
  assert.equal(formatAge("2024-11-25T00:00:00.000Z", NOW), "First seen 2 years ago");
  assert.equal(formatAge("nope", NOW), "First seen date unknown");
  assert.equal(formatAge("2026-11-25T01:00:00.000Z", NOW), "First seen in the future");
});

test("result labels cover count, empty, and error", () => {
  assert.equal(resultLabel(0), "No internships match these filters.");
  assert.equal(resultLabel(1), "1 internship");
  assert.equal(resultLabel(30), "30 internships");
  assert.equal(resultLabel(0, { emptyDataset: true }), "No internships are listed yet.");
  assert.equal(resultLabel(4, { error: true }), "Could not load internships.");
});

test("normalizeJobs accepts an array and rejects other payloads", () => {
  const jobs = [job({ id: "1" }), null, ["nested"], job({ id: "2" })];
  assert.deepEqual(normalizeJobs(jobs).map((item) => item.id), ["1", "2"]);
  assert.equal(normalizeJobs({ jobs: [] }), null);
  assert.equal(normalizeJobs("[]"), null);
});

test("inferRoles mirrors the alert channel keywords with whole-word matching", () => {
  assert.deepEqual(inferRoles("Software Engineer Intern"), ["SWE"]);
  assert.deepEqual(inferRoles("Machine Learning Research Intern"), ["ML/AI", "Research"]);
  assert.deepEqual(inferRoles("Embedded Software Intern"), ["Embedded"]);
  assert.deepEqual(inferRoles("PCB Design Intern"), ["Hardware"]);
  assert.deepEqual(inferRoles("FPGA Hardware Intern"), ["Embedded"]);
  assert.deepEqual(inferRoles("Quantitative Trader Intern"), ["Quant"]);
  assert.deepEqual(inferRoles("Data Analyst Intern"), ["Data"]);
  assert.deepEqual(inferRoles("AI Platform Intern"), ["SWE", "ML/AI"]);
  assert.deepEqual(inferRoles("International Sales Intern"), []);
  assert.deepEqual(inferRoles("Retail Associate"), []);
  assert.deepEqual(inferRoles(""), []);
  assert.deepEqual(inferRoles(undefined), []);
});

test("jobRoles prefers exported roles and falls back to the title", () => {
  assert.deepEqual(jobRoles(job({ title: "Software Intern", roles: ["Quant"] })), ["Quant"]);
  assert.deepEqual(jobRoles(job({ title: "Software Intern", roles: [] })), []);
  assert.deepEqual(jobRoles(job({ roles: ["Data", "Bogus", 7, "SWE"] })), ["SWE", "Data"]);
  assert.deepEqual(jobRoles(job({ title: "Data Science Intern" })), ["Data"]);
  assert.deepEqual(jobRoles(job({ title: "Data Science Intern", roles: "Data" })), ["Data"]);
  assert.deepEqual(jobRoles(null), []);
});

test("prepareJobs resolves roles without mutating the payload", () => {
  const input = [job({ id: "a", title: "Firmware Intern" }), job({ id: "b", roles: ["Research"] })];
  const snapshot = JSON.parse(JSON.stringify(input));
  const prepared = prepareJobs(input);
  assert.deepEqual(input, snapshot);
  assert.deepEqual(prepared.map((item) => item.roles), [["Embedded"], ["Research"]]);
  assert.deepEqual(prepareJobs(null), []);
});

test("role filter matches any selected role; remote filter reads location", () => {
  const jobs = [
    job({ id: "swe", title: "Backend Intern", location: "Remote in USA" }),
    job({ id: "ml", title: "ML Intern", roles: ["ML/AI"], location: "Austin, TX" }),
    job({ id: "both", title: "x", roles: ["SWE", "ML/AI"], location: "Remote" }),
    job({ id: "none", title: "Design Intern", location: "Remotely, OR" }),
  ];
  const ids = (criteria) => filterJobs(jobs, criteria, NOW).map((item) => item.id);
  assert.deepEqual(ids({ roles: ["SWE"] }), ["swe", "both"]);
  assert.deepEqual(ids({ roles: ["SWE", "ML/AI"] }), ["swe", "ml", "both"]);
  assert.deepEqual(ids({ roles: ["Nope"] }), ["swe", "ml", "both", "none"]);
  assert.deepEqual(ids({ remoteOnly: true }), ["swe", "both"]);
  assert.deepEqual(ids({ remoteOnly: true, roles: ["ML/AI"] }), ["both"]);
  assert.equal(isRemote("Hybrid / REMOTE"), true);
  assert.equal(isRemote(undefined), false);
});

test("roleCounts ignore the role filter but honor the others", () => {
  const jobs = [
    job({ id: "1", roles: ["SWE"], top: true }),
    job({ id: "2", roles: ["SWE", "Data"], top: false }),
    job({ id: "3", roles: ["Quant"], top: true }),
  ];
  const counts = roleCounts(jobs, { roles: ["Quant"], topOnly: true }, NOW);
  assert.equal(counts.SWE, 1);
  assert.equal(counts.Data, 0);
  assert.equal(counts.Quant, 1);
  assert.deepEqual(Object.keys(counts), ROLE_LABELS);
});

test("isNew uses the 24 hour window", () => {
  assert.equal(isNew(job({ first_seen: "2026-11-24T00:00:00.000Z" }), NOW), true);
  assert.equal(isNew(job({ first_seen: "2026-11-23T23:59:59.000Z" }), NOW), false);
  assert.equal(isNew(job({ first_seen: "2026-11-25T01:00:00.000Z" }), NOW), false);
  assert.equal(isNew(null, NOW), false);
});

test("formatRelative uses compact buckets", () => {
  assert.equal(formatRelative("2026-11-25T00:00:00.000Z", NOW), "now");
  assert.equal(formatRelative("2026-11-24T23:59:30.000Z", NOW), "now");
  assert.equal(formatRelative("2026-11-24T23:55:00.000Z", NOW), "5m ago");
  assert.equal(formatRelative("2026-11-24T22:00:00.000Z", NOW), "2h ago");
  assert.equal(formatRelative("2026-11-22T00:00:00.000Z", NOW), "3d ago");
  assert.equal(formatRelative("2026-09-25T00:00:00.000Z", NOW), "2mo ago");
  assert.equal(formatRelative("2025-11-01T00:00:00.000Z", NOW), "1y ago");
  assert.equal(formatRelative("2026-11-25T02:00:00.000Z", NOW), "");
  assert.equal(formatRelative("nope", NOW), "");
});

test("initials and avatar colors are deterministic", () => {
  assert.equal(initials("Northwind Robotics"), "NR");
  assert.equal(initials("acme"), "A");
  assert.equal(initials("3M Labs Inc"), "3L");
  assert.equal(initials("  Thistle & Finch "), "TF");
  assert.equal(initials("Émile Ōkubo"), "ÉŌ");
  assert.equal(initials("!!!"), "?");
  assert.equal(initials(null), "?");
  const color = avatarColor("Northwind Robotics");
  assert.equal(avatarColor("Northwind Robotics"), color);
  assert.equal(avatarColor(" northwind robotics "), color);
  for (const name of ["", "a", "Aldermoor Labs", "Brightloom", "x".repeat(500)]) {
    const value = avatarColor(name);
    assert.ok(Number.isInteger(value) && value >= 0 && value < AVATAR_COLORS);
  }
  const spread = new Set(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"].map(avatarColor));
  assert.ok(spread.size >= 5);
});

test("criteria round-trip through the URL query", () => {
  const criteria = {
    query: "robot arm",
    company: "Thistle & Finch",
    term: "Summer 2027",
    location: "austin",
    roles: ["ML/AI", "SWE"],
    remoteOnly: true,
    newOnly: true,
    topOnly: false,
    sort: "oldest",
  };
  const query = criteriaToQuery(criteria);
  assert.ok(query.startsWith("?"));
  assert.ok(!query.includes("top="));
  assert.deepEqual(criteriaFromQuery(query), { ...criteria, roles: ["SWE", "ML/AI"] });
  assert.equal(criteriaToQuery(DEFAULT_CRITERIA), "");
  assert.equal(criteriaToQuery({ query: "   " }), "");
  assert.deepEqual(criteriaFromQuery(""), { ...DEFAULT_CRITERIA });
});

test("criteriaFromQuery ignores junk and normalizes roles", () => {
  const parsed = criteriaFromQuery("?role=swe,bogus,quant&sort=random&new=yes&top=1&q=" + "x".repeat(500));
  assert.deepEqual(parsed.roles, ["SWE", "Quant"]);
  assert.equal(parsed.sort, "newest");
  assert.equal(parsed.newOnly, false);
  assert.equal(parsed.topOnly, true);
  assert.equal(parsed.query.length, 200);
  assert.deepEqual(criteriaFromQuery(undefined), { ...DEFAULT_CRITERIA });
});

test("activeFilterCount counts narrowing filters only", () => {
  assert.equal(activeFilterCount({}), 0);
  assert.equal(activeFilterCount({ query: "x", sort: "oldest" }), 0);
  assert.equal(
    activeFilterCount({ roles: ["SWE", "Data"], term: "Fall 2026", location: " ", remoteOnly: true, topOnly: true }),
    5
  );
});

test("slash shortcut skips form fields, editable content, and modifiers", () => {
  const key = (target, extra) => ({ key: "/", target, ...extra });
  assert.equal(isSearchShortcut(key({ tagName: "BODY" })), true);
  assert.equal(isSearchShortcut(key({ tagName: "button" })), true);
  assert.equal(isSearchShortcut(key({ tagName: "INPUT" })), false);
  assert.equal(isSearchShortcut(key({ tagName: "TEXTAREA" })), false);
  assert.equal(isSearchShortcut(key({ tagName: "SELECT" })), false);
  assert.equal(isSearchShortcut(key({ tagName: "DIV", isContentEditable: true })), false);
  assert.equal(isSearchShortcut(key({ tagName: "BODY" }, { metaKey: true })), false);
  assert.equal(isSearchShortcut({ key: "a", target: { tagName: "BODY" } }), false);
  assert.equal(isSearchShortcut(null), false);
});

test("terms sort chronologically, then alphabetically", () => {
  assert.deepEqual(
    ["Summer 2027", "Co-op", "Fall 2026", "Spring 2027", "Winter 2027", "Fall 2027"].sort(compareTerms),
    ["Fall 2026", "Winter 2027", "Spring 2027", "Summer 2027", "Fall 2027", "Co-op"]
  );
  assert.deepEqual(listTerms([job({ terms: ["Summer 2027", "Spring 2027"] })]), ["Spring 2027", "Summer 2027"]);
});

test("result labels group thousands", () => {
  assert.equal(resultLabel(3412), "3,412 internships");
  assert.equal(PAGE_SIZE, 50);
});

test("sample data is fictional and covers every role", () => {
  const sample = JSON.parse(fs.readFileSync(path.join(__dirname, "sample-jobs.json"), "utf8"));
  assert.ok(sample.length >= 30);
  const keys = ["company", "first_seen", "id", "location", "roles", "source", "terms", "title", "top", "url"];
  const seenRoles = new Set();
  for (const item of sample) {
    assert.deepEqual(Object.keys(item).sort(), keys);
    assert.ok(item.url === "" || item.url.startsWith("https://example.com/"), item.url);
    for (const role of item.roles) {
      assert.ok(ROLE_LABELS.includes(role), role);
      seenRoles.add(role);
    }
  }
  assert.deepEqual([...seenRoles].sort(), [...ROLE_LABELS].sort());
  assert.deepEqual(sortJobs(sample).map((item) => item.id), sample.map((item) => item.id));
});

test("Netlify and Vercel configs send the same security headers", () => {
  const vercel = JSON.parse(fs.readFileSync(path.join(__dirname, "vercel.json"), "utf8"));
  const netlify = fs.readFileSync(path.join(__dirname, "_headers"), "utf8");

  // Parse Netlify's `_headers`: a path line followed by indented `Key: value` lines.
  const netlifyRules = {};
  let current = null;
  for (const line of netlify.split("\n")) {
    if (!line.trim() || line.trim().startsWith("#")) continue;
    if (!/^\s/.test(line)) {
      current = line.trim();
      netlifyRules[current] = {};
    } else {
      const at = line.indexOf(":");
      netlifyRules[current][line.slice(0, at).trim().toLowerCase()] = line.slice(at + 1).trim();
    }
  }
  const vercelRules = Object.fromEntries(
    vercel.headers.map((rule) => [
      rule.source,
      Object.fromEntries(rule.headers.map((h) => [h.key.toLowerCase(), h.value])),
    ])
  );

  const site = netlifyRules["/*"];
  assert.deepEqual(vercelRules["/(.*)"], site);
  assert.match(site["content-security-policy"], /^default-src 'self';/);
  assert.match(site["content-security-policy"], /frame-ancestors 'none'/);
  assert.equal(site["x-content-type-options"], "nosniff");
  assert.equal(site["referrer-policy"], "strict-origin-when-cross-origin");

  for (const file of ["/jobs.json", "/sample-jobs.json"]) {
    const cache = netlifyRules[file]["cache-control"];
    assert.match(cache, /max-age=60\b/);
    const vercelRule = vercel.headers.find((rule) => new RegExp(`^${rule.source}$`).test(file) && rule.source !== "/(.*)");
    assert.ok(vercelRule, file);
    assert.equal(vercelRule.headers.find((h) => h.key === "Cache-Control").value, cache);
  }

  const meta = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
  assert.match(meta, /http-equiv="Content-Security-Policy" content="default-src 'self'/);
});
