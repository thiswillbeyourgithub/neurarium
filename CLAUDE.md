# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository. This file is a
**map**, not a manual: it says what exists, where it lives, and the non-obvious
rules, so you can find the code, not re-read it in prose.

> [!IMPORTANT]
> **Keep this file current AND terse, and do not grow it by default.** Update a
> line here only when a change adds or removes something a reader cannot quickly
> recover from the code itself: a new file, a new user-facing control, a new
> data-contract field, or a non-obvious rule. A pure refactor that keeps the same
> concepts needs no edit here. Prefer editing an existing line to adding one.
> Format contract, to stop it ballooning again:
> - One line per feature/file/control. Name the symbol/file; don't narrate the code.
> - State the *current* behavior only. Never write the history of a decision you
>   reversed ("used to", "the old X", "earlier this was", "no longer"). Just
>   describe what is true now; delete what is not.
> - Give a rationale only when it is non-obvious (a "why" a reader would
>   otherwise get wrong). Skip the obvious why.
> - State each behavior once; cross-reference with "(see X)" instead of repeating.
> - Deeper narrative (diagrams, module graph, boot sequence) lives in
>   [`ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## What this is

A browser-based [three.js](https://threejs.org/) 3D brain visualizer, built with the help
of Claude Code (see [README.md](README.md) for the feature tour): brain regions as
procedural meshes, projection arrows between them, and datasets of neurotransmitter
**receptors**, psychiatric **drugs** (Stahl's Prescriber's Guide), named **circuits**, and
**projection groups** layered on top. Focusing a receptor/drug dims the brain and lights the
regions (glowing "gem" dots) and pathways it touches; a drug adds effect colours
(boost/block/modulate) + a by-mechanism flow overlay. The explode slider blows the assembled
brain radially apart to reveal the deep nuclei.

Region `group` values (`lobe`, `basal_ganglia`, `diencephalon`, `limbic`,
`hindbrain`, `brainstem_nuclei` for the source nuclei raphe / locus coeruleus /
VTA) drive the legend headings + ordering via `GROUP_LABELS` in
`tools/generate_data.py` (emitted into `meta.json`, read by the viewer). Adding a
group means adding it there or its structures drop from the legend.

Coordinate convention (arbitrary units, brain centered on origin): `x` left(-)/
right(+), `y` down(-)/up(+), `z` posterior(-)/anterior(+).

## Nodes (the sourceable-datum model)

**A *node* is any sourceable datum**, one atom of brain knowledge attributable to a
source; the dataset is a graph of nodes and a detail panel is a view of one node plus
every node linked to it. The concept, the umbrella-vs-kind distinction, and the coverage
tally are narrated in [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) ("The node model"); this file
keeps only the kind map below and the grading rules under Source provenance. New data is a
node, and **every node must be sourceable** so the coverage tally stays honest.

> [!IMPORTANT]
> "Node" is the umbrella term; the per-kind names (structure, projection, circuit,
> receptor, drug, binding, target, ...) are **node kinds** and keep their names in the data
> files + code (a `structures.jsonl`, a `showReceptor`). Don't rename the collections to
> "node": that erases the distinction the graph needs.

**Node kinds and where each lives** (the emitted collection -> the sourcing-tally kind
in `meta.provenance_stats.by_kind`):
- brain region -> `structures.jsonl` -> `structures`
- projection (pathway) -> `projections.jsonl` -> `projections`
- functional circuit -> `circuits.jsonl` -> `circuits`
- projection group -> `projection_groups.jsonl` -> `projection_groups`
- receptor classification -> `receptors.jsonl`, split into four independent graded
  sub-claims: neurotransmitter `family` -> `receptors`; mechanism `receptor_class` (GPCR/ionotropic)
  -> `receptor_class`; `sign` (excit./inhib.) -> `receptor_sign`; `synaptic` site (pre/post) ->
  `receptor_synaptic` (a receptor's `classification[attr]` each carry their own grade)
- receptor *expression region* -> a receptor's `location_sources` -> `receptor_locations`
- non-receptor drug target -> `meta.drug_targets` -> `targets`
- target *tone polarity* (a direction-flipping `vesicular`/`sign`/`synaptic` flag) -> a target's `polarity_provenance` -> `target_polarity`
- target *expression region* -> a target's `location_sources` -> `target_locations`
- drug binding -> a drug's `bindings[]` -> `drug_bindings`
- drug NbN label -> a drug's `nbn` -> `drug_nbn`
- drug class classification -> a drug's `categories` (+ `category_provenance`) -> `drug_categories`
- Wikipedia reference -> any node's `wikipedia` -> `references` (a pointer *at* a node,
  tallied but excluded from the headline; a reference is not itself a knowledge node)

**The node sourcing contract.** Every node carries a provenance **grade** and, ideally, a
**source**. The grades, the single source shape, the sourceless case, and the tally +
headline % maths are all defined once under Source provenance; don't restate them here.

## Architecture

The guiding principles (data separate from rendering, no build step, single source of
truth, self-describing data, fail-loud generation), the three-layer data flow, the module
graph, and the boot sequence are narrated in [`ARCHITECTURE.md`](docs/ARCHITECTURE.md). The
non-obvious rules a maintainer needs at the file level:

Most regions are symmetric L/R pairs: a region is defined once on the right in
`generate_data.py` and mirrored, avoiding per-side duplication. Generated files are
committed so the static site fetches them directly.

**Project layout.** Everything the browser loads is under `public/` (the served
site). That directory is the *only* thing web-exposed: Caddy's `/srv` and
`tools/serve.py` both root there, so `docker/`, `tools/`, `.git` and the
uncommitted `.env` / `deploy.sh` / `CLAUDE.local.md` are never web-reachable.
Authoring + dev tooling live in `tools/`, deployment config in `docker/`, the
README hero shot in `docs/`.

### File map

**The `tools/` script reference and the emitted-data field contract (`public/data/`
`.jsonl` / `meta.json` / `shapes/*.json` fields) live in
[`tools/README.md`](tools/README.md)** (Tool reference + Data contract), moved there to
keep this file terse. In short: the anatomy is authored once in `generate_data.py` (drugs
in `tools/data/drugs_data.jsonl`), which emits the committed `public/data/`. `generate_data.py` is
now a thin orchestrator: the data lives in the `tools/data_generators/` package (`i18n`,
`provenance`, `drugs`, `geometry`, `presentation`, `connectivity`, `quotes/`, `receptors/`,
`regions/`; per-module purpose in `tools/README.md`). Each geometry form
is one `data/shapes/<name>.json` (`blob`/`curve`/`composite`, L/R pairs share one right-side
file via `mirror:true`). The author-side scripts are grouped: external-data fetchers under
`tools/fetch/`, provenance appliers under `tools/sourcing/`; their generated caches in
`tools/generated_cache/`. Run them from the repo root (`python tools/fetch/<x>.py`).

> [!NOTE]
> An ongoing effort under `geometry_refinements/` (its own `CLAUDE.md` +
> `STATUS.md`, auto-loaded only when working there) is replacing the procedural
> blob/curve/composite shapes with a self-authored SDF atlas, one structure at a time. It
> adds an `sdf` shape type. Before editing `data/shapes/*` or `shapes.js`
> geometry, check its `STATUS.md` so two sessions don't collide.

Viewer (`public/`):

- `index.html` — page shell: loads three.js (vendored import map) and, on `?debug=1`, vendored
  eruda. Holds the `#controls` panel, the popups (`#shortcuts-modal`, `#legend-modal`,
  `#sourcing-modal`, `#about-modal`, `#image-lightbox`, all `.modal-overlay`), the `#banners`
  stack, the startup `#loading` overlay. UI-chrome accent = the `--accent*` palette in `:root`;
  data/semantic colours live in `meta.json`, never here.
- `js/data.js` — fetches `meta.json` + the `.jsonl` + shape files; returns a normalized
  `{structures, projections, circuits, projectionGroups, projectionGroupsByKey, receptors,
  targets, drugs, drugsByTarget, byId, meta}`. Resolves each node's localized fields + derived
  render props (projection `color`/`sign`, receptor labels + `structureIds`, per-binding
  `targetName`/`actionLabel`/`effect`/`effectColor`/`structureIds`/`flowKind` + the drug's union
  `structureIds`/`flowKinds`/`focusable`/search `keywords`); builds the merged `targets` browse
  list, the `drugsByTarget` reverse index, and `projectionGroupsByKey` (`${mode}:${key}`).
- `js/shapes.js` — `buildGeometry()` dispatches on type to `buildBlobGeometry`/
  `buildCurveGeometry`/`buildCompositeGeometry`; `mirrorGeometryX` for the left member.
  Self-contained Perlin `fractalNoise` (fBm/ridged/domain-warp). Cortical lobes are cel-shaded
  (`MeshToonMaterial`) domes with a shader-drawn swirl (`injectCortexSwirl`/`CORTEX_SWIRL`, pure
  colour, no relief). `buildBlobGeometry` honours `clip_planes` when `JIGSAW_CLIP.enabled`.
- `js/arrows.js` — curved tube+cone arrows; colour from `projection.color`, recolourable via
  `setColor`; `tentative` -> dotted. Exposes `arrow.curve`. Each end attaches to the surface point
  *nearest the other end* (`surfaceToward`, a nearest-vertex scan) so the tip lands on real mass
  even for a concave region (the C-shaped caudate). `update(fast)` re-fits; `fast` reuses the
  cached offset + defers the pick-hull rebuild (see Spread performance), `ensurePickGeometry()`
  rebuilds it on demand. `setWidthScale(s)` rebuilds only the shaft/cone width from the cached arc
  (see Arrow width). `setOpacity` clamps to `ARROW_MAX_OPACITY` (0.8), so arrows are always a
  translucent overlay.
- `js/labels.js` — floating name labels (CSS2DRenderer): one hidden label per region, shown on
  hover / show-all / when pinned (`setPinned`). Reads the hemisphere-stripped `base_name` (the
  side is obvious from position).
- `js/circuit-schedule.js` — `scheduleCircuit()` BFS firing order for the circuit
  pulse (no three.js, testable; see Circuit animation).
- `js/circuit-anim.js` — `createCircuitAnimation` renders that schedule as beads
  riding `arrow.curve` + a wash echo on landing (see Circuit animation).
- `js/receptor-markers.js` — `createReceptorMarkers`: gem-dot expression clouds for
  a focused receptor/target. Exports `buildGemCloud` + `GEM_DOT_SIZE` (reused by
  the drug animation). See Receptors & targets.
- `js/drug-anim.js` — `createDrugAnimation`: per-drug effect-coloured gem dots +
  surface wash; `matches`. Flow overlay reuses `circuit-anim.js`. See Drugs.
- `js/surface-wash.js` — shared `buildWashShell` + `washStrength` "wash of light"
  primitive (used by circuit echo + drug glow).
- `js/anim-settings.js` — `animSettings`, the single source of truth for decorative-animation
  state (read by every animated module): `enabled` (the **Animations** toggle) + `quality` (0..1
  adaptive). See Settings & toggles + Rendering (adaptive quality).
- `js/wiki.js` — `fetchWikiLead(url, lang)` runtime fetch of a Wikipedia lead; locale wins via
  langlinks, English fallback; cached; best-effort (failure -> null).
- `js/main.js` — scene/camera/renderer/lights/OrbitControls; explode + transparency; the intro,
  auto-rotate, hover/pick raycasting; `createInfoPanel`; search; the legend builders
  (`buildLegend`/`buildLegendKey`/`buildTargetLegend`/`buildDrugLegend`); the on-demand render loop.
- `app-config.js` — `window.__APP_CONFIG__`. This committed copy is the local-dev
  fallback (feature fields empty). In the container `entrypoint.sh` renders an
  env-filled copy into `/gen` and Caddy serves that. Generic name (not
  "analytics-*") so content filters don't 404 it. Carries `ANALYTICS_*`, `DEV`,
  `STARTED_AT`, `sourceUrl`.
- Single-purpose modules, each detailed in its own section below: `js/i18n.js` (I18n),
  `js/app-init.js` (Analytics), `js/dev-banner.js` (Dev banner), `js/error-banner.js` (Error
  banners), `js/loading.js` `createLoadingScreen()` (Loading overlay), `version.js`
  `window.__APP_VERSION__` (Versioning).

Deployment (`docker/`): `docker-compose.yml` (hardened Caddy), `Dockerfile`
(strips caddy's `cap_net_bind_service` so `exec` works under `no-new-privileges`),
`Caddyfile` (serves `/srv` on `:8359`, serves `/gen/app-config.js` for
`/app-config.js`, `Cache-Control: no-store`, security headers incl. CSP),
`env.example`, `entrypoint.sh` (stamps `STARTED_AT`, validates `ANALYTICS_URL`,
derives `ANALYTICS_ORIGIN`, renders `/gen/app-config.js`).

Uncommitted, gitignored, environment-specific: `deploy.sh`, `CLAUDE.local.md`
(per-developer setup notes, incl. the deploy procedure and the Stahl source
material location).

## Running

> Moved to [`docs/RUNNING.md`](docs/RUNNING.md) to keep this file terse: serve `public/` over HTTP (`tools/serve.py`); `tools/shot.py` screenshots + the `?params` deep-link view keys.

## Deployment

> Moved to [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) to keep this file terse: the hardened Caddy container (non-root, read-only rootfs, dropped caps); actual deploy procedure in `CLAUDE.local.md`.

## Git hooks

> Moved to [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) to keep this file terse: repo-tracked hooks under `tools/git-hooks/`, activated per-clone; `pre-push` guards `main` + offers the data check.

## Data checks

> Moved to [`docs/DATA_CHECKS.md`](docs/DATA_CHECKS.md) to keep this file terse: `tools/check_data.py` (stdlib) over emitted `public/data/`: six families (duplicates, reachability, TODOs, provenance grades, source quotes, connectivity).

## Internationalization (i18n)

> Moved to [`docs/I18N.md`](docs/I18N.md) to keep this file terse: EN/FR, no build step; UI strings in `js/i18n.js`, data strings authored as `{en,fr}` via `_t()`/`FR` in `generate_data.py` but **emitted English-only** (a serialization-time `externalize` pass collapses each `{en,fr}` to English + deduplicates the French into `public/data/translations.fr.json`, fetched by the viewer only in French). Any new string needs both languages or the build raises.

## Analytics (umami)

> Moved to [`docs/ANALYTICS.md`](docs/ANALYTICS.md) to keep this file terse: optional umami, runtime-injected via `entrypoint.sh` -> `/gen/app-config.js`; generic client-facing names dodge content filters.

## Content-Security-Policy

> Moved to [`docs/CSP.md`](docs/CSP.md) to keep this file terse: Caddy sends CSP + security headers on every response; a new external resource (CDN, font, image host, cross-origin fetch) needs its directive extended in `docker/Caddyfile`.

## Dev / WIP banner

> Moved to [`docs/ANALYTICS.md`](docs/ANALYTICS.md) to keep this file terse: optional amber WIP banner, `DEV`/`STARTED_AT` in `app-config.js`, `js/dev-banner.js`; same runtime-injection plumbing as analytics.

## Error banners

> Moved to [`docs/BANNERS.md`](docs/BANNERS.md) to keep this file terse: failures surface as red dismissible banners (`js/error-banner.js`) so a visitor never opens the console.

## Loading overlay

> Moved to [`docs/BANNERS.md`](docs/BANNERS.md) to keep this file terse: startup `#loading` progress overlay (`js/loading.js`) + the startup Sources-and-provenance gate.

## Controls

> Moved to [`docs/CONTROLS.md`](docs/CONTROLS.md) to keep this file terse: the one collapsible bottom-left `#controls` panel and everything in it: the Settings pane + accordion sections, the detail-tab strip, the seven `show*()` info-panel views, selection/halo + isolate, structure-name labels, legend sections, keyboard/touch input + search, and camera focus.

## Rendering

The render loop (`renderer.setAnimationLoop`) is **on-demand**: each frame runs the cheap checks
(tweens + `controls.update()`) but skips the expensive part (`cull.tick()` + `renderer.render()` +
`labels.render()`) unless a render is needed; when idle the canvas holds its last frame. A render is
triggered when a controller animated (each per-frame `tick()` returns a "did I animate" boolean:
`intro`/`focus`/`circuitAnim`/`receptorMarkers`/`drugAnim`), the camera moved (`controls.update()`
true), or `invalidate()` fired (wired to OrbitControls `change`, `resize`, a catch-all over user
input).

> Adding a per-frame controller? Make its `tick()` return whether it animated, or it runs but never
> repaints. Screenshots are unaffected (renders the settled frame, then idles).

### Adaptive quality

`createAdaptiveQuality` keeps animation smooth on a weak GPU by watching the frame time of
*rendered, animating* frames (`adaptive.tick(rendered && active)`) and, with hysteresis, stepping the
shared `animSettings.quality` (0..1, clamped [0.6,1]) down when frames stay slow and up when they
recover. The dominant lever is `renderer.setPixelRatio(baseDpr * quality)` (fewer shaded pixels beats
the additive-glow overdraw of the gem/wash animations); secondarily the gem-dot (`dotCountFor`) +
circuit bead counts scale too, picked up on the next focus. Not persisted (a live measurement).
Composes under **Animations**: off means no motion to measure, so quality idles.

### Spread performance

Re-fitting the ~100 arrows each explode frame was dominated (~90%) by the per-end nearest-surface
scans, making Separate janky. During a continuous spread the arrows update in `fast` mode
(`applyExplode(..., true)` -> `ProjectionArrow.update(true)`): each end reuses its cached offset
(valid because regions only translate, never rotate) and pick-hull/halo rebuilds are deferred.
`createArrowRetrim` then re-trims precisely once the spread has been still ~120ms, a chunk per frame;
a click mid-spread calls `arrow.ensurePickGeometry()`. The settled result matches the per-frame-precise
layout.

### Arrow width

Arrows hold a roughly constant *apparent* width as the camera zooms. `createArrowWidth` scales each
arrow's shaft/cone by the camera<->target distance via `ProjectionArrow.setWidthScale` (rebuilds only
the width from the cached arc, no surface scan; reference distance captured on the first tick). The
explode auto-zoom is divided out via `focus.explodeZoom()`, so a **spread** doesn't rescale arrows
(only a genuine user zoom does), keeping it off the spread's hot path. The fat pick hull stays a
constant world size. Persists across explode rebuilds; clamped [0.4, 2.4]x.

## Circuit animation

Isolating a circuit plays a traveling-pulse: glowing beads ride each arrow source -> target, firing
in sequence and looping. Split in two:

- **`js/circuit-schedule.js`** (ordering, no three.js, testable). `scheduleCircuit` treats the
  arrows as a directed graph and a multi-source BFS from seeds sets each arrow's firing slot
  (`phase`) to its tail's BFS depth. Seed per component: the `group=="lobe"` node (cortex), else
  highest out-degree, else any. The seed set is mirror-completed (`mirrorId`) so L/R-paired nodes
  fire at equal depth. A feeder branch fires when activation reaches its tail, else at the cycle top.
- **`js/circuit-anim.js`** (rendering). `createCircuitAnimation` turns each slot into an additive
  bead riding `arrow.curve` (rebuilt on every explode), the burst keyed off the projection's `sign`
  (`BURST`: excitatory more/faster/brighter, inhibitory dimmer). On landing a bead fires a wash echo
  over the target (`buildWashShell` at `arrow.curve.getPoint(1)`, pathway colour, sign-keyed).

Lifecycle (`js/main.js`): the row calls `selection.setCircuit(...)` then `circuitAnim.play(...)`.
Stopping rides the selection state: an `onIsolate` watcher `stop()`s whenever the pinned-arrow set is
no longer exactly the animating circuit (`circuitAnim.matches`), so a clear / different circuit /
group focus / legend isolate all stop it; a mere structure highlight keeps it. Circuit-only (a group
focus uses `setCircuit` but never `play`).

## Circuit + projection-group panels

A Circuits row and a Projections (per-pathway) row each open a **sourced detail tab**, like a
structure/drug row. Member pathways are never stored: a circuit's are the projections with both
endpoints in its set, a group's are those whose `kind`/`sign` matches `key`. `js/data.js` localizes
both and indexes groups by `${mode}:${key}` (`projectionGroupsByKey`).

- `showCircuit`: a "Functional circuit" heading with the loop's source pill (`circuit.provenance`),
  the Wikipedia illustration (`appendWikiImages`), the description + reference (`appendReference`,
  live-refreshed with a baked fallback), its structures (deduped to bases, clickable via
  `onStructure`), and its member pathways.
- `showProjectionGroup`: a by-transmitter / by-effect heading with the group's source pill
  (`group.provenance`), the description (live-refreshed, its own pill), the reference, the member
  pathways, then (kind-mode only) a **Drugs acting on this system** list = focusable drugs whose
  `flowKinds` include this kind (mirror of the drug panel's Projections affected; jumps via `onDrug`).
- Both reuse the shared `pathwayRow`/`appendPathwayList` helper (also used by `showStructure`), which
  runs rows through `pathwayList` to collapse left/right twin pathways to one row.
- `focusCircuit` / `focusProjectionGroup` mirror `focusDrug`: isolate (a circuit also
  `circuitAnim.play()`s; a group is a static pinned-arrow focus), show the panel, open the tab
  (`circuit:` / `group:`) with a reopen thunk. `tabs.setOnEmpty` clears the focus when the last
  closes. i18n: `circuit.heading/structures/pathways`, `group.kindHeading/signHeading/pathways`.

## Receptors & targets

A focusable section listing the merged `data.targets` = every receptor (`receptors.jsonl`, authored
as `RECEPTORS`) **plus** every non-receptor drug target from `meta.drug_targets` (transporters,
enzymes, ion channels, receptor groups), so a target like SERT is explorable on its own. Built by
`buildTargetLegend`, grouped by neurotransmitter **system**. **System headings** order by total
knowledge nodes (each target's own node + its "Found in" regions + the bindings on it via
`data.drugsByTarget`), so a heavily-drugged system leads; "Other" is pinned last. **Members** order
lexicographically (`localeCompare` `numeric`, so 5-HT2 precedes 5-HT10). Both sources are normalized
in `js/data.js`.

- A receptor row's swatch = its **sign** colour; a non-receptor row's = its **type** colour
  (`target_type_colors`) + a muted tag. Clicking focuses it: dims to its regions
  (`selection.setCircuit(regionMeshes, [])`, no arrow pin) + `createReceptorMarkers.show(...)`.
- **Markers** (`js/receptor-markers.js`): dense additive **gem dots** over each region's surface (a
  `THREE.Points` cloud sampled from the mesh geometry + parented to it, so they track explode/mirror
  and vanish when it hides; count scaled by surface area; pulsed). Builder `buildGemCloud` (+
  `GEM_DOT_SIZE`), reused by the drug animation. Stopped via an `onIsolate` watcher (`.matches`).
- Panels: a receptor opens `showReceptor` (system, Wikipedia link, live-refreshed description, then
  the four classification facts (family / class / sign / synaptic) each carrying their *own*
  per-attribute grade pill (a quote grades only the attributes it substantiates, so an unsourced
  GPCR/sign/site reads honestly as `llm` instead of borrowing a neighbour's quote), then the "Found in" list via
  `locationList` grouped under `groupLabels` sub-headings, each region carrying its **own**
  expression-provenance pill + an amber "· <species>" tag when it has no human assay (`locationEntry`
  prefers Human, so an Allen confirmation clears it), or one pilled "Throughout the brain" for
  ubiquitous). A non-receptor target opens the lighter `showTarget` (type + system facts with their
  grade pills, a **Tone polarity** row for a target carrying a direction-flipping `vesicular`/`sign`/
  `synaptic` flag (its *own* graded node `target_polarity`, not the classification grade, since the flag
  flips the drug-flow overlay's sign; `TARGET_POLARITY_QUOTES` upgrades it, else `llm`), then the same
  per-region "Found in" list, kind `target_locations`). Both add a **PDSP
  Ki** lookup link (`appendLookupLink`); a receptor also gets **UniProt** (human-only) + **GtoPdb**
  name-search links (`uniprotSearchUrl`/`gtopdbSearchUrl`, no pill). Both carry an **Interacting
  drugs** section (from `drugsByTarget`, grouped by category, each row an `effectGlyph` + the
  binding's `bindingProvenancePill` = the *same* resolved binding the drug panel shows; jumps via
  `info.onDrug`). Both make each "Found in" region clickable (`info.onStructure` -> `selectStructure`).
  A stub receptor / unlocated target renders muted.

Receptor data: `_receptor_record` validates every family/class/sign/synaptic key + location base;
`locations="ALL"` -> `ubiquitous`. Each of the four classification attributes is a **separate** graded
node: the base grade defaults `llm` (overridable in `RECEPTOR_PROVENANCE`) and a
`STAHL_ESSENTIAL_RECEPTOR_QUOTES` quote upgrades **only** the attributes listed for that receptor in
`RECEPTOR_CLASSIFICATION_COVERAGE` (assigned conservatively: never when the quote and the record
disagree, e.g. CB1's "inhibition of release" quote describes retrograde function, not the receptor's
own excit./inhib. sign, so `sign` stays `llm`). A quote
need not be the same across the four attributes: `RECEPTOR_ATTR_QUOTES` gives an attribute its own
quote(s) instead of the main one, so a compound value earns `verified` only when every part is
attested (5-HT1B/D `synaptic="both"` needs one presynaptic + one postsynaptic quote). Each
expression region is a **separate** graded claim (kind
`receptor_locations`, default `llm`, upgraded per (receptor, region) by `RECEPTOR_LOCATION_SOURCES`,
quote-checked); these drove the `brainstem_nuclei` group. A non-receptor target's type/system/regions
are authored in `DRUG_TARGETS`; its regions grade identically (kind `target_locations`,
`TARGET_LOCATION_SOURCES`; both share the `_location_sources` emitter).

## Drugs

A focusable Drugs section showing, per drug, what it does to the brain. The psychiatric
drugs come from **Stahl's Prescriber's Guide (8th ed.)**, extracted **strictly from the dump**
(only interactions literally stated; gaps left as TODO / no binding); the `recreational`
category (LSD, MDMA, ketamine, cocaine, nicotine, ...) and any future substance are **not**
Stahl-bound, their bindings sourced from measured **PDSP Ki** instead. Adding a drug is just a
new row in `drugs_data.jsonl` (see Changing the data), so the corpus is open-ended, not a
fixed Stahl list.

- **Data.** The drugs live in `tools/data/drugs_data.jsonl`, read by `_load_drugs`. Vocabularies are
  defined once in `generate_data.py`: `DRUG_CATEGORY_LABELS`, `DRUG_ACTIONS` (action -> {label, net
  `effect`}), `DRUG_EFFECT_COLORS`/`DRUG_EFFECT_LABELS` (boost/block/modulate), `DRUG_TARGETS`
  (non-receptor targets, `type` a `TARGET_TYPE_LABELS` key). `_build_drug_targets` merges
  `DRUG_TARGETS` with every receptor id (so a binding can target `sert` or `5ht2a`) ->
  `meta.drug_targets`. `_drug_record` validates category/target/action/effect + rejects duplicate
  ids. A binding's net `effect`: agonist / reuptake-inhibitor / releaser / enzyme-inhibitor / PAM ->
  **boost**; antagonist / inverse-agonist / NAM / blocker -> **block**; partial-agonist / modulator
  -> **modulate**.
- **Animation** (`js/drug-anim.js`). Clicking a drug row (`buildDrugLegend`, grouped by category,
  with the live `#drugs-filter`) focuses it: dims to the union of its targets' regions
  (`selection.setCircuit(regionMeshes, flowArrows)`) + `createDrugAnimation.show(...)`, which
  scatters a `buildGemCloud` per binding coloured by net effect (pulsed per effect) under a
  `buildWashShell` in the same colour; each binding's `affinityWeight` scales its dot density
  (`buildGemCloud`'s `densityScale`), size and brightness (potent target reads denser/brighter).
  Stopped via an `onIsolate` watcher (`.matches`).
- **By-mechanism flow overlay** (reuses `js/circuit-anim.js`). The focus also rides beads along the
  projections of the drug's target system(s). It is a **tone-setter + autoreceptor** model, split from
  the dots: only *tone-setting* bindings drive flow (a reuptake/enzyme/vesicle target or a presynaptic
  inhibitory autoreceptor), never a postsynaptic receptor (those stay dots). `js/data.js` gives each
  binding a signed `toneSign` (`toneSignOf`: reuptake-inhibitor/releaser/MAO-inhibitor +, vesicular
  (VMAT2)/vesicle-protein blocker −, autoreceptor agonist − / antagonist +; a `vesicular` flag + the α2
  group's `sign`/`synaptic` come from `meta.drug_targets`) and an `affinityWeight` (0.35..1 pKi ramp
  from the measured Ki, engagement not effect size). Per engaged kind it sums `toneSign*affinityWeight`
  into `flowSystems` (`{direction, weight, rel}`): the sign is the flow direction (an SSRI drives serotonergic
  **up**, buspirone's 5-HT1A agonism **down**, a VMAT2 blocker **down**), the clamped magnitude its absolute
  `weight`, and `rel` the same normalized **per-drug** so the strongest engaged system = 1 (dosage varies, so
  the overlay shows *relative* intensity across systems). `circuit-anim.js` `play(arrows, flowSystems)` streams
  beads **continuously** end-to-end along each arc (a curated circuit keeps its sequential BFS volley; a drug
  focus, signalled by a passed `flowSystems`, streams so the relative density + speed read), recolouring/scaling
  per arrow off `rel` (boost = warm/bright/fast/dense, damp = cool/dim/slow/sparse). The system map is data: `system_flow_kinds`
  (target `system` -> projection `kind`, the diffuse ascending systems with a modeled source nucleus;
  glutamate/GABA left out). `focusDrug` filters arrows (`flowArrowsOf`), pins + `circuitAnim.play()`s
  them; a purely postsynaptic drug sets no tone -> dots + wash only. **Caveat:** a D2-antagonist
  antipsychotic reads dopaminergic-**up** (blocking the D2 *autoreceptor* disinhibits release); its
  postsynaptic blockade shows in the block-coloured dots. (This is why the dataset carries the ascending
  monoamine pathways.)
- **Panel** (`showDrug`): the molecule image (when fetched), the class, the NbN, the description
  (live-refreshed from Wikipedia, re-graded `sourced`), a Wikipedia link, then the **Acts on** binding
  list (each row: an effect glyph + target + action·note, "· speculative" when tentative, plus a
  `bindingProvenancePill` = the binding's quote source, else its Ki (verified), else `NOSOURCE`),
  sorted strongest-affinity first. Below it a **Projections affected** list (only when `flowKinds`
  non-empty): one row per ascending system whose tone the drug sets (jumps to that kind-mode group,
  pilled with the strongest binding on the system), an out-/in-arrow per `flowSystems[kind].direction`
  (raises / lowers tone); a *derived* inference from the tone-setter bindings (caption says so). Class +
  Nomenclature are clickable (open search with a `class:`/`nbn:` filter) and each carries its grade
  pill: the NbN quote source, and the class classification's `category_provenance` (its own node, kind
  `drug_categories`, default `llm`, upgradeable via `DRUG_CATEGORY_PROVENANCE` / `category_sources`).
- **Binding affinity (PDSP Ki).** A binding's `ki` (from `fetch_ki.py`) renders as a `kiChip`: the
  median + `[min-max]` + human/non-human counts + a **verified** badge (tooltip = the representative
  assay). Non-human-only is amber; an alias-borrowed value (`ki.mapped`) carries a "⚠ measured as
  `<compound>`" warning. `affinity_only` bindings (a Ki, no known direction) list as "affinity only"
  with a neutral glyph, no source pill, and never animate (excluded from `structureIds`/`flowKinds`).
  A **combo** drug (name "A + B") leads with a warning box linking each constituent (`drug.combo`);
  combos carry no Ki. A measured Ki backs `_binding_grade`, lifting the binding to `verified`.

5 drugs stay unbound as genuinely non-receptor agents (lithium, disulfiram, l-methylfolate,
triiodothyronine, caprylidene). The Stahl corpus `url` is `"TODO"` (the grade, not the link, conveys
provenance).

## Images

Two third-party image sources, handled differently on purpose.

- **Molecule images** (vendored same-origin; CSP `img-src 'self' data:`). `tools/fetch/fetch_molecules.py`
  downloads each drug's lead infobox SVG via the MediaWiki `pageimages` API into
  `public/data/molecules/<id>.svg` (`.svg` only, `<script>` stripped); writes
  `tools/generated_cache/molecules_sources.json`. `generate_data.py` emits `structure_image` only when the file
  exists. `showDrug` renders it as `<img class="mol-structure">` with CSS `filter: invert(1)` for the
  dark panel (so the page declares `color-scheme: dark`). No image if absent.
- **Structure images** (hot-linked from Wikimedia; the multi-MB GIFs are NOT vendored, only the url).
  `tools/fetch/fetch_structure_images.py` resolves a **hero** per **base** (fallback: `.gif` -> `.svg` ->
  infobox/lead; pdf/djvu lead -> first-page JPG) + a **gallery** (`gather_gallery`: the other gif/svg
  on the base's EN+FR articles, chrome excluded via `_is_gallery_chrome`, capped `MAX_GALLERY`) into
  `tools/generated_cache/structure_images_sources.json`, downloading no bytes (`IMAGE_OVERRIDES` wins for the hero).
  The **same resolver** runs over wiki-linked **circuits** (`--target circuits`) into
  `tools/generated_cache/circuit_images_sources.json`. `generate_data.py` emits `structure_image` + `_gallery` for
  both (loaded by `_load_image_sources`). `showStructure`/`showCircuit` render them via the shared
  `appendWikiImages(heroUrl, gallery, altName)`: the hero lazily with a spinner (`error` removes the
  figure), then a "show more" toggle that builds the gallery **lazily on first expand**. Needs the
  `img-src https://upload.wikimedia.org` CSP allowance.

**Lightbox.** Clicking any panel image pops it up large in `#image-lightbox` (`wireImageLightbox`,
reuses `.modal-overlay`): `open(src, alt, {invert})` fills the viewport (capped `MAX_UPSCALE`; SVGs
stay crisp), `invert` mirrors the molecule inversion. Closed by ×, backdrop, or **Esc** (routed first
in `wireShortcuts`). Darker backdrop than the shortcuts modal. i18n: `image.close`/`image.zoomHint`.

## Source provenance

How every **node** (any sourceable datum, see Nodes) is graded + sourced. Every node's source/reference
carries a **provenance grade** (the dataset is LLM-assisted, not yet human-checked), rendered as a
coloured **pill**; the grade is **data**. Grades (`PROVENANCE_LEVELS`, weakest to strongest):

- **`llm`** (grey **?**): LLM from memory, unchecked, may be a hallucination.
- **`sourced`** (yellow **~**): LLM given the source document, not quote-verified.
- **`verified`** (green **✓**): an LLM extracted a quote, it was *programmatically* confirmed present in
  the source, and a separate LLM agreed it supports the claim. Highest grade; still LLM-driven.
- absence -> a red **✕** pill (`NOSOURCE_GLYPH`, `.src-todo`). Not a stored grade.

Every node's grade rides its own row/heading (`makeProvenancePill(level)`, `info.prov*` tooltip via
`withTip`), never a separate bottom "Sources" block (a source only ever grades one node); a node with
no source shows `NOSOURCE`, never a blank. How the tally buckets these grades (and why `llm` counts as
unbacked): see The "% sourced" figure.

**Where the grade lives.** One source shape, quote-level `{corpus, page, quote, provenance}` against a
`SOURCE_CORPORA` corpus; `provenance` defaults `DEFAULT_PROVENANCE` (`"llm"`), a sourceless node is
`NOSOURCE`. Each `wikipedia` reference emits a sibling `wikipedia_provenance` (`WIKIPEDIA_PROVENANCE`
registry); a **present** link defaults `"sourced"` (`WIKIPEDIA_DEFAULT_PROVENANCE`), not `llm` (a real
reference the viewer live-fetches). `_provenance` validates every grade; upgrading a source is a data edit.

**Per-claim sources + the verify gate.** The nodes carrying such a source: a
binding's `sources[]`, a drug's `nbn_sources[]`, a projection/circuit/group quote (`KANDEL_QUOTES`), a
receptor/target location/classification, region anatomy. `corpus` keys the source-agnostic
`SOURCE_CORPORA` registry (`{ref, citation, url, pages_dir}`, emitted as `meta.source_corpora`; the
full citation is resolved from there, not denormalized onto the ~429 bindings). `_quote_sources` /
`_binding_sources` validate corpus + grade (a `verified` source needs page + quote). `verified` is
earned by a two-step (LLM extract + LLM judge supports), then `check_data.py`'s source-quote check
confirms the quote is really on the page (the backstop against a hallucination). **Page files are
author-side (see `CLAUDE.local.md`), so the quote gate is skipped + warned on a clone that lacks them**
(true for every corpus below). A binding with no quote source falls back to its **Ki** (verified), else
`NOSOURCE`. The **NbN** is simpler: `apply_nbn_sources.py` greps Stahl's verbatim
"Neuroscience-based Nomenclature: <value>" line and confirms the dataset `nbn` is a substring (stronger
than a judge for this fixed field); a newer drug with no NbN line falls back to Stahl's **Class** line
under the same gate, marked `nbn_nonstandard`.

The corpora (`SOURCE_CORPORA`), each quote-gated author-side as above unless noted:
- **#1 Stahl / #2 Kandel / #3 Stahl Essential / #4 Carlat / #6 Nieuwenhuys** are `pages_dir` book
  corpora (`page` = a page number): drug bindings/NbN/class (Stahl), pathways + region anatomy (Kandel,
  Nieuwenhuys), receptor/target mechanism (Stahl Essential); see `CLAUDE.local.md` for the trees.
- **#5 PDSP Ki** (`pdsp_ki`) has a `csv` path, not `pages_dir` (measured Ki values, not paged text). A
  binding's `ki.source` cites a **Ki id** (a CSV row) instead of a page; `check_data.py` confirms the
  row exists with that value. A verified Ki backs `_binding_grade`. Refresh `fetch_ki.py --apply`.
- **#7 GtoPdb** (`gtopdb`, `page` = a GtoPdb targetId) is the source for **receptor** "Found in"
  regions. A confirm-only LLM judge maps a cached quote (by index) to each existing region (never
  adds/drops one); `apply_location_sources.py` writes the `verified` source into
  `tools/generated_cache/location_sources.json`. Each quote carries the assay **`species`** (Human/Rat/Mouse/Monkey,
  validated in `_quote_sources`); a non-human-only region shows an amber "· <species>" tag.
- **#8 Allen AHBA** (`allen_ahba`, `page` = an HGNC gene) is the complement covering **non-receptor
  targets** + the receptors/regions GtoPdb misses. `fetch_allen.py` turns the microarray **PACall**
  boolean across human donors into a deterministic present/absent (**no judge**);
  `apply_location_sources.py --corpus allen` writes the `verified`, `species: Human` source. The panel's
  species tag prefers Human (`locationEntry`), so an Allen confirmation clears the amber tag. **Caveat:**
  microarray = mRNA in cell bodies, so a transporter confirms at its source nucleus (SERT->raphe,
  NET->LC) and its terminal-region claims honestly stay `llm`.

**Descriptions** are not a node kind (not tallied). Drugs, structures and non-receptor targets carry
**no baked description**: their panel fetches the **current Wikipedia lead** (CC BY-SA) at runtime via
`liveWikiDescription` over `js/wiki.js` `fetchWikiLead(url, lang)` (locale lead, English fallback), so
the dataset ships no copyrighted prose (a panel whose live lead fails shows none). Receptors + projection
groups carry a short **authored** `description` as the offline fallback, overridden best-effort by the
live lead. Needs the `connect-src https://*.wikipedia.org` CSP allowance.

**The `wikipedia` pill (green, viewer-only).** A live-fetched lead renders a green **✓** pill (same
glyph as `verified`: both are inspectable non-LLM extracts), NOT the stored `sourced`/`llm` grade: a
live fetch is a verbatim programmatic read that cannot drift from the article. It is a **presentation**
(`PROVENANCE_PILLS.wikipedia` + `info.provWikipedia`, `.src-prov-wikipedia` shares the green), **not** a
stored grade and **not** tallied. Asymmetry: a **baked** Wikipedia snapshot stays yellow `sourced` (a
stored copy *can* drift); only the **live** read earns green. A present reference *link* carries no pill
(the description above already grades the same source, `appendWiki(url)`); a missing link shows `NOSOURCE`.

**The "% sourced" figure.** `_provenance_stats` reduces every node + reference to its strongest grade and
buckets it into **verified** (quote-checked) / **sourced** (from a document) / **missing** (no document).
A bare `llm` grade *is* missing (an LLM asserting from memory has no document), so it buckets with a
sourceless node (the viewer still shows them differently, grey `?` vs orange `NOSOURCE`). It tallies per
node kind (drug bindings, NbN, drug class, projections, circuits, projection groups, receptor/target
classifications, receptor/target expression regions, region anatomy, wikipedia references), plus a
headline `pct_backed` over the **knowledge nodes** (references excluded, a reference points *at* a node),
emitted as `meta.provenance_stats` (key `nodes`). Each expression region is its own node, individually
upgradeable. **The live per-kind figures live in the README `SOURCING_STATS` block (auto-written by
`update_readme_stats.py`, CI runs it `--check`) and the Sources & provenance popup; they are not repeated
here, to avoid drift.** `check_data.py` re-confirms the tally is self-consistent (coverage columns M/S/S+V).

## Changing the data

The step-by-step runbook (per node-kind authoring fields, the regenerate/check/fetch
sequence, and the author-side "refresh external data" recipe) lives in
[`tools/README.md`](tools/README.md). The invariants that outlive any recipe: edit the
source of truth (`generate_data.py`, or `tools/data/drugs_data.jsonl` for drugs), never the
emitted `public/data/`; every new display string needs its `FR`/`{en,fr}` translation or
the build raises; commit the generator change + regenerated artifacts together; keep drug
extraction strictly dump-sourced. The legend rebuilds from the data at runtime.

## Versioning

The version is a single string in `version.js` (`window.__APP_VERSION__`), shown in the
panel header + the WIP banner (both read the global). Follow [semver](https://semver.org/);
to release, bump `version.js`. It is intentionally not derived from git (the site deploys as
plain files).

## Conventions

- No JS build step or package manager: three.js is vendored same-origin under
  `public/vendor/three` and loaded via an import map in `index.html`. Keep the import-map
  entries pointing at the vendored files; bump the vendored copy as a unit.
- `generate_data.py` is stdlib-only so it runs offline.
- Don't duplicate the anatomy *or its presentation maps*: positions/colors/shape params, the
  `kind -> colour` and `group -> heading` maps live only in `generate_data.py` (the latter
  emitted into `meta.json`, read by the viewer).
- **Structure granularity is demand-driven.** The modeled brain sits at a deliberately
  uneven granularity: fine where the data forces it (the monoamine source nuclei; the
  brainstem cut into midbrain/pons/medulla because the pathways name the pons), coarse where
  nothing yet forces it (each lobe is one piece, the thalamus one nucleus). Cut a region into
  finer sub-structures only when the receptor/projection/drug data distinguishes its sub-parts
  AND can source that distinction, or the LLM-assisted dataset is pushed to invent anatomy it
  cannot source. The frontal-lobe -> prefrontal-cortex split is the next cut this would justify.
