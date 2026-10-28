// Small DOM helpers shared by the drug map's modules (view, controls, gestures), and the
// plot's fixed frame: W x H viewBox units, rotation about its centre.

import { foldText } from "../search/query.js";

export const SVG = "http://www.w3.org/2000/svg";
export const W = 1000, H = 640;
export const LONG_PRESS_MS = 500;

export const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

export const button = (cls, text, onClick) => {
  const b = el("button", cls, text);
  b.type = "button";
  if (onClick) b.addEventListener("click", onClick);
  return b;
};

export const svgEl = (tag, attrs) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  return e;
};

/**
 * A search box over a grouped chip list (`.dm-tgroup` = a `.dm-tgroup-head` + its
 * `.dm-titems` chips), so a long list (60+ targets, 40+ classes) is found by typing
 * instead of scrolling. Matching folds case, accents, Greek letters and dashes like the
 * main search (`foldText`), so "5ht2a" finds "5-HT2A". A chip shows when it matches or
 * its group heading does (typing "dopamine" keeps every dopamine target); a group left
 * with no chip hides. Filtering only hides chips, it never changes the selection.
 * `apply()` re-filters, for a list rebuilt after typing (the axes list re-renders).
 * A flat list with no `.dm-tgroup` (a PC caption's weights, view.js) filters its children,
 * one row each.
 * @param {HTMLElement} list
 * @param {string} placeholder
 * @returns {{input: HTMLInputElement, apply: () => void}}
 */
export function chipSearch(list, placeholder) {
  const input = el("input", "dm-search");
  input.type = "search";
  input.placeholder = placeholder;
  input.setAttribute("aria-label", placeholder);
  const apply = () => {
    const q = foldText(input.value.trim());
    // A flat list (no groups, the axis dropdowns): each child is one row.
    if (!list.querySelector(".dm-tgroup")) {
      for (const row of list.children) row.hidden = !!q && !foldText(row.textContent).includes(q);
      return;
    }
    for (const group of list.querySelectorAll(".dm-tgroup")) {
      const head = group.querySelector(".dm-tgroup-head");
      const headHit = !q || foldText(head.textContent).includes(q);
      let any = false;
      for (const chip of group.querySelectorAll(".dm-titems .dm-chip")) {
        const hit = headHit || foldText(chip.textContent).includes(q);
        chip.hidden = !hit;
        any = any || hit;
      }
      group.hidden = !any;
    }
  };
  input.addEventListener("input", apply);
  return { input, apply };
}

/** A folded section: a rounded box whose summary names it and shows its current value. */
export function foldBox(title, cls = "") {
  const box = el("details", `dm-box ${cls}`.trim());
  const summary = el("summary");
  const value = el("span", "dm-box-value");
  summary.append(el("span", "dm-box-title", title), value);
  const body = el("div", "dm-box-body");
  box.append(summary, body);
  return { box, body, setValue: (text) => { value.textContent = text || ""; } };
}

/**
 * The gesture every filter list shares: a click picks, shift-click or a long press
 * (touch) drops. The long press swallows the click that follows it.
 */
export function pickOrDrop(node, pick, drop) {
  let pressed = null, longPressed = false;
  node.addEventListener("pointerdown", (ev) => {
    longPressed = false;
    if (ev.pointerType === "mouse") return;
    pressed = setTimeout(() => { longPressed = true; drop(); }, LONG_PRESS_MS);
  });
  for (const type of ["pointerup", "pointercancel", "pointerleave"]) {
    node.addEventListener(type, () => clearTimeout(pressed));
  }
  node.addEventListener("contextmenu", (ev) => ev.preventDefault());
  node.addEventListener("click", (ev) => {
    if (longPressed) return;
    if (ev.shiftKey) drop();
    else pick();
  });
}

/** Rotate point `p` by `angle` radians about the frame centre (y down, so clockwise). */
export function rotate(p, angle) {
  if (!angle) return { x: p.x, y: p.y };
  const c = Math.cos(angle), s = Math.sin(angle), dx = p.x - W / 2, dy = p.y - H / 2;
  return { x: W / 2 + dx * c - dy * s, y: H / 2 + dx * s + dy * c };
}
