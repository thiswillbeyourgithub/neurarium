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

- `generate_data.py` — single source of truth for the anatomy (stdlib-only,
  offline). Defines every region + projection + receptor once and emits the
  artifacts below; drugs are the exception (authored in `tools/drugs_data.json`,
  read by `_load_drugs`). Every display string is an `{en,fr}` object wrapped by
  `_t()` (see Internationalization).
- `tools/drugs_data.json` — the drug dataset's authored source (JSON list, from
  Stahl's Prescriber's Guide 8th ed.), read by `_load_drugs`, validated + emitted
  to `data/drugs.jsonl`. Edit this to add/change a drug.
- `tools/check_data.py` — stdlib integrity checker over the emitted `public/data/`
  (see Data checks).
- `tools/serve.py` — stdlib dev server sending `Cache-Control: no-store` (roots at
  `public/`; use instead of `python -m http.server`).
- `tools/shot.py` — Playwright screenshot helper (see Screenshots).
- `tools/build_source_worklist.py` — lists drug bindings not yet sourced (each with
  its Stahl page range from the index; input to the source-extraction workflow;
  skips already-sourced, so resumable).
- `tools/apply_source_quotes.py` — applies the extraction workflow's accepted
  quotes onto bindings (re-finds the normalized quote in the drug's page range
  first; reuses `check_data.py`'s `normalize_for_match`; idempotent).
- `tools/apply_nbn_sources.py` — sources each drug's NbN line (Stahl prints it
  verbatim), no agent/judge: greps the line, confirms the dataset `nbn` is a
  substring, writes a `verified` `nbn_sources` entry. Idempotent.
- `tools/pdf_to_pages.py`: splits a PDF into one `<page>.md` per page (the per-page
  text the quote gate checks against); `uv run`, defaults to the Stahl corpus so
  anyone with the book can rebuild it. `--layout` for the heavier OCR engine.
- `tools/build_toc_index.py`: builds `INDEX.md` from a PDF's embedded TOC (generic;
  used for the textbooks + Carlat). `uv run`.
- `tools/build_index.py`: Stahl-specific page index (detects each monograph by its
  `THERAPEUTICS` heading). `uv run`.
- `tools/update_readme_stats.py` — rewrites the README `SOURCING_STATS` block from
  `meta.provenance_stats`; `--check` exits 1 if out of date (CI). Idempotent.
- `tools/fetch_molecules.py` — downloads each drug's molecular-structure SVG into
  `public/data/molecules/<id>.svg` (network, idempotent, polite); writes
  `tools/molecules_sources.json`. See Images.
- `tools/fetch_structure_images.py` — resolves the *url* of each structure's best
  Wikipedia illustration into `tools/structure_images_sources.json` (network,
  idempotent, polite; reuses `fetch_molecules.py` helpers). Downloads no bytes. See Images.
- `tools/molecules_sources.json` / `tools/structure_images_sources.json`:
  provenance/attribution for the two fetch tools (`structure_images_sources.json` is
  read by `generate_data.py` offline; not served).
- `tools/git-hooks/` — repo-tracked git hooks (see Git hooks).

Emitted data (`public/data/`):

- `meta.json` — a single JSON object of presentation maps + tallies (so the
  dataset is self-describing and a port needs no hardcoded palette):
  `projection_colors`, `kind_labels`, `group_labels`, `kind_signs`, `sign_colors`,
  `sign_labels`, `system_flow_kinds` (drug target system -> projection kind),
  receptor maps (`receptor_family_labels` whose key order = legend family order,
  `receptor_class_labels`, `synaptic_labels`), drug maps (`drug_category_labels`
  whose key order = Drugs legend order, `drug_actions` action->{label,effect},
  `drug_effect_colors`, `drug_effect_labels`, `drug_targets` = the merged
  binding-target map: every non-receptor target + every receptor id),
  `target_type_labels` / `target_type_colors`, `source_corpora`, and
  `provenance_stats` (the programmatic sourcing tally; see Source provenance).
- `structures.jsonl` — one region/line: `id`, `name{en,fr}`, `base_name{en,fr}`
  (hemisphere-stripped, for the legend row), `group`, `position`, `color`,
  `shape_file`, `classification_provenance`, optional `wikipedia` (+
  `wikipedia_provenance`), optional `structure_image` (a hot-linked Wikimedia url;
  both hemispheres share it).
- `projections.jsonl` — one pathway/line: `from`, `to`, `kind`, `label{en,fr}`,
  `neurotransmitter{en,fr}`, `description{en,fr}`,
  `sources[{citation,url,provenance}]` (not translated), optional `bidirectional`,
  optional `tentative` (speculative; dotted arrow in an off-by-default section).
- `circuits.jsonl` — one functional loop/line: `id`, `name{en,fr}`,
  `structures[ids]` (arrows derived in the viewer), optional `description{en,fr}`
  + `sources`.
- `projection_groups.jsonl` — one legend pathway row/line, promoted to a sourced
  structure so it can open a panel: `id` (`<mode>_<key>`), `mode` (kind|sign),
  `key` (a kind or a sign), `name{en,fr}`, `description{en,fr}`,
  `classification_provenance`, optional `wikipedia` (+ provenance) + `sources`. One
  record per group in BOTH colour modes (7 per-transmitter + 3 per-sign); member
  pathways are derived in the viewer (kind/sign match), not stored.
- `receptors.jsonl` — one receptor/line: `id`, `name` (technical, language-
  neutral), `family`, `neurotransmitter{en,fr}`, `receptor_class`
  (ionotropic/metabotropic/chaperone), `sign` (excit/inhib/modulatory), `synaptic`
  (pre/post/both), `locations` (structure *base* ids, expanded to both
  hemispheres), optional `ubiquitous:true` (brain-wide -> lights every structure),
  `classification_provenance`, optional `description{en,fr}` + `wikipedia` (+
  provenance). Empty locations + no description = a deliberate stub (listed, not focusable).
- `drugs.jsonl` — one drug/line: `id`, `name` (technical), `categories`, optional
  `nbn{en,fr}` (+ `nbn_sources[{corpus,page,quote,provenance}]`), `bindings[]` (each: `target`,
  `action`, optional `effect` override, optional `note{en,fr}` or "TODO", optional
  `tentative`, optional `sources[{corpus,page,quote,provenance}]`),
  `sources[{citation,url,provenance}]` (the drug-level Stahl citation), optional
  `wikipedia` (+ provenance), optional `structure_image` (vendored
  `data/molecules/<id>.svg`, set only when the file exists), `focusable` (false if
  no bindings).
