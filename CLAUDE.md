# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository. This file is a
**map**, not a manual: it says what exists, where it lives, and the non-obvious
rules, so you can find the code, not re-read it in prose.

> [!CAUTION]
> **This is a large, wide-ranging codebase: manage your context deliberately.** The
> data model, generator, viewer, sourcing pipeline and deploy stack are each sizeable, so
> you cannot hold it all at once. Read only what a task needs (this map -> the one file ->
> the one symbol), lean on the doc split (`ARCHITECTURE.md`, `tools/README.md`, `docs/*`)
> instead of re-reading prose, and prefer targeted search over whole-file reads.
> **Keep files small and hierarchically organized so no single file balloons and dilutes
> context.** When adding code, anticipate its growth and place it so it stays cohesive:
> split a module *before* it gets unwieldy, reuse existing helpers rather than duplicating
> (see the no-duplication rule under Conventions), and design the seams up front so a later
> costly refactor / dedup pass is not needed. A file that has grown too big to load
> comfortably is itself a bug to fix.

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
`hindbrain`, `brainstem_nuclei` for the diffuse source nuclei raphe / locus
coeruleus / VTA / tuberomammillary / nucleus basalis) drive the legend headings + ordering via `GROUP_LABELS` in
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
- receptor *expression density profile* -> a receptor's `density` -> `receptor_density` (ONE
  node for the whole profile, not one per region: it is a single measurement ranking the
  receptor's regions against each other, see Expression density)
- non-receptor drug target -> `meta.drug_targets` -> `targets`
- target *tone polarity* (a direction-flipping `vesicular`/`sign`/`synaptic` flag) -> a target's `polarity_provenance` -> `target_polarity`
- target *expression region* -> a target's `location_sources` -> `target_locations`
- target *expression density profile* -> a target's `density` -> `target_density` (same shape)
- drug binding -> a drug's `bindings[]` -> `drug_bindings`
- drug NbN label -> a drug's `nbn` -> `drug_nbn`
- drug commercial brand name -> a drug's `brands[]` -> `drug_brands` (each brand a graded
  node; `region` na/eu/fr orders them per locale, never shown; na from Stahl, eu/fr from Wikipedia)
- drug class classification -> a drug's `categories` (+ `category_provenance`) -> `drug_categories`
- drug elimination half-life (T½) -> a drug's `half_life` (+ `half_life_sources`) -> `drug_half_life`
- drug metabolism role -> a drug's `enzymes[]` (`{enzyme, role, strength?}`) -> `drug_enzymes`
  (one node per (enzyme, role) pair; pharmacokinetics, so it has no anatomy, see Drug metabolism)
- drug active metabolite -> a drug's `metabolites[]` (each `{name, drug_id?, half_life?,
  bindings?, formed_by?, sources}`) -> `drug_metabolites` (a metabolite that is itself a modeled
  drug links via `drug_id` + reuses its bindings/T½)
- metabolite-forming enzyme -> a metabolite's `formed_by[]` (`{enzyme, reaction?, sources}`) ->
  `drug_metabolite_enzyme` (one node per (parent, metabolite, enzyme); the mirror of
  `drug_enzymes`, counted per PARENT since two parents make it by two reactions)
- non-modeled-metabolite receptor binding -> a metabolite's `bindings[]` -> `drug_metabolite_bindings`
  (sourced from the metabolite's own Wikipedia pharmacology, corpus #9; graded like a drug binding,
  a separate kind so the drug Ki coverage is unperturbed; surfaces on the receptor's Interacting drugs)
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
`generate_data.py` and mirrored, avoiding per-side duplication. The same holds for
projections: a symmetric pathway is emitted **once** in `projections.jsonl` carrying
`mirror: true` (not as two `_R`/`_L` rows), and the consumer reflects it by flipping
`_R` <-> `_L` on both endpoints (`js/data.js` at load, `check_data.py` before its
checks); `symmetric: False` opts out. So each pathway is one node in the tally, not two.
Generated files are committed so the static site fetches them directly.

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
`provenance`, `drugs`, `geometry`, `genes`, `presentation`, `connectivity`, `quotes/`, `quote_table`,
`receptors/`, `regions/`; per-module purpose in `tools/README.md`). Each geometry form
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
  stack, the startup `#loading` overlay. An author **byline** ("by Olivier Cornelis", linking
  olicorne.org per locale via the shared `common.byline` i18n key) sits both in `#loading`
  (`.loading-byline`) and inline in the panel header, right of the `neurarium` title
  (`.panel-byline` in `#controls-header`, over an invisible full-row `.collapse-hit` button so a
  row click still toggles the panel while the byline link stays clickable). UI-chrome accent = the `--accent*` palette in `:root`;
  data/semantic colours live in `meta.json`, never here. Also wires the PWA: links
  `manifest.webmanifest` + registers `sw.js`.
- PWA (installable + offline): `manifest.webmanifest` (name/icons/`theme_color`), `sw.js`
  (service worker that ALWAYS contacts the server when online, so a visitor never renders
  outdated data or a stale ES module; the Cache-API copy is an offline-only fallback, NOT
  stale-while-revalidate. One strategy for every same-origin asset (data, code, shell):
  **explicit conditional revalidation** (`revalidate()` forwards the cached copy's
  `ETag`/`Last-Modified` as `If-None-Match`/`If-Modified-Since` so an unchanged file returns a
  bodyless `304` served from cache, a changed one a fresh `200`: always fresh, cheap when
  unchanged, no version key to forget; `cache:"no-store"` on the fetch so OUR validator is the
  only one in play, since a plain SW fetch re-downloads the full body). Revalidating code is
  what keeps a stale ES module from running (each file is confirmed current before use) *without*
  re-downloading ~1 MB every load, which is what made a phone reload crawl. Bump `CACHE` when the
  caching logic changes; `activate()` prunes older caches), and
  `favicon.svg` + `icon-192/512.png` +
  `apple-touch-icon.png` (a **placeholder** node-cluster glyph, to be replaced by the designed
  favicon). Caddy pins `.webmanifest`'s content-type (Go's mime table lacks it).
