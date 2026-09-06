import test from "node:test";
import assert from "node:assert/strict";
import { failureStreak, isHourlyReminder, runScheduled } from "./worker.js";

const originalFetch = globalThis.fetch;

test.afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("uses workflow-specific runs endpoint and detects a failure streak", async () => {
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    if (options?.method === "POST") return new Response(null, { status: 204 });
    return Response.json({ workflow_runs: [
      { conclusion: "failure", html_url: "https://github.com/run/2" },
      { conclusion: "cancelled", html_url: "https://github.com/run/1" },
      { conclusion: "success" },
    ] });
  };
  const result = await runScheduled(
    { scheduledTime: "2026-09-06T12:00:00.000Z" },
    { GH_PAT: "token", DISCORD_WEBHOOK_URL: "https://discord.test/hook" },
  );
  assert.equal(result.problems.length, 1);
  assert.match(requests[1].url, /actions\/workflows\/watch\.yml\/runs\?status=completed&branch=main/);
  assert.equal(requests[1].options.method, undefined);
  assert.equal(requests[2].options.method, "POST");
});

test("handles GitHub network errors and failed alert delivery", async () => {
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    if (url.includes("dispatches")) throw new Error("offline");
    if (url.includes("/runs?")) return new Response("bad gateway", { status: 502 });
    return new Response("no", { status: 503 });
  };
  const result = await runScheduled(
    { scheduledTime: "2026-09-06T12:07:00.000Z" },
    { GH_PAT: "token", DISCORD_WEBHOOK_URL: "https://discord.test/hook" },
  );
  assert.equal(result.reminder, true);
  assert.equal(result.problems.length, 2);
  assert.equal(calls.length, 3);
});

test("detects a stale successful run", async () => {
  const messages = [];
  globalThis.fetch = async (url, options) => {
    if (options?.method === "POST") {
      messages.push(JSON.parse(options.body).content);
      return new Response(null, { status: 204 });
    }
    return Response.json({ workflow_runs: [{
      conclusion: "success",
      completed_at: "2026-09-06T10:00:00Z",
      html_url: "https://github.com/run/old",
    }] });
  };
  await runScheduled(
    { scheduledTime: Date.parse("2026-09-06T12:00:00.000Z") },
    { GH_PAT: "token", DISCORD_WEBHOOK_URL: "https://discord.test/hook" },
  );
  assert.match(messages.at(-1), /latest successful run is 120 minutes old/);
});

test("does not deliver non-hourly failure alerts", async () => {
  let alertCalls = 0;
  globalThis.fetch = async (url, options) => {
    if (url.includes("discord.test")) alertCalls += 1;
    if (options?.method === "POST") throw new Error("offline");
    return new Response("bad gateway", { status: 502 });
  };
  const result = await runScheduled(
    { scheduledTime: "2026-09-06T12:10:00.000Z" },
    { GH_PAT: "token", DISCORD_WEBHOOK_URL: "https://discord.test/hook" },
  );
  assert.equal(result.reminder, false);
  assert.equal(result.problems.length, 2);
  assert.equal(alertCalls, 0);
});

test("hourly gating uses the scheduled event time and is stateless", () => {
  assert.equal(isHourlyReminder("2026-09-06T12:00:00Z"), true);
  assert.equal(isHourlyReminder("2026-09-06T12:09:00Z"), true);
  assert.equal(isHourlyReminder("2026-09-06T12:10:00Z"), false);
  assert.deepEqual(failureStreak([
    { conclusion: "failure" },
    { conclusion: "cancelled" },
    { conclusion: "success" },
  ]), 2);
});
