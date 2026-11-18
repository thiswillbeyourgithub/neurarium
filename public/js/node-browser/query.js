// Data browser query: the stackable filters, the final sourcing filter and the
// sorting, as pure functions over collectNodes' rows (no DOM, so node-testable).
//
// Filters combine on a row's OWNER (the drug, receptor, region... the row is about),
// left to right, each filter after the first carrying an operator:
//   "kind = drug categories, text = benzo"  AND  "kind = drug half-life"
// keeps the owners both match (the benzodiazepines) and lists the LAST filter's rows
// (their half-lives), so earlier filters narrow and the last one picks what is shown.
// OR unions both sides' rows; XOR keeps the rows of owners matched by exactly one side.

import { KIND_ORDER } from "../kinds.js";
import { DISPLAY_GRADE_ORDER } from "../grades.js";

/** The operators a filter after the first can carry, in the order the UI cycles them. */
export const OPS = ["and", "or", "xor"];

/**
 * The kinds a typed kind query means: empty = every kind (null), an exact label (case
 * and accent folded) = that kind alone, else every kind whose label contains the text.
 * @param {string} query what the reader typed in a filter's kind box
 * @param {string[]} kinds the kinds present in the rows
 * @param {(k: string) => string} kindLabel
 * @param {(s: string) => string} fold
 * @returns {Set<string>|null}
 */
export function kindsFor(query, kinds, kindLabel, fold) {
  const q = fold((query || "").trim());
  if (!q) return null;
  const exact = kinds.filter((k) => fold(kindLabel(k)) === q || k === q);
  if (exact.length) return new Set(exact);
  return new Set(kinds.filter((k) => fold(kindLabel(k)).includes(q)));
}

/**
 * Which drugs each drug's active metabolites ARE (a metabolite that is itself a modeled
 * drug, `m.drugId`), so a filter's "include metabolites" can add them as owners. A
 * metabolite that is no roster drug has no rows of its own (its nodes ride its parent),
 * so it has nothing to add.
 * @param {Array<{id: string, metabolites?: Array<{drugId?: string|null}>}>} drugs
 * @returns {Map<string, string[]>}
 */
export function metaboliteOwners(drugs) {
  const out = new Map();
  for (const d of drugs || []) {
    const ids = (d.metabolites || []).map((m) => m.drugId).filter((id) => id && id !== d.id);
    if (ids.length) out.set(d.id, ids);
  }
  return out;
}

// A row's folded "name notion", computed once per row: folding thousands of strings on
// every keystroke is what made typing in a filter lag. Keyed by row object, so a
// re-collect (the twins checkbox) starts fresh without any invalidation.
const HAYSTACKS = new WeakMap();
function haystack(r, ctx) {
  let h = HAYSTACKS.get(r);
  if (h === undefined) {
    h = ctx.fold(`${r.name} ${r.notion}`);
    HAYSTACKS.set(r, h);
  }
  return h;
}

/**
 * One filter's rows. With `metabolites`, the matched drugs' metabolite drugs join the
 * owners (transitively: a metabolite of a metabolite counts), contributing their rows
 * of the filter's kind(s) whatever the text, since a metabolite need not itself match
 * (nordazepam is no "benzo" by name, yet is the half-life a benzo reader wants).
 */
function filterRows(rows, f, ctx) {
  const kinds = kindsFor(f.kind, ctx.kinds, ctx.kindLabel, ctx.fold);
  const q = ctx.fold((f.text || "").trim());
  const ofKind = (r) => !kinds || kinds.has(r.kind);
  const hit = rows.filter((r) => ofKind(r) && (!q || haystack(r, ctx).includes(q)));
  if (!f.metabolites || !ctx.metabolites) return hit;
  const owners = new Set(hit.map((r) => r.owner));
  const added = new Set();
  const stack = [...owners];
  while (stack.length) {
    for (const m of ctx.metabolites.get(stack.pop()) || []) {
      if (owners.has(m) || added.has(m)) continue;
      added.add(m);
      stack.push(m);
    }
  }
  return hit.concat(rows.filter((r) => added.has(r.owner) && ofKind(r)));
}

/**
 * Whether a filter's rows include a drug's, i.e. whether "include metabolites" could
 * change anything for it (the UI hides the box otherwise).
 */
export function filterTouchesDrugs(rows, f, ctx) {
  return filterRows(rows, { ...f, metabolites: false }, ctx)
    .some((r) => ctx.metabolites && ctx.metabolites.has(r.owner));
}

