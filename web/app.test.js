const test = require("node:test");
const assert = require("node:assert/strict");
const {
  DATA_URL,
  NEW_WINDOW_MS,
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
  assert.deepEqual(listTerms(jobs), ["Fall 2026", "Summer 2026"]);
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
