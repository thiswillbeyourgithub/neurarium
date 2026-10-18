// Source-quote helpers: rehydrating the deduplicated quote table onto every
// `{quote_id, provenance}` reference, and a source ref's download-date suffix.

/**
 * A source's reference line with its download date appended, for a page of an
 * editable online corpus (Wikipedia, PDSP, GtoPdb, ...: the `fetched` date stamped by
 * tools/data_generators/freshness.py). A book page carries no date and keeps `ref`
 * as is. `tr` is the i18n `t()`, injected so this stays pure (and node-testable).
 * @param {string} ref       e.g. "Wikipedia (EN), p. vortioxetine"
 * @param {string} fetched   e.g. "2026-10-11", or falsy
 * @param {Function} tr      (key, vars) -> localized string
 * @returns {string}         e.g. "Wikipedia (EN), p. vortioxetine, downloaded 2026-10-11"
 */
export function withFetched(ref, fetched, tr) {
  return fetched ? `${ref}, ${tr("info.sourceFetched", { date: fetched })}` : ref;
}

/**
 * Rehydrate externalized source quotes in place. The emitted data replaces every
 * quote-bearing source with a `{quote_id, provenance}` reference and stores the
 * excerpt once in quotes.jsonl (see quote_table.py). This deep-walk merges every
 * field of the quote node except its `id` (`corpus`, `page`, `quote`, `species`,
 * `llm`, `heading`, `fetched`, ...) back onto each reference, so downstream code
 * reads `source.quote` etc. exactly as before, and a field the generator adds to the
 * quote node needs no edit here (check_data.py's rehydrate_quotes copies the same
 * way). A dangling `quote_id` (no matching quote) is left as-is (check_data.py
 * guards against it).
 * @param {*} node       Any value (object/array/scalar) to walk.
 * @param {object} byId  quote_id -> quote node map.
 */
export function rehydrateQuotes(node, byId) {
  if (Array.isArray(node)) {
    for (const v of node) rehydrateQuotes(v, byId);
  } else if (node && typeof node === "object") {
    if (typeof node.quote_id === "string") {
      const q = byId[node.quote_id];
      if (q) {
        for (const k in q) if (k !== "id") node[k] = q[k];
      }
    }
    for (const k in node) rehydrateQuotes(node[k], byId);
  }
}