- SEO/social: static `<head>` meta (description, Open Graph, Twitter card, JSON-LD
  `WebApplication`) + a `<noscript>` text fallback in `index.html`; `robots.txt` +
  `sitemap.xml` + `og-image.png` (a copy of `docs/images/screenshot.png`) in `public/`.
  All English (a crawler reads the raw HTML before i18n; no prerender step) and the
  canonical / `og:url` / `og:image` / JSON-LD URLs are **hardcoded to the public domain**
  (update all four spots + `sitemap.xml`/`robots.txt` if it ever changes).
- `js/data.js` — fetches `meta.json` + the `.jsonl` (incl. `quotes.jsonl`) + shape files, rehydrates
  each `{quote_id, provenance}` source from the deduplicated `quotes.jsonl` excerpt table
  (`rehydrateQuotes`, mirror of the generator's externalize; see Source provenance); returns a normalized
  `{structures, projections, circuits, projectionGroups, projectionGroupsByKey, receptors,
  targets, drugs, drugsByTarget, byId, meta}`. Resolves each node's localized fields + derived
  render props (projection `color`/`sign`, receptor labels + `structureIds`, per-binding
  `targetName`/`actionLabel`/`effect`/`effectColor`/`structureIds`/`flowKind` + the drug's union
  `structureIds`/`flowKinds`/`focusable`/search `keywords`); builds the merged `targets` browse
  list, the `drugsByTarget` + `targetsByStructure` reverse indexes (the latter reads a receptor's
  "Found in" from the region's end, so a structure panel can list what is expressed there carrying
  the very same graded node), and `projectionGroupsByKey` (`${mode}:${key}`).
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
  adaptive) + `speed` (persisted 0.25..4 speed multiplier, the **Animation speed** slider). See
  Settings & toggles + Rendering (adaptive quality).
- `js/wiki.js` — `fetchWikiLead(url, lang)` runtime fetch of a Wikipedia lead; locale wins via
  langlinks, English fallback; cached; best-effort (failure -> null).
- `js/tour.js`: `createTour({steps, labels, onEnd, seenKey})`, a generic, three.js-free coach-mark
  engine (spotlight ring / caption bubble, viewport-aware placement that never covers the target or
  the 3D scene, resize/scroll reposition, localStorage "seen" gate). The bubble is **drag-repositionable**
  (pointer-drag past a small jitter threshold; a dragged bubble opts out of auto-placement for the step)
  and layered **above any `veil`** so it is never itself dimmed. There is **no Next button** (only
  Back + Skip + Esc): the user advances by acting on the step, so they cannot fast-forward past a
  hands-on demo. A step is passive/caption (a "click to continue" cue in the bubble, and a click on the
  dim backdrop, advance it) or **`interactive`** (the blocker gets a clip-path click-through hole so the
  user's real tap reaches the highlighted control; the cue is hidden and every off-target click + the
  forward keys are inert, so the only way on is the real tap). An interactive step advances on that tap,
  or with **`stayAfterTap`** stays put and steps its spotlight aside so the live demo it fired is
  watchable (the cue then returns to move on). A step's `target` may be one element or an **array** (a group highlight: the ring spans
  their union, e.g. the four browse sections). Steps glide between positions (snap only on the first
  step + during an active scroll). The app-specific step list is built in `js/main.js`; the data demos
  are hands-on and follow the data graph (focus a **drug** (olanzapine), read its pharmacodynamics then
  its pharmacokinetics (**Metabolism**, then open the collapsed **Drug interactions**), follow one of its
  bindings to a **receptor** (H1), then visit a **structure** (hippocampus) and a **projection system**
  (dopamine, a static group, not a circuit); each opened by tapping the highlighted row via its
  `data-tour-id`, each panel section reached via its `data-tour-sec`),
  each step's `before()` setting the scene (spread, open/collapse a section, reset a prior demo).
  Auto-runs once on a first visit (after the intro settles), forced every load with `?tour=1`, and
  replayed from the About popup's "See the tutorial" button (`#about-tour`).
- `js/changelog.js` — `createChangelog()`, the "What's new" popup (`#changelog-modal`). See
  Versioning / Changelog.
- `js/main.js` — scene/camera/renderer/lights/OrbitControls; explode + transparency; the intro,
  auto-rotate, hover/pick raycasting; `createInfoPanel`; search; the legend builders
  (`buildLegend`/`buildLegendKey`/`buildTargetLegend`/`buildEnzymeLegend`/`buildDrugLegend`); the
  on-demand render loop.
- `app-config.js` — `window.__APP_CONFIG__`. This committed copy is the local-dev
  fallback (feature fields empty). In the container `entrypoint.sh` renders an
  env-filled copy into `/gen` and Caddy serves that. Generic name (not
  "analytics-*") so content filters don't 404 it. Carries `ANALYTICS_*`, `DEV`,
  `STARTED_AT`, `sourceUrl`.
- Single-purpose modules, each detailed in its own section below: `js/i18n.js` (I18n),
  `js/app-init.js` (Analytics), `js/dev-banner.js` (Dev banner), `js/error-banner.js` (Error
  banners), `js/loading.js` `createLoadingScreen()` (Loading overlay), `version.js`
  `window.__APP_VERSION__` (Versioning), `js/render-order.js` `DECOR_RENDER_ORDER`
  (Rendering / decoration draw order).

Deployment (`docker/`): `docker-compose.yml` (hardened Caddy), `Dockerfile`
(two-stage: `xcaddy build`s a custom binary with the `caddy-ratelimit` module,
so `docker compose build` needs network; then strips caddy's
`cap_net_bind_service` so `exec` works under `no-new-privileges`),
`Caddyfile` (serves `/srv` on `:8359`, serves `/gen/app-config.js` for
`/app-config.js`, `Cache-Control: no-cache` on everything (store but always revalidate ->
cheap `304`s, never stale, and never a heuristically-cached module); a generous per-`{client_ip}` `rate_limit`
flood guard, keyed via the front proxy's `X-Forwarded-For`/`trusted_proxies`;
security headers incl. CSP),
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

