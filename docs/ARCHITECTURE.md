# Architecture

A bird's-eye view of how neurarium is put together, for contributors. It explains
the **shape of the system and the reasoning behind it**; the per-file detail sits in
the last section, File map (detail).

> [!NOTE]
> Four docs, four jobs, no overlap:
> - **[README.md](../README.md)**: what neurarium is, how to run it, the project layout table.
> - **This file**: the architecture, the data flow, the module graph, the boot
>   sequence, the extension points (the "why" and the "shape"), plus the per-file detail CLAUDE.md's file map points to. Otherwise bird's-eye, no
>   field-level detail; when it would name a field or control it points at CLAUDE.md.
> - **[CLAUDE.md](../CLAUDE.md)**: a terse map of the viewer/runtime (one line per module /
>   control / rule), not a manual: it names the symbol so you can find the code.
> - **[tools/README.md](../tools/README.md)**: the authoring how-to (Changing the data), the
>   per-tool reference, and the emitted-data field contract.

This project was built with the help of [Claude Code](https://claude.com/claude-code).

## Guiding principles

1. **Data is separate from rendering, on purpose.** The anatomy (which regions
   exist, where they sit, how they connect) is plain data; the viewer is code that
   draws whatever data it is handed. You can add regions and pathways without
   touching the renderer, and the data could drive a different engine entirely.
2. **No build step.** No bundler, no `node_modules`, no transpile. The browser
   loads hand-written ES modules and vendored three.js via an import map. What is
   in `public/` is exactly what ships. This keeps the attack surface small and the
   project trivially serveable as static files.
3. **Single source of truth.** Each fact lives in exactly one place. The anatomy
   *and its presentation maps* (region colours, the projection-kind palette, the
   group→legend-heading map, the per-structure Wikipedia links) are all defined
   once in the generator (`tools/generate_data.py` + its `tools/data_generators/`
   package); the presentation maps are emitted into the data so the viewer never
   hardcodes a second copy.
4. **Self-describing data.** `meta.json` carries the colour and heading maps, so
   a consumer (this viewer, or a port to another language) needs no out-of-band
   palette to render it correctly.
5. **Fail loud at generation time.** The generator raises on an unmapped
   projection kind, an unknown circuit structure, or a Wikipedia entry for a
   non-existent structure, so bad data never reaches the browser silently.

## The node model

The organizing concept of the whole dataset is the **node**: *a node is any
sourceable datum*, one atom of knowledge about the brain that could, in principle,
be attributed to a source. The dataset is a **graph of nodes**, and a detail panel
is simply a view of one node plus every node linked to it (a receptor node links to
the region nodes that express it and the drug nodes that act on it, and so on).

**Umbrella vs. kind.** "Node" is the umbrella term; each node has a **kind** that
keeps its own name in the data and code (a `structures.jsonl`, a `showReceptor`):
region anatomy, projection, circuit, projection group, receptor + its expression
regions, drug target + its expression regions, drug binding, drug NbN, drug class,
Wikipedia reference. CLAUDE.md ("Nodes") keeps a one-line-per-kind summary; the full map with its rationale is below.

**The full kind map** (the emitted collection -> the sourcing-tally kind in `meta.provenance_stats.by_kind`):
- brain region -> `structures.jsonl` -> `structures`
- projection (pathway) -> `projections.jsonl` -> `projections` (the route only), split from the two claims that ride the same arrow: its *transmitter* -> a projection's `claims.transmitter` -> `projection_transmitter` (on every pathway) and its *sign* (excit./inhib.) -> `claims.sign` -> `projection_sign` (on the glutamate/GABA arrows only: "modulatory" is the ABSENCE of a sign claim, not a third value). Each is graded by a closed word test over the arrow's own quotes (derived, `quotes/attestation.py`), so a sentence that only states the route no longer green-checks what it releases
- functional circuit -> `circuits.jsonl` -> `circuits`
- projection group -> `projection_groups.jsonl` -> `projection_groups`
- receptor classification -> `receptors.jsonl`, split into four independent graded sub-claims: neurotransmitter `family` -> `receptors`; mechanism `receptor_class` (GPCR/ionotropic) -> `receptor_class`; `sign` (excit./inhib.) -> `receptor_sign`; `synaptic` site (pre/post) -> `receptor_synaptic` (a receptor's `classification[attr]` each carry their own grade)
- receptor *expression region* -> a receptor's `location_sources` -> `receptor_locations`
- receptor *expression density profile* -> a receptor's `density` -> `receptor_density` (ONE node for the whole profile, not one per region: it is a single measurement ranking the receptor's regions against each other, see Expression density in VIEWER.md)
- receptor / target *clinical effect* (BETA) -> an owner's `effects[]` -> `receptor_effect` (ONE node per (mode, effect): "acting on this receptor in this mode can cause this effect", e.g. H1 antagonism -> sedation; modes + effects are closed vocabularies in `tools/data_generators/receptor_effects.py`; counted in the headline as a stored quoted claim, while a drug's derived "possible effects" are never stored nor tallied)
- receptor *release modulation* (BETA, a 2nd-order effect) -> a receptor's `release_modulation[]` -> `receptor_release_modulation` (ONE node per (kind, site, transmitter, direction): "activating this auto/heteroreceptor, on this cell type (optionally in this structure), increases/decreases this transmitter's release", e.g. H3 autoreceptor on presynaptic terminals -> less histamine; closed vocabularies in `tools/data_generators/release_modulation.py`; a drug's derived release changes are never stored nor tallied)
- receptor / target *availability across age and sex* (BETA) -> an owner's `demographics[]` -> `receptor_demographic` (ONE node per (factor, direction, structure): "in humans, its availability declines with age in the caudate" / "is higher in women"; read off hand-listed human PET / SPECT abstracts in Europe PMC #17; optional `magnitude` is verbatim text of its quote; closed vocabularies in `tools/data_generators/demographics.py`)
- receptor / target *genetic variant* -> an owner's `variants[]` -> `receptor_variant` (one node per ClinPGx #20 clinical annotation on the owner's gene, levels 1A-3 only, via `genes.GENE_OWNERS`; a drug panel lists those naming it)
- non-receptor drug target -> `meta.drug_targets` -> `targets`
- target *tone polarity* (a direction-flipping `vesicular`/`sign`/`synaptic` flag) -> a target's `polarity_provenance` -> `target_polarity`
- target *expression region* -> a target's `location_sources` -> `target_locations`
- target *expression density profile* -> a target's `density` -> `target_density` (same shape)
- drug binding -> a drug's `bindings[]` -> `drug_bindings`
- drug binding direction -> a binding's `action` -> `drug_binding_action` (graded by the binding's quote sources only, a Ki attests binding never direction; `affinity_only` = NOSOURCE; metabolite bindings counted in this same kind)
- drug NbN label -> a drug's `nbn` -> `drug_nbn`
- drug commercial brand name -> a drug's `brands[]` -> `drug_brands` (each brand a graded node; `region` na/eu/fr (or a list of them when one name sells in several regions; appliers dedupe names case/accent/space-insensitively) orders them per locale, never shown; na from Stahl, eu/fr from Wikipedia)
- drug class classification -> a drug's `categories` (+ `category_provenance`) -> `drug_categories`
- drug elimination half-life (T½) -> a drug's `half_life` (+ `half_life_sources`) -> `drug_half_life`
- drug time-to-peak (Tmax) -> a drug's `tmax` (+ `tmax_sources`) -> `drug_tmax` (the other end of the same curve as the T½ above, separately sourced and separately missing, so a separate kind)
- drug formulation -> a drug's `formulations[]` entry (`{release, release_sources, brands?, tmax?, half_life?}`) -> `drug_formulations` (ONE node per release type; the brands / Tmax / T½ under it are the same kinds as the molecule's, re-homed to the product a source measured or sold them for, see docs/DRUGS.md "Formulations")
- drug first approval -> a drug's `first_approval` (`{year, country?, agency?}`, + `first_approval_sources`) -> `drug_first_approval` (ONE node per drug: the earliest approval or introduction for medical use its source states)
- drug current holder -> a drug's `holders[]` (`{market, names[], sources}`) -> `drug_holders` (ONE node per (drug, market): who holds the marketing authorisation TODAY, read by code off Drugs@FDA (us) / BDPM (fr), never the inventor)
- drug originator -> a drug's `originator` (`{name, now?}`, + `originator_sources`, `originator_now_sources`) -> `drug_originator` (ONE node per drug: the company or lab its article says discovered / developed it; `now` is part of the node)
- drug physicochemistry -> a drug's `xlogp` / `tpsa` (numbers, + `xlogp_sources` / `tpsa_sources`) -> `drug_lipophilicity` / `drug_polar_surface`, and its `bbb` (`{label: "BBB+"|"BBB-", logbb?, logbb_max?}`, + `bbb_sources`) -> `drug_bbb` (ONE node per drug each, code-read off PubChem #21 / B3DB #22, `tools/data_generators/physchem.py`)
- drug workup (BETA) -> a drug's `workup[]` (`{test, timing, sources}`, ids from meta `workup_tests` / `workup_timings`) -> `drug_workup` (ONE node per (drug, test, timing), LLM-picked off the French RCP 4.2-4.4 #24 and judged, `tools/data_generators/workup.py`)
- drug originator country -> a drug's `originator_country` (a `history.COUNTRIES` id, + `originator_country_sources`) -> `drug_originator_country` (ONE node per drug, from the originator company's own article)
- drug therapeutic reference range -> a drug's `therapeutic_range` (`{low, high, unit, analyte?, tdm_level?}`, + `therapeutic_range_sources`) -> `drug_therapeutic_range` (ONE node per drug, AGNP Table 5)
- drug laboratory alert level -> a drug's `alert_level` (`{value, unit, analyte?}`, + `alert_level_sources`) -> `drug_alert_level` (ONE node per drug, same table row as the range but a separate claim)
- drug prodrug flag -> a drug's `prodrug: true` (+ `prodrug_sources`) -> `drug_prodrug` (ONE node per prodrug; the drug then carries no binding of its own, see Prodrugs in DRUGS.md)
- drug salt composition -> a drug's `constituents` (+ `constituents_sources`) -> `drug_constituents` (ONE node per salt; it borrows its modeled constituents' bindings, see Drugs in DRUGS.md)
- drug market withdrawal -> a drug's `withdrawals[]` (`{year, country, reason, sources}`) -> `drug_withdrawals` (one node per withdrawal; a drug never withdrawn carries none, since absence is not a claim)
- drug metabolism role -> a drug's `enzymes[]` (`{enzyme, role, strength?}`) -> `drug_enzymes` (one node per (enzyme, role) pair; pharmacokinetics, so it has no anatomy, see Drug metabolism in DRUGS.md)
- drug metabolism **strength tier** -> that row's `claims.strength` -> `drug_enzyme_strength` (only on a row that states a tier; the CYP quote gate checks the isoform is named, never the tier, so it is graded by the same word test the pathway claims use, `quotes/attestation.py`)
- enzyme population variability -> an enzyme's `variability` -> `enzyme_variability` (ONE node per isoform for the whole profile, not one per population group, for the same reason a density profile is one node: a single published aggregation ranking the groups against each other)
- pharmacogenomic prescribing -> a drug's `pgx[].rows[]` -> `drug_pgx` (ONE node per (drug, gene, phenotype), carrying two CPIC #15 citations: the implication, then the recommendation)
- drug active metabolite -> a drug's `metabolites[]` reference (`{id, sources, formed_by?}`, the per-parent "is a metabolite of" claim) -> `drug_metabolites`; the molecule itself (`{id, name, drug_id?, half_life?, bindings?}`) is ONE record in `metabolites.jsonl` (authored `tools/data/metabolites_data.jsonl`) however many drugs make it, joined by id in `js/data.js` (a metabolite that is itself a modeled drug links via `drug_id` + reuses its bindings/T½)
- metabolite-forming enzyme -> a metabolite's `formed_by[]` (`{enzyme, reaction?, sources}`) -> `drug_metabolite_enzyme` (one node per (parent, metabolite, enzyme); the mirror of `drug_enzymes`, counted per PARENT since two parents make it by two reactions)
- non-modeled-metabolite receptor binding -> a `metabolites.jsonl` record's `bindings[]` -> `drug_metabolite_bindings` (one node per record, not per parent; sourced from the metabolite's own Wikipedia pharmacology, corpus #9; graded like a drug binding, a separate kind so the drug Ki coverage is unperturbed; surfaces on the receptor's Interacting drugs)
- panel annotation -> `addons.jsonl` -> `addons` (an **addon node**: the kind whose record carries its own insertion point, for a claim no other kind has a home for. `owner_kind` + `owner` name the node it annotates, `slot` a `meta.addon_slots` hook, `display`/`tone` how it draws; authored in `tools/data_generators/addons.py`, see Addon nodes in VIEWER.md)
- Wikipedia reference -> any node's `wikipedia` -> `references` (a pointer *at* a node, tallied but excluded from the headline; a reference is not itself a knowledge node)

