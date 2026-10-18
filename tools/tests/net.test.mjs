// Unit tests for public/js/net.js, run by tools/tests/test_js_units.py via
// `node --test`: the shared fetch + status check, with a stubbed global fetch.
import test from "node:test";
import assert from "node:assert/strict";
import { fetchOk, fetchJson } from "../../public/js/net.js";

const stub = (ok, status, body) => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push([url, init]);
    return { ok, status, statusText: "Not Found", json: async () => body };
  };
  return calls;
};

test("fetchJson passes init through and parses the body", async () => {
  const calls = stub(true, 200, { a: 1 });
  assert.deepEqual(await fetchJson("x.json", { cache: "no-store" }), { a: 1 });
  assert.deepEqual(calls, [["x.json", { cache: "no-store" }]]);
});

test("fetchOk throws HTTP <status> by default, the caller's message otherwise", async () => {
  stub(false, 404);
  await assert.rejects(fetchOk("x"), { message: "HTTP 404" });
  await assert.rejects(fetchOk("x", undefined, (r) => `x: ${r.status} ${r.statusText}`),
    { message: "x: 404 Not Found" });
});
