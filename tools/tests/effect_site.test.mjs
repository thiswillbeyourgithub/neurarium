// Unit tests for public/js/effect-site.js: the central / peripheral effect filter.
// A "both" effect passes either filter; a row with no site never hides.
// Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { EFFECT_SITE_MODES, filterBySite, siteShown } from "../../public/js/effect-site.js";

const rows = [
  { effect: "sedation", site: "central" },
  { effect: "dry_mouth", site: "peripheral" },
  { effect: "nausea", site: "both" },
  { effect: "unplaced" },
];
const ids = (mode) => filterBySite(rows, mode).map((r) => r.effect);

test("all keeps every row", () => {
  assert.deepEqual(ids("all"), ["sedation", "dry_mouth", "nausea", "unplaced"]);
});

test("central drops peripheral only", () => {
  assert.deepEqual(ids("central"), ["sedation", "nausea", "unplaced"]);
});

test("peripheral drops central only", () => {
  assert.deepEqual(ids("peripheral"), ["dry_mouth", "nausea", "unplaced"]);
});

test("siteShown and the modes", () => {
  assert.deepEqual(EFFECT_SITE_MODES, ["all", "central", "peripheral"]);
  assert.equal(siteShown("peripheral", "central"), false);
  assert.equal(siteShown("both", "peripheral"), true);
  assert.deepEqual(filterBySite(null, "central"), []);
});