/**
 * Combine the filters (see the file header) into the listed rows.
 * @param {object[]} rows collectNodes' rows
 * @param {Array<{kind: string, text: string, op?: string, metabolites?: boolean}>} filters
 *   in order; the first one's `op` is ignored
 * @param {{kinds: string[], kindLabel: Function, fold: Function,
 *          metabolites?: Map<string, string[]>}} ctx
 * @returns {object[]} rows in their collected order
 */
export function runFilters(rows, filters, ctx) {
  if (!filters.length) return rows.slice();
  let acc = null;
  for (const f of filters) {
    const hit = filterRows(rows, f, ctx);
    const owners = new Set(hit.map((r) => r.owner));
    if (!acc) { acc = { rows: new Set(hit), owners }; continue; }
    if (f.op === "or") {
      acc = { rows: new Set([...acc.rows, ...hit]), owners: new Set([...acc.owners, ...owners]) };
    } else if (f.op === "xor") {
      const keep = new Set([...acc.owners, ...owners]
        .filter((o) => acc.owners.has(o) !== owners.has(o)));
      acc = { rows: new Set([...acc.rows, ...hit].filter((r) => keep.has(r.owner))), owners: keep };
    } else {
      const keep = new Set([...owners].filter((o) => acc.owners.has(o)));
      acc = { rows: new Set(hit.filter((r) => keep.has(r.owner))), owners: keep };
    }
  }
  return rows.filter((r) => acc.rows.has(r));
}

/** The sorting choices, in menu order (labels are `nodes.sort<Capitalized>`). */
export const SORTS = ["valueAsc", "valueDesc", "weakest", "strongest", "name", "kind"];

/** The sort a fresh browser (and a link without `nsort`) uses: smallest value first. */
export const DEFAULT_SORT = "valueAsc";

/**
 * Sort rows in place. "value" sorts read `row.value` (a T½ in hours, a Ki in nM...):
 * rows are grouped by kind first, since a half-life and a Ki are not comparable, and a
 * row without a value goes after every valued one.
 */
export function sortRows(rows, mode) {
  const byName = (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })
    || a.notion.localeCompare(b.notion, undefined, { numeric: true });
  const byKind = (a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind);
  if (mode === "name") return rows.sort(byName);
  if (mode === "kind") return rows.sort((a, b) => byKind(a, b) || byName(a, b));
  if (mode === "valueAsc" || mode === "valueDesc") {
    const dir = mode === "valueDesc" ? -1 : 1;
    return rows.sort((a, b) => {
      const va = a.value != null, vb = b.value != null;
      if (va !== vb) return va ? -1 : 1;
      if (!va) return byName(a, b);
      return byKind(a, b) || dir * (a.value - b.value) || byName(a, b);
    });
  }
  const dir = mode === "strongest" ? -1 : 1;
  return rows.sort((a, b) =>
    dir * (DISPLAY_GRADE_ORDER[a.grade] - DISPLAY_GRADE_ORDER[b.grade]) || byName(a, b));
}

// URL form of the filter stack (the `nf` key): filters joined by ",", each one's fields
// (op, kind, text, "m" when it includes metabolites) joined by "|". Only "%", "|" and
// "," are escaped here, so a typed separator cannot break the split; url-state.js
// escapes the rest, which keeps "Drug class" readable as Drug%20class in the address
// bar. Trailing empty fields are dropped, and the first filter's op is always empty:
//   [{kind: "Drug class", text: "benzo"}, {op: "and", kind: "half"}]
//   -> "|Drug class|benzo,and|half"
const FIELD_SEP = "|";
const FILTER_SEP = ",";
const escField = (s) => s.replace(/[%|,]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);

/**
 * @param {Array<{kind: string, text: string, op?: string, metabolites?: boolean}>} filters
 * @returns {string|null} null when the stack is one empty filter (the default)
 */
export function serializeFilters(filters) {
  const live = filters.filter((f) => f.kind || f.text || f.metabolites);
  if (!live.length) return null;
  return filters.map((f, i) => {
    const fields = [i === 0 ? "" : f.op || "and", f.kind || "", f.text || "",
      f.metabolites ? "m" : ""].map(escField);
    while (fields.length && fields[fields.length - 1] === "") fields.pop();
    return fields.join(FIELD_SEP);
  }).join(FILTER_SEP);
}

/** Inverse of serializeFilters; an unknown op reads as "and". */
export function parseFilters(value) {
  return String(value || "").split(FILTER_SEP).map((part) => {
    const [op, kind, text, m] = Array.from({ length: 4 },
      (_, i) => decodeURIComponent(part.split(FIELD_SEP)[i] || ""));
    return { op: OPS.includes(op) ? op : "and", kind, text, metabolites: m === "m" };
  });
}
