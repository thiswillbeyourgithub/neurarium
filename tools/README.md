# Authoring & data tooling

Runbooks for editing the dataset and refreshing external assets, plus the reference
for **what each tool is** (Tool reference, below) and the **emitted data contract**
(Data contract, below). Both moved here from [`../CLAUDE.md`](../CLAUDE.md) to keep that
file terse; CLAUDE.md keeps the viewer/runtime map and the non-obvious rules. Author-side
corpus locations are in `CLAUDE.local.md`.

## Contents

- [Changing the data](#changing-the-data)
- [Writing release notes](#writing-release-notes)
- [Refreshing external data (author-side)](#refreshing-external-data-author-side)
- [Tool reference](#tool-reference)
  - [Shared libraries](#shared-libraries)
  - [Generator and data modules](#generator-and-data-modules)
  - [Code and data checks](#code-and-data-checks)
  - [Meshes, dev server, screenshots, icons, demos](#meshes-dev-server-screenshots-icons-demos)
  - [Stahl quote sourcing (bindings, NbN, classes)](#stahl-quote-sourcing-bindings-nbn-classes)
  - [Expression and function (GtoPdb #7 / #23, Allen AHBA #8)](#expression-and-function-gtopdb-7--23-allen-ahba-8)
  - [Receptor effects, release modulation and demographics (BETA)](#receptor-effects-release-modulation-and-demographics-beta)
  - [Quote recheck and citation sites](#quote-recheck-and-citation-sites)
  - [Pharmacogenomics (PharmFreq #13, CPIC #15, ClinPGx #20)](#pharmacogenomics-pharmfreq-13-cpic-15-clinpgx-20)
  - [Book heading resolution](#book-heading-resolution)
  - [Drug metabolism (CYP roles)](#drug-metabolism-cyp-roles)
  - [Binding Ki (PDSP #5, GtoPdb #11)](#binding-ki-pdsp-5-gtopdb-11)
  - [Wikipedia articles and brand names (#9, #10)](#wikipedia-articles-and-brand-names-9-10)
  - [Half-life and time to peak (Stahl, DailyMed #14, BDPM #16, Europe PMC #17)](#half-life-and-time-to-peak-stahl-dailymed-14-bdpm-16-europe-pmc-17)
  - [Drug history, origin and approvals (Drugs@FDA #18)](#drug-history-origin-and-approvals-drugsfda-18)
  - [Physicochemistry, workup and TDM (#19, #21, #22, #24)](#physicochemistry-workup-and-tdm-19-21-22-24)
  - [Prodrugs and metabolite bindings](#prodrugs-and-metabolite-bindings)
  - [Binding directions and UNKNOWN searches](#binding-directions-and-unknown-searches)
  - [Binding gaps](#binding-gaps)
  - [Book corpora (PDF to pages)](#book-corpora-pdf-to-pages)
  - [README stats, images, git hooks](#readme-stats-images-git-hooks)
- [Data contract (emitted `public/data/`)](#data-contract-emitted-publicdata)
  - [Geometry](#geometry)

## Changing the data

1. Edit the relevant list in `generate_data.py` (or `tools/data/drugs_data.jsonl` for drugs).
   - **Structures**: edit `PAIRED` / `MIDLINE`; search-only acronyms ("VTA", "LC") go in `regions/__init__.py` `STRUCTURE_ALIASES` keyed by base id (emitted as `aliases`, never rendered nor graded; an unknown key fails the build, like `DRUG_ALIASES`). Paired entries are auto-mirrored (define on the right,
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
     Hypothetical section). Projections are bilateral by default (define once on the right):
     such a pathway is emitted **once** with `mirror: true` and the consumer reflects it to the
     other hemisphere (no duplicate row per pathway; see `mirror` under the data contract below).
     `symmetric: False` keeps a one-sided pathway (emits no flag). `kind` must be a `PROJECTION_COLORS` key
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
     value needs its label map entry (+ FR). The four classification attributes
     (`family`/`receptor_class`/`sign`/`synaptic`) are each **independently graded**: the base
     grade is `RECEPTOR_PROVENANCE` (default `llm`), lifted per-attribute only where
     `RECEPTOR_CLASSIFICATION_COVERAGE` says the receptor's Stahl-Essential quote
     (`STAHL_ESSENTIAL_RECEPTOR_QUOTES`) actually backs that attribute (conservative: never list
     an attribute the quote or the record disagrees on; `RECEPTOR_ATTR_QUOTES` gives an
attribute a *different* quote than the main one, or several to back a compound value like
`synaptic="both"`). An individual expression region is
     sourced (above `llm`) by adding a `{receptor_id: {base: [quote-source]}}` entry to
     `RECEPTOR_LOCATION_SOURCES`.
   - **Drugs**: edit `tools/data/drugs_data.jsonl`. Each: `id`, `name`, `categories`, optional
     `nbn` + `description` (inline `{en,fr}`), `wikipedia`, `bindings`. A binding is
     `{target, action}` (+ optional `effect` / `note` / `tentative`); `target` is a merged
     map key (a `DRUG_TARGETS` key or a receptor id), `action` a `DRUG_ACTIONS` key
     (agonist / partial_agonist / antagonist / inverse_agonist / reuptake_inhibitor /
     releaser / enzyme_inhibitor / pam / nam / blocker / modulator). `"bindings": []` is
     allowed: the drug still opens its panel (lithium), it just lights nothing. A new coarse target/category/action needs a `DRUG_TARGETS` /
     `DRUG_CATEGORY_LABELS` / `DRUG_ACTIONS` entry (with `{en,fr}` labels; a `DRUG_TARGETS`
     entry needs a `type` + optional `wikipedia`). Target classification grade
     overridable in `TARGET_PROVENANCE`; an individual "Found in" region is sourced
     (above `llm`) by adding a `{target_id: {base: [quote-source]}}` entry to
     `TARGET_LOCATION_SOURCES` (mirror of `RECEPTOR_LOCATION_SOURCES`). The drug's class
     classification grade is overridable in `DRUG_CATEGORY_PROVENANCE` (or upgraded by a
     quote-level `category_sources` on the authored drug). Keep Stahl extraction strictly
     dump-sourced (a Wikipedia binding only adds a target Stahl does not list).
   - **Panel annotations (addons)**: append to `ADDONS` in `tools/data_generators/addons.py`:
     `id`, `owner_kind` + `owner` (the node it annotates; a structure anchors its base, and
     `section` anchors a whole browse view via an `ADDON_SECTIONS` key instead of a node),
     `slot` (an `ADDON_SLOTS` key, which is the panel hook the viewer offers), `display`
     (`admonition`), `tone` (`caution`/`info`), optional `title`, `text` (both inline
     `{en,fr}`) and `sources` (graded like any node). Use it for a claim no existing kind
     has a home for. A **new slot** is two edits: the `ADDON_SLOTS` entry here and the one
     matching `appendAddons(...)` call in the viewer (`js/panel/views/*.js`, `js/legend/anatomy.js`); a slot with no call site would
     swallow the node silently. A **new display** is an `ADDON_DISPLAYS` entry plus one
     `ADDON_RENDERERS` function.
   - **Translations**: every display string is wrapped with `_t()`; add the French to the
     `FR` table or the build raises listing every miss. For a feminine/plural paired name set
     `fr_gender` (`f`/`mp`/`fp`).
2. Run `python tools/generate_data.py` to regenerate `public/data/`.
3. If you touched a `data/shapes/*.json` **sdf** spec (or added/removed a structure), re-bake
   the geometry: `node tools/bake_meshes.mjs`. Skipping it is caught, not silent (`check_data.py`
   family 11 and `--check` both re-hash the shape files), and the site still renders correctly
   meanwhile by meshing in the browser, just slower. See [`docs/BAKED_MESHES.md`](../docs/BAKED_MESHES.md).
4. Optionally run `python tools/check_data.py`.
5. For new drugs/structures with links, run the fetch tools (network, idempotent, touch
   only the new ones): `fetch_molecules.py`, `fetch_structure_images.py`. To refresh
   binding affinities, run `fetch_ki.py --apply` (reads the local PDSP CSV; idempotent),
   which rewrites `drugs_data.jsonl`'s `ki` annotations + `affinity_only` bindings.
6. Commit the generator change + the regenerated artifacts together.

The legend is generated at runtime from the data, so it updates automatically.

## Writing release notes

Every version bump needs a `docs/changelog/<major>.<minor>.<patch>/changelog.md`, or
`check_data.py` family 9 fails (the gate exists so a bump can never ship a "What's new"
popup that announces an update it cannot describe). The format:

```markdown
# 3.39.0 (2026-07-28)

## Added
- What a visitor can now do, in their words, no jargon (2e7c22f, 211e89f)
  fr: La même chose en francais
```

- The `# <version> (YYYY-MM-DD)` title is required: it carries the release date (nothing else
  does, the emit being a plain file read) and must match its directory, which catches the
  copy-paste that made the file.
- Headings are the five categories `Added` / `Improved` / `Fixed` / `Data` / `Docs`
  (`CATEGORIES` in `data_generators/changelog.py`), used in whatever order the release wants.
- Every bullet needs an indented `fr:` line right under it, like every other display string.
- A trailing `(sha, sha)` list is stripped into `commits` and rendered as links to the commit
  on the source host; other trailing parentheses stay as prose. Write the shas after committing
  the work, so they are real (family 9 checks the shape, the host resolves the rest).
- Write for a casual reader: what changed for them, not which module changed.

Then `python tools/generate_data.py` compiles the whole tree into `data/changelog.json`
(newest first) and the French into `translations.fr.json`.

## Refreshing external data (author-side)

Every fetcher sends the one User-Agent of `tools/lib/polite_http.py`, and most go through its polite GET (backoff on 429/503). Set `NEURARIUM_FETCH_CONTACT` to a real e-mail or URL before a large run (Wikimedia asks for a contact); unset, it sends "contact via repository".

To re-pull every third-party asset the dataset hot-links or vendors, run these (all
network, idempotent, polite; each touches only what changed). Always finish with
`generate_data.py` so the emitted `public/data/` picks up the new urls/files:

1. `python tools/fetch/fetch_molecules.py` — new per-drug molecule SVGs into
   `public/data/molecules/` (only drugs missing one); writes `tools/generated_cache/molecules_sources.json`.
2. `python tools/fetch/fetch_structure_images.py` — re-resolve each structure's **and**
   wiki-linked circuit's Wikipedia hero + gallery image **urls** into
   `tools/generated_cache/structure_images_sources.json` + `tools/generated_cache/circuit_images_sources.json` (no bytes
   downloaded; the gif/svg is hot-linked at runtime). `--target structures|circuits`
   scopes to one.
3. **PDSP Ki**: `python tools/fetch/fetch_ki.py --download` re-downloads the whole-DB CSV from
   `https://pdspdb.unc.edu/databases/kiDownload/download.php` over
   `data_sources/books/pdsp_ki/KiDatabase.csv` (author-side; see that dir's `README.md`), paging
   with the `fromDate=<kiId>` cursor because the whole-DB export is silently capped. TLS is fully
   verified: the host chains to an emSign root missing from the Mozilla store, so the download
   also trusts the pinned cross-certificate `tools/fetch/certs/pdsp_chain.pem` (its header gives
   the fingerprint and why); a rotated chain fails loudly pointing there. Then
   `python tools/fetch/stamp_fetch_dates.py` and `python tools/fetch/fetch_ki.py --apply` to
   rewrite `drugs_data.jsonl`'s `ki` + `affinity_only`.
4. **GtoPdb ligand interactions** (the `gtopdb_ki` Ki fallback + the curated directions for
   `affinity_only` bindings): `python tools/fetch/fetch_gtopdb_ki.py` re-downloads the bulk
   `interactions.csv` and rebuilds `data_sources/gtopdb/pages_ki/` (author-side) +
   `tools/generated_cache/gtopdb_ki.json`, then `python tools/sourcing/apply_gtopdb_ki.py`
   quote-gates + merges into `drugs_data.jsonl`. Run it **after** `fetch_ki.py`, since it only
   fills what PDSP left empty. See docs/PROVENANCE.md (corpus #11).
5. **GtoPdb receptor expression** (the `receptor_locations` sources): `python
   tools/fetch/fetch_gtopdb.py` re-pulls each receptor's tissue comments (caches to
   `data_sources/gtopdb/`, author-side), then run the confirm-only judge over
   `data_sources/gtopdb/worklist.json` and `python tools/sourcing/apply_location_sources.py --judged <f>`
   to merge new `verified` sources into `tools/generated_cache/location_sources.json`. See docs/PROVENANCE.md (corpora #7/#8).
6. **Allen AHBA expression** (the `target_locations` + residual `receptor_locations`
   sources): `python tools/fetch/fetch_allen.py` re-pulls each donor's microarray PACall (caches
   to `data_sources/allen/`, author-side; ~2GB across donors), then `python
   tools/sourcing/apply_location_sources.py --corpus allen` merges the deterministic `verified`
   sources (no judge) into `tools/generated_cache/location_sources.json`. See docs/PROVENANCE.md (corpora #7/#8).
7. **Allen AHBA expression density** (the `receptor_density` + `target_density` profiles): the same
   `fetch_allen.py` run also z-scores each gene's microarray intensity per region and writes
   `data_sources/allen/density.json` (pass `--skip-density` to opt out of the heavy
   MicroarrayExpression read), then `python tools/sourcing/apply_expression_density.py` re-gates each
   profile quote and writes `tools/generated_cache/expression_density.json`. See docs/VIEWER.md Expression density.
8. **GtoPdb target classification** (the `receptor_class` + `sign` + non-receptor `targets`
   sources): `python tools/fetch/fetch_gtopdb_class.py` pulls each target's `type` +
   transduction table (caches to `data_sources/gtopdb/pages_class/`, author-side, +
   `tools/generated_cache/gtopdb_class.json`), then `python
   tools/sourcing/apply_classification_sources.py` maps + quote-gates + merges the confirm-only
   `verified` sources (no judge) into `tools/generated_cache/classification_sources.json`. See
   docs/PROVENANCE.md (corpus #12).
9. **Drug metabolism** (the `drug_enzymes` rows): `python tools/fetch/fetch_cyp_worklist.py`
   re-reads Stahl's per-drug `Pharmacokinetics` block and the stored English Wikipedia articles
   (`data_sources/wikipedia/pages/`, corpus #9) into `tools/generated_cache/cyp_worklist.json`,
   offering candidate sentences with no verdict. An LLM pass writes each drug's picks (a candidate
   **index** plus enzyme/role/strength) into `tools/generated_cache/cyp_judged.json`, then `python
   tools/sourcing/apply_cyp_sources.py` gates them and writes both
   `tools/generated_cache/drug_enzymes.json` and `drug_enzymes_wikipedia.json`;
   `generate_data.py` merges them Stahl-first. A drug whose article is not stored yet needs `uv run
   tools/fetch/fetch_wikipedia_pharmacology.py --drug <id>` first. See docs/DRUGS.md Drug metabolism.
10. **Freshness refetch** (every editable online corpus, see docs/PROVENANCE.md "Freshness"; `check_data.py` fails once a cited page is over 12 months old, and `pre-push` enforces it): `uv run tools/fetch/fetch_wikipedia_pharmacology.py --refresh` (every stored EN article plus any roster drug lacking one), `uv run tools/fetch/fetch_brand_names.py` (every FR article; prints the drugs with none), `python tools/fetch/fetch_gtopdb_ki.py --refresh`, `python tools/fetch/fetch_dailymed.py --redownload` (the chosen labels in place; `--refresh` would re-pick labels and orphan the cited ones), `python tools/fetch/fetch_bdpm.py --refresh`, `python tools/fetch/fetch_bdpm_rcp.py` (after refreshing the RCP copies it reads), `python tools/fetch/fetch_drugsfda.py --refresh` (then `apply_drugsfda.py`), `python tools/fetch/fetch_cpic.py`, `python tools/fetch/fetch_clinpgx.py --refresh`, `python tools/fetch/fetch_physchem.py --refresh`, the PDSP CSV (item 3), and `fetch_gtopdb.py --refresh` / `fetch_gtopdb_class.py --refresh` / `fetch_gtopdb_function.py --refresh` (all three call the GtoPdb web services, which need a per-user API key: put it in env `GTOPDB_API_KEY` or the gitignored file `data_sources/gtopdb/api_key.txt`; it is sent as the `GTP-API-Key` header and never written to any page, cache or log). Allen (~2GB) and the hand-downloaded PharmFreq export are dated by their download; refetch them only when their date nears the limit. Then dry-run the appliers (`apply_gtopdb_ki.py --dry-run`, ...) and run `check_data.py` to list quotes no longer on their refreshed page, and finally `python tools/fetch/stamp_fetch_dates.py` to freeze the new dates into `tools/generated_cache/fetch_dates.json`.
11. `python tools/generate_data.py` — regenerate `public/data/` from all of the above.
12. `python tools/update_readme_stats.py` — refresh the README sourcing table
   (CI runs it `--check`).

Panel **descriptions** need no refresh script: each fetches the current Wikipedia lead
at runtime (`js/wiki.js`), so they stay current on their own.

## Tool reference

What each authoring / fetch / check script in `tools/` is (one line each). The dev/runtime
tooling (`serve.py`, `shot.py`, `demos/`) is also summarized in `../CLAUDE.md` (Running,
Screenshots).

### Shared libraries

- Shared helpers (reuse, never copy): `lib/polite_http.py` (the one GET + User-Agent), `pipeline/judged.py` (qid-checked index picks) + `pipeline/gate.py` (the applier's page gate), `lib/salt_words.py` (EN salt words for name joins), `lib/chirality.py` (enantiomer tags), `data_generators/caches.py` (`load`, `labels`, `attests` for committed caches), `data_generators/node_id.py` (the id shape `check_data` and `render_api` enforce).
- `tools/lib/`: shared libraries (no `main`, never run): the root helpers above, `quote_match.py` (`normalize_for_match`, `emitted_page_dirs`), `gene_maps.py` (owner -> HGNC gene), `page_file.py` (`page_file` / `page_path` / `read_page`, the one citation page -> file rule and raw page reader), `structure_ids.py` (`base_id`, the one hemisphere-suffix rule), `corpora/wikipedia.py` + `corpora/bdpm.py` (stored corpus pages + their joins), `parse/durations.py` (EN/FR duration parsing). A script imports these as `from lib import X` after inserting `tools/` on `sys.path`; it never imports another script for a helper.
- `tools/lib/drugs_io.py` — shared JSONL load/save for `drugs_data.jsonl` (`load_drugs`/`save_drugs`);
  used by `generate_data.py`, `fetch_ki.py`, and the three `apply_*_sources.py` writers.
- `tools/lib/text_fold.py`: shared name folding (`strip_accents`, `alnum_key`) for every author-side matcher; reuse it rather than re-spelling an NFKD fold or an INDEX-name key.

### Generator and data modules

- `generate_data.py` — single source of truth for the anatomy (stdlib-only, offline):
  defines every region/projection/receptor once, emits the artifacts below. Drugs are the
  exception (authored in `tools/data/drugs_data.jsonl`, read by `_load_drugs`). Display strings are
  `{en,fr}` via `_t()` (see CLAUDE.md I18n).
- `tools/data/drugs_data.jsonl` — the authored drug dataset (from Stahl 8th ed.), one compact
  JSON object per line, read by `_load_drugs`, emitted to `data/drugs.jsonl`. Edit to add/change a drug.
- `tools/data_generators/` — pure-data modules imported by `generate_data.py`: `drugs.py`,
  `provenance.py` (grades, `_GRADE_RANK`, source validators), `corpora.py` (`SOURCE_CORPORA`),
  `provenance_stats.py` (the sourcing tally `_strongest_grade`/`_binding_grade` + `_provenance_stats`,
  which reduce the emitted nodes to `meta.provenance_stats`), `integrity.py` (authored-table typo
  guards), `meta.py` (the `meta.json` builder),
  `i18n.py`, `quote_table.py` (the serialization-time source-quote externalize pass -> `quotes.jsonl`,
  mirroring the i18n externalize), and the `receptors/` subpackage (one module per neurotransmitter
  family, e.g. `serotonergic.py`, each exposing `ENTRIES`; `__init__.py` concatenates them into
  `RECEPTORS` in the original order), the `regions/` subpackage (one module per anatomical `group`,
  e.g. `cortex.py`/`basal_ganglia.py`, each exposing `PAIRED` + `MIDLINE`; `__init__.py` concatenates
  them into `PAIRED`/`MIDLINE` in the original order), and `geometry.py` (the shared cortical-dome SDF
  helpers, e.g. `_cortex_lobe_entry` + `MIDLINE_GAP`, plus the pure geometry math helpers
  `_scale_sdf`/`_scale_triple`/`_directional_extent`/`_bisecting_clip_planes`, imported by
  `regions/cortex.py` and `generate_data.py`),
  `genes.py` (the HGNC symbol per receptor / non-receptor target, re-exported from the fetchers that
  own the maps rather than restated; an identifier for the gene-keyed lookup links, not a graded node),
  and `connectivity.py` (the three connectivity node literals `PROJECTIONS`/`CIRCUITS`/`PROJECTION_GROUPS`
  plus the `_KQ_*`/`_SG_*` pathway quote-source constants they cite; the shared `_kandel`/`_nieuwenhuys`/`_stahl_ess`
  quote constructors live in `provenance.py`), `addons.py` (the addon-node kind: the
  `ADDON_SLOTS`/`ADDON_DISPLAYS`/`ADDON_TONES` vocabularies emitted into `meta.json` plus the
  authored `ADDONS` list), and `presentation.py` (the presentation maps emitted
  into `meta.json`: the colour/flow maps `PROJECTION_COLORS`/`KIND_TO_SIGN`/`SIGN_COLORS`/`SYSTEM_FLOW_KINDS`,
  the label maps `SIGN_LABELS`/`GROUP_LABELS`/`RECEPTOR_FAMILY_LABELS`/`RECEPTOR_CLASS_LABELS`/`SYNAPTIC_LABELS`,
  plus the per-structure `WIKIPEDIA` link table; a dependency-free leaf), and the `quotes/` subpackage (verified quote registries by
  corpus: `kandel.py` = `PROJECTION_QUOTES` + `STRUCTURE_QUOTES` (Kandel/Nieuwenhuys anatomy, cites the
  connectivity `_KQ_*`); `stahl_essential.py` = `STAHL_ESSENTIAL_RECEPTOR_QUOTES`/`STAHL_ESSENTIAL_TARGET_QUOTES`/
  `RECEPTOR_ATTR_QUOTES`/`RECEPTOR_CLASSIFICATION_COVERAGE`/`CLASSIFICATION_ATTRS`/`TARGET_POLARITY_QUOTES`;
  `metabolism.py` = `METABOLITE_ENZYME_QUOTES`; `contradictions.py` = `CONTRADICTIONS`, the
  hand-curated table of claims another corpus DENIES, keyed by citation site, any node kind (the
  `contradicted` badge, mostly the in-vitro-vs-in-vivo split; applied by `apply_contradictions`); `uncertainty.py` = the mirror image of the others
  (`UNCERTAINTY_REASONS` + `apply_binding_uncertainty`: why a quote-checked claim still deserves doubt.
  Alone among these, it authors **nothing**: both flags and bullets are derived from the emitted data,
  reading each quote's heading trail through `quote_table.heading_of`);
  chain stays acyclic provenance <- connectivity <- quotes <- generate_data).
- `tools/data_generators/changelog.py` — parses the authored `docs/changelog/<version>/changelog.md`
  files into the `changelog.json` shape (stdlib, no deps). Fails loud with `file:line` on an unknown
  category, a bullet with no `fr:` line, or stray prose, so a typo cannot silently drop a bullet.

### Code and data checks

- `tools/check_data.py`: stdlib integrity checker over emitted `public/data/` (see CLAUDE.md Data checks); the CLI only, one module per family in `tools/checks/` (family 5's walks in `tools/checks/sources/`).
- `tools/check_js.py` — stdlib scope walk over `public/**/*.js`, reporting every identifier reference
  no enclosing scope binds (the `ReferenceError` a valid-syntax file still ships). Takes paths, else
  checks the whole viewer; exit 1 on a finding. Run by `pre-push` and by `tools/tests/test_check_js.py`.

### Meshes, dev server, screenshots, icons, demos

- `tools/bake_meshes.mjs` — **Node** (no deps): meshes every distinct `sdf` shape author-side into
  `public/data/meshes/*.bin` + `index.json`, so a visitor downloads the geometry instead of
  rebuilding it (~0.7s instead of ~3.0s, more on a phone). Imports the browser's own
  `js/sdf-core.js` + `js/noise.js` so the bake cannot drift from the runtime fallback, and
  round-trips every mesh through the real decoder before writing. Run after `generate_data.py`
  (it reads the emitted `structures.jsonl`); `--check` verifies the bake is current and writes
  nothing. See [`docs/BAKED_MESHES.md`](../docs/BAKED_MESHES.md).
- `tools/serve.py` — stdlib dev server, `Cache-Control: no-store`, roots at `public/` (see CLAUDE.md Running).
- `tools/shot.py` — Playwright screenshot helper (see CLAUDE.md Screenshots).
- `tools/icons/brain_icon.py`: stdlib generator of every app icon: the README / PWA brain (`docs/images/neurarium-icon.svg`, `public/icon-*.png`, `public/apple-touch-icon.png`) and the simplified favicon (`public/favicon.svg`); PNG export via `rsvg-convert`. Edit it, never the generated files.
- `tools/demos/` — Playwright demo-video recorder: `recorder.py` (a `Demo` API) + `neurarium.py`
  (the showcase tour, writes the README hero `docs/images/preview.gif`). Needs ffmpeg+gifski+GPU; see
  `tools/demos/README.md`.

### Stahl quote sourcing (bindings, NbN, classes)

- `tools/sourcing/build_source_worklist.py` — lists not-yet-sourced drug bindings with Stahl page ranges
  (input to the source-extraction workflow; resumable).
- `tools/sourcing/apply_source_quotes.py` — applies the extraction workflow's accepted quotes onto
  bindings (re-finds the quote in the page range; idempotent).
- `tools/sourcing/apply_nbn_sources.py` — sources each drug's NbN line (greps Stahl's verbatim line,
  substring-confirms, no judge); falls back to the drug **Class** line (`nbn_nonstandard`) for a
  newer drug with no NbN line. Idempotent.
- `tools/sourcing/apply_category_sources.py` — sources each drug's class classification (`drug_categories`)
  from an extract/judge results file (a judge is needed: our coarse `categories` re-map Stahl's
  free-text class line, unlike the fixed NbN field). Idempotent.
- `tools/sourcing/apply_binding_sources.py` — writes the small hand-curated `BINDING_SOURCES` table onto
  the bindings no mechanical pass can reach (PDSP/GtoPdb have no assay at the subtype granularity we
  model, and the page prose is too irregular to grep). Re-gates every quote with `check_data`'s own
  normalizer, never overwrites an existing source, and prints known cross-corpus `CONFLICTS` rather
  than resolving them. Idempotent; `--dry-run`.

### Expression and function (GtoPdb #7 / #23, Allen AHBA #8)

- `tools/fetch/fetch_gtopdb.py` — fetches receptor tissue-distribution comments from the Guide to
  Pharmacology API (corpus #7 `gtopdb`), the source for **receptor expression regions**;
  `RECEPTOR_GENES` maps receptor->gene->targetId. Caches `data_sources/gtopdb/` + `worklist.json`
  (each quote carries assay species). See docs/PROVENANCE.md (corpora #7/#8).
- `tools/fetch/fetch_gtopdb_function.py`: stdlib, network (GtoPdb web services, API key as for #7), author-side. Corpus #23 `gtopdb_function`: per receptor / target, the `/function`, `/pathophysiology`, `/alteredExpression` and `/comments` endpoints into `data_sources/gtopdb/raw_function/<owner>.json` + one quote-gate page `pages_function/<targetId>.md` (one statement per line, section + species named). `--only <ids>`, `--refresh`, `--no-fetch` (re-flatten offline). Feeds the receptor-effect pipeline: then `python tools/fetch/fetch_receptor_effects.py` (offers the human or species-less lines as candidates) -> LLM picks by index into `receptor_effects_judged.json` -> `python tools/sourcing/apply_receptor_effects.py` -> `recheck_quotes.py build --kinds receptor_effect --unstamped` + `apply --llm <judge>` -> `stamp_fetch_dates.py` -> `generate_data.py`. For a receptor no stored corpus gives an effect, run `python tools/fetch/fetch_europepmc.py --effect-search` first (writes `europepmc_effect_search.json`, whose abstracts then join the candidates), and after the recheck `apply_receptor_effects.py --unknown-log --model <model>` logs each still effect-less owner as UNKNOWN. See docs/DRUGS.md (Receptor effects).
- `tools/fetch/fetch_allen.py` — fetches the Allen Human Brain Atlas microarray (corpus #8
  `allen_ahba`), the source for **target expression regions** + the receptor regions GtoPdb
  misses; a PACall detection-boolean vote per (gene, region), no judge. `TARGET_GENES` +
  `lib.gene_maps.RECEPTOR_GENES` map owners to genes. Caches `data_sources/allen/` + `confirmed.json`.
  The same run also emits the **density** profiles into `data_sources/allen/density.json`
  (`--skip-density` opts out of the heavy MicroarrayExpression read; `DENSITY_MIN_R` is the
  cross-donor reliability floor). See docs/PROVENANCE.md (corpora #7/#8) + docs/VIEWER.md Expression density.
- `tools/sourcing/apply_expression_density.py` — re-gates each density profile's quote against
  `data_sources/allen/pages/<gene>.md`, trims it to the regions the owner claims, and writes
  `tools/generated_cache/expression_density.json` (loaded into `RECEPTOR_DENSITY` / `TARGET_DENSITY`).
  Idempotent. See docs/VIEWER.md Expression density.
- `tools/sourcing/apply_location_sources.py` — merges accepted expression quotes into
  `tools/generated_cache/location_sources.json`, `--corpus {gtopdb,allen}` (gtopdb needs a judged file; allen is
  deterministic). Idempotent. See docs/PROVENANCE.md (corpora #7/#8).
- `tools/generated_cache/location_sources.json` — machine-written bulk location sources, loaded by
  `generate_data.py` into `RECEPTOR_LOCATION_SOURCES` / `TARGET_LOCATION_SOURCES`. Not served.

### Receptor effects, release modulation and demographics (BETA)

Four-step passes (fetcher offers candidates, one LLM pass picks by index, applier gates, Opus recheck); concepts and gates in docs/DRUGS.md.

Receptor effects (`receptor_effect`):

```
python tools/fetch/fetch_receptor_effects.py              # -> receptor_effects_worklist.json (keyword-offered candidates, no verdict)
<one LLM pass>                                             # -> receptor_effects_judged.json ({owner: [{effect, mode, picks}]})
python tools/sourcing/apply_receptor_effects.py --dry-run  # then without; sole writer of receptor_effects.json
python tools/sourcing/recheck_quotes.py build --out <dir> --kinds receptor_effect   # independent Opus judge, then `apply --llm opus`
```

Release modulation (`receptor_release_modulation`):

```
python tools/fetch/fetch_release_modulation.py               # -> release_modulation_worklist.json (mechanism + transmitter cues, no verdict)
<one LLM pass>                                                # -> release_modulation_judged.json ({owner: [{kind, structure, cell, modulates, effect, picks}]})
python tools/sourcing/apply_release_modulation.py --dry-run   # then without; sole writer of release_modulation.json
python tools/sourcing/recheck_quotes.py build --out <dir> --unstamped   # independent Opus judge, then `apply --llm opus`
```

Demographics (`receptor_demographic`, after adding the paper to `fetch_europepmc.PAPERS`):

```
python tools/fetch/fetch_europepmc.py                       # store any new paper (network)
python tools/fetch/fetch_demographics.py                    # -> demographics_worklist.json (age / sex cues, no verdict)
<one LLM pass>                                              # -> demographics_judged.json ({owner: [{factor, direction, structure, magnitude?, picks}]})
python tools/sourcing/apply_demographics.py --dry-run       # then without; sole writer of receptor_demographics.json
python tools/sourcing/recheck_quotes.py build --out <dir> --unstamped   # independent Opus judge, then `apply --llm opus`
```

### Quote recheck and citation sites

- `tools/sourcing/recheck_quotes.py` — re-verifies every emitted verified quote with a stronger model
  (Sonnet) and stamps the sourcing LLM. `build --out <dir>` writes per-page batches (page text loaded
  once per batch to minimize tokens; Allen AHBA excluded as deterministic); an LLM judges each batch
  (present + supports claim); `apply --batches <dir> --verdicts <f> [--llm sonnet]` writes
  `tools/generated_cache/quote_llm.json` ({quote_id: llm}, applied uniformly by `quote_table`) +
  `quote_recheck_flagged.json` (quotes the recheck could not fully confirm, for review) +
  `quote_recheck_disputed.json` (quotes two models disagree about). Each batch item
  carries the quote's `heading` (below), which is the context the "supports" half of the verdict turns on.
  Corpus -> page dir is read from `meta.source_corpora`, never restated. See docs/PROVENANCE.md ("The sourcing model"). Scope a pass with
  `--kinds`/`--unstamped`/`--stamped-by`/`--flagged`/`--disputed`, and
  `--max-page-chars` trims a page too long to be worth embedding whole (a stored
  Wikipedia article) to the neighbourhoods of the quotes cited on it; `apply`
  **merges** into the three caches, so a scoped pass keeps the stamps, flags and
  disputes it did not re-judge. A stamp names the **strongest** model that has confirmed
  the quote, so a second, weaker read (`--stamped-by opus` re-read by Sonnet) can only
  corroborate it; the mirror of that rule is that a weaker model *doubting* a quote is a
  disagreement, not a verdict, so it parks in `quote_recheck_disputed.json` with the stamp
  intact until the stamping model is asked again (`build --disputed`, `apply --llm <it>`).
- `tools/sourcing/demote_quotes.py` — the other half of a recheck: applies what the flags mean.
  A flagged quote is still stored, so the node still shows a green pill for a claim its
  sentence does not back; this removes that source (never the claim: a drug that loses its
  class quote is still classified, it just no longer says a book said so) or, with
  `--replace <proposals.json>` from a re-extraction pass, rewrites the quote in place after
  re-gating it against the cited page, falling back to removal when the proposal is not
  verbatim there. Walks `tools/data/drugs_data.jsonl` plus the applier-written caches, drops
  an emptied `*sources` key rather than leaving it empty, and clears the ids it handled from
  `quote_llm.json` / `quote_recheck_flagged.json`. Quotes authored in hand-written Python are
  **reported with corpus/page/quote, never rewritten**, so nothing is silently skipped.
  Matching is by `quote_table.quote_id`, so an id from any of the three caches resolves.
  A verdict that names the claim it failed (a target's `sites`, or `--ids X --sites S`) demotes
  only those citations: the quote's other claims keep their source and the quote keeps its
  judging stamp, and a site matching nothing is reported instead of passing for a run that
  changed nothing. Idempotent; `--flagged` / `--ids` / `--sites` / `--dry-run`. Stdlib, author-side.
- `tools/sourcing/citation_site.py` — the address of one *citation*, shared by the two passes
  above. A quote id is a content hash, so one sentence reaching two claims is one id, and a
  verdict keyed by it can only condemn or clear the sentence everywhere at once. A **site**
  (`drug:clozapine/bindings[5ht2a]`, `receptor:5ht1a/locations[amygdala]`) names one place the
  quote is cited from, so a judge can reject the class and keep the binding. `recheck_quotes.py`
  spells it out of the emitted data and `demote_quotes.py` recognizes it walking the authoring
  files, whose shapes differ; `tools/tests/test_citation_site.py` cross-checks the two ends over
  the real dataset, because a divergence does not crash, it just quietly demotes nothing.
  Stdlib, author-side.

### Pharmacogenomics (PharmFreq #13, CPIC #15, ClinPGx #20)

- `tools/fetch/fetch_pharmfreq.py` — stdlib, offline, author-side. Reshapes PharmFreq's
  hand-downloaded "Metabolizer status tool" export (corpus #13) into the committed
  `tools/generated_cache/enzyme_variability.json`, which `build_enzymes()` merges onto
  `meta.enzymes`. The export itself is **committed**, one TSV per gene under
  `tools/data/pharmfreq/` (small and freely redistributable, unlike the books), and the cache
  pins each file's sha256, so this corpus declares `tsv_dir` instead of `pages_dir`: there is no
  page, because the quote is composed out of the table and finding it on a page we also wrote
  would prove nothing. `check_data.py` family 12 rebuilds every profile and quote from the pinned
  files instead, which is the same guarantee and, unlike every other corpus's gate, one that runs
  on a plain clone. The reader both ends share lives in `data_generators/pharmfreq.py`. One node per isoform (kind `enzyme_variability`) whose quote carries the whole
  profile, like an Allen density profile, so the verbatim gate covers the numbers the panel shows.
  Deterministic, no judge, no network. Reports the isoforms it could not map (UGT1A1, which names
  no isoform we model) and the two the source omits (CYP3A4, CYP1A2), so a gap never reads as
  "does not vary". `--zip` points at another export, `--dry-run` writes nothing.
- `tools/fetch/fetch_cpic.py` — stdlib, network (one-shot), author-side. Pulls CPIC's PostgREST API
  (`api.cpicpgx.org/v1`, no key) for the level A/B gene-drug pairs on our roster and writes the
  committed export `tools/data/cpic/cpic_recommendations.json` (corpus #15) plus the pinned
  `tools/generated_cache/cpic_guidance.json`, which `_drug_pgx` in `generate_data.py` reads into each
  drug's `pgx` block. Same committed-export shape as `fetch_pharmfreq.py` above and the same family-12
  re-derivation gate, through the shared reader `data_generators/cpic.py`. It imports only genes that
  corpus #13 has a frequency profile for, keeps a two-gene row only where the other gene is a normal
  metabolizer (recorded as `assumes`), drops CPIC's uncertainty phenotypes, and picks one population
  per pair out of `general` / `adults` / `PHT naive`. Every exclusion is **printed on each run**
  (out-of-roster pairs, genes with no profile, pairs CPIC has levelled but written no guideline for,
  pairs whose only populations this panel cannot read), so no gap passes as covered. Deterministic
  after the fetch, no judge: the API's own strings are the quotes (`extraction: "code"`). Re-running it
  is how you refresh the corpus; the pin makes generation fail loudly if the export moves without it.
- `tools/fetch/fetch_clinpgx.py` (stdlib, network once, author-side): ClinPGx's clinical-annotations zip (corpus #20) filtered to our receptor/target genes at levels 1A-3, written as the committed export `tools/data/clinpgx/clinical_annotations.json` + its pin `tools/generated_cache/clinpgx_variants.json`; read by `data_generators/clinpgx.py` (`receptor_variant` nodes) and re-derived by check_data family 12. `--refresh` re-downloads, `--dry-run` reports.

### Book heading resolution

- `tools/fetch/fetch_quote_headers.py` — stdlib, offline, author-side. Resolves, for every emitted quote
  from a **book** corpus (a paged corpus whose page tree has an `INDEX.md`), the **trail** of headings it
  sits under, into the committed `tools/generated_cache/quote_headers.json` ({quote_id: [outermost, ...,
  innermost]}), which `quote_table` merges onto the quote nodes by id. Reads the emitted `quotes.jsonl`, so
  the order is generate -> fetch -> generate (like `recheck_quotes.py`). Two resolvers: `OutlineIndex` takes
  the ancestor chain of the `INDEX.md` outline entry covering the page (Kandel, Stahl Essential, Carlat,
  Nieuwenhuys), `StahlPages` reads Stahl's page text (which has no usable outline) for the monograph title,
  the positional subsection, and the **section** from a subsection -> section majority vote over all 158
  monographs, because the extraction drops ~30 section headings and the nearest surviving one then leaks in
  from the previous section or drug. Capped to `MAX_TRAIL` levels. A book missing from the checkout keeps
  its cached trails rather than dropping them. No LLM. `--dry-run` reports without writing. See docs/PROVENANCE.md ("Where a quote sits").

### Drug metabolism (CYP roles)

- `tools/fetch/fetch_cyp_worklist.py`: stdlib, offline. The `drug_enzymes` worklist builder, and the
  only pass that reads a corpus. Pulls Stahl's per-drug `Pharmacokinetics` bullets out of the
  author-side dump and the drugbox `Metabolism` row plus every isoform-naming sentence out of the
  stored English Wikipedia article, confirms each **verbatim** on a real page (Stahl's inside that
  drug's own `INDEX.md` range), and writes `tools/generated_cache/cyp_worklist.json`: per drug, a
  numbered candidate list plus the enzyme/role/strength vocabularies the judge must answer in. It
  applies **no veto** and states no role: a negation or a sentence about another molecule is the
  judge's to reject. `--only <ids>` scopes. See docs/DRUGS.md Drug metabolism.
- `tools/fetch/fetch_cyp.py` and `tools/lib/corpora/wikipedia.py`: **libraries, not scripts**,
  imported by the worklist builder. Each knows how one corpus is shaped (Stahl: monograph page
  spans, the dump's `Pharmacokinetics` answers, the isoform vocabulary, the verbatim gate that
  shortens a bullet once when a running header or a hyphenated line break defeats it; Wikipedia:
  which file an article lives in including redirect `PAGE_ALIASES`, the sentence split, the
  reference-list skip, the drugbox row). Neither decides whether a sentence supports a role.
- `tools/sourcing/apply_cyp_sources.py` — quote-gates the judged CYP roles
  (`cyp_judged.json`, a candidate **index** per row, never a quote string) and is the **sole
  writer** of both `tools/generated_cache/drug_enzymes.json` (Stahl) and
  `drug_enzymes_wikipedia.json` (corpus #9). Five gates: the drug and the index resolve; the
  (enzyme, role, strength) triple is in the vocabulary; the quote names the isoform the row
  claims; the quote is verbatim on the cited page under `lib.quote_match.normalize_for_match`; one
  (enzyme, role) pair per drug per corpus, keeping the reading that carries a strength tier.
  Stdlib, author-side (the gate needs the gitignored corpora). `--dry-run` reports, `--verbose`
  lists every rejected row. See docs/DRUGS.md Drug metabolism. Every source it writes is stamped `llm` with the model that
  judged the file (`--llm`, default `opus`).

### Binding Ki (PDSP #5, GtoPdb #11)

- `tools/fetch/fetch_ki.py` — parses the PDSP Ki CSV (`data_sources/books/pdsp_ki/`, author-side) into
  per-drug binding affinities; `--apply` writes each `ki` + adds median-stronger `affinity_only`
  bindings. A curated `ALIAS` map recovers drugs PDSP lists under a related compound. See docs/DRUGS.md Drugs.
  **When adding one drug, scope every writer with its `--only`** (`fetch_ki.py`, `fetch_gtopdb_ki.py`,
  `fetch_molecules.py`, `fetch_brand_names.py`): an unscoped refresh legitimately rewrites every drug
  whose upstream rows moved, burying the one-drug change. A scoped run merges into the committed cache.
- `tools/fetch/fetch_gtopdb_ki.py` — stdlib. Downloads GtoPdb's bulk ligand-interaction CSV
  (`data_sources/gtopdb/interactions.csv`, author-side), joins it to our drugs by name (an HTML-stripping
  `norm` + a curated `LIGAND_ALIASES`) and to our targets by **case-folded gene symbol** (reusing
  `lib.gene_maps.RECEPTOR_GENES` + `TARGET_GENES`, plus `EXTRA_TARGET_GENES` for the ionotropic subunit
  families), and writes one quotable row line per interaction into `data_sources/gtopdb/pages_ki/<slug>.md`
  (corpus #11 `gtopdb_ki`) + the proposals into `tools/generated_cache/gtopdb_ki.json`. Only a pKi/pKd
  becomes a Ki (`10^(9-pKi)` nM); a functional potency rides along as the direction's citation. No judge:
  the CSV's own `type` column is the direction. See docs/PROVENANCE.md (corpus #11).
- `tools/sourcing/apply_gtopdb_ki.py` — merges those proposals into `drugs_data.jsonl` (a drug's bindings and each non-modeled active metabolite's): confirm-only (never
  adds a target), PDSP-first (a `ki` only where there is none), and a `provisional_action` only on an
  `affinity_only` binding, so a stated direction always wins. A disagreement is reported, split into
  compatible refinements (`COMPATIBLE`) and genuine conflicts, never auto-resolved. Re-gates every quote
  through `lib.quote_match.normalize_for_match`; idempotent (`strip_previous` rebuilds its own prior write).

### Wikipedia articles and brand names (#9, #10)

- `tools/fetch/fetch_wikipedia_pharmacology.py` — `uv run` (deps: beautifulsoup4). Fetches a drug's
  English Wikipedia article pinned to its revision id, stores the whole page author-side
  (`data_sources/wikipedia/raw/<slug>.html` + `pages/<slug>.md`, corpus #9 `wikipedia_pharm`), and mines
  the pharmacodynamics binding table for a per-target Ki (adaptive multi-row-header grid + fuzzy target
  resolution reusing `fetch_ki`'s `norm`/`parse_ki`/`NAME_PATTERNS`). A Ki source's `quote` is the
  verbatim table row, so the normal quote gate applies. Preview by default; `--json`, `--no-fetch`. Fills
  the Ki gap where PDSP has none (e.g. alpha1, non-psychiatric agents). See docs/DRUGS.md Drugs.
- `tools/fetch/fetch_brand_names.py` — `uv run` (deps: beautifulsoup4). Resolves each drug's French
  Wikipedia article via the EN article's langlinks (reusing `fetch_wikipedia_pharmacology.py`), stores it
  author-side (`data_sources/wikipedia/pages_fr/<slug>.md`, corpus #10 `wikipedia_fr`), and writes a
  candidate trade-name-sentence worklist (`tools/generated_cache/brand_worklist.json`) for the LLM that
  extracts each drug's ordered European/French brands. EN is used only for the langlink (its pages are not
  refetched, so no corpus #9 Ki gate can drift). See docs/PROVENANCE.md (corpus #10).
- `tools/sourcing/apply_brand_names.py` — merges the LLM-extracted eu/fr brands (`brand_judged.json`) into
  `drugs_data.jsonl`, quote-gating each name verbatim on its FR page and tagging the first `fr`, the rest
  `eu` (na from Stahl is kept). Idempotent. See docs/PROVENANCE.md (corpus #10).

### Half-life and time to peak (Stahl, DailyMed #14, BDPM #16, Europe PMC #17)

- `tools/fetch/fetch_pharmacokinetics.py` — stdlib. Scans each drug's Stahl page span (from `INDEX.md`)
  for elimination half-life + active-metabolite lines, pre-parsing durations to hours, into a candidate
  worklist (`tools/generated_cache/pk_worklist.json`) for the LLM that extracts each drug's T½ +
  metabolites. See docs/DRUGS.md Drugs (Half-life + active metabolites).
- `tools/sourcing/apply_pharmacokinetics.py` — merges the LLM-extracted T½ + metabolites
  (`pk_judged.json`) into `drugs_data.jsonl`, quote-gating each value verbatim on its Stahl page and
  resolving a metabolite's `drug_id` by norm-name match (never self-link). Sole writer of
  `half_life`/`metabolites`; merges by metabolite name, accepts `wikipedia_pharm` quotes, `--only <drug ids>` scopes
  (use it: a full rerun is not a no-op). See docs/DRUGS.md Drugs (Half-life + active metabolites).
- `tools/fetch/fetch_dailymed.py` — stdlib, network, resumable. Corpus #14 fetcher: searches DailyMed
  for each drug's US prescribing label, picks ONE (plain-oral forms preferred, since a modified-release
  product states a real Tmax for a different product; the first whose pharmacokinetics section actually
  names a peak wins), and stores `data_sources/dailymed/raw/<setid>.xml` +
  `data_sources/dailymed/pages/<setid>.md` (the 12.3 / Clinical Pharmacology text only) plus the chosen
  label per drug in `generated_cache/dailymed_labels.json`. States no claim: it only puts pages on disk
  for `fetch_tmax.py` to read. See docs/PROVENANCE.md (corpus #14).
- `tools/fetch/fetch_bdpm.py` — stdlib, network. Corpus #16 fetcher: downloads the BDPM (French public drug database) tables, joins each drug to its single-active marketed products by exact INN, picks ONE plain systemic RCP and stores its section 5.2 as `data_sources/bdpm/pages/<cis>.md`, plus the chosen RCP and the French brand names per drug in `generated_cache/bdpm_labels.json`. States no claim: `fetch_tmax.py` / `fetch_half_life.py` read the pages, `apply_brand_names.py --bdpm` writes the brands (code read, no judge). See docs/PROVENANCE.md (corpus #16).
- `tools/fetch/fetch_europepmc.py`: stdlib, network (`www.ebi.ac.uk`). Corpus #17 fetcher: stores the Europe PMC abstract of each paper in its hand-listed `PAPERS` registry (PMID -> the claim it was added for) as `data_sources/europepmc/pages/<pmid>.md`. States no claim. `--ki-prose` follows a drug article's own citations instead: for every binding with no Ki, it stores the abstracts of the papers each affinity-stating paragraph of the drug's EN article cites, and writes `tools/generated_cache/ki_prose_worklist.json` (each line stating a Ki / Kd value, or a row of a Ki table, no verdict). Every stored paper with an open-access copy also gets its full text (`raw/<pmid>.xml` + the flattened body and tables after a `## Full text` marker, licence in the header). The LLM picks by index into `tools/generated_cache/ki_prose_judged.json`; `tools/sourcing/apply_ki_prose.py` (`--dry-run`) gates + writes the Ki (confirm-only, Ki-less bindings only, Ki / Kd only, value written in the quote), then run `recheck_quotes.py build --unjudged` + an independent judge + `apply` (see docs/SOURCING_GAPS.md 3c). See docs/PROVENANCE.md (corpus #17).
- `tools/fetch/fetch_tmax.py` — stdlib. Offers, per drug, every line of its own stored Wikipedia article
  (#9), Stahl monograph (#1) and DailyMed label (#14) that names a PEAK and carries a duration, pre-parsed into every
  `{hours, hours_max?}` it states, into `tools/generated_cache/tmax_worklist.json`. States no verdict of
  its own: the LLM pass answers only which candidate **index** is the drug's own oral time-to-peak. The
  drugbox is deliberately not read (no Tmax row; its `Onset of action` is clinical onset). Importable as
  a library, which is how the applier re-derives what was offered. See docs/DRUGS.md Drugs (Time-to-peak).
- `tools/sourcing/apply_tmax.py` — stdlib. Merges `tmax_judged.json` into `drugs_data.jsonl` behind six
  gates (drug in the dataset, drug offered by a fresh `fetch_tmax.build()`, index resolves, the judged
  hours equal a duration the quote states (re-parsed here, so the model supplies no number),
  `MAX_TMAX_HOURS` = 24 h oral plausibility, quote verbatim on its page). Idempotent, sole writer of
  `tmax`/`tmax_sources`; writes no `llm` stamp, so `recheck_quotes.py` must run after it.

### Drug history, origin and approvals (Drugs@FDA #18)

- `tools/fetch/fetch_drug_history.py` — stdlib, offline. Offers, per drug, every sentence of the lead and
  history-like sections (EN History / Society and culture / Legal status, FR Histoire / Historique / ...)
  of its stored EN and FR Wikipedia articles that carries a year and an approval or withdrawal word (plus
  the sentence before it as `context`), into `generated_cache/drug_history_worklist.json`, with no verdict
  and with `instructions` (a withdrawal counts only for a marketed medicine). See docs/DRUGS.md Drugs (Regulatory history).
- `tools/sourcing/apply_drug_history.py` — stdlib. Merges `drug_history_judged.json` (per drug
  `{approval: {index, year, country?, agency?} | null, withdrawals: [{index, year, country, reason}]}`)
  into `drugs_data.jsonl` behind gates (drug offered, index resolves, year in the quote, approval /
  withdrawal wording, no food / salt-substitute context on a withdrawal, every vocabulary value attested by the quote, quote verbatim on its page).
  Idempotent, sole writer of `withdrawals` and of a Wikipedia `first_approval`/`first_approval_sources`
  (a Drugs@FDA one is kept unless a judged approval replaces it); writes no `llm`
  stamp, so run `recheck_quotes.py build --kinds drug_first_approval,drug_withdrawals` after it.
- `tools/sourcing/apply_drug_holders.py` — stdlib, offline, author-side. Code-read (no judge, no recheck): rebuilds every drug's `holders[]` (kind `drug_holders`, one node per (drug, market)) from the Drugs@FDA page title of the first-approval NDA (us) and the `holder:` header line of the BDPM brand product pages (fr). Run after `fetch_drugsfda.py` / `fetch_bdpm.py`. See docs/DRUGS.md Drugs (Regulatory history).
- `tools/fetch/fetch_originator.py` — stdlib, offline. Offers, per drug, the lead / history sentences of its stored EN article naming who discovered / synthesized / developed it, and, per originator company article listed in `COMPANY_ARTICLES` (fetched once with `fetch_wikipedia_pharmacology.py --title`), its Headquarters / Country rows and its country / successor sentences, into `generated_cache/originator_worklist.json`, no verdict.
- `tools/sourcing/apply_originator.py` — stdlib. Merges `originator_judged.json` (`drugs: {id: {index, name, company}}`, `companies: {slug: {country: {index, country}, now: {index, name}}}`) behind gates (index resolves, name verbatim in an originator sentence, company lists that name, country attested, `now` in a successor sentence, quote verbatim on its page); sole writer of `originator*`; no `llm` stamp, so run `recheck_quotes.py build --kinds drug_originator,drug_originator_country` after it.
- `tools/fetch/fetch_drugsfda.py` — stdlib, network once (`download.open.fda.gov`; `--refresh` re-downloads). Corpus #18: reads openFDA's bulk Drugs@FDA export and picks, per drug, the earliest original approval among the NDAs whose single active ingredient is that drug (salt words dropped, `FDA_NAMES` for US names, stereo-aware), only when that NDA is classed a new molecular entity and no matching NDA is undated. Writes `data_sources/drugsfda/pages/<appl>.md` and `generated_cache/drugsfda_approvals.json`. No judge (code extraction).
- `tools/sourcing/apply_drugsfda.py` — stdlib. Fallback writer of a first **US** approval (`national: true`) onto a drug with none (or its own earlier one), gated (year in the quote, quote verbatim on its page); replaces a Wikipedia approval only when the FDA date is strictly earlier (earliest dated approval wins, `history.earliest_wins`, which `apply_drug_history.py` honours too, so run order does not matter); no `recheck_quotes.py` needed.

### Physicochemistry, workup and TDM (#19, #21, #22, #24)

- `tools/fetch/fetch_physchem.py` stdlib, network (`pubchem.ncbi.nlm.nih.gov`, the B3DB TSV once from GitHub), author-side. Corpora #21 PubChem + #22 B3DB: reads each drug's CID off its stored Wikipedia drugbox, writes `data_sources/pubchem/pages/<cid>.md` (XLogP3, TPSA) and `data_sources/b3db/pages/<cid>.md` (BBB label + logBB rows, joined by CID else exact name, InChI-guarded), then `generated_cache/physchem.json`. `--only <ids>` scopes, `--refresh` re-downloads. No judge (code extraction); follow with `python tools/fetch/stamp_fetch_dates.py` and `python tools/generate_data.py`. See docs/DRUGS.md (Physicochemistry and brain entry).
- `tools/fetch/fetch_bdpm_rcp.py`: stdlib, offline for drugs with a French product, author-side. Corpus #24 `bdpm_rcp`: per drug, picks the princeps (else #16's product) with an RCP 4.4 and writes `data_sources/bdpm/pages_rcp4/<cis>.md` (sections 4.2 / 4.3 / 4.4) from the freshest copy on disk (#16's `raw/` or `../justelesRCP/data/rcp/`, else EMA's SmPC in `../justelesRCP/data/eu/` for a centrally authorised drug, read only; `--justelesrcp` points elsewhere), plus `generated_cache/bdpm_rcp_labels.json`; prints the drugs with no page. A drug with no CIS product at all falls back to its EPAR found by name (`tools/fetch/fetch_ema_epar.py`: EMA's two EPAR JSON reports, cached in `data_sources/ema/raw/`; the SmPC PDF downloaded once and converted with justelesRCP's `src/ema_pdf.py`, so run `uv run --with pymupdf python tools/fetch/fetch_bdpm_rcp.py` when a new one is needed; `--offline` uses only stored SmPCs, `--refresh-ema` re-pulls the reports and SmPCs) into `pages_rcp4/EMEA-H-C-<n>.md`, the chosen EPAR recorded under `ema` in the cache; the run prints which drugs it reached that way. Then `python tools/fetch/fetch_workup.py` (worklist of the 4.2 / 4.3 / 4.4 lines naming a test, no verdict; excipient notices dropped) -> one LLM pass -> `generated_cache/workup_judged.json` (`{drug: [{index, test, timing, condition?}]}`, every offered drug keyed, `[]` = nothing, so `apply_workup.undecided` and `test_workup.JudgedCoverageTest` catch a drug nobody read) -> `python tools/sourcing/apply_workup.py --dry-run`, then real (seven gates, sole writer of `workup.json`) -> `python tools/fetch/stamp_fetch_dates.py` -> `python tools/generate_data.py` -> `python tools/sourcing/recheck_quotes.py build --kinds drug_workup --unjudged`, judge, `apply --llm opus` -> `generate_data.py` again. See docs/DRUGS.md (Pre-prescription workup).
- `tools/fetch/fetch_agnp_tdm.py`: uv script (pymupdf), offline, author-side. Corpus #19: reads the AGNP TDM guideline's Table 5 (therapeutic range, alert level, TDM level) and Table 1 (substrate isoforms) by cell rectangle off `data_sources/books/agnp_tdm_2026/a-2860-7861.pdf`, gates each row quote on `pages/<n>.md`, writes `generated_cache/agnp_tdm.json` and the drug -> pages table of that book's `INDEX.md`. No judge (code extraction); `generate_data.py` reads the cache via `data_generators/tdm.py`.

### Prodrugs and metabolite bindings

- `tools/fetch/fetch_prodrug_worklist.py` — stdlib, offline. Offers every prodrug / inactive sentence of
  each drug's stored EN Wikipedia article into `generated_cache/prodrug_worklist.json`, with no verdict
  (`--only` merges). See docs/DRUGS.md Drugs (Prodrugs).
- `tools/sourcing/apply_prodrug.py` — stdlib. Merges `prodrug_judged.json` (per drug `{index, metabolite,
  drug_id|null}`) into `drugs_data.jsonl` behind gates (drug offered, index resolves, prodrug wording,
  metabolite named, quote verbatim on its page); sole writer of `prodrug`/`prodrug_sources`, adds the
  metabolite when missing and drops the drug's own bindings (printed). Writes no `llm` stamp, so run
  `recheck_quotes.py build --kinds drug_prodrug` after it.
- `tools/fetch/fetch_metabolite_bindings.py` — `uv run` (deps: beautifulsoup4). Reuses
  `fetch_wikipedia_pharmacology` as a library to mine each non-modeled active metabolite's own English
  Wikipedia article (an allow-list of confirmed own-articles; the rest fall back to the parent article
  for prose only, filtered to sentences naming the metabolite) into `metabolite_bindings_worklist.json`
  (Ki-table rows + candidate action sentences) for the LLM pass. See docs/DRUGS.md Drugs.
- `tools/sourcing/apply_metabolite_bindings.py` — `uv run` (deps: beautifulsoup4). Merges the
  LLM-extracted metabolite bindings (`metabolite_bindings_judged.json`) into `drugs_data.jsonl`:
  quote-gates each action sentence, resolves the target, attaches a Ki (PDSP measured preferred, else
  the Wikipedia table value), and adds every remaining Ki-table target as `affinity_only`. Sole writer of
  a metabolite's `bindings`; `--only <parent drug ids>` scopes (use it: a full rerun clobbers later
  direction / Ki writes). See docs/DRUGS.md Drugs.

### Binding directions and UNKNOWN searches

- `tools/fetch/fetch_binding_directions.py`: `uv run` (deps: beautifulsoup4, only because it imports
  `fetch_metabolite_bindings`; no HTML is parsed). Offline. The binding-direction worklist builder: for
  every drug with an `affinity_only` binding it reads the stored English Wikipedia article
  (`lib.corpora.wikipedia.page_for`, which owns the redirect aliases) and offers the prose lines naming
  one of that drug's affinity-only targets, with **no verdict of its own**, into
  `tools/generated_cache/binding_directions_worklist.json`. `--only <ids>` scopes. See docs/DRUGS.md Drugs
  (Binding directions).
- `tools/fetch/fetch_binding_direction_tables.py`: `uv run` (deps: beautifulsoup4). Offline once the
  articles are stored. The other direction input, a **code extraction**: it reuses
  `fetch_wikipedia_pharmacology`'s grid, header detection, target resolver and row text to read the
  `Action` column beside the Ki one, and proposes a direction only where the cell maps **exactly** onto
  `DRUG_ACTIONS` (`Inhibitor`/`Blocker` typed by the target, a `ND` / glyph / percentage / slash reading
  reported and left alone, two rows that disagree skipped), for a target the drug currently binds
  `affinity_only`, into `tools/generated_cache/binding_directions_tables.json`. `--only <ids>` scopes.
  See docs/DRUGS.md Drugs (Binding directions).
- `tools/sourcing/apply_binding_directions.py`: stdlib. Quote-gates the judged directions
  (`binding_directions_judged.json`, a candidate **index** per row, never a quote string) and is the
  **sole writer** of an `action` onto an `affinity_only` binding in `drugs_data.jsonl`. Six gates: the
  drug was offered; the index resolves; the target is a currently affinity-only binding of that drug
  (confirm-only, so nothing is added or revised); the action is in `DRUG_ACTIONS`; the quote names the
  target (`tools/lib/target_aliases.py`, the matcher the fetcher offered it with); the quote is verbatim on
  `data_sources/wikipedia/pages/<slug>.md`. Writes no `llm` stamp (`recheck_quotes.py`'s job).
  Idempotent, `--dry-run`/`--verbose`. **`--tables`** applies the table proposals instead
  (`binding_directions_tables.json`): gates 3, 4 and 6 are the same shared `BindingGate`, there is no index
  to resolve, and gate 5 becomes "the row opens with its target cell and that cell resolves to the
  target claimed" under the fetcher's own resolver; the source is stamped `extraction: "code"`, so this
  input needs no `recheck_quotes.py` pass. Needs beautifulsoup4 on the path for that resolver.
  **`--search`** applies the UNKNOWN search's picks (`binding_directions_search_judged.json`, index
  per site into `binding_directions_search_worklist.json`) through the same `BindingGate`, the citation
  carrying the candidate's own corpus (EN/FR Wikipedia or a Europe PMC abstract) and page; a metabolite
  pick is written once, on its `metabolites_data.jsonl` record. **`--unknown-log`** (run after the recheck) writes
  `tools/generated_cache/unknown_searches.json`: every searched binding still `affinity_only` whose
  search found no direction anywhere, with its per-corpus search record (see docs/PROVENANCE.md, UNKNOWN).
  See docs/DRUGS.md Drugs (Binding directions).
- The UNKNOWN search, end to end (binding directions; the recipe for any kind in
  `unknown.UNKNOWN_REQUIRED_SOURCES`):
  `python tools/fetch/fetch_europepmc.py --binding-search` (network, resumable, ledger
  `tools/generated_cache/europepmc_binding_search.json`, top 5 abstracts per binding stored as corpus #17
  pages) -> `uv run --with beautifulsoup4 tools/fetch/fetch_binding_directions.py --search` (offline,
  builds the worklist over PDSP, GtoPdb, EN + FR Wikipedia and those abstracts, recording what each corpus
  was asked and returned) -> one LLM pick by index -> `apply_binding_directions.py --search` ->
  `recheck_quotes.py build --kinds drug_bindings,drug_metabolite_bindings --unjudged` + an independent
  judge + `apply --llm <model>` -> `apply_binding_directions.py --unknown-log` -> `generate_data.py`.
- `tools/lib/target_aliases.py`: stdlib **library**, imported by both halves above: every name a modeled
  drug target goes by in prose (Greek folded to Latin, separator-tolerant, boundary-strict, so `d2`
  never fires on `CYP2D6` and `alpha2` never absorbs `alpha2A`). One definition, because a gate that
  disagreed with the offer would accept what the worklist could not have shown.

### Binding gaps

- The binding-gap pass (a **new** binding a drug's EN Wikipedia article states, corpus #9), end to end:
  `uv run tools/fetch/fetch_binding_gaps.py` (offline, `--only <ids>`; writes
  `tools/generated_cache/binding_gaps_worklist.json`, drugbox target cells + direction-stating prose
  sentences naming an uncovered target) -> one LLM pass deciding every candidate by index into
  `binding_gaps_judged.json` (`{drug: [{index, target, pick, action | reason}]}`, `_`-prefixed keys are
  metadata) -> `python tools/sourcing/apply_binding_gaps.py --dry-run --verbose` then without
  `--dry-run` (stdlib, sole writer, `--verbose` lists the additions on Stahl drugs, whose own bindings stay untouched) ->
  `generate_data.py` -> `recheck_quotes.py build --kinds drug_bindings --unjudged` + judge +
  `apply --llm <model>` -> `generate_data.py`. `tools/lib/binding_gaps.py` (stdlib library) holds the
  predicates both halves run (negation per clause, stereo relatives, covered targets, Stahl detection).
  See docs/DRUGS.md Drugs (Binding gaps).

### Book corpora (PDF to pages)

- `tools/fetch/pdf_to_pages.py` — splits a PDF into one `<page>.md` per page (the quote-gate text);
  `uv run`, `--layout` for OCR.
- `tools/fetch/build_toc_index.py` — `INDEX.md` from a PDF's embedded TOC (generic). `uv run`.
- `tools/fetch/build_index.py` — Stahl-specific page index (by `THERAPEUTICS` heading). `uv run`.

### README stats, images, git hooks

- `tools/update_readme_stats.py` — rewrites the README `SOURCING_STATS` + `SOURCES_TABLE` blocks
  (and the headline %) from `meta`; `--check` exits 1 if stale (CI). Idempotent.
- `tools/fetch/fetch_molecules.py` — downloads each drug's molecule SVG into `public/data/molecules/`;
  writes `tools/generated_cache/molecules_sources.json`. See docs/VIEWER.md Images.
- `tools/fetch/fetch_structure_images.py` — resolves the *url* of each structure's (and wiki-linked
  circuit's) Wikipedia hero + gallery images into `tools/{structure,circuit}_images_sources.json`
  (`--target structures|circuits|all`); downloads no bytes. See docs/VIEWER.md Images.
- `tools/generated_cache/{molecules,structure_images,circuit_images}_sources.json` — provenance/attribution for
  the fetch tools (the image ones are read by `generate_data.py` offline; not served).
- `tools/git-hooks/` — repo-tracked git hooks (see CLAUDE.md Git hooks).

## Data contract (emitted `public/data/`)

The field list of each emitted file. The viewer reads exactly these shapes; the generator
emits them. Every claim carries its own quote-level source (see docs/PROVENANCE.md);
there is no node-level catch-all `sources` block.

> **Source quotes are externalized.** A quote-bearing source is emitted on the node as a bare
> `{quote_id, provenance}` reference; its immutable excerpt `{id, corpus, page, quote, species?}`
> lives once in the deduplicated `quotes.jsonl` side table (keyed by a content hash, so identical
> excerpts share one entry). The viewer (`js/data.js`) and `check_data.py` both rehydrate each
> reference in memory (merging the excerpt back onto the source) at load, so every shape below that
> shows `sources[{corpus,page,quote,...}]` is the *rehydrated* view; on disk it is `{quote_id,
> provenance}`. Ki sources (no `quote`) and bare wikipedia provenance are not externalized. See the
> serialization pass in `data_generators/quote_table.py` (mirrors the i18n externalize pass).

> **Emitted data is English-only.** Display strings marked `{en,fr}` below are *authored*
> bilingual but serialized as the plain English string; the French is deduplicated into one
> side table, `translations.fr.json` (`{english: french}`, sorted keys), which the viewer
> fetches only in French and looks each English string up in (see docs/I18N.md, the
> externalize pass). So on disk every `name{en,fr}` etc. is just a string.

- `meta.json` — presentation maps + tallies, so the dataset is self-describing (a port needs
  no hardcoded palette): `projection_colors`, `kind_labels`, `group_labels`, `kind_signs`,
  `sign_colors`, `sign_labels`, `system_flow_kinds` (drug target system -> projection kind),
  the receptor maps (`receptor_family_labels` key order = legend family order,
  `receptor_family_colors` = the same families' swatch colours, reusing `projection_colors`
  where the family has a modeled pathway, so a view colouring by transmitter (the simulation's
  receptor bars) matches the 3D scene; `receptor_class_labels`, `synaptic_labels`), the drug maps (`drug_category_labels` key order =
  Drugs legend order, `drug_actions` action->{label,effect}, `drug_effect_colors`,
  `drug_effect_labels`, `drug_targets` = every non-receptor target + every receptor id; a target
  with a direction-flipping `vesicular`/`sign`/`synaptic` flag also carries `polarity_provenance`
  (+ optional `polarity_sources`), its own graded node kind `target_polarity`; a `receptor_group`
  target also carries `subtypes` (its modeled subtype receptor ids, a sourceless taxonomy the
  viewer lists as per-subtype drug dropdowns); a target with an Allen profile carries the same
  `density` object as a receptor; a non-receptor target also carries `gene`, the representative
  HGNC symbol, like a receptor's),
  `enzymes` (metabolic isoform id -> {label, wikipedia}), `enzyme_roles`
  (role -> {label, `direction`: what it does to a co-prescribed substrate's level}) and
  `enzyme_strengths` + `enzyme_reactions` (the chemical step by which an enzyme makes an
  active metabolite; see docs/DRUGS.md Drug metabolism),
  `target_type_labels`/`target_type_colors`, `source_corpora`, `uncertainty_reasons` (the closed
  vocabulary a node's `uncertainty[]` bullets draw from, each `{source, absence, args}`),
  `addon_slots` (the addon-node hook registry, slot -> the node kind whose panel it is in) +
  `addon_sections` (the browse views an addon may anchor instead of a node, key -> label) +
  `addon_displays` + `addon_tones` (tone -> glyph),
  `density_min_reliability` (the
  cross-donor r floor every published profile clears), `provenance_stats` (the sourcing
  tally; see docs/PROVENANCE.md).
- `translations.fr.json` — the deduplicated French side table, `{english: french}` with sorted
  keys, covering every emitted display string whose French differs from its English. Fetched by
  the viewer only in French (English users skip it); a missing key falls back to the English
  string. Written last by `write_artifacts` from the externalize pass (see docs/I18N.md).
- `quotes.jsonl` — the deduplicated source-quote side table, one quote node per line sorted by
  `id` (a `q_<12 hex>` content hash): `id`, `corpus`, `page`, `quote`, optional `species`, optional
  `llm` (the model that extracted+judged the quote, `haiku`/`sonnet`/`opus`; absent = unknown),
  optional `heading` (the trail of book headings the passage sits under, outermost first, derived
  by `fetch/fetch_quote_headers.py`; only the levels it could resolve are present). Every
  node's quote-bearing source references one by `quote_id`; the viewer + `check_data.py` rehydrate
  it at load (see the externalize note above).
- `changelog.json` — the release notes, `{versions: [{version, date, entries[{category,
  text{en,fr}, commits[sha]}]}]}`, newest version first (the order `js/changelog.js` walks to show
  every release since a visitor's last one). Not a node kind: it is editorial prose about the app, carries no
  provenance grade, and is absent from the sourcing tally. Compiled from the authored
  `docs/changelog/<version>/changelog.md` files (see Writing release notes below).
- `structures.jsonl` — `id`, `name{en,fr}`, `base_name{en,fr}` (hemisphere-stripped, legend
  row), `group`, `position`, `color`, `shape_file`, `classification_provenance`, optional
  `wikipedia`(+`_provenance`), optional `structure_image` (hot-linked Wikimedia url, shared by
  both hemispheres) + `structure_image_gallery`.
- `projections.jsonl` — `from`, `to`, `kind`, `label{en,fr}`, `neurotransmitter{en,fr}`,
  `description{en,fr}`, optional `sources[{corpus,page,quote,provenance}]` (from `KANDEL_QUOTES`),
  `bidirectional`, `tentative` (dotted, off-by-default section). `mirror: true` marks a symmetric
  pathway stored **once** (the right-hemisphere record): the consumer reflects it by flipping
  `_R` <-> `_L` on both endpoints (`js/data.js` at load, `check_data.py` before its checks), so the
  file carries no per-side duplicate. Set from the `symmetric` authoring hint (see Projections above).
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
  `ubiquitous:true`, `classification` (`{family,receptor_class,sign,synaptic}` -> each a
  `{grade, sources?}` sub-claim, so a quote grades only the attributes it substantiates), optional
  `location_sources` (`{base:[quote-source]}`, sparse per-region upgrade above `llm`; `"ALL"` =
  the ubiquitous claim), optional `density` (`{reliability, donors, profile:{base:z} sorted
  strongest first, grade, sources}`, ONE graded node for the whole Allen z-score profile, see
  docs/VIEWER.md Expression density), optional `description{en,fr}` + `wikipedia`(+prov), optional
  `gene` (the HGNC symbol, an identifier for the gene-keyed lookup links: NOT a graded node; absent
  only for a stub with no human gene). Empty
  locations + no description = a deliberate stub (listed, not focusable).
- `drugs.jsonl` — `id`, `name`, `categories`, `category_provenance` (+ optional
  `category_sources`), optional `nbn{en,fr}` (+ `nbn_sources`, + `nbn_nonstandard:true` when the
  value is Stahl's class descriptor not a formal NbN), `bindings[]` (each: `target`, `action`,
  optional `effect`/`note{en,fr}`/`tentative`/`sources[{corpus,page,quote,provenance}]`/`ki`
  (measured PDSP affinity)/`affinity_only:true` (Ki but no known direction, panel-only)/
  `uncertainty[]` (each: `kind` (a `meta.uncertainty_reasons` key), optional `args` (the i18n
  sentence's slots), and either `sources[]` or `absence:true`; non-empty = the orange ⚠ badge
  takes the pill over, see docs/PROVENANCE.md)),
  optional `half_life` (`{hours, hours_max?}`, elimination T½) + `half_life_sources[]`,
  optional `tmax` (same shape, time to peak plasma concentration, kind `drug_tmax`) + `tmax_sources[]`,
  optional `formulations[]` (`{release, release_sources, brands?, tmax?, half_life?}`, kind `drug_formulations`, written only by
  `tools/sourcing/apply_formulations.py` after `tools/fetch/fetch_formulation_worklist.py` + one index-pick pass; re-run it after any
  brand / Tmax / T½ applier, see docs/DRUGS.md "Formulations"),
  optional `first_approval` (`{year, country?, agency?}`, kind `drug_first_approval`) +
  `first_approval_sources[]`, optional `withdrawals[]` (`{year, country, reason, sources[]}`, kind
  `drug_withdrawals`; ids from `data_generators/history.py`, written by `apply_drug_history.py`),
  optional `holders[]` (`{market, names[], sources[]}`, kind `drug_holders`, written by `apply_drug_holders.py`),
  optional `originator` (`{name, now?}`, kind `drug_originator`) + `originator_sources[]` + `originator_now_sources[]`
  and `originator_country` + `originator_country_sources[]` (kind `drug_originator_country`; written by `apply_originator.py`),
  optional `therapeutic_range` + `alert_level` (+ their `*_sources[]`, kinds `drug_therapeutic_range` /
  `drug_alert_level`, emitted from `generated_cache/agnp_tdm.json`, never authored),
  optional `prodrug: true` + `prodrug_sources[]` (kind `drug_prodrug`, written by `apply_prodrug.py`;
  a prodrug carries no `bindings`, its metabolite does),
  optional `constituents[]` (names) + `constituents_sources[]` for a salt with an INN of its own (kind
  `drug_constituents`, hand-authored; no `bindings`, the viewer borrows its modeled constituents'),
  optional
  `enzymes[]` (each: `enzyme` (a `meta.enzymes` key), `role`, optional `strength`, `sources[]`;
  one node per (enzyme, role) pair, kind `drug_enzymes`, merged in from the committed
  `generated_cache/drug_enzymes.json` + `drug_enzymes_wikipedia.json`, never authored),
  `metabolites[]` (each a reference `{id, sources[]}` into `metabolites.jsonl`, the sources being
  "<id> is an active metabolite of this drug"; optional `formed_by[]` (each: `enzyme`, optional
  `reaction` (a `meta.enzyme_reactions` key), `sources[]`), one node per (parent, metabolite, enzyme),
  kind `drug_metabolite_enzyme`, hand-curated in `data_generators/quotes/metabolism.py`),
  optional `wikipedia`(+prov), optional `structure_image` (vendored `data/molecules/<id>.svg`,
  only when the file exists), `focusable`. No drug-level source: provenance is per-claim (see
  docs/PROVENANCE.md).
- `metabolites.jsonl`: one record per active-metabolite **molecule** (authored in
  `tools/data/metabolites_data.jsonl`, written by the PK / prodrug / metabolite-bindings appliers via
  `drugs_io.attach_metabolite`): `id`, `name`, optional `drug_id` linking a modeled drug, optional
  `half_life`(+`half_life_sources`), optional `bindings[]` for a non-modeled metabolite (same shape as a
  drug binding, kind `drug_metabolite_bindings`, counted once however many drugs reference the record).
- `addons.jsonl` — **addon nodes**: a sourced annotation that carries its own insertion point.
  `id`, `owner_kind` (`drug`/`receptor`/`target`/`structure`/`section`), `owner` (that node's
  id; a structure anchors its hemisphere-less *base*, a `section` anchors a `meta.addon_sections`
  key rather than a node), `slot` (a `meta.addon_slots` key), `display`
  (a `meta.addon_displays` entry), `tone` (a `meta.addon_tones` key), optional `title{en,fr}`,
  `text{en,fr}` (the claim), `sources[{corpus,page,quote,provenance}]`. Tally kind `addons`.
  Authored in `data_generators/addons.py`; the vocabularies are closed, and both the generator
  and `check_data.py` reject an unknown slot / display / tone or an anchor that names no real
  node (an addon in a slot nothing draws would ship silently invisible).
- `molecules/<id>.svg` — vendored per-drug structure diagrams (`fetch_molecules.py`). Structure
  illustrations are NOT vendored (hot-linked, see docs/VIEWER.md Images).

### Geometry

Geometry (`data/shapes/<name>.json`): one file per distinct *form*. L/R pairs share a single
right-side file; the left member sets `mirror:true` on its structure record and the viewer
reflects it across x. Three types:
- `blob` `{radii, seed, detail, noise, + optional octaves/ridged/frequency/aniso/
  clip/clip_planes}` — a gradient-noise-deformed ellipsoid.
- `curve` `{points, profile, seed, noise, radial/tubular_segments}` — a
  round-capped tapered tube swept along a spline (caudate; brainstem levels
  midbrain/pons/medulla).
- `composite` `{parts:[...]}` — sub-shapes (each optional offset/scale/rotate)
  merged into one mesh (cerebellum = 2 hemispheres + vermis). The `sdf` type (SDF atlas,
  under `geometry_refinements/`) is documented there; see CLAUDE.md's geometry note.
