// The drug map's maths, DOM-free so it is unit tested (tools/tests/drug_map.test.mjs):
// each drug's binding profile as an affinity vector over the targets, a 2-component
// PCA of the drugs on screen, the view filter, and the point colours.
//
// Features, each drug one vector over named keys:
//   - receptors: one key per target, affinity `pKi - PKI_FLOOR` where pKi = 9 - log10(Ki
//     nM), so a Ki of 10 µM or weaker scores 0 (too weak to matter) and 1 nM scores 4.
//     With `measuredKi` (the view's default) a binding with no measured Ki (a
//     Stahl-listed one, say) is left out, so every position rests on measured
//     affinities; without it a source still states it, so it gets PKI_UNMEASURED, a
//     middling affinity. A drug with no measured Ki at all is never mapped
//     (`mappableDrugs`): its whole vector would be placeholders. `signed` multiplies it
//     by the binding's net effect (EFFECT_SIGN), so an agonist and an antagonist of one
//     receptor land on opposite sides; a binding with no stated direction then counts 0.
//   - tone: one key per transmitter system (`tone:<kind>`), the drug's signed net tone
//     (`drug.flowSystems[kind].sum`, the panel's "net neurotransmission").
//   - both: the two blocks side by side.
// With `normalize` (the default) each block is scaled to unit length on its own, so the
// map places drugs by the SHAPE of a profile (which targets, in what proportion), not by
// overall potency or how many targets a corpus happened to list, and in "both" the
// receptor and tone blocks weigh the same; without it, raw values, so a potent,
// promiscuous drug sits further out than a weak, selective one.

/** pKi at and below which a binding counts as no binding (Ki >= 10 µM). */
export const PKI_FLOOR = 5;
/** Assumed pKi for a stated binding without a measured Ki (100 nM). */
export const PKI_UNMEASURED = 7;
/** Signed mode: a binding's net effect as a sign. A partial agonist / modulator
 *  ("modulate") counts as half an agonist; an affinity-only binding (no effect) as 0. */
export const EFFECT_SIGN = { boost: 1, block: -1, modulate: 0.5 };
export const FEATURE_SOURCES = ["receptors", "tone", "both"];
export const TONE_PREFIX = "tone:";

const hasMeasuredKi = (b) => !!b.ki && typeof b.ki.median === "number" && b.ki.median > 0;
const affinityOf = (b) => {
  const pki = hasMeasuredKi(b) ? 9 - Math.log10(b.ki.median) : PKI_UNMEASURED;
  return Math.max(0, pki - PKI_FLOOR);
};

/**
 * Each drug's feature vector (see the module comment). Receptor features use
 * `drug.bindings` (which carries a prodrug's borrowed bindings, so lisdexamfetamine sits
 * by dextroamphetamine), not the separate active-metabolite bindings; a target bound
 * twice keeps its strongest value. `only` keeps just those keys (target ids and/or
 * `tone:<kind>`; `[]` keeps none, null every one). `measuredKi` drops the bindings
 * with no measured Ki from the receptor block. Drugs whose vector is all zero get
 * none (they cannot be placed).
 * @param {object[]} drugs
 * @param {{normalize?: boolean, signed?: boolean, source?: string, only?: string[]|null,
 *   measuredKi?: boolean}} [opts]
 * @returns {Map<string, Map<string, number>>} drug id -> (feature key -> value)
 */
export function buildProfiles(drugs, { normalize = true, signed = false, source = "receptors", only = null, measuredKi = false } = {}) {
  const keep = only ? new Set(only) : null;
  const out = new Map();
  for (const d of drugs) {
    const rec = new Map(), tone = new Map();
    if (source !== "tone") {
      for (const b of d.bindings || []) {
        if (!b.target || (measuredKi && !hasMeasuredKi(b))) continue;
        const a = affinityOf(b) * (signed ? EFFECT_SIGN[b.effect] || 0 : 1);
        if (Math.abs(a) > Math.abs(rec.get(b.target) || 0)) rec.set(b.target, a);
      }
    }
    if (source !== "receptors") {
      for (const [kind, f] of Object.entries(d.flowSystems || {})) {
        if (f.sum) tone.set(TONE_PREFIX + kind, f.sum);
      }
    }
    const v = new Map();
    for (const block of [rec, tone]) {
      const kept = [...block].filter(([k, w]) => w && (!keep || keep.has(k)));
      const norm = Math.hypot(...kept.map(([, w]) => w));
      for (const [k, w] of kept) v.set(k, normalize ? w / norm : w);
    }
    if (v.size) out.set(d.id, v);
  }
  return out;
}

