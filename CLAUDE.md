# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

> [!IMPORTANT]
> Keep this file up to date. Whenever a new feature, control, data field, or
> file is added, update the relevant section below in the same change. This file
> is meant to stay an accurate map of the project.

## What this is

A browser-based 3D brain visualizer built on [three.js](https://threejs.org/).
It shows brain regions (cortical lobes, basal ganglia / deep nuclei,
diencephalon, limbic, hindbrain) as procedurally shaped meshes (cel-shaded
cortical lobes carrying a swirl motif, smooth deep nuclei, foliated cerebellum,
swept-tube caudate/brainstem/hippocampus/cingulate/fornix)
and draws arrows for neuron projections between them. It also carries a dataset of
neurotransmitter **receptors** (which transmitter, mechanism class, excit/inhib
sign, pre/post-synaptic site, and the regions each is expressed in); focusing one
dims the brain and scatters glowing dots over the regions carrying it (see
"Receptors" below). It also carries a dataset of psychiatric **drugs** (from
Stahl's Prescriber's Guide): each drug's coarse class, its molecular-target
**bindings** (what target, what action) and a one-line mechanism; focusing one
dims the brain and animates effect-coloured gem dots (boost / block / modulate)
over the regions each target sits in, so you can see what the drug does to the
brain (see "Drugs" below). Region `group` values
(`lobe`, `basal_ganglia`, `diencephalon`, `limbic`, `hindbrain`,
`brainstem_nuclei` for the neuromodulatory source nuclei raphe / locus coeruleus /
VTA) drive the legend
headings + ordering via the `GROUP_LABELS` map in `tools/generate_data.py`, which
is emitted into the data's `meta.json` and read by the viewer; adding a new
group means adding it there too or its structures are dropped from the legend.
At explode 0 the regions are positioned and shaped to
lock together into a whole brain (the cortical lobes tile a hemisphere with a
flat medial wall at the longitudinal fissure); the explode slider blows them
radially apart to reveal the deep nuclei. On load the regions start blown out
and animate back together into the whole brain. The view can be rotated/zoomed,
auto-rotated, "blown out" (exploded), and made transparent.

Built with the help of Claude Code.

## Architecture (data vs. rendering, on purpose)

(For a higher-level narrative with diagrams, the module graph, and the boot
sequence, see [`ARCHITECTURE.md`](ARCHITECTURE.md); this section is the detailed
map.)

The anatomy is kept as plain data, separate from the rendering code, so the
project can grow without touching the viewer:

**Project layout.** Everything the browser loads lives under `public/` (the
served site: `index.html`, `app-config.js`, `version.js`, `js/`, `data/` which
holds the per-type dataset files (`meta.json`, `structures.jsonl`,
`projections.jsonl`, `circuits.jsonl`, `receptors.jsonl`) + the `shapes/`
geometry files), and that
directory is the *only* thing exposed to the web: Caddy's
`/srv` and `tools/serve.py` both root at it, so `docker/`, `tools/`, `.git` and
the uncommitted `.env` / `deploy.sh` / `CLAUDE.local.md` are never web-reachable.
Authoring + dev tooling live in `tools/` (`generate_data.py`, `drugs_data.json`,
`serve.py`,
`shot.py`, `git-hooks/`); deployment config in `docker/`; the README hero shot in
`docs/`. The map below names files by role; their directories are as just listed.

```
tools/generate_data.py  Single source of truth for the anatomy. Defines every
                      region + projection (+ receptor) once and emits the artifacts
                      below; the drugs are the exception, authored in the sibling
                      tools/drugs_data.json and read by _load_drugs (see "Drugs").
                      Every translatable display string below is an {en, fr}
                      object (see "Internationalization"); js/data.js localizes
                      them at load. The dataset is split by record type for
                      clarity (the file a record lives in encodes its type, so
                      there is no "type" field on the lines):
                        - data/meta.json: a single JSON object, the presentation
                          maps projection_colors (kind -> arrow colour), kind_labels
                          (kind -> {en,fr} functional-class label), group_labels
                          (group -> {en,fr} legend heading), and the colour-mode
                          maps kind_signs (kind -> excit/inhib/modulatory sign),
                          sign_colors (sign -> colour) and sign_labels
                          (sign -> {en,fr} heading), plus the receptor legend maps
                          receptor_family_labels (family -> {en,fr} heading, its
                          key order = the receptor legend's family order),
                          receptor_class_labels (mechanism class -> {en,fr}) and
                          synaptic_labels (pre/post -> {en,fr}), plus the drug maps
                          drug_category_labels (coarse class -> {en,fr} legend
                          heading, its key order = the Drugs legend's category
                          order), drug_actions (action key -> {label:{en,fr},
                          effect}), drug_effect_colors (boost/block/modulate ->
                          colour) and drug_effect_labels (effect -> {en,fr}), and
                          drug_targets (the merged binding-target map: every
                          non-receptor target like sert/mao_a/nav with its
                          {name:{en,fr}, type, system, regions[bases], optional
                          wikipedia} plus every receptor id as a target linked back
                          to its receptor), and the non-receptor-target presentation
                          maps target_type_labels (type -> {en,fr} tag, e.g.
                          transporter/enzyme/ion_channel) and target_type_colors
                          (type -> swatch/dot colour, since a transporter has no
                          excit/inhib sign to reuse); so the dataset is
                          self-describing and a port needs no hardcoded palette
                        - data/structures.jsonl: one region per line: id, name
                          ({en,fr}, with the hemisphere prefix/suffix), base_name
                          ({en,fr}, hemisphere-stripped, used for the legend row),
                          group, position, color, shape_file, and an optional
                          wikipedia (article URL, shown as a link in the structure
                          info panel)
                        - data/projections.jsonl: one pathway per line: from, to,
                          kind, label ({en,fr}), neurotransmitter ({en,fr}),
                          description ({en,fr}), sources[{citation,url}] (not
                          translated), optional bidirectional, and optional
                          tentative (a speculative pathway: drawn as a dotted arrow
                          in a separate, off-by-default legend section)
                        - data/circuits.jsonl: one named functional loop per line:
                          id, name ({en,fr}), structures[ids] (its arrows are
                          derived in the viewer as the projections whose endpoints
                          are both in the set)
                        - data/receptors.jsonl: one neurotransmitter receptor per
                          line: id, name (technical, language-neutral, e.g.
                          "5-HT2A"), family (a key of receptor_family_labels),
                          neurotransmitter ({en,fr}), receptor_class
                          (ionotropic/metabotropic/chaperone), sign (excit/inhib/
                          modulatory, reusing the projection sign maps), synaptic
                          (presynaptic/postsynaptic/both), locations (structure
                          *base* ids where it is expressed; the viewer expands each
                          to both hemispheres), an optional ubiquitous:true (a
                          brain-wide receptor, empty locations -> lights every
                          structure), optional description ({en,fr}) and wikipedia.
                          A receptor with empty locations and no description is a
                          deliberate "stub" (no CNS role: listed but not focusable)
                        - data/drugs.jsonl: one drug per line: id, name (technical,
                          language-neutral, e.g. "Citalopram"), categories[keys of
                          drug_category_labels], optional nbn ({en,fr} Neuroscience-
                          based Nomenclature), optional description ({en,fr} one-line
                          mechanism), bindings[] (each: target = a drug_targets key,
                          action = a drug_actions key, optional effect override,
                          optional note ({en,fr} or "TODO"), optional tentative),
                          sources[{citation,url}] (always the Stahl citation, url
                          "TODO" for now), optional wikipedia, and focusable (false
                          for a drug with no bindings -> listed but not clickable).
                          The data is authored in tools/drugs_data.json (sourced
                          from Stahl's Prescriber's Guide 8th ed.), not inline in
                          the generator, see "Drugs" below
data/shapes/<name>.json  One geometry file per distinct *form* (independent of
                      where it sits / what it connects to). Symmetric left/right
                      pairs share a single right-side file; the left member
                      reflects it (a `mirror` flag on its structure record, see
                      below), so there is no per-side duplication. Three types:
                      "blob" {radii, seed, detail, noise, + optional
                      octaves/ridged/frequency/aniso/clip/clip_planes/carve_tubes}
                      = a gradient-noise-deformed ellipsoid (the optional fields
                      turn the smooth surface into foliated cerebellum; the
                      cortical lobes stay smooth domes and get their cel-shaded
                      look + swirl motif from a shader instead, see js/shapes.js
                      CORTEX_SWIRL), `clip` cuts axis-aligned flat faces e.g. the
                      lobes' medial wall, `clip_planes` are the generated
                      bisecting cuts between overlapping neighbours so adjacent
                      regions tile flush like jigsaw pieces instead of inter-
                      penetrating, and `carve_tubes` are swept-tube channels
                      subtracted from a lobe by a `carves` curve (the caudate) so
                      it seats into a notch instead of poking through;
                      "curve" {points, profile, seed, noise, radial/tubular_
                      segments} = a round-capped tapered tube swept along a spline
                      (the C-shaped caudate, the tapering brainstem); "composite"
                      {parts:[...]} = several sub-shapes (each with optional
                      offset/scale/rotate) merged into one mesh, for regions that
                      aren't a single lump (the cerebellum = 2 hemispheres +
                      vermis).
index.html            Page shell: loads three.js (vendored, via import map) and,
                      on ?debug=1 only, the vendored eruda console; holds
                      the single bottom-left collapsible "neurarium" panel
                      (reset / search / keyboard-shortcuts buttons, the two
                      sliders, auto-rotate, the
                      nested JS-populated legend whose first rows are "show all
                      names" / "hide projections", a nested JS-populated Receptors
                      section, a nested JS-populated Drugs section (with its own
                      filter box), and a nested About section; Legend / Receptors /
                      Drugs / About are a single-open accordion). The panel body is
                      split
                      into a #settings-pane (all the above) and a #details-pane
                      (#info-body) switched by a #panel-tabs bar of
                      browser-style tabs: a pinned Settings tab (always first,
                      never scrolled away) plus one closable tab per opened detail
                      in a scrollable #detail-tabs strip, so a structure /
                      connection / receptor / target / drug detail shows in the
                      panel instead of a separate window, and several stay open at
                      once like browser tabs (createPanelTabs in js/main.js).
                      Also the in-place search box, the centered
                      #shortcuts-modal keyboard-shortcuts popup (filled by
                      wireShortcutsHelp), and
                      the top #banners stack (the WIP banner + error banners).
js/data.js            Fetches the per-type data files (meta.json + structures/
                      projections/circuits/receptors/drugs.jsonl) + all shape
                      files,
                      returns a normalized {structures, projections, circuits,
                      receptors, targets, drugs, byId, meta} object. It reads the
                      meta maps and
                      resolves each projection's arrow `color` from its kind (so
                      the viewer reads `projection.color`, never a hardcoded
                      palette), and resolves each receptor's family/class/sign/
                      synaptic labels + sign colour and expands its `locations`
                      bases to concrete `structureIds` (both hemispheres, or every
                      structure when `ubiquitous`). It also resolves each drug:
                      localized description/nbn, the coarse `categoryLabels` (+
                      primary `category`), and per-binding `targetName` +
                      `actionLabel` + net `effect`/`effectColor`/`effectLabel` +
                      the concrete `structureIds` each binding lights (a receptor-
                      linked target reuses that receptor's structureIds, a
                      ubiquitous one lights all, others expand the target's region
                      bases to both hemispheres); the union is the drug's
                      `structureIds` (what the focus dims to), plus `focusable` +
                      search `keywords`. It also builds the merged **`targets`**
                      browse list (every receptor + every non-receptor drug target),
                      one normalized focusable entry each: `kind` (receptor or a
                      target type), `system` (grouping family), `swatchColor` (a
                      receptor's sign colour, a target's type colour), expanded
                      `structureIds`, `focusable` + `keywords`; a receptor entry
                      points back at its record, a non-receptor one adds
                      typeLabel/systemLabel/wikipedia/locationNames for showTarget.
                      `meta` carries
                      {projectionColors, groupLabels, ..., receptorFamilyLabels,
                      receptorClassLabels, synapticLabels, targetTypeLabels,
                      targetTypeColors, drugCategoryLabels,
                      drugEffectColors, drugEffectLabels}.
js/shapes.js          Builds a mesh from a shape payload: buildGeometry()
                      dispatches on shape.type to buildBlobGeometry (deformed
                      ellipsoid), buildCurveGeometry (round-capped tapered tube
                      along a spline) or buildCompositeGeometry (merged sub-
                      shapes). A `mirror` flag on the structure reflects the
                      geometry across x (mirrorGeometryX) for the left member of
                      a pair. Self-contained gradient (Perlin) noise +
                      fractal/ridged/domain-warp helpers (fractalNoise). Cortical
                      lobes are smooth domes rendered cel-shaded (MeshToonMaterial,
                      flat lighting bands) and carry a stylized swirl motif drawn
                      as darker "ink" contour lines injected into their material
                      (injectCortexSwirl / CORTEX_SWIRL: a domain-warped noise
                      field whose contour lines curl into loose spirals), so the
                      surface pattern is pure colour, not triangles or relief.
                      buildBlobGeometry also
                      honours `clip_planes` (the generated inter-region jigsaw
                      cuts) when the `JIGSAW_CLIP.enabled` flag is on, and
                      `carve_tubes` (the caudate hollowing a notch in the lobes it
                      threads) when `CARVE_TUBES.enabled` is on. No JS deps
                      beyond three.js.
js/arrows.js          Builds curved tube+cone arrows for projections; each
                      arrow's colour comes from its `projection.color` (resolved
                      by js/data.js from the data's meta map, single source
                      tools/generate_data.py), not a hardcoded table here, and is
                      recolourable at runtime via `setColor` (the panel's arrow
                      colour-mode switch, Neurotransmitter / Potential, see
                      Controls). A
                      `projection.tentative` arrow is drawn as a *dotted* tube
                      (a gapped run of short segments merged by a small local
                      mergeIndexedGeometries; no addon) so speculative pathways
                      read as "maybe".
js/labels.js          Floating structure-name labels (three.js CSS2DRenderer):
                      one hidden label per region, shown on hover or all at once.
js/circuit-schedule.js  Automatic sequencing for the circuit "traveling pulse"
                      animation: scheduleCircuit() turns a circuit's arrow set into
                      a per-arrow firing slot via a BFS over the directed graph
                      (node=structure, edge=arrow), with no hand-authored path.
                      Dependency-free (no three.js), so the ordering logic is
                      isolated + testable. See "Circuit animation" below.
js/circuit-anim.js    Rendering half of that animation (createCircuitAnimation):
                      turns each arrow's scheduled slot into a glowing additive
                      bead riding the arrow's live curve (arrow.curve, exposed by
                      js/arrows.js) from source to target, looping so a curated
                      loop reads as signal flowing around it. Runs only while a
                      circuit is isolated; ticked in the render loop.
js/receptor-markers.js  Receptor / target "expression dots"
                      (createReceptorMarkers): when a receptor *or* a non-receptor
                      drug target is focused (its row in the merged Receptors &
                      targets section), scatters dense additive
                      glowing "gem" dots over the surface of every structure
                      expressing it (a crisp bright core + a 4-point sparkle-star
                      sprite, so they read as shiny gems not stains; per-dot
                      brightness varies). Each structure's dot count scales with its
                      surface area (so big lobes + tiny nuclei look equally
                      peppered). Each cloud is a THREE.Points sampled from the
                      structure mesh's own geometry and parented to it (so the dots
                      track its explode/mirror transform and vanish when it is
                      hidden, like the selection halo + circuit node-flash shells);
                      colour = the receptor's sign colour (a target's type colour),
                      gently pulsed. One
                      controller per scene; ticked in the render loop. The single-
                      cloud builder is factored out as an exported `buildGemCloud`
                      (+ `GEM_DOT_SIZE`) so the per-drug animation reuses the exact
                      gem look without duplication. See "Receptors" below.
js/drug-anim.js       Per-drug "what it does to the brain" animation
                      (createDrugAnimation): when a drug is focused (its Drugs
                      legend/list row or a drug search result), scatters a gem
                      cloud (via buildGemCloud) over the regions each of the drug's
                      bindings lights, coloured by that binding's net effect
                      (boost emerald / block rose / modulate violet), and pulses
                      each cloud per effect (boost fast/bright/swelling, block
                      slow/dim, modulate in between). It owns only the dots (the
                      dimming of the rest of the brain is the selection
                      controller's setCircuit, like a receptor focus). One
                      controller per scene; ticked in the render loop; stopped off
                      the selection state via `matches`. See "Drugs" below.
js/main.js            Scene/camera/renderer/lights/OrbitControls setup, the
                      explode + transparency logic, the auto-play "assemble"
                      intro (createIntroAnimation), auto-rotate, hover raycasting
                      for labels, arrow + structure picking and the detail panel
                      (createInfoPanel: a connection view, a structure view with
                      its connection list, a receptor view, a non-receptor target
                      view (showTarget), or a drug view
                      (showDrug), rendered into the
                      main panel's Details pane; the select* layer opens one
                      browser-style tab per detail via createPanelTabs), the
                      structure+connection+receptor/target+drug search, the legend
                      builder (buildLegend), the merged Receptors & targets legend
                      builder (buildTargetLegend, grouped by neurotransmitter
                      system, wiring each receptor/target row to dim the
                      brain + light its dots), and the Drugs legend builder
                      (buildDrugLegend, grouped by category with its own filter
                      box, wiring each drug row to dim the brain + play the
                      per-drug animation), and the render loop.
app-config.js         Tiny config file (window.__APP_CONFIG__). This committed
                      copy is the LOCAL-DEV fallback: the feature fields are empty,
                      so dev servers keep umami + the DEV banner off. In the
                      container it is NOT served; entrypoint.sh renders an
                      env-filled copy into /gen and Caddy serves that instead (see
                      below). Named generically (not "analytics-*") so content
                      filters / proxies that block "analytics" paths don't 404 it.
                      Carries the umami ANALYTICS_* values, DEV + STARTED_AT (the
                      WIP-banner flag and container start time), and sourceUrl (the
                      "source" link target, from SOURCE_URL, defaulting to the
                      public site).
js/app-init.js        Reads that config and injects the umami tag if configured;
                      no-op otherwise.
js/i18n.js            Internationalization (en / fr). A classic script (like
                      app-config.js) loaded early so the module viewer AND the
                      classic banner scripts can read window.__I18N__. Owns the
                      single UI message catalogue (both languages), detects the
                      language (?lang= param > saved choice > browser locale fr* >
                      en), and on
                      DOMContentLoaded fills the static markup tagged data-i18n /
                      data-i18n-html / data-i18n-attr so English text is not
                      duplicated between the HTML and the catalogue. Exposes
                      t(key,vars) (UI strings) and pick(field) (resolve a
                      translatable {en,fr} *data* field to the current language,
                      used by js/data.js). setLang() saves the choice and reloads
                      (data is resolved at load, see "Internationalization").
js/dev-banner.js      Reads that config and, when DEV=1, shows the top "work in
                      progress / restarted X ago" banner (STARTED_AT drives the
                      "X ago"); no-op otherwise. Lives in the shared #banners
                      stack. See "Dev / WIP banner" below.
js/error-banner.js    Surfaces failures as explicit red, dismissible banners in
                      the #banners stack instead of hiding them in eruda: installs
                      window error + unhandledrejection handlers, exposes a global
                      window.showErrorBanner(msg) for app code, de-dupes repeats
                      into one "(xN)" banner, and republishes the stack height to
                      the --banners-height CSS var so #status stays clear. See
                      "Error banners" below.
version.js            Single source of truth for the app version (a plain
                      `window.__APP_VERSION__` global, no build step). Shown in
                      the panel header (js/main.js) + the WIP banner
                      (js/dev-banner.js). Bump it on a release.
docker/               Deployment: docker-compose.yml (hardened Caddy service),
                      Dockerfile (strips caddy's cap_net_bind_service so exec
                      works under no-new-privileges), Caddyfile (serves /srv on
                      :8359, serves the startup-rendered /gen/app-config.js for
                      /app-config.js, sends Cache-Control: no-store so prod never
                      serves a stale module either, same as tools/serve.py, and
                      sets the security headers incl. a Content-Security-Policy,
                      see "Content-Security-Policy" below),
                      env.example (copy to docker/.env), entrypoint.sh (startup
                      wrapper baked into the image: stamps STARTED_AT, validates
                      ANALYTICS_URL, derives ANALYTICS_ORIGIN for the CSP, and
                      renders /gen/app-config.js from the environment, see below).
tools/shot.py         Screenshot helper (Playwright): serves public/ with
                      tools/serve.py, drives a headless Chromium to load
                      index.html (with view params), and captures the canvas with
                      page.screenshot() to a PNG. Lets a dev/Claude Code see the
                      output. Headless renders WebGL fine once Chromium is given
                      the SwiftShader GL flags (baked in); no $DISPLAY / xdotool /
                      ImageMagick needed. `--headed` opens a real visible window
                      (real GPU) if preferred. Bare `python tools/shot.py` writes
                      docs/screenshot.png (the README hero shot). Needs the
                      playwright package + `playwright install chromium` once (or
                      run via `uv run tools/shot.py`; it carries inline deps).
tools/serve.py        Stdlib static dev server that sends Cache-Control:no-store
                      so the browser never serves a stale ES module (use instead
                      of `python -m http.server` while developing; see Running).
tools/check_data.py   Stdlib integrity checker over the emitted public/data/
                      files (independent of generate_data.py): flags duplicate
                      ids/names (exact + normalized), unreachable cross-references
                      (e.g. a drug binding whose target is not a known target),
                      and TODO placeholders (stray TODOs warned separately from
                      the known source-url TODO backlog). Exit 0 = no errors
                      (warnings allowed), 1 = errors. Run `python
                      tools/check_data.py`; the pre-push hook offers to run it.
                      See "Data checks".
tools/drugs_data.json  The drug dataset's authored source (a JSON list, sourced
                      from Stahl's Prescriber's Guide 8th ed.), read by
                      generate_data.py's _load_drugs and validated + emitted to
                      data/drugs.jsonl. Kept out of generate_data.py because it is
                      large; this is the file to edit to add/change a drug. See
                      "Drugs" and "Changing the data".
tools/git-hooks/      Repo-tracked git hooks (single source of truth). Currently
                      pre-push, which refuses to push any branch other than
                      main and then offers (y/N on the terminal) to run
                      tools/check_data.py before letting the push through.
                      Activated per-clone with
                      `git config core.hooksPath tools/git-hooks` (see Git hooks).
```

(There are also two uncommitted, environment-specific files not shown above:
`deploy.sh` and `CLAUDE.local.md`; both are gitignored. The latter holds
per-developer setup notes, including the deploy procedure.)

Why a generator instead of hand-written data files: most regions are symmetric
left/right pairs, and the project is expected to get complex. Defining a region
once in `generate_data.py` and mirroring it avoids duplicating anatomical data
across ~20 files. The generated files are committed so the static site can fetch
them directly.

Coordinate convention (arbitrary units, brain centered on origin):
`x` left(-)/right(+), `y` down(-)/up(+), `z` posterior(-)/anterior(+).

## Running

The data files are loaded with `fetch()`, so the page must be served over HTTP
(opening `index.html` via `file://` fails CORS). The served site is `public/`.
From the repo root:

```
python tools/serve.py        # http://localhost:8000/ (recommended for dev)
# or: cd public && python -m http.server 8000
```

(`tools/serve.py` roots at `public/` by default regardless of where you run it;
the bare `http.server` fallback must be started from inside `public/`.)

Prefer `tools/serve.py` while developing: it is the same stdlib server but sends
`Cache-Control: no-store`, so the browser refetches every ES module on each
reload. Plain `http.server` sends no cache headers, and browsers then *heuristic*-
cache the JS modules; that can serve a stale `js/*.js` next to a freshly fetched
one, producing baffling mismatch crashes (e.g. a new `main.js` calling a function
whose old cached signature differs). If you ever see such an error after editing
JS, it is almost always a stale cached module: hard-reload (Ctrl/Cmd+Shift+R) or
switch to `tools/serve.py`.

Debugging: [eruda](https://github.com/liriliri/eruda) provides an on-screen
console (a floating button, pinned **top-right** so the bottom-left panel doesn't
cover it) usable on desktop and mobile. It is **gated**: it loads only when the
URL carries **`?debug=1`** (exactly), so normal production visitors never download
or expose it. Append `?debug=1` to any URL (e.g.
`http://localhost:8000/?debug=1`) to turn it on. A small inline gate in
`index.html` injects the eruda script only on that flag and then pins the entry
button top-right (re-pinning on resize, since eruda resets it otherwise);
otherwise the page ships no debug console (runtime errors still surface to
everyone via the red error banners, see "Error banners"). eruda is **vendored
same-origin** under `public/vendor/eruda/eruda.js` (so the page pulls no
third-party script; the CSP needs no CDN allowance, only `font-src ... data:` for
eruda's embedded icon font, see "Content-Security-Policy"). Bump that vendored
copy as a unit to upgrade.

### Screenshots & deep-link view params

`tools/shot.py` renders the page to a PNG so the output can be inspected (this is
how shapes are reviewed/refined, and how the README hero shot is made). It is a
small self-contained Playwright script: it serves the repo with `tools/serve.py`,
drives a headless Chromium, and captures the canvas with `page.screenshot()`:

```
python tools/shot.py                                                  # -> docs/screenshot.png
python tools/shot.py --params "explode=0.5&view=iso" --out /tmp/brain.png
python tools/shot.py --params "only=putamen_R&view=iso" --out /tmp/putamen.png
```

It needs the `playwright` package plus the browser binary
(`playwright install chromium`) once; or run it via `uv run tools/shot.py`, which
auto-installs the inline dependency. Headless WebGL renders correctly because the
script launches Chromium with the SwiftShader GL flags (`--use-gl=angle
--use-angle=swiftshader`); the earlier "headless comes back blank" problem was
just those flags being absent. No `$DISPLAY` / `xdotool` / ImageMagick is needed.

> [!NOTE]
> Pass `--headed` to open a real visible browser window (real GPU) instead of
> headless, e.g. to watch what is being captured. The default headless path is
> the reliable one and needs no display. `--wait` is milliseconds to let the data
> load and a few frames render before the capture (default 6000).

The `--params` string is the URL query parsed by `applyViewParams` in
`js/main.js`, so the same keys also work as deep links in a normal browser:

| key | effect |
| --- | --- |
| `only=id[,id2]` | show only these structure ids (others + all arrows hidden) |
| `view=front\|back\|left\|right\|top\|bottom\|iso` | frame the visible meshes from that angle |
| `explode=0..1` | blow-out amount (also moves the slider) |
| `transparency=0..1` | material opacity |
| `names=all` | show every structure label |
| `autorotate=1` | spin (deep links default auto-rotate **off** so the framed view holds; this forces it on) |
| `ui=0` | hide the control panels + legend (clean shape shots) |

`only`/`view` auto-fit the camera to whatever is visible, so a single structure
fills the frame, handy for reviewing one region's shape at a time.

## Deployment

The site is served by a hardened Caddy container (`docker/docker-compose.yml`):
non-root UID 1000, `cap_drop: ALL`, `no-new-privileges`, read-only rootfs
(writable paths via tmpfs, each `size=`-capped so the RAM-backed mounts can't be
filled to exhaust host memory), CPU + memory + `pids` limits (the last anti
fork-bomb, all under `deploy.resources.limits` so `pids` isn't also set as the
top-level `pids_limit`, which compose rejects as a conflicting double
definition), `mem_swappiness: 0`, and rotated `json-file` logging (so log output
can't fill the host disk). Caddy listens on `:8359`,
published as `127.0.0.1:8359` so a host reverse proxy terminates TLS in front of
it. The image is a thin build on `caddy:2-alpine` (`docker/Dockerfile`) whose
only job is to strip the caddy binary's `cap_net_bind_service` file capability,
which otherwise makes `exec` fail under `no-new-privileges`
(`exec /usr/bin/caddy: operation not permitted`); the `public/` site root (only
the served files, not the rest of the repo) is bind-mounted read-only at `/srv`
at runtime.

The actual deploy procedure (how the tree reaches the server and the restart
commands) is environment-specific and intentionally kept out of this committed
file. See `CLAUDE.local.md` (uncommitted, per-developer setup notes).

## Git hooks

The repo ships its git hooks under `tools/git-hooks/` (tracked, so they are the
single source of truth, not copied into `.git/hooks`). They are activated
**per-clone** by pointing git at that directory once:

```
git config core.hooksPath tools/git-hooks
```

That setting lives in `.git/config` and is *not* committed, so every fresh clone
must run it once (there is no build/install step otherwise). Current hooks:

- `pre-push`: refuses to push any ref other than `main` (other branches, tags,
  and deletes all crash the push). Deployment here does not go through git, so
  `main` is the only ref that should ever leave this machine. When the branch is
  `main`, it then **prompts on the terminal** (`y/N`, default no) to run
  `tools/check_data.py` (see "Data checks") before completing the push; a `y`
  runs it and a check that reports **errors** aborts the push (warnings, like the
  known TODO source urls, pass). The prompt + answer use `/dev/tty` (stdin is
  git's ref list), and a non-interactive push (no controlling terminal) skips the
  prompt so automation never hangs.

## Data checks

`tools/check_data.py` is a stdlib-only integrity checker that runs over the
**emitted** dataset (`public/data/`: `meta.json` + the `.jsonl` files), the
artifacts the static site actually serves, independently of `generate_data.py`.
It is a cheap regression guard (the generator already raises on most of these at
build time, but this also catches generator/data drift and the duplicate/TODO
classes the generator does not look for). Run it directly:

```
python tools/check_data.py     # exit 0 = no errors (warnings allowed), 1 = errors
```

Three families of checks:

- **Duplicates** (per collection: structures / receptors / drugs / circuits /
  targets, plus projections). An exact duplicate id/key, or two ids that collide
  once **normalized** (lowercased, every non-alphanumeric stripped, so `mao_a`
  and `mao-a` both become `maoa`), is an **error**. Two entries whose **display
  names** collide once normalized is a **warning** (a likely accidental re-entry
  to eyeball). Projections have no id, so they are checked for duplicate
  `from -> to` endpoints instead.
- **Reachability** (referential integrity): every cross-reference must resolve or
  the detail is **unreachable** in the viewer. The canonical case (the reason
  this exists): a drug binding whose `target` is not a key of `meta.drug_targets`
  can never be focused from its panel. Also checks projection endpoints/kind,
  circuit/receptor/target structure refs, receptor classification keys, target
  type + region bases, and that every receptor is also a `drug_targets` key. All
  dangling references are **errors**.
- **TODOs**: a literal `"TODO"` outside a source url (e.g. a binding `note` left
  as TODO), plus any focusable target with no `wikipedia` (shown as a TODO pill),
  is a **warning**; source urls left as `"TODO"` are counted and warned about
  **separately** (the known, tracked backlog, currently every source). TODOs
  never fail the run, they only print, so the pre-push gate passes on the current
  data.

The check functions take the loaded data as plain arguments (not the files), so
they are unit-testable by feeding crafted records.

## Internationalization (i18n)

The site is bilingual (English / French), no build step. `js/i18n.js` (a classic
script, loaded early in `index.html`) is the whole mechanism:

- **Two string sources, one pattern.** *UI* strings (panel labels, buttons,
  info-panel headings, banners, the receptor panel's field labels, ...) live in
  the message catalogue **inside
  `js/i18n.js`** (one object per language). *Data* strings (region names, pathway
  labels + descriptions, circuit names, legend group headings, neurotransmitters,
  kind labels, and the receptor `neurotransmitter` / `description` + the receptor
  family / class / synaptic labels) live in the data file as `{en, fr}` objects,
  authored once in
  `tools/generate_data.py` (see "Changing the data") and resolved by `js/data.js`.
- **Generator side (`tools/generate_data.py`).** The anatomy is authored in
  English; a single `FR` table (English string -> French) is the French source,
  and `_t("English")` wraps any display string into `{"en": ..., "fr": FR[...]}`
  when the records are built. A string with no `FR` entry is collected and
  `build_records` **raises listing every missing one**, so the data can never ship
  half-translated. Per-hemisphere names are **composed, not stored**: `_side_name`
  prefixes `Right`/`Left` (English) and suffixes the gender/number-agreed
  `droit/droite/droits/droites` or `gauche/gauches` (French, tuned by an entry's
  optional `fr_gender` of `"m"`/`"f"`/`"mp"`/`"fp"`). Each structure record also
  carries a hemisphere-stripped **`base_name`** `{en,fr}` (the legend groups twins
  by it, so no language-specific prefix parsing). `meta.json` gains
  **`kind_labels`** (`kind -> {en,fr}` functional-class label) and **`sign_labels`**
  (`sign -> {en,fr}` colour-mode heading) alongside
  `projection_colors`/`group_labels`/`sign_colors`; `js/data.js` localizes every
  such field (incl. `name`/`base_name`, projection `label`/`description`/
  `neurotransmitter`, circuit `name`, and the `group_labels`/`kind_labels`/
  `sign_labels` map values) to plain strings at load via `pick`. Source citation
  text + URLs are not translated.
- **Language pick.** `detectLang()` uses a `?lang=en|fr` query param if present
  (and persists it to `localStorage`, so a deep link *sets the default* for later
  visits too), else a saved choice (`localStorage` `neurarium:lang`), else the
  browser locale (any `fr*` -> French), else English. `window.__I18N__` exposes
  `lang`, `t(key, vars)` (UI lookup with
  `{token}` interpolation, falls back to English then the key), `pick(field)`
  (collapse an `{en,fr}` data field to the current language; a plain string passes
  through), and `setLang(lang)`.
- **Static markup** in `index.html` is *not* duplicated into the catalogue: the
  English text is removed from the HTML and the elements carry `data-i18n="key"`
  (textContent), `data-i18n-html="key"` (innerHTML, for the About paragraphs'
  links) or `data-i18n-attr="attr:key,..."` (attributes like `placeholder` /
  `title`); `i18n.js` fills them from the catalogue at `DOMContentLoaded`.
  Dynamically-built UI (legend, info panel, banners) calls `t()` directly; the
  classic banner scripts read `window.__I18N__` with a key-fallback so an error is
  still surfaced if i18n somehow failed to load.
- **Switching** is a small `EN/FR` control (`#lang-switch`) at the top of the
  panel body (tagged `.collapsible-control`, so it hides with the sliders +
  auto-rotate while a section is open). Clicking the inactive language calls
  `setLang`, which **saves the choice
  and reloads**: `js/data.js` resolves the data language at load, so a reload is
  simpler and more robust than re-rendering the whole scene live. The chosen
  language is also written to `<html lang>`.

> [!IMPORTANT]
> Any new user-visible string must be added to **both** language tables in
> `js/i18n.js` (UI) or authored as an `{en, fr}` object in `generate_data.py`
> (data). Don't hardcode a display string in the viewer or the HTML. Source
> citation text and URLs are intentionally **not** translated.

## Analytics (umami)

Optional, privacy-friendly umami tracking. Because this is a no-build static
site on a read-only rootfs, the config is injected at runtime:

1. Set `ANALYTICS_URL`, `ANALYTICS_WEBSITE_ID` and (optional) `ANALYTICS_SRI` in
   `docker/.env` (see `docker/env.example`). `ANALYTICS_DNT` is umami's
   `data-do-not-track` value (mirrors WebSend's `UMAMI_DNT`): `"true"` (default)
   respects the browser Do Not Track signal, `"false"` tracks all visitors.
2. compose passes them into the container; `docker/entrypoint.sh` renders
   `/gen/app-config.js` from those env vars at container start, and the Caddyfile
   serves that file for `/app-config.js`. (Earlier this was a Caddy `templates`
   block filling `{{env}}` placeholders in the file; that parsed the whole JS as
   a Go template on every request and 500'd on any stray brace marker in the
   file, silently taking both umami and the DEV banner down, so it was replaced
   by the render-once-at-startup approach. The committed `app-config.js` is now
   just the empty local-dev fallback.)
3. `js/app-init.js` reads `window.__APP_CONFIG__` and injects the umami `<script>`
   (with SRI/crossorigin if a hash is given, and an explicit `data-do-not-track`).

   The client-facing file/global names are intentionally generic (`app-config.js`,
   `js/app-init.js`, `__APP_CONFIG__`), not "analytics-*": a path containing
   "analytics" is blocked by many content filters and forward proxies (Squid
   blocklists), which would 404 it before the browser sees it. The `ANALYTICS_*`
   env vars stay as-is since they are server-side and never sent to the client.

Leave `ANALYTICS_URL`/`ANALYTICS_WEBSITE_ID` empty (or run locally without
templating) and analytics is fully disabled, the page works the same.

`ANALYTICS_URL` must be the full URL of the umami tracker *script* (e.g.
`https://umami.example.com/script.js`), not the instance base URL: it is used
verbatim as a `<script src>`, so the instance's HTML homepage would load nothing
and silently record zero events. To make that misconfiguration loud, the
container **validates it at startup** (`docker/entrypoint.sh`): when
`ANALYTICS_URL` is set it must be reachable *and* serve JavaScript (checked via
the response `Content-Type`), otherwise the container refuses to start (crashes)
instead of looking configured while tracking nothing. Empty `ANALYTICS_URL`
skips the check.

## Content-Security-Policy

Caddy sends a `Content-Security-Policy` (plus `X-Content-Type-Options`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`) on every response
(`docker/Caddyfile`). The policy is `default-src 'self'` with `object-src`,
`base-uri`, `frame-ancestors` and `form-action` locked down. Both three.js and
the gated eruda debug console are vendored same-origin (`public/vendor/three`,
`public/vendor/eruda`), so the page pulls **no third-party script** and
`script-src` needs no CDN allowance. The only relaxations are:

- `font-src 'self' data:`: eruda embeds its icon font as a `data:` URI, so
  without `data:` the debug console's icons render as tofu/X. (`img-src` already
  allows `data:`.)
- the **umami origin** in `script-src` + `connect-src`, when analytics is
  configured. `docker/entrypoint.sh` derives `ANALYTICS_ORIGIN`
  (`scheme://host[:port]`) from `ANALYTICS_URL` and the Caddyfile interpolates it
  as `{$ANALYTICS_ORIGIN:}`; empty (analytics off) adds no extra origin.

`script-src`/`style-src` include `'unsafe-inline'` because this is a no-build
site with an inline `<script type="importmap">`, the inline eruda gate, and an
inline `<style>` block, and there is no bundler to hash/nonce them. That is the
one looseness; it could be tightened to hashes later. The CSP is
only emitted by Caddy in the container, not by `tools/serve.py` in dev.

> [!IMPORTANT]
> If you add a new external resource (another CDN script, a remote font, an
> `<iframe>`, an image host, a cross-origin `fetch`), extend the matching CSP
> directive in `docker/Caddyfile` or the browser will silently block it in prod.

## Dev / WIP banner

Optional "work in progress" banner across the top of the page, for when the
instance is being actively redeployed. Same runtime-injection plumbing as
analytics (no build step):

1. `DEV` in `docker/.env` (default `0`). Set `DEV=1` to enable the banner.
2. The container also needs to know *when it started* so the banner can say
   "restarted X ago". Compose env is static, so the entrypoint
   (`docker/entrypoint.sh`, baked into the image and set as `entrypoint` in
   `docker-compose.yml`) stamps `STARTED_AT=$(date +%s)` (epoch seconds). (The
   same script also validates `ANALYTICS_URL`, see the Analytics section.)
3. The entrypoint then renders `DEV` + `STARTED_AT` (alongside the `ANALYTICS_*`
   values) into `/gen/app-config.js`, which Caddy serves for `/app-config.js`.
4. `js/dev-banner.js` reads `window.__APP_CONFIG__`: when `dev === "1"` it
   reveals `#dev-banner` (an amber bar in the shared `#banners` stack, hidden by
   default via the `hidden` attribute, so `banner.hidden = false` shows it) and
   computes "X minutes/hours/days ago" from `startedAt` client-side (refreshed
   each minute). It does not nudge the rest of the UI itself: the `#banners`
   stack publishes its height as `--banners-height` (see "Error banners"), which
   the `#status` pill offsets against. Any other `DEV` value, or the empty
   local-dev fallback, keeps it hidden, so the banner only ever appears when
   explicitly turned on in a container.
5. **Clicking the banner hides it for the current view only.** The dismissal is
   deliberately *not* persisted (no `sessionStorage`), so a reload brings it back:
   while `DEV=1` the WIP/redeploy warning should keep showing by default rather
   than being silenced for the session by a single click.
6. The banner ends with a **"Source" link** to `cfg.sourceUrl` (from the
   `SOURCE_URL` env var, default the public site; point it at the code repository
   in `docker/.env`). Only an `http(s)` value is rendered, and clicking the link
   navigates instead of dismissing the banner (the dismiss handler ignores clicks
   on an `<a>`). The repo URL is deliberately **not hardcoded** in the committed
   source: it comes from the env var so no specific account/host is baked in.

## Error banners

So a visitor never has to open eruda to find out why something broke, failures
surface as explicit **red, dismissible banners** in the same top `#banners` stack
as the WIP banner (`js/error-banner.js`):

- It installs `window` `error` (capture phase, so failed resource loads count
  too) + `unhandledrejection` handlers that build a banner from the real message
  and, for script errors, the `file:line` it came from, rather than a vague
  "something went wrong".
- It exposes a global **`window.showErrorBanner(message)`** so app code can
  surface its own explicit errors the same way. `js/main.js` uses it for the
  brain-data load failure (replacing the old red `#status` pill there).
- Multiple errors **stack** as separate banners (newest below the dev banner /
  earlier errors); each has a **×** button to dismiss it. Identical messages are
  **de-duplicated** into one banner with an `(×N)` repeat counter (so a fault
  firing every animation frame can't flood the screen), and there is a hard cap
  (`MAX_BANNERS`) on distinct banners.
- A `ResizeObserver` on `#banners` republishes the stack height to the
  `--banners-height` CSS variable, which the `#status` pill's `top` offsets
  against, so the pill always sits below whatever is stacked (dev banner +
  errors), with no per-banner body class.

## Controls

- **Panel layout**: everything lives in one collapsible **"neurarium" panel at
  the bottom-left** (`#controls`
  in `index.html`, its header `#controls-toggle` collapses the whole body). Its
  body is split into a **`#settings-pane`** (the controls listed below) and a
  **`#details-pane`** (`#info-body`, the structure/connection/receptor/target/drug
  detail), switched by a **`#panel-tabs`** bar of **browser-style tabs**. The first
  tab, **Settings** (`#tab-settings`), is **pinned** (always first, never scrolled
  away) and shows the controls pane; every other tab is one **opened detail** in
  the scrollable **`#detail-tabs`** strip, each carrying a **×** to close it. The
  bar is hidden until the first detail is picked; picking one opens its tab,
  activates it (shows the Details pane) and expands the panel if collapsed, so a
  detail shows *in the panel* rather than a separate bottom-right window, and
  several details stay open at once like browser tabs (`createPanelTabs` in
  `js/main.js`; see "Detail tabs" + "Info panel" below). Clicking a tab
  re-activates that detail (re-rendering it *and* re-applying its 3D focus);
  clicking the **Settings** tab returns to the controls without closing any detail
  tabs (they stay as history); closing the last detail tab clears the 3D
  selection and falls back to Settings. From
  the top the Settings pane holds: the **reset + search + keyboard-shortcuts**
  icon buttons (a `.toolbar-row`), then
  the **Separate** and **Transparency** sliders, then **Auto-rotate** and **See
  inside**, then the
  nested collapsed **Legend** (`#legend`) whose first rows are the **Show all
  names** and **Hide projections** buttons followed by the **arrow colour-mode
  switch** (Neurotransmitter / Potential, `#color-mode`), then the nested
  collapsed **Receptors & targets** (`#receptors`) section, then the nested
  collapsed **Drugs** (`#drugs`) section (with its own `#drugs-filter` box), then
  the nested
  collapsed **About** (`#about`) section. Searching swaps the search box in place of the panel's
  normal contents (`#controls-main` hidden, `#search` shown) rather than opening
  a popup; the reset/search buttons stay visible so the magnifier toggles back.
  The panel / legend / receptors / drugs / about collapse headers share one
  `wireCollapse` helper in
  `js/main.js`. **Legend, Receptors, Drugs and About are an accordion**: opening
  one
  closes the others (only one open at a time), and while any is open every control
  above
  it (the `#lang-switch`, the `.toolbar-row`, the two sliders and the Auto-rotate
  / See inside checkboxes, all tagged
  `.collapsible-control`) is hidden via the
  `#controls.section-open` class so the open section's content doesn't push the
  panel tall; only the section headers stay visible. The accordion is wired as a
  list of `{toggle, body}` sections in `wireControls`, so adding another section
  is one array entry. `wireCollapse` takes an
  `onToggle(open)` callback
  and `setSection()` sets a section's state programmatically; `syncSectionLayout()`
  toggles `section-open`. A section can only be opened while the controls are
  visible (i.e. not searching), so this never hides the toolbar mid-search.
  **Small-screen pan-aside**: on a small screen the panel covers much of the
  centered brain, so while the panel body is **expanded** the rendered brain is
  pushed clear of it (and recentred when it collapses or on a wide screen). The
  layout differs by orientation:
  - **portrait**: an `@media (orientation: portrait)` rule (index.html) makes
    `#controls` span the **full width** but only the **bottom half** (`max-height:
    50vh`), and the brain is pushed straight **up** into the clear top section by
    half the panel's height fraction, so it sits centred in the space above the
    panel whatever the panel's actual height (which the `ResizeObserver` tracks as
    the Legend/About accordion grows it).
  - **narrow landscape** (`max-width: 700px`, not portrait): the panel stays a
    bottom-left box, so the brain is pushed to the **top-right** (`LANDSCAPE_PAN`).

  Wired in `wireControls` (`updatePanelPan`, gated on the panel actually being
  visible so `?ui=0` shots are unaffected; recomputed on the `orientation` /
  `max-width:700px` media-query flips and on a `ResizeObserver` over the panel)
  and applied via `focus.setScreenOffset` (see `createCameraFocus` below): a
  render-time **camera view offset** (`PerspectiveCamera.setViewOffset`), eased
  in/out in `focus.tick`, not a move of the orbit target, so the pan survives
  rotation/zoom/framing and reverts cleanly (and rescales itself on resize).
- **About** (`#about`, collapsed by default): a short blurb (what neurarium is,
  that it's a WIP, made by Olivier Cornelis + Claude) plus a **Source code** link
  whose href is set from `cfg.sourceUrl` by `js/main.js` (the row is removed if
  that isn't a valid `http(s)` URL), then a **licence line** (`about.license`,
  linking the canonical AGPL-3.0 text) which is a separate paragraph so it shows
  even when the source-code row is dropped. See "Dev / WIP banner" for
  `sourceUrl`.
- **Auto-rotate** checkbox: spins the camera around the brain (OrbitControls
  `autoRotate`). **On by default** (a slow turn on load); it switches itself off
  (and unticks the box) the moment the user picks content, i.e. any pick routed
  through the selection controller (a structure/arrow click-tap-or-search, a
  legend isolate, or a circuit), so what you clicked holds still. Clearing the
  selection does not re-enable it. Wired via `selection.onPick(stopAutoRotate)`
  in `js/main.js`. Deep links / screenshots get it forced **off** by
  `applyViewParams` unless `?autorotate=1` is passed, so a framed view holds.
- **See inside** checkbox (`#see-inside`, off by default): hides the structures
  on the camera-facing side of the brain so the deep nuclei aren't blocked by the
  near cortex (a "cutaway" without clipping geometry). `createNearCull` in
  `js/main.js` recomputes the hidden set **every frame** from the live
  camera/`controls.target`, so the near hemisphere peels away and follows as you
  orbit; a structure is hidden once its centre sits more than `NEAR_CULL_BIAS`
  past the centre plane toward the camera (the bias keeps the central core
  visible). It snapshots visibility on enable so toggling off restores exactly
  what was there, composing with `?only=` (already-hidden meshes stay hidden);
  isolate mode is independent (it dims via opacity, not visibility). Arrows are
  left visible (so the revealed connections still show). `cull.tick()` runs in
  the render loop after `controls.update()`.
- **Arrow colour-mode switch** (`#color-mode`, a two-state segmented control that
  lives in `#legend-actions` right under **Hide projections**, defaulting to
  **Neurotransmitter**): picks how every arrow is coloured. **Neurotransmitter**
  (the default) colours each arrow per molecule (`projection.color`, the
  `PROJECTION_COLORS` palette). **Potential** recolours every arrow by its coarse
  **sign** (`projection.signColor`): excitatory red, inhibitory blue, the
  neuromodulatory kinds (dopaminergic / cholinergic / neuroendocrine) a neutral
  "modulatory" grey. The maps are emitted by the generator into the data's `meta`
  record (`signColors` / `signLabels`, with the per-projection `sign` resolved in
  `js/data.js` from the meta `kind_signs` fold), not hardcoded. Picking an option
  marks the active button, recolours arrows in place (`ProjectionArrow.setColor`)
  **and rebuilds the legend** so its Projections section shows one row per sign
  (in Potential mode) instead of one per neurotransmitter; the legend's
  focus-greying callback is registered once and re-pointed on each rebuild (so the
  switch never stacks `onIsolate` listeners). The switch sits inside
  `#legend-actions`, which `buildLegend` preserves as a node across rebuilds, so
  its click listeners survive. See `projectionGroups` + the colour-mode wiring
  (`setColorMode`) in `js/main.js`.
- **Separate** slider (0..1, labelled "Separate" in the UI; the explode/`?explode`
  terminology lives on internally): pushes each region radially outward from
  the brain center to reveal deep structures. Tuning constant:
  `EXPLODE_STRENGTH` in `js/main.js`. As the regions spread the camera
  **auto-zooms out** (and back in as they reassemble) so the **whole brain keeps a
  constant apparent size** and only the individual structures appear to shrink as
  they separate: the explode handler calls `focus.zoomForExplode(amount)`
  (`createCameraFocus`), which scales the camera->target distance by the ratio of
  the assembly's true **outer radius** (`boundingRadiusAt`: `max` over regions of
  `|base| * (1 + amount * EXPLODE_STRENGTH) + that region's own radius`) at the new
  vs the last amount, applied as an incremental ratio so any manual zoom is
  preserved. (Scaling by the bare `1 + amount * EXPLODE_STRENGTH` spread factor
  instead would ignore the fixed structure radii and over-pull the camera back, so
  the brain would visibly shrink while exploding; folding the radii in holds it
  steady.)
- **Intro animation**: on a plain page load the regions start fully blown out
  and glide back together into the assembled whole, *exactly like dragging the
  Separate slider from 1 to 0*: the camera follows the spread (`zoomForExplode`,
  so the brain holds a steady apparent size) and at the same time sweeps
  `INTRO_ROTATION_TURNS` of a revolution (0.75), both finishing together on the
  resting view (`createIntroAnimation` in `js/main.js`, advanced once per frame
  in the render loop; duration `INTRO_DURATION_MS`, easeInOutCubic). It drives
  the explode slider in sync, owns the rotation itself (so OrbitControls'
  auto-rotate is suspended for the duration and restored at the end), is
  cancelled the moment the user grabs that slider, and is skipped when
  `?explode=` is pinned (deep links / headless screenshots) so the requested
  static amount is honored. The resting framing is deliberately a touch pulled
  back (the default `camera.position` and a `maxDistance` comfortably beyond the
  full spread so the intro's zoom-out isn't clamped). When the **dev / WIP
  banner** is up (`window.__APP_CONFIG__.dev === "1"`, the same flag
  `js/dev-banner.js` reads), the brain is presented a little lower and further
  back (`DEV_BANNER_DROP` lifts the look-point so it renders below the banner,
  `DEV_BANNER_UNZOOM` pulls the camera out), applied before the intro captures
  the pose so it settles there.
- **Transparency** slider: the value is the material opacity (left = more
  transparent); depth-writing is disabled while translucent so overlapping
  regions blend. Opacity is owned by the selection controller
  (`createSelection` in `js/main.js`), not a standalone helper, so the slider
  value and the isolate-mode dimming (below) compose into one final per-mesh
  opacity.
- **Selection / halo + isolate** (`createSelection` in `js/main.js`): the single
  source of truth for which structures/arrows are highlighted/focused.
  - Picking a structure in the 3D view (click/tap or a structure
    search result) gives it a soft glowing **halo** (a back-side additive shell
    child, `mesh.userData.halo`); this is a lightweight highlight only, no
    dimming. (A **double-click** instead isolates the structure, like its legend
    row, see below.) Picking an **arrow** (click/tap or a connection search result) halos
    it too (a fatter additive tube along its arc, `ProjectionArrow.setHalo`); the
    structure halo and arrow halo are mutually exclusive.
  - Clicking a **structure row in the legend** toggles that structure (both
    hemispheres) into the **isolate** set; clicking a **category heading** toggles
    every structure under it at once. While the set is non-empty the scene focuses
    on it: every other structure drops to a faint opacity (`DIM`), arrows that
    don't touch an isolated structure fade with them (`ProjectionArrow.
    setOpacity`), the isolated structures keep full (slider) opacity + halo, and
    the legend greys its non-isolated rows/headings (`.dimmed`, isolated ones get
    `.selected`). Legend selection is additive (click more rows to add).
  - The **Circuits** legend section lists curated functional loops (from the
    `circuit` records). Clicking one isolates *exactly* that circuit: its
    structures + the projections between them stay opaque, everything else fades
    (`selection.setCircuit`, which pins an explicit arrow set instead of the
    "touching" rule). Clicking the active circuit again clears it. Isolating a
    circuit also starts its **traveling-pulse animation** (see "Circuit
    animation" below): glowing beads sweep its arrows in sequence and loop, so the
    loop reads as signal flowing around it. The animation stops the instant the
    focus stops being that circuit.
  - The **Projections** legend section lists one row per projection group, the
    grouping following the active **colour mode** (the arrow colour-mode switch,
    Neurotransmitter / Potential, just above) so the legend always matches the
    arrows on screen:
    in the default per-**neurotransmitter** mode one row per molecule (e.g.
    `Glutamate (excitatory)`, coloured by its arrow colour and labelled with the
    functional kind in parens; per-transmitter not per-kind, so a kind carrying
    more than one transmitter splits automatically, though today's data is 1:1);
    in **Potential** (sign) mode one row per sign (Excitatory / Inhibitory / Modulatory,
    coloured by the sign swatch). The rows are built by `projectionGroups` in
    `js/main.js`. Each row is clickable: clicking one isolates *only* that group
    via the same `setCircuit` machinery (it pins every arrow in the group plus the
    structures they connect, so just those pathways + their endpoints stay opaque
    and everything else fades). Unlike a circuit, such a focus dims *every*
    structure, so its structure/heading rows grey out rather than lighting up;
    only the group row lights. Clicking the active one again clears it. The rows
    are built from the **non-tentative** projections only (the speculative ones
    live in their own section below).
  - The **Hypothetical pathways** legend section is separate and **off by
    default**: a single "Show speculative (N)" toggle reveals/hides every
    `tentative` projection's (dotted) arrow at once. They are deliberately kept
    out of the per-neurotransmitter rows so a speculative link never reads as an
    established one. Visibility composes with the global **Hide projections**
    button via `createProjectionVisibility` in `js/main.js`: an arrow shows only
    when projections aren't globally hidden *and* it is established or (when
    tentative) its section is toggled on (global-hide wins; re-showing restores
    the tentative arrows only if their section is on).
  - The **reset** button and a **double-click on empty space** fully clear it
    (halos + isolate + circuit), restoring default opacity. Framing a connection
    or arrow just swaps the halo, leaving any isolate set intact.
- **Structure names**: hovering a region with the mouse (or tapping it on a
  touch screen) shows its name as a floating label; tapping empty space clears
  it. Raycast in `js/main.js` -> `js/labels.js`. The hover pick (`pickHover`) is
  **focus-aware**: while something is focused (a halo'd structure, an isolated
  set, a circuit, a receptor's regions), a focused region the ray passes through
  wins over a nearer non-focused one, so hovering the thing you focused names
  *it* even when a dimmed region (e.g. the near cortex over an isolated deep
  nucleus) sits in front of it. The **Show all names** button
  (the legend's first row) forces every label on at once. Labels are boxless:
  white glyphs outlined in the structure's own color (`--label-color`) plus a
  black halo, so they stay legible over any region and overlapping names don't
  hide behind opaque boxes.
- **Legend**: nested inside the bottom-left panel, collapsed by default; click
  its header to expand. It starts with the **action buttons** (a `#legend-actions`
  container kept first across rebuilds by `buildLegend`, which preserves that
  node): **Show all names** and **Hide projections** (off by default; toggles
  every arrow's visibility at once via `arrow.setVisible`, and refreshes labels
  so the connection labels follow). The rest is generated from the data (see
  below). Each structure row is clickable to isolate/focus that region, and each
  **neurotransmitter row** is clickable to isolate that transmitter's pathways
  (see Selection above).
- **Receptors & targets** (`#receptors`, collapsed by default, the accordion peer
  between Legend and About): the merged `data.targets` browse list (every receptor
  from `data/receptors.jsonl` **plus** every non-receptor drug target from the
  meta `drug_targets` map: transporters, enzymes, ion channels, receptor groups),
  built by `buildTargetLegend` in `js/main.js` and grouped by **neurotransmitter
  system** (one `<h2>` per system, in the `receptor_family_labels` key order, then
  an **"Other / non-aminergic"** heading for the system-less ones), so a
  transporter like SERT sits under Serotonergic beside the 5-HT receptors. Each
  row's swatch is coloured by a receptor's excit/inhib/modulatory **sign** (a
  non-receptor target's **type** colour, `target_type_colors`), and a non-receptor
  row carries a muted **type tag** ("transporter", "enzyme", ...). Clicking a row
  **focuses** it: it dims the whole brain to just the regions it sits in and
  scatters glowing **dots** over those regions' surfaces (`createReceptorMarkers`,
  see "Receptors" below), and opens the **info-panel view**: a receptor opens
  `showReceptor` (the system, a Wikipedia link, the description, the classification
  facts and the region list, or "Throughout the brain" for a ubiquitous receptor);
  a non-receptor target opens the lighter `showTarget` (its system, a Wikipedia
  link or a TODO pill until one is gathered, the type + system facts, and the
  region list). Clicking the active row again clears it; switching to any other
  focus drops the dots. A **stub** receptor (no CNS role: empty locations) or an
  unlocated target renders muted and is not clickable. The dimming reuses
  `selection.setCircuit(regionMeshes, [])` (no arrow pin, so the pathways fade and
  the dots are the only bright thing); the markers are stopped off the selection
  state, the same way the circuit pulse is.
- **Drugs** (`#drugs`, collapsed by default, the accordion peer between Receptors &
  targets and About): the psychiatric drugs from `data/drugs.jsonl`, built by
  `buildDrugLegend` in `js/main.js` and grouped by **primary category** (one
  `<h2>` per category, in the `drug_category_labels` key order) with one row per
  drug. A **`#drugs-filter`** text box at the top of the section live-filters the
  rows by name (hiding empty category headings; an empty result shows a "no
  matches" line). Clicking a row **focuses** that drug: it dims the whole brain to
  the regions its targets sit in and plays the **per-drug animation** (effect-
  coloured gem dots pulsing boost/block/modulate over those regions,
  `createDrugAnimation`, see "Drugs" below), and opens the drug **info-panel
  view** (`createInfoPanel.showDrug`: the class, the NbN nomenclature, a Wikipedia
  link, the description, the **Acts on** binding list and the Stahl source).
  Clicking the active row again clears it; switching to any other focus drops the
  dots. A drug with no mapped bindings renders muted and is not clickable. The
  dimming reuses `selection.setCircuit(regionMeshes, [])` and the animation is
  stopped off the selection state, exactly like the receptor markers.
- **Touch / mouse**: one finger or left-drag rotates; two-finger pinch (or
  scroll wheel) zooms; two-finger drag pans. Handled by OrbitControls.
  **Shift + wheel** drives the **Separate** slider instead of zooming: a
  capture-phase `window` wheel listener in `js/main.js` runs before
  OrbitControls, and on `shiftKey` swallows the event (preventDefault +
  stopPropagation) and nudges the slider (dispatching its `input` event so the
  intro-cancel + re-aim fire). Plain wheel falls through to zoom.
- **Keyboard shortcuts** (`wireShortcuts` in `js/main.js`): single-key, no
  modifier, ignored while typing in a field (and Ctrl/Cmd/Alt combos are left
  alone so Ctrl/Cmd+F still works). **n** toggles all names, **s** spreads fully
  or back to assembled (toggling the **Separate** slider), **l** collapses /
  expands the **Legend** section, **c** toggles **See inside**, **r** toggles the
  **Receptors & targets** section, **m** toggles the **Drugs** (meds) section,
  **f** opens search (the bare-key twin of **Ctrl/Cmd+F**), **Tab** /
  **Shift+Tab** cycle the open **detail tabs** (the pinned Settings tab + each
  opened detail, wrapping; `tabs.cycle` re-applies a detail's 3D focus on landing,
  and the key keeps its default focus move when no detail is open), **Esc** closes
  search and collapses any open Legend / Receptors / Drugs / About section. Each
  maps to
  an existing control by **clicking the same DOM element** a mouse user would (or
  dispatching the slider's `input`), so there is no duplicated behaviour; a
  handled key calls `preventDefault` so `f` never types into the search box it
  just focused. The same shortcuts are listed in the **shortcuts help popup**
  (see below).
- **Keyboard + reset + search** (the icon-button row at the top of the panel,
  just above the
  sliders, spread across the row via `justify-content: space-between`): a
  **keyboard-shortcuts** button (keyboard icon, **left**) opens the shortcuts help
  popup (below), a **reset** button (crosshair icon, **center**) recenters the
  camera on the
  middle of the brain and re-frames the whole thing (useful after panning slides
  it off-center), and a **search** button (magnifier icon, **right**) swaps a
  search box in
  place of the panel body (not a popup). The search box filters
  **structures (by name),
  connections (by pathway label), receptors (by name / neurotransmitter /
  system) and drugs (by name / category / target)**. Picking a structure centers
  on it,
  shows its label, and opens its structure panel (below);
  picking a connection frames its two endpoints and opens the connection panel;
  picking a receptor frames the regions expressing it and focuses it (dim + dots +
  receptor panel), exactly like clicking its Receptors legend row; picking a drug
  frames its regions and focuses it (dim + animation + drug panel), exactly like
  clicking its Drugs legend row. Receptor rows
  show their neurotransmitter as a `· tag` and drug rows their primary category;
  only **focusable** receptors / drugs are
  searchable (stubs + binding-less drugs are legend-only). The match runs over
  each item's display
  label plus hidden `keywords` (a receptor's family / mechanism / sign, a drug's
  category / target names).
  Connection results carry a hemisphere tag (`R` / `L` / `L↔R`) so the mirrored
  twins stay distinct (`connectionSideTag` in `js/main.js`). **Ctrl/Cmd+F** is a
  shortcut for the same search: a `window` keydown listener intercepts it (so the
  browser's native page-find, useless on a canvas + data app, never opens),
  expands the panel if it was collapsed (the search box lives inside the panel
  body) and opens search focused on its input; pressing it again while open just
  refocuses + selects the text. **Escape** closes search. The results are
  **keyboard-navigable**: rendering pre-highlights the first row (a `.active`
  class), **ArrowDown** / **ArrowUp** move the highlight (wrapping; hovering a row
  syncs it), and **Enter** activates the highlighted row (so a bare Enter after
  typing picks the first result). `activeIndex` + `highlight()` in `wireToolbar`.
- **Keyboard-shortcuts help popup** (`#shortcuts-modal`, built by
  `wireShortcutsHelp` in `js/main.js`): a centered dialog over a dimmed full-
  screen backdrop (a `.modal-overlay`, reusing `.panel` for the glass look)
  listing each shortcut as a `<kbd>` key + a localized action. The key -> action
  rows are generated from a list that mirrors the bindings in `wireShortcuts`, so
  the popup can't drift from the real shortcuts; the action labels come from the
  `shortcuts.*` i18n keys. Opened by the toolbar's **keyboard** button or the
  **?** key; closed by the **×**, a click on the backdrop, or **Esc** (when the
  popup is open `wireShortcuts` routes Esc to close it first, before any
  search/section collapse). Like `.panel-tabs`, the overlay needs a
  `.modal-overlay[hidden]` rule so the `hidden` attribute wins over its
  `display:grid`.
- **Detail tabs** (`createPanelTabs` in `js/main.js`, the `#panel-tabs` bar; see
  "Panel layout"): the browser-style tab strip. It owns *only* the tab strip + which
  pane shows; it does **not** know how to render a detail or apply its 3D focus.
  The `select*` layer in `main()` (selectStructure / selectConnection / focusTarget
  / focusDrug) renders the detail + focuses the scene, then calls
  `openDetailTab(key, title, reopen)` to register/activate the tab. The `reopen`
  thunk re-runs that same `select*`, so clicking a tab restores both the panel
  content and the scene with no duplicated render logic. Tab **key** dedupes one
  tab per thing (`structure:<id>`, `connection:<from>-><to>`, `target:<id>`,
  `drug:<id>`); `MAX_TABS` bounds the strip (oldest inactive drops). Closing the
  active tab falls back to a neighbour (re-applying its focus) or, if it was the
  last, to Settings + an `onEmpty()` that clears the selection
  (`tabs.setOnEmpty(() => selection.clear())`). Interactions: click a tab to
  activate, click its **×** to close, **long-press then drag** a tab to reorder
  (pointer-based, ~450 ms hold; a move before the hold fires is a scroll instead;
  the DOM is reordered live and `openTabs` synced on drop), and **wheel / touch-
  drag** scrolls the overflowing strip (`touch-action: pan-x`). A real drag sets a
  one-shot `suppressClick` so the drag's synthetic click doesn't also re-activate
  the tab. The `panel.closeTab` i18n key labels the × for a11y. **Tab** /
  **Shift+Tab** (wired in `wireShortcuts`) cycle the active tab via `tabs.cycle`,
  through Settings + the open details in strip order, wrapping.
- **Info panel** (the **Details pane** of the main panel, `createInfoPanel` in
  `js/main.js`, rendered into `#info-body`; the active **detail tab** drives which
  one shows, see "Detail tabs" + "Panel layout"): shows a *connection*, a
  *structure*, a *receptor* (via
  `showReceptor`, opened from a Receptors legend row, see "Receptors" above), or a
  *drug* (via `showDrug`, opened from a Drugs legend row / drug search, see
  "Drugs" above: its class, NbN nomenclature, Wikipedia link, description, the
  **Acts on** list of bindings (each an effect-coloured swatch + the target name +
  the action·note, dimmed when tentative) and the Stahl source).
  `createInfoPanel` is pure rendering: opening the matching tab + applying the 3D
  focus is the caller's (`select*`) job, so each show*() is reused unchanged
  whether the detail is first picked or re-shown by clicking its tab. An empty-
  space click returns to Settings via `tabs.showSettings()` (the detail tabs stay).
  Everywhere a data **source / reference** is shown (the connection + drug
  **Source(s)** list and every **Wikipedia / Reference** row), a small **"?"
  caveat badge** sits next to it (`makeHelpIcon` in `createInfoPanel`): its
  tooltip warns that the sources are **LLM-inferred (web + the Stahl PDF) and not
  yet human-checked**. The tooltip shows on hover and is pinned on click/tap (a
  `.show` class), so touch devices (no `:hover`) can read it too; it is anchored
  to the full-width `.info-sources` / `.info-wiki` container (not the tiny icon)
  so its `left:0/right:0` bubble can't overflow + be clipped by the narrow panel.
  The message is the `info.sourceCaveat` i18n key (NOT the About / dev-banner
  "Source code" link, which points at the code repo, not a data source).
  - **Clicking/tapping an arrow** (or picking a connection in search) shows the
    **connection** view: the pathway label, its route (`from → to`, `↔` for a
    bidirectional/commissural link), kind + neurotransmitter, a one-line
    description, and its sources (a verified http(s) url renders as a link, a
    `"TODO"` url as a small orange "TODO" pill badge next to the citation). Built
    from the projection's metadata. Arrow
    picking (`pickArrowAt`) takes priority over the region behind it.
  - **Clicking/tapping a structure** (or a structure search
    result) shows the **structure** view (`showStructure`): its name, its group
    heading (from `data.meta.groupLabels`), a **Wikipedia link** when the
    structure record carries a `wikipedia` url (rendered only for an http(s)
    value), and the list of pathways touching it. Each connection row
    shows a kind-coloured swatch, a direction glyph (`→` it projects out, `←` it
    receives, `↔` reciprocal) and the other endpoint; **clicking a row jumps to
    that pathway** (frames the endpoints, halos the arrow, swaps in the
    connection view) via the panel's `onConnection` hook, wired in `js/main.js`
    to the same action as a connection search result. A structure with no mapped
    pathways shows "No mapped connections yet."
  - A click/tap that **misses** every arrow and structure (empty space) closes
    the panel.
- **Double-click**: on a structure **isolates/focuses** it (both hemispheres),
  exactly like clicking its legend row (`selection.toggleIsolate`, see Selection
  above); on empty space recenters the whole brain (same as the reset button).
- All camera framing above (reset, search) goes through one smooth
  tween, `createCameraFocus` in `js/main.js`: it moves the orbit pivot and
  camera distance but keeps the current view direction, is advanced once per
  frame in the render loop, and is cancelled the moment the user grabs the
  controls so a drag always wins. It also owns the **screen offset**
  (`setScreenOffset(x,y)`, eased in `tick`): a render-time `setViewOffset` that
  shifts the rendered brain by a fraction of the viewport without touching the
  orbit target, used for the phone/portrait pan-aside (see "Panel layout").
- After focusing a single structure (a structure search), moving
  the **blow-out** slider keeps that structure centered: `createCameraFocus`
  remembers it (`focused`) and `reaimFocused()` (called from the explode handler)
  re-points the orbit pivot at its new exploded position. Only the pivot moves,
  so the camera *rotates in place* to track it (a reorientation, not a
  translation), preserving the distance + angle you set. Framing a connection or
  the whole brain clears the tracked structure.

## Circuit animation

Isolating a circuit (clicking a row in the legend's **Circuits** section) plays a
**traveling-pulse animation** over that loop: a short **volley** of glowing beads
rides each of the circuit's arrows from its source region to its target, the
volleys firing in sequence and looping, so a curated loop (the direct pathway, the
Papez memory circuit, ...) reads as signal *flowing* around it rather than as a
static set of arrows. It is split in two on purpose:

- **`js/circuit-schedule.js` (the ordering, no three.js).** `scheduleCircuit`
  computes the firing order with **no hand-authored path**: the circuit's arrows
  are a directed graph (node = structure, edge = arrow, direction `from -> to`); a
  breadth-first search spreads activation from the seeds and each arrow's firing
  slot (`phase`) is the BFS depth of its tail. Stepping a clock through the depths
  and wrapping sweeps the pulses around and loops. It degrades gracefully on any
  arrow set. The **seed** per weakly-connected component is the node whose
  structure `group == "lobe"` (cortex is the conventional top of these loops), else
  the highest-out-degree node, else any. **Left-right symmetry** is enforced: the
  seed set is *mirror-completed* (each seed's `_R`/`_L` twin is added, via
  `mirrorId`) and the BFS is *multi-source*, so over a mirror-symmetric circuit the
  mirror-paired nodes get equal depth and the two hemispheres pulse in step,
  whether the circuit is two disjoint L/R loops (the direct pathway) or a single
  component whose halves join through a shared **midline hub** (cortex -> brainstem
  -> cerebellum -> thalamus), which a one-sided seed would otherwise sweep
  asymmetrically. An off-cycle **feeder branch** (e.g. the nigrostriatal dopamine
  input into the direct pathway) just fires when activation reaches its tail, or at
  the top of the cycle if no seed reaches it, instead of breaking a single path.
  Kept dependency-free so this ordering logic stays isolated and unit-testable.
- **`js/circuit-anim.js` (the rendering).** `createCircuitAnimation` turns each
  scheduled slot into an additive glowing sphere riding that arrow's live curve
  (`arrow.curve`, exposed by `js/arrows.js` and rebuilt on every explode, so the
  beads track the layout). One controller per scene, `tick()`ed once per frame in
  the render loop (like the intro/focus tweens). `STEP_MS` is the per-slot
  duration; the whole loop is `numSteps * STEP_MS`. Each arrow fires a **burst** of
  beads at the start of its slot, the burst's character keyed off the projection's
  `sign` (`BURST` table): an **excitatory** arrow sends more beads, faster and
  brighter (a dramatic volley); an **inhibitory** one fewer, slower and dimmer;
  modulatory sits between. The beads in a volley are spaced `gap` apart along the
  arc and advance at `speed` x the slot rate (> 1, so the volley lands early and
  reads as a burst then a pause); `scale`/`bright` size + brighten them. A bead
  hides while its arrow is hidden (so the global "Hide projections" toggle clears
  the beads too). As a bead **lands**, its target region briefly brightens (a
  *node flash*): a back-side additive shell per target node (the same geometry-
  reuse trick as the selection halo, but owned here and sized a touch larger, so
  it reads on top of any steady isolate halo) whose opacity is topped up as the
  bead reaches the surface and then decays (`FLASH_DECAY_MS`), so the hand-off
  from arrow to arrow around the loop is legible, not just the moving beads.

**Lifecycle (in `js/main.js`).** The circuit legend row calls
`selection.setCircuit(...)` then `circuitAnim.play(circuitArrows)`. Stopping is
driven off the selection state, not scattered call sites: `createSelection`'s
`onIsolate` is multi-subscriber, and the animation subscribes a watcher that
calls `circuitAnim.stop()` whenever the live pinned-arrow set is no longer exactly
the animating circuit (`circuitAnim.matches`). So a clear, a different circuit, a
projection-group focus (a neurotransmitter or sign row), or a legend isolate all
stop it, while merely highlighting a structure (which leaves the circuit pinned)
keeps it running. The animation is **circuit-only**: a projection-group focus also
goes through `setCircuit` but never calls `play`. No new user-visible string (the
trigger is the existing circuit row), so no i18n change.

## Receptors

A dataset of neurotransmitter **receptors** (`data/receptors.jsonl`, authored as
the `RECEPTORS` list in `tools/generate_data.py`), surfaced (together with the
non-receptor drug targets, see "Receptors & targets" just below) as a focusable
**Receptors & targets** legend section. The point is anatomical: see, per receptor,
which modeled regions express it, plus its functional classification, sourced from
each receptor's Wikipedia article. Split, like the rest, into data and rendering:

- **Data (`tools/generate_data.py` -> `data/receptors.jsonl`).** Each receptor
  carries its `neurotransmitter`, mechanism `receptor_class` (ionotropic /
  metabotropic / chaperone), excit/inhib/modulatory `sign` (reusing the projection
  `SIGN_COLORS` / `SIGN_LABELS`, so the swatch matches the arrow colour mode),
  `synaptic` site (pre / post / both), and `locations` (structure **base** ids,
  like a circuit; the viewer expands each to both hemispheres). The sentinel
  `locations="ALL"` is emitted as `ubiquitous:true` for a brain-wide receptor
  (NMDA, AMPA, GABA-A/B, mGluR7), which lights every structure. A receptor with no
  meaningful CNS role is a deliberate **stub**: empty `locations`, no
  `description`, rendered muted + inert. `_receptor_record` validates every
  family / class / sign / synaptic key against its map and every location base
  against the known structures. The receptor location set drove three new
  structures (`brainstem_nuclei` group: raphe, locus coeruleus, VTA), the
  neuromodulatory source nuclei the pathways already needed.
- **Rendering (`js/receptor-markers.js` + `js/main.js`).** Clicking a receptor row
  (`buildTargetLegend`, which builds the merged Receptors & targets list) dims the
  brain to just its regions via
  `selection.setCircuit(regionMeshes, [])` (no arrow pin, so all pathways fade and
  the dots are the only bright thing) and calls
  `createReceptorMarkers.show(regionMeshes, signColour)`, which scatters dense
  additive glowing **gem dots** over each region's surface (a `THREE.Points` cloud,
  a crisp bright core + a 4-point sparkle-star sprite so they read as shiny gems
  rather than stains/spots; count scaled per region by surface area), each cloud
  sampled from the structure mesh's own geometry and parented to it, so the dots
  track the explode/mirror transform and vanish when the mesh is hidden, exactly
  like the selection halo + circuit node-flash shells). The info panel switches to
  the receptor view (`showReceptor`). The markers are stopped off the selection
  state, the same pattern as the circuit pulse: a `selection.onIsolate` watcher
  hides them the moment the isolate set is no longer exactly the receptor's region
  set (`createReceptorMarkers.matches`), so a clear, a circuit, a legend isolate or
  another receptor all drop them.

**Receptors & targets (the merged browse list).** The legend section is *not*
receptors-only: it lists the unified `data.targets`, every receptor **plus** every
non-receptor drug target (transporters, enzymes, ion channels, receptor groups)
from the meta `drug_targets` map, so a target a drug acts on (SERT, MAO-A, Nav, ...)
is explorable on its own, not only as a line in a drug's "Acts on" list. The two
sources are normalized to one shape in `js/data.js` and grouped by neurotransmitter
`system` (then an "Other / non-aminergic" heading), so SERT sits under Serotonergic
beside the 5-HT receptors. A receptor isn't a transporter, so the distinction is
kept: a receptor keeps its sign swatch + full `showReceptor` panel, a non-receptor
target gets its `type`-colour swatch, a muted type tag, and the lighter
`showTarget` panel (its system, a Wikipedia link or a TODO pill until one is
gathered, the type + system facts, the region list). The *focus* machinery is
shared (the same `focusTarget` path, `createReceptorMarkers` dots and
`setCircuit` dimming serve both); only the panel view + swatch colour differ by
`kind`. A non-receptor target's `type` (transporter / enzyme / ion_channel /
vesicle_protein / receptor_group), `system`, region footprint and optional
`wikipedia` are authored in the `DRUG_TARGETS` map in `tools/generate_data.py` (see
"Drugs" and "Changing the data"); the regions currently carry no per-target source,
hence the TODO pill.

To add or edit a receptor, see "Changing the data" below.

## Drugs

A dataset of psychiatric **drugs** (`data/drugs.jsonl`), surfaced as a focusable
**Drugs** legend section with a per-drug brain animation. The point is to show, for
each drug, *what it does to the brain*: which molecular targets it acts on, how, and
where those targets sit. The data is sourced from **Stahl's Prescriber's Guide
(8th ed.)** under fair-use sourcing, extracted **strictly from the dump** (only
interactions literally stated in the source text; nothing supplemented from outside
pharmacology, gaps left as TODO / no binding). Split, like the rest, into data and
rendering:

- **Data (`tools/drugs_data.json` -> `data/drugs.jsonl`).** Unlike the receptors,
  the 158 drugs are **not** authored inline in `generate_data.py` (too large); they
  live in a sibling `tools/drugs_data.json` read by `_load_drugs()` (a missing file
  is a warning, not an error, so the generator still runs without it). Each drug has
  `id`, `name` (technical, language-neutral), `categories` (coarse classes), an
  optional `nbn` (Neuroscience-based Nomenclature) and `description` (both authored
  inline as `{en,fr}`, bypassing the shared FR table), a Wikipedia url, and
  `bindings`. A **binding** is a `target` + `action` (+ optional `effect` override,
  `note`, `tentative`). The drug **vocabularies** are defined once in
  `generate_data.py`: `DRUG_CATEGORY_LABELS` (coarse class -> {en,fr}),
  `DRUG_ACTIONS` (action -> {label:{en,fr}, net `effect`}), `DRUG_EFFECT_COLORS` /
  `DRUG_EFFECT_LABELS` (boost emerald / block rose / modulate violet) and
  `DRUG_TARGETS` (the non-receptor targets: transporters / enzymes / channels /
  generic receptor families, each with `{name:{en,fr}, type, system, regions[bases],
  optional wikipedia}`, where `type` is a `TARGET_TYPE_LABELS` key driving the
  merged Receptors & targets legend's swatch colour + tag).
  `_build_drug_targets()` **merges** `DRUG_TARGETS` with every receptor id (so a
  binding can target either a coarse target like `sert` or a specific receptor like
  `5ht2a`, the latter linked back to its receptor record for its regions), and that
  merged map is emitted into `meta.json` as `drug_targets` (also the source of the
  browsable Receptors & targets list, see "Receptors"). `_drug_record()`
  validates every category / target / action / effect against the vocabularies (and
  rejects duplicate ids) and attaches the constant `STAHL_SOURCE` citation. A drug
  with no bindings is emitted `focusable: false` (listed, not clickable), like a
  receptor stub. The net `effect` of a binding (which colours the animation) comes
  from its action: agonist / reuptake-inhibitor / releaser / enzyme-inhibitor / PAM
  -> **boost**; antagonist / inverse-agonist / NAM / blocker -> **block**; partial
  agonist / modulator -> **modulate**.
- **Rendering (`js/drug-anim.js` + `js/main.js`).** Clicking a drug row
  (`buildDrugLegend`, grouped by primary category in the meta order, with a live
  `#drugs-filter` box) **focuses** that drug: it dims the brain to the union of the
  drug's targets' regions via `selection.setCircuit(regionMeshes, [])` (no arrow
  pin, so the pathways fade and the dots are the only bright thing) and calls
  `createDrugAnimation.show(drug, meshById)`, which scatters a gem cloud
  (`buildGemCloud`, reused from `js/receptor-markers.js`) over each binding's
  regions coloured by that binding's net-effect colour, pulsing per effect (boost
  fast/bright/swelling, block slow/dim, modulate in between). The info panel
  switches to the drug view (`createInfoPanel.showDrug`: the class, the NbN
  nomenclature, a Wikipedia link, the description, the **Acts on** list (one row per
  binding: an effect-coloured swatch + the target name + the action·note, dimmed +
  italic when tentative), and the Stahl source). Drugs are also searchable (name /
  category / target keywords). The animation is stopped off the selection state, the
  same pattern as the receptor markers + circuit pulse: a `selection.onIsolate`
  watcher hides it the moment the isolate set is no longer exactly the drug's region
  set (`createDrugAnimation.matches`).

The drug data was extracted by **parallel agents** from per-drug source text. 44
drugs lacked a structured "How the Drug Works" entry in the dump's Q/A and were
recovered from the dump's full-page OCR (`PageImages`); 5 drugs remain unbound
because they are genuinely non-receptor agents (lithium, disulfiram, l-methylfolate,
triiodothyronine, caprylidene). The source `url` on the Stahl citation is currently
the literal **"TODO"** (rendered as an orange TODO pill in the panel) pending a real
reference link.

To add or edit a drug, see "Changing the data" below.

## Changing the data

1. Edit the `PAIRED`, `MIDLINE`, or `PROJECTIONS` lists in `generate_data.py`.
   - Paired entries are auto-mirrored to both hemispheres (`_R` / `_L`). Define
     them on the **right** side (x > 0); the generator emits one shared
     right-side shape file and the `_L` member references it with `mirror:true`,
     so the viewer reflects the geometry across x (a *true* mirror, not a copy).
   - A region is a gradient-noise-deformed ellipsoid by default
     (`radii`/`seed`/`detail`/`noise`). Optional surface knobs shape the
     character of that noise (consumed by `buildBlobGeometry` in `js/shapes.js`):
     - `octaves` (default 1): fBm layers; >1 adds finer wrinkles on the broad
       form. Cortex uses ~2 with a small `noise` so the lobes stay smooth broad
       domes (the surface *swirl motif* is drawn in the shader, see below, not
       geometry). The
       ridged path is a ridged-multifractal: each finer octave is gated by the
       coarser one's ridge strength, so troughs stay smooth instead of filling
       with creases.
     - `ridged` (default False): fold the noise into sharp creases along its
       zero-set. This is what turns lumps into folia (the cerebellum). Needs
       higher `detail` (6) and lower `noise` than a smooth blob, and a `frequency`
       that sets how many folds. (The cortical lobes no longer use it: they are
       smooth domes carrying the cel-shaded swirl motif instead.)
     - `frequency` (default 2.4): noise lattice frequency; higher = smaller,
       more numerous folds.
     - `aniso` ([ax,ay,az], default [1,1,1]): per-axis frequency skew. Equal =
       isotropic meandering gyri; a big single-axis value stacks near-parallel
       bands (the cerebellum's folia use a strong y skew).
     Smooth deep nuclei just use `detail` 5 + a small `noise` (~0.05) and none of
     the above.
     - `clip` ({x/y/z min/max}): cut axis-aligned flat faces. Rarely set by hand;
       setting `medial=True` on a lobe makes the generator derive the right medial
       clip from its side so the hemispheres meet at the midline (see below).
     - `clip_planes` (auto, never authored): the generator computes a bisecting
       cut plane between each blob and every overlapping *same-group* neighbour
       (`_bisecting_clip_planes` in `generate_data.py`) and clamps vertices past
       it onto it (`buildBlobGeometry`), so overlapping regions grow flat mating
       faces and tile flush like jigsaw pieces (the lobes, and the deep nuclei
       among themselves) instead of one colour poking through another. Adjacency
       is derived from the geometry (a plane appears only where two bodies' reach
       overlaps), the seam is split by each body's reach so the larger keeps more,
       and only blobs take part (curves/composites are skipped). It is built once
       on the right side and mirrored with the rest of the geometry. The
       `JIGSAW_CLIP.enabled` flag in `js/shapes.js` is the A/B switch: turn it off
       to ignore the planes (regions overlap as before) without regenerating; the
       medial wall is independent and always applied.
     - `carve_tubes` (auto, never authored): a curve flagged `carves=True` (the
       caudate) hollows a swept-tube *channel* out of every lobe its spine threads,
       so it sits in a clean notch ("partly exposed", a jigsaw piece set into the
       seam) instead of the cortex poking through it. The generator
       (`_tube_carve` in `generate_data.py`) emits, on each threaded lobe, the
       carver's spine points + per-station channel radius (its `profile` inflated
       by noise + `LOBE_CARVE_GAP`) in that lobe's local frame;
       `buildBlobGeometry` pushes any lobe vertex inside the tube out onto the
       tube surface. Adjacency is geometry-derived (a spine point reaching inside
       the lobe), only `group=="lobe"` blobs are carved (a nucleus never carves a
       lobe), and like the planes it is computed once on the right side and
       mirrored. The `CARVE_TUBES.enabled` flag in `js/shapes.js` is the A/B
       switch. (The caudate is also nudged up so its head emerges through the
       fronto-parietal seam; per-explode it pulls back out of the notch, which is
       expected.)
     - The cortical surface pattern is *not* geometry: every `group=="lobe"`
       structure is a smooth dome rendered **cel-shaded** (a `MeshToonMaterial`
       with a shared N-step grey `gradientMap`, so its lighting falls into flat
       bands) carrying a **swirl motif** drawn in the shader
       (`injectCortexSwirl` / the `CORTEX_SWIRL` knobs in `js/shapes.js`). The
       motif is a domain-warped noise field whose evenly-spaced contour lines are
       darkened into "ink" lines (the warp curls them into loose spirals); the
       darkening is applied to `diffuseColor` *before* lighting, so it stays a
       flat painted-on pattern with no relief, no faceting, no extra triangles.
       Tune via `CORTEX_SWIRL`: `freq` (swirl size), `warp` (how spirally),
       `rings` (lines per unit), `width` (line thickness), `ink` (line darkness),
       `octaves` (low = clean loops), `steps` (toon lighting bands);
       `enabled:false` drops the lobes back to the plain smooth material. It lives
       in JS, not the data.
   - Give a region a `shape=dict(type="curve", ...)` for a round-capped tapered
     tube instead of an ellipsoid (the caudate, the brainstem): `points` is the
     spine head->tail, `profile` the radius sampled along it (caps close each
     end). A paired `curve` may now be asymmetric across x (e.g. an off-midline
     spine): the `_L` member is a true reflection of the right-side geometry, so
     it flips correctly. Midline curves like the brainstem are emitted once and
     never mirrored. A curve may also carry `carves=True` to make it hollow a
     notch in the lobes it threads (see `carve_tubes` above; only the caudate uses
     it).
   - Give a region a `shape=dict(type="composite", parts=[...])` to merge several
     sub-shapes into one mesh; each part is a shape payload (usually a blob) with
     optional `offset`/`scale`/`rotate`. Used for the cerebellum (two foliated
     hemispheres + a central vermis). A paired composite is mirrored as a whole
     for the `_L` side, so its parts may sit asymmetrically across x.
   - Layout / "lock into place": regions are positioned (the `pos` field) so that
     at explode 0 they assemble into a whole brain, and the explode slider pushes
     each radially outward from the origin (`EXPLODE_STRENGTH` in `js/main.js`).
     The cortical lobes are sized to *overlap* their neighbors (so their union is
     one continuous hemisphere, not separate balls) and flagged `medial` so a
     flat wall at `MIDLINE_GAP` forms the longitudinal fissure; the temporal is
     the exception (lateral, below the Sylvian fissure: no medial wall, just a
     flat `ymax` top). Deep nuclei sit small and central so they hide inside the
     cortex at 0 and are revealed by exploding. When moving a lobe, re-render the
     assembled hemisphere (`only=frontal_R,parietal_R,temporal_R,occipital_R&
     explode=0&view=right|left|top`) to check the seams and the medial wall.
   - To give a region a **Wikipedia link**, add its `base` id + article URL to the
     `WIKIPEDIA` registry near the top of `generate_data.py` (a small map keyed by
     base id, like `SOURCES`, so both hemispheres of a pair share the one article
     written once). The generator attaches the URL to each structure record
     (`_structure_record`) and the viewer shows it as a link in the structure info
     panel; a base absent from the map just gets no link, and a key that is not a
     known structure base raises in `build_records` (typo guard).
   - Projection `from`/`to` reference structure ids (e.g. `putamen_R`). The arrow
     points `from` -> `to` (a cone at the target end).
   - A projection carries metadata so the viewer can explain it: `label` (short
     pathway name, also what the search box matches on), `neurotransmitter` (the
     specific molecule), `description` (one-line summary), and `sources` (a list
     of `SOURCES` keys). Keep the `label` unique-ish and human-readable: clicking
     an arrow or picking it in the search opens an info panel built from these
     fields, so every connection must have a name.
   - `sources`: cite shared references by short key from the `SOURCES` registry at
     the top of `generate_data.py` (so a citation common to several pathways is
     written once); the generator expands each key to a full `{citation, url}`
     object in the emitted data (`_expand_sources`, raises on an unknown key). New
     references go in `SOURCES`; leave `url` as the literal `"TODO"` until a real
     link is verified (the panel renders an http(s) url as a link, `"TODO"` as a
     small orange "TODO" pill badge). **There are currently TODO urls on every source** awaiting real
     DOIs/links.
   - `bidirectional: True` draws a cone at *both* ends (reciprocal / commissural
     pathways). Use it with `symmetric: False` and explicit `_L`/`_R` endpoints
     for the commissures (corpus callosum, anterior commissure) so the single
     cross-midline connection is not mirrored into a duplicate.
   - `tentative: True` marks a **speculative / less-certain** pathway. It is
     carried through to the emitted record; the viewer draws such arrows as a
     *dotted* tube and lists them in a separate, off-by-default "Hypothetical
     pathways" legend section (not in the per-neurotransmitter rows), so they read
     as "maybe" and never masquerade as established connections.
   - Projections are **bilateral by default**: define a symmetric pathway once
     on the right and the generator emits a hemisphere-flipped twin (`_R` <->
     `_L` on both endpoints; midline endpoints stay put). Set
     `"symmetric": False` on an entry to keep a genuinely one-sided pathway from
     being mirrored. The flag is a generator hint and is stripped from the data.
   - Projection `kind` must be a key of `PROJECTION_COLORS` in
     `tools/generate_data.py` (`excitatory`, `inhibitory`, `dopaminergic`,
     `cholinergic`, `neuroendocrine`); add
     new kinds there (the generator raises if a projection uses an unmapped kind)
     + in this doc if needed. The map is emitted into the data's `meta.json` and
     each projection gets a resolved `color` at load, so the viewer never
     hardcodes the palette. `kind` drives the arrow *color*; `neurotransmitter` is
     the finer label shown in the info panel. A new kind must also be folded onto a
     **sign** in `KIND_TO_SIGN` (`excitatory` / `inhibitory` / `modulatory`) for
     the panel's excit/inhib colour mode (`SIGN_COLORS` / `SIGN_LABELS` give the
     sign its grey/red/blue swatch + heading); these are emitted into `meta` too,
     and the per-projection `sign` is resolved in `js/data.js`. The pulse animation
     also keys its burst size/speed off that sign (`BURST` in `js/circuit-anim.js`).
   - To add a named **circuit**, append to the `CIRCUITS` list: `id`, `name`, and
     `structures` as **base** ids (no `_R`/`_L`). The generator expands each base
     to whatever was emitted (both hemispheres, or the bare id for a midline form)
     and raises on a typo; the circuit's arrows are *not* listed (the viewer takes
     every projection whose endpoints are both in the set), so a circuit never
     duplicates the pathway list. It shows up in the legend's Circuits section.
   - To add a **receptor**, append to the `RECEPTORS` list: `id`, `name` (the
     technical, language-neutral label, e.g. `"5-HT2A"`), `family` (a key of
     `RECEPTOR_FAMILY_LABELS`), `neurotransmitter`, `receptor_class`
     (`ionotropic` / `metabotropic` / `chaperone`), `sign`
     (`excitatory` / `inhibitory` / `modulatory`), `synaptic`
     (`presynaptic` / `postsynaptic` / `both`), and `locations` as structure
     **base** ids (no `_R`/`_L`; the viewer expands each to both hemispheres), or
     the sentinel `"ALL"` for a brain-wide receptor (emitted as `ubiquitous`). Add
     an `{en}` `description` + its `description_fr` (authored inline, unique per
     receptor, so it bypasses the shared `FR` table) and a `wikipedia` url. A
     receptor with no meaningful CNS role is a **stub**: give it empty `locations`
     and no `description`. `_receptor_record` validates every family / class / sign
     / synaptic key against its map and every location base against the known
     structures, and rejects duplicate ids. A new `family` / `receptor_class` /
     `synaptic` value needs an entry in the matching label map (and its `FR`
     translation) or the build raises. It shows up in the legend's Receptors
     section; the `neurotransmitter` (and any new label) still needs an `FR` entry.
   - To add or edit a **drug**, edit `tools/drugs_data.json` (a JSON list, **not**
     inline in `generate_data.py`). Each entry: `id` (unique, kebab/lowercase),
     `name`, `categories` (one or more keys of `DRUG_CATEGORY_LABELS`), optional
     `nbn` + `description` (authored inline as `{en,fr}` objects, so they bypass the
     shared `FR` table), `wikipedia` url, and `bindings`. Each binding is
     `{"target": ..., "action": ...}` where `target` is a key of the **merged**
     target map (a `DRUG_TARGETS` key like `sert`/`mao_a`/`nav`, **or** a receptor
     id like `5ht2a`/`d2`/`h1`) and `action` is a key of `DRUG_ACTIONS`
     (`agonist` / `partial_agonist` / `antagonist` / `inverse_agonist` /
     `reuptake_inhibitor` / `releaser` / `enzyme_inhibitor` / `pam` / `nam` /
     `blocker` / `modulator`); optional per-binding `effect` (overrides the action's
     net effect), `note` (`{en,fr}` or `"TODO"`) and `tentative: true`. A drug with
     `"bindings": []` is emitted `focusable: false` (listed, not clickable).
     `_drug_record` validates every category / target / action / effect against the
     vocabularies and rejects duplicate ids; a new coarse target / category / action
     needs an entry in `DRUG_TARGETS` / `DRUG_CATEGORY_LABELS` / `DRUG_ACTIONS` (with
     `{en,fr}` labels) or the build raises. A new `DRUG_TARGETS` entry must declare a
     `type` (a `TARGET_TYPE_LABELS` key: transporter / enzyme / ion_channel /
     vesicle_protein / receptor_group; it drives the merged Receptors & targets
     legend's swatch + tag) and may carry an optional `wikipedia` url (left absent
     -> a TODO pill); the build raises on an unknown type or a non-http(s) wikipedia.
     Keep extraction **strictly dump-sourced**
     (only what the source text states; leave gaps as TODO / no binding). It shows up
     in the legend's Drugs section automatically.
   - **Translations.** Every display string (a region `name`, a projection
     `label`/`description`/`neurotransmitter`, a circuit `name`, a group/kind
     label) is wrapped with `_t()` at build time, which looks the English text up
     in the `FR` table (English -> French) near the top of the file. Add the
     French there for any new/edited string: the generator **raises listing every
     untranslated string** if you forget, so it can't ship half-translated. For a
     paired structure whose French name is feminine or plural, set `fr_gender`
     (`"f"`/`"mp"`/`"fp"`; default `"m"`) so the composed "droit/droite/..." side
     suffix agrees. See "Internationalization".
2. Run `python tools/generate_data.py` to regenerate `public/data/`
   (`meta.json` + `structures.jsonl` + `projections.jsonl` + `circuits.jsonl` +
   `receptors.jsonl` + `drugs.jsonl` + `shapes/`).
3. Optionally run `python tools/check_data.py` to sanity-check the regenerated
   files (duplicate ids/names, unreachable references, stray TODOs); see "Data
   checks". The pre-push hook also offers to run it.
4. Commit the generator change and the regenerated artifacts together.

The legend (region colors and the projection rows, per-neurotransmitter or
per-sign depending on the colour-mode toggle) is generated at runtime from the
data, so it updates automatically; no separate legend edit is needed.

## Versioning

Lightweight, no-build versioning suited to this static site:

- The version is a single string in `version.js` (`window.__APP_VERSION__`), the
  one place to change it. `js/main.js` shows it in the panel header (`v0.1.0`)
  and `js/dev-banner.js` appends it to the WIP banner; both just read the global,
  so there is no duplication.
- Follow [semver](https://semver.org/) (MAJOR.MINOR.PATCH). To release, bump
  `version.js`.
- It is intentionally *not* derived from git (the site is deployed as plain
  files, not from a repo checkout, so a baked-in string is what actually reaches
  the browser).

## Conventions

- No JS build step or package manager: three.js is vendored same-origin under
  `public/vendor/three` and loaded via an import map in `index.html`. Keep the
  `three` and `three/addons/` entries in that import map pointing at the vendored
  files, and bump the vendored copy as a unit.
- `generate_data.py` is intentionally stdlib-only so it runs offline with a bare
  `python` interpreter.
- Avoid duplicating the anatomy *and its presentation maps*:
  positions/colors/shape params, the projection `kind`->colour map and the
  `group`->legend-heading map all live only in `generate_data.py`; the latter two
  are emitted into the data's `meta.json` and read by the viewer, so there is
  no second copy in JS.
