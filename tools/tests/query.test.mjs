// Unit tests for public/js/boot/query.js isFramedView: only a view key freezes the
// auto-rotate (js/scene/camera.js applyViewParams); a startup flag alone does not.
// Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";

globalThis.window = { location: { search: "" } };
const { isFramedView, VIEW_KEYS } = await import("../../public/js/boot/query.js");

const q = (s) => new URLSearchParams(s);

test("startup flags alone are not a framed view", () => {
  for (const s of ["", "lang=fr", "tour=1", "lang=en&tour=1"]) {
    assert.equal(isFramedView(q(s)), false, s);
  }
});

test("every view key makes a framed view, alongside a flag too", () => {
  for (const k of VIEW_KEYS) {
    assert.equal(isFramedView(q(`${k}=1`)), true, k);
    assert.equal(isFramedView(q(`lang=fr&${k}=0`)), true, k);
  }
});

test("the screenshot tools' queries are framed views", () => {
  assert.equal(isFramedView(q("explode=0.45&view=iso&ui=0")), true);
  assert.equal(isFramedView(q("solo=putamen_R&ghost=0.06&view=iso&ui=0&explode=0")), true);
});

// Class-wide guard: a key applyViewParams reads but VIEW_KEYS lacks would apply its
// view yet leave a `?key=` link spinning; an undocumented one is unfindable.
test("VIEW_KEYS covers every key applyViewParams reads, and RUNNING.md documents each", async () => {
  const { readFileSync } = await import("node:fs");
  const read = (p) => readFileSync(new URL(`../../${p}`, import.meta.url), "utf8");
  const camera = read("public/js/scene/camera.js");
  const body = camera.slice(camera.indexOf("export function applyViewParams"));
  const used = new Set([...body.matchAll(/\bq\.(?:has|get)\("(\w+)"\)/g)].map((m) => m[1]));
  for (const m of body.matchAll(/for \(const key of \[([^\]]*)\]\)/g)) {
    for (const k of m[1].matchAll(/"(\w+)"/g)) used.add(k[1]);
  }
  assert.ok(used.size >= 5, "parsed too few keys out of applyViewParams");
  for (const k of used) assert.ok(VIEW_KEYS.includes(k), `${k}: read but not in VIEW_KEYS`);
  const running = read("docs/RUNNING.md");
  for (const k of VIEW_KEYS) assert.ok(running.includes(`\`${k}=`), `${k}: not in docs/RUNNING.md`);
});
