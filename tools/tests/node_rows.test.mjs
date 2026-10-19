// The Data browser lists exactly the nodes the coverage tally counts: loads the SHIPPED
// public/data through the real loader (js/data.js), runs collectNodes, and compares
// each registry kind's rows, grade bucket by bucket, with meta.provenance_stats.by_kind. A kind added to
// the generator and the registry but never collected (or collected twice) fails here,
// which tools/tests/test_node_kinds.py (names only) cannot see. Run by
// tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const PUBLIC = new URL("../../public/", import.meta.url);

// The browser globals the loader and the classic i18n script touch.
globalThis.window = globalThis;
globalThis.location = { search: "" };
globalThis.localStorage = { getItem: () => null, setItem() {} };
globalThis.document = { documentElement: {}, addEventListener() {} };
Object.defineProperty(globalThis, "navigator",
  { value: { languages: ["en"] }, configurable: true });
for (const f of ["js/i18n/en.js", "js/i18n/fr.js", "js/i18n.js"]) {
  vm.runInThisContext(readFileSync(new URL(f, PUBLIC), "utf8"));
}
// The data dir is read straight off disk; a missing file (the build-time effect
// index under derived/, never committed) answers 404, as on a bare static server.
globalThis.fetch = async (url) => {
  try {
    return new Response(readFileSync(new URL(url, PUBLIC)), { status: 200 });
  } catch {
    return new Response("", { status: 404, statusText: "Not Found" });
  }
};
console.error = () => {}; // the expected missing-effect-index warning

const { loadBrainData } = await import(new URL("js/data.js", PUBLIC));
const { collectNodes } = await import(new URL("js/node-browser/collect.js", PUBLIC));
const { formatHalfLife } = await import(new URL("js/panel/format.js", PUBLIC));
const { KIND_ORDER, KIND_LABELS } = await import(new URL("js/kinds.js", PUBLIC));

// Kinds with a Sources bar but deliberately no browser rows (their rows live
// elsewhere): enzyme_variability is browsed in the enzyme panel (see kinds.js).
const NO_ROWS = new Set(["enzyme_variability"]);

const data = await loadBrainData("data");
const nav = new Proxy({}, { get: () => () => {} });
const rows = collectNodes(data, { t: window.__I18N__.t, formatHalfLife, nav });
const byKind = data.meta.provenanceStats.by_kind;

// The tally's grade buckets a row's display grade can land in.
const BUCKETS = ["verified", "uncertain", "sourced", "llm", "nosource", "unknown"];

test("every registry kind's rows match its tally, grade bucket by grade bucket", () => {
  const counts = {};
  for (const r of rows) {
    const c = (counts[r.kind] ||= Object.fromEntries(BUCKETS.map((b) => [b, 0])));
    assert.ok(r.grade in c, `${r.kind}: row grade ${r.grade} is no tally bucket`);
    c[r.grade] += 1;
  }
  for (const kind of KIND_ORDER) {
    const tally = byKind[kind];
    assert.ok(tally, `${kind}: in kinds.js but not in by_kind`);
    const got = counts[kind] || Object.fromEntries(BUCKETS.map((b) => [b, 0]));
    for (const b of BUCKETS) {
      const want = NO_ROWS.has(kind) ? 0 : tally[b];
      // An owner-level UNKNOWN (receptor_effect's `effects_unknown`: no effect node,
      // so nothing to list) is tallied but has no row; a per-node one has its row.
      if (b === "unknown") assert.ok(got[b] <= want, `${kind}: ${got[b]} unknown rows vs tally ${want}`);
      else assert.equal(got[b], want, `${kind}: ${got[b]} ${b} rows vs tally ${want}`);
    }
  }
  for (const kind of Object.keys(counts)) {
    assert.ok(KIND_ORDER.includes(kind), `${kind}: rows but no registry entry`);
  }
});

test("every registry label is in the English catalogue", () => {
  for (const [kind, key] of Object.entries(KIND_LABELS)) {
    assert.notEqual(window.__I18N__.t(key), key, `${kind}: no ${key} string`);
  }
});
