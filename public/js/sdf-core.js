// SDF core: the signed-distance evaluator + bounds + the marching-cubes meshing
// pass, all reduced to PLAIN ARRAYS.
//
// ZERO three.js imports. The polygonizer is our own THREE-free `marchField`
// (js/marching-cubes.js), and the output is raw `{positions, indices}` typed
// arrays, not a `THREE.BufferGeometry`. That is what lets this exact code run in
// BOTH places with no three at all:
//   - the main thread, via js/sdf.js (which wraps the arrays into a BufferGeometry);
//   - the SDF Web Worker (js/sdf-worker.js), which has no import map (so it cannot
//     resolve a bare "three" specifier) and now pulls in no three whatsoever, so it
//     starts instantly instead of loading + parsing the 1.3MB three.js per worker.
// Noise is injected via `deps` (from the THREE-free js/noise.js), same as before.
//
// Coordinate convention is neurarium's: x left(-)/right(+), y down(-)/up(+),
// z posterior(-)/anterior(+); brain centered on the origin; arbitrary units.

import { marchField } from "./marching-cubes.js";

// ----------------------------------------------------------------------------
// SDF evaluation. Every primitive returns a signed distance: negative inside,
// zero on the surface, positive outside (distances are approximate for the
// non-sphere primitives, which is fine for meshing). All functions are written
// to allocate nothing: the field is sampled O(resolution^3) times, so per-call
// garbage would dominate. Vectors are passed as plain (x, y, z) scalars.
// ----------------------------------------------------------------------------

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const mix = (a, b, t) => a + (b - a) * t;

function sdSphere(x, y, z, c, r) {
  const dx = x - c[0], dy = y - c[1], dz = z - c[2];
  return Math.hypot(dx, dy, dz) - r;
}

// iq's cheap ellipsoid bound: not an exact SDF but stable and good enough to mesh.
function sdEllipsoid(x, y, z, c, r) {
  const px = (x - c[0]), py = (y - c[1]), pz = (z - c[2]);
  const k0 = Math.hypot(px / r[0], py / r[1], pz / r[2]);
  if (k0 === 0) return -Math.min(r[0], r[1], r[2]);
  const k1 = Math.hypot(px / (r[0] * r[0]), py / (r[1] * r[1]), pz / (r[2] * r[2]));
  return (k0 * (k0 - 1.0)) / k1;
}

// Rounded box: `half` is the half-extent before rounding, `round` the corner radius.
function sdBox(x, y, z, c, half, round) {
  const qx = Math.abs(x - c[0]) - half[0];
  const qy = Math.abs(y - c[1]) - half[1];
  const qz = Math.abs(z - c[2]) - half[2];
  const ox = Math.max(qx, 0), oy = Math.max(qy, 0), oz = Math.max(qz, 0);
  const outside = Math.hypot(ox, oy, oz);
  const inside = Math.min(Math.max(qx, qy, qz), 0);
  return outside + inside - (round || 0);
}

// Round cone / capsule: segment a->b with radius r1 at a, r2 at b (r2 defaults
// to r1, giving a plain capsule). Approximate (radius lerps along the segment
// parameter), which is smooth and plenty for organic tubes.
function sdRoundCone(x, y, z, a, b, r1, r2) {
  const bax = b[0] - a[0], bay = b[1] - a[1], baz = b[2] - a[2];
  const pax = x - a[0], pay = y - a[1], paz = z - a[2];
  const baba = bax * bax + bay * bay + baz * baz || 1e-9;
  const h = clamp((pax * bax + pay * bay + paz * baz) / baba, 0, 1);
  const cx = pax - bax * h, cy = pay - bay * h, cz = paz - baz * h;
  return Math.hypot(cx, cy, cz) - mix(r1, r2 == null ? r1 : r2, h);
}