> Moved to [`docs/DATA_CHECKS.md`](docs/DATA_CHECKS.md) to keep this file terse: `tools/check_data.py` (stdlib) over emitted `public/data/`: eleven families (quote table, duplicates, reachability, TODOs, provenance grades, source quotes, connectivity, Ki coverage, drug flow consistency, changelog, innervation coverage).

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

> Moved to [`docs/BANNERS.md`](docs/BANNERS.md) to keep this file terse: startup `#loading` progress overlay (`js/loading.js`) + its `.loading-tagline` tease. The Sources popup is NOT shown on launch (it opens on demand only).

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

### Decoration draw order

Every additive decoration that clings to a structure (gem-dot clouds, wash shells, selection
halos) is pinned to `DECOR_RENDER_ORDER` (`js/render-order.js`) so it always draws after the
structures. The structure materials are `transparent: true` (for the slider), and three.js
sorts that pass by each object's **geometry bounding-sphere centre**, so a decoration with its
own geometry (a dot cloud is a sparse surface sample) otherwise sorts *before* the region past
some camera azimuth and the region paints over its own glow: the dots vanish abruptly as you
rotate. Occlusion is unaffected (structures still write depth, decorations still depth-test).

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
  per-region "Found in" list, kind `target_locations`). Both add **PDSP
  Ki** + **ClinPGx** lookup links (`appendLookupLink`); a receptor also gets **UniProt** (human-only) +
  **GtoPdb** search links (`uniprotSearchUrl`/`clinpgxSearchUrl`/`gtopdbSearchUrl`, no pill). The
  gene databases (UniProt, ClinPGx) search the node's `gene`, its HGNC symbol (α1A -> `ADRA1A`; an
  identifier, not a graded node, mapped in `data_generators/genes.py`), GtoPdb the display name. Both carry an **Interacting
  drugs** section (from `drugsByTarget`, grouped by category, each row an `effectGlyph` + the
  binding's `bindingProvenancePill` = the *same* resolved binding the drug panel shows; jumps via
  `info.onDrug`). A **receptor_group** target (α2/glutamate) additionally lists, under its own
  Interacting drugs, one collapsed **By receptor subtype** dropdown per modeled subtype that has drugs
  (`appendSubtypeInteractors` off `target.subtypes`, a sourceless taxonomy in `meta.drug_targets`), so
  a subtype binder (asenapine at α2A) is reachable from the coarse panel. Both make each "Found in"
  region clickable (`info.onStructure` -> `selectStructure`). A stub receptor / unlocated target renders muted.

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

### Expression density

