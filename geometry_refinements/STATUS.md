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
- **Grind order (agreed w/ human):** cortex hemisphere first (it's the worst-looking
  AND the make-or-break test of smooth-union/abut), then rest of basal_ganglia,
  limbic, diencephalon, brainstem_nuclei, hindbrain (cerebellum last).
- **Cortex approach (agreed):** each lobe stays its OWN independent SDF "shaped to
  abut" its neighbours at explode 0 (keeps the per-structure model: each lobe still
  explodes/highlights alone). Not a single merged hemisphere mesh. Continuity comes
  from: (a) GEOMETRIC gyral folds via the new ridged-fractal `displace` (real
  sulci/gyri, so inter-lobe seams read as just another sulcus, not a ball-ball
  crease); (b) a flat medial wall via a half-space `plane` subtract applied AFTER
  the folds; (c) for adjoining lobes, share ONE world-space fold field by setting
  each lobe's `displace.origin = pos` so the gyri line up across the seam. The
  `displace` op now takes `ridged`/`octaves`/`unit`/`origin`/`aniso` (reuses
  shapes.js `fractalNoise` via the dep; backward-compatible with old Perlin specs).
- **Imaging:** `sculpt_shot.py` emits all three sheets per structure
  (`contact.png` renders-only, `refs.png` references-only, `combined.png` both),
  kept for the human's double-check; the loop critiques mainly off `combined.png`.
- **Tiny lone structures render blank:** `shot.py`'s camera auto-fit (`only=<id>`)
  produces a BLANK frame for a very small isolated structure (e.g. septal_nuclei,
  max dim ~0.7). The mesh is fine; only the framing fails. Render such tiny nuclei
  alongside a larger anchor neighbour (e.g. `only=<tiny>,thalamus_R`) to judge them.
- **Reference images + Syncthing:** this checkout is inside a Syncthing folder that
  deletes local-only (gitignored) files like `refs/` between commands. So cache
  reference images in the **session scratchpad** and point `sculpt_shot.py
  --refs-dir <scratchpad>/refs` at them (re-fetch per session; refs are never
  committed anyway). Renders are regenerated on demand, so their deletion is moot.

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
- done - prove the loop on the starter trio (putamen, hippocampus, claustrum): all
  three converged in a sane number of iterations (putamen 1 refine, hippocampus 0,
  claustrum 1) to clearly-better-than-procedural shapes. **Phase 0 complete; the
  grind is green-lit.** The refine loop (author SDF -> regenerate -> sculpt_shot
  combined render+reference sheet -> critique -> refine) works end to end.

## Phase 1: per-structure grind

29 distinct shapes (paired structures = one right-side shape, mirrored to `_L`;
midline = one shape). Suggested order: the **starter trio** first (one of each
geometric class), then within each group. Cortex lobes are best done together as a
smooth-union set (see CLAUDE.md Phase 1 / Phase 2), not in isolation.

Starter trio (Phase 0 step 6): **putamen** (convex blob), **hippocampus** (curved
tube), **claustrum** (thin sheet).

### lobe (cortex; converted as a coordinated set, reviewed on a whole-hemisphere render)

The four main lobes are sectors of ONE shared cortical-mantle ellipsoid
(`_cortex_lobe` in generate_data.py), carved by shared cut planes + a flat medial
wall, so at explode 0 they reassemble into a single continuous hemisphere instead
of a cluster of balls. The fissures are now OBLIQUE (tilted), so the seams read
like the real central / Sylvian fissures, not axis-aligned slabs:
  - central: through (1.15,0.55,0.4), tilted forward going down (frontal | parietal)
  - Sylvian: through (1.15,-0.1,0.2), rising posteriorly (fronto-parietal | temporal)
  - par-occ: z=-1.9 (occipital is the posterior cap)