// Half-space: the side of the plane `dot(p, n) <= offset` is "inside" (negative).
// `n` need not be unit; it is normalized here so `offset` is in world units.
function sdPlane(x, y, z, n, offset) {
  const len = Math.hypot(n[0], n[1], n[2]) || 1e-9;
  return (x * n[0] + y * n[1] + z * n[2]) / len - (offset || 0);
}

// Swept tube: min over consecutive round-cone segments of a polyline. Radius is
// either a constant `radius` or a per-station `profile` (head->tail), sampled at
// each point's index fraction.
function sdTube(x, y, z, node) {
  const pts = node.points;
  const n = pts.length;
  let r = node.radius;
  const prof = node.profile;
  const radiusAt = (i) => {
    if (!prof) return r;
    const t = n > 1 ? i / (n - 1) : 0;
    const f = t * (prof.length - 1);
    const lo = Math.floor(f), hi = Math.min(lo + 1, prof.length - 1);
    return mix(prof[lo], prof[hi], f - lo);
  };
  let d = Infinity;
  for (let i = 0; i < n - 1; i++) {
    const seg = sdRoundCone(x, y, z, pts[i], pts[i + 1], radiusAt(i), radiusAt(i + 1));
    if (seg < d) d = seg;
  }
  return d;
}

// Smooth-min / smooth-max (polynomial). k is the blend radius in world units.
function smin(a, b, k) {
  if (k <= 0) return Math.min(a, b);
  const h = clamp(0.5 + (0.5 * (b - a)) / k, 0, 1);
  return mix(b, a, h) - k * h * (1 - h);
}
function smax(a, b, k) {
  if (k <= 0) return Math.max(a, b);
  const h = clamp(0.5 - (0.5 * (b - a)) / k, 0, 1);
  return mix(b, a, h) + k * h * (1 - h);
}

// Evaluate an SDF node tree at (x, y, z). `deps.noise3d(x,y,z,seed)` is used for
// the `displace` op only; absent -> displacement is a no-op.
export function evalNode(node, x, y, z, deps) {
  // Primitive?
  switch (node.prim) {
    case "sphere":    return sdSphere(x, y, z, node.center, node.radius);
    case "ellipsoid": return sdEllipsoid(x, y, z, node.center, node.radii);
    case "box":       return sdBox(x, y, z, node.center, node.half, node.round);
    case "capsule":
    case "roundcone": return sdRoundCone(x, y, z, node.a, node.b, node.r1 ?? node.radius, node.r2);
    case "tube":      return sdTube(x, y, z, node);
    case "plane":     return sdPlane(x, y, z, node.normal, node.offset);
  }
  // Op.
  const kids = node.nodes || (node.node ? [node.node] : []);
  switch (node.op) {
    case "union": {
      let d = Infinity;
      for (const c of kids) d = Math.min(d, evalNode(c, x, y, z, deps));
      return d;
    }
    case "smoothUnion": {
      let d = Infinity;
      for (const c of kids) {
        const dc = evalNode(c, x, y, z, deps);
        d = d === Infinity ? dc : smin(d, dc, node.k || 0);
      }
      return d;
    }
    case "intersect": {
      let d = -Infinity;
      for (const c of kids) d = Math.max(d, evalNode(c, x, y, z, deps));
      return d;
    }
    case "smoothIntersect": {
      let d = -Infinity;
      for (const c of kids) {
        const dc = evalNode(c, x, y, z, deps);
        d = d === -Infinity ? dc : smax(d, dc, node.k || 0);
      }
      return d;
    }
    case "subtract": {
      // nodes[0] minus the union of the rest.
      let d = evalNode(kids[0], x, y, z, deps);
      const k = node.k || 0;
      for (let i = 1; i < kids.length; i++) {
        const cut = -evalNode(kids[i], x, y, z, deps);
        d = k > 0 ? smax(d, cut, k) : Math.max(d, cut);
      }
      return d;
    }
    case "displace": {
      // Surface relief: push the surface out/in by amp * noise(p).
      const base = evalNode(kids[0], x, y, z, deps);
      if (!node.amp) return base;
      const f = node.freq || 1;
      // `ridged`/`octaves` -> fractal (fBm / ridged-multifractal w/ domain warp,
      // the gyrus/sulcus + folia generator, shared with the blob path). Sampled in
      // ~unit space (coords / `unit`, default 1) plus an optional `origin` offset
      // so several structures can share ONE world-space fold field (continuous
      // folds across abutting lobes). Otherwise: cheap single-octave Perlin.
      let n;
      if (node.ridged || node.octaves) {
        if (!deps.fractalNoise) return base;
        const u = node.unit || 1;
        const o = node.origin || [0, 0, 0];
        n = deps.fractalNoise(
          (x + o[0]) / u, (y + o[1]) / u, (z + o[2]) / u,
          node.seed || 0, node.octaves || 4, !!node.ridged, f, node.aniso || [1, 1, 1],
        );
      } else {
        if (!deps.noise3d) return base;
        n = deps.noise3d(x * f, y * f, z * f, node.seed || 0);
      }
      return base - node.amp * n;
    }
  }
  throw new Error(`sdf: unknown node ${JSON.stringify(node).slice(0, 80)}`);
}

