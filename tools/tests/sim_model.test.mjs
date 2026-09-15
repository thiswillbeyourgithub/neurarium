// Unit tests for public/js/sim-model.js (the simulation maths), run by
// `node --test tools/tests/sim_model.test.mjs` and, from the Python suite, by
// tools/tests/test_sim_model.py. Pure functions only: no DOM, no data files.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  TMAX_HOURS, P_FLOOR, bindingSign, toAxis, fromAxis, halfLifeHours, pkCurve,
  ligandsOf, receptorProfile, pkFlags, buildMatrix, nnls, solveCombination,
} from "../../public/js/sim-model.js";

const ki = (median) => ({ median });
const drug = (id, bindings, extra = {}) => ({
  id, name: id, bindings, metabolites: [], halfLife: { hours: 10 }, enzymes: [], ...extra,
});
const bind = (target, effect, median, extra = {}) => ({ target, targetName: target, effect, ki: ki(median), ...extra });

test("bindingSign: boost +1, block -1, modulate +0.5, affinity-only null", () => {
  assert.equal(bindingSign(bind("d2", "boost", 1)), 1);
  assert.equal(bindingSign(bind("d2", "block", 1)), -1);
  assert.equal(bindingSign(bind("d2", "modulate", 1)), 0.5);
  assert.equal(bindingSign({ target: "d2", affinityOnly: true, ki: ki(1) }), null);
});

test("axis: symmetric log, 1 nM reads 4, 10 uM reads ~0.3, round-trips", () => {
  assert.ok(Math.abs(toAxis(1) - 4) < 1e-3);
  assert.ok(Math.abs(toAxis(P_FLOOR) - Math.log10(2)) < 1e-9);
  assert.ok(Math.abs(toAxis(-1) + 4) < 1e-3);
  for (const v of [0, 1e-5, 3e-3, -0.7, 2]) assert.ok(Math.abs(fromAxis(toAxis(v)) - v) < 1e-12 + 1e-9 * Math.abs(v));
});

test("halfLifeHours: midpoint of a range, null when absent", () => {
  assert.equal(halfLifeHours({ hours: 21, hours_max: 54 }), 37.5);
  assert.equal(halfLifeHours({ hours: 6 }), 6);
  assert.equal(halfLifeHours(null), null);
});

test("pkCurve: peaks at TMAX_HOURS with height 1, halves every T½ late on", () => {
  const c = pkCurve(20);
  assert.ok(Math.abs(c.tmax - TMAX_HOURS) < 1e-6);
  assert.ok(Math.abs(c.at(c.tmax) - 1) < 1e-9);
  assert.ok(c.at(1) < 1 && c.at(1) > 0);
  // Far past the peak absorption is over, so the ratio over one T½ is 1/2.
  assert.ok(Math.abs(c.at(220) / c.at(200) - 0.5) < 1e-3);
  assert.equal(c.at(0), 0);
});

test("pkCurve: a very short T½ peaks early rather than failing", () => {
  const c = pkCurve(0.5);
  assert.ok(c.tmax < TMAX_HOURS && c.tmax > 0);
  assert.ok(Math.abs(c.at(c.tmax) - 1) < 1e-9);
});

test("ligandsOf: metabolite rides the parent's ke and can be toggled off", () => {
  const parent = drug("flx", [bind("sert", "boost", 1)], {
    halfLife: { hours: 48 },
    metabolites: [{ name: "norflx", halfLife: { hours: 240 }, bindings: [bind("sert", "boost", 2)] }],
  });
  const ligs = ligandsOf(parent);
  assert.equal(ligs.length, 2);
  assert.ok(Math.abs(ligs[1].curve.ka - ligs[0].curve.ke) < 1e-12);
  assert.ok(ligs[1].curve.tmax > ligs[0].curve.tmax);
  assert.equal(ligandsOf(parent, { metabolites: false }).length, 1);
});

test("receptorProfile: sums per direction, keeps unknown apart, flags assumed Ki", () => {
  const a = drug("a", [bind("d2", "boost", 10), bind("h1", "block", 100)]);
  const b = drug("b", [bind("d2", "block", 5), { target: "s1", targetName: "s1", affinityOnly: true, ki: ki(50) },
    { target: "m1", targetName: "m1", effect: "boost", ki: null }]);
  const { rows, flags } = receptorProfile([{ drug: a, ratio: 1 }, { drug: b, ratio: 2 }]);
  const byT = Object.fromEntries(rows.map((r) => [r.target, r]));
  assert.ok(Math.abs(byT.d2.boost - 0.1) < 1e-12);
  assert.ok(Math.abs(byT.d2.block + 0.4) < 1e-12);
  assert.ok(Math.abs(byT.s1.unknown - 0.04) < 1e-12);
  assert.equal(byT.s1.boost, 0);
  assert.ok(Math.abs(byT.m1.boost - 0.02) < 1e-12); // assumed 100 nM -> 0.01, ×ratio 2
  assert.deepEqual(flags.map((f) => f.kind).sort(), ["assumedKi", "unknownDirection"]);
  assert.ok(Math.abs(byT.d2.perLigand.get("b") + 0.4) < 1e-12);
});