**Every node is sourceable.** Each carries a provenance **grade** (`llm` < `sourced`
< `verified`) and, ideally, a **source**: one quote-level `{corpus, page, quote,
provenance}` pointing at a page of a real corpus (`SOURCE_CORPORA`, e.g. Stahl,
Kandel, the PDSP Ki database). The grade is *data*, and the viewer renders it as a
coloured **pill** on the row/heading that carries the claim: green `✓` verified,
yellow `~` sourced, grey `?` llm, orange `NOSOURCE` when there is no source. A node's
grade is never simply absent from a panel.

**The coverage tally.** `_provenance_stats` (`tools/data_generators/provenance_stats.py`) reduces every node to its
single strongest grade and buckets it into **verified** / **sourced** / **missing**,
where *missing* is "no source document at all" (a bare `llm` grade counts as missing:
an LLM asserting something from memory is precisely *no document*). It emits
`meta.provenance_stats`; the About panel and the README headline read it, so the
"% sourced" figure is always a real programmatic count of the shipped data, never
hand-typed. `check_data.py` re-derives the same numbers as a self-consistency gate.
Full mechanics live in [`PROVENANCE.md`](PROVENANCE.md).

## The three layers

```
   AUTHORING                 ARTIFACTS (committed)              VIEWER (browser)
 ┌───────────────┐         ┌───────────────────────────┐         ┌──────────────────┐
 │ generate_     │  emits  │ public/data/meta.json      │  fetch  │ public/js/*.js   │
 │ data.py       │ ──────► │ structures.jsonl           │ ──────► │ + index.html     │
 │ (stdlib only) │         │ projections / circuits     │         │ (three.js)       │
 │               │         │ shapes/*.json (geometry)   │         │                  │
 └───────────────┘         └───────────────────────────┘         └──────────────────┘
   one definition            plain JSONL + JSON,                renders, no anatomy
   per region/pathway        the data contract                  knowledge of its own
```

