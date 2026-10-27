// Where the drug map draws its names, in screen pixels and DOM-free (unit tested in
// tools/tests/drug_map.test.mjs): a name and dot size that follow how crowded the
// visible points are, and a placement where no name covers a dot, another name or
// another name's leader line.
//
// Placement (placeLabels), designed to name as many dots as possible:
// 1. Candidates: each dot offers its name at 8 positions around it (right, left, above,
//    below, then the four diagonals) on ring 0, touching the dot; when all of those are
//    taken, the same 8 positions on farther rings (RINGS, each one name height further
//    out), joined back to the dot by a thin leader line (which may cross other dots,
//    never a name or another leader). A name sits on the nearest
//    free position, so most names stay glued to their dot and only crowded ones float.
// 2. Greedy pass, sparsest dots first (they are cheap to name and anchor the layout).
// 3. Repair pass: a dot left unnamed looks at its ring-0 / ring-1 positions blocked by
//    exactly ONE placed name (nothing else); if that name can move to another free
//    position of its own, it moves and both get named. One level deep, so it stays fast.
// Collision checks go through a uniform grid (GRID_PX cells), so a full layout of the
// whole roster (~150 dots, ~200 candidates each) runs in a few ms, fast enough to redo
// on every pan / zoom frame.

/** Name size range in px: the crowded end still legible, the sparse end not shouting. */
export const FONT_PX = [11, 16];
const DOT_PX = [3.5, 6];
const clamp = (v, [lo, hi]) => Math.min(hi, Math.max(lo, v));

/** How many rings of positions a name may try: ring 0 touches its dot, the rest float. */
// 5 rings reach ~75 px from the dot: farther, a leader is harder to follow than a
// missing name (hover still names any dot).
export const RINGS = 5;
// Spatial grid cell for collision lookups, px (about one short name wide).
const GRID_PX = 32;
// A leader line is stored as a chain of LEADER_STEP_PX boxes, each as wide as the step
// so the chain has no gaps: a later name or leader cannot be drawn across it.
const LEADER_STEP_PX = 4;
// Ring-0 then diagonal order: the reading positions first (right, left), then above /
// below, then the corners. Unit offsets (ux, uy) of the box from the dot.
const DIRS = [[1, 0], [-1, 0], [0, -1], [0, 1], [1, -1], [-1, -1], [1, 1], [-1, 1]];

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

const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/**
 * A uniform grid of boxes, each tagged with an owner: `dot`, `label`, `leader`, plus the
 * point index it belongs to, so a box can be lifted out again (the repair pass).
 */
function createGrid() {
  const cells = new Map();
  // Integer cell keys (no string building in the hot path); offset so slightly negative
  // coordinates (a box just off the frame's edge) stay distinct.
  const key = (cx, cy) => (cx + 1024) * 4096 + cy + 1024;
  const keys = (b) => {
    const out = [];
    for (let cx = Math.floor(b.x / GRID_PX); cx <= Math.floor((b.x + b.w) / GRID_PX); cx++) {
      for (let cy = Math.floor(b.y / GRID_PX); cy <= Math.floor((b.y + b.h) / GRID_PX); cy++) out.push(key(cx, cy));
    }
    return out;
  };
  return {
    add(box) {
      for (const k of keys(box)) {
        if (!cells.has(k)) cells.set(k, []);
        cells.get(k).push(box);
      }
    },
    remove(box) {
      for (const k of keys(box)) {
        const c = cells.get(k);
        const i = c ? c.indexOf(box) : -1;
        if (i >= 0) c.splice(i, 1);
      }
    },
    /** Whether any box overlapping (x, y, w, h) passes `ok` (early exit, no allocation). */
    any(x, y, w, h, ok) {
      for (let cx = Math.floor(x / GRID_PX); cx <= Math.floor((x + w) / GRID_PX); cx++) {
        for (let cy = Math.floor(y / GRID_PX); cy <= Math.floor((y + h) / GRID_PX); cy++) {
          for (const o of cells.get(key(cx, cy)) || []) {
            if (x < o.x + o.w && o.x < x + w && y < o.y + o.h && o.y < y + h && ok(o)) return true;
          }
        }
      }
      return false;
    },
    /** Every box overlapping `b`, each once. */
    hits(b) {
      const seen = new Set();
      for (const k of keys(b)) {
        for (const o of cells.get(k) || []) if (!seen.has(o) && overlap(b, o)) seen.add(o);
      }
      return [...seen];
    },
  };
}