- `molecules/<id>.svg` — vendored per-drug molecular-structure diagrams (from
  `fetch_molecules.py`). Structure illustrations are NOT vendored (hot-linked, see Images).

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

Viewer (`public/`):

- `index.html` — page shell: loads three.js (vendored, import map) and, on
  `?debug=1` only, vendored eruda. Holds the bottom-left collapsible `#controls`
  ("neurarium") panel and the `#banners` stack (see Controls).
- `js/data.js` — fetches `meta.json` + the `.jsonl` files + all shape files;
  returns a normalized `{structures, projections, circuits, projectionGroups,
  projectionGroupsByKey, receptors, targets, drugs, drugsByTarget, byId, meta}`.
  Resolves each projection's `color`/`sign`, each receptor's labels +
  `structureIds`, each drug's localized fields + per-binding `targetName`/
  `actionLabel`/`effect`/`effectColor`/`structureIds` + the union `structureIds` +
  `flowKinds` + `focusable` + search `keywords`. Builds the merged `targets` browse
  list (receptors + non-receptor drug targets, one normalized focusable entry each)
  and `drugsByTarget` (reverse index target -> drugs + resolved binding).
  `projectionGroupsByKey` indexes groups by `${mode}:${key}`. `meta` carries the
  localized presentation maps.
- `js/shapes.js` — `buildGeometry()` dispatches on type to `buildBlobGeometry` /
  `buildCurveGeometry` / `buildCompositeGeometry`; `mirrorGeometryX` for the left
  member. Self-contained Perlin noise + `fractalNoise` (fBm/ridged/domain-warp).
  Cortical lobes are smooth domes rendered cel-shaded (`MeshToonMaterial`) carrying
  a painted-on swirl motif (`injectCortexSwirl` / `CORTEX_SWIRL`: domain-warped
  noise contour "ink" lines, pure colour, no relief). `buildBlobGeometry` honours
  `clip_planes` when `JIGSAW_CLIP.enabled`. No deps beyond three.js.
- `js/arrows.js` — curved tube+cone arrows; colour from `projection.color`,
  recolourable via `setColor` (colour-mode switch); `tentative` -> dotted tube via
  a small local `mergeIndexedGeometries`. Exposes `arrow.curve`.
- `js/labels.js` — floating structure-name labels (CSS2DRenderer): one hidden
  label per region, shown on hover / show-all / when pinned (`setPinned`).
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
- `js/wiki.js` — `fetchWikiLead(url, lang)` runtime fetch of a Wikipedia lead;
  locale wins via langlinks, English fallback; cached; best-effort (failure -> null).
- `js/main.js` — scene/camera/renderer/lights/OrbitControls; explode +
  transparency; `createIntroAnimation`; auto-rotate; hover raycasting; arrow +
  structure picking; `createInfoPanel`; the search; `buildLegend` (Structures +
  Projections rows, returns the shared focus-greying callback), `buildLegendKey`
  (static key), `buildTargetLegend`, `buildDrugLegend`; the on-demand render loop.
- `app-config.js` — `window.__APP_CONFIG__`. This committed copy is the local-dev
  fallback (feature fields empty). In the container `entrypoint.sh` renders an
  env-filled copy into `/gen` and Caddy serves that. Generic name (not
  "analytics-*") so content filters don't 404 it. Carries `ANALYTICS_*`, `DEV`,
  `STARTED_AT`, `sourceUrl`.
- `js/app-init.js` — injects the umami tag if configured; no-op otherwise.
- `js/i18n.js` — internationalization (classic script, loaded early). See I18n.
- `js/dev-banner.js` — when `DEV=1`, shows the WIP banner. See Dev banner.
- `js/error-banner.js` — surfaces failures as red dismissible banners. See Error banners.
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
`docs/screenshot.png` (the README hero shot).

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
(used by `js/main.js` for the data-load failure). Banners stack; each has a ×;
identical messages dedupe into one `(×N)`; a `MAX_BANNERS` cap. A `ResizeObserver`
republishes the stack height to `--banners-height`, which `#status` offsets against.

## Controls

Everything lives in one collapsible **"neurarium" panel bottom-left** (`#controls`;
header `#controls-toggle` collapses the whole body). The body splits into a
`#settings-pane` and a `#details-pane` (`#info-body`), switched by a `#panel-tabs`
bar of **browser-style tabs**: a pinned **Settings** tab (`#tab-settings`, always
first) showing the controls, plus one closable tab per opened detail in the
scrollable `#detail-tabs` strip (see Detail tabs + Info panel). From the top the
settings pane holds, always visible, the `#lang-switch` (EN/FR) + a reset/search/
keyboard-shortcuts `.toolbar-row`, then **seven** nested collapsible sections:

- **Controls** (`#controls-settings`): the **Separate** + **Transparency** sliders,
  then **Auto-rotate**, **Show all names**, **Show projections**, **See inside**
  checkboxes. Ships **open** and toggles **independently** of the accordion (its own
  `wireCollapse`), so a slider tweak never collapses the section you were browsing.
- Then six **single-open-accordion** sections (opening one closes the others):
  **Structures** (`#structures`, region rows by group), **Projections**
  (`#projections`, header "Projections & Circuits": the colour-mode switch, pathway
  rows, Circuits, Hypothetical pathways), **Receptors & targets** (`#receptors`),
  **Drugs** (`#drugs`, with `#drugs-filter`), **Legend** (`#legend`, a static key),
  **About** (`#about`).

The accordion is a list of `{toggle, body}` in `wireControls`; `wireCollapse` takes
an `onToggle(open)` and `setSection()` sets state programmatically. Searching swaps
`#search` in place of `#controls-main`. Section bodies ship `hidden`; opening one
slides it in (`section-slide-in` 200ms, disabled under `prefers-reduced-motion`).

**Pan-aside.** While the body is expanded the brain is pushed clear of the panel
(`updatePanelPan`, gated on the panel being visible so `?ui=0` is unaffected;
recomputed on the orientation media-query flip + a `ResizeObserver`), applied via
`focus.setScreenOffset` -> `PerspectiveCamera.setViewOffset` (a render-time offset
eased in `focus.tick`, so it survives rotation/zoom and rescales on resize):
- **portrait**: `#controls` is full-width, bottom-half (`max-height: 50vh`); brain
  pushed up.
- **landscape**: `#controls` is a left sidebar (`width: clamp(240px, 25vw, 420px)`),
  full vertical height when expanded (gated `:has(#controls-body:not([hidden]))` so
  a collapsed panel stays a small header); brain pushed right.

