// Signed-distance-field (SDF) geometry path for the self-authored brain atlas,
// MAIN-THREAD entry point.
//
// A structure can be authored as an `sdf` shape spec: a tree of primitives
// (sphere, ellipsoid, box, capsule/round-cone, swept tube, half-space plane)
// combined by ops (union, intersect, subtract, and their smooth variants) with
// optional surface-noise displacement. `buildSdfGeometry()` samples that field
// onto a uniform grid, marches it to a triangle mesh with our own THREE-free
// marcher, then welds + re-normals the result so the mesh is smooth and watertight
// (and mirrors cleanly for the `_L` member).
//
// The heavy, three-free part (the evaluator + bounds + the marching pass that
// returns raw `{positions, indices}` arrays) lives in js/sdf-core.js +
// js/marching-cubes.js, so the SAME code runs inside the SDF Web Worker
// (js/sdf-worker.js) with no three at all. This module is the thin three-side
// wrapper: it wraps the returned arrays into a `THREE.BufferGeometry` with normals.
//
// Why SDF: it is the only medium that does *smooth-union* (melting the cortical
// lobes of a hemisphere into one continuous surface with soft valleys, instead of
// a bunch of separate balls), while also carving thin shells and reading as
// organic form. See geometry_refinements/CLAUDE.md for the whole effort.
//
// Coordinate convention is neurarium's: x left(-)/right(+), y down(-)/up(+),
// z posterior(-)/anterior(+); brain centered on the origin; arbitrary units.

import * as THREE from "three";
import { meshSdfToArrays, evalNode } from "./sdf-core.js";

/**
 * Mesh an SDF spec to a smooth, welded, indexed BufferGeometry in world units.
 *
 * @param {object} spec  `{ type:"sdf", root, resolution?, bounds?, margin? }`.
 * @param {object} deps  `{ noise3d?(x,y,z,seed), fractalNoise?(...) }` (injected,
 *   from js/noise.js).
 * @returns {THREE.BufferGeometry}
 */
export function buildSdfGeometry(spec, deps = {}) {
  const { positions, indices } = meshSdfToArrays(spec, deps);
  return geometryFromArrays(positions, indices);
}

/**
 * Wrap raw `{positions, indices}` (from `meshSdfToArrays`, on this thread or out
 * of the SDF worker) into an indexed BufferGeometry with smooth vertex normals.
 * Normals are computed here (not in the worker) because the `_L` mirror re-runs
 * `computeVertexNormals` anyway, and it is cheap relative to the field fill.
 *
 * @param {Float32Array|number[]} positions
 * @param {Uint32Array|number[]} indices
 * @returns {THREE.BufferGeometry}
 */
export function geometryFromArrays(positions, indices) {
  const geometry = new THREE.BufferGeometry();
  const pos = positions instanceof Float32Array ? positions : new Float32Array(positions);
  const idx = indices instanceof Uint32Array ? indices : new Uint32Array(indices);
  geometry.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geometry.setIndex(new THREE.BufferAttribute(idx, 1));
  geometry.computeVertexNormals();
  return geometry;
}

// Exposed for the unit smoke test (a unit sphere should mesh to ~radius 1).
export { evalNode };