/**
 * Name placement (see the file header): 8 positions on RINGS rings per dot, greedy
 * sparsest-first, then a one-move repair pass. A name never leaves the frame, never
 * covers a dot, a name or a leader; a dot with no free position stays unnamed (zooming
 * in spreads the points and frees room).
 * @param {{id: string, x: number, y: number, text: string}[]} pts  screen px
 * @param {{font: number, r: number, width: number, height: number,
 *   measure: (text: string) => number, rings?: number,
 *   avoid?: {x: number, y: number, w: number, h: number}[], repair?: boolean}} o
 *   `measure` = a name's width in px at `font`; `avoid` = screen boxes no name or leader
 *   may cover (the watermark); `repair` = run the repair pass (default; off only in tests)
 * @returns {Map<string, {x: number, y: number, leader?: {x1: number, y1: number, x2: number, y2: number}}>}
 *   id -> the name's left edge + baseline, plus its leader line (dot edge -> box) when it floats
 */
export function placeLabels(pts, { font, r, width, height, measure, rings = RINGS, avoid = [], repair = true }) {
  const grid = createGrid();
  for (const a of avoid) grid.add({ ...a, kind: "avoid", i: -1 });
  for (let i = 0; i < pts.length; i++) {
    grid.add({ x: pts[i].x - r, y: pts[i].y - r, w: 2 * r, h: 2 * r, kind: "dot", i });
  }
  // A text box is taller than its font size (ascent + descent).
  const h = font * 1.3;
  const gap = r + 3;
  const step = h * 0.9;

  // Every candidate of point i, nearest ring first: {x, y, w, h, ring, leader?}.
  function candidates(i) {
    const p = pts[i], w = measure(p.text);
    const out = [];
    for (let ring = 0; ring < rings; ring++) {
      const d = gap + ring * step;
      for (const [ux, uy] of DIRS) {
        // Box edge at distance d from the dot along (ux, uy); diagonals at d / sqrt 2 each way.
        const k = ux && uy ? Math.SQRT1_2 : 1;
        const x = ux > 0 ? p.x + d * k : ux < 0 ? p.x - d * k - w : p.x - w / 2;
        const y = uy > 0 ? p.y + d * k : uy < 0 ? p.y - d * k - h : p.y - h / 2;
        const box = { x, y, w, h, ring };
        if (ring) {
          // Leader from the dot's edge to the box's nearest point.
          const nx = clamp(p.x, [x, x + w]), ny = clamp(p.y, [y, y + h]);
          const len = Math.hypot(nx - p.x, ny - p.y);
          box.leader = { x1: p.x + (nx - p.x) / len * (r + 1), y1: p.y + (ny - p.y) / len * (r + 1), x2: nx, y2: ny };
        }
        out.push(box);
      }
    }
    return out;
  }
  const inFrame = (b) => b.x >= 0 && b.y >= 0 && b.x + b.w <= width && b.y + b.h <= height;
  // The small boxes a leader occupies (and must find free), its own dot excluded.
  const leaderBoxes = (lead, i) => {
    const len = Math.hypot(lead.x2 - lead.x1, lead.y2 - lead.y1);
    const n = Math.max(1, Math.ceil(len / LEADER_STEP_PX));
    const out = [];
    for (let s = 0; s <= n; s++) {
      const x = lead.x1 + (lead.x2 - lead.x1) * s / n, y = lead.y1 + (lead.y2 - lead.y1) * s / n;
      out.push({ x: x - LEADER_STEP_PX / 2, y: y - LEADER_STEP_PX / 2, w: LEADER_STEP_PX, h: LEADER_STEP_PX, kind: "leader", i });
    }
    return out;
  };
  // What blocks a candidate of point i: the boxes it hits, and the names / leaders its
  // leader would cross. A leader may run over other dots: inside a dense cluster every
  // way out crosses one, and a faint line over a dot reads fine, a name over it does not.
  const blockers = (c, i) => {
    const hit = new Set(grid.hits(c));
    if (c.leader) {
      for (const lb of leaderBoxes(c.leader, i)) {
        for (const o of grid.hits(lb)) if (o.kind !== "dot") hit.add(o);
      }
    }
    return [...hit];
  };
  // The fast yes / no form of `blockers` (the greedy pass asks it ~40 times per dot):
  // the name box first, then its leader sampled every LEADER_STEP_PX, stopping at the first hit.
  const anything = () => true, notDot = (o) => o.kind !== "dot";
  const fixed = (o) => o.kind === "dot" || o.kind === "avoid";
  const free = (c) => {
    if (grid.any(c.x, c.y, c.w, c.h, anything)) return false;
    const L = c.leader;
    if (!L) return true;
    const n = Math.max(1, Math.ceil(Math.hypot(L.x2 - L.x1, L.y2 - L.y1) / LEADER_STEP_PX));
    for (let s = 0; s <= n; s++) {
      const x = L.x1 + (L.x2 - L.x1) * s / n, y = L.y1 + (L.y2 - L.y1) * s / n;
      if (grid.any(x - LEADER_STEP_PX / 2, y - LEADER_STEP_PX / 2, LEADER_STEP_PX, LEADER_STEP_PX, notDot)) return false;
    }
    return true;
  };
  const placed = new Map(); // i -> {box, leader boxes}
  const commit = (i, c) => {
    const parts = [{ ...c, kind: "label", i }, ...(c.leader ? leaderBoxes(c.leader, i) : [])];
    for (const b of parts) grid.add(b);
    placed.set(i, { c, parts });
  };
  const lift = (i) => {
    for (const b of placed.get(i).parts) grid.remove(b);
    const was = placed.get(i).c;
    placed.delete(i);
    return was;
  };
  const cands = pts.map((_, i) => candidates(i).filter(inFrame));

  // Greedy, sparsest first.
  const nn = nearest(pts);
  const order = pts.map((_, i) => i).sort((a, b) => nn[b] - nn[a]);
  for (const i of order) {
    const c = cands[i].find(free);
    if (c) commit(i, c);
  }

  // Repair: move one blocking name aside to name a missing dot.
  for (const i of repair ? order : []) {
    if (placed.has(i)) continue;
    for (const c of cands[i]) {
      if (c.ring > 1) break;
      // A dot or the watermark under the box can never move: skip before the full census.
      if (grid.any(c.x, c.y, c.w, c.h, fixed)) continue;
      const bl = blockers(c, i);
      const owners = new Set(bl.map((o) => o.i));
      if (owners.size !== 1 || bl.some((o) => o.kind === "dot" || o.kind === "avoid")) continue;
      const j = bl[0].i;
      const was = lift(j);
      // Reserve the freed spot for i while j looks for a new home.
      commit(i, c);
      const alt = cands[j].find((x) => x !== was && free(x));
      if (alt) { commit(j, alt); break; }
      lift(i);
      commit(j, was);
    }
  }

  const out = new Map();
  for (const [i, { c }] of placed) {
    out.set(pts[i].id, { x: c.x, y: c.y + font * 1.0, ...(c.leader ? { leader: c.leader } : {}) });
  }
  return out;
}
