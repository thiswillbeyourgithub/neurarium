# Controls

> Reference detail moved out of [`CLAUDE.md`](../CLAUDE.md) to keep that file a terse map. This is the full text for the viewer's controls, panels, input, and selection model.


One collapsible **"neurarium" panel bottom-left** (`#controls`; `#controls-toggle` collapses the
body). The body splits into `#settings-pane` and `#details-pane` (`#info-body`), switched by the
`#panel-tabs` bar: a pinned **Settings** tab (`#tab-settings`) + one closable tab per opened
detail in `#detail-tabs` (see Detail tabs + Info panel). The settings pane holds, pinned at top,
the `#lang-switch` (EN/FR) + a keyboard-shortcuts / reset / search / legend / sources / about
`.toolbar-row`, then:

- **Controls** (`#controls-settings`): the **Separate** + **Transparency** sliders, the
  **animation-speed** slider (`#anim-speed-row`, hidden unless an animation is on screen), the
  **Auto-rotate** / **Show all names** / **Show projections** / **See inside** checkboxes, and the
  **arrow colour-mode** switch (`#color-mode`). Ships open; toggles independently of the accordion.
- Five **single-open-accordion** sections (opening one closes the others), in on-screen order
  **Drugs** (`#drugs`, with `#drugs-filter`), **Receptors & targets** (`#receptors`), **Metabolising
  enzymes** (`#enzymes`), **Brain structures**
  (`#structures`, headed by the `panel.structures` string), **Projections** (`#projections`, "Projections & Circuits"). Markup order in
  `index.html` sets the order (see the browse-section comment there).
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
- **Show projections** (`#toggle-projections`, **off**): checking it draws every arrow at once
  (`projVis`; composes with the Hypothetical toggle). Off is not "no arrows": the set the current
  focus lights is exempt (`projVis.setFocusArrows`, fed by `selection.onIsolate`'s third argument),
  so a circuit / drug / structure focus still draws its own pathways and only those.
- **See inside** (`#see-inside`, off): `createNearCull` recomputes each frame which **outer-shell**
  structures (`group == "lobe"` + the cerebellum, `isShellMesh`) sit on the camera-facing side
  (centre > `NEAR_CULL_BIAS` past the orbit-centre plane) and hides them, peeling the near cortex off
  the deep nuclei; the nuclei themselves are never culled, or the mode would hide what it is for.
  Snapshots visibility to restore; composes with `?only=`; arrows stay. `cull.tick()` runs after
  `controls.update()`.
- **Animations** (`#toggle-animations`, `animSettings.enabled`): the decorative motion (intro,
  gem-dot twinkle, drug wash, circuit pulse). Default on for a fine pointer, off for coarse /
  reduced-motion; persisted. Off is *content-preserving*: focus still lights regions/arrows + shows
  a static gem field, just frozen (intro skipped, `tick()`s to a still frame, `play` no-ops).
- **Animation speed** (`#anim-speed`, `animSettings.speed`, persisted): a multiplier every animated
  module applies live to its per-frame time delta (no phase jump). The linear 0..1 input maps
  geometrically to 0.25x..4x with the midpoint = 1x (the reference pace). Its row (`#anim-speed-row`)
  is revealed only while an animation is actually on screen (a focused drug / receptor / circuit),
  recomputed each rendered frame in the render loop from the controllers' `active` getters.
- **Panel-only mode** (`#toggle-3d`, an icon button pinned in the panel header, not in Settings so
  it stays reachable once the panel fills the screen; persisted `neurarium.no3d`, and mirrored into
  the URL as the `panel` view key, see `docs/RUNNING.md`): `body.no-3d` hides
  `#scene` + `#labels-layer` and lets the expanded panel fill the viewport; the render loop
  early-returns, so animations freeze in place and resume when 3D returns. Turning it on expands a
  collapsed panel first (`expandPanel`, the shared wrapper over `openControlsBody`), since with no
  brain behind it a folded panel would leave a blank viewport. A view that merely wants the room
  (the Data browser) passes `{persist: false}` so it borrows the mode without rewriting the
  visitor's stored preference.
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
  place explaining the sourcing system (see Source provenance); NOT auto-shown on startup, opens
  only on demand (this button, the Legend/About links, the tour's Sources step).
  `buildAboutSourcing(null)` renders the static intro + key immediately, a second call fills the
  tally once loaded.
- **Receptors & targets** (`#receptors`) / **Drugs** (`#drugs`) / **Metabolising enzymes**
  (`#enzymes`, `buildEnzymeLegend` -> `showEnzyme`): see their sections.
- **About** (`#about-modal`, ⓘ, `wireAboutModal`): a blurb (Olivier Cornelis + Claude), a "Start the
  tutorial" button (`#about-tour`, above the caveat: the offer comes before one feature's limitation),
  the animation caveat + a collapsed **What the animations mean** dropdown (`about.animCaveat` /
  `animSummary` / `animIntro` / `animList`: one `<li>` per visual aspect, each opening with a bold
  "&lt;aspect&gt;: &lt;explainer&gt;", ordered dots -> beads -> glow so each builds on the last; the
  caveat stays *outside* the dropdown so a limitation is never behind a click), a data dropdown, an
  "open an issue on GitHub" link (`cfg.sourceUrl + "/issues"`, dropped unless `sourceUrl` is repo-like), a Source
  code link, a licence line (AGPL-3.0), a CC BY-SA attribution line, and a Sources & provenance
  link (`#about-open-sourcing`). The tally is not here (own popup).

### Data browser

**`#nodes`** (`js/node-browser.js`): the Sources & provenance popup's coverage bars read node by
node. Unlike the browse sections above it does **not** expand in place: the `#nodes-toggle` row
opens a **detail tab** (key `browser:1`, deep-linked `#tabs=browser:1`) whose body is a detached
container the module owns, so its filter, selects and scroll survive a tab switch; the panel only
hosts it (`info.showNodeBrowser`). Clicking that row also enters the panel-only mode for this visit
(the rows are a wide table reading nothing off the scene); a deep link does not, so it can still
name the `panel` view itself. Header + rows share one two-level grid template (`grade`, then
`name`/`notion`/`kind` inside the clickable button), which is why the header is built with a row's
exact structure and an empty `notion` cell is still emitted. The **kind** column shows only in the
"All kinds" reading: with one kind selected every row would repeat the select above the list, so
`apply()` puts `.no-kind` on the grid and the CSS drops the column and reflows the other two. The
kind then heads the **notion** column instead of the word "notion", naming what the cells under it
actually hold; and when no matching row carries a notion at all (a circuit, a projection group: the
name *is* the claim) that column goes too, `.no-notion`, and the kind heads the **name** column
instead.

`collectNodes(data, deps)` enumerates every graded knowledge node (references excluded, like the
bars) as `{kind, name, notion, grade, uncertain, go, sources, uncertainty, ki}`, where `grade` is
the *display* grade a pill shows (`uncertain` overrides a quote-checked node carrying uncertainty
bullets), `go` navigates to the owning panel, and the last three are the node's **backing**. Its
per-kind counts match `meta.provenance_stats.by_kind` (drift is a bug). It runs **lazily**, on the
first open, since walking the whole dataset should not cost a visitor who never opens it.

`createNodeBrowser` renders an intro line naming what a node is (plus a **"The same data as
files"** button opening the About popup's data-file dropdown, `#about-data-files`, rather than
copying its links), a filter box (`#nodes-filter`, folded through the same `foldText` the search
uses), kind / grade / sort selects, a **Show both hemispheres** checkbox (`#nodes-show-twins`,
persisted `neurarium.nodeTwins`, **default off**: each region reads once without its side, 32 rows
against the 57 the tally counts; shown only while the current result holds some `structures` row,
the only kind it changes), a "{shown} of {total}" line, a **column header naming the row keys**
(`grade` / `name` / `notion` / `kind`, each with a localized tooltip, so the node structure is
visible rather than implied) and the rows in chunks (150, then +300 per "show more"). **Default
sort is weakest-grade first**: the browser doubles as a sourcing workbench, so the unsourced claims
surface on top. A row's pill is `info.provenancePill(grade, row)` and its kind tag `KIND_LABELS`
(both shared with the popup, so the two views cannot drift); passing the row itself means a
browser pill opens on the node's verbatim quote / measured Ki / reasons to doubt, the very tooltip
that node's pill shows inside a detail panel (one `sourceBackedPill` builds both). Rows navigate
via the same callbacks as the popup's example nodes, plus a `connection` one that isolates the
arrow carrying a projection. A node whose owner has nothing to focus renders inert.

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
> is organized into nodes, and the eight `show*()` views (connection / structure /
> receptor / target / drug / enzyme / circuit / projection-group) share the same building
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

Every view starts from `clearBody()` (never a bare `body.innerHTML = ""`): it also resets
`#details-pane`'s scroll, so a click deep in a long panel does not open the next one already
scrolled into its middle. The exception is a jump that has a *reason*: `flashRow(el)` scrolls that
one row into view and flashes it (`.node-flash`), so arriving in another node's panel lands on the
row that explains the jump (a metabolite reached from a receptor, an isoform reached from another
drug's Drug-interactions list, via `showDrug`'s `highlightMetabolite` / `highlightEnzymes` opts). It
defers a frame because the caller shows the pane *after* rendering.

Views:
- **connection**: label, a `Projection` type line, route (`from → to`, `↔` bidirectional; each
  endpoint clickable via `endpointEl` -> `onStructurePick`), kind + neurotransmitter, description.
  Each of those rows carries the pathway's own `proj.provenance` badge (no bottom Sources block).
  Arrow picking (`pickArrowAt`) beats the region behind.
- **structure** (`showStructure`): name, a group heading with the anatomy grade pill
  (`classification_provenance`), a Reference row (Wikipedia link or `NOSOURCE`), the live Wikipedia
  lead as a description whose source marker is the Wikipedia link itself, relocated inline in place of a
  grade pill (the reference row is then dropped; it stays only for a failed fetch or lookups), then the
  pathway list. Each connection
  row: a bold `directionArrow` (inline SVG, pathway colour, out/in/both; wrapped in `withTip` so a
  tap explains direction without bubbling to the row click), the other endpoint, and the pathway's
  summary pill (`proj.provenance`, resolved in `js/data.js`), orange ⚠ when the pathway is a blanket
  claim. Left/right twin pathways collapse to
  one row (by direction + other-endpoint `base_name` + label). Then **Receptors found here**
  (`appendExpressedTargets`), the reverse of a receptor's "Found in": every target expressed in this
  region, off `data.targetsByStructure`, grouped by neurotransmitter system in the
  `groupTargetsBySystem` order (biggest system in THIS region first, capped 8 per group with the rest
  expandable in place). Each row carries that region's OWN expression node (grade pill + amber species
  tag), the same claim the receptor panel shows from the other end, and jumps to the target.
- **receptor / target / drug / enzyme / circuit / projection-group**: see their sections.

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
