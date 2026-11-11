// Unit tests for public/js/panel/find-in-panel.js fold + rankEntries (the Shift+F
// in-panel find), run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { fold, rankEntries } from "../../public/js/panel/find-in-panel.js";

const entry = (label, detail = "", alt = "", tip = "") =>
  ({ label, detail, section: "", target: null, text: fold(`${label} ${detail}`), alt: fold(alt), tip: fold(tip) });

test("fold lowercases, strips accents and punctuation", () => {
  assert.equal(fold("Demi-vie d'élimination"), "demi vie d elimination");
});

test("a translated label outranks a word buried in a longer label", () => {
  const rows = [
    entry("The French label (RCP) asks for these before starting"),
    entry("Originator", "Eli Lilly and Company", "Laboratoire d'origine"),
  ];
  assert.deepEqual(rankEntries(rows, "lab").map((e) => e.label),
    ["Originator", "The French label (RCP) asks for these before starting"]);
});

test("every word must match, tooltip hits rank last", () => {
  const rows = [
    entry("Time to peak", "6 h", "Délai du pic", "unlike the half-life"),
    entry("Plasma elimination half-life", "14 days", "Demi-vie"),
  ];
  assert.deepEqual(rankEntries(rows, "half").map((e) => e.label),
    ["Plasma elimination half-life", "Time to peak"]);
  assert.deepEqual(rankEntries(rows, "demi vie").map((e) => e.label), ["Plasma elimination half-life"]);
  assert.deepEqual(rankEntries(rows, "half zzz"), []);
  assert.deepEqual(rankEntries(rows, "  "), []);
});
