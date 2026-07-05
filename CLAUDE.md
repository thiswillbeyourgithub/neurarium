# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository. This file is a
**map**, not a manual: it says what exists, where it lives, and the non-obvious
rules, so you can find the code, not re-read it in prose.

> [!IMPORTANT]
> **Keep this file current AND terse.** When you add a feature, control, data
> field, or file, update the relevant line here in the same change. Format
> contract, to stop it ballooning again:
> - One line per feature/file/control. Name the symbol/file; don't narrate the code.
> - State the *current* behavior only. Never write the history of a decision you
>   reversed ("used to", "the old X", "earlier this was", "no longer"). Just
>   describe what is true now; delete what is not.
> - Give a rationale only when it is non-obvious (a "why" a reader would
>   otherwise get wrong). Skip the obvious why.
> - State each behavior once; cross-reference with "(see X)" instead of repeating.
> - Deeper narrative (diagrams, module graph, boot sequence) lives in
>   [`ARCHITECTURE.md`](ARCHITECTURE.md).

## What this is

A browser-based 3D brain visualizer built on [three.js](https://threejs.org/),
built with the help of Claude Code. It shows brain regions (cortical lobes, deep
nuclei, diencephalon, limbic, hindbrain, neuromodulatory source nuclei) as
procedurally shaped meshes and draws arrows for neuron projections between them.
On top of the anatomy it carries datasets of neurotransmitter **receptors**,
psychiatric **drugs** (from Stahl's Prescriber's Guide), named **circuits**, and
**projection groups**. Focusing a receptor/target dims the brain and scatters
glowing "gem" dots over the regions carrying it; focusing a drug does the same in
effect colours (boost/block/modulate) plus a by-mechanism flow overlay, so you
can see what a drug does to the brain.

At explode 0 the regions lock together into a whole brain (lobes tile a hemisphere
with a flat medial wall at the longitudinal fissure); the explode slider blows
them radially apart to reveal the deep nuclei. On load the regions start blown out
and assemble. The view rotates/zooms, auto-rotates, explodes, and goes transparent.

Region `group` values (`lobe`, `basal_ganglia`, `diencephalon`, `limbic`,
`hindbrain`, `brainstem_nuclei` for the source nuclei raphe / locus coeruleus /
VTA) drive the legend headings + ordering via `GROUP_LABELS` in
`tools/generate_data.py` (emitted into `meta.json`, read by the viewer). Adding a
group means adding it there or its structures drop from the legend.

Coordinate convention (arbitrary units, brain centered on origin): `x` left(-)/
right(+), `y` down(-)/up(+), `z` posterior(-)/anterior(+).

## Nodes (the sourceable-datum model)

The organizing concept of the whole project: **a *node* is any sourceable datum**,
one atom of knowledge about the brain that could, in principle, be attributed to a
source. The dataset is a **graph of nodes**; a detail panel is a view of one node
plus every node linked to it (a receptor node links to the region nodes expressing
it and the drug nodes acting on it, etc.). New features should think in nodes: if you
add a datum, it is a node, and **every node must be sourceable** (see Source
provenance) so the coverage tally stays honest.

> [!IMPORTANT]
> "Node" is the umbrella term. The per-kind names (structure, projection, circuit,
> receptor, drug, binding, target, ...) are **node kinds**, and they keep their names
> in the data files + code (a `structures.jsonl`, a `showReceptor`, ...): the kinds
> are distinct and renaming the collections to "node" would erase the distinction the
> graph needs. So: umbrella = node; specific = its kind.

**Node kinds and where each lives** (the emitted collection -> the sourcing-tally kind
in `meta.provenance_stats.by_kind`):
- brain region -> `structures.jsonl` -> `structures`
- projection (pathway) -> `projections.jsonl` -> `projections`
- functional circuit -> `circuits.jsonl` -> `circuits`
- projection group -> `projection_groups.jsonl` -> `projection_groups`
- receptor classification -> `receptors.jsonl` -> `receptors`
- receptor *expression region* -> a receptor's `location_sources` -> `receptor_locations`
- non-receptor drug target -> `meta.drug_targets` -> `targets`
- target *expression region* -> a target's `location_sources` -> `target_locations`
- drug binding -> a drug's `bindings[]` -> `drug_bindings`
- drug NbN label -> a drug's `nbn` -> `drug_nbn`
- drug class classification -> a drug's `categories` (+ `category_provenance`) -> `drug_categories`
- Wikipedia reference -> any node's `wikipedia` -> `references` (a pointer *at* a node,
  tallied but excluded from the headline; a reference is not itself a knowledge node)

**The node sourcing contract.** Every node carries a provenance **grade**
(`PROVENANCE_LEVELS`: `llm` < `sourced` < `verified`) and, ideally, a **source**. There
is one source shape everywhere: a quote-level `{corpus, page, quote, provenance}`
against a `SOURCE_CORPORA` corpus (drug bindings, NbN, projection/circuit/group quotes,
receptor/target classifications + locations, region anatomy). A node with no source is
counted **missing** (its pill reads `NOSOURCE`; see The tally). `meta.provenance_stats`
(emitted by `_provenance_stats`, key `nodes`) reduces every node to its strongest grade
and counts them; the headline % is over the knowledge nodes (references excluded). Full
mechanics in Source provenance.

## Architecture

Anatomy is plain data, separate from rendering, so the project can grow without
touching the viewer. Most regions are symmetric L/R pairs: a region is defined
once on the right in `generate_data.py` and mirrored, avoiding per-side
duplication. Generated files are committed so the static site fetches them directly.

**Project layout.** Everything the browser loads is under `public/` (the served
site). That directory is the *only* thing web-exposed: Caddy's `/srv` and
`tools/serve.py` both root there, so `docker/`, `tools/`, `.git` and the
uncommitted `.env` / `deploy.sh` / `CLAUDE.local.md` are never web-reachable.
Authoring + dev tooling live in `tools/`, deployment config in `docker/`, the
README hero shot in `docs/`.

### File map

Data + authoring (`tools/`):

- `generate_data.py` — single source of truth for the anatomy (stdlib-only, offline):
  defines every region/projection/receptor once, emits the artifacts below. Drugs are the
  exception (authored in `tools/drugs_data.json`, read by `_load_drugs`). Display strings are
  `{en,fr}` via `_t()` (see I18n).
- `tools/drugs_data.json` — the authored drug dataset (from Stahl 8th ed.), read by
  `_load_drugs`, emitted to `data/drugs.jsonl`. Edit to add/change a drug.
- `tools/check_data.py` — stdlib integrity checker over emitted `public/data/` (see Data checks).
- `tools/serve.py` — stdlib dev server, `Cache-Control: no-store`, roots at `public/` (see Running).
- `tools/shot.py` — Playwright screenshot helper (see Screenshots).
- `tools/demos/` — Playwright demo-video recorder: `recorder.py` (a `Demo` API) + `neurarium.py`
  (the showcase tour, writes the README hero `docs/preview.gif`). Needs ffmpeg+gifski+GPU; see
  `tools/demos/README.md`.
- `tools/build_source_worklist.py` — lists not-yet-sourced drug bindings with Stahl page ranges
  (input to the source-extraction workflow; resumable).
- `tools/apply_source_quotes.py` — applies the extraction workflow's accepted quotes onto
  bindings (re-finds the quote in the page range; idempotent).
- `tools/apply_nbn_sources.py` — sources each drug's NbN line (greps Stahl's verbatim line,
  substring-confirms, no judge); falls back to the drug **Class** line (`nbn_nonstandard`) for a
  newer drug with no NbN line. Idempotent.