**Scroll model (both orientations).** The panel is a flex column with
`overflow:hidden`, so the panel never scrolls; its top chrome (header, lang switch,
toolbar, detail tabs) is pinned and exactly one inner region scrolls
(`#controls-main`, or `#details-pane` / `#search` when shown). A `min-height:0` flex
chain makes an open accordion section show at its **natural height** and the whole
list scroll (lower collapsed headers below the fold). Flex-display rules are scoped
`:not([hidden])` so a hidden pane stays `display:none`.

### Settings & toggles

- **Auto-rotate**: spins the camera (OrbitControls `autoRotate`). **On by default**;
  switches off the moment the user picks content (any pick routed through the
  selection controller, via `selection.onPick(stopAutoRotate)`). Deep links force it
  off unless `?autorotate=1`.
- **Show all names** (`#toggle-names`, off): forces every label on. Key **n**;
  `?names=all`.
- **Show projections** (`#toggle-projections`, checked): unchecking hides every
  arrow (`projVis`; composes with the Hypothetical toggle).
- **See inside** (`#see-inside`, off): hides structures on the camera-facing side so
  deep nuclei aren't blocked. `createNearCull` recomputes the hidden set every frame
  from the live camera/`controls.target` (a structure hides once its centre is more
  than `NEAR_CULL_BIAS` past the centre plane toward the camera); snapshots
  visibility on enable to restore exactly; composes with `?only=`; arrows stay
  visible. `cull.tick()` runs after `controls.update()`.
- **Arrow colour-mode** (`#color-mode`, in `#projections-actions`, default
  **Neurotransmitter**): **Neurotransmitter** colours each arrow per molecule
  (`projection.color`); **Potential** recolours by coarse **sign**
  (`projection.signColor`: excit red, inhib blue, modulatory grey). Maps from meta
  `signColors`/`signLabels`. `setColorMode` recolours in place
  (`ProjectionArrow.setColor`) and rebuilds the Projections section (one row per sign
  vs per transmitter); the focus-greying callback is re-pointed each rebuild.
  `buildLegend` preserves `#projections-actions` across rebuilds.
