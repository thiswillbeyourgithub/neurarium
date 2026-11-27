// ringStale (public/js/tour/layout.js): the drift watch re-lays out a ring whose
// target moved with no scroll event (content reflowing in above the row), the race
// that left tour step "A whole system" tapping a stale ring.
import { test } from "node:test";
import assert from "node:assert/strict";
import { layoutStep, ringStale } from "../../public/js/tour/layout.js";

// A fake element whose box can move under the ring, like a reflowed panel row.
function fakeEl(rect) {
  const el = { rect, getClientRects: () => [1], getBoundingClientRect: () => ({ ...el.rect }) };
  return el;
}
const fakeNode = () => ({ hidden: false, style: {}, classList: { toggle() {} } });

function laidOut(row) {
  globalThis.window = { innerWidth: 1280, innerHeight: 800 };
  const st = { ring: fakeNode(), blocker: fakeNode(), bubble: { ...fakeNode(), offsetWidth: 200, offsetHeight: 100 } };
  const step = { target: row, dim: false };
  layoutStep(st, step);
  return { st, step };
}

test("a freshly laid-out ring is not stale", () => {
  const row = fakeEl({ left: 20, top: 475, right: 320, bottom: 505, width: 300, height: 30 });
  const { st, step } = laidOut(row);
  assert.equal(st.ring.style.top, "469px");
  assert.equal(ringStale(st, step), false);
});

test("a row that reflowed 10px under the ring makes it stale", () => {
  const row = fakeEl({ left: 20, top: 465, right: 320, bottom: 495, width: 300, height: 30 });
  const { st, step } = laidOut(row);
  row.rect = { ...row.rect, top: 475, bottom: 505 };
  assert.equal(ringStale(st, step), true);
  layoutStep(st, step);
  assert.equal(ringStale(st, step), false);
});

test("a hidden ring is never stale", () => {
  const row = fakeEl({ left: 0, top: 0, right: 10, bottom: 10, width: 10, height: 10 });
  const { st, step } = laidOut(row);
  st.ring.hidden = true;
  row.rect = { ...row.rect, top: 50, bottom: 60 };
  assert.equal(ringStale(st, step), false);
});
