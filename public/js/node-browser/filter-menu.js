// Data browser filter row's kebab (⋮) button and the small menu it opens: a list of
// action buttons plus optional extra rows (the "include metabolites" checkbox). The
// menu closes on a pick, on Escape, or on any press outside it.

import { el, btn } from "../panel/dom.js";

/**
 * @param {object} opts
 * @param {string} opts.title the button's tooltip / aria label
 * @param {{label: string, run: () => void}[]} opts.actions menu buttons, in order
 * @param {HTMLElement[]} [opts.extras] rows appended under the actions (kept live, not closing)
 * @returns {{root: HTMLElement, items: HTMLButtonElement[]}} the wrapper to place in the
 *   row, and the action buttons (in `actions` order) so the caller can disable one
 */
export function makeKebab({ title, actions, extras = [] }) {
  const root = el("span", "node-filter-kebab");
  const toggle = btn("node-filter-kebab-btn", "⋮");
  toggle.title = title;
  toggle.setAttribute("aria-label", title);
  toggle.setAttribute("aria-haspopup", "menu");
  toggle.setAttribute("aria-expanded", "false");
  const menu = el("div", "node-filter-menu");
  menu.setAttribute("role", "menu");
  menu.hidden = true;

  const outside = (e) => { if (!root.contains(e.target)) close(); };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); toggle.focus(); } };
  function close() {
    menu.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    document.removeEventListener("pointerdown", outside, true);
    menu.removeEventListener("keydown", onKey);
  }
  const open = () => {
    menu.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    document.addEventListener("pointerdown", outside, true);
    menu.addEventListener("keydown", onKey);
  };
  toggle.addEventListener("click", () => (menu.hidden ? open() : close()));

  const items = actions.map(({ label, run }) => {
    const b = btn("node-filter-menu-item", label);
    b.setAttribute("role", "menuitem");
    b.addEventListener("click", () => { close(); run(); });
    menu.appendChild(b);
    return b;
  });
  for (const x of extras) menu.appendChild(x);
  root.appendChild(toggle);
  root.appendChild(menu);
  return { root, items };
}