- **Separate** slider (0..1; explode internally): pushes each region radially out
  (`EXPLODE_STRENGTH`). The camera auto-zooms so the **whole brain keeps a constant
  apparent size**: the handler calls `focus.zoomForExplode(amount)`, scaling the
  camera->target distance by the ratio of the assembly's outer radius
  (`boundingRadiusAt`, folding each region's own radius in) at the new vs last amount.
- **Intro** (`createIntroAnimation`): on a plain load the regions start blown out and
  glide together (like dragging Separate 1->0), the camera following
  (`zoomForExplode`) and sweeping `INTRO_ROTATION_TURNS` (0.75), finishing together
  (`INTRO_DURATION_MS`, easeInOutCubic). Drives the slider; suspends + restores
  auto-rotate; cancelled when the user grabs the slider; skipped when `?explode=` is
  pinned. When the dev banner is up (`__APP_CONFIG__.dev === "1"`), the brain settles
  lower + further back (`DEV_BANNER_DROP`, `DEV_BANNER_UNZOOM`).
- **Transparency** slider: value = material opacity (depth-write disabled while
  translucent). Owned by the selection controller, so it composes with isolate dimming.

### Selection / halo + isolate (`createSelection`)

Single source of truth for what is highlighted/focused.
- Picking a structure (click/tap or structure search result) gives it a soft halo
  (`mesh.userData.halo`); double-click isolates it instead. Picking an arrow halos it
  (`ProjectionArrow.setHalo`); structure + arrow halos are mutually exclusive.
- A **Structures legend row** toggles that structure (both hemispheres) into the
  **isolate** set and opens its detail tab (`selectStructure`, on isolate-on only;
  toggle-off opens nothing); a **category heading** toggles the whole group (isolate
  only). While the set is non-empty, others drop to `DIM`, arrows not touching an
  isolated structure fade (`ProjectionArrow.setOpacity`), the legend greys non-
  isolated rows (`.dimmed`/`.selected`). Additive.
- **Circuits** subsection rows isolate exactly that circuit (`selection.setCircuit`
  pins an explicit arrow set), start the traveling-pulse (see Circuit animation), and
  open its detail tab (`showCircuit` via `focusCircuit`). Re-click clears.
- **Projections** rows (one per group, following the colour mode) isolate only that
  group via `setCircuit` (pins the group's arrows + their endpoints; dims every
  structure, so its structure rows grey and only the group row lights), and open a
  detail tab (`showProjectionGroup` via `focusProjectionGroup`; the row's `dataKey`
  is `kind:<kind>` / `sign:<sign>`). Built from non-tentative projections.
- **Hypothetical pathways** subsection (off by default): a "Show speculative (N)"
  toggle reveals every `tentative` arrow (dotted). Visibility composes with **Show
  projections** via `createProjectionVisibility` (an arrow shows only when
  projections aren't globally hidden AND it is established or its section is on).
- The **reset** button + a **double-click on empty space** fully clear (halos +
  isolate + circuit). Framing a connection/arrow just swaps the halo.

### Structure names

Hover (or tap) shows a name label; tapping empty space clears. **Selecting** a
structure also **pins** its name (`selection.onHighlight` -> `labels.setPinned`), and
hovering another region *adds* its label. The hover pick (`pickHover`) is focus-aware:
while something is focused, a focused region the ray passes through wins over a nearer
non-focused one. Labels are boxless: white glyphs outlined in the region's own colour
(`--label-color`) + a black halo.

### Legend sections

- **Structures** (`#structures`): rows by group, generated by `buildLegend` into
  `#structures-body`. Row click isolates + opens the detail tab (`onPickStructure`,
  gated on `selection.isIsolated`); heading isolates the group.
- **Projections** (`#projections`): same `buildLegend` into `#projections-body`,
  preserving `#projections-actions` (the colour-mode switch) first. Below: the
  Projections rows (per transmitter, or per sign in Potential mode), the Circuits
  section, and the off-by-default Hypothetical pathways toggle. `buildLegend` fills
  both Structures + Projections and returns one shared focus-greying callback.
- **Legend (the key)** (`#legend`): a *static* colour/symbol key built once by
  `buildLegendKey` from meta (so colours never drift): the expression gem dots (a
  swatch per sign), the per-drug effect dots + wash (boost/block/modulate), and a
  dotted speculative pathway. Each heading carries a `.legend-caption`.
- **Receptors & targets** (`#receptors`): see Receptors & targets.
- **Drugs** (`#drugs`): see Drugs.
- **About** (`#about`): a blurb (made by Olivier Cornelis + Claude), an "open an
  issue" line (link to `cfg.sourceUrl + "/issues"`, dropped unless `sourceUrl` is a
  repo-like URL with a path), a **Source code** link (`cfg.sourceUrl`, http(s) only),
  a **licence** line (AGPL-3.0), a **CC BY-SA attribution** line (Wikipedia
  descriptions + molecule images), and the **Sources & provenance** block
  (`#about-sourcing`, `buildAboutSourcing` from `data.meta.provenanceStats`: the grade
  key + the coverage tally). This block is the single place explaining the whole
  sourcing system (see Source provenance). The README mirrors the issue invitation +
  coverage table.

### Input

- **Touch / mouse**: one finger / left-drag rotates; pinch / wheel zooms; two-finger
  drag pans (OrbitControls). **Shift + wheel** drives the Separate slider instead of
  zooming (a capture-phase `window` listener swallows it on `shiftKey` and dispatches
  the slider's `input`).
- **Keyboard shortcuts** (`wireShortcuts`, single-key, ignored while typing and for
  Ctrl/Cmd/Alt combos): **n** names, **s** spread/assemble, **l** Structures, **p**
  Projections, **k** Legend, **c** See inside, **r** Receptors, **m** Drugs, **f**
  search, **Tab**/**Shift+Tab** cycle detail tabs (`tabs.cycle`, re-applying a
  detail's focus), **Esc** peels one layer (active detail tab -> else clear any
  focus/isolate/circuit -> else close search / collapse the open section). Arrow keys
  browse the open section's rows + Enter activates (see below). Each maps by clicking
  the same DOM element a mouse user would; a handled key calls `preventDefault`.
- **Section row navigation** (`sectionNav`): with a section open, **ArrowDown/Up** move
  a roving `.kbd-active` highlight through its action buttons + `.clickable` rows, and
  **Enter** activates (a plain `.click()`). Rows recomputed each key (skips
  hidden/disabled), wraps, cleared on section change/close + Esc (`sectionNav.reset()`).
  Keys swallowed only when a section handled them; typing in the drug filter keeps the arrows.
- **Toolbar icon-row** (top of the panel, `justify-content: space-between`):
  keyboard-shortcuts (left, opens the help popup), reset (center, recenters + reframes
  the brain), search (right, swaps `#search` in place, not a popup).
- **Search**: filters structures (by name), connections (by label), receptors (name /
  neurotransmitter / system), drugs (name / category / target). Picking centers/frames
  + opens the matching panel (a receptor/drug pick focuses it exactly like its legend
  row). Only **focusable** receptors/drugs are searchable; receptor rows show a `· tag`
  (neurotransmitter), drug rows their category. Matching is case- + accent-insensitive
  (`foldText`: lowercase + NFD strip diacritics, also used by `#drugs-filter`) over the
  label + hidden `keywords`. A structured `field:"value"` filter (`parseSearchQuery` +
  `SEARCH_FIELDS`): `class:"SNRI"` / `nbn:"..."` keeps drugs whose class/nomenclature
  matches (the field name is folded, so French `classe:` / `nomenclature:` work); a
  field filter lists the whole class. A drug panel's **Class** + **Nomenclature** are
  clickable and build such a query (each `data.drugs` item carries a folded `fields`
  map; `info.onSearch` -> `openSearchWithQuery`). A **"?"** button toggles
  `#search-syntax`. Connection results carry a hemisphere tag (`connectionSideTag`
  R/L/L↔R). **Ctrl/Cmd+F** intercepts the native page-find, expands the panel + opens
  search. **Esc** closes. Results are keyboard-navigable (`activeIndex`/`highlight`:
  first row pre-highlighted, ArrowUp/Down wrap, hover syncs, Enter activates).
- **Keyboard-shortcuts help popup** (`#shortcuts-modal`, `wireShortcutsHelp`): a
  centered dialog over a `.modal-overlay` backdrop, rows generated from a list
  mirroring `wireShortcuts` (so it can't drift), labels from `shortcuts.*` i18n.
  Opened by the keyboard button or **?**; closed by ×, backdrop, or Esc (routed first
  when open). Needs a `.modal-overlay[hidden]` rule.

### Detail tabs (`createPanelTabs`)

Owns the `#panel-tabs` strip + which pane shows; it does **not** render a detail or
apply its 3D focus. The `select*` layer (`selectStructure` / `selectConnection` /
`focusTarget` / `focusDrug` / `focusCircuit` / `focusProjectionGroup`) renders +
focuses, then calls `openDetailTab(key, title, reopen)`; the `reopen` thunk re-runs
that same `select*`, so clicking a tab restores both content and scene with no
duplicated logic. Keys dedupe one tab per thing (`structure:` / `connection:` /
`target:` / `drug:` / `circuit:` / `group:`); `MAX_TABS` bounds the strip. Closing the
active tab falls back to a neighbour (re-applying its focus) or, if last, to Settings +
`onEmpty()` (`tabs.setOnEmpty(() => selection.clear())`). Interactions: click to
activate, × to close, **long-press (~450 ms) then drag** to reorder (a move before the
hold = scroll), **wheel / touch-drag** to scroll the strip. The strip is
`touch-action: none` and the drag-scroll is JS-driven (a native pan would fire
`pointercancel` mid-hold and kill the long-press); a real drag sets a one-shot
`suppressClick`. `panel.closeTab` labels the × for a11y. **Tab**/**Shift+Tab** cycle
via `tabs.cycle`; **Esc** closes the active tab via `tabs.closeActive` (returns false
when only Settings is active, so Esc falls through to its other duties).

### Info panel (`createInfoPanel`, into `#info-body`)

Pure rendering of a connection / structure / receptor / target / drug / circuit /
projection-group view; the active detail tab drives which shows. Opening the tab +
applying focus is the `select*` caller's job, so each `show*()` is reused unchanged
whether first picked or re-shown. An empty-space click returns to Settings
(`tabs.showSettings()`; detail tabs stay).

Every source/reference shows a **provenance pill** (`makeProvenancePill`, see Source
provenance) with a hover/tap tooltip via the shared `withTip(trigger, text)` helper.
The bubble is appended to `document.body` (escaping the panel's overflow clipping +
any dimmed row's opacity), `position: fixed` in viewport coords (centred above the
trigger, flipped below / clamped if needed; `place()` subtracts a
transformed/filtered ancestor's offset via `fixedContainingBlock`; re-places on
scroll/resize). On a pointer device hover/focus reveals it and clicking the badge pins
it open (text selectable; hovering the bubble keeps it open via a grace timer); a
pinned tip closes on re-click, an outside `pointerdown`, or opening another. On touch
(no `(hover: hover)`) only the click-toggle path runs. Only one tip is open at a time
(a shared `openTip` closes the previous, tearing down its listeners). Tooltip text
shows the concrete source first, the tier-grade explainer underneath. Pill tooltips
are `info.provNone/provLlm/provSourced/provVerified`.

Views:
- **connection**: label, route (`from → to`, `↔` bidirectional), kind +
  neurotransmitter, description, sources (http(s) url as link else plain text; a
  provenance pill per citation). Arrow picking (`pickArrowAt`) beats the region behind.
- **structure** (`showStructure`): name, group heading, a Reference row (Wikipedia
  link + pill, else `NOSOURCE`), then (when the link resolves) the live Wikipedia lead
  as a `sourced` description (structures carry no baked description; fetch-only), a
  **Source** row grading the region's anatomy (`classification_provenance`), and the
  pathway list. Each connection row: kind swatch, direction glyph (`→`/`←`/`↔`), the
  other endpoint, and the pathway's summary pill
  (`makeProvenancePill(proj.provenance, citationsTip(proj.sources))`, `proj.provenance`
  = the strongest grade over `proj.sources`, resolved once in `js/data.js`). Clicking a
  row jumps to that pathway (`onConnection`). "No mapped connections yet." otherwise.
- **receptor / target / drug / circuit / projection-group**: see their sections.

A click that misses everything (empty space) closes the panel. **Double-click**: on a
structure isolates it; on empty space recenters.

### Camera focus (`createCameraFocus`)

All framing (reset, search, panel buttons) goes through one smooth tween: it moves the
orbit pivot + camera distance but keeps the view direction, is advanced once per frame,
and is cancelled the moment the user grabs the controls. It also owns the screen offset
(`setScreenOffset(x,y)`, eased in `tick`) used for the pan-aside. After focusing a
single structure, moving the Separate slider keeps it centered: `createCameraFocus`
remembers it (`focused`) and `reaimFocused()` re-points the pivot at its exploded
position (the camera rotates in place). Framing a connection or the whole brain clears
the tracked structure.

## Rendering

The render loop (`renderer.setAnimationLoop`) is **on-demand**: each frame runs the
cheap per-frame checks (advancing tweens + `controls.update()`), but the expensive part
(`cull.tick()` + `renderer.render()` + `labels.render()`) is **skipped** unless a
render is needed; when idle the canvas holds its last frame. A render is triggered when:
- an animation is running: each per-frame controller's `tick()` returns a boolean "did I
  animate" (`intro`, `focus`, `circuitAnim`, `receptorMarkers`, `drugAnim`); any true
  keeps drawing;
- the camera moved: `controls.update()` returns true while damping settles or
  auto-rotate spins;
- `invalidate()` was called: wired to OrbitControls' `change`, window `resize`, and a
  catch-all over every user input (capture + passive, observe-only).

Adding a new per-frame controller? Make its `tick()` return whether it animated, or it
runs but never triggers a repaint. Screenshots are unaffected (the loop renders the
settled frame then idles).

## Circuit animation

Isolating a circuit plays a traveling-pulse: a volley of glowing beads rides each arrow
source -> target, firing in sequence and looping, so a curated loop reads as signal
flowing around it. Split in two:

- **`js/circuit-schedule.js`** (ordering, no three.js, testable). `scheduleCircuit`
  treats the circuit's arrows as a directed graph (node = structure, edge = arrow,
  `from -> to`); a BFS spreads activation from seeds and each arrow's firing slot
  (`phase`) is the BFS depth of its tail. The seed per component is the `group=="lobe"`
  node (cortex), else highest-out-degree, else any. L/R symmetry is enforced: the seed
  set is mirror-completed (`mirrorId`) and the BFS is multi-source, so mirror-paired
  nodes get equal depth (works whether the circuit is two disjoint L/R loops or one
  component joined through a midline hub). An off-cycle feeder branch fires when
  activation reaches its tail, else at the top of the cycle.
- **`js/circuit-anim.js`** (rendering). `createCircuitAnimation` turns each slot into an
  additive bead riding `arrow.curve` (rebuilt on every explode). `STEP_MS` is the
  per-slot duration. Each arrow fires a burst keyed off the projection's `sign`
  (`BURST`: excitatory = more/faster/brighter, inhibitory = fewer/slower/dimmer,
  modulatory between); beads are spaced `gap` and advance at `speed`×, `scale`/`bright`
  size them; a bead hides while its arrow is hidden. As a bead lands it fires a wash echo
  over the target region (the shared `buildWashShell`, seeded at the impact point
  `arrow.curve.getPoint(1)` in the target's local frame, in the pathway's colour,
  `WASH_MS`, brightness keyed off the sign).

Lifecycle (`js/main.js`): the row calls `selection.setCircuit(...)` then
`circuitAnim.play(circuitArrows)`. Stopping is driven off the selection state:
`createSelection`'s `onIsolate` is multi-subscriber and the animation subscribes a
watcher that calls `stop()` whenever the live pinned-arrow set is no longer exactly the
animating circuit (`circuitAnim.matches`). So a clear, a different circuit, a
projection-group focus, or a legend isolate all stop it; merely highlighting a structure
keeps it. The animation is circuit-only (a projection-group focus uses `setCircuit` but
never `play`).

## Circuit + projection-group panels

A Circuits row and a Projections (per-pathway) row each open a **sourced detail tab**,
the same way a structure/drug row does (this is why projection groups are a real data
structure and circuits gained a description + sources). Member pathways are never stored:
a circuit's are the projections with both endpoints in its set, a group's are the
projections whose `kind`/`sign` matches `key`. `js/data.js` localizes both and indexes
the groups by `${mode}:${key}` (`projectionGroupsByKey`).

- `showCircuit`: the loop's description, its structures (deduped to bases, each clickable
  to jump via `onStructure`), its member pathways, its sources.
