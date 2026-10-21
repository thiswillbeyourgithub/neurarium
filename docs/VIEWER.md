# Viewer internals

The viewer's theme, rendering, circuit animation, circuit/group panels, receptors & targets, addon nodes, images and changelog mechanics, in full. Split out of `CLAUDE.md` (which keeps a terse summary of each section) to keep that file small; this project is built with the help of Claude Code. Section names referenced below (Nodes, Source provenance, Drugs, Controls, ...) are sections of `CLAUDE.md` unless they are one of the sections below; drug detail lives in [`DRUGS.md`](DRUGS.md), provenance detail in [`PROVENANCE.md`](PROVENANCE.md).

## Theme (day / night)

Two palettes, one token block. `css/tokens.css`'s `:root` defines the dark palette; a `:root[data-theme="light"]` block redefines **only tokens**, never a rule, so a component written later is themed on the day it lands as long as it reads them. The one that makes this cheap is **`--ink`**, an RGB triplet rather than a colour: every white-on-dark hairline, hover fill and divider is `rgba(var(--ink), a)`, so flipping the chrome is one token instead of dozens of edits. Alongside it `--page-bg`, `--text-strong`, `--label-ink` / `--label-halo` (the floating region labels sit over the scene, not the panel, so they carry their own ink) and `--mol-filter` (the molecule line art is inverted on dark, left alone on light). The same split covers the **semantic** ink: `--sem-missing` / `--sem-llm` / `--sem-sourced` / `--sem-verified` / `--sem-uncertain` / `--sem-amber` / `--sem-caution` (the graded pills and flag tags), `--tip-bg` / `--tip-shadow` (the tooltip bubble, opaque and a step darker than the panel it covers) and, for a boxed callout, `--addon-ink` (split from `--addon-accent` because the accent paints the callout's own ground, so it cannot also be its text). A `#fff` sitting **on** `var(--accent)` stays literal: it is white in both themes, and `tools/tests/test_theme_tokens.py` fails on any other literal text colour, plus on a token one theme declares and the other does not.

`js/theme.js` (`createTheme`) owns only the decision, and it is short: the visitor's stored click, else **dark**. It does not read `prefers-color-scheme`, which is the non-obvious part: the feature dropped `no-preference`, so a light query answers `light` both for a visitor who asked and for one who never touched the setting, and following it would hand the un-art-directed palette to everyone who expressed nothing. So light is opt-in, one click on the `#toggle-theme` sun/moon button in the panel header (persisted `neurarium.theme`), and it sticks.

The WebGL canvas is not CSS and cannot read tokens, so `apply()` hands the resolved `--page-bg` to `js/scene/setup.js`, which repaints `scene.background` and calls `repaint` (the module-scoped hook the render loop fills in with `invalidate`, since the two ends live in different functions).


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
layout. The other half was **allocation**: every re-fit built a fresh `THREE.TubeGeometry` per arrow
(~95 typed-array allocations + as many GPU buffer create/deletes per frame), so `writeTube`
(`js/arrows.js`) rewrites the shaft/halo/pick buffers **in place** instead, the topology written once.
Never reintroduce a per-frame `new TubeGeometry` here. It is exact, not an approximation: the arcs are
quadratic Beziers, hence planar, so the plane normal is the parallel-transported binormal and the
tangent is analytic (no Frenet walk, no `getPointAt` arc-length table). Only a `tentative` arrow's
dotted shaft still rebuilds (5 arrows, merged from dash segments).

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

Lifecycle (`js/legend/anatomy.js`, `js/boot/focus.js`): the row calls `selection.setCircuit(...)` then `circuitAnim.play(...)`.
Stopping rides the selection state: an `onIsolate` watcher `stop()`s whenever the pinned-arrow set is
no longer exactly the animating circuit (`circuitAnim.matches`), so a clear / different circuit /
group focus / legend isolate all stop it; a mere structure highlight keeps it. Circuit-only (a group
focus uses `setCircuit` but never `play`).

## Folded panel sections