The boundary between the middle and right columns is the **data contract**: as
long as the viewer keeps reading the same record shapes, the generator can evolve
freely, and as long as the generator keeps emitting them, the viewer can be
rewritten (or replaced) freely.

### Authoring: `tools/generate_data.py`

Standard-library-only Python. Now a thin orchestrator: it defines the build/emit
logic and imports the data from the `tools/data_generators/` package (`i18n.py`,
`provenance.py`, `drugs.py`, `geometry.py`, `presentation.py`, `connectivity.py`,
and the `quotes/`, `receptors/`, `regions/` subpackages; see tools/README.md for the
per-module purpose). It defines every region once (right-side only for
symmetric pairs; the generator mirrors it to the left), every projection
(bilateral by default, mirrored unless flagged one-sided), every named circuit,
and the registries (`WIKIPEDIA`, `KANDEL_QUOTES`, `PROJECTION_COLORS`, `GROUP_LABELS`).
Running it regenerates `public/data/` (`meta.json` + the `*.jsonl` files +
`shapes/`). The generated files are committed so the static site can fetch them
directly.

### Artifacts: the data contract

The dataset under `public/data/` is split by record type for clarity: the file a
record lives in encodes its type, so there is no `type` field on the lines.
`meta.json` is a single JSON object of presentation maps (colours, labels, the
merged binding-target map) that makes the dataset self-describing; the rest are
JSONL, one node per line, one file per kind: `structures.jsonl`, `projections.jsonl`,
`circuits.jsonl`, `projection_groups.jsonl`, `receptors.jsonl`, `drugs.jsonl` (drugs
authored in `tools/data/drugs_data.jsonl`, not the generator), plus vendored
`molecules/<id>.svg` diagrams. The emitted data is **English-only**: every display
string is serialized as its English text and the French is deduplicated into one side
table, `translations.fr.json`, which the viewer fetches only in French (see
docs/I18N.md). Every claim carries its own quote-level source; there is no node-level
catch-all `sources` block. The exact field list of each file is in tools/README.md
("Data contract"), not duplicated here.

`public/data/shapes/<name>.json` is one geometry payload per distinct *form* (symmetric
pairs share a single right-side file; the left member reflects it). Shape types:
`blob` (a noise-deformed ellipsoid), `curve` (a tube swept along a spline),
`composite` (several sub-shapes merged), and `sdf` (an authored signed-distance
atlas meshed via marching cubes, replacing the procedural forms one structure at a
time; see the `geometry_refinements/` effort in CLAUDE.md).

### Viewer: `public/`

Vanilla ES modules over three.js. `index.html` is the shell; the JS modules build
and drive the scene. See the module graph below.

## Module graph

Solid arrows are ES-module `import`s; `index.html` loads the classic scripts and
the `main.js` entry point.