- `showProjectionGroup`: a by-transmitter / by-effect heading, the description (live-
  refreshed from Wikipedia), the reference link, the member pathways, the sources.
- Both reuse a shared `pathwayRow` / `appendPathwayList` helper (also used by
  `showStructure`), so the row markup (swatch + label + summary pill + jump) lives once.
- `focusCircuit` / `focusProjectionGroup` mirror `focusDrug`: isolate (a circuit also
  `circuitAnim.play()`s its pulse; a group is a static pinned-arrow focus), show the
  panel, open the tab (`circuit:` / `group:`) with a reopen thunk that recomputes
  meshes/arrows. `tabs.setOnEmpty` clears the focus when the last closes. i18n:
  `circuit.heading/structures/pathways`, `group.kindHeading/signHeading/pathways`.

## Receptors & targets

A focusable section listing the merged `data.targets` = every receptor (from
`receptors.jsonl`, authored as `RECEPTORS` in `generate_data.py`) **plus** every
non-receptor drug target from the meta `drug_targets` map (transporters, enzymes, ion
channels, receptor groups), so a target like SERT is explorable on its own. Built by
`buildTargetLegend`, grouped by neurotransmitter **system** (`receptor_family_labels`
key order, then "Other / non-aminergic"). The two sources are normalized to one shape in
`js/data.js`.

