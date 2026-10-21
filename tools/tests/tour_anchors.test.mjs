// Every guided-tour step must point at something the app still has. Run by
// tools/tests/test_js_units.py via `node --test`; the fast twin of the headless
// walk (tools/tour_walk.py), which is the only other thing that would notice.
//
// How: public/js/boot/tour-steps.js is imported for real (its two DOM-heavy
// imports, the explode slider and the tour engine, are stubbed by a resolve
// hook), with a `document` that RECORDS every selector / id it is asked for. Each
// step's target, tapTarget, veil, clickThrough, gate and before() is run, so a
// selector built inside a helper (tourPanelIntro, tourOpenSec, ...) is caught as
// surely as a literal one. Every recorded selector must then resolve:
//   - statically: each compound part (`#id.cls[attr="v"]`) matches some start tag
//     of public/index.html (descendant order is not checked);
//   - else dynamically: each simple part is in DYNAMIC below, whose module must
//     still contain the token literally (a renamed class or hook fails here), and a
//     `data-tour-id` row's id must exist in the emitted data.
// Every i18n key the steps name must exist in both catalogues (test_i18n.py checks
// EN/FR parity, not that a key used by the tour exists at all).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import vm from "node:vm";

const PUB = new URL("../../public/", import.meta.url);
const read = (rel) => readFileSync(new URL(rel, PUB), "utf8");
const jsonl = (rel) => read(rel).split("\n").filter(Boolean).map((l) => JSON.parse(l));

// ---- Stubs: the two imports that need three.js / a live DOM ----------------------
const STUBS = {
  "/scene/explode.js": "export const applyExplode = () => {};",
  "/tour.js": "export const createTour = (opts) => opts;",
};
registerHooks({
  resolve(spec, ctx, next) {
    for (const [tail, src] of Object.entries(STUBS)) {
      if (spec.endsWith(tail)) {
        return { url: `data:text/javascript,${encodeURIComponent(src)}`, shortCircuit: true };
      }
    }
    return next(spec, ctx);
  },
});

// A stand-in for "any DOM/three object": every property is itself, every call
// returns itself, so arbitrary chains (`el.classList.toggle(...)`) are no-ops.
const ANY = new Proxy(function () {}, {
  get: (_t, p) => (p === Symbol.toPrimitive ? () => 0 : p === "then" ? undefined : ANY),
  apply: () => ANY,
  set: () => true,
});

let recorded = null; // Set of selectors asked for while running one step
const record = (sel) => { recorded?.add(sel); };
// An element that also records the lookups made from it (`pane.querySelector`).
const recordingEl = (ctx) => new Proxy(function () {}, {
  get(_t, p) {
    if (p === "querySelector" || p === "querySelectorAll" || p === "closest") {
      return (s) => { record(p === "closest" ? s : `${ctx} ${s}`); return recordingEl(s); };
    }
    return p === Symbol.toPrimitive ? () => 0 : p === "then" ? undefined : ANY;
  },
  apply: () => ANY,
  set: () => true,
});
globalThis.document = {
  getElementById: (id) => { record(`#${id}`); return recordingEl(`#${id}`); },
  querySelector: (s) => { record(s); return recordingEl(s); },
  querySelectorAll: (s) => { record(s); return recordingEl(s); },
};
globalThis.MutationObserver = class { observe() {} disconnect() {} };
const usedKeys = new Set();
const tKey = (k) => { usedKeys.add(k); return k; };
globalThis.window = { __I18N__: { t: tKey, tHtml: tKey } };

const { createViewerTour } = await import(new URL("js/boot/tour-steps.js", PUB));
const data = { drugs: [], targets: [], structures: [], projections: [],
  projectionGroupsByKey: new Map(), meta: {} };
const { tour: opts } = createViewerTour(new Proxy({ data, meshById: new Map() },
  { get: (o, p) => (p in o ? o[p] : ANY) }));
const steps = opts.steps;
for (const k of Object.values(opts.labels)) if (typeof k === "function") k(1, 2);

// ---- Collect every selector each step touches -----------------------------------
const STEP_FIELDS = ["target", "tapTarget", "veil", "clickThrough", "gate", "before"];
function selectorsOf(step) {
  const out = new Map(); // selector -> field that asked for it
  for (const field of STEP_FIELDS) {
    const v = step[field];
    if (v == null) continue;
    recorded = new Set();
    let r = v;
    if (typeof v === "function") r = field === "gate" ? v(() => {}) : v();
    if (field !== "gate" && field !== "before") {
      for (const item of [r].flat()) if (typeof item === "string") recorded.add(item);
    }
    for (const s of recorded) if (!out.has(s)) out.set(s, field);
    recorded = null;
  }
  return out;
}

