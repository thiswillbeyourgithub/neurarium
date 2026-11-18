// Data browser filter stack UI: one row per filter (drag handle, AND/OR/XOR operator,
// kind box, text box, "include metabolites", remove) plus the "Add filter" button.
// Pure state lives in the `filters` array handed to node-browser/query.js runFilters;
// this file only edits it. Rows reorder by dragging the handle (a long press on touch).

import { el, btn } from "../panel/dom.js";
import { OPS } from "./query.js";

// A touch drag starts only after a long press, so a tap on the handle stays a tap.
const LONG_PRESS_MS = 400;

/**
 * @param {object} opts
 * @param {Function} opts.t i18n lookup
 * @param {Array<[string, string]>} opts.kindOptions [kind, label] pairs for the kind box
 * @param {() => void} opts.onChange called after any edit (typing is debounced by caller)
 * @returns {{root: HTMLElement, filters: object[], showMetabolites: (fn: Function) => void}}
 */
export function createFilterStack({ t, kindOptions, onChange }) {
  const filters = [];
  const rowEls = [];
  const root = el("div", "node-filter-stack");
  const listEl = el("div", "node-filters");
  // One shared datalist: the kind box is free text, so a reader types "half" and the
  // browser offers "Drug half-life" (query.kindsFor also accepts any label substring).
  const datalist = document.createElement("datalist");
  datalist.id = "nodes-kind-list";
  for (const [, label] of kindOptions) {
    const o = document.createElement("option");
    o.value = label;
    datalist.appendChild(o);
  }
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

  const addRow = () => {
    const f = { kind: "", text: "", op: "and", metabolites: false };
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
    const kind = makeInput("node-filter-kind", t("nodes.kindPlaceholder"));
    kind.setAttribute("list", datalist.id);
    const text = makeInput("drugs-filter node-filter-text", t("nodes.filter"));
    const metab = el("label", "list-toggle node-filter-metab");
    const metabBox = document.createElement("input");
    metabBox.type = "checkbox";
    metab.appendChild(metabBox);
    metab.appendChild(el("span", null, t("nodes.metabolites")));
    metab.title = t("nodes.metabolitesHint");
    metab.hidden = true;
    const remove = btn("node-filter-remove", "✕");
    remove.title = t("nodes.removeFilter");
    remove.setAttribute("aria-label", t("nodes.removeFilter"));

    op.addEventListener("change", () => { f.op = op.value; onChange(true); });
    kind.addEventListener("input", () => { f.kind = kind.value; onChange(); });
    text.addEventListener("input", () => { f.text = text.value; onChange(); });
    metabBox.addEventListener("change", () => { f.metabolites = metabBox.checked; onChange(true); });
    remove.addEventListener("click", () => {
      const i = filters.indexOf(f);
      filters.splice(i, 1);
      rowEls.splice(i, 1);
      row.remove();
      relabel();
      onChange(true);
    });
    wireDrag(handle, row, f);

    for (const n of [handle, op, kind, text, metab, remove]) row.appendChild(n);
    filters.push(f);
    rowEls.push({ row, op, text, remove, metab, f });
    listEl.appendChild(row);
    relabel();
    return text;
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
      if (moved) onChange(true);
    };
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  }

  addBtn.addEventListener("click", () => {
    addRow().focus();
    onChange(true);
  });
  addRow();
  root.appendChild(datalist);
  root.appendChild(listEl);
  root.appendChild(addBtn);

  return {
    root,
    filters,
    /** Show each row's "include metabolites" box only where `touches(f)` says it matters. */
    showMetabolites(touches) {
      for (const r of rowEls) r.metab.hidden = !r.f.metabolites && !touches(r.f);
    },
  };
}