The temporal is a LATERAL inferior wedge (the `_TEMPORAL_BITE`: below Sylvian AND
x>0.95), subtracted from frontal+parietal so they keep their inferomedial / orbital
surface and the temporal no longer slabs across the midline. Gentle GEOMETRIC gyri
(shared world-space fold field, origin=pos -> continuous across seams) + the
swirl-ink shader on top. Validated: one continuous dome at explode 0, oblique
central/Sylvian seams, both hemispheres meet at the midline, temporal stays lateral
(probe: x>=0.95, none medial of it), orbital surface preserved, base reads as a
proper brain base (hemispheres + olfactory bulbs + brainstem + cerebellum, deep
nuclei only in the central interpeduncular region), wedges separate cleanly on
explode, no NaN/blank, check_data clean.

- done - frontal (paired) - anterior sector, oblique central seam; keeps orbital
  surface (temporal bite subtracted). llm.
- done - parietal (paired) - middle sector (oblique central .. par-occ); keeps
  medial-inferior surface (temporal bite subtracted). llm.
- done - temporal (paired) - LATERAL inferior wedge (below oblique Sylvian, x>0.95,
  z>-1.9); pulled back lateral per human (no longer reaches the midline). llm.
- done - occipital (paired) - posterior cap (z<-1.9). llm.
- done - insula (paired) - now a buried thin SDF ellipsoid (mediolaterally flat,
  gentle gyri) tucked inside the cortical surface (lateral edge ~x=2.35, inside the
  ~2.5 cortex), so it no longer pokes out; reveals laterally on explode. llm.

Cortex polish complete (oblique fissures + temporal pulled lateral + insula tucked,
all agreed w/ human). Possible later: the temporal-orbital parasagittal seam (x=0.95)
is dead-straight on the base; overall dome scale/position fine-tune in Phase 2.

### basal_ganglia

- done - putamen (paired)  [starter trio] - SDF: mediolaterally-flattened lens
  (ellipsoid) with a medial scoop (cradles the globus pallidus) + faint surface
  displace. Phase 0 proof structure. Provenance llm.
- done - caudate (paired) - SDF: the comma/tadpole. A slim tapered `tube` on a 3D
  comma spline (head -> body arching over the thalamus -> wispy tail hooking down +
  forward into the temporal lobe; the tail swings gently lateral so no view
  collapses flat) smooth-unioned with a distinct bulbous head ovoid, under a light
  displace; res 112. Ref: BodyParts3D model (head bulges into the frontal horn,
  tail follows the lateral ventricle). Reads as a clear comma, hidden at explode 0,
  reveals on explode. Replaces the uniform procedural `curve` tube. llm.
- done - globus_pallidus (paired) - SDF: the medial wedge of the lentiform
  nucleus. A medially-tapering roundcone intersected with a tall/AP ellipsoid ->
  a wedge with a convex lateral face (nests in the putamen's medial scoop) tapering
  to a medial apex (toward the thalamus / internal capsule), under a light displace;
  res 72. Verified w/ thalamus+putamen anchors: correct orientation, forms the lens
  with the putamen, hidden behind it from iso. Replaces the smooth blob. llm.
- done - claustrum (paired)  [starter trio] - SDF: a thin (~0.09) curved spherical
  SHELL clipped by an ellipsoid to the claustrum's tall narrow patch (so it is a
  curved lamina concave toward the putamen, not a flat slab); smoothIntersect
  rounds the rim; explicit tight bounds resolve the thin sheet cheaply.
  Demonstrates the SDF shell/intersect (thin-sheet) path. Provenance llm.
- done - accumbens (paired) - SDF: a gentle teardrop (the ventral striatum has no
  distinctive standalone silhouette). A roundcone fat at the free ventral pole
  tapering dorsally (and slightly posterolateral) into the striatum, light displace;
  res 64. Replaces the smooth blob. Position still an anatomical guess. llm.
- done - thalamus (paired) - SDF: the egg. A single tapered roundcone (narrow
  rounded anterior pole -> bulbous posterior pulvinar) gives a clean teardrop with
  no fused-balls waist; axis tilted anteromedial -> posterolateral, under a light
  displace; res 80. Ref: BodyParts3D model + dorsal nuclei schematic (pulvinar
  overhang, AM->PL long axis). L+R pair flanks the midline correctly. Replaces the
  symmetric blob. llm.