```
                         index.html
                             │ (script tags, in order)
   ┌─────────────────────────┼───────────────────────────────────┐
   │                         │                                    │
 app-config.js          error-banner.js / dev-banner.js      main.js  (module entry)
 (window.__APP_CONFIG__)  (classic; #banners stack)              │
   │                                                             │ imports
 app-init.js                                                     ▼
 (injects umami)             data.js ──fetch──► data/*.{json,jsonl} + data/shapes/*.json
                              (no three.js; returns normalized {structures,
                               projections, circuits, receptors, drugs, byId, meta})
                                  ▲
                                  │ loadBrainData()
                                  │
   main.js ── imports ──►  shapes.js   (buildStructureMesh: blob/curve/composite/sdf,
                                        cel-shaded cortex swirl, jigsaw clip)
            ── imports ──►  arrows.js   (buildArrows: curved tube+cone per
                                        projection, colour from projection.color)
            ── imports ──►  labels.js   (createLabels: CSS2D floating names)
            ── imports ──►  circuit-anim.js / circuit-schedule.js (traveling pulse
                                        + a wash-of-light echo on each target node)
            ── imports ──►  receptor-markers.js (createReceptorMarkers: glowing
                                        surface dots for a focused receptor;
                                        exports buildGemCloud, reused by drug-anim)
            ── imports ──►  drug-anim.js (createDrugAnimation: effect-coloured
                                        pulsing gem dots + a surface wash per region)
            ── imports ──►  three + OrbitControls (vendored)

   circuit-anim.js, drug-anim.js ── import ──►  surface-wash.js (buildWashShell: the
                                        shared shader "wash of light" over a surface)
```

`data.js`, `shapes.js`, and `arrows.js` have **no dependency on each other**; they
meet only in `main.js`, which orchestrates everything. `data.js` deliberately
knows nothing about three.js (it is pure fetch + normalize), so the data layer
could be reused headless.

## Boot sequence

1. `index.html` parses. The classic scripts run first, in order:
   `app-config.js` (sets `window.__APP_CONFIG__`), `app-init.js` (injects the
   umami tag if configured), `version.js` (sets `window.__APP_VERSION__`), then
   `error-banner.js` and `dev-banner.js` (install the `#banners` machinery before
   anything that might fail).
2. A small inline gate injects the vendored eruda debug console only on `?debug=1`.
3. The import map points `three` / `three/addons/` at the vendored copy.
4. `js/main.js` (module) runs: sets up scene/camera/renderer/lights/OrbitControls,
   then `await loadBrainData()`.
5. `loadBrainData()` fetches the per-type data files (`meta.json` +
   `structures`/`projections`/`circuits`/`receptors`/`drugs.jsonl`) in parallel,
   reads the
   `meta` maps, resolves each projection's `color` from its kind, expands each
   receptor's location bases to concrete structure ids, resolves each drug's
   bindings (target name, net effect colour, the regions each binding lights), and
   fetches every
   referenced shape file in parallel.
6. `main.js` builds the meshes (`buildStructureMeshes` in `js/boot/meshing.js`, over `buildStructureMesh`), the arrows (`buildArrows`),
   and the labels (`createLabels`), wires the controllers (below), and starts the
   render loop.
7. The intro animation plays: regions start exploded and glide back together into
   the assembled brain (skipped when `?explode=` is pinned, e.g. screenshots).

## Rendering and interaction (`main.js` + `js/boot/`)

`main.js` (with the `js/boot/` stages it calls) is the only stateful orchestrator. Beyond scene setup and the render
loop, it owns a few small controllers, each the single source of truth for one
concern:

- **Selection** (`createSelection`): which structures/arrows are haloed or
  isolated, and the resulting per-mesh opacity (so the Transparency slider and the
  isolate-dimming compose into one value). Handles structure halos, arrow halos,
  legend isolate, circuits, and per-neurotransmitter focus.
- **Info panel** (`createInfoPanel`): the main panel's Details tab showing a
  *connection* view (a clicked arrow), a *structure* view (a clicked region: name,
  group, Wikipedia link, and a clickable list of its pathways), a *receptor*
  view (a clicked Receptors legend row: its classification + where it is
  expressed), or a *drug* view (a clicked Drugs legend row: its class, NbN
  nomenclature, the bindings it acts on, and the Stahl source).
- **Receptor markers** (`receptor-markers.js`): glowing surface dots over the
  regions expressing a focused receptor; dropped when the focus changes, watched
  off the selection state like the circuit pulse.
- **Drug animation** (`drug-anim.js`): effect-coloured gem dots (boost/block/
  modulate) pulsing over the regions a focused drug's targets sit in, reusing the
  receptor `buildGemCloud`, with a looping **surface wash** under them in the same
  effect colour; watched off the selection state the same way. On top of this, a
  drug focus also rides **flowing beads** along the projections of its target
  transmitter system(s) (the **by-mechanism flow** overlay): `main.js` resolves the
  drug's `flowKinds` (via the `meta.system_flow_kinds` map), pins those arrows and
  replays the **shared circuit pulse** (`circuit-anim.js`) over them, so the drug
  and circuit animations merge instead of duplicating. A drug with no mapped
  pathway pins nothing and just shows the dots + wash.
