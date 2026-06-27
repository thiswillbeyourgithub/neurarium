# geometry_refinements/ - the brain-shape refinement runbook

This is a **self-contained runbook** for one long-running effort: replacing
neurarium's coarse procedural region shapes with a **self-made, Claude-authored
stylized atlas**, one structure at a time, refined against reference images via a
render-and-critique loop. A Claude session opened **inside this directory** should
be able to read this file (plus `STATUS.md`) and know the entire process from
start to finish, with no other context needed beyond the repo's root docs.

> [!IMPORTANT]
> **This effort is NOT started yet.** The infrastructure (Phase 0) does not exist
> until the first session builds it. Do **Phase 0 first**, then the per-structure
> grind. `STATUS.md` is the single source of truth for where things stand;
> always read it before doing anything and update it after every change.

## On opening a session here, do this

1. Read this whole file.
2. Read the repo-root `CLAUDE.md` (the data/viewer map) and `ARCHITECTURE.md`,
   specifically the geometry sections: the shape-file schema (`blob` / `curve` /
   `composite`), `public/js/shapes.js`, and the "Changing the data" workflow.
3. Read `STATUS.md`. Continue from the **first item that is not `done`**: if Phase 0
   is incomplete, build it; otherwise take the next `pending` structure.
4. Work **only** within this effort's files (see Scope). Make small commits.

## Why this exists

The current regions are independently-positioned noise-deformed ellipsoids
(`blob`), swept tubes (`curve`), and merged sub-shapes (`composite`). They
interpenetrate (no cross-region boolean/clipping except a same-group planar
jigsaw), and the cortex reads as a cluster of separate balls rather than one
continuous brain. We investigated real anatomical atlases: there is no permissive
drop-in model that covers neurarium's structure set (the monoamine source nuclei
raphe / locus coeruleus / VTA and the claustrum / olfactory bulb have no
CC-licensed source in any format), so a self-drawn atlas is both the cleanest
provenance and the only path that covers everything. Provenance stays `llm`
(Claude-authored, reference-guided): do not overclaim.

## The approach (decided)

- **Medium: signed-distance fields (SDF), meshed to geometry.** SDF is the only
  medium that does **smooth-union** (melting the lobes of a hemisphere into one
  continuous cortical surface with soft valleys, the fix for "bunch of balls"),
  and it also carves, makes thin shells, and renders organic forms naturally.
  Author each structure as an SDF spec: a set of primitives (ellipsoid, sphere,
  capsule/round-cone, swept tube along a polyline, box, half-space plane) combined
  by ops (union, `smoothUnion(k)`, intersect, subtract, `smoothSubtract(k)`) with
  optional domain-warp noise for the surface. Mesh the field (marching cubes /
  surface nets) to a `THREE.BufferGeometry`.
- **All JavaScript, in three.js.** No Python geometry stack. Use vendored
  three.js addons: `THREE.MarchingCubes` (built-in addon, metaball-style
  smooth-union, ideal for the cortex merge) and/or a small custom SDF evaluator +
  a marching-cubes/surface-nets pass for arbitrary primitives; `three-bvh-csg` for
  any exact boolean cut (e.g. the medial wall) where smooth-union is wrong.
- **Runtime vs build-time bake: to be settled by the Phase 0 perf check.** Prefer
  **runtime in-browser** meshing (keeps the project's no-build, vendored,
  param-driven identity, no committed mesh payload). If meshing at acceptable
  resolution is too slow at load (measure it), fall back to a **Node build-time
  bake** (same three.js, run headless once, export/commit meshes). Record the
  decision in `STATUS.md`.
- **Hybrid, always shippable.** Add the SDF path **alongside** the existing
  `blob` / `curve` / `composite` builders, never replacing them wholesale. Every
  commit must leave the viewer fully working: un-converted structures keep their
  current shapes; the brain always renders. This is what lets the effort run over
  days and lets unrelated fixes land anytime.

## Scope & isolation (do not confuse other sessions)