test("receptorProfile at a time weights each ligand by its curve", () => {
  const a = drug("a", [bind("d2", "boost", 1)], { halfLife: { hours: 10 } });
  const peak = receptorProfile([{ drug: a, ratio: 1 }], { t: TMAX_HOURS }).rows[0].boost;
  const later = receptorProfile([{ drug: a, ratio: 1 }], { t: 100 }).rows[0].boost;
  assert.ok(Math.abs(peak - 1) < 1e-6);
  assert.ok(later < 0.01);
});

test("pkFlags: shared substrate once, inhibitor -> substrate directed", () => {
  const a = drug("a", [], { enzymes: [{ enzyme: "cyp2d6", role: "substrate" }, { enzyme: "cyp3a4", role: "inhibitor" }] });
  const b = drug("b", [], { enzymes: [{ enzyme: "cyp2d6", role: "substrate" }, { enzyme: "cyp3a4", role: "substrate" }] });
  const flags = pkFlags([{ drug: a }, { drug: b }]);
  assert.deepEqual(flags.map((f) => [f.kind, f.a, f.b, f.enzyme]).sort(), [
    ["inhibits", "a", "b", "cyp3a4"], ["sharedSubstrate", "a", "b", "cyp2d6"],
  ]);
});

test("nnls: recovers a non-negative mix, zeroes a negative one", () => {
  const c1 = Float64Array.from([1, 0, 1]), c2 = Float64Array.from([0, 1, 1]), c3 = Float64Array.from([-1, 1, 0]);
  const y = Float64Array.from([2, 3, 5]); // = 2·c1 + 3·c2
  const x = nnls([c1, c2, c3], y);
  assert.ok(Math.abs(x[0] - 2) < 1e-6 && Math.abs(x[1] - 3) < 1e-6 && Math.abs(x[2]) < 1e-6);
  const x2 = nnls([c1], Float64Array.from([-1, 0, -1]));
  assert.equal(x2[0], 0);
});

test("solveCombination: finds the drug whose profile is the target, respects fixed + cap", () => {
  const a = drug("a", [bind("d2", "block", 10), bind("h1", "block", 100)]);
  const b = drug("b", [bind("sert", "boost", 1)]);
  const c = drug("c", [bind("d2", "block", 20), bind("sert", "boost", 1), bind("a1", "block", 1)]);
  // 2×a + 2×b exactly; the h1 row pins a at 2 (c has no h1), which then leaves c no
  // room on d2, so the solution is unique despite three columns.
  const target = new Map([["d2", -0.2], ["sert", 2], ["h1", -0.02]]);
  const r = solveCombination(target, [a, b, c], { maxDrugs: 3 });
  const picks = Object.fromEntries(r.picks.map((p) => [p.drug.id, p.ratio]));
  assert.ok(r.fit > 0.99, `fit ${r.fit}`);
  assert.ok(Math.abs(picks.a - 2) < 1e-3 && Math.abs(picks.b - 2) < 1e-3, JSON.stringify(picks));
  // With a already fixed at 2, only b is needed.
  const r2 = solveCombination(target, [a, b, c], { fixed: [{ drug: a, ratio: 2 }] });
  assert.deepEqual(r2.picks.map((p) => p.drug.id), ["b"]);
  // onlyListed=false penalizes c's off-target a1 block; c still not chosen.
  const r3 = solveCombination(target, [a, b, c], { onlyListed: false });
  assert.ok(!r3.picks.some((p) => p.drug.id === "c"));
  // A cap of 1 drug keeps the strongest single contributor.
  const r4 = solveCombination(target, [a, b, c], { maxDrugs: 1 });
  assert.equal(r4.picks.length, 1);
  assert.equal(r.rows, 3);
  assert.deepEqual(r.picks.map((p) => p.opposes), [[], []]);
});

test("solveCombination: a pick that pulls against a wish is named as opposing it", () => {
  const blocker = drug("blk", [bind("d2", "block", 1)]);
  const agonist = drug("ago", [bind("d2", "boost", 1)]);
  // The fixed blocker overshoots a mild d2-block wish; the only way down is the agonist.
  const r = solveCombination(new Map([["d2", -0.1]]), [agonist], { fixed: [{ drug: blocker, ratio: 1 }] });
  assert.deepEqual(r.picks.map((p) => [p.drug.id, p.opposes]), [["ago", ["d2"]]]);
});

test("buildMatrix: skips direction-less bindings and drugs engaging no row", () => {
  const a = drug("a", [{ target: "d2", affinityOnly: true, ki: ki(1) }, bind("h1", "block", 1)]);
  const { cols } = buildMatrix([a], ["d2"]);
  assert.equal(cols.length, 0);
  assert.equal(buildMatrix([a], ["d2", "h1"]).cols[0].vec[1], -1);
});
