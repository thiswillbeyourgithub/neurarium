// Unit tests for the empty-section wording of public/js/panel/dom.js (lowerFirst,
// noDataText), run by tools/tests/test_js_units.py. Its Python twin
// (api_sections.lower_first / no_data) is pinned to the same examples in
// tools/tests/test_panel_md_parity.py, so the panel and /api placeholders agree.
import test from "node:test";
import assert from "node:assert/strict";

globalThis.window = globalThis.window || {};
await import("../../public/js/i18n/en.js");
const EN = window.__I18N_MESSAGES__.en;
window.__I18N__ = {
  t: (key, vars = {}) => Object.entries(vars)
    .reduce((s, [k, v]) => s.replaceAll(`{${k}}`, v), EN[key] ?? key),
};
const { lowerFirst, noDataText, sectionSelector } = await import("../../public/js/panel/dom.js");

test("sectionSelector finds a section by its tour anchor, else all its classes", () => {
  assert.equal(sectionSelector({ tourSec: "workup", cls: "info-locations" }),
    '[data-tour-sec="workup"]');
  assert.equal(sectionSelector({ cls: "info-connections info-tone" }),
    ".info-connections.info-tone");
  assert.equal(sectionSelector({ cls: "" }), null);
  assert.equal(sectionSelector(), null);
});

test("lowerFirst lowers a heading's first letter, never an acronym", () => {
  assert.equal(lowerFirst("Age and sex differences"), "age and sex differences");
  assert.equal(lowerFirst("CNS penetration"), "CNS penetration");
  assert.equal(lowerFirst("Pharmacogenomics"), "pharmacogenomics");
  assert.equal(lowerFirst(""), "");
  assert.equal(lowerFirst("A"), "a");
});

test("noDataText names the section and the panel's kind", () => {
  assert.equal(noDataText("Age and sex differences", "receptor"),
    "No information about age and sex differences for this receptor yet.");
  assert.equal(noDataText("CNS penetration", "drug"),
    "No information about CNS penetration for this drug yet.");
});

test("every kind the panels pass has its noun", () => {
  for (const kind of ["drug", "receptor", "target", "structure", "circuit", "group", "enzyme"])
    assert.ok(EN[`info.kindThis.${kind}`], kind);
});
