// Data browser filter stack UI: one row per filter (drag handle, operator menu, kind box,
// text box, "include metabolites", remove) plus the "Add filter" button. The operator
// menu also offers BEGIN GROUP / END GROUP, which insert a "(" / ")" marker row before
// the row (see node-browser/query.js for the flat-list grouping): the rows between the
// markers render indented behind a parenthesis, and "Add filter" lands inside a group
// still open at the end of the stack.
// Pure state lives in the `filters` array handed to node-browser/query.js runFilters;
// this file only edits it. Rows reorder by dragging the handle (a long press on touch).

import { el, btn } from "../panel/dom.js";
import { OPS, firstInScope, isGroupOpen, isGroupClose } from "./query.js";
import { wrapKindPicker } from "./kind-picker.js";

// A touch drag starts only after a long press, so a tap on the handle stays a tap.
const LONG_PRESS_MS = 400;
// The operator menu's two group actions: picking one edits the stack, never stays picked.
const BEGIN = "begin";
const END = "end";

/**
 * @param {object} opts
 * @param {Function} opts.t i18n lookup
 * @param {(i: number) => string[]} opts.kindLabelsFor the kind labels filter `i`'s box
 *   offers (asked each time it opens, see query.compatibleKinds)
 * @param {(s: string) => string} opts.fold case + accent fold, for the kind suggestions
 * @param {() => void} opts.onChange called after any edit (the query is now stale)
 * @param {() => void} opts.onSubmit Enter in a text or kind box: run the query
 * @returns {{root: HTMLElement, filters: object[], setFilters: (list: object[]) => void,
 *            showMetabolites: (fn: Function) => void}}
 */