Every `show*()` detail panel (drug, receptor, target, enzyme, structure, circuit, projection group) ends with `foldBody()` (`js/panel/info.js` -> `foldSections`): each `h3`-headed section becomes a collapsed `details.disclosure.panel-sec`, body indented; the unheaded top (title, group line, addons, image, description, receptor facts) stays visible. A freshly opened panel (a new node, or the same one picked again) starts with every section folded; the sections open in a tab are remembered per tab by the tab strip (`sectionsByKey` in `js/panel/tabs.js`, keyed by `panelSectionKey`, kept current by a `toggle` listener) and re-opened when the reader comes back to that tab, exactly like its scroll (`scrollByKey`). A jump into a section opens it first: `flashRow` opens every ancestor `<details>`, and a tour step uses `tourOpenSec(ensure, sec)`. The projection panel has no headed section, so it is not folded.

A section is shown even when the node has nothing for it, so a reader of one panel learns the dataset tracks it for other nodes: `emptySection` (`js/panel/dom.js`) renders its heading + subtitle and one muted line, i18n `info.noData` ("No information about <section> for this <kind> yet.", kind noun `info.kindThis.<kind>`). It is never folded (a `div.panel-sec-head`, not an `h3`, so no caret opens onto nothing), and an empty subsection inside an empty section is not repeated. Flags (prodrug and combo notes, contradiction notes, addon slots) stay hidden when absent. The `/api/` pages mirror it through `api_sections.ALWAYS` (same heading, subtitle and sentence, each with its own section page), guarded by `test_panel_md_parity.EmptySectionsTest`.

## Circuit + projection-group panels

A Circuits row and a Projections (per-pathway) row each open a **sourced detail tab**, like a
structure/drug row. Member pathways are never stored: a circuit's are the projections with both
endpoints in its set, a group's are those whose `kind`/`sign` matches `key`. `js/data/anatomy.js` localizes
both and indexes groups by `${mode}:${key}` (`projectionGroupsByKey`).

- `showCircuit`: a "Functional circuit" heading with the loop's source pill (`circuit.provenance`),
  the Wikipedia illustration (`appendWikiImages`), the description + reference (`appendReference`,
  live-refreshed with a baked fallback), its structures (deduped to bases, clickable via
  `onStructure`), and its member pathways.
- `showProjectionGroup`: a by-transmitter / by-effect heading with the group's source pill
  (`group.provenance`), the description (live-refreshed, its own pill), the reference, the member
  pathways, then (kind-mode only) a **Drugs acting on this system** list = focusable drugs whose
  `flowKinds` include this kind (mirror of the drug panel's Pharmacodynamics: net neurotransmission; jumps via `onDrug`), each with its signed tone (`netTone`) and ranked by it, highest raise first.
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
knowledge nodes (each target's own node + its "Regional distribution" regions + the bindings on it via
`data.drugsByTarget`), so a heavily-drugged system leads; "Other" is pinned last. **Members** order
lexicographically (`localeCompare` `numeric`, so 5-HT2 precedes 5-HT10). Both sources are normalized
in `js/data/targets.js`.

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
  GPCR/sign/site reads honestly as `llm` instead of borrowing a neighbour's quote), then the "Regional distribution" list via
  `locationList` grouped under `groupLabels` sub-headings, each region carrying its **own**
  expression-provenance pill + an amber "· <species>" tag when it has no human assay (`locationEntry`
  prefers Human, so an Allen confirmation clears it), or one pilled "Throughout the brain" for
  ubiquitous). A non-receptor target opens the lighter `showTarget` (type + system facts with their
  grade pills, a **Effect of blockade on tone** row for a target carrying a direction-flipping `vesicular`/`sign`/
  `synaptic` flag (its *own* graded node `target_polarity`, not the classification grade, since the flag
  flips the drug-flow overlay's sign; `TARGET_POLARITY_QUOTES` upgrades it, else `llm`), then the same
  per-region "Regional distribution" list, kind `target_locations`). Both add **PDSP
  Ki** + **ClinPGx** lookup links (`appendLookupLink`); a receptor also gets **UniProt** (human-only) +
  **GtoPdb** search links (`uniprotSearchUrl`/`clinpgxSearchUrl`/`gtopdbSearchUrl`, no pill). The
  gene databases (UniProt, ClinPGx) search the node's `gene`, its HGNC symbol (α1A -> `ADRA1A`; an
  identifier, not a graded node, mapped in `data_generators/genes.py`), GtoPdb the display name. Both carry an **Interacting
  drugs** section (from `drugsByTarget`, grouped by category, each row an `effectGlyph` + the
  binding's `bindingProvenancePill` = the *same* resolved binding the drug panel shows; jumps via
  `info.onDrug`). A **receptor_group** target (α2/glutamate) additionally lists, under its own
  Ligands (drugs), one collapsed **By receptor subtype** dropdown per modeled subtype that has drugs
  (`appendSubtypeInteractors` off `target.subtypes`, a sourceless taxonomy in `meta.drug_targets`), so
  a subtype binder (asenapine at α2A) is reachable from the coarse panel. Both make each "Regional distribution"
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

