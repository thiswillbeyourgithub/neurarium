// Drugs map focus (public/js/drug-map/focus.js): which dot the pointer means, so a
// nameless dot in a crowded cluster still shows its name on hover / first tap.
// Run: node --test tools/tests/

import test from "node:test";
import assert from "node:assert/strict";
import { nearestDot, stickyNearest, NEAR_PX } from "../../public/js/drug-map/focus.js";

// Three dots in screen px: two touching (a cluster where layout.js drops a name), one apart.
const dots = [
  { id: "haloperidol", sx: 100, sy: 100 },
  { id: "fluphenazine", sx: 106, sy: 100 },
  { id: "clozapine", sx: 300, sy: 200 },
];

test("the nearest dot wins, even inside a tight cluster", () => {
  assert.equal(nearestDot(dots, 101, 100, NEAR_PX.mouse).id, "haloperidol");
  assert.equal(nearestDot(dots, 105, 101, NEAR_PX.mouse).id, "fluphenazine");
});

test("a pointer near, not on, a dot still means it", () => {
  assert.equal(nearestDot(dots, 320, 200, NEAR_PX.mouse).id, "clozapine"); // 20 px off
});

test("too far means nothing; a finger reaches farther than a mouse", () => {
  assert.equal(nearestDot(dots, 200, 150, NEAR_PX.mouse), null);
  assert.equal(nearestDot(dots, 328, 200, NEAR_PX.mouse), null); // 28 px off
  assert.equal(nearestDot(dots, 328, 200, NEAR_PX.touch).id, "clozapine");
  assert.equal(nearestDot([], 0, 0, NEAR_PX.touch), null);
});

// Hover hysteresis: between two close dots a plain nearest test flips at the midpoint, so a
// hand's jitter there flickered the focus between the two names.
test("the hovered dot holds against a near tie (jitter around the midpoint)", () => {
  // haloperidol at x=100, fluphenazine at x=106: midpoint 103.
  for (const x of [102.5, 103, 103.5, 104, 105]) {
    assert.equal(stickyNearest(dots, x, 100, "haloperidol", NEAR_PX.mouse, 8).id, "haloperidol");
  }
  // A plain nearest test flips there: the flicker this guards.
  assert.equal(nearestDot(dots, 103.5, 100, NEAR_PX.mouse).id, "fluphenazine");
});

test("a clearly closer dot takes the hover over", () => {
  const far = [{ id: "a", sx: 0, sy: 0 }, { id: "b", sx: 20, sy: 0 }];
  assert.equal(stickyNearest(far, 19, 0, "a", NEAR_PX.mouse, 8).id, "b"); // 19 vs 1
  assert.equal(stickyNearest(far, 12, 0, "a", NEAR_PX.mouse, 8).id, "a"); // 12 vs 8
});

test("the hover holds a little past the reach, then drops", () => {
  const one = [{ id: "a", sx: 0, sy: 0 }];
  assert.equal(stickyNearest(one, NEAR_PX.mouse + 4, 0, "a", NEAR_PX.mouse, 8).id, "a");
  assert.equal(stickyNearest(one, NEAR_PX.mouse + 9, 0, "a", NEAR_PX.mouse, 8), null);
  assert.equal(stickyNearest(one, NEAR_PX.mouse + 4, 0, null, NEAR_PX.mouse, 8), null);
  assert.equal(stickyNearest(dots, 101, 100, "gone", NEAR_PX.mouse, 8).id, "haloperidol");
});
