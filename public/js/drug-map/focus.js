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
// A drug whose name layout.js already placed keeps that name, only boldened in place
// (`dm-label-focus`): drawing a second copy elsewhere made the eye jump. A nameless drug
// gets a focus name, drawn larger than the placed names, and while it shows, the placed
// names it would collide with are hidden (`dm-label-under`), so it reads cleanly inside
// a crowded cluster.
// "Near" is measured from the pointer, so a tap between two dots picks the closer one,
// and a tiny dot needs no pixel-exact aim. The mouse hover is sticky (`stickyNearest`):
// between two close dots a plain nearest-dot test flips at the exact midpoint, so a
// hand's jitter there made the focus flicker; the hovered drug now holds until another
// dot is HYST_PX closer, and up to NEAR_PX + HYST_PX away. The focus name itself is
// hit-testable and names its drug: it hides the placed name under it, and were it
// transparent to the pointer, the pointer would then fall through to nothing, drop the
// hover, bring the placed name back, and loop. A click on a placed name means its drug even
// when that name runs farther than NEAR_PX from the dot.
//
// `nearestDot` / `stickyNearest` are DOM-free (node tests); `createFocus` wires the events and draws.

import { svgEl } from "./dom.js";

/** How far (screen px) from a dot the pointer still means it. */
export const NEAR_PX = { mouse: 24, touch: 32 };

/** Screen px another dot must be closer by to take the mouse hover over (see top). */
export const HYST_PX = 8;

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
 * The nearest dot with hysteresis towards `currentId`: the current dot stays meant while
 * within `maxPx + hystPx`, unless another is more than `hystPx` closer. E.g. dots 10 px
 * apart at x = 0 (current) and x = 10: the pointer at x = 6 keeps the first (6 vs 4, not
 * 8 closer); at x = 10 the second wins (10 vs 0).
 * @param {{id: string, sx: number, sy: number}[]} dots
 * @param {number} x
 * @param {number} y
 * @param {string|null} currentId
 * @param {number} maxPx
 * @param {number} [hystPx]
 * @returns {object|null}
 */
export function stickyNearest(dots, x, y, currentId, maxPx, hystPx = HYST_PX) {
  const best = nearestDot(dots, x, y, maxPx);
  const cur = currentId && dots.find((d) => d.id === currentId);
  if (!cur) return best;
  const dCur = Math.hypot(cur.sx - x, cur.sy - y);
  if (dCur > maxPx + hystPx) return best;
  return best && Math.hypot(best.sx - x, best.sy - y) < dCur - hystPx ? best : cur;
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
  // `sticky` (the mouse hover) holds the hovered drug against near ties (stickyNearest).
  const meant = (ev, maxPx, sticky = false) => {
    if (!frame) return null;
    const id = ev.target?.dataset?.drug;
    if (id) return frame.dots.find((d) => d.id === id) || null;
    const { x, y } = local(ev);
    return sticky ? stickyNearest(frame.dots, x, y, hover, maxPx) : nearestDot(frame.dots, x, y, maxPx);
  };

  function paint() {
    layer.replaceChildren();
    for (const n of svg.querySelectorAll(".dm-label-under, .dm-label-focus")) n.classList.remove("dm-label-under", "dm-label-focus");
    if (!frame) return;
    const { k, r, font, b } = frame;
    const shown = [];
    for (const id of new Set([picked, hover])) {
      const d = id && frame.dots.find((x) => x.id === id);
      if (!d) continue;
      layer.appendChild(svgEl("circle", { cx: d.x, cy: d.y, r: (r + 3) * k, class: "dm-focus-ring", "stroke-width": 2 * k }));
      const placed = svg.querySelector(`text.dm-label[data-drug="${CSS.escape(id)}"]`);
      if (placed) { placed.classList.add("dm-label-focus"); continue; }
      // Right of the dot, or left of it when the name would run off the frame.
      const left = d.x > b.x + b.w * 0.7;
      const txt = svgEl("text", {
        x: d.x + (left ? -1 : 1) * (r + 6) * k, y: d.y + font * 0.35 * k,
        "text-anchor": left ? "end" : "start", class: "dm-focus-label",
        "font-size": (font + FOCUS_FONT_GAIN) * k, "stroke-width": 3 * k, "data-drug": id,
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
      // A boldened placed name stays, whatever a focus name overlaps.
      if (n.classList.contains("dm-label-focus") || !boxes.some((fb) => boxesOverlap(fb, n.getBBox()))) continue;
      n.classList.add("dm-label-under");
      // Its leader line (a floated name, layout.js) goes with it.
      for (const l of svg.querySelectorAll(`line.dm-name-leader[data-drug="${CSS.escape(id)}"]`)) l.classList.add("dm-label-under");
    }
  }

  svg.addEventListener("pointerdown", (ev) => { pointerType = ev.pointerType || "mouse"; });
  svg.addEventListener("pointermove", (ev) => {
    if (ev.pointerType !== "mouse" || ev.buttons) return;
    const d = meant(ev, NEAR_PX.mouse, true);
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