export function createFilterStack({ t, kindLabelsFor, fold, onChange, onSubmit }) {
  const filters = [];
  const rowEls = [];
  const root = el("div", "node-filter-stack");
  const listEl = el("div", "node-filters");
  const addBtn = btn("node-add-filter", t("nodes.addFilter"));

  const option = (sel, value, label) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    sel.appendChild(opt);
  };

  // The menu follows position: a scope's first entry has no operator (nothing on its
  // left) so it offers only the group actions, and END GROUP needs an open group.
  const fillOps = (r, first, inGroup) => {
    r.op.textContent = "";
    if (first) option(r.op, "", "·");
    else for (const o of OPS) option(r.op, o, t(`nodes.op_${o}`));
    option(r.op, BEGIN, t("nodes.op_begin"));
    if (inGroup && !first && !isGroupOpen(r.f)) option(r.op, END, t("nodes.op_end"));
    r.op.value = first ? "" : r.f.op || "and";
  };

  // Rebuild the nesting from the flat list: an open marker's row, then a group box
  // (the parenthesis) holding what follows up to its close marker's row. Also redoes
  // each menu, the `#nodes-filter` id the tour anchors on (first real filter's text)
  // and the remove buttons (never on the last filter).
  const relabel = () => {
    const first = firstInScope(filters);
    const realCount = filters.filter((f) => !f.group).length;
    const stack = [listEl];
    let anchored = false;
    listEl.textContent = "";
    rowEls.forEach((r, i) => {
      const host = stack[stack.length - 1];
      if (isGroupClose(r.f)) {
        r.row.classList.toggle("stray", stack.length === 1);
        if (stack.length > 1) stack.pop();
        stack[stack.length - 1].appendChild(r.row);
        return;
      }
      if (r.op) fillOps(r, first[i], stack.length > 1);
      host.appendChild(r.row);
      if (isGroupOpen(r.f)) {
        const box = el("div", "node-filter-group");
        host.appendChild(box);
        stack.push(box);
        return;
      }
      r.text.id = !anchored ? "nodes-filter" : "";
      anchored = true;
      r.remove.hidden = realCount === 1;
    });
  };

  const makeInput = (cls, placeholder) => {
    const input = document.createElement("input");
    input.type = "text";
    input.className = cls;
    input.autocomplete = "off";
    input.placeholder = placeholder;
    input.setAttribute("aria-label", placeholder);
    return input;
  };

  const makeRemove = (titleKey) => {
    const remove = btn("node-filter-remove", "✕");
    remove.title = t(titleKey);
    remove.setAttribute("aria-label", t(titleKey));
    return remove;
  };

  const insertAt = (i, entry) => {
    filters.splice(i, 0, entry.f);
    rowEls.splice(i, 0, entry);
  };
  const removeAt = (i) => {
    filters.splice(i, 1);
    rowEls.splice(i, 1);
  };

  // The operator menu: an operator edits this entry, a group action inserts a marker
  // before it. BEGIN hands the entry's operator to the new group (which now sits where
  // the entry did) and makes the entry the group's first.
  const makeOpSelect = (f) => {
    const op = document.createElement("select");
    op.className = "node-select node-filter-op";
    op.title = t("nodes.opLabel");
    op.setAttribute("aria-label", t("nodes.opLabel"));
    op.addEventListener("change", () => {
      const i = filters.indexOf(f);
      if (op.value === BEGIN) {
        insertAt(i, makeMarker({ group: "open", op: firstInScope(filters)[i] ? "and" : f.op }));
      } else if (op.value === END) {
        insertAt(i, makeMarker({ group: "close" }));
      } else {
        f.op = op.value;
      }
      relabel();
      onChange();
    });
    return op;
  };

  // A "(" or ")" row: handle, the operator menu (an open marker only: how the group
  // combines with what precedes it), the parenthesis, and ✕ to ungroup (drops both
  // markers, keeps the filters inside).
  function makeMarker(init) {
    const f = init.group === "open" ? { group: "open", op: init.op || "and" } : { group: "close" };
    const row = el("div", `node-filter node-filter-marker ${f.group}`);
    const handle = el("span", "node-filter-handle", "⠿");
    handle.title = t("nodes.dragHint");
    const op = isGroupOpen(f) ? makeOpSelect(f) : null;
    const paren = el("span", "node-filter-paren", isGroupOpen(f) ? "(" : ")");
    const remove = makeRemove("nodes.ungroup");
    const entry = { row, op, f };
    remove.addEventListener("click", () => {
      const pair = matchingMarker(filters.indexOf(f));
      removeAt(filters.indexOf(f));
      if (pair) removeAt(filters.indexOf(pair));
      relabel();
      onChange();
    });
    wireDrag(handle, row, f);
    for (const n of [handle, op, paren, remove]) if (n) row.appendChild(n);
    return entry;
  }

  // The marker paired with the one at `i` (null for an unclosed open or a stray close).
  const matchingMarker = (i) => {
    const dir = isGroupOpen(filters[i]) ? 1 : -1;
    let depth = 0;
    for (let j = i + dir; j >= 0 && j < filters.length; j += dir) {
      const f = filters[j];
      if ((dir > 0 ? isGroupOpen : isGroupClose)(f)) depth++;
      else if ((dir > 0 ? isGroupClose : isGroupOpen)(f)) {
        if (!depth) return f;
        depth--;
      }
    }
    return null;
  };

  function makeFilter(init) {
    const f = { kind: "", text: "", op: "and", metabolites: false, ...init };
    const row = el("div", "node-filter");
    const handle = el("span", "node-filter-handle", "⠿");
    handle.title = t("nodes.dragHint");
    const op = makeOpSelect(f);
    const kind = makeInput("node-filter-kind", t("nodes.kindPlaceholder"));
    kind.value = f.kind;
    const kindBox = wrapKindPicker({
      input: kind, labels: () => kindLabelsFor(filters.indexOf(f)), fold,
      onPick: (label) => { f.kind = label; onChange(); },
    });
    const text = makeInput("drugs-filter node-filter-text", t("nodes.filter"));
    text.value = f.text;
    const metab = el("label", "list-toggle node-filter-metab");
    const metabBox = document.createElement("input");
    metabBox.type = "checkbox";
    metabBox.checked = f.metabolites;
    metab.appendChild(metabBox);
    metab.appendChild(el("span", null, t("nodes.metabolites")));
    metab.title = t("nodes.metabolitesHint");
    metab.hidden = true;
    const remove = makeRemove("nodes.removeFilter");

    kind.addEventListener("input", () => { f.kind = kind.value; onChange(); });
    text.addEventListener("input", () => { f.text = text.value; onChange(); });
    metabBox.addEventListener("change", () => { f.metabolites = metabBox.checked; onChange(); });
    // Enter runs the query. The kind box's own keydown (registered first, in
    // wrapKindPicker) already took an Enter that picked a highlighted suggestion.
    for (const box of [kind, text]) {
      box.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.defaultPrevented) { e.preventDefault(); box.blur(); onSubmit(); }
      });
    }
    remove.addEventListener("click", () => {
      removeAt(filters.indexOf(f));
      relabel();
      onChange();
    });
    wireDrag(handle, row, f);
    // On a phone a tap must land the caret and raise the keyboard: a tap on a box
    // selects what it holds (retyping a kind replaces it), and a tap on the row's bare
    // background focuses its text box rather than doing nothing.
    for (const box of [kind, text]) {
      box.addEventListener("focus", () => { if (box.value) box.select(); });
    }
    row.addEventListener("click", (e) => { if (e.target === row) text.focus(); });

    for (const n of [handle, op, kindBox, text, metab, remove]) row.appendChild(n);
    return { row, op, text, remove, metab, f, kind };
  }

  const append = (init = {}) => {
    const entry = init.group ? makeMarker(init) : makeFilter(init);
    insertAt(filters.length, entry);
    return entry;
  };

  // Drag to reorder: pointer events cover mouse and touch alike. The row under the
  // pointer swaps places live, so the reader sees the order they are building; moving
  // a marker re-draws which rows its parenthesis encloses.
  function wireDrag(handle, row, f) {
    let timer = 0;
    let dragging = false;
    let moved = false;
    const start = () => { dragging = true; moved = false; row.classList.add("dragging"); };
    handle.addEventListener("pointerdown", (e) => {
      handle.setPointerCapture(e.pointerId);
      if (e.pointerType === "mouse") start();
      else timer = setTimeout(start, LONG_PRESS_MS);
    });
    handle.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const over = document.elementFromPoint(e.clientX, e.clientY)?.closest(".node-filter");
      if (!over || over === row || !listEl.contains(over)) return;
      const from = filters.indexOf(f);
      const to = rowEls.findIndex((r) => r.row === over);
      const [re] = rowEls.splice(from, 1);
      filters.splice(from, 1);
      insertAt(to, re);
      moved = true;
      relabel();
    });
    const end = () => {
      clearTimeout(timer);
      if (!dragging) return;
      dragging = false;
      row.classList.remove("dragging");
      if (moved) onChange();
    };
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  }

  addBtn.addEventListener("click", () => {
    const { kind } = append();
    relabel();
    kind.focus();
    onChange();
  });
  append();
  relabel();
  root.appendChild(listEl);
  root.appendChild(addBtn);

  return {
    root,
    filters,
    /** Replace the whole stack (a shared link); fires no onChange. */
    setFilters(list) {
      filters.length = 0;
      rowEls.length = 0;
      for (const f of list.some((x) => !x.group) ? list : [...list, {}]) append(f);
      relabel();
    },
    /** Show each row's "include metabolites" box only where `touches(f)` says it matters. */
    showMetabolites(touches) {
      for (const r of rowEls) if (r.metab) r.metab.hidden = !r.f.metabolites && !touches(r.f);
    },
  };
}
