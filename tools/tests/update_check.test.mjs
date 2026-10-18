// Unit tests for public/js/update-check.js: reading version.js and deciding whether a
// tab should reload onto a newer deploy, run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { parseTried, extractAppVersion, RETRY_MS, shouldReload } from "../../public/js/update-check.js";

test("reads the version a version.js body declares", () => {
  assert.equal(extractAppVersion('// header\nwindow.__APP_VERSION__ = "3.128.0";\n'), "3.128.0");
  assert.equal(extractAppVersion("<html>not found</html>"), null);
  assert.equal(extractAppVersion(""), null);
});

test("reloads only for another version, once per version", () => {
  const now = 1_000_000_000;
  assert.equal(shouldReload("3.90.1", "3.122.0", null, now), true);
  assert.equal(shouldReload("3.122.0", "3.122.0", null, now), false);
  assert.equal(shouldReload("3.90.1", "3.122.0", { version: "3.122.0", at: now }, now), false,
    "no reload loop");
  assert.equal(shouldReload("3.90.1", null, null, now), false);
  assert.equal(shouldReload("3.90.1", "3.123.0", { version: "3.122.0", at: now }, now), true,
    "a newer deploy than the one tried reloads at once");
});

test("a reload that still landed old is retried later, or when back online", () => {
  // Regression: one failed reload (offline, the SW served the old build) blocked
  // every retry for the rest of the session.
  const at = 1_000_000_000;
  const tried = { version: "3.122.0", at };
  assert.equal(shouldReload("3.90.1", "3.122.0", tried, at + RETRY_MS - 1), false);
  assert.equal(shouldReload("3.90.1", "3.122.0", tried, at + RETRY_MS), true);
  assert.equal(shouldReload("3.90.1", "3.122.0", tried, at + 1, true), true, "online forces");
});

test("reads the stored attempt, old plain-string format included", () => {
  assert.equal(parseTried(null), null);
  assert.deepEqual(parseTried('{"version":"3.1.0","at":42}'), { version: "3.1.0", at: 42 });
  assert.deepEqual(parseTried("3.1.0"), { version: "3.1.0", at: 0 });
});
