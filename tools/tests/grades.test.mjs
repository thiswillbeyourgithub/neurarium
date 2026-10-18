// Unit tests for public/js/grades.js, run by tools/tests/test_js_units.py via
// `node --test`: the one home of the grade orderings and the rules built on them.
import test from "node:test";
import assert from "node:assert/strict";
import {
  GRADE_RANK, DISPLAY_GRADE_ORDER, strongestGrade, shownGrade, backed,
} from "../../public/js/grades.js";

test("strongestGrade picks the best stored grade, null when none", () => {
  assert.equal(strongestGrade([{ provenance: "llm" }, { provenance: "verified" },
    { provenance: "sourced" }]), "verified");
  assert.equal(strongestGrade([]), null);
  assert.equal(strongestGrade(null), null);
  assert.equal(strongestGrade([{ provenance: "bogus" }]), null);
});

test("shownGrade lifts only a backed grade with doubt to uncertain", () => {
  assert.equal(shownGrade("verified", [{}]), "uncertain");
  assert.equal(shownGrade("sourced", [{}]), "uncertain");
  assert.equal(shownGrade("llm", [{}]), "llm");
  assert.equal(shownGrade("verified", []), "verified");
});

test("display order agrees with the stored rank and slots uncertain/unknown", () => {
  for (const [a, b] of [["llm", "sourced"], ["sourced", "verified"]]) {
    assert.ok(GRADE_RANK[a] < GRADE_RANK[b]);
    assert.ok(DISPLAY_GRADE_ORDER[a] < DISPLAY_GRADE_ORDER[b]);
  }
  assert.ok(DISPLAY_GRADE_ORDER.sourced < DISPLAY_GRADE_ORDER.uncertain);
  assert.ok(DISPLAY_GRADE_ORDER.uncertain < DISPLAY_GRADE_ORDER.verified);
  assert.ok(DISPLAY_GRADE_ORDER.nosource < DISPLAY_GRADE_ORDER.unknown);
  assert.ok(DISPLAY_GRADE_ORDER.unknown < DISPLAY_GRADE_ORDER.llm);
});

test("backed sums verified + uncertain + sourced, missing fields as 0", () => {
  assert.equal(backed({ verified: 3, uncertain: 2, sourced: 1, llm: 9 }), 6);
  assert.equal(backed({ llm: 4 }), 0);
});
