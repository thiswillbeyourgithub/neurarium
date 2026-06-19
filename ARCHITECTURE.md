# Architecture

A bird's-eye view of how Neurarium is put together, for contributors. It explains
the **shape of the system and the reasoning behind it**; it is intentionally not a
line-by-line file reference.

> [!NOTE]
> Three docs, three jobs, no overlap:
> - **[README.md](README.md)**: what Neurarium is, how to run it, the project layout table.
> - **This file**: the architecture, the data flow, the module graph, the boot
>   sequence, the extension points (the "why" and the "shape").
> - **[CLAUDE.md](CLAUDE.md)**: the exhaustive, always-current map: every file's
>   role, every control, every data field, and the step-by-step recipes for
>   changing the anatomy. When you need specifics, go there.

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
   once in `tools/generate_data.py`; the presentation maps are emitted into the
   data so the viewer never hardcodes a second copy.
4. **Self-describing data.** `brain.jsonl` carries a `meta` record with the colour
   and heading maps, so a consumer (this viewer, or a port to another language)
   needs no out-of-band palette to render it correctly.
5. **Fail loud at generation time.** The generator raises on an unmapped
   projection kind, an unknown circuit structure, or a Wikipedia entry for a
   non-existent structure, so bad data never reaches the browser silently.

## The three layers

```
   AUTHORING                 ARTIFACTS (committed)              VIEWER (browser)
 ┌───────────────┐         ┌───────────────────────┐         ┌──────────────────┐
 │ generate_     │  emits  │ public/data/brain.jsonl│  fetch  │ public/js/*.js   │
 │ data.py       │ ──────► │   meta / structure /   │ ──────► │ + index.html     │
 │ (stdlib only) │         │   projection / circuit │         │ (three.js)       │
 │               │         │ public/shapes/*.json   │         │                  │
 └───────────────┘         └───────────────────────┘         └──────────────────┘
   one definition            plain JSONL + JSON,                renders, no anatomy
   per region/pathway        the data contract                  knowledge of its own
```

The boundary between the middle and right columns is the **data contract**: as
long as the viewer keeps reading the same record shapes, the generator can evolve
freely, and as long as the generator keeps emitting them, the viewer can be
rewritten (or replaced) freely.

### Authoring: `tools/generate_data.py`

Standard-library-only Python. It defines every region once (right-side only for
symmetric pairs; the generator mirrors it to the left), every projection
(bilateral by default, mirrored unless flagged one-sided), every named circuit,
and the registries (`SOURCES`, `WIKIPEDIA`, `PROJECTION_COLORS`, `GROUP_LABELS`).
Running it regenerates `public/data/` and `public/shapes/`. The generated files
are committed so the static site can fetch them directly.

### Artifacts: the data contract

`public/data/brain.jsonl` is one JSON object per line. Five record kinds:

| record | role |
| --- | --- |
| `meta` (first line) | presentation maps: `projection_colors` (kind→arrow colour), `group_labels` (group→legend heading). Makes the dataset self-describing. |
| `structure` | a region: `id`, `name`, `group`, `position`, `color`, `shape_file`, optional `wikipedia`, optional `mirror`. |
| `projection` | a directed pathway: `from`, `to`, `kind`, `label`, `neurotransmitter`, `description`, `sources[]`, optional `bidirectional`, optional `tentative` (speculative; drawn dotted in a separate, off-by-default legend section). |
| `circuit` | a named functional loop: `id`, `name`, `structures[]` (its arrows are derived in the viewer). |

`public/shapes/<name>.json` is one geometry payload per distinct *form* (symmetric
pairs share a single right-side file; the left member reflects it). Three shape
types: `blob` (a noise-deformed ellipsoid), `curve` (a tube swept along a spline),
`composite` (several sub-shapes merged).

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
 (injects umami)             data.js ──fetch──► brain.jsonl + shapes/*.json
                              (no three.js; returns normalized {structures,
                               projections, circuits, byId, meta})
                                  ▲
                                  │ loadBrainData()
                                  │
   main.js ── imports ──►  shapes.js   (buildStructureMesh: blob/curve/composite,
                                        gyrus bump, jigsaw clip)
            ── imports ──►  arrows.js   (buildArrows: curved tube+cone per
                                        projection, colour from projection.color)
            ── imports ──►  labels.js   (createLabels: CSS2D floating names)
            ── imports ──►  three + OrbitControls (vendored)
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
2. A small inline gate injects the eruda debug console only on `DEV=1` or `?debug`.
3. The import map points `three` / `three/addons/` at the vendored copy.
4. `js/main.js` (module) runs: sets up scene/camera/renderer/lights/OrbitControls,
   then `await loadBrainData()`.
5. `loadBrainData()` fetches `brain.jsonl`, parses the records, reads the `meta`
   maps, resolves each projection's `color` from its kind, and fetches every
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
- **Info panel** (`createInfoPanel`): one bottom-right panel showing either a
  *connection* view (a clicked arrow) or a *structure* view (a clicked region:
  name, group, Wikipedia link, and a clickable list of its pathways).
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