// ---- Static markup: every start tag of index.html, as {tag, id, classes, attrs} ----
const TAGS = [...read("index.html").matchAll(/<([a-zA-Z][\w-]*)\b([^>]*)>/g)].map(([, tag, rest]) => {
  const attrs = {};
  for (const [, name, , dq, sq, bare] of rest.matchAll(/([\w:-]+)(?:\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
    attrs[name] = dq ?? sq ?? bare ?? "";
  }
  return { tag: tag.toLowerCase(), attrs, classes: new Set((attrs.class || "").split(/\s+/)) };
});

// Split a compound (`a#x.y[data-z="w"]`) into its simple parts.
function parts(compound) {
  const out = [];
  const re = /#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]|^([a-zA-Z][\w-]*)/g;
  let m, consumed = 0;
  while ((m = re.exec(compound))) {
    consumed += m[0].length;
    if (m[1]) out.push({ kind: "id", value: m[1], text: m[0] });
    else if (m[2]) out.push({ kind: "class", value: m[2], text: m[0] });
    else if (m[3]) out.push({ kind: "attr", name: m[3], value: m[4], text: m[0] });
    else out.push({ kind: "tag", value: m[5].toLowerCase(), text: m[0] });
  }
  if (consumed !== compound.length) throw new Error(`selector part the test cannot read: ${compound}`);
  return out;
}
const tagHas = (t, p) => p.kind === "id" ? t.attrs.id === p.value
  : p.kind === "class" ? t.classes.has(p.value)
  : p.kind === "tag" ? t.tag === p.value
  : p.value === undefined ? p.name in t.attrs : t.attrs[p.name] === p.value;
const inMarkup = (ps) => TAGS.some((t) => ps.every((p) => tagHas(t, p)));

// ---- Dynamic anchors: token -> the module that builds it --------------------------
// Each entry's `token` must occur literally in `module`. Add one when a tour step
// starts pointing at a new runtime-built element.
const DYNAMIC = {
  "#nodes-filter": { module: "js/node-browser/view.js", token: '"nodes-filter"' },
  ".node-filters": { module: "js/node-browser/view.js", token: '"node-filters"' },
  ".detail-tab": { module: "js/panel/tabs.js", token: '"detail-tab"' },
  ".active": { module: "js/panel/tabs.js", token: '" active"' },
  ".detail-tab-close": { module: "js/panel/tabs.js", token: '"detail-tab-close"' },
  ".info-desc": { module: "js/panel/reference.js", token: '"info-desc"' },
  '[data-tour-sec="bindings"]': { module: "js/panel/views/drug.js", token: 'tourSec = "bindings"' },
  '[data-tour-sec="metabolism"]': { module: "js/panel/views/drug.js", token: 'tourSec = "metabolism"' },
  '[data-tour-sec="pk"]': { module: "js/panel/pk-interactions.js", token: 'tourSec = "pk"' },
  '[data-tour-sec="facts"]': { module: "js/panel/views/receptor.js", token: 'tourSec = "facts"' },
  '[data-tour-sec="regions"]': { module: "js/panel/views/receptor.js", token: '"regions"' },
  // tourPanelIntro's figure: step 24 opens the hippocampus structure panel.
  '[data-tour-sec="wiki"]': { module: "js/panel/views/structure.js", token: 'structure.name, "wiki"' },
};
// `data-tour-id="<prefix>:<id>"` rows: the prefix's builder, plus the ids the data has.
const drugTargets = JSON.parse(read("data/meta.json")).drug_targets || {};
const TOUR_IDS = {
  drug: { module: "js/legend/drugs.js", ids: () => jsonl("data/drugs.jsonl").map((d) => d.id) },
  ixtarget: { module: "js/panel/views/drug.js",
    ids: () => [...jsonl("data/receptors.jsonl").map((r) => r.id), ...Object.keys(drugTargets)] },
  structure: { module: "js/legend/anatomy.js",
    ids: () => jsonl("data/structures.jsonl").map((s) => s.id.replace(/_[LR]$/, "")) },
  group: { module: "js/legend/anatomy.js",
    ids: () => jsonl("data/projection_groups.jsonl").map((g) => `${g.mode}:${g.key}`) },
};

// Why a simple part that index.html lacks is still fine (null = it is broken).
function dynamicProblem(p) {
  if (p.kind === "attr" && p.name === "data-tour-id" && p.value) {
    const [prefix, ...rest] = p.value.split(":");
    const spec = TOUR_IDS[prefix];
    if (!spec) return `no TOUR_IDS entry for row prefix "${prefix}:"`;
    if (!read(spec.module).includes(`\`${prefix}:\${`)) {
      return `${spec.module} no longer builds data-tour-id="${prefix}:..."`;
    }
    const id = rest.join(":");
    return spec.ids().includes(id) ? null : `no ${prefix} "${id}" in public/data`;
  }
  const spec = DYNAMIC[p.text];
  if (!spec) return `${p.text} is not in index.html and has no DYNAMIC entry`;
  return read(spec.module).includes(spec.token) ? null : `${spec.module} no longer contains ${spec.token}`;
}

test("the tour has steps to check", () => {
  assert.ok(steps.length > 10, `only ${steps.length} steps found`);
});

test("every selector a tour step uses resolves to something the app has", () => {
  const problems = [];
  steps.forEach((step, i) => {
    const name = `step ${i + 1} (${step.title})`;
    for (const [sel, field] of selectorsOf(step)) {
      for (const compound of sel.trim().split(/\s+/)) {
        const ps = parts(compound);
        if (inMarkup(ps)) continue;
        for (const p of ps) {
          if (TAGS.some((t) => tagHas(t, p)) && !(p.kind === "attr" && p.name.startsWith("data-tour"))) continue;
          const why = dynamicProblem(p);
          if (why) problems.push(`${name} ${field} "${sel}": ${why}`);
        }
      }
    }
  });
  assert.deepEqual(problems, [], problems.join("\n"));
});

test("every i18n key the tour names exists in both catalogues", () => {
  const ctx = { window: {} };
  vm.createContext(ctx);
  for (const f of ["js/i18n/en.js", "js/i18n/fr.js"]) vm.runInContext(read(f), ctx);
  const tables = ctx.window.__I18N_MESSAGES__;
  assert.ok(usedKeys.size > 10, `only ${usedKeys.size} keys recorded`);
  const missing = [];
  for (const k of usedKeys) for (const lang of ["en", "fr"]) {
    if (!(k in tables[lang])) missing.push(`${k} (${lang})`);
  }
  assert.deepEqual(missing, [], `tour i18n keys missing: ${missing.join(", ")}`);
});
