// Small DOM helpers shared by the drug map's modules (view, controls, gestures), and the
// plot's fixed frame: W x H viewBox units, rotation about its centre.

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
