// Unit tests for quoteLines (public/js/panel/format.js), run by
// tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";

// format.js reads the i18n global at load.
globalThis.window = { __I18N__: { t: (k) => k, lang: "en" } };
const { quoteLines } = await import("../../public/js/panel/format.js");

test("a labelled parsed table row reads one field per line", () => {
  assert.equal(quoteLines("Drugs: Lithium | Laboratory alert level: 1.2 mmol/L"),
    "Drugs: Lithium\nLaboratory alert level: 1.2 mmol/L");
});

test("an unlabelled cell row or plain prose stays on one line", () => {
  assert.equal(quoteLines("5-HT2A | 120 | Human"), "5-HT2A | 120 | Human");
  assert.equal(quoteLines("Note: this is a sentence."), "Note: this is a sentence.");
  assert.equal(quoteLines("Ki: 3 nM | 5-HT2A"), "Ki: 3 nM | 5-HT2A");
});