The "Regional distribution" list answers *where*, not *how much*; a `density` profile ranks those regions
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
- Viewer: `js/data/expression.js` `densityEntry` normalizes it to `{profile, rel, reliability, donors,
  provenance, sources}` (`rel` = the z rescaled to 0.08..1 for the bar); `locationList` prepends a
  caption row ("Expression density" + the donor-agreement r + the profile's grade pill) and
  `locationRow` appends a bar + signed z per region. **Caveat shipped in the caption tooltip:**
  mRNA, not protein, and transcript sits in cell bodies, not terminals (SERT peaks at raphe).

### Effects (BETA)

- Each `receptor_effect` node is one row of a receptor / target panel's **Functional effects** section (`appendEffects` in `js/panel/sections.js`, folded, after "Regional distribution", with the `.beta-tag`): `<effect> · <mode>` + the node's own grade pill.
- A drug panel adds a derived **Predicted effects (target-based)** section (`appendPossibleEffects`, the first of the BETA sections closing the panel after Metabolism and Pharmacogenomics, from `data.possibleEffectsByDrug`): the build-time effect index (`tools/data_generators/effect_index.py`, see the Effects bullet below) joins the drug's bindings with its targets' effect nodes, **direction-aware** (a binding inherits a node only when its `action` is in that mode's `actions`, emitted in `meta.receptor_effect_modes`, so an antagonist never inherits agonism effects) and an `affinity_only` binding (no action) contributes nothing. Worded "could cause", never "causes", stated once in a lead line over the list: it is a statement about the receptors, not about the drug. A `.seg-switch` (the Interactions one's style) groups it **by effect** (default; receptors under each) or **by receptor** (effects under each), both ordered by the drug's Ki (`bindingKi`, unmeasured last, then by name; `js/effect-grouping.js` `groupPossibleEffects`), each binding showing its compact Ki; the choice persists via `js/prefs.js` (`neurarium.effectGroup`). Each chip jumps to the target; nothing lights the 3D scene.
- The **Effects** browse section (`#effects`, `buildEffectLegend`, after Enzymes) turns the same nodes around: one row per effect some target carries (`data.effects`, read by `readEffectIndex` from `derived/effects.json`, which `tools/render_api.py --effects-out` writes from `tools/data_generators/effect_index.py` at image build time and `tools/serve.py` per request; never committed. One join, so the effect panel, every drug panel, llms.txt and `/api/` cannot disagree; a failed fetch raises a red banner and leaves both empty), tagged with its drug count. A row, a search hit (its label in both languages via `search_names.fr.json`) or any effect name in a receptor / drug panel opens `showEffect`: the receptors / targets carrying it grouped by mode with their pills, then "Drugs that could cause it", each naming the bindings that lead there. A panel-only focus like an enzyme's (`focusEffect`, no 3D state), deep-linked as `#tabs=effect:<id>`. The same module feeds llms.txt's "Clinical effects" section and the `/api/effect/<id>` pages.

### Age and sex differences (BETA)

- Each `receptor_demographic` node is one row of a receptor / target panel's **Age and sex differences** section (`appendDemographics`, folded, last of the beta sections): a direction chip (`meta.demographics.glyphs`, "↓ Age", "♀ > Sex"), the conditional sentence ("reported to decline with age in Caudate nucleus", i18n `demog.<factor>.<direction>`) + grade pill, then the paper's own magnitude wording in quotes when it states one. The caption says these are human group averages, not a prediction for one person, and not medical advice. Nothing lights the 3D scene.

### Release modulation (BETA)

- Each `receptor_release_modulation` node is one row of a receptor panel's **Release modulation** section (`appendDownstream`, folded, after Functional effects): "activating it decreases histamine release" + grade pill, then the site ("Autoreceptor on presynaptic terminals in VTA").
- A drug panel adds a derived **Presynaptic modulation** section (`appendReleaseChanges`, after the possible effects): `deriveReleaseChanges` keeps a node's direction for an agonist, flips it for an antagonist, skips `affinity_only`, groups by (transmitter, direction, structure) with one chip per receptor. Worded "could increase", never stored; no 3D overlay (a site is a cell type, not a pathway the scene draws). It stays a browser-side derivation (`js/release-modulation.js`), unlike possible effects, which come from the build-time effect index: that index exists because one join feeds four readers (effect panel, drug panel, llms.txt, `/api/`), while release changes have one reader (the drug panel) and no reverse "which drugs change X release" view, so there is nothing for a shared join to keep consistent. Moving it would mean a second Python join in `tools/data_generators/` plus its `/api/` and llms.txt pages; do that only when a second reader appears.

## Addon nodes (panel annotations)

Every other node kind has an implied home: a binding belongs in **Pharmacodynamics: binding profile**, an enzyme row in
**Metabolism**, so the collection decides where it draws. An **addon** is the kind for a claim
with no such home (a caveat over a whole section, a flag on one drug), and it earns its keep by
**carrying its own insertion point**: adding one is a data edit, never a viewer edit. It is a
node like any other otherwise: quote-level `sources`, a grade, a pill, a row in the Data browser,
a line in the tally.

- **Data.** `tools/data_generators/addons.py`: the authored `ADDONS` list plus four **closed**
  vocabularies emitted into meta so the hook registry is data, not JS: `ADDON_SLOTS`
  (`meta.addon_slots`, slot -> the node kind whose panel it is in), `ADDON_SECTIONS`, `ADDON_DISPLAYS`,
  `ADDON_TONES` (tone -> glyph; the colour ramp each tone paints with is chrome and lives in `index.html`),
  `ADDON_BASES` (`meta.addon_bases`): `claim` (default, knowledge, sourced + tallied) or `dataset` (a
  statement about this dataset itself, see the two section anchors below).
- **A slot exists only if the viewer calls it.** Each `ADDON_SLOTS` key has exactly one
  `appendAddons(host, ownerKind, ownerId, slot)` call in the viewer (`js/panel/views/*.js`, `js/legend/anatomy.js`); a slot with no call site
  would swallow its node silently (well-formed, graded, counted, never drawn), which is why the
  generator AND `check_data.py` both reject an unknown slot / display / tone or an anchor naming
  no real node, and why `test_generate.AddonTest` looks each slot's literal up across `public/js/**/*.js`.
  Today: `drug.top`, `drug.metabolism`, `drug.timing` (under the Tmax / half-life chips, drawn
  whenever the drug has either duration, so it does not need enzyme rows), `receptor.top`, `target.top`,
  `structure.top` (a structure addon anchors the hemisphere-less **base**, so it shows on both),
  `section.projections`, `section.metabolism`.
- **A section anchor is the owner kind that is not a node** (`ADDON_SECTIONS`, `meta.addon_sections`,
  section key -> label): for a claim true of a whole view at once (a browse section, or a panel
  section every drug repeats), so there is no single datum to hang it on and no panel to open from it
  (`focus` is null, the caveat already sits where it applies). Its id pool is that vocabulary. One of
  its slots is filled from `buildLegend` rather than from a `show*()` view, which is why
  `createInfoPanel` exports `appendAddons` instead of the box being redrawn there.
- **Viewer.** `js/data/addons.js` resolves each addon's owner once (`ownerName` + a `focus` `{nav, arg}`
  recipe the Data browser and the Sources popup both hand to their own nav table) and indexes them
  as `addonsBySlot` keyed `${ownerKind}:${owner}:${slot}`. `js/panel/addons.js` `ADDON_RENDERERS` dispatches
  on `display`; a second form is one entry there plus one string in `ADDON_DISPLAYS`. Every form shares the `addonBox` shell (tone class, label, pill); `collapsible` is a `<details>` closed by default whose summary carries the label + pill (a pill click opens the Sources popup, never toggles), used for a caveat a reader needs once, not on every panel (`enzyme_list_not_exhaustive`).