// ----------------------------------------------------------------------------
// Bounds. The marching grid must enclose the surface with a margin so the field
// is "outside" at the border (else the mesh is left open). We take the AABB of
// every *bounded* primitive (planes are skipped, they only cut) and pad it per
// axis. The box is left at its TIGHT (non-cubic) extent: the meshing pass keeps
// voxels near-isotropic by choosing a per-axis sample count from one target voxel
// size, so a thin/elongated structure no longer pays for a cube of empty cells.
// ----------------------------------------------------------------------------

function accumulateBounds(node, box) {
  const add = (cx, cy, cz, rx, ry, rz) => {
    box.min[0] = Math.min(box.min[0], cx - rx); box.max[0] = Math.max(box.max[0], cx + rx);
    box.min[1] = Math.min(box.min[1], cy - ry); box.max[1] = Math.max(box.max[1], cy + ry);
    box.min[2] = Math.min(box.min[2], cz - rz); box.max[2] = Math.max(box.max[2], cz + rz);
  };
  switch (node.prim) {
    case "sphere":    add(node.center[0], node.center[1], node.center[2], node.radius, node.radius, node.radius); return;
    case "ellipsoid": add(node.center[0], node.center[1], node.center[2], node.radii[0], node.radii[1], node.radii[2]); return;
    case "box": {
      const r = node.round || 0;
      add(node.center[0], node.center[1], node.center[2], node.half[0] + r, node.half[1] + r, node.half[2] + r);
      return;
    }
    case "capsule":
    case "roundcone": {
      const r = Math.max(node.r1 ?? node.radius, node.r2 ?? node.r1 ?? node.radius);
      add(node.a[0], node.a[1], node.a[2], r, r, r);
      add(node.b[0], node.b[1], node.b[2], r, r, r);
      return;
    }
    case "tube": {
      const prof = node.profile;
      const r0 = node.radius || 0;
      node.points.forEach((p, i) => {
        const r = prof ? prof[Math.min(i, prof.length - 1)] : r0;
        add(p[0], p[1], p[2], r, r, r);
      });
      return;
    }
    case "plane": return; // unbounded; only cuts
  }
  const kids = node.nodes || (node.node ? [node.node] : []);
  for (const c of kids) accumulateBounds(c, box);
}

export function fieldBounds(spec) {
  if (spec.bounds) {
    return { min: spec.bounds[0].slice(), max: spec.bounds[1].slice() };
  }
  const box = { min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity] };
  accumulateBounds(spec.root, box);
  if (!isFinite(box.min[0])) throw new Error("sdf: spec has no bounded primitive; give explicit `bounds`");
  const margin = spec.margin ?? 0.2;
  const min = [0, 0, 0], max = [0, 0, 0];
  for (let a = 0; a < 3; a++) {
    const c = (box.min[a] + box.max[a]) / 2;
    const half = (box.max[a] - box.min[a]) / 2;
    const pad = half * margin + 1e-3; // breathing room so the border is outside
    min[a] = c - half - pad;
    max[a] = c + half + pad;
  }
  return { min, max };
}