- **Surface wash** (`surface-wash.js`): the shared shader "wash of light" that
  spreads a ripple across a structure's surface from an origin point (a thin shell
  reusing the mesh geometry, additive, no added triangles). Drives the circuit node
  echo (seeded at the bead's impact point) and the per-drug region glow.
- **Camera focus** (`createCameraFocus`): smooth tweens for reset / double-click /
  search framing, advanced once per frame and cancelled the moment the user grabs
  the controls.
- **Labels** (`labels.js`): floating CSS2D names, shown on hover or all at once.

Picks (click / tap / double-click / search) are routed through small
`selectStructure` / `selectConnection` helpers so every entry point produces the
same halo + panel + label behaviour without duplication.

## Extending the system

The detailed recipes (with the exact fields and gotchas) are in CLAUDE.md under
"Changing the data"; the short version:

- **A new region or pathway**: edit `PAIRED` / `MIDLINE` / `PROJECTIONS` in
  `generate_data.py`, run `python tools/generate_data.py`, commit the generator
  change and the regenerated artifacts together.
- **A new projection kind / colour**: add it to `PROJECTION_COLORS` (the generator
  raises if a projection uses an unmapped kind); it flows into the data's `meta`
  record and the legend automatically.
- **A new circuit**: append to `CIRCUITS` with base structure ids.
- **A new receptor**: append to `RECEPTORS` (neurotransmitter, class, sign,
  synaptic site, location base ids or `"ALL"`); it shows up in the Receptors
  legend section automatically.
- **A new drug**: add an entry to `tools/data/drugs_data.jsonl` (categories + bindings,
  each binding a `target` + `action` from the drug vocabularies in
  `generate_data.py`); it shows up in the Drugs legend section automatically. Run
  `python tools/fetch/fetch_molecules.py` to also pull its molecular-structure SVG.
- **A Wikipedia link**: add the region's base id + URL to the `WIKIPEDIA` registry.

The legend, colours, and headings are all derived from the data at runtime, so
none of these need a matching change in the viewer.

## Deployment (in brief)

The site is static, so deployment is just "serve `public/`". In production a
hardened Caddy container (non-root, read-only rootfs, dropped capabilities,
resource limits, strict Content-Security-Policy) serves it behind a TLS-
terminating reverse proxy. Runtime config (analytics, the WIP banner) is injected
at container start by rendering `app-config.js` from environment variables, since
the rootfs is read-only and there is no build step. Full details are in CLAUDE.md
under "Deployment", "Analytics", "Content-Security-Policy", and "Dev / WIP banner".

## File map (detail)

The per-file detail behind CLAUDE.md's one-line file map. Section names cited as "see X" are CLAUDE.md sections (or the `docs/*.md` file CLAUDE.md points them to).

**Project layout.** `public/` is the **only** web-exposed directory: Caddy's `/srv` and `tools/serve.py` both root there, so `docker/`, `tools/`, `.git` and the uncommitted `.env` / `deploy.sh` / `CLAUDE.local.md` are never web-reachable. Authoring + dev tooling live in `tools/`, deployment config in `docker/`.

**The `tools/` script reference and the emitted-data field contract (`public/data/` `.jsonl` / `meta.json` / `shapes/*.json` fields) live in [`tools/README.md`](../tools/README.md)** (Tool reference + Data contract). The generator layout is under Authoring above (plus the `genes` and `quote_table` modules of `tools/data_generators/`). Each geometry form is one `data/shapes/<name>.json` (`blob`/`curve`/`composite`, L/R pairs share one right-side file via `mirror:true`). The author-side scripts are grouped: external-data fetchers under `tools/fetch/`, provenance appliers under `tools/sourcing/`; their generated caches in `tools/generated_cache/`. Run them from the repo root (`python tools/fetch/<x>.py`).

> [!NOTE]
> An ongoing effort under `geometry_refinements/` (its own `CLAUDE.md` +
> `STATUS.md`, auto-loaded only when working there) is replacing the procedural
> blob/curve/composite shapes with a self-authored SDF atlas, one structure at a time. It
> adds an `sdf` shape type. Before editing `data/shapes/*` or `shapes.js`
> geometry, check its `STATUS.md` so two sessions don't collide.

Viewer (`public/`):

- `index.html`: page shell (markup only; styles live in `css/`): loads three.js (vendored import map) and, on `?debug=1`, vendored
  eruda. Holds the `#controls` panel, the popups (`#shortcuts-modal`, `#legend-modal`,
  `#sourcing-modal`, `#about-modal`, `#image-lightbox`, all `.modal-overlay`), the `#banners`
  stack, the startup `#loading` overlay. An author **byline** ("by Olivier Cornelis", linking
  olicorne.org per locale via the shared `common.byline` i18n key) sits both in `#loading`
  (`.loading-byline`) and inline in the panel header, right of the `neurarium` title
  (`.panel-byline` in `#controls-header`, over an invisible full-row `.collapse-hit` button so a
  row click still toggles the panel while the byline link stays clickable). UI-chrome accent = the `--accent*` palette in `:root`;
  data/semantic colours live in `meta.json`, never here. Also wires the PWA: links
  `manifest.webmanifest` + registers `sw.js`.
- Update check: `js/update-check.js` fetches `version.js` past every cache on load, when the tab becomes visible again and when the connection returns, and reloads once if it names another version (a restored in-memory tab or an offline-fallback launch would otherwise keep showing an old build); offline it does nothing, so the cached build keeps running.
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
  `favicon.svg` (the simplified small rung, legible at 16 px) + `icon-192/512.png` (transparent,
  purpose `any`) + `icon-maskable-192/512.png` + `apple-touch-icon.png` (both opaque on the dark
  `--page-bg`, drawing inside the safe zone), all generated by `tools/icons/brain_icon.py`. Caddy pins the content-type of `.webmanifest` and `.jsonl` (Go's mime table lacks
  both, and `nosniff` then stops the browser guessing; `tools/serve.py` mirrors the `.jsonl` one).
- SEO/social: static `<head>` meta (description, Open Graph, Twitter card, JSON-LD
  `WebApplication`) + a `<noscript>` text fallback in `index.html`; `robots.txt` +
  `sitemap.xml` + `og-image.png` (a copy of `docs/images/screenshot.png`) in `public/`.
  All English (a crawler reads the raw HTML before i18n; no prerender step) and the
  canonical / `og:url` / `og:image` / JSON-LD URLs are **hardcoded to the public domain**
  (update all four spots + `sitemap.xml`/`robots.txt` if it ever changes).
- LLM agents: `public/llms.txt` (https://llmstxt.org) is **generated** by `tools/data_generators/llms_txt.py` from the emitted records (file list, counts, field names, how to read a claim, deep links, "clone, don't crawl", contact link); `tools/tests/test_llms_txt.py` fails when it is stale. Its live companion `/status.json` (`{version, started_at}`) is rendered by `docker/entrypoint.sh` into `/gen` like `app-config.js`, so it exists only in the container (404 under `tools/serve.py`); `started_at` is floored to 5 minutes. It is never a repo file, so never committed. The `/api/` Markdown pages (one per node, stored fields only, `[grade quote_id]` markers + a Sources list per page) are rendered by `tools/render_api.py` in the Dockerfile's `api` stage and baked into the image (never committed, refreshed on each `docker compose build`); Caddy resolves `<path>`, `<path>.md` or `<path>/index.md` and answers anything else with `not_found.md` (the full page list) under a 404; the build context is the repo root, allowlisted by `.dockerignore`. The same stage writes the viewer's effect index `/derived/effects.json` (`render_api.py --effects-out`, `data_generators/effect_index.py`, the only implementation of the effect -> receptors -> drugs join), served by Caddy from `/opt/neurarium/derived` and by `tools/serve.py` from a temp dir rebuilt (atomically) only when `public/data/` changes; never committed, never under `public/`.
- `js/data.js` is the loader's public surface (re-exports + the `BrainData` typedef) over the stage modules in `js/data/`: `load.js` orchestrates `fetch.js`, `quotes.js`, `vocab.js` (meta maps), `anatomy.js`, `receptors.js`, `bindings.js`, `drugs.js` (+ `drug-facts.js`, `pk.js`), `metabolites.js`, `drug-index.js`, `targets.js`, `effects.js`, `addons.js`, with shared `sources.js` / `expression.js` / `localize.js` / `tone.js`; each stage takes the dataset-so-far and adds its slice. Together they: fetch `meta.json` + the `.jsonl` (incl. `quotes.jsonl`, and `metabolites.jsonl` whose records it joins onto each drug's `{id}` refs) + shape files, rehydrates
  each `{quote_id, provenance}` source from the deduplicated `quotes.jsonl` excerpt table
  (`rehydrateQuotes`, mirror of the generator's externalize; see Source provenance); returns a normalized
  `{structures, projections, circuits, projectionGroups, projectionGroupsByKey, receptors,
  targets, drugs, drugsByTarget, addons, addonsBySlot, byId, meta}`. Resolves each node's localized fields + derived
  render props (projection `color`/`sign`, receptor labels + `structureIds`, per-binding
  `targetName`/`actionLabel`/`effect`/`effectColor`/`structureIds`/`flowKind` + the drug's union
  `structureIds`/`flowKinds`/`focusable`/search `keywords`); builds the merged `targets` browse
  list, the `drugsByTarget` + `targetsByStructure` reverse indexes (the latter reads a receptor's
  "Locations" from the region's end, so a structure panel can list what is expressed there carrying
  the very same graded node), and `projectionGroupsByKey` (`${mode}:${key}`).
- `js/shapes.js`: `buildGeometry()` dispatches on type to `buildBlobGeometry`/
  `buildCurveGeometry`/`buildCompositeGeometry`; `mirrorGeometryX` for the left member.
  Self-contained Perlin `fractalNoise` (fBm/ridged/domain-warp). Cortical lobes are cel-shaded
  (`MeshToonMaterial`) domes with a shader-drawn swirl (`injectCortexSwirl`/`CORTEX_SWIRL`, pure
  colour, no relief). `buildBlobGeometry` honours `clip_planes` when `JIGSAW_CLIP.enabled`.
- `js/mesh-codec.js` + `js/baked-meshes.js`: the SDF geometry is meshed author-side
  (`tools/bake_meshes.mjs` -> `public/data/meshes/`) and downloaded rather than rebuilt on every
  load; the runtime mesher stays as a `console.info`-logged fallback for any shape the bake does
  not cover. Format, measurements + the staleness gates: [`docs/BAKED_MESHES.md`](BAKED_MESHES.md).
- `js/arrows.js`: curved tube+cone arrows; colour from `projection.color`, recolourable via
  `setColor`; `tentative` -> dotted. Exposes `arrow.curve`. Each end attaches to the surface point
  *nearest the other end* (`surfaceToward`, a nearest-vertex scan) so the tip lands on real mass
  even for a concave region (the C-shaped caudate). `update(fast)` re-fits; `fast` reuses the
  cached offset + defers the pick-hull rebuild (see Spread performance), `ensurePickGeometry()`
  rebuilds it on demand. `setWidthScale(s)` rebuilds only the shaft/cone width from the cached arc
  (see Arrow width). `setOpacity` clamps to `ARROW_MAX_OPACITY` (0.8), so arrows are always a
  translucent overlay.
- `js/labels.js`: floating name labels (CSS2DRenderer): one hidden label per region, shown on
  hover / show-all / when pinned (`setPinned`). Reads the hemisphere-stripped `base_name` (the
  side is obvious from position).
- `js/circuit-schedule.js`: `scheduleCircuit()` BFS firing order for the circuit
  pulse (no three.js, testable; see Circuit animation).
- `js/circuit-anim.js`: `createCircuitAnimation` renders that schedule as beads
  riding `arrow.curve` + a wash echo on landing (see Circuit animation).
- `js/receptor-markers.js`: `createReceptorMarkers`: gem-dot expression clouds for
  a focused receptor/target. Exports `buildGemCloud` + `GEM_DOT_SIZE` (reused by
  the drug animation). See Receptors & targets.
- `js/receptor-effects.js`: `resolveEffects` (an owner's `effects[]` -> display rows) +
  `readEffectIndex` (resolves the ids of the build-time `derived/effects.json`; the join
  itself is `tools/data_generators/effect_index.py`). Pure, no DOM. See Receptors &
  targets (Effects).
- `js/release-modulation.js`: `resolveModulation` (a receptor's `release_modulation[]` ->
  display rows) + `deriveReleaseChanges` (the drug panel's direction-aware join) +
  `transmitterVars`. Pure, no DOM. See Receptors & targets (Downstream).
- `js/receptor-demographics.js`: `resolveDemographics` (an owner's `demographics[]` ->
  display rows, age first). Pure, no DOM. See Receptors & targets (Across age and sex).
- `js/receptor-variants.js`: `resolveVariants` (an owner's `variants[]` -> display rows),
  `groupByVariant`, `variantsForDrug` (the drug panel's join). Pure, no DOM.
- `js/drug-anim.js`: `createDrugAnimation`: per-drug effect-coloured gem dots +
  surface wash; `matches`. Flow overlay reuses `circuit-anim.js`. See Drugs.
- `js/surface-wash.js`: shared `buildWashShell` + `washStrength` "wash of light"
  primitive (used by circuit echo + drug glow).
- `js/anim-settings.js`: `animSettings`, the single source of truth for decorative-animation
  state (read by every animated module): `enabled` (the **Animations** toggle) + `quality` (0..1
  adaptive) + `speed` (persisted 0.25..4 speed multiplier, the **Animation speed** slider). See
  Settings & toggles + Rendering (adaptive quality).
- `js/web-url.js`: `isWebUrl(url)`, the one http(s) scheme guard every data-derived `href` goes through (DOM-free, so pure modules can import it).
- `js/wiki.js`: `fetchWikiLead(url, lang)` runtime fetch of a Wikipedia lead; locale wins via
  langlinks, English fallback; cached; best-effort (failure -> null).
- `js/tour/` (re-exported by `js/tour.js`): `index.js` holds `createTour({steps, labels, onEnd, seenKey})` (the go / start / stop step machine), `overlay.js` the overlay DOM + bubble drag + veils, `layout.js` target resolution, ring, click-through hole and bubble placement, `scroll.js` scroll-into-view, the scroll arrow, the elastic clamp and scroll-follow. A generic, three.js-free coach-mark
  engine (spotlight ring / caption bubble, viewport-aware placement that never covers the target or
  the 3D scene, resize/scroll reposition, localStorage "seen" gate). The bubble is **drag-repositionable**
  (pointer-drag past a small jitter threshold; a dragged bubble opts out of auto-placement for the step)
  and layered **above any `veil`** so it is never itself dimmed. Forward is a **Next** button (right of Back + Skip; Esc also exits), but it stays **disabled** on a
  hands-on step until the required action is done, so the user cannot fast-forward past a demo. A step is
  passive/caption (Next enabled at once, and a click on the dim backdrop also advances it) or
  **`interactive`** (the blocker gets a clip-path click-through hole so the user's real tap reaches the
  highlighted control; Next stays greyed until that tap). An interactive step advances on that tap, or
  with **`stayAfterTap`** stays put and steps its spotlight aside so the live demo it fired is watchable
  (Next then ungreys to move on). A **gate** step (`gate(signal)`) waits for an app-fired gesture signal
  (rotate, slider, scroll, modal close), then ungreys Next or auto-advances when `gateAdvances`. A step's `target` may be one element or an **array** (a group highlight: the ring spans
  their union, e.g. the four browse sections). Steps glide between positions (snap only on the first
  step + during an active scroll). The app-specific step list is built in `js/boot/tour-steps.js`. It opens with
  how to *read* the app (Legend, then Sources & provenance, then the **Data browser** those grades
  count, whose reading mode motivates the two view toggles: bring the 3D back, fold the panel away),
  then walks the data; the data demos
  are hands-on and follow the data graph (focus a **drug** (olanzapine), read its pharmacodynamics then
  its pharmacokinetics (**Metabolism**, ending in **Pharmacokinetic interactions**), follow one of its
  bindings to a **receptor** (H1), then visit a **structure** (hippocampus) and a **projection system**
  (dopamine, a static group, not a circuit); each opened by tapping the highlighted row via its
  `data-tour-id`, each panel section reached via its `data-tour-sec`),
  each step's `before()` setting the scene (spread, open/collapse a section, reset a prior demo).
  Auto-runs once on a first visit (after the intro settles), forced every load with `?tour=1`, and
  replayed from the About popup's "See the tutorial" button (`#about-tour`).
- `js/changelog.js`: `createChangelog()`, the "What's new" popup (`#changelog-modal`). See
  Versioning / Changelog.
- `js/main.js`: the short boot/orchestration entry: loads data, then hands explicit dependency
  objects to the `js/boot/` modules in order (meshes, arrows, selection, focus, picking, legends,
  views, controls, launch, URL bindings, render loop).
- `js/scene/`: `setup.js` (renderer, camera, lights, OrbitControls, theme repaint), `camera.js`
  (named views + focus tween), `explode.js`, `see-inside.js`, `intro.js`, `quality.js`
  (adaptive quality), `selection.js` (halo + isolate state).
- `js/boot/`: one `wire*()` per UI concern, called once from `main.js`: `controls.js` (Settings
  pane), `toolbar.js` (reset + search popup over `search/index.js`), `shortcuts.js`, `picking.js` (canvas click / tap /
  hover), `header-toggles.js` (theme + panel-only mode), `speed-slider.js`, `tour-steps.js` (the
  guided tour's steps), `url-bindings.js` (data-bound deep-link keys), `legends.js` (anatomy legend +
  colour key + arrow colour mode), plus the boot stages: `meshing.js` (baked / SDF-pool / synchronous
  structure meshes), `focus.js` (`wireFocus`: every `focus*` / `select*` helper, `createSceneFocus` +
  `createPanelOnlyFocus`, the panel cross-links), `views.js` (Data browser + Simulation tabs, the shared
  `nodeNav`), `launch.js` (tour gating, assemble intro, launch changelog, loading dismissal),
  `render-loop.js` (on-demand loop), `query.js` (the `?query` parsed once + its named predicates).
- `js/panel/`: the detail panel: `info.js` (`createInfoPanel`, dispatching to `views/<kind>.js`,
  one `show*()` per node kind), `tabs.js` (detail-tab strip), and the shared row builders
  (`pills.js`, `tooltip.js`, `bindings.js`, `metabolism.js`, `expression.js`, `pathways.js`,
  `sections.js`, `addons.js`, `reference.js`, `format.js`, `dom.js`), plus `pk-interactions.js` (the drug panel's derived Pharmacokinetic interactions subsection, last in Metabolism) and `active-metabolites.js` (the Active metabolites subsection opening its Metabolism section).
- `js/legend/`: the browse sections (`anatomy.js`, `targets.js`, `drugs.js`, `browse.js` for
  enzymes + effects, `key.js`, shared `item.js`). `js/about/`: the popups (`modals.js`) and the
  Sources & provenance tally (`sourcing.js`). `js/search/query.js`: search text folding; `js/search/index.js`: `buildSearchItems`, the search box's row index (every searchable thing + the `data-search` controls, each with its pick action).
- `js/util.js`: dependency-free shared helpers (`groupBy`, `stripSide`, `mirrorId`, `normName`).
- `js/net.js`: `fetchOk(url, init, message)` / `fetchJson`, the one fetch + status check (each caller keeps its own error message).
- `js/grades.js`: the provenance-grade orderings (`GRADE_RANK` stored, `DISPLAY_GRADE_ORDER` display incl. uncertain/unknown) + `strongestGrade`, `shownGrade`, `backed(counts)`.
- `css/`: the stylesheets, linked from `index.html` in cascade order (order matters):
  `tokens.css` (both theme palettes, see Theme), `base.css`, `controls.css`, `modals.css`,
  `tour.css`, `segmented.css`, `search.css`, `labels.css`, `popups.css`, `legend.css`,
  `node-browser.css`, `simulation.css`, `panel.css`, `pills.css`, `panel-drug.css`,
  `loading.css`, `banners.css`. `sw.js` precaches them with the shell
  (`tools/tests/test_stylesheets.py` guards both lists).
- `app-config.js`: `window.__APP_CONFIG__`. This committed copy is the local-dev
  fallback (feature fields empty). In the container `entrypoint.sh` renders an
  env-filled copy into `/gen` and Caddy serves that. Generic name (not
  "analytics-*") so content filters don't 404 it. Carries `ANALYTICS_*`, `DEV`,
  `STARTED_AT`, `sourceUrl`.
- Single-purpose modules, each detailed in its own section below: `js/i18n.js` (I18n, string tables in `js/i18n/en.js` + `fr.js`),
  `js/app-init.js` (Analytics), `js/dev-banner.js` (Dev banner), `js/error-banner.js` (Error
  banners), `js/theme.js` (Theme), `js/loading.js` `createLoadingScreen()` (Loading overlay), `version.js`
  `window.__APP_VERSION__` (Versioning), `js/render-order.js` `DECOR_RENDER_ORDER`
  (Rendering / decoration draw order).
- `js/physchem.js`: `appendPhyschemChips` (the drug panel's "CNS penetration" section: XLogP3, TPSA and BBB chips on `tdm.js`'s `valueChip`) and the `formatLogP` / `formatTpsa` / `formatBbb` wording the node browser shares.
- `js/workup.js`: `groupWorkup` (a drug's workup rows split before / during) and `formatWorkup` (one node as "test, timing"), shared by the drug panel's BETA "Monitoring (French SmPC)" section (`js/panel/sections.js`) and the node browser.
- `js/drug-history.js`: `appendDrugHistory` (a drug's first-approval + withdrawal fact rows) and the `formatApproval` / `formatWithdrawal` wording the node browser shares.
- `js/node-browser.js` (re-exports `js/node-browser/`: `collect.js` the pure `collectNodes`, `view.js` the `createNodeBrowser` UI): the Data browser (`#nodes`): every
  graded knowledge node as one filterable/sortable list, opened as a **detail tab** (deep link
  `#tabs=browser:1`) rather than an accordion section, each row carrying its own backing so its pill
  shows the same source the node's panel pill does (see [`docs/CONTROLS.md`](CONTROLS.md)).
- `js/sim-model.js`: the drug-combination maths (pure, no DOM): `receptorProfile`, `ligandsOf`,
  `pkFlags`, `solveCombination` (NNLS), the `toAxis`/`fromAxis` log axis. Its header lists every
  shortcut it takes; see Simulation (beta). Tested by `tools/tests/sim_model.test.mjs`.
- `js/simulation.js`: `createSimulation`, the Simulation (beta) tab (`#simulation`): the
  assumptions callout, the picked-drug list, the two plots and the profile solver, opened as a
  **detail tab** (deep link `#tabs=simulation:1`) like the Data browser.
- `js/sim-plots.js`: `buildPkPlot` / `buildRxPlot` (+ `formatKi`), the tab's two inline-SVG plots,
  given rows and returning an `<svg>` plus the readers a pointer needs.
- `js/search-rank.js`: `rankMatch(label, keywords, query)`, the pure relevance rank behind the search popup (unit-tested by `tools/tests/search_rank.test.mjs`).
- `js/url-state.js`: `createUrlState()`, the `key -> {read, write}` registry that makes the URL
  fragment a complete description of the UI (open tabs + their order, active tab, popup, sliders,
  toggles, panel layout, open section, search + filter text, camera). Each control registers its
  own pair as it is wired; a view at its default writes nothing and a missing key is never written,
  so links stay short and never override a visitor's persisted preference. Keys +
  the older `#focus*` aliases in [`docs/RUNNING.md`](RUNNING.md).
- `js/prefs.js`: `loadFlag(key, dflt)` / `saveFlag(key, on)` for on/off preferences (panel-only mode, show-metabolites, show-twins, animations) and `loadString` / `saveString` for the rest (theme, animation speed, tour seen, changelog seen, interactions grouping): the only module that touches `localStorage` (storage throws in private mode, so a read falls back to the default and a write is best-effort). `js/i18n.js` keeps its own guarded access, being a classic script that runs before any module; `tools/tests/test_prefs_storage.py` enforces this.

Deployment (`docker/`): `docker-compose.yml` (hardened Caddy), `Dockerfile`
(two-stage: `xcaddy build`s a custom binary with the `caddy-ratelimit` module,
so `docker compose build` needs network; then strips caddy's
`cap_net_bind_service` so `exec` works under `no-new-privileges`),
`Caddyfile` (serves `/srv` on `:8359`, serves `/gen/app-config.js` + `/gen/status.json` for
`/app-config.js` + `/status.json`, `Cache-Control: no-cache` on everything (store but always revalidate ->
cheap `304`s, never stale, and never a heuristically-cached module); `encode` compresses by an
**explicit** content-type list, since Caddy's default omits the baked meshes' octet-stream (so a
NEW kind of asset ships uncompressed until its type is added there); a generous per-`{client_ip}` `rate_limit`
flood guard, keyed via the front proxy's `X-Forwarded-For`/`trusted_proxies`;
security headers incl. CSP),
`env.example`, `entrypoint.sh` (stamps `STARTED_AT`, validates `ANALYTICS_URL`,
derives `ANALYTICS_ORIGIN`, renders `/gen/app-config.js`).

Uncommitted, gitignored, environment-specific: `deploy.sh`, `CLAUDE.local.md`
(per-developer setup notes, incl. the deploy procedure and the Stahl source
material location).
