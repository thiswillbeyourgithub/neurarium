// Nudging overlapping drug-map dots apart, in screen pixels and DOM-free (unit tested
// in tools/tests/drug_map.test.mjs). Only dots whose circles touch move, each by at
// most one dot diameter, so every distance larger than a dot (all a reader can see) and
// every direction survives; zooming in spreads the points and the nudge fades to zero.
// e.g. dots of radius 4 px whose centres sit 2 px apart end up ~9 px apart (3.5 px
// each way); the same pair at 4x zoom sits 8 px apart and does not move at all.
// Exactly coincident dots are the exception: they unfold into a spiral at any zoom.

const ITERATIONS = 40;
// Clear space kept between two neighbouring dots' edges, px.
const GAP_PX = 1;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5)); // rad, ~137.5 degrees
// Sunflower radius step, in dot spacings: j-th dot at SPIRAL_STEP * spacing * sqrt(j).
// 0.6 leaves neighbours about one spacing apart; the relaxation evens out the rest.
const SPIRAL_STEP = 0.6;

/**
 * Spread overlapping dots. Coincident dots (identical profiles) first unfold into a
 * sunflower spiral, in id order.
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
  // Where each dot is clamped around: its true place, except for coincident dots.
  const home = pts.map((p) => ({ x: p.x, y: p.y }));
  // Coincident groups (same position to a tenth of a pixel: identical profiles, e.g.
  // the benzodiazepines, which all bind only the GABA-A benzodiazepine site) carry no
  // direction or distance to preserve between them, so they unfold into a sunflower
  // spiral spaced a dot apart, however many there are; the cap then applies around
  // each one's spiral place.
  const groups = new Map();
  pts.forEach((p, i) => {
    const key = `${Math.round(p.x * 10)},${Math.round(p.y * 10)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(i);
  });
  for (const idx of groups.values()) {
    if (idx.length < 2) continue;
    idx.forEach((i, j) => {
      const a = j * GOLDEN_ANGLE, d = SPIRAL_STEP * min * Math.sqrt(j + 0.5);
      home[i] = { x: pts[i].x + Math.cos(a) * d, y: pts[i].y + Math.sin(a) * d };
      pos[i] = { ...home[i] };
    });
  }
  // Only pairs that can ever touch (within reach of two capped moves) are relaxed.
  const reach = min + 2 * cap;
  const pairs = [];
  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      if (Math.abs(home[i].x - home[j].x) < reach && Math.abs(home[i].y - home[j].y) < reach) pairs.push([i, j]);
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
    // Clamp each dot back within `cap` of its home.
    pos.forEach((q, i) => {
      const dx = q.x - home[i].x, dy = q.y - home[i].y, d = Math.hypot(dx, dy);
      if (d > cap) { q.x = home[i].x + dx / d * cap; q.y = home[i].y + dy / d * cap; }
    });
    if (!moved) break;
  }
  const out = new Map();
  pos.forEach((q, i) => {
    if (Math.hypot(q.x - pts[i].x, q.y - pts[i].y) > 0.05) out.set(pts[i].id, q);
  });
  return out;
}
