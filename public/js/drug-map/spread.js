// Nudging overlapping drug-map dots apart, in screen pixels and DOM-free (unit tested
// in tools/tests/drug_map.test.mjs). Only dots whose circles touch move, each by at
// most one dot diameter, so every distance larger than a dot (all a reader can see) and
// every direction survives; zooming in spreads the points and the nudge fades to zero.
// e.g. dots of radius 4 px whose centres sit 2 px apart end up ~9 px apart (3.5 px
// each way); the same pair at 4x zoom sits 8 px apart and does not move at all.

const ITERATIONS = 40;
// Clear space kept between two neighbouring dots' edges, px.
const GAP_PX = 1;

/**
 * Spread overlapping dots. Coincident dots (identical profiles) fan out on a small
 * golden-angle ring first, in id order.
 * @param {{id: string, x: number, y: number}[]} input  screen px, unique ids
 * @param {number} r  dot radius, px
 * @returns {Map<string, {x: number, y: number}>} id -> displayed position (only moved
 *   dots are listed)
 */
export function spreadPoints(input, r) {
  // Relaxed in id order, so the same dots land in the same places whatever order the
  // caller lists them in (a re-render must not reshuffle a cluster).
  const pts = [...input].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const min = 2 * r + GAP_PX, cap = 2 * r;
  const pos = pts.map((p) => ({ x: p.x, y: p.y }));
  // Coincident groups: same position to a tenth of a pixel.
  const groups = new Map();
  pts.forEach((p, i) => {
    const key = `${Math.round(p.x * 10)},${Math.round(p.y * 10)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(i);
  });
  for (const idx of groups.values()) {
    if (idx.length < 2) continue;
    idx.forEach((i, j) => {
      const a = j * 2.39996; // golden angle, rad
      pos[i].x += Math.cos(a) * r * 0.6;
      pos[i].y += Math.sin(a) * r * 0.6;
    });
  }
  // Only pairs that can ever touch (within reach of two capped moves) are relaxed.
  const reach = min + 2 * cap;
  const pairs = [];
  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      if (Math.abs(pts[i].x - pts[j].x) < reach && Math.abs(pts[i].y - pts[j].y) < reach) pairs.push([i, j]);
    }
  }
  for (let it = 0; it < ITERATIONS && pairs.length; it++) {
    let moved = false;
    for (const [i, j] of pairs) {
      const a = pos[i], b = pos[j];
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy);
      if (d >= min) continue;
      const push = (min - d) / 2;
      // Two exactly coincident dots (the golden ring missed) split along x.
      const ux = d ? dx / d : 1, uy = d ? dy / d : 0;
      a.x -= ux * push; a.y -= uy * push;
      b.x += ux * push; b.y += uy * push;
      moved = true;
    }
    // Clamp each dot back within `cap` of where it truly is.
    pos.forEach((q, i) => {
      const dx = q.x - pts[i].x, dy = q.y - pts[i].y, d = Math.hypot(dx, dy);
      if (d > cap) { q.x = pts[i].x + dx / d * cap; q.y = pts[i].y + dy / d * cap; }
    });
    if (!moved) break;
  }
  const out = new Map();
  pos.forEach((q, i) => {
    if (Math.hypot(q.x - pts[i].x, q.y - pts[i].y) > 0.05) out.set(pts[i].id, q);
  });
  return out;
}