/**
 * One selection gesture on a filter list (the class chips, the target picker). `cur`
 * null = everything selected; `keys` = what was clicked (one class, one target, or a
 * whole system's targets). "pick" narrows everything to `keys`, else toggles them (all
 * already in -> out, otherwise added); "drop" removes them from `cur` (or everything).
 * Order is kept and new keys appended, since the picker's first two are the x / y axes.
 * e.g. universe ["d2", "h1", "5ht2a"]:
 *   pickSet(null, ["d2"], "pick", u)         -> ["d2"]
 *   pickSet(["d2"], ["5ht2a"], "pick", u)    -> ["d2", "5ht2a"]
 *   pickSet(["d2", "h1"], ["h1"], "pick", u) -> ["d2"]
 *   pickSet(null, ["h1"], "drop", u)         -> ["d2", "5ht2a"]
 * @param {string[]|null} cur
 * @param {string[]} keys
 * @param {"pick"|"drop"} mode
 * @param {string[]} universe
 * @returns {string[]}
 */
export function pickSet(cur, keys, mode, universe) {
  if (mode === "drop") return (cur || universe).filter((k) => !keys.includes(k));
  if (!cur) return [...keys];
  if (keys.every((k) => cur.includes(k))) return cur.filter((k) => !keys.includes(k));
  return [...cur, ...keys.filter((k) => !cur.includes(k))];
}

/**
 * Plot one or two chosen features directly, no PCA: x = the first key's value, y =
 * the second's (0 when only one is chosen). What "5-HT2A vs D2" asks for.
 * @returns {Map<string, {x:number, y:number}>}
 */
export function directPoints(ids, profiles, keys) {
  return new Map(ids.map((id) => {
    const v = profiles.get(id);
    return [id, { x: v.get(keys[0]) || 0, y: keys[1] ? v.get(keys[1]) || 0 : 0 }];
  }));
}

/**
 * Two-component PCA of the given drugs' profiles: centre each target column over THIS
 * set, take the covariance's top two eigenvectors by power iteration with deflation.
 * Cheap enough to rerun on every view (n drugs x p targets: a p x p covariance, p ~ 150).
 * Each axis is sign-fixed so its largest loading is positive, so a small filter change
 * does not mirror the whole map.
 * @param {string[]} ids  drug ids to place (each must have a profile)
 * @param {Map<string, Map<string, number>>} profiles
 * @returns {{points: Map<string, {x:number, y:number}>,
 *   axes: {share:number, loadings:{target:string, w:number}[]}[]}}
 */
export function pca(ids, profiles) {
  const targets = [...new Set(ids.flatMap((id) => [...profiles.get(id).keys()]))].sort();
  const p = targets.length, n = ids.length;
  const col = new Map(targets.map((t, i) => [t, i]));
  const X = ids.map((id) => {
    const row = new Float64Array(p);
    for (const [t, w] of profiles.get(id)) row[col.get(t)] = w;
    return row;
  });
  const mean = new Float64Array(p);
  for (const row of X) for (let j = 0; j < p; j++) mean[j] += row[j] / n;
  for (const row of X) for (let j = 0; j < p; j++) row[j] -= mean[j];
  const C = Array.from({ length: p }, () => new Float64Array(p));
  for (const row of X) {
    for (let i = 0; i < p; i++) {
      if (!row[i]) continue;
      for (let j = i; j < p; j++) C[i][j] += row[i] * row[j];
    }
  }
  let total = 0;
  for (let i = 0; i < p; i++) {
    for (let j = 0; j < i; j++) C[i][j] = C[j][i];
    total += C[i][i];
  }
  const axes = [];
  for (let k = 0; k < 2; k++) {
    const { vec, value } = topEigen(C, p);
    // Deflate so the next pass finds the next component.
    for (let i = 0; i < p; i++) for (let j = 0; j < p; j++) C[i][j] -= value * vec[i] * vec[j];
    let big = 0;
    for (let i = 0; i < p; i++) if (Math.abs(vec[i]) > Math.abs(vec[big])) big = i;
    if (vec[big] < 0) for (let i = 0; i < p; i++) vec[i] = -vec[i];
    axes.push({
      vec,
      share: total > 0 ? Math.max(0, value) / total : 0,
      loadings: targets.map((target, i) => ({ target, w: vec[i] }))
        .filter((l) => l.w).sort((a, b) => Math.abs(b.w) - Math.abs(a.w)),
    });
  }
  const points = new Map();
  ids.forEach((id, r) => {
    const dot = (v) => X[r].reduce((s, x, j) => s + x * v[j], 0);
    points.set(id, { x: p ? dot(axes[0].vec) : 0, y: p ? dot(axes[1].vec) : 0 });
  });
  return { points, axes: axes.map(({ share, loadings }) => ({ share, loadings })) };
}