// ----------------------------------------------------------------------------
// Meshing. Samples the field on a regular grid, marches it (our own THREE-free
// `marchField`, which returns a world-space triangle soup), then welds coincident
// vertices into an indexed triangle list expressed as PLAIN typed arrays
// (`{positions, indices}`), so the caller (main thread or worker) decides how to
// wrap it. No three at all.
// ----------------------------------------------------------------------------

/**
 * Per-axis sample counts for a spec's grid. A target voxel size (from
 * `resolution` over the longest span) sets the density, then each axis gets as
 * many samples as it needs to hold that density: equant shapes stay ~cubic, but a
 * thin/elongated structure samples its short axes sparsely instead of padding
 * them out to a cube of mostly-empty cells (the dominant load-time cost). An
 * explicit `resolution` triple overrides this where the relief is anisotropic.
 *
 * Split out of `meshSdfToArrays` so the load-time budget (js/sdf-quality.js) can
 * PRICE a spec without meshing it; the two must not drift, hence one function.
 *
 * @param {object} spec
 * @returns {[number, number, number]}
 */
export function sdfGridDims(spec) {
  const { min, max } = fieldBounds(spec);
  const span = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
  if (Array.isArray(spec.resolution)) {
    const clampN = (n) => Math.max(8, Math.min(160, Math.round(n)));
    return [clampN(spec.resolution[0]), clampN(spec.resolution[1]), clampN(spec.resolution[2])];
  }
  const res = Math.max(16, Math.min(160, spec.resolution || 64));
  const voxel = Math.max(span[0], span[1], span[2]) / (res - 1);
  const dimOf = (s) => Math.max(8, Math.min(160, Math.round(s / voxel) + 1));
  return [dimOf(span[0]), dimOf(span[1]), dimOf(span[2])];
}

/**
 * What a spec costs to mesh, in grid samples (one SDF-tree walk each). The field
 * fill dominates, so this is a good relative price for ordering + budgeting.
 *
 * @param {object} spec
 * @returns {number}
 */
export function estimateSdfCost(spec) {
  const [Nx, Ny, Nz] = sdfGridDims(spec);
  return Nx * Ny * Nz;
}

/**
 * @param {object} spec  `{ root, resolution?, bounds?, margin? }`. `resolution` is
 *   the sample count along the LONGEST axis (the other axes scale down with their
 *   extent so voxels stay ~isotropic); pass an explicit `[Nx, Ny, Nz]` triple to
 *   pin per-axis sampling (e.g. a structure whose finest relief is on a short
 *   axis, like the cerebellum's folia).
 * @param {object} deps  `{ noise3d?, fractalNoise? }` (from js/noise.js).
 * @param {(frac:number)=>void} [onProgress]  called with 0..1 as the field fills,
 *   so a slow phone's loading bar keeps moving THROUGH one big structure instead
 *   of freezing between two whole-item ticks (a 112^3 grid is ~1.4M noise
 *   evaluations, several seconds on a weak CPU). Reported ~20 times per mesh, off
 *   the z-slab loop; called once more at 1 when the marcher + weld are done.
 * @returns {{positions: Float32Array, indices: Uint32Array}}
 */
