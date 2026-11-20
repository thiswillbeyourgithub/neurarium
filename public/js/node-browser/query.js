// Data browser query: the stackable filters, the final sourcing filter and the
// sorting, as pure functions over collectNodes' rows (no DOM, so node-testable).
//
// Filters combine on a row's OWNER (the drug, receptor, region... the row is about),
// left to right, each filter after the first carrying an operator:
//   "kind = drug categories, text = benzo"  AND  "kind = drug half-life"
// keeps the owners both match (the benzodiazepines) and lists the LAST filter's rows
// (their half-lives), so earlier filters narrow and the last one picks what is shown.
// OR unions both sides' rows; XOR keeps the rows of owners matched by exactly one side;
// NOT ("and not") keeps the owners the right side does NOT match. A text-less NOT lists
// the left side's rows (the gap finder: "benzo AND NOT half-life" = benzos lacking one);
// a NOT with text lists the right kind's rows missing that text, like AND lists its last
// filter's, and drops owners holding no row of that kind (no data is not a "not").
//
// Parentheses ride the same flat list as marker entries, so the stack stays one array
// (drag, URL and UI unchanged): `{group: "open", op}` begins a group that combines with
// what precedes it through its own `op`, `{group: "close"}` ends it. A stray close is
// ignored, an unclosed group closes at the end of the stack:
//   [A, {group: "open", op: "not"}, B, {op: "or", ...C}, {group: "close"}]  =  A AND NOT (B OR C)

import { KIND_ORDER } from "../kinds.js";
import { DISPLAY_GRADE_ORDER } from "../grades.js";

/** The operators a filter (or group) after the first can carry, in menu order. */
export const OPS = ["and", "or", "xor", "not"];

export const isGroupOpen = (f) => f.group === "open";
export const isGroupClose = (f) => f.group === "close";

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
  const acc = evalItems(rows, groupTree(filters), ctx);
  return acc ? rows.filter((r) => acc.rows.has(r)) : rows.slice();
}

/**
 * The flat stack as a tree: a leaf is `{f}`, a group `{f, items}` (f = its open marker).
 * Stray closes are dropped, unclosed groups end with the stack.
 */
function groupTree(filters) {
  const root = { items: [] };
  const open = [root];
  for (const f of filters) {
    if (isGroupOpen(f)) {
      const g = { f, items: [] };
      open[open.length - 1].items.push(g);
      open.push(g);
    } else if (isGroupClose(f)) {
      if (open.length > 1) open.pop();
    } else {
      open[open.length - 1].items.push({ f });
    }
  }
  return root.items;
}

/** One scope, left to right: `{rows: Set, owners: Set}`, or null when it holds no filter. */
function evalItems(rows, items, ctx) {
  let acc = null;
  for (const it of items) {
    let res;
    if (it.items) {
      res = evalItems(rows, it.items, ctx);
      if (!res) continue; // an empty group neither narrows nor widens
    } else {
      const hit = filterRows(rows, it.f, ctx);
      res = { rows: new Set(hit), owners: new Set(hit.map((r) => r.owner)) };
      // A texted NOT shows its own kind's rows that miss the text (see combine).
      if (it.f.op === "not" && (it.f.text || "").trim()) {
        res.pool = filterRows(rows, { ...it.f, text: "" }, ctx);
      }
    }
    acc = acc ? combine(acc, res, it.f.op) : res;
  }
  return acc;
}

function combine(acc, res, op) {
  if (op === "or") {
    return { rows: new Set([...acc.rows, ...res.rows]), owners: new Set([...acc.owners, ...res.owners]) };
  }
  if (op === "xor") {
    const keep = new Set([...acc.owners, ...res.owners]
      .filter((o) => acc.owners.has(o) !== res.owners.has(o)));
    return { rows: new Set([...acc.rows, ...res.rows].filter((r) => keep.has(r.owner))), owners: keep };
  }
  if (op === "not" && res.pool) {
    // "benzo AND NOT excretion = urine": the benzos' excretion rows that do not say
    // urine. An owner with no row of that kind drops out: missing data is no "not".
    const pool = res.pool.filter((r) => acc.owners.has(r.owner) && !res.owners.has(r.owner));
    return { rows: new Set(pool), owners: new Set(pool.map((r) => r.owner)) };
  }
  if (op === "not") {
    const keep = new Set([...acc.owners].filter((o) => !res.owners.has(o)));
    return { rows: new Set([...acc.rows].filter((r) => keep.has(r.owner))), owners: keep };
  }
  const keep = new Set([...res.owners].filter((o) => acc.owners.has(o)));
  return { rows: new Set([...res.rows].filter((r) => keep.has(r.owner))), owners: keep };
}