// Dominant eigenpair of a symmetric PSD matrix by power iteration from a fixed,
// deterministic start (so the same view always draws the same map).
function topEigen(C, p) {
  let vec = Float64Array.from({ length: p }, (_, i) => 1 + (i % 7) / 10);
  let value = 0;
  for (let it = 0; it < 300 && p; it++) {
    const next = new Float64Array(p);
    for (let i = 0; i < p; i++) {
      let s = 0;
      for (let j = 0; j < p; j++) s += C[i][j] * vec[j];
      next[i] = s;
    }
    const norm = Math.hypot(...next);
    if (!norm) return { vec: new Float64Array(p), value: 0 };
    for (let i = 0; i < p; i++) next[i] /= norm;
    const delta = next.reduce((s, x, i) => s + Math.abs(x - vec[i]), 0);
    vec = next;
    value = norm;
    if (delta < 1e-10) break;
  }
  return { vec, value };
}

/** The map's default view: every class, every year, nothing hidden. */
export const DEFAULT_VIEW = Object.freeze({
  cats: null,          // null = all categories, else a Set of primary category keys
  years: null,         // null = any year, else [from, to] (drugs with no year drop out)
  hidden: new Set(),   // drug ids hidden by hand
  color: "category",   // one of COLOR_MODES
  labels: true,
  spread: true,        // nudge overlapping dots apart on screen (js/drug-map/spread.js)
  normalize: true,     // unit-length profiles (see buildProfiles)
  signed: true,        // agonist vs antagonist on opposite signs
  marketed: true,      // only drugs with a current marketing authorisation (US or FR holder)
  measuredKi: true,    // leave out bindings with no measured Ki (see buildProfiles)
  source: "receptors", // one of FEATURE_SOURCES
  only: null,          // null = every feature, else the chosen keys, in pick order
});

// A drug's major metabolic route: the enzymes a source calls its MAJOR substrate route,
// else its one substrate enzyme when it has only one (its only stated route).
function routeOf(d) {
  const subs = (d.enzymes || []).filter((e) => e.role === "substrate");
  const major = subs.filter((e) => e.strength === "major");
  const pick = major.length ? major : subs.length === 1 ? subs : [];
  if (!pick.length) return null;
  const names = [...new Set(pick.map((e) => e.label || e.enzyme))].sort();
  return [names.join(" + "), names.join(" + ")];
}

// Whether a drug's bindings all carry a measured Ki: "all" / "some" / "none".
function kiCoverage(d) {
  const bs = d.bindings || [];
  if (!bs.length) return null;
  const n = bs.filter(hasMeasuredKi).length;
  return n === bs.length ? "all" : n ? "some" : "none";
}

/** The drugs the map can show at all: those with at least one measured Ki. A drug with
 *  none (most benzodiazepines, barbiturates, anticonvulsants) would be placed by
 *  placeholder affinities alone, so it is left off rather than shown at a made-up spot. */
export const mappableDrugs = (drugs) => drugs.filter((d) => (d.bindings || []).some(hasMeasuredKi));

export const COLOR_MODES = ["category", "nbn", "year", "lab", "route", "ki"];

export const primaryCategory = (d) => (d.categories && d.categories[0]) || "other";

/** The drugs a view keeps (before the profile check). */
export function filterDrugs(drugs, view) {
  return drugs.filter((d) => {
    if (view.hidden.has(d.id)) return false;
    if (view.cats && !view.cats.has(primaryCategory(d))) return false;
    // "Marketed" = someone holds a marketing authorisation today (a `holders[]` row,
    // US or France): withdrawn, discontinued and never-approved drugs drop.
    if (view.marketed && !(d.holders && d.holders.length)) return false;
    if (view.years) {
      const y = d.firstApproval && d.firstApproval.year;
      if (!y || y < view.years[0] || y > view.years[1]) return false;
    }
    return true;
  });
}

const UNKNOWN_COLOR = "#8a8f98";
// Ki coverage: every binding measured, or only some ("none" never reaches the map,
// see mappableDrugs).
const KI_KEYS = ["all", "some"];
const KI_COLORS = { all: "hsl(140, 55%, 52%)", some: "hsl(42, 80%, 55%)" };
// Categorical hue for the i-th key: golden-angle steps keep neighbours apart.
const hue = (i) => `hsl(${Math.round((i * 137.508) % 360)}, 62%, 56%)`;

/** A category's colour, fixed by its meta index so filtering never repaints it (the
 *  map's points and its category chips share it). */
export function categoryColor(cat, catLabels) {
  const i = Object.keys(catLabels).indexOf(cat);
  return i < 0 ? UNKNOWN_COLOR : hue(i);
}

/**
 * Give each key (a nomenclature, say) a class colour, chosen so switching the map from
 * "class" to this mode repaints as few points as possible: the (key, class) pairs that
 * share the most drugs claim their colour first, each class colour used once (a greedy
 * maximum-weight matching); keys left over take the unused class colours, then fresh hues.
 * E.g. NbN "dopamine, serotonin receptor antagonist" (mostly atypicals) inherits the
 * atypical colour, so those points keep theirs.
 * @returns {Map<string, string>} key -> colour
 */
