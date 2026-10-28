// The drug map's camera gestures. The camera is `{box, angle}`: the SVG viewBox (null =
// the fitted frame) and a rotation (radians) of the points about the frame centre.
// Wheel or pinch zooms about the pointer / the fingers' midpoint, shift-wheel or a
// two-finger twist rotates about it, one-finger drag pans, double-click refits (and
// unrotates).
//
// The camera is bounded so it cannot lose the map: zooming out stops at MAX_UNZOOM x the
// fitted frame (a little room to peek behind the watermark or the title, no more: further
// out only shrinks the dots, and a wheel scroll meant for the page kept zooming out), and a
// pan stops once half the screen shows empty space past the fitted frame (`clampBox`).

import { W, H, rotate } from "./dom.js";

const ZOOM_STEP = 1.15;
const ROTATE_STEP = Math.PI / 36; // 5 degrees per shift-wheel notch
// A pointer moving less than this (px) is still a click, not a pan.
const DRAG_SLOP_PX = 5;
/** How far (x the fitted frame's width) the reader may zoom out. */
export const MAX_UNZOOM = 1.1;

/**
 * Bound a viewBox against the fitted frame `fit`: at most MAX_UNZOOM x its width (shrunk
 * about its own centre), and shifted so its centre stays inside `fit`, i.e. at most half the
 * screen past the frame's edge. E.g. fit {x:0, y:0, w:1000, h:600} and a 500-wide box at
 * x = 900 (centre 1150, past the right edge) comes back at x = 750 (centre 1000).
 * DOM-free (node tests).
 * @param {{x: number, y: number, w: number, h: number}} box
 * @param {{x: number, y: number, w: number, h: number}} fit
 * @returns {{x: number, y: number, w: number, h: number}}
 */
export function clampBox(box, fit) {
  let { x, y, w, h } = box;
  const maxW = fit.w * MAX_UNZOOM;
  if (w > maxW) {
    const k = maxW / w;
    x += (w - maxW) / 2;
    y += (h - h * k) / 2;
    w = maxW;
    h *= k;
  }
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  x = clamp(x, fit.x - w / 2, fit.x + fit.w - w / 2);
  y = clamp(y, fit.y - h / 2, fit.y + fit.h - h / 2);
  return { x, y, w, h };
}

/**
 * @param {SVGSVGElement} svg
 * @param {() => {box: object|null, angle: number}} get
 * @param {(cam: {box: object|null, angle: number}) => void} set
 * @param {() => object} fitted  the frame shown when `box` is null
 */
export function wireGestures(svg, get, rawSet, fitted) {
  // Every gesture goes through the bounds; the zoom-out cap itself sits in `camAt` (so a
  // capped wheel keeps the pointer's point still), clampBox's shrink is the pinch backstop.
  const set = (cam) => rawSet(cam.box ? { ...cam, box: clampBox(cam.box, fitted()) } : cam);
  const frame = () => get().box || fitted();
  const frac = (ev) => {
    const r = svg.getBoundingClientRect();
    return { fx: (ev.clientX - r.left) / r.width, fy: (ev.clientY - r.top) / r.height };
  };
  const toSvg = (ev, b = frame()) => {
    const { fx, fy } = frac(ev);
    return { x: b.x + fx * b.w, y: b.y + fy * b.h };
  };
  // The camera that is `w` wide, turned by `angle`, and keeps the unrotated point `at`
  // under screen fraction (fx, fy): zoom, rotation and pan in one formula.
  const camAt = (w, angle, at, { fx, fy }) => {
    w = Math.min(fitted().w * MAX_UNZOOM, Math.max(W / 40, w));
    const h = w * (H / W), q = rotate(at, angle);
    return { box: { x: q.x - fx * w, y: q.y - fy * h, w, h }, angle };
  };
  // The unrotated point under a screen position.
  const anchor = (ev) => rotate(toSvg(ev), -get().angle);

  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const { angle } = get(), d = ev.deltaY || ev.deltaX;
    set(ev.shiftKey
      ? camAt(frame().w, angle + Math.sign(d) * ROTATE_STEP, anchor(ev), frac(ev))
      : camAt(frame().w * (d > 0 ? ZOOM_STEP : 1 / ZOOM_STEP), angle, anchor(ev), frac(ev)));
  }, { passive: false });

  // Every pointer down on the plot is tracked, a dot included (a finger landing on a
  // dot can still pan or pinch): one = drag to pan once it moves past DRAG_SLOP_PX, two
  // = pinch (zoom + rotate), and going from two back to one resumes the pan from the
  // finger left. Moves and ends are read on `window`, so a pointer released off the
  // plot never stays behind as a ghost that turns the next touch into a pinch. A
  // gesture swallows the click that ends it, so a pan never opens or hides a drug.
  const touches = new Map(); // pointerId -> last event
  let drag = null, pinch = null, gestured = false;
  const two = () => {
    const [a, b] = [...touches.values()];
    return { clientX: (a.clientX + b.clientX) / 2, clientY: (a.clientY + b.clientY) / 2,
      dist: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) || 1,
      turn: Math.atan2(b.clientY - a.clientY, b.clientX - a.clientX) };
  };
  const startDrag = (ev, moved) => {
    drag = { start: toSvg(ev), b: frame(), x0: ev.clientX, y0: ev.clientY, moved };
  };
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    if (!touches.size) gestured = false;
    touches.set(ev.pointerId, ev);
    if (touches.size === 2) {
      const m = two();
      drag = null;
      gestured = true;
      pinch = { ...m, at: anchor(m), w: frame().w, angle: get().angle };
    } else if (touches.size === 1) startDrag(ev, false);
  });
  window.addEventListener("pointermove", (ev) => {
    if (!touches.has(ev.pointerId)) return;
    touches.set(ev.pointerId, ev);
    if (pinch && touches.size === 2) {
      const m = two();
      set(camAt(pinch.w * (pinch.dist / m.dist), pinch.angle + m.turn - pinch.turn, pinch.at, frac(m)));
    } else if (drag) {
      if (!drag.moved && Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < DRAG_SLOP_PX) return;
      drag.moved = gestured = true;
      const { fx, fy } = frac(ev);
      set({ box: { ...drag.b, x: drag.start.x - fx * drag.b.w, y: drag.start.y - fy * drag.b.h }, angle: get().angle });
    }
  });
  const end = (ev) => {
    if (!touches.delete(ev.pointerId)) return;
    pinch = null;
    drag = null;
    if (touches.size === 1) startDrag([...touches.values()][0], true);
  };
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", end);
  // Capture phase, ahead of a dot's own click (open) and contextmenu (hide) handlers.
  for (const type of ["click", "contextmenu"]) {
    svg.addEventListener(type, (ev) => {
      if (!gestured) return;
      ev.stopPropagation();
      ev.preventDefault();
    }, true);
  }
  svg.addEventListener("dblclick", () => set({ box: null, angle: 0 }));
}