The "Found in" list answers *where*, not *how much*; a `density` profile ranks those regions
against each other. Derived from **Allen AHBA** (corpus #8) microarray intensity: per donor, the
representative probe's log2 intensity is z-scored across all that donor's samples, averaged per
base, then averaged across donors, so a region's `z` reads "this many standard deviations from
this gene's brain-wide average". Reliability = the median pairwise Pearson **r** between donors'
profiles; a gene below `DENSITY_MIN_R` (0.5, in `fetch_allen.py`) publishes **nothing**, so the
noise floor is an honesty gate rather than a caveat. **Confirm-only**: a profile is trimmed to the
regions the owner already claims, never adding one.

- **One node per profile**, not per region (`receptor_density` / `target_density`): it is a single
  measurement over the owner's regions, so per-region tallying would flood the headline with ~1000
  uniformly-verified nodes.
- The whole profile (every region's z, the donor list, the probe, and `r`) is written **into the
  quote**, so `check_data.py`'s verbatim gate covers the numbers a reader judges it by, and the
  pill tooltip exposes them in-app.
- Pipeline: `fetch_allen.py` (`--skip-density` opts out of the heavy MicroarrayExpression read)
  -> `data_sources/allen/density.json` -> `tools/sourcing/apply_expression_density.py` ->
  the committed `tools/generated_cache/expression_density.json`, merged into `RECEPTOR_DENSITY` /
  `TARGET_DENSITY` + `DENSITY_MIN_RELIABILITY` (emitted as `meta.density_min_reliability`).
- Viewer: `js/data.js` `densityEntry` normalizes it to `{profile, rel, reliability, donors,
  provenance, sources}` (`rel` = the z rescaled to 0.08..1 for the bar); `locationList` prepends a
  caption row ("Relative amount" + the donor-agreement r + the profile's grade pill) and
  `locationRow` appends a bar + signed z per region. **Caveat shipped in the caption tooltip:**
  mRNA, not protein, and transcript sits in cell bodies, not terminals (SERT peaks at raphe).

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
  scatters a `buildGemCloud` coloured by net effect (pulsed per effect) under a `buildWashShell`
  in the same colour, **one pair per (region, effect)**, not per binding: a region carrying many
  of the drug's targets otherwise stacked a cloud + a full-surface wash per binding (26 on one
  region for clozapine), which saturated it to flat white and paid that many shader passes for
  one colour. The group keeps its strongest binding's `affinityWeight`, which scales dot density
  (`buildGemCloud`'s `densityScale`), size and brightness (potent target reads denser/brighter),
  and the wash gain is split between the effects on a region (`washScale`), so a region glows
  like one wash however many effects it carries. Stopped via an `onIsolate` watcher (`.matches`).
- **By-mechanism flow overlay** (reuses `js/circuit-anim.js`). The focus also rides beads along the
  projections of the drug's target system(s). It is a **tone-setter + autoreceptor** model, split from
  the dots: only *tone-setting* bindings drive flow (a reuptake/enzyme/vesicle target or a presynaptic
  inhibitory autoreceptor), never a postsynaptic receptor (those stay dots). `js/data.js` gives each
  binding a signed `toneSign` (`toneSignOf`: reuptake-inhibitor/releaser/MAO-inhibitor +, vesicular
  (VMAT2)/vesicle-protein blocker − but a VMAT2 **substrate** (`vesicular_releaser`: the amphetamines,
  MDMA, which dump the stores) +, autoreceptor agonist − / antagonist +; a `vesicular` flag + the α2
  group's `sign`/`synaptic` come from `meta.drug_targets`) and an `affinityWeight` (0.35..1 pKi ramp
  from the measured Ki, engagement not effect size). Per engaged kind it sums `toneSign*affinityWeight`
  into `flowSystems` (`{direction, weight, rel}`): the sign is the flow direction (an SSRI drives serotonergic
  **up**, buspirone's 5-HT1A agonism **down**, a VMAT2 blocker **down**), the clamped magnitude its absolute
  `weight`, and `rel` the same normalized **per-drug** so the strongest engaged system = 1 (dosage varies, so
  the overlay shows *relative* intensity across systems). `circuit-anim.js` `play(arrows, flowSystems)` streams
  beads **continuously** end-to-end along each arc (a curated circuit keeps its sequential BFS volley; a drug
  focus, signalled by a passed `flowSystems`, streams so the relative density + speed read), recolouring/scaling
  per arrow off `rel` (boost = warm/bright/fast/dense, damp = cool/dim/slow/sparse). The system map is data: `system_flow_kinds`
  (target `system` -> projection `kind`, the diffuse systems with a modeled source; glutamate/GABA
  left out, and `melatonergic` is mapped for the group panel though its MT1/MT2 are postsynaptic so no
  drug ever rides it). `focusDrug` filters arrows (`flowArrowsOf`), pins + `circuitAnim.play()`s
  them; a purely postsynaptic drug sets no tone -> dots + wash only. **Caveat:** a D2-antagonist
  antipsychotic reads dopaminergic-**up** (blocking the D2 *autoreceptor* disinhibits release); its
  postsynaptic blockade shows in the block-coloured dots. (This is why the dataset carries the ascending
  monoamine pathways.)
- **Panel** (`showDrug`): the molecule image (when fetched), the class, the NbN, the description
  (live-refreshed from Wikipedia, re-graded `sourced`), a Wikipedia link + the EMA / FDA / ClinPGx /
  Drugs.com (+ Vidal in French) `appendLookupLink` searches, then the **Acts on** binding
  list (each row: an effect glyph + target + action·note, "· speculative" when tentative, plus a
  `bindingProvenancePill` = the binding's quote source, else its Ki (verified), else `NOSOURCE`, or the
  orange ⚠ when it carries `uncertainty[]`, see Source provenance),
  sorted strongest-affinity first. Below it a **Projections affected** list (only when `flowKinds`
  non-empty): one row per ascending system whose tone the drug sets (jumps to that kind-mode group,
  pilled with the strongest binding on the system), an out-/in-arrow per `flowSystems[kind].direction`
  (raises / lowers tone); a *derived* inference from the tone-setter bindings (caption says so). Class +
  Nomenclature are clickable (open search with a `class:`/`nbn:` filter) and each carries its grade
  pill: the NbN quote source, and the class classification's `category_provenance` (its own node, kind
  `drug_categories`, default `llm`, upgradeable via `DRUG_CATEGORY_PROVENANCE` / `category_sources`).
- **Half-life + active metabolites (Stahl PK).** A drug carries an elimination `half_life`
  (`{hours, hours_max?}`, its own graded node kind `drug_half_life`, source `half_life_sources`) and a
  `metabolites[]` list, each an **active metabolite** (a `name`, its own `half_life`/`half_life_sources`,
  and `sources`; graded node kind `drug_metabolites`; a `drug_id` when the metabolite is itself a modeled
  drug so the panel links to it). `showDrug` renders T½ as an `hl-chip` (auto-scaled to min/h/days via
  `formatHalfLife`, between the brands and the **Acts on** list) and an **Active metabolites** section
  (each row its name + its own T½ chip, "a bit like the Ki"). In `buildDrugLegend` a default-on
  **Show active metabolites** toggle (`#drugs-show-metabolites`, persisted `neurarium.metabolites`) adds
  discreet indented `.metab-item` bullets under each parent (a bullet + its parent both stay visible
  when the drugs filter or the global search matches the metabolite name). Pipeline mirrors the brand one:
  `tools/fetch/fetch_pharmacokinetics.py` scans the Stahl page spans into `pk_worklist.json`, one LLM pass
  writes `pk_judged.json`, and `tools/sourcing/apply_pharmacokinetics.py` quote-gates + merges T½/metabolites
  into `drugs_data.jsonl` (idempotent, sole writer).
- **Non-modeled-metabolite receptor bindings (Wikipedia).** A metabolite that is not itself a modeled
  drug carries its own `bindings[]` (kind `drug_metabolite_bindings`), sourced from the metabolite's own
  English Wikipedia pharmacology (corpus #9 `wikipedia_pharm`) + the PDSP Ki database (corpus #5): **target
  + action** from a quote-gated prose sentence; **affinity** prefers a PDSP measured Ki, else the Wikipedia
  table value. PDSP is BOTH a target-discovery source (every modeled target with an active assay on the
  metabolite's own name becomes a binding, so norfluoxetine gets its 11 measured sites even though its
  Wikipedia article has no Ki table) AND the preferred Ki for a Wikipedia-found target; a discovered target
  with no sourced action stays an `affinity_only` binding. A receptor's
  Interacting-drugs list then shows the binder as "NAME (metab. of PRODRUG)" (`drug.metaboliteOf`, via
  `drugsByTarget`). Pipeline: `tools/fetch/fetch_metabolite_bindings.py` (reuses
  `fetch_wikipedia_pharmacology` as a library) mines each metabolite's own article (an allow-list of
  confirmed own-articles) **and its parent drug's article** for prose (parent lines mention-filtered to the
  metabolite so a parent-only claim can't leak; an own-article metabolite still draws on its parent because
  a thin own article, e.g. Seproxetine for norfluoxetine, often omits the binding profile the parent states),
  a quote gating against whichever read page holds it, into `metabolite_bindings_worklist.json`; one LLM pass writes
  `metabolite_bindings_judged.json`; `tools/sourcing/apply_metabolite_bindings.py` quote-gates + merges
  into `drugs_data.jsonl` (idempotent, sole writer of a metabolite's bindings). **Shared metabolite:** one
  metabolite can be produced by several modeled drugs (desipramine by imipramine + lofepramine, mCPP by
  nefazodone + trazodone), so it appears once under each parent; its bindings are a property of the
  molecule, so the applier keys by metabolite name and writes an **identical** list to each parent, the
  tally + viewer dedup it by folded name (counted / listed once, "metab. of A, B"), and `check_data` fails
  loud if two parents' inline copies ever diverge (a hand-edit backstop).
- **Binding affinity (PDSP Ki).** A binding's `ki` (from `fetch_ki.py`) renders as a `kiChip`: the
  median + `[min-max]` + human/non-human counts + a **verified** badge (tooltip = the representative
  assay). Non-human-only is amber; an alias-borrowed value (`ki.mapped`) carries a "⚠ measured as
  `<compound>`" warning. `affinity_only` bindings (a Ki, no known direction) list as "affinity only"
  with a neutral glyph, no source pill, and never animate (excluded from `structureIds`/`flowKinds`).
  A **combo** drug (name "A + B") leads with a warning box linking each constituent (`drug.combo`);
  combos carry no Ki. A measured Ki backs `_binding_grade`, lifting the binding to `verified`.
  `fetch_ki.py --apply` drops every PDSP assay >=10 uM as "inactive", so a genuine but weak binder
  (caffeine at A2a) can only be recorded by hand; such a `ki.source` carries `"curated": true` so the
  idempotent `--apply` refresh never strips it (`_is_curated_ki`). Where PDSP has no assay at all,
  GtoPdb's curated interactions (corpus #11) fill in: a Ki for a Ki-less binding, and a
  a direction for an `affinity_only` one (see `apply_gtopdb_ki.py`). Such a binding is a binding
  like any other: it animates, and its source pill names the corpus. The authored
  `provisional_action` flag exists only for that applier's idempotency and is deliberately **not**
  emitted (`sources` already carry the corpus, so it would be a derivable duplicate).

5 drugs stay unbound as genuinely non-receptor agents (lithium, disulfiram, l-methylfolate,
triiodothyronine, caprylidene). The Stahl corpus `url` is `"TODO"` (the grade, not the link, conveys
provenance).

## Drug metabolism

Which enzymes clear a drug, or have their activity changed by it. **Pharmacokinetics, so it
has no anatomy**: a liver enzyme is not a brain region, and nothing here ever lights the 3D
scene (the Enzymes section's caption says so, so a still scene reads as intended).

- **Data.** `ENZYMES` / `ENZYME_ROLES` (`substrate`/`inhibitor`/`inducer`, each with the
  `direction` it moves a co-prescribed substrate's level) / `ENZYME_STRENGTHS` (`major`/`minor`
  for a substrate, `strong`/`moderate`/`weak` for the rest) live in `tools/data_generators/drugs.py`,
  emitted into `meta.enzymes*`. Field is `enzyme`, not `cyp`: the non-CYP routes (UGT, esterases,
  MAO) will want the same one. Strength is **ordinal on purpose**: the AUC fold-changes behind
  the regulatory tiers are not in the corpora (see `docs/SOURCING_GAPS.md`).
- **Sourcing: two deterministic fetchers, no LLM in either**, each writing a committed cache
  `generate_data.py` merges (rows are NOT authored in `drugs_data.jsonl`); **Stahl wins** a
  (enzyme, role) pair both state.
  - `tools/fetch/fetch_cyp.py` -> `generated_cache/drug_enzymes.json`, from Stahl's per-drug
    `Pharmacokinetics` block, regular enough ("Substrate for CYP2D6", "Inhibits CYP2C19") that
    a pattern match + the ordinary verbatim quote gate beats a judge. Only that block is read:
    the `Drug Interactions` block's isoform sentences are mostly about *other* drugs acting on
    this one.
  - `tools/fetch/fetch_cyp_wikipedia.py` -> `generated_cache/drug_enzymes_wikipedia.json`, from
    the drug's stored English Wikipedia article (corpus #9), the only source for the drugs
    outside Stahl's roster. Leans on the **drugbox `Metabolism` row** (regular, and a substrate
    claim by construction); prose is read only per *sentence*, with the drug named before the
    verb and nothing in between that hands the verb another subject, plus a negation veto and a
    victim-frame veto tested on the sentence **head** only (Wikipedia states absence and other
    molecules' metabolism constantly, which Stahl's terse bullets never did; what follows the
    verb is the claim's own consequence, so vetoing on it dropped genuine rows). A sentence
    stating two roles is **split by position**, each enzyme going to the verb it follows, while
    a later verb stays coordinated with the first. Non-CYP routes are read only where `ENZYMES`
    carries them (`adh`), never guessed.
- **Which enzyme FORMS an active metabolite** is the mirror relation (there the drug is the
  substrate, here the metabolite is the product) and its own node kind, so it is **hand-curated**
  in `tools/data_generators/quotes/metabolism.py` (`METABOLITE_ENZYME_QUOTES`, keyed
  `(drug_id, metabolite name)`) rather than grepped: the corpora state it as prose whose near
  misses are all wrong the same way (an enzyme that *clears* the metabolite, or makes a different
  one). 14 of the 36 metabolites are covered; the rest stay NOSOURCE. `reaction` is an optional
  `ENZYME_REACTIONS` key (a closed, translated vocabulary), omitted when the source names the
  enzyme but not the step. `generate_data.py` raises if a key matches no metabolite, so an
  applier re-run cannot silently drop a node.
- **Viewer.** `showDrug` gains a **Metabolism** list (enzyme + role + strength + its own grade
  pill, clickable to the enzyme, headed by a ClinPGx pathway-search link) and a **Drug interactions**
  list, both **after** the anatomy sections
  (pharmacokinetics lights nothing in the scene, so it does not interrupt Acts on -> Projections
  affected -> Acts within); each **Active metabolites** row gains a `.metab-formed` "formed by
  <enzyme>" line with its own pill. An **Enzymes** accordion section
  (`buildEnzymeLegend`) opens `showEnzyme`: a ClinPGx search (the variant / poor-vs-ultra-rapid
  metabolizer story this dataset does not model), the metabolites that isoform forms, then its drugs
  grouped by role. Both ends share one `enzymeRow` builder (same node, either side).
- **The drug -> drug edges are derived, never stored** (`pkInteractionsOf` in `js/data.js`, like
  `flowSystems`): an inhibitor/inducer of an enzyme meets its substrates, one row per (other drug,
  direction) naming every shared isoform. Rendered two ways from the same edges via a persisted
  segmented control (`PK_GROUP_KEY`): **by drug** (the four `PK_DIRECTIONS` buckets as headings,
  raises/lowers first, then raised-by/lowered-by) or **by enzyme** (one heading per isoform, so a
  pair meeting at two isoforms appears under each, sub-grouped by those same four directions). A
  row is the drug name alone: the direction is always a heading above it, never repeated per row.
  Capped **per heading** (8) with the rest expandable in place, since a global cap would swallow
  whole headings. Collapsed by default (a `disclosure` `<details>`,
  summary = title + edge count, opening it scrolls itself to the top of the pane) so dozens of
  derived rows don't bury the sourced sections above. Because the edges are an **inference**, every
  string stays conditional ("could raise", never "raises"). The caption states it is a flag to check
  with a prescriber, **never a contraindication**, and that a missing row is not a safety claim.

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
- **`uncertain`** (orange **⚠**): not a stored grade either but a **display grade**, taken by a node
  whose `uncertainty` bullets are non-empty (see below). It replaces the green ✓ on the pill and in the
  tally, and buckets as **backed** (the quote really was checked).

Every node's grade rides its own row/heading (`makeProvenancePill(level)`), never a separate bottom
"Sources" block (a source only ever grades one node); a node with no source shows `NOSOURCE`, never a
blank. The pill's tooltip shows the concrete source (the verbatim quote + citation) then a small "Click
for details" cue (`makeDetailsCue`) that opens the Sources & provenance popup: that popup is the single
place explaining what each grade means, so the verbose per-grade paragraph is not inlined into every
pill (it stays only as the pill's `aria-label`, `info.prov*`). The popup's tally is
**progressive-disclosure** (`buildAboutSourcing`): one global bar over all knowledge nodes by default,
clickable to reveal the per-node-kind bars, each of which is in turn clickable to reveal its grade counts
+ one clickable **example node** (`buildKindExample`: a representative datum rendered as a knowledge
triplet, its notion in quotation marks, that navigates to the real drug/receptor/structure/circuit/group).
The grade key lists only `NOSOURCE` / `llm` / `uncertain` / `verified` (the `~sourced` and
live-Wikipedia rows were dropped: no knowledge node is ever graded `sourced`). How the tally buckets
these grades (and why `llm` counts as unbacked): see The "% sourced" figure.

**The sourcing model.** A verified quote node may carry an optional `llm` (`haiku`/`sonnet`/`opus`,
`SOURCING_LLMS`) naming the model that extracted+judged it, so a reader can weigh a quote by that
model's capability; it is quote-node metadata (not part of the id hash), absent = unknown. Any new
sourcing/recheck pass must stamp it (a non-LLM deterministic source like Allen's PACall omits it).
A batch recheck (`tools/sourcing/recheck_quotes.py`, run as a Sonnet workflow) writes a central
`generated_cache/quote_llm.json` (`{quote_id: llm}`) that `quote_table` applies uniformly (an override
wins over a source-level `llm`); quotes it could not confirm land in `quote_recheck_flagged.json` for
review, not stamped.

**Where the grade lives.** One source shape, quote-level `{corpus, page, quote, provenance}` against a
`SOURCE_CORPORA` corpus; `provenance` defaults `DEFAULT_PROVENANCE` (`"llm"`), a sourceless node is
`NOSOURCE`. Each `wikipedia` reference emits a sibling `wikipedia_provenance` (`WIKIPEDIA_PROVENANCE`
registry); a **present** link defaults `"sourced"` (`WIKIPEDIA_DEFAULT_PROVENANCE`), not `llm` (a real
reference the viewer live-fetches). `_provenance` validates every grade; upgrading a source is a data edit.

**Where a quote sits (the book heading).** A quote node from a **book** corpus may carry a derived
`heading`: a **trail** of headings, outermost first (`["Clozapine", "Side effects", "How Drug Causes
Side Effects"]`, capped to its 3 deepest levels), rendered as a breadcrumb above the passage in the
source tooltip and handed to the LLM judge in `recheck_quotes.py`'s batches. A flat list, not named
levels, because the books do not share a shape (a Stahl monograph, a Kandel part/chapter/section, a
Nieuwenhuys chapter), so the viewer only joins it. It is **context, not a claim** (not a node, not
graded, not tallied), and it is what makes a quote judgeable rather than merely checkable: the same
sentence under *How the Drug Works* is Stahl attributing a mechanism to that drug, under *How Drug
Causes Side Effects* it is a subject-less rule (the distinction the `uncertain` badge rests on).
Derived by `tools/fetch/fetch_quote_headers.py` into the committed
`generated_cache/quote_headers.json` and applied by id in `quote_table` (like `quote_llm.json`).
Two resolvers: the four outline-bearing books (Kandel, Stahl Essential, Carlat, Nieuwenhuys) take
the ancestor chain of their `INDEX.md` entry covering the page; **Stahl** has no usable outline, so
its trail is read off the page text (monograph title from `INDEX.md`, then positional subsection,
then **section = a subsection -> section majority vote over all 158 monographs**, since the
extraction drops ~30 section headings and the nearest surviving one then leaks in from the previous
section or drug). A corpus is a "book" exactly when its page tree has an `INDEX.md`, which is what
excludes the flat stores (GtoPdb, Allen, Wikipedia) where a chapter has no meaning. An unresolved
level is **omitted**, never guessed. `check_data.py` family 5 checks the shape, then re-derives the
checkable half offline (a Stahl trail must open with the monograph containing the cited page),
which catches a stale or hand-edited cache.

**Doubting a `verified` claim (the `uncertain` badge).** `verified` says the sentence is on the page; it
never said the sentence is *about this node*. A node whose quote does not attribute the claim carries an
`uncertainty[]` array (drug bindings + projections, `tools/data_generators/quotes/uncertainty.py`), which
takes over its pill: orange ⚠, tooltip = "Here are LLM-written reasons to be uncertain about this claim:"
then one bullet per reason, then the node's own source as usual. **Every bullet is itself a badged,
sourced claim**: a `kind` from the closed `UNCERTAINTY_REASONS` vocabulary (emitted as
`meta.uncertainty_reasons`) + slot `args`, and either a real quote-gated source (the kind declares whether
it reuses the owner's own quote or its Ki) or `absence: true`, which renders the red ✕ and reads "the
corpus does not say this". No prose is stored: the sentence comes from an `uncertain.<kind>` i18n key, so
a new kind means a new string in **both** catalogues. Forgetting a source raises at generation
(`_uncertainty_bullet`) and errors in `check_data.py` family 5, which also gates each bullet quote
verbatim and stands its subject-less-quote guard down for a binding that declares uncertainty (the two
answer the same problem). **Nothing is authored per site**: `apply_binding_uncertainty` /
`apply_projection_uncertainty` *derive* both the flags and the bullets from the emitted data, so a data
edit cannot leave a stale flag behind and a new drug or arrow is covered the day it lands. Three flags
today, and a node hit by any is uncertain:
- **the subject-less side-effect rule** (89 bindings): the quote's heading trail ends in Stahl's *How Drug
  Causes Side Effects* and the sentence does not attribute the action to the drug (`_attributes_to_drug`:
  it neither names it, nor uses a pronoun subject, nor elides the subject in Stahl's telegraphic style).
  This is what the heading trails were resolved for.
- **the family-level claim** (`family_claim`, +22): one source sentence covers several of the drug's
  bindings on subtypes of one family (same id stem) and names none of them individually, so the split into
  subtypes is ours, not the book's ("Blockade of alpha adrenergic 1 receptors" -> alpha1A/B/D). Bearable
  when a measured Ki pins the subtype down, so it only flags a subtype **with no Ki**.
- **the blanket pathway claim** (`blanket_claim`, 35 projections): the projection twin of the above. An
  anatomy book states a diffuse system by its sweep ("project to virtually every part of the neuraxis"),
  so one sentence sources several arrows out of one nucleus while naming none of their targets: which
  regions the sweep is drawn to is our reading. Same `>= 2 siblings, none named` construction, over
  regions; a target the sentence *does* name (raphe -> thalamus) keeps its green check.
Both run as a post-pass (not `_binding_record` / `_projection_records`) because the bullets look across
siblings: `class_wide` counts the drugs the same sentence is printed on, `family_claim` the subtypes one
sentence covers, `blanket_claim` the arrows.

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
under the same gate, marked `nbn_nonstandard`. **Brands** are gated the same way:
`apply_brand_sources.py` reads each drug's Stahl "Brands?" dump list and confirms each brand appears
verbatim on the drug's page range (region `na`, `verified`); a brand not found verbatim is dropped, not
guessed. The eu/fr brands come from Wikipedia (corpus #10 `wikipedia_fr`), region-tagged only for ordering.

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
- **#9 Wikipedia pharm** (`wikipedia_pharm`, `page` = the article slug) backs a binding **Ki** where PDSP
  (#5) has none (a *fallback*, never overriding a measured assay). `fetch_wikipedia_pharmacology.py` stores
  the whole English article author-side (pinned to a revision id) and mines its pharmacodynamics binding
  table; a Ki source's `quote` is the verbatim table row, gated exactly like a book page. A tertiary
  source citing the primary literature: the grade attests quote-presence, the corpus label conveys tier.
- **#10 Wikipedia FR** (`wikipedia_fr`, `page` = the FR article slug) is the source for a drug's
  **European / French** commercial brands (`eu`/`fr` region; na comes from Stahl). The FR infobox holds
  only chemistry, so the trade names live in prose; `fetch_brand_names.py` resolves each drug's FR article
  (via the EN article's langlinks), stores it author-side under `data_sources/wikipedia/pages_fr/`, and
  emits a candidate-sentence worklist; an LLM extracts each drug's ordered trade names, and
  `apply_brand_names.py` quote-gates every name verbatim on the FR page (the hallucination backstop),
  writing the first as `fr` and the rest as `eu`. A brand source's `quote` is the brand name.
- **#11 GtoPdb ligand interactions** (`gtopdb_ki`, `page` = the GtoPdb ligand slug) is GtoPdb's
  *other* half (#7 is its tissue API) and complements PDSP (#5) where a radioligand panel
  structurally cannot reach: **targets PDSP does not assay** (the GABA-A benzodiazepine site,
  MAO-A/B, acetylcholinesterase, orexin, melatonin, SV2A, Nav) and the **direction** of an
  `affinity_only` binding. One versioned bulk CSV (`DATA/interactions.csv`), so
  `fetch_gtopdb_ki.py` is deterministic (no judge): it joins on **gene symbol** (case-folded, a
  rodent row reads `Scn2a`), flattens each matched compound's rows into
  `data_sources/gtopdb/pages_ki/<slug>.md`, and a proposal's `quote` is one verbatim row line, so
  the normal quote gate applies unchanged. `apply_gtopdb_ki.py` merges **confirm-only** (never
  adds a target) and **PDSP-first** (a Ki only where there is none; a stated direction always
  wins), reporting rather than resolving a disagreement. Only a pKi/pKd becomes a `ki`: a
  functional potency (pIC50/pEC50) rides along as the direction's citation. Contents CC BY-SA 4.0,
  database ODbL.
- **#12 GtoPdb target classification** (`gtopdb_class`, `page` = the GtoPdb targetId) is GtoPdb's
  third slice, backing the *mechanism* nodes: a target's `type` (gpcr/lgic/vgic/enzyme) is a
  receptor's `receptor_class` and a non-receptor target's `type`, read directly; a GPCR's `sign`
  is **mapped** from its transduction table (`transducers` + `effectors`) under the narrow table
  in `apply_classification_sources.py` (Gi/Go -> inhibitory, Gs / Gq/G11 -> excitatory; anything
  mixed or unmapped writes nothing), since GtoPdb states the transduction and never a sign. No
  judge: `fetch_gtopdb_class.py` flattens both fields into `data_sources/gtopdb/pages_class/
  <targetId>.md` and the applier is **confirm-only** (writes only where GtoPdb agrees with the
  value we already state, reporting a disagreement instead of rewriting the data). The sources
  **add to** a book quote rather than replacing it, so an attribute both cover shows two
  citations. GtoPdb has **no pre/post-synaptic field**, so `synaptic` is out of its reach.

**Descriptions** are not a node kind (not tallied). Drugs, structures and non-receptor targets carry
**no baked description**: their panel fetches the **current Wikipedia lead** (CC BY-SA) at runtime via
`liveWikiDescription` over `js/wiki.js` `fetchWikiLead(url, lang)` (locale lead, English fallback), so
the dataset ships no copyrighted prose (a panel whose live lead fails shows none). Receptors + projection
groups carry a short **authored** `description` as the offline fallback, overridden best-effort by the
live lead. Needs the `connect-src https://*.wikipedia.org` CSP allowance.

**The live-Wikipedia source link (green, viewer-only).** A live-fetched lead shows its provenance as the
**Wikipedia link itself**, relocated (by `liveWikiDescription`) to the end of the description in place of a
grade pill and styled as a green pill-link (`.wiki-src`, reusing `.src-prov-wikipedia`): a live fetch is a
verbatim programmatic read that cannot drift, so it earns the green tier, and the link (not a cryptic ✓)
makes plain the text is *from* Wikipedia and clicks through to it. `appendWiki` stashes the reference link
as `wrap._refLink`; on a successful fetch it moves up and the emptied reference row is dropped (any lookup
links stay). It is a **presentation**, **not** a stored grade and **not** tallied; the green ✓
`PROVENANCE_PILLS.wikipedia` pill (`info.provWikipedia`) remains only as a fallback if the link can't be
moved. Asymmetry: a **baked** Wikipedia snapshot stays yellow `sourced` (a stored copy *can* drift); only
the **live** read earns the green link. When the live fetch fails, the baked description keeps its stored
pill and the reference link stays in its own row; a missing link shows `NOSOURCE`.

**The "% sourced" figure.** `_provenance_stats` reduces every node + reference to its strongest grade and
buckets it into **verified** (quote-checked) / **uncertain** (quote-checked, but its `uncertainty[]`
bullets say the quote does not attribute the claim) / **sourced** (from a document) / **missing** (no
document). A bare `llm` grade *is* missing (an LLM asserting from memory has no document), so it buckets
with a sourceless node (the viewer still shows them differently, grey `?` vs orange `NOSOURCE`).
`uncertain` counts as **backed** (a real document exists), so flagging a claim leaves `pct_backed`
untouched and only moves the node out of the green count. It tallies per
node kind (drug bindings, NbN, drug class, projections, circuits, projection groups, receptor/target
classifications, receptor/target expression regions, region anatomy, wikipedia references), plus a
headline `pct_backed` over the **knowledge nodes** (references excluded, a reference points *at* a node).
The `references` kind stays in `by_kind` but the viewer does **not** render it as a coverage bar (a
reference is not a knowledge node, and every present link defaults to `sourced`, so the bar was uniformly
yellow noise); it is emitted as `meta.provenance_stats` (key `nodes`). Each expression region is its own node, individually
upgradeable. **The live per-kind figures live in the README `SOURCING_STATS` block (auto-written by
`update_readme_stats.py`, CI runs it `--check`) and the Sources & provenance popup; they are not repeated
here, to avoid drift.** `check_data.py` re-confirms the tally is self-consistent (coverage columns M/S/S+V).
Separately, `meta.provenance_stats.ki_coverage` tracks **measured-affinity (PDSP Ki) coverage** (bindings
with a Ki, drugs with none; combos excluded): NOT a grade (a quote-only binding is still sourced), but the
honest complement surfacing where a measured affinity was never looked up. Rendered in the sourcing popup +
README block, warned per-drug by `check_data.py` family 7.

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
panel header + the loading overlay's title (`js/main.js` fills every `[data-app-version]`
slot, so a new display spot is markup-only) + the WIP banner (which reads the global
directly). Follow [semver](https://semver.org/);
to release, bump `version.js` **and write that version's changelog** (below). It is
intentionally not derived from git (the site deploys as plain files).

> [!IMPORTANT]
> **Every code change ships a version bump: patch at the very least.** A fix, a
> refactor, a doc-only touch to shipped code: bump the patch and write the changelog
> entry for it. The version is what a visitor's browser compares against to decide
> whether to show them anything new, so an unbumped change is invisible to them and
> indistinguishable from the previous build. Reserve minor/major for what semver says.

### Changelog ("What's new")

Release notes for casual visitors, one file per version: `docs/changelog/<major.minor.patch>/
changelog.md`, a required `# <version> (YYYY-MM-DD)` title (the release **date** has nowhere
else to live, the emit being a file read with no git history to date a version from; the
version doubles as a copy-paste check against the directory) then `## <Category>` sections
(closed vocabulary `CATEGORIES` in `tools/data_generators/changelog.py`) of
`- bullet (sha, sha)` lines, each with an indented `fr:` line (required, like every display
string). `docs/` is not web-exposed, so `generate_data.py` emits them newest-first to
`public/data/changelog.json`.
`js/changelog.js` `createChangelog()` fetches that **only when its popup opens**, and
`showIfUnseen()` shows every release after the version in `localStorage`
`neurarium.changelogSeen` (a first-ever visitor is silently marked current: they get the
tour instead). What it records there is the newest release **the notes carry**, never the
running build, and a failed fetch records nothing: `changelog.json` and `version.js` are
emitted separately, so marking the build would burn a release whose notes had not landed
yet and it would never be shown. Shown with a **Show all release notes** button under them (rendered only while the
view is a subset, so the rest of the history is a click away rather than a wall to scroll).
Also reachable from the About popup's "What's new" link, which opens the full history;
scrolls via the shared `.modal` rule. Each version heading carries its date, formatted in
the reader's locale (read from `documentElement.lang` at render time, so an EN/FR switch
follows). A commit sha links to `<sourceUrl>/commit/<sha>` only when
`sourceUrl` points *into* a repository (same rule as the About "open an issue" link, so
no repo/username is hardcoded); otherwise it renders as plain text.
`check_data.py` family 9 fails if `version.js` has no changelog directory.

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
