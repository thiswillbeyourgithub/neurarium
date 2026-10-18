// Unit tests for public/js/i18n.js t / tHtml, run by tools/tests/test_js_units.py
// via `node --test`. i18n.js is a classic script (an IIFE that sets
// window.__I18N__), so it runs in a vm context with the few browser globals it
// touches stubbed.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// The string tables load first, as in index.html: i18n.js reads them off a global.
const SRC = ["i18n/en.js", "i18n/fr.js", "i18n.js"]
  .map((f) => readFileSync(new URL(`../../public/js/${f}`, import.meta.url), "utf8"));

function loadI18n() {
  const window = { location: { search: "" } };
  const ctx = {
    window,
    URLSearchParams,
    localStorage: { getItem: () => "en", setItem() {} },
    navigator: { languages: ["en"] },
    document: { documentElement: {}, addEventListener() {} },
  };
  vm.createContext(ctx);
  for (const src of SRC) vm.runInContext(src, ctx);
  return window.__I18N__;
}

test("tHtml escapes interpolated values, t leaves them raw", () => {
  const { t, tHtml } = loadI18n();
  const evil = '<img src=x onerror="alert(1)">&';
  assert.equal(t("tour.step", { n: evil, total: 2 }).includes(evil), true);
  const safe = tHtml("tour.step", { n: evil, total: 2 });
  assert.equal(safe.includes("<img"), false);
  assert.ok(safe.includes("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;"));
});

test("tHtml keeps the catalogue entry's own markup and equals t without vars", () => {
  const { t, tHtml } = loadI18n();
  assert.equal(tHtml("tour.welcome.body"), t("tour.welcome.body"));
  assert.equal(tHtml("no.such.key"), "no.such.key");
});
