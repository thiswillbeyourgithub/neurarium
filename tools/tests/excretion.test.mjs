// Unit tests for public/js/excretion.js (excretion grouping + wording),
// run by tools/tests/test_js_units.py via `node --test`. Built with the help of Claude Code.
import test from "node:test";
import assert from "node:assert/strict";
import { formatExcretion, formatValue, groupExcretion, localizeAspects }
  from "../../public/js/excretion.js";

const META = {
  route: { label: { en: "route", fr: "voie" }, values: { renal: { en: "urine", fr: "urines" } } },
  urine_ph: { label: { en: "urine pH", fr: "pH urinaire" }, values: { dependent: { en: "dep", fr: "dép" } } },
};

test("aspects localize with their values, in meta order", () => {
  const a = localizeAspects(META, (m) => m.fr);
  assert.deepEqual(Object.keys(a), ["route", "urine_ph"]);
  assert.deepEqual(a.route, { label: "voie", values: { renal: "urines" } });
  assert.deepEqual(localizeAspects(undefined, (m) => m.en), {});
});

test("rows group by aspect in vocabulary order, empty aspects dropped", () => {
  const a = localizeAspects(META, (m) => m.en);
  const rows = [{ aspect: "urine_ph", value: "dependent" }, { aspect: "route", value: "renal" }];
  assert.deepEqual(groupExcretion(rows, a).map((g) => [g.aspect, g.label, g.rows.length]),
    [["route", "route", 1], ["urine_ph", "urine pH", 1]]);
  assert.deepEqual(groupExcretion([rows[1]], a).map((g) => g.aspect), ["route"]);
  assert.deepEqual(groupExcretion(undefined, a), []);
});

test("a node reads as aspect, value, then its verbatim figure", () => {
  const n = { aspectLabel: "route", valueLabel: "urine (kidneys)", amount: "80%" };
  assert.equal(formatValue(n), "urine (kidneys) (80%)");
  assert.equal(formatExcretion(n), "route: urine (kidneys) (80%)");
  assert.equal(formatExcretion({ ...n, amount: null }), "route: urine (kidneys)");
});
