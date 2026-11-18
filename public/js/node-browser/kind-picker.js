// Data browser kind box: a free-text input with our own suggestion list under it.
// Not a native <datalist>: its popup is drawn by the browser, unstyleable (transparent
// over the panel on some platforms) and slow to open on phones. This list is a plain
// opaque <ul>, filtered by label substring like query.kindsFor matches.

import { el } from "../panel/dom.js";

/**
 * @param {object} opts
 * @param {HTMLInputElement} opts.input the kind text box (already built by the caller)
 * @param {string[]} opts.labels every kind label, in menu order
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
  const folded = labels.map((l) => [l, fold(l)]);
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
    const hits = folded.filter(([, f]) => !q || f.includes(q));
    list.textContent = "";
    for (const [label] of hits) {
      const li = el("li", null, label);
      li.setAttribute("role", "option");
      // pointerdown, not click: it fires before the input's blur closes the list.
      li.addEventListener("pointerdown", (e) => { e.preventDefault(); pick(label); });
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
      pick(items()[active].textContent);
    } else if (e.key === "Escape") {
      e.stopPropagation();
      close();
    }
  });
  return wrap;
}
