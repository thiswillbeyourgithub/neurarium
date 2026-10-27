// The drug map's focus layer: which drug the pointer means, and its name drawn on top.
//
// Names are placed by layout.js, which drops one rather than overlap (a crowded cluster
// shows a few names, not all), so a dot can sit nameless. The focus layer makes every
// dot readable anyway:
// - mouse: the dot nearest the pointer (within NEAR_PX.mouse screen px) shows its name
//   and a ring, whether or not layout.js placed a name for it; a click opens it.
// - touch: a tap on or near a dot (NEAR_PX.touch, a finger is wider) selects it (name +
//   ring); a second tap on the same dot opens it. A tap on empty plot clears it.
// - right-click / long-press hides the meant drug, as before.
// The focus name is drawn larger than the placed names, and while it shows, the placed
// names it would collide with (its own drug's included, so a name never shows twice)
// are hidden (`dm-label-under`), so it reads cleanly inside a crowded cluster.
// "Near" is measured from the pointer, so a tap between two dots picks the closer one,
// and a tiny dot needs no pixel-exact aim. A click on a placed name means its drug even
// when that name runs farther than NEAR_PX from the dot.
//
// `nearestDot` is DOM-free (node tests); `createFocus` wires the events and draws.

import { svgEl } from "./dom.js";

/** How far (screen px) from a dot the pointer still means it. */
export const NEAR_PX = { mouse: 24, touch: 32 };

/** How much larger (px) the focus name is than the placed names. */
const FOCUS_FONT_GAIN = 4;

/**
 * Whether two {x, y, width, height} boxes overlap (DOM-free, node tests).
 * @param {{x: number, y: number, width: number, height: number}} a
 * @param {{x: number, y: number, width: number, height: number}} b
 * @returns {boolean}
 */
export const boxesOverlap = (a, b) => a.x < b.x + b.width && b.x < a.x + a.width
  && a.y < b.y + b.height && b.y < a.y + a.height;

/**
 * The dot nearest (x, y), if within `maxPx`.
 * @param {{sx: number, sy: number}[]} dots  screen-px positions
 * @param {number} x
 * @param {number} y
 * @param {number} maxPx
 * @returns {object|null}
 */
export function nearestDot(dots, x, y, maxPx) {
  let best = null, bestD = maxPx * maxPx;
  for (const d of dots) {
    const dd = (d.sx - x) ** 2 + (d.sy - y) ** 2;
    if (dd <= bestD) { best = d; bestD = dd; }
  }
  return best;
}

/**
 * @param {{svg: SVGSVGElement, onOpen: (drug: object) => void,
 *   onHide: (drug: object) => void}} o
 * @returns {{draw: (frame: object) => void, clear: () => void}}
 *   `draw` takes the frame drawPoints just drew: {dots: [{id, p, x, y, sx, sy}] (x / y
 *   in viewBox units, sx / sy in screen px), k (viewBox units per px), r, font, b}
 */
export function createFocus({ svg, onOpen, onHide }) {
  let frame = null;
  let hover = null, picked = null; // drug ids
  let pointerType = "mouse";
  const layer = svgEl("g", { class: "dm-focus" });

  const local = (ev) => {
    const rect = svg.getBoundingClientRect();
    return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
  };
  // The drug an event means: a placed name's own drug, else the nearest dot.
  const meant = (ev, maxPx) => {
    if (!frame) return null;
    const id = ev.target?.dataset?.drug;
    if (id) return frame.dots.find((d) => d.id === id) || null;
    const { x, y } = local(ev);
    return nearestDot(frame.dots, x, y, maxPx);
  };

  function paint() {
    layer.replaceChildren();
    for (const n of svg.querySelectorAll(".dm-label-under")) n.classList.remove("dm-label-under");
    if (!frame) return;
    const { k, r, font, b } = frame;
    const shown = [];
    for (const id of new Set([picked, hover])) {
      const d = id && frame.dots.find((x) => x.id === id);
      if (!d) continue;
      layer.appendChild(svgEl("circle", { cx: d.x, cy: d.y, r: (r + 3) * k, class: "dm-focus-ring", "stroke-width": 2 * k }));
      // Right of the dot, or left of it when the name would run off the frame.
      const left = d.x > b.x + b.w * 0.7;
      const txt = svgEl("text", {
        x: d.x + (left ? -1 : 1) * (r + 6) * k, y: d.y + font * 0.35 * k,
        "text-anchor": left ? "end" : "start", class: "dm-focus-label",
        "font-size": (font + FOCUS_FONT_GAIN) * k, "stroke-width": 3 * k,
      });
      txt.textContent = d.p.drug.name;
      layer.appendChild(txt);
      shown.push({ id, txt });
    }
    svg.appendChild(layer); // last child: drawn over every dot and name
    if (!shown.length) return;
    // getBBox needs the text in the document, hence after the append (viewBox units).
    const boxes = shown.map(({ txt }) => txt.getBBox());
    for (const n of svg.querySelectorAll("text.dm-label")) {
      const id = n.dataset.drug;
      if (!shown.some((s) => s.id === id) && !boxes.some((fb) => boxesOverlap(fb, n.getBBox()))) continue;
      n.classList.add("dm-label-under");
      // Its leader line (a floated name, layout.js) goes with it.
      for (const l of svg.querySelectorAll(`line.dm-name-leader[data-drug="${CSS.escape(id)}"]`)) l.classList.add("dm-label-under");
    }
  }

  svg.addEventListener("pointerdown", (ev) => { pointerType = ev.pointerType || "mouse"; });
  svg.addEventListener("pointermove", (ev) => {
    if (ev.pointerType !== "mouse" || ev.buttons) return;
    const d = meant(ev, NEAR_PX.mouse);
    svg.classList.toggle("dm-pointing", !!d);
    if ((d?.id || null) === hover) return;
    hover = d?.id || null;
    paint();
  });
  svg.addEventListener("pointerleave", () => {
    svg.classList.remove("dm-pointing");
    if (hover) { hover = null; paint(); }
  });
  // Bubble phase: gestures.js swallows (capture phase) the click that ends a pan.
  svg.addEventListener("click", (ev) => {
    const touch = pointerType !== "mouse";
    const d = meant(ev, touch ? NEAR_PX.touch : NEAR_PX.mouse);
    if (touch && (!d || d.id !== picked)) {
      picked = d?.id || null;
      paint();
      return;
    }
    if (d) onOpen(d.p.drug);
  });
  svg.addEventListener("contextmenu", (ev) => {
    const d = meant(ev, pointerType !== "mouse" ? NEAR_PX.touch : NEAR_PX.mouse);
    if (!d) return;
    ev.preventDefault();
    onHide(d.p.drug);
  });

  return {
    draw(next) { frame = next; paint(); },
    clear() { hover = picked = null; paint(); },
  };
}
