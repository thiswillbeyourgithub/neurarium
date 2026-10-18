// Unit tests for public/sw.js's fetch handler, run by tools/tests/test_js_units.py
// via `node --test`. sw.js is a classic worker script (no exports), so it is run in
// a vm context with stubbed `self`, `caches` and `fetch`, and the registered
// "fetch" listener is driven directly.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const SRC = readFileSync(new URL("../../public/sw.js", import.meta.url), "utf8");
const ORIGIN = "https://example.test";

// Load sw.js against a fake Cache API holding `stored` (url -> Response) and a
// network answering `network(request)`. Returns the fetch listener plus the store.
function loadWorker({ stored = {}, network }) {
  const store = new Map(Object.entries(stored));
  const listeners = {};
  const cache = {
    put: async (req, res) => { store.set(typeof req === "string" ? req : req.url, res); },
    add: async () => {},
  };
  const ctx = {
    self: {
      location: { origin: ORIGIN, href: `${ORIGIN}/sw.js` },
      addEventListener: (type, fn) => { listeners[type] = fn; },
      skipWaiting() {},
      clients: { claim: async () => {} },
    },
    caches: {
      match: async (req) => store.get(typeof req === "string" ? req : req.url),
      open: async () => cache,
      keys: async () => [],
    },
    fetch: async (req) => network(req),
    Headers, Request, Response, URL, Promise, Error,
  };
  vm.runInNewContext(SRC, ctx);
  return { onFetch: listeners.fetch, store };
}

// Fire one GET through the listener; resolves to { res, pending } where `pending`
// is everything the worker handed to event.waitUntil.
// A navigation is passed as a plain `{url, method, mode}` object, since node's
// Request refuses `mode: "navigate"`.
async function fire(onFetch, url, { navigate = false } = {}) {
  let answer;
  const pending = [];
  onFetch({
    request: navigate ? { url, method: "GET", mode: "navigate" } : new Request(url),
    respondWith: (p) => { answer = p; },
    waitUntil: (p) => { pending.push(p); },
  });
  const res = await answer;
  await Promise.all(pending);
  return { res, pending };
}

test("a server error falls back to the cached copy", async () => {
  // Regression: a 502 during a container restart beat the last good copy.
  const url = `${ORIGIN}/data/meta.json`;
  const { onFetch } = loadWorker({
    stored: { [url]: new Response("cached", { status: 200 }) },
    network: async () => new Response("bad gateway", { status: 502 }),
  });
  const { res } = await fire(onFetch, url);
  assert.equal(res.status, 200);
  assert.equal(await res.text(), "cached");
});

test("a server error with nothing cached is passed through", async () => {
  const url = `${ORIGIN}/data/none.json`;
  const { onFetch } = loadWorker({
    network: async () => new Response("bad gateway", { status: 502 }),
  });
  const { res } = await fire(onFetch, url);
  assert.equal(res.status, 502);
});

test("a fresh 200 is cached through waitUntil, not before answering", async () => {
  const url = `${ORIGIN}/js/main.js`;
  const { onFetch, store } = loadWorker({
    network: async () => new Response("fresh", { status: 200 }),
  });
  const { res, pending } = await fire(onFetch, url);
  assert.equal(await res.text(), "fresh");
  assert.equal(pending.length, 1, "cache write handed to event.waitUntil");
  assert.equal(await store.get(url).text(), "fresh");
});

test("shell navigations share the index.html cache key, whatever their query", async () => {
  // Regression: every `?lang=` / `?tour=` navigation was cached under its own full
  // URL, adding one entry per query string forever.
  const { onFetch, store } = loadWorker({
    network: async () => new Response("shell", { status: 200 }),
  });
  await fire(onFetch, `${ORIGIN}/?lang=fr`, { navigate: true });
  await fire(onFetch, `${ORIGIN}/index.html?tour=1`, { navigate: true });
  assert.deepEqual([...store.keys()], [`${ORIGIN}/index.html`]);
});

test("a non-shell navigation (an /api/ page) keeps its own key", async () => {
  const url = `${ORIGIN}/api/drug/caffeine.md`;
  const { onFetch, store } = loadWorker({
    network: async () => new Response("md", { status: 200 }),
  });
  await fire(onFetch, url, { navigate: true });
  assert.deepEqual([...store.keys()], [url]);
});
