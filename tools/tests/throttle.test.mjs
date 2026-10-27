// throttleLatest (public/js/util.js): hover picking leans on it to keep a 1000 Hz mouse
// from running a ~8 ms raycast per move, which starved the auto-rotation.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import { throttleLatest } from "../../public/js/util.js";

test("a burst of calls runs once per window, on the latest arguments", () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  try {
    const seen = [];
    const f = throttleLatest((x) => seen.push(x), 50);
    for (let i = 0; i < 1000; i++) { f(i); mock.timers.tick(1); }
    mock.timers.tick(100);
    // 1000 ms of calls at 50 ms per run: ~20 runs, not 1000.
    assert.ok(seen.length >= 19 && seen.length <= 21, `ran ${seen.length} times`);
    assert.equal(seen.at(-1), 999);
  } finally {
    mock.timers.reset();
  }
});

test("an isolated call runs on the next tick", () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  try {
    const seen = [];
    const f = throttleLatest((x) => seen.push(x), 50);
    mock.timers.tick(1000);
    f("a");
    mock.timers.tick(0);
    assert.deepEqual(seen, ["a"]);
  } finally {
    mock.timers.reset();
  }
});