export function matchClassColors(drugs, keys, keyOf, catLabels) {
  const overlap = new Map(); // "key\u0000cat" -> shared drugs
  for (const d of drugs) {
    const k = keyOf(d);
    if (!k) continue;
    const id = `${k[0]}\u0000${primaryCategory(d)}`;
    overlap.set(id, (overlap.get(id) || 0) + 1);
  }
  const pairs = [...overlap].map(([id, n]) => [...id.split("\u0000"), n])
    .sort((a, b) => b[2] - a[2] || a[0].localeCompare(b[0]) || a[1].localeCompare(b[1]));
  const out = new Map(), usedCats = new Set();
  for (const [k, cat] of pairs) {
    if (out.has(k) || usedCats.has(cat) || categoryColor(cat, catLabels) === UNKNOWN_COLOR) continue;
    out.set(k, categoryColor(cat, catLabels));
    usedCats.add(cat);
  }
  const spare = Object.keys(catLabels).filter((c) => !usedCats.has(c)).map((c) => categoryColor(c, catLabels));
  let fresh = Object.keys(catLabels).length;
  for (const k of keys) if (!out.has(k)) out.set(k, spare.shift() || hue(fresh++));
  return out;
}

/**
 * Colour each drug for a mode, plus the legend that explains it.
 * Categorical modes (category / nbn / lab) colour by key, in first-seen order of
 * `keyOrder` then of the drugs; `year` is a ramp, older paler, more recent stronger.
 * @param {object[]} drugs  the placed drugs
 * @param {string} mode
 * @param {{catLabels: Object<string,string>, unknown: string, t: Function}} ctx
 * @returns {{colorOf: Map<string,string>, legend: {label:string, color:string, count:number}[],
 *   ramp: {from:number, to:number}|null}}
 */
export function colorize(drugs, mode, { catLabels, unknown, t }) {
  const colorOf = new Map();
  if (mode === "year") {
    const years = drugs.map((d) => d.firstApproval && d.firstApproval.year).filter(Boolean);
    const from = Math.min(...years), to = Math.max(...years);
    for (const d of drugs) {
      const y = d.firstApproval && d.firstApproval.year;
      if (!y) { colorOf.set(d.id, UNKNOWN_COLOR); continue; }
      const f = to > from ? (y - from) / (to - from) : 1;
      colorOf.set(d.id, `hsl(212, ${Math.round(12 + 78 * f)}%, ${Math.round(74 - 26 * f)}%)`);
    }
    return { colorOf, legend: [], ramp: years.length ? { from, to } : null };
  }
  const keyOf = {
    category: (d) => [primaryCategory(d), catLabels[primaryCategory(d)] || primaryCategory(d)],
    nbn: (d) => (d.nbn ? [d.nbn, d.nbn] : null),
    lab: (d) => (d.originator && d.originator.name ? [d.originator.name, d.originator.name] : null),
    route: routeOf,
    ki: (d) => { const k = kiCoverage(d); return k ? [k, t(`drugmap.ki.${k}`)] : null; },
  }[mode];
  // Category keys follow the meta order (so a class keeps its colour across views);
  // the others by frequency, the commonest first.
  const counts = new Map();
  for (const d of drugs) {
    const k = keyOf(d);
    if (!k) continue;
    if (!counts.has(k[0])) counts.set(k[0], { label: k[1], count: 0 });
    counts.get(k[0]).count++;
  }
  const fixed = { category: Object.keys(catLabels), ki: KI_KEYS }[mode];
  const keys = fixed
    ? [...fixed, ...counts.keys()].filter((k, i, a) => counts.has(k) && a.indexOf(k) === i)
    : [...counts.keys()].sort((a, b) => counts.get(b).count - counts.get(a).count || a.localeCompare(b));
  const colorKey = mode === "nbn" ? matchClassColors(drugs, keys, keyOf, catLabels)
    : new Map(keys.map((k, i) =>
      [k, mode === "category" ? categoryColor(k, catLabels) : mode === "ki" ? KI_COLORS[k] : hue(i)]));
  for (const d of drugs) {
    const k = keyOf(d);
    colorOf.set(d.id, k ? colorKey.get(k[0]) : UNKNOWN_COLOR);
  }
  const legend = keys.map((k) => ({ key: k, label: counts.get(k).label, color: colorKey.get(k), count: counts.get(k).count }));
  const missing = drugs.filter((d) => !keyOf(d)).length;
  if (missing) legend.push({ key: null, label: unknown, color: UNKNOWN_COLOR, count: missing });
  return { colorOf, legend, ramp: null };
}