- Five today. One `drug.timing`: lithium's brain half-life (7Li MRS, 28 h) outlasting its serum one
  (16 h), from corpus #17. Two `drug.metabolism`: paroxetine + MDMA inhibit the CYP2D6 that clears them
  (mechanism-based / autoinhibition), so their kinetics are non-linear, which the per-isoform rows
  below cannot state (a row gives a role, never a curve). Two section anchors, both `basis: "dataset"`:
  unsourceable by construction because each states what no corpus backs rather than what one does, so
  they draw a neutral dashed **◌** pill ("about this dataset", `.src-prov-dataset`) instead of the red
  ✕, and stay out of the tally and the Data browser (see `docs/PROVENANCE.md`): `section.projections`, bilaterality (nearly every pathway is authored once and mirrored) as a
  modelling assumption, one node over the whole collection rather than an uncertainty flag on ~90
  arrows; and `section.metabolism`, under every drug's enzyme rows, saying the list holds the routes
  some source happens to name and never claims to be complete, so a missing isoform is a hole in the
  sources and not a claim that the drug avoids it. That one also names where the hole propagates: the
  drug -> drug rows are derived from the same list, so an unnamed shared route is an interaction
  nothing draws (clomipramine gained 11 when its CYP2C19 row landed, 3.93.1).