- A receptor row's swatch = its excit/inhib/modulatory **sign** colour; a non-receptor
  row's = its **type** colour (`target_type_colors`) + a muted type tag. Clicking a row
  **focuses** it: dims the brain to its regions via `selection.setCircuit(regionMeshes,
  [])` (no arrow pin, so pathways fade and the dots are the only bright thing) and calls
  `createReceptorMarkers.show(regionMeshes, colour)`.
- **Markers** (`js/receptor-markers.js`): dense additive glowing **gem dots** over each
  region's surface (a `THREE.Points` cloud sampled from the structure mesh's own
  geometry and parented to it, so they track explode/mirror and vanish when the mesh
  hides; a bright core + a 4-point sparkle-star sprite; count scaled per region by
  surface area; gently pulsed). The single-cloud builder is `buildGemCloud` (+
  `GEM_DOT_SIZE`), reused by the drug animation. Stopped off the selection state via an
  `onIsolate` watcher (`createReceptorMarkers.matches`).
- Panels: a receptor opens `showReceptor` (system, Wikipedia link, the description
  live-refreshed from Wikipedia, the classification facts ending in a **Source** row
  grading them, the region list or "Throughout the brain" for ubiquitous); a non-receptor
  target opens the lighter `showTarget` (system, Wikipedia link or `NOSOURCE`, the
  type + system facts ending in a Source row, the region list). Both then carry an
  **Interacting drugs** section (the drugs acting on this target, from `drugsByTarget`,
  grouped by primary drug category, each row a net-effect glyph (green **+** / red **−** /
  purple **≈**), dimmed + italic "· speculative" when tentative, and the binding's source
  pill (`bindingProvenancePill`, the *same* resolved binding shown on the drug panel, so a
  drug<->target link carries its source on both with no duplication); clicking a drug row
  focuses it via `info.onDrug`). Both make each **"Found in" region row clickable** (jumps
  to that structure via `info.onStructure` -> `selectStructure`). A stub receptor / an
  unlocated target renders muted, not clickable.

Receptor data: `_receptor_record` validates every family/class/sign/synaptic key + every
location base. `locations="ALL"` -> `ubiquitous`. `classification_provenance` defaults
`llm`, overridable in `RECEPTOR_PROVENANCE`. The receptor locations drove the
`brainstem_nuclei` group (raphe, locus coeruleus, VTA). A non-receptor target's
`type`/`system`/regions/`wikipedia` are authored in `DRUG_TARGETS`.

## Drugs

A focusable Drugs section showing, per drug, what it does to the brain. Data is from
**Stahl's Prescriber's Guide (8th ed.)**, extracted **strictly from the dump** (only
interactions literally stated; gaps left as TODO / no binding).

- **Data.** The 158 drugs live in `tools/drugs_data.json` (too large to inline), read by
  `_load_drugs` (a missing file is a warning). Vocabularies are defined once in
  `generate_data.py`: `DRUG_CATEGORY_LABELS`, `DRUG_ACTIONS` (action -> {label, net
  `effect`}), `DRUG_EFFECT_COLORS`/`DRUG_EFFECT_LABELS` (boost emerald / block rose /
  modulate violet), `DRUG_TARGETS` (non-receptor targets, each `{name{en,fr}, type,
  system, regions[bases], optional wikipedia}`, `type` a `TARGET_TYPE_LABELS` key).
  `_build_drug_targets` merges `DRUG_TARGETS` with every receptor id (so a binding can
  target a coarse target like `sert` or a specific receptor like `5ht2a`) and emits it as
  `meta.drug_targets`. `_drug_record` validates category/target/action/effect + rejects
  duplicate ids and attaches the constant `STAHL_SOURCE`. A binding's net `effect`:
  agonist / reuptake-inhibitor / releaser / enzyme-inhibitor / PAM -> **boost**;
  antagonist / inverse-agonist / NAM / blocker -> **block**; partial-agonist / modulator
  -> **modulate**.
- **Animation** (`js/drug-anim.js`). Clicking a drug row (`buildDrugLegend`, grouped by
  category, with the live `#drugs-filter`) focuses it: dims to the union of its targets'
  regions via `selection.setCircuit(regionMeshes, flowArrows)` and calls
  `createDrugAnimation.show(drug, meshById)`, which scatters a gem cloud (`buildGemCloud`)
  per binding coloured by that binding's net effect, pulsing per effect (boost
  fast/bright/swelling, block slow/dim, modulate between), and under the dots breathes a
  surface wash in the same colour (`buildWashShell`, per-effect period + `washGain`).
  Stopped off the selection state via an `onIsolate` watcher (`createDrugAnimation.matches`).
- **By-mechanism flow overlay** (reuses `js/circuit-anim.js`). The focus also rides
  flowing beads along the projections of the drug's target transmitter system(s) (an SSRI
  lights the serotonergic ascending fan, an SNRI the noradrenergic + serotonergic, a D2
  antipsychotic the dopaminergic). The mapping is data: `generate_data.py` emits
  `system_flow_kinds` (target `system` -> projection `kind`, restricted to the diffuse
  ascending systems with a modeled source nucleus: serotonergic, adrenergic ->
  noradrenergic, dopaminergic, cholinergic; glutamate/GABA left out so the overlay is a
  drug-specific fan). `js/data.js` resolves each drug's `flowKinds`; `focusDrug` filters
  arrows (`flowArrowsOf`), pins them via `setCircuit` and `circuitAnim.play()`s them.
  Stopped by the same `circuitAnim` `onIsolate` watcher. A drug with unmapped systems pins
  no arrows -> dots + wash only. (This is why the dataset carries the ascending monoamine
  pathways; without them most antidepressants would have no flow.)
- **Panel** (`showDrug`): the molecular-structure image (when fetched), the class, the
  NbN nomenclature, the description (baked copy painted first then live-refreshed from
  Wikipedia, re-graded `sourced`), a Wikipedia link, then the **Acts on** binding list
  (each row: a coloured effect glyph + target name + action·note, dimmed + italic "·
  speculative" when tentative, plus a source pill via `bindingProvenancePill` = the
  binding's own quote-level source, else the drug-level Stahl citation as a fallback so the
  grade is never blank). There is no standalone drug-level Source(s) block. Class +
  Nomenclature values are clickable (open search with a `class:` / `nbn:` filter). Drugs
  are searchable (name / category / target keywords).

