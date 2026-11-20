// Data browser kind box: a free-text input with our own suggestion list under it.
// Not a native <datalist>: its popup is drawn by the browser, unstyleable (transparent
// over the panel on some platforms) and slow to open on phones. This list is a plain
// opaque <ul>, filtered by label substring like query.kindsFor matches.
//
// Entries come grouped (kind-groups.js kindChoices): owner and section headers are
// pickable rows too, indented by depth. Typing keeps every matching entry plus the
// headers above it, so "half" still shows it sits under Drug > Pharmacokinetics.

import { el } from "../panel/dom.js";

/**
 * @param {object} opts
 * @param {HTMLInputElement} opts.input the kind text box (already built by the caller)
 * @param {() => {label: string, depth: number, head?: boolean}[]} opts.labels the entries to offer now,
 *   in menu order (asked on every open, so the caller can drop kinds the filters above
 *   make useless)
 * @param {(s: string) => string} opts.fold case + accent fold, as the filter uses
 * @param {(label: string) => void} opts.onPick a suggestion was chosen
 * @returns {HTMLElement} the wrapper to place in the row (holds input + list)
 */
export function wrapKindPicker({ input, labels, fold, onPick }) {
  const wrap = el("span", "node-kind-wrap");
  const list = el("ul", "node-kind-suggest");
  list.setAttribute("role", "listbox");
  list.hidden = true;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  wrap.appendChild(input);
  wrap.appendChild(list);
  let active = -1;

  const items = () => [...list.children];
  const setActive = (i) => {
    const li = items();
    active = li.length ? (i + li.length) % li.length : -1;
    li.forEach((n, k) => n.classList.toggle("active", k === active));
    if (active >= 0) li[active].scrollIntoView({ block: "nearest" });
  };
  const close = () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    active = -1;
  };
  const open = () => {
    // On focus the box's own text is selected, so a reader means to replace it: offer
    // every kind then, and filter only once they type.
    const q = input.selectionStart === 0 && input.selectionEnd === input.value.length
      ? "" : fold(input.value.trim());
    const hits = matching(labels(), q, fold);
    list.textContent = "";
    for (const { label, depth, head } of hits) {
      const li = el("li", `depth-${depth}${head ? " head" : ""}`, label);
      li.dataset.label = label;
      li.setAttribute("role", "option");
      // Picked on click, which a touch scroll never fires, so a finger can scroll a long
      // list without choosing what it lands on. mousedown (also synthesized by a tap) is
      // cancelled so the input keeps focus and its blur does not close the list before
      // the click arrives.
      li.addEventListener("mousedown", (e) => e.preventDefault());
      li.addEventListener("click", () => pick(label));
      list.appendChild(li);
    }
    list.hidden = hits.length === 0;
    input.setAttribute("aria-expanded", String(!list.hidden));
    active = -1;
  };
  const pick = (label) => {
    input.value = label;
    close();
    onPick(label);
  };

  input.addEventListener("focus", () => requestAnimationFrame(open));
  input.addEventListener("input", open);
  input.addEventListener("blur", close);
  input.addEventListener("keydown", (e) => {
    if (list.hidden && e.key === "ArrowDown") { open(); return; }
    if (list.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setActive(active + (e.key === "ArrowDown" ? 1 : -1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(items()[active].dataset.label);
    } else if (e.key === "Escape") {
      e.stopPropagation();
      close();
    }
  });
  return wrap;
}

/**
 * The entries whose label holds `q`, each with the headers above it (in order, once).
 * @param {{label: string, depth: number}[]} entries
 * @param {string} q folded query, "" keeps all
 * @param {(s: string) => string} fold
 */
function matching(entries, q, fold) {
  if (!q) return entries;
  const out = [];
  const above = []; // above[d] = the latest entry at depth d
  let shown = -1; // index in `entries` of the last ancestor chain already emitted
  entries.forEach((e, i) => {
    above[e.depth] = { e, i };
    above.length = e.depth + 1;
    if (!fold(e.label).includes(q)) return;
    for (const a of above) if (a.i > shown) { out.push(a.e); shown = a.i; }
  });
  return out;
}
