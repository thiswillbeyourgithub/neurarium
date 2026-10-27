// Where the drug map draws its names, in screen pixels and DOM-free (unit tested in
// tools/tests/drug_map.test.mjs): a name and dot size that follow how crowded the
// visible points are, and a greedy placement where no name covers a dot or another name.

/** Name size range in px: the crowded end still legible, the sparse end not shouting. */
export const FONT_PX = [11, 16];
const DOT_PX = [3.5, 6];
const clamp = (v, [lo, hi]) => Math.min(hi, Math.max(lo, v));

// Each point's distance (px) to its nearest neighbour, Infinity when alone.
function nearest(pts) {
  return pts.map((p, i) => {
    let best = Infinity;
    for (let j = 0; j < pts.length; j++) {
      if (j !== i) best = Math.min(best, Math.hypot(p.x - pts[j].x, p.y - pts[j].y));
    }
    return best;
  });
}

/**
 * Name font + dot radius (px) for points on screen, from their median nearest-neighbour
 * distance: e.g. 47 antipsychotics spread over a 1000 px plot (~40 px apart) get 16 px
 * names, the whole roster (~12 px apart) 11 px.
 * @param {{x: number, y: number}[]} pts  screen px
 * @returns {{font: number, r: number}}
 */
export function sizesFor(pts) {
  const d = nearest(pts).filter(Number.isFinite).sort((a, b) => a - b);
  const median = d.length ? d[d.length >> 1] : Infinity;
  return { font: clamp(median * 0.45, FONT_PX), r: clamp(median * 0.2, DOT_PX) };
}

/**
 * Greedy name placement: the sparsest points first (they cost the fewest names), each
 * trying right, left, above then below its dot, keeping the first slot that stays in
 * the frame and overlaps no dot and no name already placed. A name with no free slot is
 * not drawn; zooming in spreads the points and frees room for it.
 * @param {{id: string, x: number, y: number, text: string}[]} pts  screen px
 * @param {{font: number, r: number, width: number, height: number,
 *   measure: (text: string) => number}} o  `measure` = a name's width in px at `font`
 * @returns {Map<string, {x: number, y: number}>} id -> the name's left edge + baseline
 */
export function placeLabels(pts, { font, r, width, height, measure }) {
  const taken = pts.map((p) => ({ x: p.x - r, y: p.y - r, w: 2 * r, h: 2 * r }));
  const free = (a) => a.x >= 0 && a.y >= 0 && a.x + a.w <= width && a.y + a.h <= height
    && !taken.some((o) => a.x < o.x + o.w && o.x < a.x + a.w && a.y < o.y + o.h && o.y < a.y + a.h);
  const gap = r + 3;
  const nn = nearest(pts);
  const order = pts.map((p, i) => i).sort((a, b) => nn[b] - nn[a]);
  const out = new Map();
  for (const i of order) {
    const p = pts[i];
    // A text box is taller than its font size (ascent + descent).
    const w = measure(p.text), h = font * 1.3;
    const slot = [
      { x: p.x + gap, y: p.y - h / 2 },
      { x: p.x - gap - w, y: p.y - h / 2 },
      { x: p.x - w / 2, y: p.y - gap - h },
      { x: p.x - w / 2, y: p.y + gap },
    ].map((s) => ({ ...s, w, h })).find(free);
    if (!slot) continue;
    taken.push(slot);
    out.set(p.id, { x: slot.x, y: slot.y + font * 1.0 });
  }
  return out;
}