Extraction history: parallel agents from per-drug text; 44 drugs recovered from full-page
OCR (`PageImages`); 5 stay unbound as genuinely non-receptor agents (lithium, disulfiram,
l-methylfolate, triiodothyronine, caprylidene). A corrected dump was diffed against the
OCR-recovered bindings: 2 plainly-wrong bindings dropped, the rest real-but-unstated
affinities kept and flagged `tentative`. The Stahl `url` is `"TODO"` (the citation still
renders, with its provenance pill).

## Images

Two third-party image sources, handled differently on purpose.

- **Molecule images** (vendored same-origin; the CSP is `img-src 'self' data:`).
  `tools/fetch_molecules.py` downloads each drug's lead infobox SVG (skeletal formula) via
  the MediaWiki `pageimages` API into `public/data/molecules/<id>.svg`, keeping `.svg`
  leads only, lightly sanitized (`<script>` stripped, `width`/`height` from `viewBox`).
  Network-separate from the offline generator; idempotent + polite; writes
  `tools/molecules_sources.json`. `generate_data.py` (`_available_molecule_ids` +
  `_drug_record`) emits `structure_image` only when the file exists. `showDrug` renders it
  as `<img class="mol-structure">`; CSS `filter: invert(1)` makes the black line-art read
  light on the dark panel (coloured atom labels shift hue, accepted). No image if absent.
  Because force-dark would defeat the inversion, the page declares `<meta
  name="color-scheme" content="dark">` + `color-scheme: dark`.
- **Structure images** (hot-linked from Wikimedia; the GIFs are multi-MB so they are NOT
  vendored, only the url is stored). `tools/fetch_structure_images.py` resolves the best
  image per **base** via a fallback chain (first `.gif`, else first `.svg`, else the
  infobox/lead image; a pdf/djvu lead salvaged as its rendered first-page JPG) into
  `tools/structure_images_sources.json` (with the resolved kind, for provenance), reusing
  `fetch_molecules.py`'s polite-fetch helpers, downloading no bytes; an `IMAGE_OVERRIDES`
  map wins over the resolver. `generate_data.py` (`_load_structure_image_urls` +
  `_structure_record`) emits the `structure_image` url. `showStructure` renders it as
  `<img class="structure-image" loading="lazy">` with a spinner (`.img-spinner`); the
  `load` listener clears the spinner, `error` removes the figure (failed/blocked -> no
  image, never a broken icon). Not inverted (colour art). Needs the `img-src
  https://upload.wikimedia.org` CSP allowance.

## Source provenance

Every source/reference carries a **provenance grade** saying how trustworthy its
attribution is (the dataset is LLM-assisted, not yet human-checked). The viewer renders it
as a coloured **pill** with a tooltip; the grade is **data**. Grades (`PROVENANCE_LEVELS`
in `generate_data.py`, weakest to strongest):

- **`llm`** (grey **?**): LLM from memory, unchecked, may be a hallucination.
- **`sourced`** (yellow **~**): LLM given the source document, but the claim was not
  quote-verified.
- **`verified`** (green **✓**): an LLM extracted a quote, it was *programmatically*
  confirmed present in the source, and a separate LLM agreed it supports the claim. Highest
  grade available; still LLM-driven (the `info.provVerified` tooltip says so).
- absence -> orange **`NOSOURCE`** pill (`info.noSource`; tooltip `info.provNone`; CSS class
  `.src-todo`). Not a stored grade.

**Where the grade lives.** A citation source is `{citation, url, provenance}`; a `SOURCES`
entry may set its own, else `_expand_sources` defaults `DEFAULT_PROVENANCE` (`"llm"`). Each
`wikipedia` reference emits a sibling `wikipedia_provenance` from the `WIKIPEDIA_PROVENANCE`
override registry; a **present** link defaults `"sourced"` (`WIKIPEDIA_DEFAULT_PROVENANCE`),
not `llm` (a Wikipedia article is a real reference; the viewer even live-fetches its lead).
Upgrading a source as it is checked is a **data** edit; `_provenance` validates every grade.

**Per-claim sources + the verify gate (drugs).** Beyond the drug-level `STAHL_SOURCE`, each
binding may carry `sources[]` and each drug `nbn_sources[]`, each
`{corpus, page, quote, provenance}`: `corpus` is a key of the source-agnostic
`SOURCE_CORPORA` registry (Stahl is corpus #1, `{ref, citation, url, pages_dir}`, emitted as
`meta.source_corpora`), `quote` is verbatim from that page. `_quote_sources` /
`_binding_sources` validate (corpus + grade; a `verified` source needs page + quote); the
full citation is not denormalized onto the ~429 bindings (the viewer resolves it from
`meta.source_corpora`). A pill's per-claim ref reads `<ref>, p. N` (full title + edition, so
it is unambiguous); the longer `citation` is the fallback shown by `bindingProvenancePill`
on a binding with no quote-level source. `verified` is earned by a two-step (LLM extract +
LLM judge supports), then `check_data.py`'s source-quote check confirms the quote is really
on the page (the backstop against a hallucinated quote). The **NbN** is simpler:
`apply_nbn_sources.py` greps Stahl's verbatim "Neuroscience-based Nomenclature: <value>"
line and confirms the dataset `nbn` is a substring (a programmatic check, stronger than a
judge for this field). Page files live under the author-side source tree (see
`CLAUDE.local.md`), so the quote check is author-/hook-side and skipped (warned) on a clone
without them.