- done - substantia_nigra (paired) - SDF: a thin, gently curved lamina (concave
  anteromedially, hugging the cerebral peduncle), not a flat lens. Three flattened
  (thin-DV) ellipsoids smooth-unioned (k=0.30) along an AP arc bowed laterally at
  the middle, under a light displace; res 64. Flat in front view, concave-medial in
  the L+R pair. Replaces the flat ellipsoid. llm.
- done - subthalamic_nucleus (paired) - SDF: a biconvex lens (lentil). Two large
  spheres offset along the thin DV axis, smooth-intersected so their overlap is a
  lens with a crisp equatorial edge, clipped by an AP-elongated ellipsoid (longer
  front-to-back than wide), faint displace; res 60. Replaces the rounded ellipsoid.
  llm.

### limbic

- done - hippocampus (paired)  [starter trio] - SDF: slim tapered tube on a
  genuinely 3D comma spline (head lateral+anterior+inferior, body sweeping
  medial+up+posterior, tail hooking up+forward toward the splenium) + a digitated
  pes (small base paw + 3 finger bumps) + a beaded dentate-gyrus ridge along the
  inferomedial edge + light displace; res 112. Took several passes (straight carrot
  -> ball head -> flat head -> 3D curve -> this): the keepers were the 3D sweep (so
  no view collapses to a bulb-on-a-shaft), slimmer proportions, and the dentate
  beading that finally makes it read as a hippocampus, not a generic tube. Scale
  checked in-context. Provenance llm.
- done - amygdala (paired) - SDF: the almond. A roundcone (tapered capsule) along
  the antero-superior -> postero-inferior axis: fat rounded AS pole tapering to a
  blunt PI tip where it caps the head of the hippocampus, light displace; res 64.
  Verified anterosuperior to the hippocampus head. Replaces the near-sphere blob. llm.
- done - cingulate (paired) - SDF: a flattened C-ribbon (a gyrus is a ribbon, not a
  worm). The parasagittal arch tube intersected with a thin-x slab -> a band thin
  mediolaterally (~0.22) and tall radially, gentle displace; res 100, explicit
  bounds. Reads as the cingulate gyrus over the corpus callosum. Replaces the round
  curve tube. llm.
- holdout - fornix (paired) - kept as the `curve` tapered tube. The fornix is a
  thin white-matter TRACT, and a round swept tube is the anatomically correct
  primitive for a fiber bundle, so SDF offers no clear shape win over the existing
  curve. Possible future refinement (not an SDF win, a topology change): the fornix
  is really a LYRE (the two crura from the hippocampi fuse into a midline body under
  the callosum, then split into the two descending columns to the mammillary
  bodies); modeling that would mean making it a midline structure with a fused body
  + splaying crura/columns + the hippocampal commissure, instead of the current two
  mirrored parasagittal arches. Defer unless the human wants it. llm.
- done - septal_nuclei (paired) - SDF: a small vertical ellipsoid flattened
  mediolaterally (thin in x, set in the thin septal wall), light displace; res 56.
  No distinctive standalone shape, so this is a near-equivalent atlas-medium
  conversion of the blob. Confirmed good via a thalamus-anchored render (renders
  blank alone, a shot.py tiny-lone-structure framing quirk, see imaging note). llm.
- done - olfactory_bulb (paired) - SDF: a match-stick. A swollen anterior bulb
  ellipsoid smooth-unioned with a slender tapered roundcone tract running back (and
  rising gently) toward the brain, faint displace; res 80 with tight bounds for the
  thin tract. Reads as bulb + tract. Replaces the plain elongated blob. llm.

### diencephalon

- done - hypothalamus (paired) - SDF: a rounded mass with the characteristic
  inferior INFUNDIBULAR FUNNEL (the floor / tuber cinereum tapering down + medially
  toward the midline pituitary stalk). Ellipsoid smooth-unioned with a short
  medially-angled roundcone funnel, light displace; res 72. The L+R pair converges
  on the midline (median eminence). Replaces the plain sphere blob. llm.
- holdout - mammillary (paired) - kept as the small `blob`. Each mammillary body is
  genuinely a small round HEMISPHERICAL BUMP, so a sphere is already the correct
  shape and a blob-sphere vs an SDF-sphere is visually identical (no refinement to
  be had). If the human wants a uniformly-SDF atlas, this is a trivial 5-line
  convert (a small ellipsoid + faint displace, like septal_nuclei); flagged, not
  done, because it changes nothing on screen. llm.