- `tools/apply_category_sources.py` — sources each drug's class classification (`drug_categories`)
  from an extract/judge results file (a judge is needed: our coarse `categories` re-map Stahl's
  free-text class line, unlike the fixed NbN field). Idempotent.
- `tools/fetch_gtopdb.py` — fetches receptor tissue-distribution comments from the Guide to
  Pharmacology API (corpus #7 `gtopdb`), the source for **receptor expression regions**;
  `RECEPTOR_GENES` maps receptor->gene->targetId. Caches `sources/gtopdb/` + `worklist.json`
  (each quote carries assay species). See Expression locations.
- `tools/fetch_allen.py` — fetches the Allen Human Brain Atlas microarray (corpus #8
  `allen_ahba`), the source for **target expression regions** + the receptor regions GtoPdb
  misses; a PACall detection-boolean vote per (gene, region), no judge. `TARGET_GENES` +
  `fetch_gtopdb.RECEPTOR_GENES` map owners to genes. Caches `sources/allen/` + `confirmed.json`.
  See Expression locations.
- `tools/apply_location_sources.py` — merges accepted expression quotes into
  `tools/location_sources.json`, `--corpus {gtopdb,allen}` (gtopdb needs a judged file; allen is
  deterministic). Idempotent. See Expression locations.
- `tools/location_sources.json` — machine-written bulk location sources, loaded by
  `generate_data.py` into `RECEPTOR_LOCATION_SOURCES` / `TARGET_LOCATION_SOURCES`. Not served.
- `tools/fetch_ki.py` — parses the PDSP Ki CSV (`sources/books/pdsp_ki/`, author-side) into
  per-drug binding affinities; `--apply` writes each `ki` + adds median-stronger `affinity_only`
  bindings. A curated `ALIAS` map recovers drugs PDSP lists under a related compound. See Drugs.
- `tools/pdf_to_pages.py` — splits a PDF into one `<page>.md` per page (the quote-gate text);
  `uv run`, `--layout` for OCR.
- `tools/build_toc_index.py` — `INDEX.md` from a PDF's embedded TOC (generic). `uv run`.
- `tools/build_index.py` — Stahl-specific page index (by `THERAPEUTICS` heading). `uv run`.
- `tools/update_readme_stats.py` — rewrites the README `SOURCING_STATS` + `SOURCES_TABLE` blocks
  (and the headline %) from `meta`; `--check` exits 1 if stale (CI). Idempotent.
- `tools/fetch_molecules.py` — downloads each drug's molecule SVG into `public/data/molecules/`;
  writes `tools/molecules_sources.json`. See Images.
- `tools/fetch_structure_images.py` — resolves the *url* of each structure's (and wiki-linked
  circuit's) Wikipedia hero + gallery images into `tools/{structure,circuit}_images_sources.json`
  (`--target structures|circuits|all`); downloads no bytes. See Images.
- `tools/{molecules,structure_images,circuit_images}_sources.json` — provenance/attribution for
  the fetch tools (the image ones are read by `generate_data.py` offline; not served).
- `tools/git-hooks/` — repo-tracked git hooks (see Git hooks).

Emitted data (`public/data/`):

- `meta.json` — presentation maps + tallies, so the dataset is self-describing (a port needs
  no hardcoded palette): `projection_colors`, `kind_labels`, `group_labels`, `kind_signs`,
  `sign_colors`, `sign_labels`, `system_flow_kinds` (drug target system -> projection kind),
  the receptor maps (`receptor_family_labels` key order = legend family order,
  `receptor_class_labels`, `synaptic_labels`), the drug maps (`drug_category_labels` key order =
  Drugs legend order, `drug_actions` action->{label,effect}, `drug_effect_colors`,
  `drug_effect_labels`, `drug_targets` = every non-receptor target + every receptor id),
  `target_type_labels`/`target_type_colors`, `source_corpora`, `provenance_stats` (the sourcing
  tally; see Source provenance).
- `structures.jsonl` — `id`, `name{en,fr}`, `base_name{en,fr}` (hemisphere-stripped, legend
  row), `group`, `position`, `color`, `shape_file`, `classification_provenance`, optional
  `wikipedia`(+`_provenance`), optional `structure_image` (hot-linked Wikimedia url, shared by
  both hemispheres) + `structure_image_gallery`.
- `projections.jsonl` — `from`, `to`, `kind`, `label{en,fr}`, `neurotransmitter{en,fr}`,
  `description{en,fr}`, optional `sources[{corpus,page,quote,provenance}]` (from `KANDEL_QUOTES`),
  `bidirectional`, `tentative` (dotted, off-by-default section).
- `circuits.jsonl` — `id`, `name{en,fr}`, `structures[ids]` (arrows derived in the viewer),
  optional `description{en,fr}` + `sources` + `wikipedia`(+prov) + `structure_image` (+ gallery);
  same shape + rendering as a structure's.
- `projection_groups.jsonl` — a legend pathway row promoted to a sourced structure so it opens a
  panel: `id` (`<mode>_<key>`), `mode` (kind|sign), `key`, `name{en,fr}`, `description{en,fr}`,
  `classification_provenance`, optional `wikipedia`(+prov) + `sources`. One record per group in
  BOTH colour modes (7 per-transmitter + 3 per-sign); member pathways derived in the viewer.
- `receptors.jsonl` — `id`, `name`, `family`, `neurotransmitter{en,fr}`, `receptor_class`
  (ionotropic/metabotropic/chaperone), `sign` (excit/inhib/modulatory), `synaptic`
  (pre/post/both), `locations` (structure *base* ids, both hemispheres), optional
  `ubiquitous:true`, `classification_provenance` (mechanism grade only), optional
  `location_sources` (`{base:[quote-source]}`, sparse per-region upgrade above `llm`; `"ALL"` =
  the ubiquitous claim), optional `description{en,fr}` + `wikipedia`(+prov). Empty locations + no
  description = a deliberate stub (listed, not focusable).
- `drugs.jsonl` — `id`, `name`, `categories`, `category_provenance` (+ optional
  `category_sources`), optional `nbn{en,fr}` (+ `nbn_sources`, + `nbn_nonstandard:true` when the
  value is Stahl's class descriptor not a formal NbN), `bindings[]` (each: `target`, `action`,
  optional `effect`/`note{en,fr}`/`tentative`/`sources[{corpus,page,quote,provenance}]`/`ki`
  (measured PDSP affinity)/`affinity_only:true` (Ki but no known direction, panel-only)),
  optional `wikipedia`(+prov), optional `structure_image` (vendored `data/molecules/<id>.svg`,
  only when the file exists), `focusable`. No drug-level source: provenance is per-claim (see
  Source provenance).
- `molecules/<id>.svg` — vendored per-drug structure diagrams (`fetch_molecules.py`). Structure
  illustrations are NOT vendored (hot-linked, see Images).

Geometry (`data/shapes/<name>.json`): one file per distinct *form*. L/R pairs
share a single right-side file; the left member sets `mirror:true` on its
structure record and the viewer reflects it across x. Three types:
- `blob` `{radii, seed, detail, noise, + optional octaves/ridged/frequency/aniso/
  clip/clip_planes}` — a gradient-noise-deformed ellipsoid.
- `curve` `{points, profile, seed, noise, radial/tubular_segments}` — a
  round-capped tapered tube swept along a spline (caudate; brainstem levels
  midbrain/pons/medulla).
- `composite` `{parts:[...]}` — sub-shapes (each optional offset/scale/rotate)
  merged into one mesh (cerebellum = 2 hemispheres + vermis).

> [!NOTE]
> An ongoing effort under `geometry_refinements/` (its own `CLAUDE.md` +
> `STATUS.md`, auto-loaded only when working there) is replacing these procedural
> shapes with a self-authored SDF atlas, one structure at a time. It adds an `sdf`
> shape type alongside the above. Before editing `data/shapes/*` or `shapes.js`
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
- `js/app-init.js` — injects the umami tag if configured; no-op otherwise.
- `js/i18n.js` — internationalization (classic script, loaded early). See I18n.
- `js/dev-banner.js` — when `DEV=1`, shows the WIP banner. See Dev banner.
- `js/error-banner.js` — surfaces failures as red dismissible banners. See Error banners.
- `js/loading.js` — `createLoadingScreen()` drives the startup `#loading` progress
  overlay. See Loading overlay.
- `version.js` — `window.__APP_VERSION__`, the single app-version source. See Versioning.

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

The data is loaded with `fetch()`, so serve over HTTP (`file://` fails CORS). The
served site is `public/`. From the repo root:

```
python tools/serve.py        # http://localhost:8000/ (recommended)
# or: cd public && python -m http.server 8000
```

Prefer `tools/serve.py`: it sends `Cache-Control: no-store`, so the browser
refetches every ES module each reload. Plain `http.server` lets browsers heuristic-
cache JS modules, which can serve a stale `js/*.js` and cause baffling mismatch
crashes; if you see one after editing JS, hard-reload (Ctrl/Cmd+Shift+R) or use `serve.py`.

Debugging: [eruda](https://github.com/liriliri/eruda) on-screen console, **gated**
on `?debug=1` exactly (normal visitors never download it), vendored same-origin at
`public/vendor/eruda/eruda.js`, pinned top-right. Runtime errors otherwise surface
via the red error banners.

### Screenshots & deep-link view params

`tools/shot.py` (Playwright) renders the page to a PNG: serves `public/` with
`tools/serve.py`, drives headless Chromium (SwiftShader GL flags baked in, so
WebGL renders without a display), captures the canvas. Bare run writes
`docs/screenshot.png` (a static still). The README's animated hero is `docs/preview.gif`,
recorded by `tools/demos/neurarium.py` (see the `tools/demos/` entry above).

```
python tools/shot.py
python tools/shot.py --params "explode=0.5&view=iso" --out /tmp/brain.png
python tools/shot.py --params "only=putamen_R&view=iso" --out /tmp/putamen.png
```

Needs `playwright` + `playwright install chromium` once (or `uv run tools/shot.py`,
inline deps). `--headed` opens a real window; `--wait` ms before capture (default 6000).

The `--params` string is the URL query parsed by `applyViewParams` in
`js/main.js`, so the keys also work as deep links:

| key | effect |
| --- | --- |
| `only=id[,id2]` | show only these structure ids (others + arrows hidden) |
| `view=front\|back\|left\|right\|top\|bottom\|iso` | frame the visible meshes |
| `explode=0..1` | blow-out amount (also moves the slider) |
| `transparency=0..1` | material opacity |
| `names=all` | show every label |
| `autorotate=1` | spin (deep links default auto-rotate off; this forces it on) |
| `ui=0` | hide the panels + legend (clean shape shots) |

`only`/`view` auto-fit the camera to whatever is visible.

## Deployment

A hardened Caddy container (`docker/docker-compose.yml`): non-root UID 1000,
`cap_drop: ALL`, `no-new-privileges`, read-only rootfs (writable paths via
`size=`-capped tmpfs), CPU + memory + `pids` limits (all under
`deploy.resources.limits` so `pids` isn't double-defined, which compose rejects),
`mem_swappiness: 0`, rotated `json-file` logging. Listens `:8359`, published
`127.0.0.1:8359` so a host reverse proxy terminates TLS in front. The image is a
thin build on `caddy:2-alpine` (`docker/Dockerfile`) that strips the binary's
`cap_net_bind_service` (else `exec` fails under `no-new-privileges`); `public/` is
bind-mounted read-only at `/srv`. The actual deploy procedure is in `CLAUDE.local.md`.

## Git hooks

Shipped under `tools/git-hooks/` (tracked = single source of truth), activated
per-clone once: `git config core.hooksPath tools/git-hooks` (not committed; every
fresh clone runs it). Current:

- `pre-push`: refuses any ref but `main`. On `main`, prompts on the terminal
  (`y/N`, via `/dev/tty`) to run `tools/check_data.py`; a check that reports
  **errors** aborts the push (warnings pass). A non-interactive push skips the prompt.

## Data checks

`tools/check_data.py` (stdlib) runs over the **emitted** `public/data/`,
independent of `generate_data.py`. Exit 0 = no errors (warnings allowed), 1 =
errors. Functions take loaded data as args (unit-testable). Six families:

- **Duplicates** (per collection + projections by `from -> to`): exact or
  normalized id/key collision = error (`normalize_for_match` lowercases + strips
  non-alphanumerics, so `mao_a`/`mao-a` collide); normalized display-name collision
  = warning.
- **Reachability**: every cross-reference must resolve (drug binding `target`,
  projection endpoints/kind, circuit/receptor/target structure refs, projection-
  group `kind`/`sign` key, receptor classification keys, target type + region bases,
  every receptor also a `drug_targets` key). The region-base check is what
  guarantees the panels' "Found in" rows are clickable. Dangling refs = error.
- **TODOs** (provenance-aware): a literal `"TODO"` outside a source url, or a
  focusable target with no `wikipedia`, = warning. A source *url* left `"TODO"` is
  `[ok]` for an `llm` citation (expected) but **warned** if the source claims a
  higher grade. TODOs never fail the run.
- **Provenance grades**: every `provenance` (incl. per-binding sources, `nbn_sources`,
  circuit + projection-group sources), every `classification_provenance`, every
  `wikipedia_provenance` must be a known grade (`llm`/`sourced`/`verified`) or
  error. Re-confirms `meta.provenance_stats` is self-consistent (per-kind sums,
  totals, recomputed `pct_backed`) or error.
- **Source quotes** (the heart of sourcing): each quote-level drug source
  (`{corpus,page,quote,provenance}`): `corpus` must resolve to `meta.source_corpora`,
  a `verified` source must carry page + quote, and the normalized quote must be an
  exact substring of the normalized cited page text. Page material is author-side
  (see CLAUDE.local.md); the quote check is skipped + warned on a clone without it.
  A quote not on its page = error (the gate that keeps the LLM extraction honest).
  Also checks each binding's `ki`: its source corpus resolves, an `affinity_only`
  binding carries a `ki`, and (author-side, skipped on a clone) the cited `ki_id` row
  is really in the corpus CSV with that value (the PDSP analogue of the quote gate).
- **Structure connectivity** (warns, never errors): isolated / inward-only /
  outward-only structures from the projection endpoints (`bidirectional` counts
  both ways). Source nuclei + olfactory bulb are expected outward-only, pituitary
  inward-only; the point is to flag a region wired one-way (e.g. a missing return pathway).

## Internationalization (i18n)

English / French, no build step; `js/i18n.js` (classic script, loaded early) is the
whole mechanism.

- **Two string sources.** *UI* strings live in the message catalogue inside
  `js/i18n.js` (one object per language). *Data* strings (region/pathway/circuit
  names, descriptions, neurotransmitters, the group/kind/sign/receptor labels) are
  `{en,fr}` objects authored in `generate_data.py` and resolved by `js/data.js`.
- **Generator side.** Anatomy is authored in English; a single `FR` table
  (English -> French) is the French source, and `_t("English")` wraps any display
  string into `{en, fr}`. A string with no `FR` entry makes `build_records` raise
  listing every missing one, so it can't ship half-translated. Per-hemisphere names
  are composed by `_side_name` (Right/Left, and gender/number-agreed French tuned by
  an optional `fr_gender` of `m`/`f`/`mp`/`fp`), not stored; each record also carries
  a hemisphere-stripped `base_name`.
- **Language pick.** `detectLang()`: `?lang=en|fr` (persisted to localStorage) >
  saved choice > browser locale `fr*` > English. `window.__I18N__` exposes `lang`,
  `t(key, vars)` (UI, `{token}` interpolation, falls back to English then the key),
  `pick(field)` (collapse an `{en,fr}` field; plain string passes through), `setLang`.
- **Static markup** in `index.html` carries `data-i18n` (textContent),
  `data-i18n-html` (innerHTML), `data-i18n-attr="attr:key,..."`, filled at
  `DOMContentLoaded`; dynamic UI calls `t()` directly. `setLang` saves the choice and
  reloads (data is resolved at load), and writes `<html lang>`. The `#lang-switch`
  (EN/FR) is pinned at the top of the panel body.

> [!IMPORTANT]
> Any new user-visible string goes in **both** language tables in `js/i18n.js` (UI)
> or as an `{en, fr}` object in `generate_data.py` (data). Source citations + URLs
> are intentionally not translated.

## Analytics (umami)

Optional, privacy-friendly. Because this is a no-build static site on a read-only
rootfs, config is injected at runtime:

1. Set `ANALYTICS_URL`, `ANALYTICS_WEBSITE_ID`, optional `ANALYTICS_SRI`,
   `ANALYTICS_DNT` (umami `data-do-not-track`, default `"true"`) in `docker/.env`.
2. `docker/entrypoint.sh` renders `/gen/app-config.js` from those vars at start;
   Caddy serves it for `/app-config.js`.
3. `js/app-init.js` reads `window.__APP_CONFIG__` and injects the umami `<script>`
   (with SRI/crossorigin + explicit `data-do-not-track`).

Client-facing names are generic (`app-config.js`, `js/app-init.js`,
`__APP_CONFIG__`) because a path containing "analytics" is blocked by many content
filters/proxies. Leave the URL/ID empty to fully disable. `ANALYTICS_URL` must be
the tracker *script* URL (used as a `<script src>`); the container validates at
startup that it is reachable and serves JavaScript, else it crashes (so a
misconfiguration is loud, not silently tracking nothing).

## Content-Security-Policy

Caddy sends a CSP + `X-Content-Type-Options`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer` on every response (`docker/Caddyfile`).
`default-src 'self'` with `object-src`/`base-uri`/`frame-ancestors`/`form-action`
locked. three.js + eruda are vendored same-origin, so `script-src` needs no CDN.
Relaxations:

- `font-src 'self' data:` — eruda's embedded icon font.
- the umami origin in `script-src` + `connect-src` when configured (entrypoint
  derives `ANALYTICS_ORIGIN`, the Caddyfile interpolates `{$ANALYTICS_ORIGIN:}`).
- `https://*.wikipedia.org` in `connect-src` — info panels fetch the current
  Wikipedia lead (`js/wiki.js`).
- `https://upload.wikimedia.org` in `img-src` — the structure panel hot-links each
  region's illustration. (`img-src` also allows `data:`.)

`script-src`/`style-src` include `'unsafe-inline'` (no-build site: inline importmap,
eruda gate, inline `<style>`). CSP is emitted only by Caddy, not `serve.py`.

> [!IMPORTANT]
> A new external resource (CDN script, remote font, iframe, image host, cross-origin
> fetch) needs the matching CSP directive extended in `docker/Caddyfile`.

## Dev / WIP banner

Optional "work in progress" top banner, same runtime-injection plumbing as
analytics. `DEV` in `docker/.env` (default 0); `entrypoint.sh` stamps
`STARTED_AT=$(date +%s)` and renders both into `/gen/app-config.js`.
`js/dev-banner.js` reveals `#dev-banner` (amber, in `#banners`) when `dev === "1"`
and computes "X ago" from `startedAt` (refreshed per minute). Clicking dismisses it
for the current view only (not persisted, so a reload brings it back). It ends with
a **Source** link to `cfg.sourceUrl` (`SOURCE_URL` env, default the public site;
only `http(s)`; clicking the link navigates instead of dismissing). The repo URL is
not hardcoded in committed source.

## Error banners

So a visitor never opens eruda to learn why something broke, failures surface as
red dismissible banners in `#banners` (`js/error-banner.js`): installs `window`
`error` (capture phase, so failed resource loads count) + `unhandledrejection`
handlers (with `file:line` for script errors); exposes `window.showErrorBanner(msg)`
(used by `js/main.js` for the data-load failure). A failed resource whose element
carries `data-optional` is skipped (no banner): a panel's molecule / Wikipedia
illustration self-handles a failed load by dropping its own figure, and an absent
optional image is not an app error to shout about. Banners stack; each has a ×;
identical messages dedupe into one `(×N)`; a `MAX_BANNERS` cap. A `ResizeObserver`
republishes the stack height to `--banners-height`, which `#status` offsets against.

## Loading overlay

A startup progress overlay so a slow first load shows feedback instead of a blank
canvas. `#loading` (static markup in `index.html`, **visible by default** so it paints
before any ES module parses) covers the canvas above every panel/banner; `js/loading.js`
`createLoadingScreen()` exposes `setProgress(frac, label)` (monotone: the bar only ever
moves forward), `done()` (fill to 100%, fade out via the `.loaded` opacity transition,
then detach) and `fail()` (detach at once so an error banner takes over). `js/main.js`
drives it: the data fetch fills the first half (`loadBrainData`'s `onProgress` fires per
shape file), SDF meshing the back half (`sdf-pool` `meshAll`'s per-item `onItem`,
captioned with each region's name), then `done()` fades it out as the assemble intro
begins. i18n keys `loading.*`.

**Startup sourcing gate.** Immediately (before the data load), `main()` shows the
**Sources & provenance** popup (`#sourcing-modal`) over the still-visible `#loading`
overlay (it sits above via a higher `z-index`, 80 > `#loading`'s 70), so a visitor reads
how the data is sourced while it loads and closes it to reach the app (still loading
behind it, or already up). Skipped for the `?ui=0` clean-shot mode. Its static intro +
grade key render at once (`buildAboutSourcing(null)`); the coverage tally fills once the
dataset loads.

## Controls

One collapsible **"neurarium" panel bottom-left** (`#controls`; `#controls-toggle` collapses the
body). The body splits into `#settings-pane` and `#details-pane` (`#info-body`), switched by the
`#panel-tabs` bar: a pinned **Settings** tab (`#tab-settings`) + one closable tab per opened
detail in `#detail-tabs` (see Detail tabs + Info panel). The settings pane holds, pinned at top,
the `#lang-switch` (EN/FR) + a keyboard-shortcuts / reset / search / legend / sources / about
`.toolbar-row`, then:

- **Controls** (`#controls-settings`): the **Separate** + **Transparency** sliders, the
  **Auto-rotate** / **Show all names** / **Show projections** / **See inside** checkboxes, and the
  **arrow colour-mode** switch (`#color-mode`). Ships open; toggles independently of the accordion.
- Four **single-open-accordion** sections (opening one closes the others): **Structures**
  (`#structures`), **Projections** (`#projections`, "Projections & Circuits"), **Receptors &
  targets** (`#receptors`), **Drugs** (`#drugs`, with `#drugs-filter`).
- Three **toolbar-icon popups** (all `.modal-overlay`, via `wireModal`): **Legend**
  (`#legend-modal`), **Sources & provenance** (`#sourcing-modal`), **About** (`#about-modal`).

The accordion is a list of `{toggle, body}` in `wireControls`; `wireCollapse(onToggle)` +
`setSection()` drive it. Searching swaps `#search` in for `#controls-main`.

**Pan-aside.** While expanded, the brain is pushed clear of the panel (`updatePanelPan` ->
`focus.setScreenOffset` -> `PerspectiveCamera.setViewOffset`, eased in `focus.tick`; gated on the
panel being visible so `?ui=0` is unaffected). Portrait: full-width bottom-half panel, brain up.
Landscape: left sidebar, brain right.

**Scroll model.** The panel is an `overflow:hidden` flex column that never scrolls; its top chrome
is pinned and exactly one inner region scrolls (`#controls-main`, or `#details-pane`/`#search`). A
`min-height:0` flex chain gives an open section its natural height with the list scrolling.

### Settings & toggles

- **Auto-rotate** (OrbitControls `autoRotate`, on by default): off the moment the user picks
  content (`selection.onPick(stopAutoRotate)`); `?autorotate=1` forces on.
- **Show all names** (`#toggle-names`, off): every label on. Key **n**; `?names=all`.
- **Show projections** (`#toggle-projections`, on): unchecking hides every arrow (`projVis`;
  composes with the Hypothetical toggle).
- **See inside** (`#see-inside`, off): `createNearCull` recomputes each frame the structures on
  the camera-facing side (centre > `NEAR_CULL_BIAS` past the centre plane) and hides them so deep
  nuclei show; snapshots visibility to restore; composes with `?only=`; arrows stay. `cull.tick()`
  runs after `controls.update()`.
- **Animations** (`#toggle-animations`, `animSettings.enabled`): the decorative motion (intro,
  gem-dot twinkle, drug wash, circuit pulse). Default on for a fine pointer, off for coarse /
  reduced-motion; persisted. Off is *content-preserving*: focus still lights regions/arrows + shows
  a static gem field, just frozen (intro skipped, `tick()`s to a still frame, `play` no-ops).
- **Arrow colour-mode** (`#color-mode`, default Neurotransmitter): Neurotransmitter =
  `projection.color` per molecule; Potential = `projection.signColor` by coarse sign (from meta
  `signColors`/`signLabels`). `setColorMode` recolours in place + rebuilds the Projections section
  (per sign vs per transmitter). The switch lives outside `#projections-body` so rebuilds never
  touch it.
- **Separate** slider (0..1 explode): pushes regions radially out (`EXPLODE_STRENGTH`); the camera
  auto-zooms to keep a constant apparent size (`focus.zoomForExplode` off `boundingRadiusAt`).
- **Auto-spread** (`createAutoSpread`): focusing a **deep** (non-lobe) node from search / a panel
  animates Separate to full (`autoSpreadIfDeep` -> `spreadTo(1)`) so it isn't buried; only ever
  raises the spread; a manual slider grab cancels; a plain 3D click doesn't trigger it.
- **Intro** (`createIntroAnimation`): on load the regions assemble from blown-out (Separate 1->0)
  while the camera follows + sweeps `INTRO_ROTATION_TURNS`. Drives the slider; suspends/restores
  auto-rotate; cancelled on a slider grab; skipped when `?explode=` is pinned. Under the dev banner
  the brain settles lower/further back (`DEV_BANNER_DROP`/`_UNZOOM`).
- **Transparency** slider = material opacity (depth-write off while translucent). Owned by the
  selection controller, so it composes with isolate dimming.

### Selection / halo + isolate (`createSelection`)

Single source of truth for what is highlighted/focused.
- Plain 3D click/tap halos a structure (`mesh.userData.halo`) or arrow (`ProjectionArrow.setHalo`);
  double-click isolates. From **search or a detail panel** a pick isolates instead
  (`selectStructure({isolate:true})` dims the rest + pins the L/R pair;
  `selectConnection({isolate:true})` pins the arrow + endpoints). Structure + arrow halos are
  mutually exclusive.
- A **Structures legend row** toggles that structure (both hemispheres) into the isolate set +
  opens its tab (on isolate-on only); a **category heading** toggles the group. While the set is
  non-empty others drop to `DIM`, untouched arrows fade (`setOpacity`), the legend greys non-
  isolated rows. Additive.
- A **Circuits** row isolates that circuit (`selection.setCircuit` pins an arrow set) + plays the
  pulse (see Circuit animation) + opens its tab (`focusCircuit`). A **Projections** row isolates a
  group via `setCircuit` (pins the group's arrows + endpoints; dims every structure) + opens its
  tab (`focusProjectionGroup`; `dataKey` = `kind:<kind>`/`sign:<sign>`). Built from non-tentative
  projections.
- **Hypothetical pathways** (off by default): a "Show speculative (N)" toggle reveals every
  `tentative` (dotted) arrow, composed with **Show projections** via `createProjectionVisibility`.
- **reset** + **double-click empty space** fully clear (halos + isolate + circuit).

### Structure names

Hover/tap shows a boxless name label (white glyphs outlined in the region's `--label-color` + a
black halo); tapping empty space clears. Selecting a structure **pins** its name for the whole L/R
pair (`selection.onHighlight` -> `labels.setPinned`); hovering another *adds* its label. Labels
carry no "Right/Left" (`base_name`). `pickHover` is focus-aware: a focused region the ray passes
through beats a nearer non-focused one.

### Legend sections

- **Structures** (`#structures`): rows by group via `buildLegend` into `#structures-body`. Row
  click isolates + opens the tab (`onPickStructure`, gated on `selection.isIsolated`); heading
  isolates the group.
- **Projections** (`#projections`): same `buildLegend` into `#projections-body` (the colour-mode
  switch that drives them lives up in Controls); below it the per-group rows, the Circuits section,
  and the Hypothetical pathways toggle. `buildLegend` fills both Structures + Projections and
  returns one shared focus-greying callback.
- **Legend (the key)** (`#legend-modal`, toolbar popup or **k**): a *static* colour/symbol key
  built once by `buildLegendKey` into `#legend-body` from meta (so colours never drift): the
  expression gem dots, the per-drug effect dots + wash, the drug flow overlay (from
  `meta.systemFlowKinds`), a dotted speculative pathway; ends with a Sources & provenance link
  (`#legend-open-sourcing`). Wired by `wireLegendModal`.
- **Sources & provenance** (`#sourcing-modal`, `wireSourcingModal`): the grade key + coverage
  tally (`#about-sourcing`, `buildAboutSourcing` from `data.meta.provenanceStats`). The single
  place explaining the sourcing system (see Source provenance); auto-shown over the loading overlay
  on startup (the gate). `buildAboutSourcing(null)` renders the static intro + key immediately, a
  second call fills the tally once loaded.
- **Receptors & targets** (`#receptors`) / **Drugs** (`#drugs`): see their sections.
- **About** (`#about-modal`, ⓘ, `wireAboutModal`): a blurb (Olivier Cornelis + Claude), an "open
  an issue" link (`cfg.sourceUrl + "/issues"`, dropped unless `sourceUrl` is repo-like), a Source
  code link, a licence line (AGPL-3.0), a CC BY-SA attribution line, and a Sources & provenance
  link (`#about-open-sourcing`). The tally is not here (own popup).

### Input

- **Touch / mouse**: one finger / left-drag rotates; pinch / wheel zooms; two-finger drag pans
  (OrbitControls). **Shift + wheel** drives the Separate slider (a capture-phase `window` listener
  swallows it on `shiftKey`).
- **Keyboard shortcuts** (`wireShortcuts`, single-key, ignored while typing / for modifier combos):
  **n** names, **s** spread, **l** Structures, **p** Projections, **k** Legend, **c** See inside,
  **r** Receptors, **m** Drugs, **f** search, **Tab**/**Shift+Tab** cycle detail tabs, **Esc** peels
  one layer (active tab -> clear focus/isolate/circuit -> close search / collapse section). Arrow
  keys browse the open section (see below). Each maps by clicking the DOM element a mouse user would.
- **Section row navigation** (`sectionNav`): with a section open, **ArrowDown/Up** rove a
  `.kbd-active` highlight over its buttons + `.clickable` rows, **Enter** activates. Recomputed each
  key, wraps, cleared on section change/close + Esc. Typing in the drug filter keeps the arrows.
- **Toolbar icon-row** (wraps to a second row when narrow): keyboard-shortcuts, reset, search (swaps
  `#search` in place), legend, sources, about. The three popups share `wireModal`.
- **Search**: filters structures / connections / receptors / drugs / circuits / projection groups
  (the last two tagged `· circuit` / `· pathways`). **Type-filter chips** (`#search-filters`) scope
  to one kind (`activeType`, session-persisted). **Hovering** a result transiently applies its full
  focus via a `preview` thunk (the `select*`/`focus*` helpers' `preview:true` = scene focus only, no
  panel/tab/camera/auto-spread); leaving the list restores neutral, a click commits. Picking focuses
  + frames + opens the panel, exactly like the item's legend row (structure/connection via
  `selectStructure`/`selectConnection`'s `isolate`); the same focus-on-pick rule holds for
  detail-panel rows. Only **focusable** receptors/drugs are searchable. The box remembers the last
  query for the session. Matching is case/accent-insensitive and normalizes Greek + dashes
  (`foldText` + `GREEK_NAMES`, so "beta" finds "β1" and "5ht" finds "5-HT"; also used by
  `#drugs-filter`) over the label + hidden `keywords`. A `field:"value"` filter (`parseSearchQuery` +
  `SEARCH_FIELDS`): `class:"SNRI"` / `nbn:"..."` (field name folded, so French `classe:` works); a
  drug panel's clickable Class + Nomenclature build such a query (`info.onSearch` ->
  `openSearchWithQuery`). A **"?"** toggles `#search-syntax`. Connection results carry a
  `connectionSideTag`. **Ctrl/Cmd+F** intercepts page-find + opens search; **Esc** closes. Results
  are relevance-ranked (label-prefix > substring > keyword-only), capped, and keyboard-navigable.
- **Keyboard-shortcuts help popup** (`#shortcuts-modal`, `wireShortcutsHelp`): a centered dialog,
  rows mirroring `wireShortcuts` (so it can't drift), labels from `shortcuts.*` i18n. Opened by the
  keyboard button or **?**; closed by ×, backdrop, or Esc (routed first when open).

### Detail tabs (`createPanelTabs`)

Owns the `#panel-tabs` strip + which pane shows; it does **not** render a detail or apply focus.
The `select*` layer (`selectStructure`/`selectConnection`/`focusTarget`/`focusDrug`/`focusCircuit`/
`focusProjectionGroup`) renders + focuses, then calls `openDetailTab(key, title, reopen)`; the
`reopen` thunk re-runs that `select*`, so clicking a tab restores content + scene with no duplicated
logic. Keys dedupe one tab per thing (`structure:`/`connection:`/`target:`/`drug:`/`circuit:`/
`group:`); `MAX_TABS` bounds the strip. Closing the active tab falls back to a neighbour (re-applying
its focus) or, if last, to Settings + `onEmpty()` (`tabs.setOnEmpty(() => selection.clear())`).
Interactions: click, × to close, **long-press (~450ms) then drag** to reorder, wheel/touch-drag to
scroll. The strip is `touch-action: none` with a JS-driven drag-scroll (a native pan would
`pointercancel` mid-hold and kill the long-press). **Tab**/**Shift+Tab** cycle (`tabs.cycle`); **Esc**
closes the active tab (`tabs.closeActive`, false when only Settings is active).

### Info panel (`createInfoPanel`, into `#info-body`)

Pure rendering of a connection / structure / receptor / target / drug / circuit /
projection-group view; the active detail tab drives which shows. Opening the tab +
applying focus is the `select*` caller's job, so each `show*()` is reused unchanged
whether first picked or re-shown. An empty-space click returns to Settings
(`tabs.showSettings()`; detail tabs stay).

> [!IMPORTANT]
> **Panel changes are cross-cutting: think in node kinds, not one panel.** All info
> is organized into nodes, and the seven `show*()` views (connection / structure /
> receptor / target / drug / circuit / projection-group) share the same building
> blocks (`makeProvenancePill`, `appendSourcedHeading` = a node's identity line +
> its grade pill, `pathwayRow` / `appendPathwayList`, `locationList`,
> `appendReference` / `appendWikiImages`, the "Interacting drugs" / "Found in" lists).
> When you change what one panel shows or how it renders a row, **check whether the
> other panel kinds carry the analogous node and would benefit from the same change,
> and ask the user about any you find** before finishing. Prefer editing the shared
> helper over one call site, so a fix lands on every panel that reuses it at once
> (this is why the row markup lives in one place). Skipping this means a request made
> for one panel silently misses the others.

Every source shows a **provenance pill** (`makeProvenancePill`, see Source provenance) with a
hover/tap tooltip via `withTip(trigger, text)` (a present Wikipedia reference *link* is the
exception: no pill). The bubble is appended to `document.body` (escaping the panel's overflow +
dimming), `position: fixed`, re-placed on scroll/resize (`place()` / `fixedContainingBlock`).
Hover/focus reveals; clicking pins it (selectable); only one open at a time (`openTip`). Touch runs
the click-toggle path only. Text shows the concrete source first, the grade explainer under. Pill
tooltips are `info.provNone/provLlm/provSourced/provVerified`.

Views:
- **connection**: label, a `Projection` type line, route (`from → to`, `↔` bidirectional; each
  endpoint clickable via `endpointEl` -> `onStructurePick`), kind + neurotransmitter, description.
  Each of those rows carries the pathway's own `proj.provenance` badge (no bottom Sources block).
  Arrow picking (`pickArrowAt`) beats the region behind.
- **structure** (`showStructure`): name, a group heading with the anatomy grade pill
  (`classification_provenance`), a Reference row (Wikipedia link or `NOSOURCE`), the live Wikipedia
  lead as a `sourced` description (fetch-only, no baked copy), then the pathway list. Each connection
  row: a bold `directionArrow` (inline SVG, pathway colour, out/in/both; wrapped in `withTip` so a
  tap explains direction without bubbling to the row click), the other endpoint, and the pathway's
  summary pill (`proj.provenance`, resolved in `js/data.js`). Left/right twin pathways collapse to
  one row (by direction + other-endpoint `base_name` + label).
- **receptor / target / drug / circuit / projection-group**: see their sections.

A click on empty space closes the panel. **Double-click**: on a structure isolates it; on empty
space recenters.

### Camera focus (`createCameraFocus`)

All framing (reset, search, panel buttons) goes through one smooth tween: moves the orbit pivot +
camera distance, keeps the view direction, advanced once per frame, cancelled the moment the user
grabs the controls. Also owns the screen offset (`setScreenOffset`, eased in `tick`) for the
pan-aside. While a focus is held, moving Separate keeps it centered: the explode handler calls
`reaimFocused()`, enabling a **pivot-follow** that `tick()` eases (only the pivot moves, so the
camera holds the user's distance + angle). The tracked center is `getFocusMeshes` over the live
`selection.getSelected()`: a single `focused` structure tracks precisely, a multi-region focus tracks
the visible set's bounding-sphere center (only visible meshes, so it composes with "See inside"). The
follow disables itself once settled, on a camera grab (`cancel`), or when the focus clears.

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
  the classification facts each carrying the *mechanism* grade pill, then the "Found in" list via
  `locationList` grouped under `groupLabels` sub-headings, each region carrying its **own**
  expression-provenance pill + an amber "· <species>" tag when it has no human assay (`locationEntry`
  prefers Human, so an Allen confirmation clears it), or one pilled "Throughout the brain" for
  ubiquitous). A non-receptor target opens the lighter `showTarget` (type + system facts with their
  grade pills, then the same per-region "Found in" list, kind `target_locations`). Both add a **PDSP
  Ki** lookup link (`appendLookupLink`); a receptor also gets **UniProt** (human-only) + **GtoPdb**
  name-search links (`uniprotSearchUrl`/`gtopdbSearchUrl`, no pill). Both carry an **Interacting
  drugs** section (from `drugsByTarget`, grouped by category, each row an `effectGlyph` + the
  binding's `bindingProvenancePill` = the *same* resolved binding the drug panel shows; jumps via
  `info.onDrug`). Both make each "Found in" region clickable (`info.onStructure` -> `selectStructure`).
  A stub receptor / unlocated target renders muted.

Receptor data: `_receptor_record` validates every family/class/sign/synaptic key + location base;
`locations="ALL"` -> `ubiquitous`. `classification_provenance` (the mechanism grade) defaults `llm`,
overridable in `RECEPTOR_PROVENANCE`. Each expression region is a **separate** graded claim (kind
`receptor_locations`, default `llm`, upgraded per (receptor, region) by `RECEPTOR_LOCATION_SOURCES`,
quote-checked); these drove the `brainstem_nuclei` group. A non-receptor target's type/system/regions
are authored in `DRUG_TARGETS`; its regions grade identically (kind `target_locations`,
`TARGET_LOCATION_SOURCES`; both share the `_location_sources` emitter).

## Drugs

A focusable Drugs section showing, per drug, what it does to the brain. Data is from
**Stahl's Prescriber's Guide (8th ed.)**, extracted **strictly from the dump** (only
interactions literally stated; gaps left as TODO / no binding).

- **Data.** The 158 drugs live in `tools/drugs_data.json`, read by `_load_drugs`. Vocabularies are
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
  `buildWashShell` in the same colour. Stopped via an `onIsolate` watcher (`.matches`).
- **By-mechanism flow overlay** (reuses `js/circuit-anim.js`). The focus also rides beads along the
  projections of the drug's target system(s) (an SSRI the serotonergic fan, an SNRI + noradrenergic,
  a D2 antipsychotic the dopaminergic). The map is data: `generate_data.py` emits `system_flow_kinds`
  (target `system` -> projection `kind`, restricted to the diffuse ascending systems with a modeled
  source nucleus; glutamate/GABA left out so the overlay is a drug-specific fan). `js/data.js`
  resolves `flowKinds`; `focusDrug` filters arrows (`flowArrowsOf`), pins + `circuitAnim.play()`s
  them; a drug with unmapped systems pins none -> dots + wash only. (This is why the dataset carries
  the ascending monoamine pathways.)
- **Panel** (`showDrug`): the molecule image (when fetched), the class, the NbN, the description
  (live-refreshed from Wikipedia, re-graded `sourced`), a Wikipedia link, then the **Acts on** binding
  list (each row: an effect glyph + target + action·note, "· speculative" when tentative, plus a
  `bindingProvenancePill` = the binding's quote source, else its Ki (verified), else `NOSOURCE`),
  sorted strongest-affinity first. Below it a **Projections affected** list (only when `flowKinds`
  non-empty): one row per ascending system engaged (jumps to that kind-mode group, pilled with the
  strongest binding on the system); a *derived, non-directional* inference (caption says so). Class +
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

- **Molecule images** (vendored same-origin; CSP `img-src 'self' data:`). `tools/fetch_molecules.py`
  downloads each drug's lead infobox SVG via the MediaWiki `pageimages` API into
  `public/data/molecules/<id>.svg` (`.svg` only, `<script>` stripped); writes
  `tools/molecules_sources.json`. `generate_data.py` emits `structure_image` only when the file
  exists. `showDrug` renders it as `<img class="mol-structure">` with CSS `filter: invert(1)` for the
  dark panel (so the page declares `color-scheme: dark`). No image if absent.
- **Structure images** (hot-linked from Wikimedia; the multi-MB GIFs are NOT vendored, only the url).
  `tools/fetch_structure_images.py` resolves a **hero** per **base** (fallback: `.gif` -> `.svg` ->
  infobox/lead; pdf/djvu lead -> first-page JPG) + a **gallery** (`gather_gallery`: the other gif/svg
  on the base's EN+FR articles, chrome excluded via `_is_gallery_chrome`, capped `MAX_GALLERY`) into
  `tools/structure_images_sources.json`, downloading no bytes (`IMAGE_OVERRIDES` wins for the hero).
  The **same resolver** runs over wiki-linked **circuits** (`--target circuits`) into
  `tools/circuit_images_sources.json`. `generate_data.py` emits `structure_image` + `_gallery` for
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
no source shows `NOSOURCE`, never a blank. The coverage **tally** collapses the two unbacked cases
(`llm` and `NOSOURCE`) into one **missing** tier, so its tiers are verified / sourced / missing (see
The "% sourced" figure).

**Where the grade lives.** One source shape, quote-level `{corpus, page, quote, provenance}` against a
`SOURCE_CORPORA` corpus; `provenance` defaults `DEFAULT_PROVENANCE` (`"llm"`), a sourceless node is
`NOSOURCE`. Each `wikipedia` reference emits a sibling `wikipedia_provenance` (`WIKIPEDIA_PROVENANCE`
registry); a **present** link defaults `"sourced"` (`WIKIPEDIA_DEFAULT_PROVENANCE`), not `llm` (a real
reference the viewer live-fetches). `_provenance` validates every grade; upgrading a source is a data edit.

**Per-claim sources + the verify gate.** Every source is `{corpus, page, quote, provenance}`: a
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
  `tools/location_sources.json`. Each quote carries the assay **`species`** (Human/Rat/Mouse/Monkey,
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

1. Edit the relevant list in `generate_data.py` (or `tools/drugs_data.json` for drugs).
   - **Structures**: edit `PAIRED` / `MIDLINE`. Paired entries are auto-mirrored (define on the right,
     x > 0; the generator emits one right-side shape file and the `_L` member references it with
     `mirror:true`). A region is a noise-deformed ellipsoid by default; blob/curve/composite shape knobs
     are in the Geometry section (`medial=True` derives the right medial clip; `clip_planes` is auto via
     `_bisecting_clip_planes`, `JIGSAW_CLIP.enabled`; cortex pattern is shader-drawn via
     `injectCortexSwirl`/`CORTEX_SWIRL`). Layout: the `pos` field positions regions to assemble at
     explode 0; lobes overlap + `medial` so the hemispheres meet at `MIDLINE_GAP` (temporal is the
     lateral exception); deep nuclei sit small + central. Re-render to check
     (`only=frontal_R,parietal_R,temporal_R,occipital_R&explode=0&view=right`).
   - **Structure links + grades**: add a `base -> URL` entry to the `WIKIPEDIA` registry
     for a Wikipedia link (both hemispheres share it; a non-base key raises). Anatomy source
     grade is `classification_provenance`, default `llm`, overridable in
     `STRUCTURE_PROVENANCE` (the `RECEPTOR_PROVENANCE` / `TARGET_PROVENANCE` /
     `STRUCTURE_PROVENANCE` trio via `_lookup_provenance`).
   - **Projections**: edit `PROJECTIONS`. `from`/`to` are structure ids; the arrow points
     `from -> to`. Carry `label` / `neurotransmitter` / `description`. A pathway is graded
     by a verified quote in `KANDEL_QUOTES` (keyed by the right-side `(from, to)` pair);
     an unsourced pathway shows `NOSOURCE` (no fabricated citations).
     `bidirectional: True` (both cones; use with
     `symmetric: False` + explicit `_L`/`_R` for commissures). `tentative: True` (dotted,
     Hypothetical section). Projections are bilateral by default (define once on the right);
     `symmetric: False` keeps a one-sided pathway. `kind` must be a `PROJECTION_COLORS` key
     (excitatory / inhibitory / dopaminergic / cholinergic / neuroendocrine / serotonergic /
     noradrenergic); a new kind also needs `KIND_TO_SIGN` (-> `SIGN_COLORS` / `SIGN_LABELS`)
     and `BURST` in `circuit-anim.js`.
   - **Circuits**: append to `CIRCUITS`: `id`, `name`, `structures` as base ids (arrows
     derived). Optional `description` + `description_fr` + `wikipedia` + `sources` (a list
     of quote-level `{corpus,page,quote,provenance}` dicts, validated by `_expand_sources`).
   - **Projection groups**: edit `PROJECTION_GROUPS`: one entry per group in both modes,
     `{mode, key, name, description, description_fr, wikipedia, sources}` (`mode` kind|sign,
     `key` validated; `sources` quote-level dicts). Normally you only edit
     descriptions/wikipedia (all 7 kinds + 3 signs exist); a new entry is needed only when
     adding a new projection `kind`.
   - **Receptors**: append to `RECEPTORS`: `id`, `name`, `family`, `neurotransmitter`,
     `receptor_class`, `sign`, `synaptic`, `locations` (base ids or `"ALL"`). Optional
     `description` + `description_fr` (inline) + `wikipedia`. A stub = empty `locations` +
     no description. `_receptor_record` validates keys + bases. A new family/class/synaptic
     value needs its label map entry (+ FR). Mechanism grade overridable in
     `RECEPTOR_PROVENANCE`; an individual expression region is sourced (above `llm`) by
     adding a `{receptor_id: {base: [quote-source]}}` entry to `RECEPTOR_LOCATION_SOURCES`.
   - **Drugs**: edit `tools/drugs_data.json`. Each: `id`, `name`, `categories`, optional
     `nbn` + `description` (inline `{en,fr}`), `wikipedia`, `bindings`. A binding is
     `{target, action}` (+ optional `effect` / `note` / `tentative`); `target` is a merged
     map key (a `DRUG_TARGETS` key or a receptor id), `action` a `DRUG_ACTIONS` key
     (agonist / partial_agonist / antagonist / inverse_agonist / reuptake_inhibitor /
     releaser / enzyme_inhibitor / pam / nam / blocker / modulator). `"bindings": []` ->
     `focusable: false`. A new coarse target/category/action needs a `DRUG_TARGETS` /
     `DRUG_CATEGORY_LABELS` / `DRUG_ACTIONS` entry (with `{en,fr}` labels; a `DRUG_TARGETS`
     entry needs a `type` + optional `wikipedia`). Target classification grade
     overridable in `TARGET_PROVENANCE`; an individual "Found in" region is sourced
     (above `llm`) by adding a `{target_id: {base: [quote-source]}}` entry to
     `TARGET_LOCATION_SOURCES` (mirror of `RECEPTOR_LOCATION_SOURCES`). The drug's class
     classification grade is overridable in `DRUG_CATEGORY_PROVENANCE` (or upgraded by a
     quote-level `category_sources` on the authored drug). Keep extraction strictly
     dump-sourced.
   - **Translations**: every display string is wrapped with `_t()`; add the French to the
     `FR` table or the build raises listing every miss. For a feminine/plural paired name set
     `fr_gender` (`f`/`mp`/`fp`).
2. Run `python tools/generate_data.py` to regenerate `public/data/`.
3. Optionally run `python tools/check_data.py`.
4. For new drugs/structures with links, run the fetch tools (network, idempotent, touch
   only the new ones): `fetch_molecules.py`, `fetch_structure_images.py`. To refresh
   binding affinities, run `fetch_ki.py --apply` (reads the local PDSP CSV; idempotent),
   which rewrites `drugs_data.json`'s `ki` annotations + `affinity_only` bindings.
5. Commit the generator change + the regenerated artifacts together.

The legend is generated at runtime from the data, so it updates automatically.

### Refreshing external data (author-side)

To re-pull every third-party asset the dataset hot-links or vendors, run these (all
network, idempotent, polite; each touches only what changed). Always finish with
`generate_data.py` so the emitted `public/data/` picks up the new urls/files:

1. `python tools/fetch_molecules.py` — new per-drug molecule SVGs into
   `public/data/molecules/` (only drugs missing one); writes `tools/molecules_sources.json`.
2. `python tools/fetch_structure_images.py` — re-resolve each structure's **and**
   wiki-linked circuit's Wikipedia hero + gallery image **urls** into
   `tools/structure_images_sources.json` + `tools/circuit_images_sources.json` (no bytes
   downloaded; the gif/svg is hot-linked at runtime). `--target structures|circuits`
   scopes to one.
3. **PDSP Ki**: re-download the whole-DB CSV from
   `https://pdspdb.unc.edu/databases/kiDownload/download.php` over
   `sources/books/pdsp_ki/KiDatabase.csv` (author-side; see that dir's `README.md`), then
   `python tools/fetch_ki.py --apply` to rewrite `drugs_data.json`'s `ki` + `affinity_only`.
4. **GtoPdb receptor expression** (the `receptor_locations` sources): `python
   tools/fetch_gtopdb.py` re-pulls each receptor's tissue comments (caches to
   `sources/gtopdb/`, author-side), then run the confirm-only judge over
   `sources/gtopdb/worklist.json` and `python tools/apply_location_sources.py --judged <f>`
   to merge new `verified` sources into `tools/location_sources.json`. See Expression locations.
5. **Allen AHBA expression** (the `target_locations` + residual `receptor_locations`
   sources): `python tools/fetch_allen.py` re-pulls each donor's microarray PACall (caches
   to `sources/allen/`, author-side; ~2GB across donors), then `python
   tools/apply_location_sources.py --corpus allen` merges the deterministic `verified`
   sources (no judge) into `tools/location_sources.json`. See Expression locations.
6. `python tools/generate_data.py` — regenerate `public/data/` from all of the above.
7. `python tools/update_readme_stats.py` — refresh the README sourcing table
   (CI runs it `--check`).

Panel **descriptions** need no refresh script: each fetches the current Wikipedia lead
at runtime (`js/wiki.js`), so they stay current on their own.

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
