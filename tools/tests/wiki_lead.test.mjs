// Unit tests for public/js/wiki.js clipLead (the collapsed Wikipedia lead preview),
// run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { clipLead, fetchWikiLead } from "../../public/js/wiki.js";

test("a lead that fits is returned whole, no ellipsis", () => {
  assert.equal(clipLead("Caffeine is a stimulant.", 300), "Caffeine is a stimulant.");
});

test("a long lead is cut at a word boundary with an ellipsis", () => {
  const out = clipLead("Caffeine is a central nervous system stimulant of the methylxanthine class", 30);
  assert.equal(out, "Caffeine is a central nervous…");
  assert.ok(out.length <= 31);
});

test("trailing punctuation before the cut is dropped", () => {
  assert.equal(clipLead("Alpha beta, gamma delta epsilon", 12), "Alpha beta…");
});

test("one huge token falls back to a hard cut", () => {
  assert.equal(clipLead("a " + "x".repeat(50), 20), "a " + "x".repeat(18) + "…");
});

test("fetchWikiLead: concurrent calls share one fetch, a failure is retried", async () => {
  // Regression: the resolved value was cached, so two panels opening the same
  // drug before the first answer each fired their own request.
  globalThis.sessionStorage = { getItem: () => null, setItem() {} };
  let calls = 0;
  let fail = true;
  globalThis.fetch = async () => {
    calls += 1;
    await new Promise((r) => setTimeout(r, 5));
    if (fail) throw new TypeError("offline");
    return { ok: true, json: async () => ({ query: { pages: { 1: { extract: "Caffeine is a stimulant." } } } }) };
  };
  const url = "https://en.wikipedia.org/wiki/Caffeine";
  const [a, b] = await Promise.all([fetchWikiLead(url, "en"), fetchWikiLead(url, "en")]);
  assert.equal(calls, 1);
  assert.equal(a, null);
  assert.equal(b, null);
  fail = false;
  const live = await fetchWikiLead(url, "en");
  assert.equal(calls, 2, "the failure was evicted");
  assert.deepEqual(live, { text: "Caffeine is a stimulant.", lang: "en" });
  await fetchWikiLead(url, "en");
  assert.equal(calls, 2, "a positive is cached");
});
