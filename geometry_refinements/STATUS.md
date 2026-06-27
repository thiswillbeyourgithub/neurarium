# geometry_refinements / STATUS

Single source of truth for the brain-shape refinement effort. Read this before
doing anything; update it after every change. The process is in this directory's
`CLAUDE.md`.

**Status values:** `pending` (not started) | `drafting` (claimed, in progress, do
not touch from another session) | `done` (accepted, committed) | `holdout`
(deliberately kept procedural for now).

## Decisions log

- **Geometry medium:** SDF (signed-distance fields) meshed to geometry, authored
  in JS / three.js. (See CLAUDE.md "The approach".)
- **Mesher:** a self-authored SDF evaluator (`public/js/sdf.js`) fills the
  vendored `THREE.MarchingCubes` scalar field (`field[i] = -sdf`, `isolation=0`),
  then welds + re-normals the output into a smooth, watertight, indexed geometry
  that mirrors cleanly for the `_L` member. Noise is injected from `shapes.js`
  (no duplicated Perlin, no import cycle). Primitives: sphere, ellipsoid, box,
  capsule/round-cone, swept tube, half-space plane. Ops: union, intersect,
  subtract, their smooth variants, and `displace` (surface noise).
- **`three-bvh-csg`:** NOT vendored (deferred). Booleans incl. the flat medial
  wall are done as half-space ops in the SDF field, so exact mesh-mesh CSG is not
  needed yet. Add it only if a structure genuinely needs an exact mesh cut.
- **Runtime vs build-time bake:** RUNTIME (in-browser), for now. Phase 0 perf
  (this machine, SwiftShader headless; meshing is pure-CPU JS so the GL backend
  does not affect it): single nucleus res 72 ~130ms / 17.8k tris; 5-lobe cortex
  smooth-union res 96 ~817ms / 27.7k tris, res 112 ~1.19s / 37.7k tris. Cost is
  the O(N^3) field fill. Per-structure runtime meshing (~100ms at res 64-72) is
  fine for the grind. The fully-converted 29-shape brain would add ~2s at load
  (over the ~1s bar), so the fallback if that proves painful at Phase 2 is to move
  meshing into a **Web Worker** (keeps the no-build identity; preferred over a
  committed bake). Resolution budget: nuclei 56-72, cortex 96-112.
- **Provenance of these shapes:** `llm` (Claude-authored, reference-guided).

## Phase 0: infrastructure (do first, once)

Build order (details + done-criteria in CLAUDE.md):

- done - vendor libs: `THREE.MarchingCubes` addon vendored + committed (import map
  already resolves the `three/addons/` prefix). `three-bvh-csg` deliberately
  deferred (see Decisions log).
- done - SDF mesher module `public/js/sdf.js`: evaluator (primitives + ops) +
  `buildSdfGeometry` -> welded, smooth, indexed BufferGeometry. Verified: an
  ellipsoid meshes to a clean smooth lens (putamen render).
- done - `type:"sdf"` dispatch in `public/js/shapes.js` (noise injected). Authoring
  path in `generate_data.py` needs no change: `_shape_record` passes any
  `shape=dict(...)` through verbatim, so `shape=dict(type="sdf", ...)` just works
  (an sdf entry is auto-excluded from the blob jigsaw, like curve/composite).
- done - render helper `tools/sculpt_shot.py`: multi-angle labeled contact sheet
  (front/right/top/iso) + kept individual frames; `--mode only` (isolated) or
  `--mode context` (solid over a ghosted brain, via the new viewer `solo=` param).
  Reuses `tools/shot.py`'s `dev_server`/`capture` (no duplication). Run with the
  sandbox disabled in this env (headless WebGL needs the SwiftShader GL device).
- done - perf check + decision: RUNTIME (numbers + verdict in Decisions log above).
- in progress - prove the loop on the starter trio (putamen, hippocampus, claustrum).

## Phase 1: per-structure grind

29 distinct shapes (paired structures = one right-side shape, mirrored to `_L`;
midline = one shape). Suggested order: the **starter trio** first (one of each
geometric class), then within each group. Cortex lobes are best done together as a
smooth-union set (see CLAUDE.md Phase 1 / Phase 2), not in isolation.

Starter trio (Phase 0 step 6): **putamen** (convex blob), **hippocampus** (curved
tube), **claustrum** (thin sheet).

### lobe (cortex; do as a coherent smooth-union set)

- pending - frontal (paired)
- pending - parietal (paired)
- pending - temporal (paired)
- pending - occipital (paired)
- pending - insula (paired)

### basal_ganglia

- done - putamen (paired)  [starter trio] - SDF: mediolaterally-flattened lens
  (ellipsoid) with a medial scoop (cradles the globus pallidus) + faint surface
  displace. Phase 0 proof structure. Provenance llm.
- pending - caudate (paired)
- pending - globus_pallidus (paired)
- pending - claustrum (paired)  [starter trio]
- pending - accumbens (paired)
- pending - thalamus (paired)
- pending - substantia_nigra (paired)
- pending - subthalamic_nucleus (paired)

### limbic

- pending - hippocampus (paired)  [starter trio]
- pending - amygdala (paired)
- pending - cingulate (paired)
- pending - fornix (paired)
- pending - septal_nuclei (paired)
- pending - olfactory_bulb (paired)

### diencephalon

- pending - hypothalamus (paired)
- pending - mammillary (paired)
- pending - pituitary (midline)

### brainstem_nuclei (monoamine source nuclei)

- pending - vta (paired)
- pending - locus_coeruleus (paired)
- pending - raphe (midline)

### hindbrain

- pending - midbrain (midline)
- pending - pons (midline)
- pending - medulla (midline)
- pending - cerebellum (midline)

## Phase 2: whole-brain fit

- pending - assemble all `done` shapes, smooth-union the cortex, fix scale / seams /
  positions / residual interpenetration.

## Milestone review log

(Human leaves correction notes here after each milestone contact-sheet review; the
loop reads and applies them.)

- (none yet)
