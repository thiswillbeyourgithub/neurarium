// Unit tests for public/js/changelog.js createChangelog().open(), run by
// tools/tests/test_js_units.py via `node --test`. The DOM is stubbed to the few
// globals the module touches (no `#changelog-body`, so render() is a no-op).
import test from "node:test";
import assert from "node:assert/strict";
import { createChangelog } from "../../public/js/changelog.js";

const KEY = "neurarium.changelogSeen";

function setup(fetchImpl) {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
  };
  globalThis.document = { getElementById: () => null, documentElement: { lang: "en" } };
  globalThis.fetch = fetchImpl;
  let opened = 0;
  const log = createChangelog({
    version: "3.131.1",
    sourceUrl: "",
    t: (k) => k,
    pick: (x) => x,
    wireModal: () => ({ open: () => { opened += 1; }, close() {}, isOpen: false }),
  });
  return { log, store, opened: () => opened };
}

test("opening offline does not mark the running build as seen", async () => {
  // Regression: seenMark() falls back to the build when nothing loaded, so an
  // offline open burned every unread release.
  const { log, store, opened } = setup(async () => { throw new TypeError("offline"); });
  await log.open();
  assert.equal(opened(), 1, "the modal still opens, showing the empty message");
  assert.equal(store.has(KEY), false);
});

test("opening online records the newest shipped release", async () => {
  const versions = [{ version: "3.131.0", date: "2026-10-17", items: [] }];
  const { log, store } = setup(async () => ({ ok: true, json: async () => ({ versions }) }));
  await log.open();
  assert.equal(store.get(KEY), "3.131.0");
});

test("concurrent loads share one fetch, and a failed load is retried", async () => {
  // Regression: the resolved value was cached, so two opens racing the first
  // fetch each fired their own request.
  let calls = 0;
  let fail = true;
  const versions = [{ version: "3.131.0", date: "2026-10-17", items: [] }];
  const { log } = setup(async () => {
    calls += 1;
    await new Promise((r) => setTimeout(r, 5));
    if (fail) throw new TypeError("offline");
    return { ok: true, json: async () => ({ versions }) };
  });
  await Promise.all([log.open(), log.open()]);
  assert.equal(calls, 1, "two concurrent opens fetch once");
  fail = false;
  await log.open();
  assert.equal(calls, 2, "the failed load was evicted, so the next open retries");
  await log.open();
  assert.equal(calls, 2, "a successful load is cached");
});