**Descriptions.** Drugs, structures and non-receptor targets carry **no baked
description**: their panel fetches the **current Wikipedia lead** (CC BY-SA) at runtime via
the shared `liveWikiDescription` helper over `js/wiki.js` `fetchWikiLead(url, lang)` (the
lead for the viewer's locale, English fallback), shown as a `sourced` paragraph when it
arrives, so the text stays current and the dataset ships no copyrighted prose; a wiki-linked
panel whose live lead fails to load shows no description. Receptors (and projection groups)
carry a short **authored** `description` painted first as the offline fallback, which the
live lead overrides best-effort when it arrives. Needs the `connect-src
https://*.wikipedia.org` CSP allowance.

**Presentation.** `makeProvenancePill(level)` -> a `.src-prov-<level>` pill (`.src-todo` for
the none case) with the glyph + `info.prov*` tooltip via `withTip`; colours are CSS.
`appendSources` adds a pill per citation; `appendWiki(url, provenance)` one per reference row
(or `NOSOURCE`). Each pill's tooltip explains its own grade and the About block carries the
full key, so there is no separate blanket "?" caveat.

**The "% sourced" figure.** `_provenance_stats` reduces every claim + reference to its
strongest grade and tallies per kind (drug bindings / NbN / projections /
receptor classifications / target classifications / region anatomy / wikipedia references)
plus a headline `pct_backed` over the **factual claims** (sourced-or-verified / total),
emitted as `meta.provenance_stats`. The About panel shows it (`buildAboutSourcing`) and
`tools/update_readme_stats.py` writes the same into the README `SOURCING_STATS` block;
`check_data.py` re-confirms the tally is self-consistent. References (wikipedia links) are
their own kind, not folded into the headline (a reference is a pointer, not a claim). The
circuit + projection-group descriptions are validated for a known grade but not yet folded
into the headline (all `llm` for now). Current: ~66% of 785 factual claims backed (bindings
94%, NbN 97%; projections + classifications + region anatomy the gap). Descriptions are no
longer a claim kind: every wiki-linked panel fetches the live Wikipedia lead instead of
baking it.

## Changing the data

1. Edit the relevant list in `generate_data.py` (or `tools/drugs_data.json` for drugs).
   - **Structures**: edit `PAIRED` / `MIDLINE`. Paired entries are auto-mirrored (define
     on the right, x > 0; the generator emits one right-side shape file and the `_L` member
     references it with `mirror:true`). A region is a noise-deformed ellipsoid by default;
     blob surface knobs (consumed by `buildBlobGeometry`): `octaves` (fBm layers),
     `ridged` (creases -> folia; needs higher `detail`, lower `noise`, a `frequency`),
     `frequency`, `aniso` ([ax,ay,az] per-axis skew), `clip` (axis-aligned flat faces;
     `medial=True` derives the right medial clip). Auto, never authored: `clip_planes`
     (`_bisecting_clip_planes`, the jigsaw cuts between overlapping same-group neighbours;
     `JIGSAW_CLIP.enabled` toggles). Cortex pattern is shader-drawn, not geometry (`injectCortexSwirl` /
     `CORTEX_SWIRL` knobs `freq`/`warp`/`rings`/`width`/`ink`/`octaves`/`steps`, or
     `enabled:false`). Use `shape=dict(type="curve", ...)` for a tapered tube (midline
     curves are emitted once, not mirrored) or `type="composite"` for merged sub-shapes.
     Layout: the `pos` field positions regions to assemble at explode 0; lobes overlap +
     `medial` so the hemispheres meet at `MIDLINE_GAP` (temporal is the lateral exception);
     deep nuclei sit small + central. Re-render to check
     (`only=frontal_R,parietal_R,temporal_R,occipital_R&explode=0&view=right`).
   - **Structure links + grades**: add a `base -> URL` entry to the `WIKIPEDIA` registry
     for a Wikipedia link (both hemispheres share it; a non-base key raises). Anatomy source
     grade is `classification_provenance`, default `llm`, overridable in
     `STRUCTURE_PROVENANCE` (the `RECEPTOR_PROVENANCE` / `TARGET_PROVENANCE` /
     `STRUCTURE_PROVENANCE` trio via `_lookup_provenance`).
   - **Projections**: edit `PROJECTIONS`. `from`/`to` are structure ids; the arrow points
     `from -> to`. Carry `label` / `neurotransmitter` / `description` / `sources` (a list of
     `SOURCES` registry keys, expanded by `_expand_sources`; new refs go in `SOURCES`, `url`
     `"TODO"` until verified). `bidirectional: True` (both cones; use with
     `symmetric: False` + explicit `_L`/`_R` for commissures). `tentative: True` (dotted,
     Hypothetical section). Projections are bilateral by default (define once on the right);
     `symmetric: False` keeps a one-sided pathway. `kind` must be a `PROJECTION_COLORS` key
     (excitatory / inhibitory / dopaminergic / cholinergic / neuroendocrine / serotonergic /
     noradrenergic); a new kind also needs `KIND_TO_SIGN` (-> `SIGN_COLORS` / `SIGN_LABELS`)
     and `BURST` in `circuit-anim.js`.
   - **Circuits**: append to `CIRCUITS`: `id`, `name`, `structures` as base ids (arrows
     derived). Optional `description` + `description_fr` + `sources` for the detail panel.
   - **Projection groups**: edit `PROJECTION_GROUPS`: one entry per group in both modes,
     `{mode, key, name, description, description_fr, wikipedia, sources}` (`mode` kind|sign,
     `key` validated). Normally you only edit descriptions/sources (all 7 kinds + 3 signs
     exist); a new entry is needed only when adding a new projection `kind`.
   - **Receptors**: append to `RECEPTORS`: `id`, `name`, `family`, `neurotransmitter`,
     `receptor_class`, `sign`, `synaptic`, `locations` (base ids or `"ALL"`). Optional
     `description` + `description_fr` (inline) + `wikipedia`. A stub = empty `locations` +
     no description. `_receptor_record` validates keys + bases. A new family/class/synaptic
     value needs its label map entry (+ FR). Grade overridable in `RECEPTOR_PROVENANCE`.
   - **Drugs**: edit `tools/drugs_data.json`. Each: `id`, `name`, `categories`, optional
     `nbn` + `description` (inline `{en,fr}`), `wikipedia`, `bindings`. A binding is
     `{target, action}` (+ optional `effect` / `note` / `tentative`); `target` is a merged
     map key (a `DRUG_TARGETS` key or a receptor id), `action` a `DRUG_ACTIONS` key
     (agonist / partial_agonist / antagonist / inverse_agonist / reuptake_inhibitor /
     releaser / enzyme_inhibitor / pam / nam / blocker / modulator). `"bindings": []` ->
     `focusable: false`. A new coarse target/category/action needs a `DRUG_TARGETS` /
     `DRUG_CATEGORY_LABELS` / `DRUG_ACTIONS` entry (with `{en,fr}` labels; a `DRUG_TARGETS`
     entry needs a `type` + optional `wikipedia`). Target grade overridable in
     `TARGET_PROVENANCE`. Keep extraction strictly dump-sourced.
   - **Translations**: every display string is wrapped with `_t()`; add the French to the
     `FR` table or the build raises listing every miss. For a feminine/plural paired name set
     `fr_gender` (`f`/`mp`/`fp`).
2. Run `python tools/generate_data.py` to regenerate `public/data/`.
3. Optionally run `python tools/check_data.py`.
4. For new drugs/structures with links, run the fetch tools (network, idempotent, touch
   only the new ones): `fetch_molecules.py`, `fetch_structure_images.py`.
5. Commit the generator change + the regenerated artifacts together.

The legend is generated at runtime from the data, so it updates automatically.

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