Other Claude sessions may run in this repo on the same git checkout. This subdir's
`CLAUDE.md` is auto-loaded **only** for sessions working in this subtree, so it
will not pollute their context, but the working tree is shared. Therefore:

- **Touch only**: this directory; the SDF mesher module(s) under `public/js/` (new
  files, plus the dispatch in `public/js/shapes.js`); per-structure shape specs in
  `tools/generate_data.py` and their emitted `public/data/shapes/<base>.json`; the
  render helper under `tools/`; vendored libs under `public/vendor/`.
- **Coordinate via `STATUS.md`.** Before editing a structure, mark it
  `drafting` there. Do not edit a structure another session has flagged in
  progress.
- **Do not run two committing sessions at the same instant.** If you (the human)
  want a quick fix elsewhere, pause this loop first. (For true parallelism, this
  effort can move to a dedicated git worktree/branch, but that needs explicit
  human approval; default is stay on `main`.)
- `geometry_refinements/refs/` and `geometry_refinements/renders/` are
  **gitignored** (reference images are third-party/copyrighted and are never
  committed; renders are scratch). Only original, self-authored geometry is
  committed.

## Phase 0: build the infrastructure (do this first, once)

Build the pipeline end to end and prove it on one structure. Done-criteria in
brackets. Update `STATUS.md` as each lands. Commit in small units.

1. **Vendor the libs.** Add `THREE.MarchingCubes` (three.js addon) wired into the
   `index.html` import map, and `three-bvh-csg` vendored same-origin under
   `public/vendor/`. Keep the no-CDN, vendored convention. [page still loads; libs
   importable]
2. **SDF mesher module** (`public/js/sdf.js` or similar): a generic SDF evaluator
   (the primitives + ops above) and a `meshField(...)` that marching-cubes the
   field to a `BufferGeometry` with normals. Self-contained, no new runtime deps
   beyond the vendored libs. [a unit sphere SDF meshes to a clean sphere]
3. **`type:"sdf"` in the shape pipeline.** Extend `buildGeometry()` in
   `public/js/shapes.js` to dispatch `type:"sdf"` to a `buildSdfGeometry()` that
   reads the spec and calls the mesher; keep `mirrorGeometryX` working for the `_L`
   member. Add a `shape=dict(type="sdf", ...)` authoring path in
   `tools/generate_data.py` that emits the spec to `public/data/shapes/<base>.json`
   like the other types. [a hand-written test sdf spec renders in the viewer
   alongside the untouched procedural regions]
4. **Render helper** (`tools/sculpt_shot.py` or a mode of `tools/shot.py`):
   renders one structure from canonical angles (front, right, top, iso) into a
   single contact-sheet PNG, with an **in-context** option (target solid, the rest
   of the brain ghosted at high transparency) so fit is judged continuously.
   Headless WebGL needs the sandbox disabled in this environment (the SwiftShader
   GL device is blocked under the sandbox); document that. [one command yields a
   labeled multi-angle contact sheet of a given structure id]
5. **Perf check + decision.** Mesh a representative load (including a hemisphere
   cortex smooth-union) at a usable resolution; time it. If runtime meshing is
   acceptable (rough bar: assembling the whole brain stays well under ~1 s added to
   load on a mid laptop, and is not painful on mobile), keep runtime. Else switch
   to a Node build-time bake (same three.js, export to `public/data/shapes/` and
   commit). **Write the decision + numbers into `STATUS.md`.**
6. **Prove the loop on the starter trio** (one each of: convex blob = `putamen`,
   curved tube = `hippocampus`, thin sheet = `claustrum`). If these converge to
   clearly-better-than-current shapes in a sane number of iterations, Phase 0 is
   done and the grind is green-lit. If they thrash, stop and report: the medium or
   the loop needs rethinking before scaling to all 29.

## Phase 1: the per-structure refine loop

For each `pending` structure in `STATUS.md` (suggested order: the starter trio
first, then easy-to-hard within each group; do the cortex lobes as a coherent
smooth-union set, not in isolation):