- **The `drug.metabolism` slot has a derived fallback.** A drug that is both a substrate and a
  modulator of one isoform changes its own clearance, and that is computable: `js/data/pk.js`
  `autoModulation` (an inference over the enzyme rows, like `pkInteractionsOf`) feeds
  `derivedAutoModulation` in `js/panel/addons.js`, which draws the same box worded conditionally, with no
  source pill and a line saying it is our reading of the two rows. It fires **only when the slot
  holds no authored addon** (`appendAddons` returns how many it drew): a sourced statement of the
  mechanism outranks the inference. So the rule covers the ~25 other self-modulating drugs for
  free, and an authored addon stays the way to state what the rule cannot see (MDMA's
  autoinhibition is not in its enzyme rows: the corpus gives it a substrate role only).
  Either form (authored or derived) also puts a yellow **⚠** beside the drug's T½ chip far above,
  whose tooltip says the kinetics are non-linear and whose click scrolls down to the section: a T½
  only means something while clearance is linear, and the caveat is written where the enzyme rows
  make it legible, so the chip points at it rather than repeating it.

## Images

Two third-party image sources, handled differently on purpose.

- **Molecule images** (vendored same-origin; CSP `img-src 'self' data:`). `tools/fetch/fetch_molecules.py`
  downloads each drug's lead infobox SVG via the MediaWiki `pageimages` API into
  `public/data/molecules/<id>.svg` (`.svg` only, `<script>` stripped); writes
  `tools/generated_cache/molecules_sources.json`. `generate_data.py` emits `structure_image` only when the file
  exists. `showDrug` renders it as `<img class="mol-structure">` filtered by the theme's `--mol-filter`
  (`invert(1)` on dark, `none` on light; see Theme). No image if absent.
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

## Versioning: changelog mechanics

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
`showIfUnseen()` fires at **launch** (the "Start exploring" click), not once the assemble
intro settles: the notes are about the build, not the scene. The tour therefore gates on
that popup the way it gates on the Sources one, so the two never stack. It shows every
release after the version in `localStorage`
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