/**
 * Which entries of the flat stack are the first in their scope (a group's first entry,
 * or the stack's), i.e. whose operator is ignored. Stray closes count as nothing.
 * @returns {boolean[]}
 */
export function firstInScope(filters) {
  const seen = [false];
  return filters.map((f) => {
    if (isGroupClose(f)) {
      if (seen.length > 1) { seen.pop(); seen[seen.length - 1] = true; }
      return false;
    }
    const first = !seen[seen.length - 1];
    seen[seen.length - 1] = true;
    if (isGroupOpen(f)) seen.push(false);
    return first;
  });
}

/**
 * The kinds worth offering in filter `i`'s kind box. Only an AND narrows to the owners
 * the filters above it kept, so only then can a kind be useless: after
 * "Drug classes = benzo", an AND on "Regions" matches no owner (a benzodiazepine has no
 * region rows), so it is not offered. OR / XOR add owners, so every kind stays. Filters
 * above that match nothing (still being typed, or a typo) narrow nothing either: an
 * empty list would read as a broken box, so every kind stays then too.
 * @param {object[]} rows collectNodes' rows
 * @param {object[]} filters the whole stack
 * @param {number} i the filter whose kind box is opening
 * @param {object} ctx as runFilters
 * @returns {Set<string>|null} the kinds to offer, null = every kind
 */
export function compatibleKinds(rows, filters, i, ctx) {
  if (i <= 0) return null;
  // The prefix's owners bound filter i only through an unbroken AND chain: its own op
  // (skipped when it opens its scope) and every enclosing group's must be AND, else
  // (A AND NOT (B AND [i])) would wrongly restrict i to A minus B.
  const first = firstInScope(filters);
  let depth = 0;
  for (let j = i; j >= 0; j--) {
    const f = filters[j];
    if (j < i && isGroupClose(f)) { depth++; continue; }
    if (j < i && isGroupOpen(f) && depth > 0) { depth--; continue; }
    if (j < i && !isGroupOpen(f)) continue;
    // j === i, or an open marker enclosing i: its op matters unless it is first in scope.
    if (!first[j] && (f.op || "and") !== "and") return null;
  }
  if (filters.slice(0, i).every((f) => f.group)) return null;
  const owners = new Set(runFilters(rows, filters.slice(0, i), ctx).map((r) => r.owner));
  if (!owners.size) return null;
  const out = new Set();
  for (const r of rows) if (owners.has(r.owner)) out.add(r.kind);
  return out;
}

/** The sorting choices, in menu order (labels are `nodes.sort<Capitalized>`). */
export const SORTS = ["valueAsc", "valueDesc", "weakest", "strongest", "name", "kind"];

/** The sort a fresh browser (and a link without `nsort`) uses: smallest value first. */
export const DEFAULT_SORT = "valueAsc";

/**
 * Sort rows in place. "value" sorts read `row.value` (a T½ in hours, a Ki in nM...):
 * rows are grouped by kind first, since a half-life and a Ki are not comparable, and a
 * row without a value goes after every valued one, sorted by its claim text instead
 * (numeric-aware, so "route: faeces" < "route: urine", reversed for largest first).
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
      if (!va) {
        return byKind(a, b)
          || dir * a.notion.localeCompare(b.notion, undefined, { numeric: true })
          || byName(a, b);
      }
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
// bar. Trailing empty fields are dropped, and a scope's first entry has an empty op.
// A group marker puts "(" or ")" in the op field, an open marker its op in the next:
//   [{kind: "Drug class", text: "benzo"}, {group: "open", op: "not"}, {kind: "half"},
//    {group: "close"}]
//   -> "|Drug class|benzo,(|not,|half,)"
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
  const first = firstInScope(filters);
  return filters.map((f, i) => {
    const op = first[i] ? "" : f.op || "and";
    const fields = (isGroupClose(f) ? [")"] : isGroupOpen(f) ? ["(", op]
      : [op, f.kind || "", f.text || "", f.metabolites ? "m" : ""]).map(escField);
    while (fields.length && fields[fields.length - 1] === "") fields.pop();
    return fields.join(FIELD_SEP);
  }).join(FILTER_SEP);
}

/** Inverse of serializeFilters; an unknown op reads as "and". */
export function parseFilters(value) {
  const opOf = (op) => (OPS.includes(op) ? op : "and");
  return String(value || "").split(FILTER_SEP).map((part) => {
    const [op, kind, text, m] = Array.from({ length: 4 },
      (_, i) => decodeURIComponent(part.split(FIELD_SEP)[i] || ""));
    if (op === ")") return { group: "close" };
    if (op === "(") return { group: "open", op: opOf(kind) };
    return { op: opOf(op), kind, text, metabolites: m === "m" };
  });
}
