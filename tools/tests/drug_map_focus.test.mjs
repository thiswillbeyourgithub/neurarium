// Drugs map focus (public/js/drug-map/focus.js): which dot the pointer means, so a
// nameless dot in a crowded cluster still shows its name on hover / first tap.
// Run: node --test tools/tests/

import test from "node:test";
import assert from "node:assert/strict";
import { nearestDot, NEAR_PX } from "../../public/js/drug-map/focus.js";

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
