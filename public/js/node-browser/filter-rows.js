// Data browser filter stack UI: one row per filter (drag handle, AND/OR/XOR operator,
// kind box, text box, "include metabolites", remove) plus the "Add filter" button.
// Pure state lives in the `filters` array handed to node-browser/query.js runFilters;
// this file only edits it. Rows reorder by dragging the handle (a long press on touch).

import { el, btn } from "../panel/dom.js";
import { OPS } from "./query.js";
import { wrapKindPicker } from "./kind-picker.js";

// A touch drag starts only after a long press, so a tap on the handle stays a tap.
const LONG_PRESS_MS = 400;

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

  // Ids, operator and remove visibility follow position: the first row has no operator
  // (nothing on its left) and keeps the `#nodes-filter` id the tour anchors on.
  const relabel = () => {
    rowEls.forEach((r, i) => {
      r.op.hidden = i === 0;
      r.text.id = i === 0 ? "nodes-filter" : "";
      r.remove.hidden = rowEls.length === 1;
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

  const addRow = (init = {}) => {
    const f = { kind: "", text: "", op: "and", metabolites: false, ...init };
    const row = el("div", "node-filter");
    const handle = el("span", "node-filter-handle", "⠿");
    handle.title = t("nodes.dragHint");
    const op = document.createElement("select");
    op.className = "node-select node-filter-op";
    op.title = t("nodes.opLabel");
    op.setAttribute("aria-label", t("nodes.opLabel"));
    for (const o of OPS) {
      const opt = document.createElement("option");
      opt.value = o;
      opt.textContent = t(`nodes.op_${o}`);
      op.appendChild(opt);
    }
    op.value = f.op;
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
    const remove = btn("node-filter-remove", "✕");
    remove.title = t("nodes.removeFilter");
    remove.setAttribute("aria-label", t("nodes.removeFilter"));

    op.addEventListener("change", () => { f.op = op.value; onChange(); });
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
      const i = filters.indexOf(f);
      filters.splice(i, 1);
      rowEls.splice(i, 1);
      row.remove();
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
    filters.push(f);
    rowEls.push({ row, op, text, remove, metab, f });
    listEl.appendChild(row);
    relabel();
    return kind;
  };

  // Drag to reorder: pointer events cover mouse and touch alike. The row under the
  // pointer swaps places live, so the reader sees the order they are building.
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
      if (!over || over === row || over.parentNode !== listEl) return;
      const from = filters.indexOf(f);
      const to = rowEls.findIndex((r) => r.row === over);
      const [rf] = filters.splice(from, 1);
      filters.splice(to, 0, rf);
      const [re] = rowEls.splice(from, 1);
      rowEls.splice(to, 0, re);
      listEl.insertBefore(row, to > from ? over.nextSibling : over);
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
    addRow().focus();
    onChange();
  });
  addRow();
  root.appendChild(listEl);
  root.appendChild(addBtn);

  return {
    root,
    filters,
    /** Replace the whole stack (a shared link); fires no onChange. */
    setFilters(list) {
      filters.length = 0;
      rowEls.length = 0;
      listEl.textContent = "";
      for (const f of list.length ? list : [{}]) addRow(f);
    },
    /** Show each row's "include metabolites" box only where `touches(f)` says it matters. */
    showMetabolites(touches) {
      for (const r of rowEls) r.metab.hidden = !r.f.metabolites && !touches(r.f);
    },
  };
}