- done - pituitary (midline) - SDF: gland-on-a-stalk. A bean ellipsoid (wider ML
  than tall) smooth-unioned with a slender tapered roundcone infundibular stalk
  rising toward the hypothalamus, faint displace; res 72, tight bounds for the thin
  stalk. In context the stalk reaches up between the two hypothalami whose funnels
  angle down to meet it. Replaces the plain blob. llm.

### brainstem_nuclei (monoamine source nuclei)

- holdout - vta (paired) - kept as the small `blob`. The VTA is a diffuse midbrain
  cell group with no distinctive silhouette (a plain small ovoid, medial to the
  SN); a blob-ovoid vs an SDF-ovoid is visually identical, nothing to add. Trivial
  to convert for a uniform-SDF atlas if the human wants it (mammillary precedent). llm.
- done - locus_coeruleus (paired) - SDF: a slim near-vertical CAPSULE (a roundcone
  with near-equal end radii), so the "blue spot" reads as the pencil-line rod of
  cells it is rather than a lens; faint displace; res 56. Replaces the blob. llm.
- done - raphe (midline) - SDF: a slim vertical CAPSULE column hugging the midline
  (the "seam"), faint displace; res 64. Reads as the continuous serotonin column.
  Replaces the vertical blob. llm.

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

- 2026-06-28 - **Cortex polish landed (oblique fissures + temporal lateral + insula).**
  Human review of the one-dome milestone chose: full polish + pull temporal back
  lateral. Done: the central + Sylvian cuts are now OBLIQUE planes (tilted) so the
  seams read like real fissures; the temporal is a lateral inferior wedge (the
  `_TEMPORAL_BITE`, subtracted from frontal/parietal so they keep their orbital /
  inferomedial surface) and no longer reaches the midline; the insula is a buried
  thin SDF ellipsoid that no longer pokes out. `_cortex_lobe` gained oblique-cut +
  `subtract_regions` support (`_cut_to_plane` / `_region_node`). Validated across
  right/left/iso/top/front/bottom + full-brain renders (see scratchpad ob_*/fob_*/
  ins_*). All 5 lobes `done`. check_data clean.
- 2026-06-28 - **Cortex carved into one dome (milestone, awaiting human review).**
  Settled the fold treatment (gentle geometric gyrification + the swirl ink reads
  as cortex; ridged-only read as eroded rock, swirl-only as a smooth ball). Then
  the real fix for the ball-cluster: the four lobes are now sectors of one shared
  cortical-mantle ellipsoid, carved by shared planes, reassembling into a single
  continuous hemisphere. Fixed a mesher NaN (flat cut-plane faces -> MarchingCubes
  0/0 -> NaN vertex -> blank framing). Committed (infra 69a0ef6 + the carve).
  Remaining: insula tuck, oblique seams, temporal-midline OK, dome fine-tune.
- 2026-06-28 - **Cortex grind started, then BLOCKED.** Began the cortex (frontal
  lobe SDF + the ridged-fractal `displace` extension), but the viewer is crashed by
  an unrelated, uncommitted in-flight feature in `public/js/main.js` from another
  session (an `autoSpread` deep-nucleus auto-explode: `createAutoSpread` at line 352,
  `autoSpread` referenced out of scope in the render loop at ~line 4500 ->
  `ReferenceError: autoSpread is not defined` every frame; plus a leftover
  `DBG autoSpreadIfDeep` console.log). Not in this effort's scope, left untouched.
  Human is handling that session. RESUME when main.js loads: render-verify the
  frontal lobe, then continue the lobes.
- 2026-06-28 - **Trio milestone reviewed + approved.** Phase 0 + the starter trio
  (putamen, hippocampus, claustrum) accepted by the human; grind paused here at
  their request. Next session: resume the per-structure grind from the first
  `pending` structure (suggested next: the rest of `basal_ganglia`, or do the
  cortex lobes together as a smooth-union set per Phase 1 / Phase 2).
