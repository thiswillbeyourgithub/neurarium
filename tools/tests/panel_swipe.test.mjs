// swipeStep (public/js/boot/panel-swipe.js): a header swipe moves the panel one size.
import { test } from "node:test";
import assert from "node:assert/strict";
import { swipeStep } from "../../public/js/boot/panel-swipe.js";

test("up grows one step, down shrinks one step, the ends stay put", () => {
  assert.equal(swipeStep("collapsed", "up"), "half");
  assert.equal(swipeStep("half", "up"), "full");
  assert.equal(swipeStep("full", "up"), "full");
  assert.equal(swipeStep("full", "down"), "half");
  assert.equal(swipeStep("half", "down"), "collapsed");
  assert.equal(swipeStep("collapsed", "down"), "collapsed");
});
