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

**A *node* is any sourceable datum** (one atom of brain knowledge); a detail panel views one node plus every node linked to it. New data is a node, and **every node must be sourceable** so the coverage tally stays honest. Concept, full kind map with rationale, and tally: [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) ("The node model"); grades + source shape: Source provenance.

> [!IMPORTANT]
> "Node" is the umbrella term; structure, projection, receptor, drug, binding, target, ... are **node kinds** and keep their names in data files + code (`structures.jsonl`, `showReceptor`). Never rename collections to "node".

**Kinds** (node -> where it lives -> tally kind in `meta.provenance_stats.by_kind`):
- region `structures.jsonl` -> `structures`; circuit `circuits.jsonl` -> `circuits`; projection group `projection_groups.jsonl` -> `projection_groups`
- projection `projections.jsonl` -> `projections` (route only) + `claims.transmitter` -> `projection_transmitter` + `claims.sign` -> `projection_sign` (glutamate/GABA only: "modulatory" is the ABSENCE of a sign claim, not a third value)
- receptor `receptors.jsonl` classification, four graded sub-claims: `family` -> `receptors`, `receptor_class`, `sign` -> `receptor_sign`, `synaptic` -> `receptor_synaptic`
- receptor/target `effects[]` -> `receptor_effect` (BETA; one node per (mode, effect) from closed vocabularies, in the headline; a drug's possible effects and the effect -> receptors -> drugs index (the BETA Effects section / `showEffect`, `/api/effect/<id>`) are derived only by `data_generators/effect_index.py` (the viewer fetches its build-time `/derived/effects.json`, written by `render_api.py --effects-out` in the Docker `api` stage and by `tools/serve.py`), never stored; an owner with no node may carry an owner-level UNKNOWN `effects_unknown`, never indexed as an effect)
- receptor `release_modulation[]` -> `receptor_release_modulation` (BETA; one node per (kind, site, transmitter, direction): auto/heteroreceptor control of release; a drug's release changes are derived in `js/release-modulation.js`, never stored)
- receptor/target `demographics[]` -> `receptor_demographic` (BETA; one node per (factor age|sex, direction, structure) from human PET/SPECT Europe PMC abstracts, optional verbatim `magnitude`; panel section "Age and sex differences")
- receptor/target `variants[]` -> `receptor_variant` (one node per ClinPGx clinical annotation on the owner's gene, levels 1A-3 only, via `genes.GENE_OWNERS`; panel section "Pharmacogenomics", a drug panel lists those naming it under its own Pharmacogenomics section, `js/receptor-variants.js`)
- target `meta.drug_targets` -> `targets`; `polarity_provenance` -> `target_polarity`
- expression: `location_sources` -> `receptor_locations` / `target_locations`; `density` -> `receptor_density` / `target_density` (ONE node per profile, not per region)
- drug `bindings[]` -> `drug_bindings`; binding `action` -> `drug_binding_action` (graded by quote sources only: a Ki attests binding, never direction; `affinity_only` = NOSOURCE)
- drug `formulations[]` -> `drug_formulations` (ONE node per release type, `release` from the closed `RELEASES` vocab, graded by `release_sources`; its `brands` / `tmax` / `half_life` tally under the molecule's kinds; a claim no source ties to one product stays on the molecule)
- drug `prodrug` -> `drug_prodrug` (inactive until metabolised: no own bindings, the viewer borrows its metabolite's tagged `viaMetabolite`); a salt's `constituents` -> `drug_constituents` (borrows its modeled constituents' bindings the same way)
- drug `nbn` -> `drug_nbn`; `brands[]` -> `drug_brands`; `categories` -> `drug_categories`; `half_life` / `tmax` -> `drug_half_life` / `drug_tmax`; `first_approval` -> `drug_first_approval`; `withdrawals[]` -> `drug_withdrawals` (one node per withdrawal; none when never withdrawn); `holders[]` -> `drug_holders` (one node per (drug, market), the CURRENT holder, code-read); `originator` -> `drug_originator` (`now` rides the same node); `originator_country` -> `drug_originator_country` (from the company's own article)
- physchem (code-read, no judge): `xlogp` -> `drug_lipophilicity` + `tpsa` -> `drug_polar_surface` (PubChem #21, computed estimates); `bbb` (`{label, logbb?, logbb_max?}`) -> `drug_bbb` (B3DB #22, curated measurement; conflicting rows publish nothing). ONE node per drug each; combos, salts and inorganics get none
- drug `workup[]` -> `drug_workup` (BETA; one node per (test, timing `before`|`during`) from closed vocabularies `workup.TESTS` / `TIMINGS`, read off the French RCP 4.2-4.4 (#24); a subgroup-only ask is a conditional row, `conditions` = verbatim French span of its quote, shown "only if"; panel section "Monitoring (French SmPC)")
- TDM (AGNP #19): `therapeutic_range` (+ `tdm_level`) -> `drug_therapeutic_range`; `alert_level` -> `drug_alert_level`
- metabolism: `enzymes[]` -> `drug_enzymes` (per (enzyme, role)); `claims.strength` -> `drug_enzyme_strength`; enzyme `variability` -> `enzyme_variability` (ONE node per isoform, not per population group)
- pharmacogenomics: `pgx[].rows[]` -> `drug_pgx` (ONE node per (drug, gene, phenotype), carrying TWO citations: CPIC's implication then its recommendation)
- metabolites: ONE record per molecule in `tools/data/metabolites_data.jsonl` (-> `metabolites.jsonl`: name, `drug_id`, T½, `bindings[]` -> `drug_metabolite_bindings`, counted once however many parents); a drug's `metabolites[]` holds `{id, sources}` refs -> `drug_metabolites` + per-parent `formed_by[]` -> `drug_metabolite_enzyme`
- `addons.jsonl` -> `addons` (see Addon nodes); `wikipedia` -> `references` (tallied but excluded from the headline: a pointer at a node, not knowledge)

## Architecture

Full detail (principles, data flow, module graph, boot sequence, per-file map): [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Traps:

- `public/` is the only web-exposed dir; `docker/`, `tools/` (fetch/, sourcing/, lib/ (shared libraries, never scripts), generated_cache/; see [`tools/README.md`](tools/README.md)), `.env` are never reachable. Generated `public/data/` is committed.
- Symmetric regions + projections are authored once on the right (`mirror: true`) and reflected by the consumer (`js/data.js`, `check_data.py`), so one pathway = one node.
- Check `geometry_refinements/STATUS.md` before editing `data/shapes/*` or `shapes.js` geometry.
- `sw.js` always revalidates conditionally (not stale-while-revalidate); bump `CACHE` when caching logic changes.
- Caddy `encode` uses an explicit content-type list (a new asset type ships uncompressed until added) and pins `.webmanifest`/`.jsonl` types.
- SEO canonical / `og:url` / `og:image` / JSON-LD URLs are hardcoded (4 spots in `index.html` + `sitemap.xml`/`robots.txt` + `llms_txt.SITE_URL`).
- UI-chrome colours are `--accent*` tokens in `css/tokens.css`; data colours live in `meta.json`.
- Search matches both languages (`data/search_names.fr.json`) and search-only acronyms (`aliases` on structures via `STRUCTURE_ALIASES`, on drugs via `DRUG_ALIASES`). A control is searchable via `data-search` in `index.html`; `js/url-state.js` writes nothing at defaults; `js/prefs.js` is the only `localStorage` touch (classic `i18n.js` excepted).
- Any UI change must be checked against `js/tour.js` by running the tour end to end (headless, step by step): its steps (in `js/boot/tour-steps.js`) anchor on selectors and `data-tour-*` hooks and break silently.
- Every change (new data, new panel section, new derived readout) must also ask whether the agent surface needs it: `llms.txt` (`tools/data_generators/llms_txt.py`) and the `/api/` pages (`tools/render_api.py`) are rendered separately from the viewer, so a feature added only to `js/main.js` is invisible to an LLM reader.
- Uncommitted local files: `deploy.sh`, `CLAUDE.local.md`, `docker/.env`.

Files (`public/`, the full per-file map is in `docs/ARCHITECTURE.md`): `main.js` is the boot/orchestration entry, delegating to `js/boot/` (UI wiring), `js/scene/`, `js/panel/` (+ `views/`), `js/legend/`, `js/about/`, `js/search/`; styles in `css/*.css` (linked in cascade order, also precached by `sw.js`). Data `js/data.js` (facade over the `js/data/` loader stages), `js/util.js`, `js/grades.js`, `js/net.js`, `js/wiki.js`, `app-config.js`, `version.js`; scene `shapes.js`, `mesh-codec.js`, `baked-meshes.js`, `arrows.js`, `labels.js`, `render-order.js`; animation `circuit-schedule.js`, `circuit-anim.js`, `receptor-markers.js`, `receptor-effects.js`, `release-modulation.js`, `receptor-variants.js`, `drug-anim.js`, `surface-wash.js`, `anim-settings.js`; tabs `node-browser/` (`node-browser.js` re-exports), `simulation.js`, `sim-model.js`, `sim-plots.js`; chrome `index.html`, `tour/` (`tour.js` re-exports), `changelog.js`, `drug-history.js`, `tdm.js`, `workup.js`, `physchem.js`, `i18n.js`, `theme.js`, `loading.js`, `app-init.js` (analytics), `dev-banner.js`, `error-banner.js`, `update-check.js` (reloads a stale tab onto the deployed version); state `url-state.js`, `prefs.js`; search `search-rank.js`; PWA `sw.js`, `manifest.webmanifest`. Agents `llms.txt` (generated) + `/api/` Markdown (`tools/render_api.py`, built into the image, never committed; see `docs/ARCHITECTURE.md`). Deploy (`docker/`): `docker-compose.yml`, `Dockerfile`, `Caddyfile`, `entrypoint.sh`, `env.example`.

## Running

> Moved to [`docs/RUNNING.md`](docs/RUNNING.md) to keep this file terse: serve `public/` over HTTP (`tools/serve.py`); `tools/shot.py` screenshots + the `?params` deep-link view keys.

## Deployment

> Moved to [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) to keep this file terse: the hardened Caddy container (non-root, read-only rootfs, dropped caps); actual deploy procedure in `CLAUDE.local.md`.

## Git hooks

> Moved to [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) to keep this file terse: repo-tracked hooks under `tools/git-hooks/`, activated per-clone; `pre-push` guards `main`, always runs `tools/check_js.py` + the node JS tests + offers the data check.

## Data checks

> Moved to [`docs/DATA_CHECKS.md`](docs/DATA_CHECKS.md) to keep this file terse: `tools/check_data.py` (stdlib CLI, one module per family in `tools/checks/`) over emitted `public/data/`: fourteen families (quote table, duplicates, reachability, TODOs, provenance grades, source quotes, connectivity, Ki coverage, drug flow consistency, changelog, innervation coverage, baked meshes, enzyme variability, freshness: an editable online corpus page cited but downloaded over 12 months ago fails, also run unskippably by `pre-push`).

There is a **code** check too, since there is no build step to hold a linter: `tools/check_js.py` (stdlib) walks each `public/**/*.js` scope tree and fails on any identifier reference no enclosing scope binds. That is the crash `node --check` cannot see (the file parses; the browser raises only when that line runs), and it is what a missing destructured parameter looks like. It runs unskippably in `pre-push` and as `tools/tests/test_check_js.py`. It is a lint, not a parser: every ambiguity resolves toward silence, so it under-reports rather than crying wolf (its docstring lists which).

## Internationalization (i18n)

> Moved to [`docs/I18N.md`](docs/I18N.md) to keep this file terse: EN/FR, no build step; UI strings in `js/i18n/en.js` + `fr.js` (runtime `js/i18n.js`), data strings authored as `{en,fr}` via `_t()`/`FR` in `generate_data.py` but **emitted English-only** (a serialization-time `externalize` pass collapses each `{en,fr}` to English + deduplicates the French into `public/data/translations.fr.json`, fetched by the viewer only in French). Any new string needs both languages or the build raises.

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

> Moved to [`docs/CONTROLS.md`](docs/CONTROLS.md) to keep this file terse: the one collapsible bottom-left `#controls` panel and everything in it: the Settings pane + accordion sections, the detail-tab strip, the eight `show*()` info-panel views, selection/halo + isolate, structure-name labels, legend sections, keyboard/touch input + search, and camera focus. One data contract worth knowing here: the search box indexes the panel's **own controls** alongside the data, and a control joins that index by carrying **`data-search`** in `index.html` (named by its own visible label, optional attribute value = search aliases), so a new option is searchable with no JS edit; `tools/tests/test_search_controls.py` guards the contract.

## Theme (day / night)

Two palettes, one token block: `css/tokens.css`'s `:root` is the dark palette and `:root[data-theme="light"]` redefines **only tokens, never a rule**, so any component that reads the tokens is themed for free. `--ink` is an RGB triplet (`rgba(var(--ink), a)` for every hairline/hover/divider), so flipping the chrome is one token; semantic ink (`--sem-*`, `--tip-*`, `--addon-ink`) is split the same way. A `#fff` sitting on `var(--accent)` is the only literal text colour allowed: `tools/tests/test_theme_tokens.py` fails on any other, and on a token one theme declares and the other does not. `js/theme.js` picks the stored click, else **dark**; light is opt-in via `#toggle-theme` and `prefers-color-scheme` is deliberately **not** read (the query cannot tell "asked for light" from "never chose", so following it would hand the un-art-directed palette to everyone). The WebGL canvas cannot read tokens, so `apply()` hands `--page-bg` to `js/main.js`, which repaints `scene.background`.

Full detail: [`docs/VIEWER.md`](docs/VIEWER.md).

## Rendering

The render loop is **on-demand**: each frame runs cheap checks but renders only when a controller animated, the camera moved, or `invalidate()` fired; idle, the canvas holds its last frame.

> A new per-frame controller's `tick()` must return whether it animated, or it runs but never repaints.

- **Decoration draw order:** every additive decoration clinging to a structure (gem dots, wash shells, halos) is pinned to `DECOR_RENDER_ORDER` (`js/render-order.js`), because three.js sorts the transparent pass by bounding-sphere centre and a sparse dot cloud otherwise sorts before its region past some azimuth and vanishes.
- **Adaptive quality:** `createAdaptiveQuality` steps `animSettings.quality` (pixel ratio first, then dot/bead counts) down on slow animating frames and back up with hysteresis.
- **Spread performance:** during a continuous spread arrows update in `fast` mode (cached end offsets, deferred pick-hull rebuild) and `createArrowRetrim` re-trims precisely once the spread settles. Never reintroduce a per-frame `new TubeGeometry`: `writeTube` (`js/arrows.js`) rewrites the buffers in place.
- **Arrow width:** `createArrowWidth` keeps a constant apparent width under user zoom (explode auto-zoom divided out).

Full detail: [`docs/VIEWER.md`](docs/VIEWER.md).

## Circuit animation

Isolating a circuit plays a traveling pulse of beads along its arrows. Split in two: `js/circuit-schedule.js` (`scheduleCircuit`, BFS firing order, no three.js, testable) and `js/circuit-anim.js` (`createCircuitAnimation`, beads on `arrow.curve` + a sign-keyed wash echo on landing). It stops via an `onIsolate` watcher once the pinned-arrow set is no longer exactly the animating circuit (`circuitAnim.matches`). Full detail: [`docs/VIEWER.md`](docs/VIEWER.md).

## Circuit + projection-group panels

A Circuits row and a Projections row each open a sourced detail tab (`showCircuit` / `showProjectionGroup`, focused via `focusCircuit` / `focusProjectionGroup`). Member pathways are never stored: a circuit's are the projections with both endpoints in its set, a group's those whose `kind`/`sign` matches; groups are indexed by `${mode}:${key}`. Full detail: [`docs/VIEWER.md`](docs/VIEWER.md).

## Receptors & targets

A focusable section listing the merged `data.targets` = every receptor **plus** every non-receptor drug target from `meta.drug_targets`, grouped by neurotransmitter system (`buildTargetLegend`); focusing one shows gem-dot markers on its regions (`js/receptor-markers.js`). Panels: `showReceptor` / `showTarget`.

- Each of a receptor's four classification attributes (family / class / sign / synaptic) is its **own** graded node: a quote upgrades only the attributes listed in `RECEPTOR_CLASSIFICATION_COVERAGE` (or given their own quote in `RECEPTOR_ATTR_QUOTES`), never one it does not substantiate.
- Each expression region is its **own** graded node (`receptor_locations` / `target_locations`, shared `_location_sources` emitter). A target's direction-flipping polarity flag is its own node too (`target_polarity`).
- **Expression density** (Allen AHBA, corpus #8): **one node per profile**, not per region; **confirm-only** (trimmed to regions the owner already claims, never adding one); a gene below `DENSITY_MIN_R` (0.5, donor agreement) publishes **nothing** (an honesty gate, not a caveat). Caveat shipped in the caption: mRNA, not protein, and transcript sits in cell bodies, not terminals.

Full detail (panels, markers, density pipeline): [`docs/VIEWER.md`](docs/VIEWER.md).

## Drugs

Full detail: [`docs/DRUGS.md`](docs/DRUGS.md).

- Roster scope is **CNS-active, not psychiatric**: a drug belongs when it acts on a modeled target (exclusions in `docs/DRUGS.md`; open sourcing gaps in `docs/SOURCING_GAPS.md`).
- Drugs live in `tools/data/drugs_data.jsonl`, never in `public/data/`. Stahl bindings are **strictly dump-sourced** and never overwritten (a target Stahl omits may be added from a judged Wikipedia sentence); non-Stahl drugs get bindings from **PDSP Ki**.
- Every LLM pass is four steps: fetcher offers candidates with **no verdict** -> LLM answers by **index** echoing the candidate's `qid` (`tools/pipeline/judged.py`, a shifted worklist is refused) -> applier gates (`tools/pipeline/gate.py`) and is **sole writer** -> `recheck_quotes.py` stamps the judge. An `extraction: "code"` path needs no recheck.
- A hand-recorded Ki carries `ki.source.curated: true`, so `fetch_ki.py --apply` never strips it.

## Drug metabolism

Full detail: [`docs/DRUGS.md`](docs/DRUGS.md).

- Pharmacokinetics has **no anatomy**: nothing here ever lights the 3D scene. Rows come from committed caches, never `drugs_data.jsonl`.
- Drug -> drug edges are **derived, never stored**, and always worded conditionally ("could raise", never a contraindication).
- The CPIC readout (`pgxSection`) pairs a phenotype's frequency with what CPIC says follows: the picked population group is **never persisted** (an ancestry is not a flag to store), and the "not medical advice, genotype rather than infer from ancestry" caveat is part of the section, not a tip.

## Simulation (beta)

Full detail: [`docs/DRUGS.md`](docs/DRUGS.md).

- The one place the app **computes** a claim: an **engagement index, never % occupancy**, potencies add with no competition. Every shortcut is listed once in the `js/sim-model.js` header.

## Addon nodes (panel annotations)

An **addon** is the node kind for a claim with no implied home (a caveat over a section, a flag on one drug), and it **carries its own insertion point** (`owner_kind` + `owner` + `slot`), so adding one is a data edit, never a viewer edit. Authored in `tools/data_generators/addons.py` with closed vocabularies `ADDON_SLOTS` / `ADDON_SECTIONS` / `ADDON_DISPLAYS` / `ADDON_TONES` / `ADDON_BASES` emitted into meta. A `basis: "dataset"` addon (a statement about the dataset itself) is unsourceable by design: neutral ◌ pill, untallied.

- **A slot exists only if a panel view (`js/panel/views/*.js`, or `js/legend/anatomy.js`) calls `appendAddons(host, ownerKind, ownerId, slot)` for it**, else its node is silently swallowed; the generator and `check_data.py` reject an unknown slot, and `test_generate.AddonTest` checks every slot has a call site. Slots today: `drug.top`, `drug.metabolism`, `drug.timing` (under the Tmax / half-life chips), `receptor.top`, `target.top`, `structure.top` (anchors the hemisphere-less base), `section.projections`, `section.metabolism` (the enzyme list is never exhaustive, said once for every drug).
- The `drug.metabolism` slot has a derived fallback (`autoModulation` -> `derivedAutoModulation`, conditional wording, no pill) that fires **only when the slot holds no authored addon**.

Full detail: [`docs/VIEWER.md`](docs/VIEWER.md).

## Images

Molecule images are **vendored** same-origin (`tools/fetch/fetch_molecules.py` -> `public/data/molecules/<id>.svg`, CSP `img-src 'self'`); structure + circuit images are **hot-linked** from Wikimedia (only the url is stored, via `tools/fetch/fetch_structure_images.py`), which needs the `img-src https://upload.wikimedia.org` CSP allowance. Full detail (resolver, gallery, lightbox): [`docs/VIEWER.md`](docs/VIEWER.md).

## Source provenance

Every node's source carries a **grade** (data, rendered as a pill on the row that carries the claim, never a separate "Sources" block). Ladder (`PROVENANCE_LEVELS`): `llm` grey **?** (from memory, unchecked) < `sourced` yellow **~** (given the document, not quote-checked) < `verified` green **✓** (quote programmatically found on the page + a separate LLM judge agreed). No source = red **✕** `NOSOURCE` (not a stored grade); blue **∅** UNKNOWN = searched every required corpus, none states it (only via a committed search log, `tools/data_generators/unknown.py`; outside the headline denominator; expires like freshness). `uncertain` orange **⚠** is a *display* grade taken by a node with non-empty `uncertainty[]` bullets; it buckets as **backed**.

- **One source shape:** quote-level `{corpus, page, quote, provenance}` against a `SOURCE_CORPORA` corpus (emitted as `meta.source_corpora`); `provenance` defaults `llm`. Upgrading a grade is a data edit.
- **No LLM-picked quote ships unjudged by Sonnet or better** (`sonnet`/`opus`, never `haiku`): `check_data.py` family 5 fails on a citation whose pipeline has `extract_llm` and no `judge_llm`. Any extraction pass that writes no `llm` stamp must be followed by `tools/sourcing/recheck_quotes.py`. A quote **code** copied from a table (`extraction: "code"`, or a `machine` corpus) needs no judge.
- Grade, `pipeline` (chain of custody, `QUOTE_PIPELINES`) and verdicts ride the **citation**, not the quote node: one sentence can back two claims by two routes (citation sites, `tools/sourcing/citation_site.py`). Judge stamps (`quote_llm.json`) are keyed `{quote: {site: llm}}`, so a quote newly cited at another site ships unjudged there.
- **Uncertainty flags are derived, never authored per site** (`apply_binding_uncertainty` / `apply_projection_uncertainty` / `apply_animal_evidence`); every bullet is itself a sourced claim from the closed `UNCERTAINTY_REASONS` vocabulary. The exception is `contradicted`, hand-curated in `tools/data_generators/quotes/contradictions.py` as one `CONTRADICTIONS` table keyed by citation site (any node-shaped site, `citation_site.node_index`). `animal_evidence` flags a claim whose every species-recording source is non-primate (`tools/lib/species.py`).
- **Tally:** a bare `llm` grade buckets as **missing** (no document), like a sourceless node. The live figures live in the README `SOURCING_STATS` block + the Sources popup, never repeated here.
- **Page files are author-side** (`CLAUDE.local.md`), so the quote gate is skipped + warned on a clone, except #13 PharmFreq and #15 CPIC (exports committed, gated by re-derivation).
- Descriptions are not nodes: drugs/structures/targets fetch the live Wikipedia lead at runtime (shown as a green source link, not a stored grade).

Corpora (`SOURCE_CORPORA`):
- #1 `stahl`: drug bindings, NbN, class, brands (na), T½/metabolites, CYP roles.
- #2 `kandel` / #6 `nieuwenhuys`: pathways + region anatomy.
- #3 `stahl_essential`: receptor/target mechanism classification. #4 `carlat`: drug cross-checks.
- #5 `pdsp_ki`: measured binding Ki (a CSV row id, not a page).
- #7 `gtopdb`: receptor "Regional distribution" regions (with assay species). #8 `allen_ahba`: target + residual receptor regions (PACall, no judge) and expression density.
- #9 `wikipedia_pharm`: fallback Ki, binding directions, metabolite bindings, CYP roles, Tmax, non-Stahl drug classes (#10 FR leads as fallback), receptor synaptic site / ion-channel sign / target type (with #3 prose). #10 `wikipedia_fr`: eu/fr brands.
- #11 `gtopdb_ki`: Ki/direction where PDSP has no assay. #12 `gtopdb_class`: target type + GPCR sign (mapped from transduction).
- #13 `pharmfreq`: enzyme metabolizer-phenotype variability. #14 `dailymed`: US label Tmax.
- #15 `cpic`: what a metabolizer phenotype implies for one prescription (implication + recommendation + strength), `page` = guideline ClinPGx id.
- #16 `bdpm`: French RCP section 5.2 Tmax/half-life + fr brands (code read of the denomination), `page` = product CIS.
- #17 `europepmc`: paper abstracts, plus Europe PMC's open-access full text (tables as `cell | cell` rows, licence recorded) where one exists, for what only a study measures (hand-listed `fetch_europepmc.PAPERS`, or a Wikipedia-cited paper for a missing Ki), `page` = PMID.
- #19 `agnp_tdm`: AGNP TDM consensus guideline 2026 (Table 5 therapeutic range + alert level, Table 1 CYP/UGT substrates, ranked after the other metabolism corpora), code-read table rows, `page` = PDF page.
- #20 `clinpgx`: ClinPGx (PharmGKB) clinical annotations, CC BY-SA 4.0, committed export `tools/data/clinpgx/` pinned + re-derived like #15, one quote per genotype sentence (code copy, no judge), `page` = annotation id.
- #21 `pubchem`: computed XLogP3 + TPSA (code-read property table, no judge), `page` = PubChem CID, the drug's CID read off its stored Wikipedia drugbox.
- #22 `b3db`: B3DB blood-brain-barrier benchmark (Meng 2021), BBB+/BBB- label + logBB, one quote per row (code copy, no judge), joined by CID else exact name and always guarded by InChI formula + connectivity, `page` = CID.
- #23 `gtopdb_function`: GtoPdb per-target "Physiological Functions", "Clinically-Relevant Mutations and Pathophysiology" and "Altering Gene Expression" rows (+ comments), one statement per line naming its section and species, backing `receptor_effect` (LLM-picked by index + judged; a row with a stated non-human species is never offered), `page` = targetId.
- #24 `bdpm_rcp`: the same official French RCPs as #16, sections 4.2 / 4.3 / 4.4, the checks a label asks for before and during treatment (`drug_workup`, LLM index pick + judge), `page` = product CIS, linked to the BDPM `/extrait` page (EMA SmPC PDF for a centrally authorised drug); built offline from an RCP copy on disk, freshest copy winning.
- #18 `drugsfda`: Drugs@FDA (openFDA export), the fallback first **US** approval (`national: true`, code-read, no judge) where no other source dates one, `page` = NDA number.

Full detail (sourcing model, citation sites, book heading trails, the four uncertainty flags, per-corpus mechanics, the "% sourced" maths): [`docs/PROVENANCE.md`](docs/PROVENANCE.md).

## Changing the data

The step-by-step runbook (per node-kind authoring fields, the regenerate/check/fetch
sequence, and the author-side "refresh external data" recipe) lives in
[`tools/README.md`](tools/README.md). The invariants that outlive any recipe: edit the
source of truth (`generate_data.py`, or `tools/data/drugs_data.jsonl` for drugs), never the
emitted `public/data/`; every new display string needs its `FR`/`{en,fr}` translation or
the build raises; commit the generator change + regenerated artifacts together; keep Stahl
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

One file per version: `docs/changelog/<major.minor.patch>/changelog.md`, titled `# <version> (YYYY-MM-DD)`, then `## <Category>` sections (closed `CATEGORIES` in `tools/data_generators/changelog.py`) of `- bullet (sha, sha)` lines, each with a required indented `fr:` line. `generate_data.py` emits them to `public/data/changelog.json`, shown by `js/changelog.js`. `check_data.py` family 9 fails if `version.js` has no changelog directory. Full detail (popup, seen-tracking, sha links): [`docs/VIEWER.md`](docs/VIEWER.md).

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
