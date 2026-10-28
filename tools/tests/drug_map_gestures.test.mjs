// Drugs map camera bounds (public/js/drug-map/gestures.js clampBox): the reader cannot zoom
// out past MAX_UNZOOM x the fitted frame, nor pan so far that more than half the screen
// shows empty space past it.
// Run: node --test tools/tests/

import test from "node:test";
import assert from "node:assert/strict";
import { clampBox, MAX_UNZOOM } from "../../public/js/drug-map/gestures.js";

const fit = { x: 0, y: 0, w: 1000, h: 600 };

test("a box inside the fitted frame is left alone", () => {
  const b = { x: 100, y: 50, w: 500, h: 300 };
  assert.deepEqual(clampBox(b, fit), b);
});

test("zooming out stops at MAX_UNZOOM, about the box centre", () => {
  const b = clampBox({ x: -500, y: -300, w: 2000, h: 1200 }, fit);
  assert.equal(b.w, 1000 * MAX_UNZOOM);
  assert.ok(Math.abs(b.h - 600 * MAX_UNZOOM) < 1e-9);
  assert.ok(Math.abs(b.x + b.w / 2 - 500) < 1e-9 && Math.abs(b.y + b.h / 2 - 300) < 1e-9);
});

test("a pan stops with the box centre on the frame edge (half the screen empty)", () => {
  assert.equal(clampBox({ x: 900, y: 0, w: 500, h: 300 }, fit).x, 750);
  assert.equal(clampBox({ x: -900, y: 0, w: 500, h: 300 }, fit).x, -250);
  assert.equal(clampBox({ x: 0, y: 2000, w: 500, h: 300 }, fit).y, 450);
  assert.equal(clampBox({ x: 0, y: -2000, w: 500, h: 300 }, fit).y, -150);
});
