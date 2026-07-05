# Architecture

A bird's-eye view of how neurarium is put together, for contributors. It explains
the **shape of the system and the reasoning behind it**; it is intentionally not a
line-by-line file reference.

> [!NOTE]
> Four docs, four jobs, no overlap:
> - **[README.md](../README.md)**: what neurarium is, how to run it, the project layout table.
> - **This file**: the architecture, the data flow, the module graph, the boot
>   sequence, the extension points (the "why" and the "shape"). Bird's-eye only, no
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
Wikipedia reference. The full kind → collection → tally-key mapping is in CLAUDE.md
("Nodes"); it is not repeated here.

**Every node is sourceable.** Each carries a provenance **grade** (`llm` < `sourced`
< `verified`) and, ideally, a **source**: one quote-level `{corpus, page, quote,
provenance}` pointing at a page of a real corpus (`SOURCE_CORPORA`, e.g. Stahl,
Kandel, the PDSP Ki database). The grade is *data*, and the viewer renders it as a
coloured **pill** on the row/heading that carries the claim: green `✓` verified,
yellow `~` sourced, grey `?` llm, orange `NOSOURCE` when there is no source. A node's
grade is never simply absent from a panel.

**The coverage tally.** `_provenance_stats` (generator) reduces every node to its
single strongest grade and buckets it into **verified** / **sourced** / **missing**,
where *missing* is "no source document at all" (a bare `llm` grade counts as missing:
an LLM asserting something from memory is precisely *no document*). It emits
`meta.provenance_stats`; the About panel and the README headline read it, so the
"% sourced" figure is always a real programmatic count of the shipped data, never
hand-typed. `check_data.py` re-derives the same numbers as a self-consistency gate.
Full mechanics live in CLAUDE.md ("Nodes" + "Source provenance").

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
6. `main.js` builds the meshes (`buildStructureMesh`), the arrows (`buildArrows`),
   and the labels (`createLabels`), wires the controllers (below), and starts the
   render loop.
7. The intro animation plays: regions start exploded and glide back together into
   the assembled brain (skipped when `?explode=` is pinned, e.g. screenshots).

## Rendering and interaction (inside `main.js`)

`main.js` is the only stateful orchestrator. Beyond scene setup and the render
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
