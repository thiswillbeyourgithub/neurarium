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
- **Runtime vs build-time bake:** UNDECIDED. Settle in Phase 0 step 5 (perf check)
  and record the numbers + verdict here.
- **Provenance of these shapes:** `llm` (Claude-authored, reference-guided).

## Phase 0: infrastructure (do first, once)

Not started. Build order (details + done-criteria in CLAUDE.md):

- pending - vendor libs (`THREE.MarchingCubes` addon + `three-bvh-csg`, same-origin)
- pending - SDF mesher module (`public/js/sdf.js`): evaluator + `meshField` -> BufferGeometry
- pending - `type:"sdf"` path in `public/js/shapes.js` + authoring path in `generate_data.py`
- pending - render helper (multi-angle in-context contact sheet of one structure)
- pending - perf check + runtime-vs-bake decision (record above)
- pending - prove the loop on the starter trio (putamen, hippocampus, claustrum)

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

- pending - putamen (paired)  [starter trio]
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
