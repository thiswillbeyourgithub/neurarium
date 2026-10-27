// The drug map's maths, DOM-free so it is unit tested (tools/tests/drug_map.test.mjs):
// each drug's binding profile as an affinity vector over the targets, a 2-component
// PCA of the drugs on screen, the view filter, and the point colours.
//
// Affinity: one dimension per target, `pKi - PKI_FLOOR` where pKi = 9 - log10(Ki nM),
// so a Ki of 10 µM or weaker scores 0 (too weak to matter) and 1 nM scores 4. A binding
// with no measured Ki (a Stahl-listed one, say) is not ignored: it is a binding a source
// states, so it gets PKI_UNMEASURED, a middling affinity. With `normalize` (the default)
// each profile is then scaled to unit length, so the map places drugs by the SHAPE of
// their profile (which targets, in what proportion), not by how potent they are overall
// or how many targets a corpus happened to list; without it, raw affinities, so a
// potent, promiscuous drug sits further out than a weak, selective one.

/** pKi at and below which a binding counts as no binding (Ki >= 10 µM). */
export const PKI_FLOOR = 5;
/** Assumed pKi for a stated binding without a measured Ki (100 nM). */
export const PKI_UNMEASURED = 7;

const affinityOf = (b) => {
  const ki = b.ki && typeof b.ki.median === "number" ? b.ki.median : null;
  const pki = ki && ki > 0 ? 9 - Math.log10(ki) : PKI_UNMEASURED;
  return Math.max(0, pki - PKI_FLOOR);
};

/**
 * Each drug's unit-length affinity profile. Uses `drug.bindings` (which carries a
 * prodrug's borrowed bindings, so lisdexamfetamine sits by dextroamphetamine) and not
 * the separate active-metabolite bindings. A target bound twice keeps its strongest
 * affinity. Drugs with no nonzero affinity get no profile (they cannot be placed).
 * @param {object[]} drugs
 * @param {{normalize?: boolean}} [opts]  scale each profile to unit length (default on)
 * @returns {Map<string, Map<string, number>>} drug id -> (target id -> weight)
 */
export function buildProfiles(drugs, { normalize = true } = {}) {
  const out = new Map();
  for (const d of drugs) {
    const v = new Map();
    for (const b of d.bindings || []) {
      if (!b.target) continue;
      const a = affinityOf(b);
      if (a > (v.get(b.target) || 0)) v.set(b.target, a);
    }
    const norm = Math.hypot(...v.values());
    if (!norm) continue;
    if (normalize) for (const [k, w] of v) v.set(k, w / norm);
    out.set(d.id, v);
  }
  return out;
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
  labels: false,
  normalize: true,     // unit-length profiles (see buildProfiles)
});

export const COLOR_MODES = ["category", "nbn", "year", "lab"];

export const primaryCategory = (d) => (d.categories && d.categories[0]) || "other";

/** The drugs a view keeps (before the profile check). */
export function filterDrugs(drugs, view) {
  return drugs.filter((d) => {
    if (view.hidden.has(d.id)) return false;
    if (view.cats && !view.cats.has(primaryCategory(d))) return false;
    if (view.years) {
      const y = d.firstApproval && d.firstApproval.year;
      if (!y || y < view.years[0] || y > view.years[1]) return false;
    }
    return true;
  });
}

const UNKNOWN_COLOR = "#8a8f98";
// Categorical hue for the i-th key: golden-angle steps keep neighbours apart.
const hue = (i) => `hsl(${Math.round((i * 137.508) % 360)}, 62%, 56%)`;

/** A category's colour, fixed by its meta index so filtering never repaints it (the
 *  map's points and its category chips share it). */
export function categoryColor(cat, catLabels) {
  const i = Object.keys(catLabels).indexOf(cat);
  return i < 0 ? UNKNOWN_COLOR : hue(i);
}

/**
 * Colour each drug for a mode, plus the legend that explains it.
 * Categorical modes (category / nbn / lab) colour by key, in first-seen order of
 * `keyOrder` then of the drugs; `year` is a ramp, older paler, more recent stronger.
 * @param {object[]} drugs  the placed drugs
 * @param {string} mode
 * @param {{catLabels: Object<string,string>, unknown: string}} ctx
 * @returns {{colorOf: Map<string,string>, legend: {label:string, color:string, count:number}[],
 *   ramp: {from:number, to:number}|null}}
 */
export function colorize(drugs, mode, { catLabels, unknown }) {
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
  const keys = mode === "category"
    ? [...Object.keys(catLabels), ...counts.keys()].filter((k, i, a) => counts.has(k) && a.indexOf(k) === i)
    : [...counts.keys()].sort((a, b) => counts.get(b).count - counts.get(a).count || a.localeCompare(b));
  const colorKey = new Map(keys.map((k, i) =>
    [k, mode === "category" ? categoryColor(k, catLabels) : hue(i)]));
  for (const d of drugs) {
    const k = keyOf(d);
    colorOf.set(d.id, k ? colorKey.get(k[0]) : UNKNOWN_COLOR);
  }
  const legend = keys.map((k) => ({ key: k, label: counts.get(k).label, color: colorKey.get(k), count: counts.get(k).count }));
  const missing = drugs.filter((d) => !keyOf(d)).length;
  if (missing) legend.push({ key: null, label: unknown, color: UNKNOWN_COLOR, count: missing });
  return { colorOf, legend, ramp: null };
}
