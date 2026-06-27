// Signed-distance-field (SDF) geometry path for the self-authored brain atlas.
//
// A structure can be authored as an `sdf` shape spec: a tree of primitives
// (sphere, ellipsoid, box, capsule/round-cone, swept tube, half-space plane)
// combined by ops (union, intersect, subtract, and their smooth variants) with
// optional surface-noise displacement. `buildSdfGeometry()` samples that field
// onto a uniform grid, marches it to a triangle mesh with the vendored
// `THREE.MarchingCubes` addon, then welds + re-normals the result so the mesh is
// smooth and watertight (and mirrors cleanly for the `_L` member).
//
// Why SDF: it is the only medium that does *smooth-union* (melting the cortical
// lobes of a hemisphere into one continuous surface with soft valleys, instead of
// a bunch of separate balls), while also carving thin shells and reading as
// organic form. See geometry_refinements/CLAUDE.md for the whole effort.
//
// Coordinate convention is neurarium's: x left(-)/right(+), y down(-)/up(+),
// z posterior(-)/anterior(+); brain centered on the origin; arbitrary units.
//
// Noise is *injected* (the `deps.noise3d` argument) rather than imported, so this
// module does not duplicate shapes.js's Perlin and the two modules have no import
// cycle: shapes.js imports this, this imports nothing from shapes.js.

import * as THREE from "three";
import { MarchingCubes } from "three/addons/objects/MarchingCubes.js";

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
function evalNode(node, x, y, z, deps) {
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
      // Surface bumps: push the surface out/in by amp * noise(p * freq).
      const base = evalNode(kids[0], x, y, z, deps);
      if (!deps.noise3d || !node.amp) return base;
      const f = node.freq || 1;
      const n = deps.noise3d(x * f, y * f, z * f, node.seed || 0);
      return base - node.amp * n;
    }
  }
  throw new Error(`sdf: unknown node ${JSON.stringify(node).slice(0, 80)}`);
}

// ----------------------------------------------------------------------------
// Bounds. The marching grid must enclose the surface with a margin so the field
// is "outside" at the border (else the mesh is left open). We take the AABB of
// every *bounded* primitive (planes are skipped, they only cut), make it a cube
// (so grid voxels stay near-isotropic) and pad it.
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

function cubeBounds(spec) {
  if (spec.bounds) {
    return { min: spec.bounds[0].slice(), max: spec.bounds[1].slice() };
  }
  const box = { min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity] };
  accumulateBounds(spec.root, box);
  if (!isFinite(box.min[0])) throw new Error("sdf: spec has no bounded primitive; give explicit `bounds`");
  const cx = (box.min[0] + box.max[0]) / 2;
  const cy = (box.min[1] + box.max[1]) / 2;
  const cz = (box.min[2] + box.max[2]) / 2;
  const half = Math.max(
    box.max[0] - box.min[0], box.max[1] - box.min[1], box.max[2] - box.min[2],
  ) / 2;
  const pad = (half * (spec.margin || 0.2)) + 1e-3; // breathing room so the border is outside
  const h = half + pad;
  return { min: [cx - h, cy - h, cz - h], max: [cx + h, cy + h, cz + h] };
}

// ----------------------------------------------------------------------------
// Meshing.
// ----------------------------------------------------------------------------

const _dummyMat = new THREE.MeshBasicMaterial();

/**
 * Mesh an SDF spec to a smooth, welded, indexed BufferGeometry in world units.
 *
 * @param {object} spec  `{ type:"sdf", root, resolution?, bounds?, margin? }`.
 * @param {object} deps  `{ noise3d?(x,y,z,seed) }` (injected, see file header).
 * @returns {THREE.BufferGeometry}
 */
export function buildSdfGeometry(spec, deps = {}) {
  const N = Math.max(16, Math.min(160, spec.resolution || 64));
  const { min, max } = cubeBounds(spec);
  const span = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];

  // Generously sized triangle buffer (the addon clips + warns if it overflows).
  const maxPoly = Math.max(20000, N * N * 8);
  const mc = new MarchingCubes(N, _dummyMat, false, false, maxPoly);
  mc.isolation = 0; // surface at sdf == 0
  const field = mc.field;

  // Fill the field: high (positive) inside so it matches the addon's metaball
  // convention (so the gradient-based normals and triangle winding come out
  // facing outward). worldOf(i) = min + (i / N) * span, the affine inverse of the
  // addon's vertex output fx = (i - N/2) / (N/2).
  for (let z = 0; z < N; z++) {
    const wz = min[2] + (z / N) * span[2];
    const zo = z * N * N;
    for (let y = 0; y < N; y++) {
      const wy = min[1] + (y / N) * span[1];
      const yo = zo + y * N;
      for (let x = 0; x < N; x++) {
        const wx = min[0] + (x / N) * span[0];
        field[yo + x] = -evalNode(spec.root, wx, wy, wz, deps);
      }
    }
  }

  mc.update(); // polygonize into mc.positionArray, mc.count = vertex count
  const vcount = mc.count;
  const src = mc.positionArray;
  if (vcount >= maxPoly * 3) {
    console.warn(`sdf: marching buffer full at resolution ${N}; raise maxPoly or lower resolution`);
  }

  // Map the addon's [-1,1] output back to world (world = center + pos*halfspan),
  // welding coincident vertices into an index so vertex normals come out smooth
  // (and stay smooth after the _L mirror, which re-runs computeVertexNormals).
  const cx = (min[0] + max[0]) / 2, cy = (min[1] + max[1]) / 2, cz = (min[2] + max[2]) / 2;
  const hx = span[0] / 2, hy = span[1] / 2, hz = span[2] / 2;
  const eps = Math.max(hx, hy, hz) / (N * 8); // sub-voxel weld tolerance
  const inv = 1 / eps;

  const lookup = new Map();
  const positions = [];
  const indices = new Array(vcount);
  for (let v = 0; v < vcount; v++) {
    const wx = cx + src[v * 3] * hx;
    const wy = cy + src[v * 3 + 1] * hy;
    const wz = cz + src[v * 3 + 2] * hz;
    const key = `${Math.round(wx * inv)},${Math.round(wy * inv)},${Math.round(wz * inv)}`;
    let idx = lookup.get(key);
    if (idx === undefined) {
      idx = positions.length / 3;
      lookup.set(key, idx);
      positions.push(wx, wy, wz);
    }
    indices[v] = idx;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

// Exposed for the unit smoke test (a unit sphere should mesh to ~radius 1).
export { evalNode };
