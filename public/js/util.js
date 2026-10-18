// Tiny dependency-free helpers shared across the viewer (no DOM, no three.js), so
// the data loader, the panels and the node-testable modules import one copy.

/**
 * Group a list into a Map of arrays, keys and members both in first-seen order.
 * @template T, K
 * @param {Iterable<T>} list
 * @param {(item: T) => K} keyFn
 * @returns {Map<K, T[]>}
 */
export function groupBy(list, keyFn) {
  const out = new Map();
  for (const item of list) {
    const k = keyFn(item);
    const bucket = out.get(k);
    if (bucket) bucket.push(item);
    else out.set(k, [item]);
  }
  return out;
}

/** `accumbens_R` -> `accumbens`: side-stripped base id. A hemisphere
 * rendering detail, so anything keyed by region (expression, search rows, deep
 * links) keys by base. */
export function stripSide(id) {
  return String(id == null ? "" : id).replace(/_[LR]$/, "");
}

/**
 * A structure id's left/right twin (a midline id, with no suffix, maps to
 * itself), following the data + viewer's `_R`/`_L` convention.
 * @param {string} id
 * @returns {string}
 */
export const mirrorId = (id) =>
  id.endsWith("_R") ? `${id.slice(0, -2)}_L`
    : id.endsWith("_L") ? `${id.slice(0, -2)}_R`
      : id;

// Fold a drug / metabolite name for joining ("Desmethyldiazepam (nordazepam)" ->
// "desmethyldiazepamnordazepam").
export const normName = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