export function meshSdfToArrays(spec, deps, onProgress) {
  const { min, max } = fieldBounds(spec);
  const span = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];

  const [Nx, Ny, Nz] = sdfGridDims(spec);

  // Sample the field on the Nx*Ny*Nz grid, inclusive of both bounds: worldOf(i,a)
  // = min[a] + (i / (Na - 1)) * span[a]. Store -sdf (positive inside) so the
  // surface is where the field crosses 0; `marchField` marks corners with
  // field < 0 as inside, matching three's table convention (so winding/normals
  // come out facing outward exactly as before).
  const field = new Float32Array(Nx * Ny * Nz);
  const sx = span[0] / (Nx - 1), sy = span[1] / (Ny - 1), sz = span[2] / (Nz - 1);
  const planeXY = Nx * Ny;
  // The field fill dominates the cost (one SDF-tree walk, noise included, per
  // sample), so it owns the reported 0..FILL_SHARE; the marcher + weld are the
  // remainder. Reported every `step` slabs to keep the message rate low.
  const FILL_SHARE = 0.9;
  const step = Math.max(1, Math.ceil(Nz / 20));
  for (let z = 0; z < Nz; z++) {
    if (onProgress && z % step === 0) onProgress((z / Nz) * FILL_SHARE);
    const wz = min[2] + z * sz;
    const zo = z * planeXY;
    for (let y = 0; y < Ny; y++) {
      const wy = min[1] + y * sy;
      const yo = zo + y * Nx;
      for (let x = 0; x < Nx; x++) {
        const wx = min[0] + x * sx;
        let d = -evalNode(spec.root, wx, wy, wz, deps);
        // A flat (axis-aligned) cut plane makes the sdf exactly 0 at grid points
        // that land on it; two adjacent zeros make a crossing edge interpolate
        // 0/0 -> a NaN vertex, which then poisons the geometry's bounding box and
        // blanks the viewer's auto-framing. Nudge exact zeros just off the
        // isosurface so every crossing edge has distinct endpoints.
        if (d === 0) d = 1e-5;
        field[yo + x] = d;
      }
    }
  }

  if (onProgress) onProgress(FILL_SHARE);
  const src = marchField(field, [Nx, Ny, Nz], min, span); // flat world-space triangle soup

  // Weld coincident vertices into an index so vertex normals come out smooth (and
  // stay smooth after the _L mirror, which re-runs computeVertexNormals). Shared
  // edges between neighbouring cells produce bit-identical vertices, so a small
  // rounding tolerance merges them cleanly. A triangle with any non-finite vertex
  // is dropped whole (a degenerate cell on a flat cut plane can emit a NaN, and a
  // single NaN position poisons the geometry's bounding box/sphere, blanking the
  // viewer's auto-framing); the stray face leaves at most a 1-triangle pinhole,
  // invisible on the double-sided material.
  const eps = Math.max(sx, sy, sz) / 8; // sub-voxel weld tolerance
  const inv = 1 / eps;
  const lookup = new Map();
  const positions = [];
  const indices = [];
  let dropped = 0;
  for (let t = 0; t + 8 < src.length; t += 9) {
    if (!Number.isFinite(src[t]) || !Number.isFinite(src[t + 1]) || !Number.isFinite(src[t + 2]) ||
        !Number.isFinite(src[t + 3]) || !Number.isFinite(src[t + 4]) || !Number.isFinite(src[t + 5]) ||
        !Number.isFinite(src[t + 6]) || !Number.isFinite(src[t + 7]) || !Number.isFinite(src[t + 8])) {
      dropped++;
      continue;
    }
    for (let k = 0; k < 9; k += 3) {
      const wx = src[t + k], wy = src[t + k + 1], wz = src[t + k + 2];
      const key = `${Math.round(wx * inv)},${Math.round(wy * inv)},${Math.round(wz * inv)}`;
      let idx = lookup.get(key);
      if (idx === undefined) {
        idx = positions.length / 3;
        lookup.set(key, idx);
        positions.push(wx, wy, wz);
      }
      indices.push(idx);
    }
  }
  if (dropped) console.warn(`sdf: dropped ${dropped} degenerate (non-finite) triangle(s)`);

  if (onProgress) onProgress(1);
  return { positions: new Float32Array(positions), indices: new Uint32Array(indices) };
}