1. **Claim it.** Mark it `drafting` in `STATUS.md`.
2. **Gather references.** WebSearch the structure (e.g. "<name> coronal axial
   sagittal", "<name> 3d anatomy"), download a few clear images to
   `geometry_refinements/refs/<base>/` (gitignored), and `Read` them. Prefer
   orthogonal anatomical sections plus a 3D view. Note the shape's essence in one
   line (e.g. "claustrum = thin curved vertical sheet lateral to the putamen").
3. **Author / adjust the SDF spec** for the structure in `tools/generate_data.py`,
   in neurarium coordinates (x L-/R+, y D-/U+, z P-/A+; brain centered on origin;
   arbitrary units) and at the existing scale. Keep paired structures authored on
   the right and mirrored; midline ones authored once. Regenerate
   (`python tools/generate_data.py`).
4. **Render** an in-context multi-angle contact sheet via the render helper.
5. **Critique vs refs.** Compare silhouette, proportions, orientation, and fit
   with neighbours from each view. Write down the concrete deltas (too round, too
   large, wrong long-axis, interpenetrates X, sits too lateral, ...).
6. **Refine.** Adjust the spec; repeat 3-5 until it meets the **acceptance bar**:
   - silhouette matches the references from at least 3 orthogonal views + iso;
   - correct scale and position relative to neighbours, no gross interpenetration
     with adjacent structures (check in-context);
   - reads correctly in the assembled brain.
7. **Accept.** Mark it `done` in `STATUS.md` with a one-line note (and provenance
   `llm`). **One commit** (generator change + emitted shape file together; follow
   the root "Changing the data" workflow; run `tools/check_data.py`). Commit
   message: `Geometry: SDF-sculpt the <structure>`.
8. **Checkpoint the human.** Every few accepted structures, post a milestone
   contact sheet and pause for review. Read any correction notes the human leaves
   in `STATUS.md` and apply them. "Minimal intervention," not blind: the weak spot
   is judging 3D form from 2D renders, so human eyes at milestones are the
   safeguard.

## Phase 2: whole-brain fit (final pass)

Once enough structures are `done`: render the whole assembled brain, smooth-union
the hemisphere lobes into one coherent cortical surface, and fix scale / seams /
positions / any residual interpenetration. Re-tune the few procedural holdouts (if
any) to sit correctly inside the real shapes. Final commit(s).

## Conventions (in addition to the repo root's)

- **No em-dashes anywhere** (code, comments, commits, this dir's docs). Use commas,
  colons, parentheses.
- **Provenance is `llm`** for these shapes (Claude-authored, reference-guided);
  do not claim higher.
- **Never break the build.** Every commit leaves the viewer working (hybrid).
- **Many small commits**, one per accepted structure. Never `git add -A` (stages
  unrelated home-dir noise); add explicit paths.
- **Never** create/switch git branches or add to `.gitignore` without explicit
  human approval. Default is `main`.
- Keep `STATUS.md` current: it is what makes this resumable across days and
  context resets.

## Kicking it off (for the human)

Open a Claude session **in this directory** and either let it proceed from
`STATUS.md`, or drive the grind with a self-paced loop, e.g.:

> `/loop refine the next pending structure in STATUS.md per this dir's CLAUDE.md`

It will read this runbook + `STATUS.md`, do Phase 0 if needed, then process one
structure per iteration, committing each, and checkpoint at milestones.

## Future automation (optional, Phase 2+)

The per-structure loop is an optimization loop (render, critique, mutate). It can
later be automated/scaled with a reflective optimizer such as **GEPA**
(github.com/gepa-ai/gepa), which evolves textual artifacts (the SDF spec is text)
against an evaluation function. The prerequisite is an **automatic
render-vs-reference scorer** (a vision-model judge, or a silhouette-IoU /
Chamfer-distance metric against reference masks), which does not exist yet. Build
and validate the manual loop first; only reach for GEPA once a scorer exists and
the manual loop is proven to converge.

Built with the help of Claude Code.
