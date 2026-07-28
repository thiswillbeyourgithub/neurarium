# Authoring & data tooling

Runbooks for editing the dataset and refreshing external assets, plus the reference
for **what each tool is** (Tool reference, below) and the **emitted data contract**
(Data contract, below). Both moved here from [`../CLAUDE.md`](../CLAUDE.md) to keep that
file terse; CLAUDE.md keeps the viewer/runtime map and the non-obvious rules. Author-side
corpus locations are in `CLAUDE.local.md`.

## Changing the data

1. Edit the relevant list in `generate_data.py` (or `tools/data/drugs_data.jsonl` for drugs).
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
   which rewrites `drugs_data.jsonl`'s `ki` annotations + `affinity_only` bindings.
5. Commit the generator change + the regenerated artifacts together.

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
3. **PDSP Ki**: re-download the whole-DB CSV from
   `https://pdspdb.unc.edu/databases/kiDownload/download.php` over
   `data_sources/books/pdsp_ki/KiDatabase.csv` (author-side; see that dir's `README.md`), then
   `python tools/fetch/fetch_ki.py --apply` to rewrite `drugs_data.jsonl`'s `ki` + `affinity_only`.
4. **GtoPdb ligand interactions** (the `gtopdb_ki` Ki fallback + the curated directions for
   `affinity_only` bindings): `python tools/fetch/fetch_gtopdb_ki.py` re-downloads the bulk
   `interactions.csv` and rebuilds `data_sources/gtopdb/pages_ki/` (author-side) +
   `tools/generated_cache/gtopdb_ki.json`, then `python tools/sourcing/apply_gtopdb_ki.py`
   quote-gates + merges into `drugs_data.jsonl`. Run it **after** `fetch_ki.py`, since it only
   fills what PDSP left empty. See CLAUDE.md Source provenance (corpus #11).
5. **GtoPdb receptor expression** (the `receptor_locations` sources): `python
   tools/fetch/fetch_gtopdb.py` re-pulls each receptor's tissue comments (caches to
   `data_sources/gtopdb/`, author-side), then run the confirm-only judge over
   `data_sources/gtopdb/worklist.json` and `python tools/sourcing/apply_location_sources.py --judged <f>`
   to merge new `verified` sources into `tools/generated_cache/location_sources.json`. See CLAUDE.md Source provenance (corpora #7/#8).
6. **Allen AHBA expression** (the `target_locations` + residual `receptor_locations`
   sources): `python tools/fetch/fetch_allen.py` re-pulls each donor's microarray PACall (caches
   to `data_sources/allen/`, author-side; ~2GB across donors), then `python
   tools/sourcing/apply_location_sources.py --corpus allen` merges the deterministic `verified`
   sources (no judge) into `tools/generated_cache/location_sources.json`. See CLAUDE.md Source provenance (corpora #7/#8).
7. **Allen AHBA expression density** (the `receptor_density` + `target_density` profiles): the same
   `fetch_allen.py` run also z-scores each gene's microarray intensity per region and writes
   `data_sources/allen/density.json` (pass `--skip-density` to opt out of the heavy
   MicroarrayExpression read), then `python tools/sourcing/apply_expression_density.py` re-gates each
   profile quote and writes `tools/generated_cache/expression_density.json`. See CLAUDE.md Expression density.
8. **GtoPdb target classification** (the `receptor_class` + `sign` + non-receptor `targets`
   sources): `python tools/fetch/fetch_gtopdb_class.py` pulls each target's `type` +
   transduction table (caches to `data_sources/gtopdb/pages_class/`, author-side, +
   `tools/generated_cache/gtopdb_class.json`), then `python
   tools/sourcing/apply_classification_sources.py` maps + quote-gates + merges the confirm-only
   `verified` sources (no judge) into `tools/generated_cache/classification_sources.json`. See
   CLAUDE.md Source provenance (corpus #12).
9. **Drug metabolism** (the `drug_enzymes` rows): `python tools/fetch/fetch_cyp.py` re-reads Stahl's
   per-drug `Pharmacokinetics` block into `tools/generated_cache/drug_enzymes.json`, then `python
   tools/fetch/fetch_cyp_wikipedia.py` does the same over the stored English Wikipedia articles
   (`data_sources/wikipedia/pages/`, corpus #9) into
   `tools/generated_cache/drug_enzymes_wikipedia.json` for the drugs Stahl has no monograph for.
   Both are offline greps behind the verbatim quote gate (no LLM); `generate_data.py` merges them
   Stahl-first. A drug whose article is not stored yet needs `uv run
   tools/fetch/fetch_wikipedia_pharmacology.py --drug <id>` first. See CLAUDE.md Drug metabolism.
10. `python tools/generate_data.py` — regenerate `public/data/` from all of the above.
11. `python tools/update_readme_stats.py` — refresh the README sourcing table
   (CI runs it `--check`).

Panel **descriptions** need no refresh script: each fetches the current Wikipedia lead
at runtime (`js/wiki.js`), so they stay current on their own.

## Tool reference

What each authoring / fetch / check script in `tools/` is (one line each). The dev/runtime
tooling (`serve.py`, `shot.py`, `demos/`) is also summarized in `../CLAUDE.md` (Running,
Screenshots).

- `generate_data.py` — single source of truth for the anatomy (stdlib-only, offline):
  defines every region/projection/receptor once, emits the artifacts below. Drugs are the
  exception (authored in `tools/data/drugs_data.jsonl`, read by `_load_drugs`). Display strings are
  `{en,fr}` via `_t()` (see CLAUDE.md I18n).
- `tools/data/drugs_data.jsonl` — the authored drug dataset (from Stahl 8th ed.), one compact
  JSON object per line, read by `_load_drugs`, emitted to `data/drugs.jsonl`. Edit to add/change a drug.
- `tools/data_generators/` — pure-data modules imported by `generate_data.py`: `drugs.py`,
  `provenance.py` (also houses the sourcing-tally helpers `_GRADE_RANK`/`_strongest_grade`/
  `_binding_grade` + `_provenance_stats`, which reduce the emitted nodes to `meta.provenance_stats`),
  `i18n.py`, `quote_table.py` (the serialization-time source-quote externalize pass -> `quotes.jsonl`,
  mirroring the i18n externalize), and the `receptors/` subpackage (one module per neurotransmitter
  family, e.g. `serotonergic.py`, each exposing `ENTRIES`; `__init__.py` concatenates them into
  `RECEPTORS` in the original order), the `regions/` subpackage (one module per anatomical `group`,
  e.g. `cortex.py`/`basal_ganglia.py`, each exposing `PAIRED` + `MIDLINE`; `__init__.py` concatenates
  them into `PAIRED`/`MIDLINE` in the original order), and `geometry.py` (the shared cortical-dome SDF
  helpers, e.g. `_cortex_lobe_entry` + `MIDLINE_GAP`, plus the pure geometry math helpers
  `_scale_sdf`/`_scale_triple`/`_directional_extent`/`_bisecting_clip_planes`, imported by
  `regions/cortex.py` and `generate_data.py`),
  and `connectivity.py` (the three connectivity node literals `PROJECTIONS`/`CIRCUITS`/`PROJECTION_GROUPS`
  plus the `_KQ_*`/`_SG_*` pathway quote-source constants they cite; the shared `_kandel`/`_nieuwenhuys`/`_stahl_ess`
  quote constructors live in `provenance.py`), and `presentation.py` (the presentation maps emitted
  into `meta.json`: the colour/flow maps `PROJECTION_COLORS`/`KIND_TO_SIGN`/`SIGN_COLORS`/`SYSTEM_FLOW_KINDS`,
  the label maps `SIGN_LABELS`/`GROUP_LABELS`/`RECEPTOR_FAMILY_LABELS`/`RECEPTOR_CLASS_LABELS`/`SYNAPTIC_LABELS`,
  plus the per-structure `WIKIPEDIA` link table; a dependency-free leaf), and the `quotes/` subpackage (verified quote registries by
  corpus: `kandel.py` = `PROJECTION_QUOTES` + `STRUCTURE_QUOTES` (Kandel/Nieuwenhuys anatomy, cites the
  connectivity `_KQ_*`); `stahl_essential.py` = `STAHL_ESSENTIAL_RECEPTOR_QUOTES`/`STAHL_ESSENTIAL_TARGET_QUOTES`/
  `RECEPTOR_ATTR_QUOTES`/`RECEPTOR_CLASSIFICATION_COVERAGE`/`CLASSIFICATION_ATTRS`/`TARGET_POLARITY_QUOTES`;
  `metabolism.py` = `METABOLITE_ENZYME_QUOTES`; `uncertainty.py` = the mirror image of the others
  (`UNCERTAINTY_REASONS` + `UNCERTAIN_BINDING_CLAIMS` + `apply_binding_uncertainty`: why a quote-checked
  claim still deserves doubt); chain stays acyclic provenance <- connectivity <- quotes <- generate_data).
- `tools/data_generators/changelog.py` — parses the authored `docs/changelog/<version>/changelog.md`
  files into the `changelog.json` shape (stdlib, no deps). Fails loud with `file:line` on an unknown
  category, a bullet with no `fr:` line, or stray prose, so a typo cannot silently drop a bullet.
- `tools/drugs_io.py` — shared JSONL load/save for `drugs_data.jsonl` (`load_drugs`/`save_drugs`);
  used by `generate_data.py`, `fetch_ki.py`, and the three `apply_*_sources.py` writers.
- `tools/check_data.py` — stdlib integrity checker over emitted `public/data/` (see CLAUDE.md Data checks).
- `tools/serve.py` — stdlib dev server, `Cache-Control: no-store`, roots at `public/` (see CLAUDE.md Running).
- `tools/shot.py` — Playwright screenshot helper (see CLAUDE.md Screenshots).
- `tools/demos/` — Playwright demo-video recorder: `recorder.py` (a `Demo` API) + `neurarium.py`
  (the showcase tour, writes the README hero `docs/images/preview.gif`). Needs ffmpeg+gifski+GPU; see
  `tools/demos/README.md`.
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
- `tools/fetch/fetch_gtopdb.py` — fetches receptor tissue-distribution comments from the Guide to
  Pharmacology API (corpus #7 `gtopdb`), the source for **receptor expression regions**;
  `RECEPTOR_GENES` maps receptor->gene->targetId. Caches `data_sources/gtopdb/` + `worklist.json`
  (each quote carries assay species). See CLAUDE.md Source provenance (corpora #7/#8).
- `tools/fetch/fetch_allen.py` — fetches the Allen Human Brain Atlas microarray (corpus #8
  `allen_ahba`), the source for **target expression regions** + the receptor regions GtoPdb
  misses; a PACall detection-boolean vote per (gene, region), no judge. `TARGET_GENES` +
  `fetch_gtopdb.RECEPTOR_GENES` map owners to genes. Caches `data_sources/allen/` + `confirmed.json`.
  The same run also emits the **density** profiles into `data_sources/allen/density.json`
  (`--skip-density` opts out of the heavy MicroarrayExpression read; `DENSITY_MIN_R` is the
  cross-donor reliability floor). See CLAUDE.md Source provenance (corpora #7/#8) + Expression density.
- `tools/sourcing/apply_expression_density.py` — re-gates each density profile's quote against
  `data_sources/allen/pages/<gene>.md`, trims it to the regions the owner claims, and writes
  `tools/generated_cache/expression_density.json` (loaded into `RECEPTOR_DENSITY` / `TARGET_DENSITY`).
  Idempotent. See CLAUDE.md Expression density.
- `tools/sourcing/apply_location_sources.py` — merges accepted expression quotes into
  `tools/generated_cache/location_sources.json`, `--corpus {gtopdb,allen}` (gtopdb needs a judged file; allen is
  deterministic). Idempotent. See CLAUDE.md Source provenance (corpora #7/#8).
- `tools/generated_cache/location_sources.json` — machine-written bulk location sources, loaded by
  `generate_data.py` into `RECEPTOR_LOCATION_SOURCES` / `TARGET_LOCATION_SOURCES`. Not served.
- `tools/sourcing/recheck_quotes.py` — re-verifies every emitted verified quote with a stronger model
  (Sonnet) and stamps the sourcing LLM. `build --out <dir>` writes per-page batches (page text loaded
  once per batch to minimize tokens; Allen AHBA excluded as deterministic); an LLM judges each batch
  (present + supports claim); `apply --batches <dir> --verdicts <f> [--llm sonnet]` writes
  `tools/generated_cache/quote_llm.json` ({quote_id: llm}, applied uniformly by `quote_table`) +
  `quote_recheck_flagged.json` (quotes the recheck could not fully confirm, for review). See CLAUDE.md
  Source provenance ("The sourcing model").
- `tools/fetch/fetch_cyp.py`: stdlib, offline. Reads Stahl's per-drug `Pharmacokinetics` block out of
  the author-side dump, classifies each CYP line's role (`substrate`/`inhibitor`/`inducer`) + optional
  strength, re-confirms it **verbatim** on a page in that drug's own `INDEX.md` range, and writes the
  committed `tools/generated_cache/drug_enzymes.json` (merged in at build time, NOT authored in
  `drugs_data.jsonl`). No LLM: the sentence shape is fixed enough to grep, so the quote gate is the
  whole guarantee. `--dry-run` reports, `--verbose` lists dropped bullets. See CLAUDE.md Drug metabolism.
- `tools/fetch/fetch_cyp_wikipedia.py`: stdlib, offline (reads pages corpus #9 already stored). The same
  pass over a drug's English Wikipedia article, for the drugs Stahl has no monograph for. Reuses
  `fetch_cyp.py`'s role/strength/victim rules by import, adds the three a long Wikipedia paragraph needs
  (sentence split, drug-named-before-the-verb, negation veto), and writes the committed
  `tools/generated_cache/drug_enzymes_wikipedia.json`. Stahl wins any pair both state. `--dry-run`
  reports, `--verbose` lists dropped lines. A drug whose article URL redirects needs a `PAGE_ALIASES`
  entry (the store names files after the *resolved* title). See CLAUDE.md Drug metabolism.
- `tools/fetch/fetch_ki.py` — parses the PDSP Ki CSV (`data_sources/books/pdsp_ki/`, author-side) into
  per-drug binding affinities; `--apply` writes each `ki` + adds median-stronger `affinity_only`
  bindings. A curated `ALIAS` map recovers drugs PDSP lists under a related compound. See CLAUDE.md Drugs.
  **When adding one drug, scope every writer with its `--only`** (`fetch_ki.py`, `fetch_gtopdb_ki.py`,
  `fetch_molecules.py`, `fetch_brand_names.py`): an unscoped refresh legitimately rewrites every drug
  whose upstream rows moved, burying the one-drug change. A scoped run merges into the committed cache.
- `tools/fetch/fetch_gtopdb_ki.py` — stdlib. Downloads GtoPdb's bulk ligand-interaction CSV
  (`data_sources/gtopdb/interactions.csv`, author-side), joins it to our drugs by name (an HTML-stripping
  `norm` + a curated `LIGAND_ALIASES`) and to our targets by **case-folded gene symbol** (reusing
  `fetch_gtopdb.RECEPTOR_GENES` + `TARGET_GENES`, plus `EXTRA_TARGET_GENES` for the ionotropic subunit
  families), and writes one quotable row line per interaction into `data_sources/gtopdb/pages_ki/<slug>.md`
  (corpus #11 `gtopdb_ki`) + the proposals into `tools/generated_cache/gtopdb_ki.json`. Only a pKi/pKd
  becomes a Ki (`10^(9-pKi)` nM); a functional potency rides along as the direction's citation. No judge:
  the CSV's own `type` column is the direction. See CLAUDE.md Source provenance (corpus #11).
- `tools/sourcing/apply_gtopdb_ki.py` — merges those proposals into `drugs_data.jsonl`: confirm-only (never
  adds a target), PDSP-first (a `ki` only where there is none), and a `provisional_action` only on an
  `affinity_only` binding, so a stated direction always wins. A disagreement is reported, split into
  compatible refinements (`COMPATIBLE`) and genuine conflicts, never auto-resolved. Re-gates every quote
  through `check_data.normalize_for_match`; idempotent (`strip_previous` rebuilds its own prior write).
- `tools/fetch/fetch_wikipedia_pharmacology.py` — `uv run` (deps: beautifulsoup4). Fetches a drug's
  English Wikipedia article pinned to its revision id, stores the whole page author-side
  (`data_sources/wikipedia/raw/<slug>.html` + `pages/<slug>.md`, corpus #9 `wikipedia_pharm`), and mines
  the pharmacodynamics binding table for a per-target Ki (adaptive multi-row-header grid + fuzzy target
  resolution reusing `fetch_ki`'s `norm`/`parse_ki`/`NAME_PATTERNS`). A Ki source's `quote` is the
  verbatim table row, so the normal quote gate applies. Preview by default; `--json`, `--no-fetch`. Fills
  the Ki gap where PDSP has none (e.g. alpha1, non-psychiatric agents). See CLAUDE.md Drugs.
- `tools/fetch/fetch_brand_names.py` — `uv run` (deps: beautifulsoup4). Resolves each drug's French
  Wikipedia article via the EN article's langlinks (reusing `fetch_wikipedia_pharmacology.py`), stores it
  author-side (`data_sources/wikipedia/pages_fr/<slug>.md`, corpus #10 `wikipedia_fr`), and writes a
  candidate trade-name-sentence worklist (`tools/generated_cache/brand_worklist.json`) for the LLM that
  extracts each drug's ordered European/French brands. EN is used only for the langlink (its pages are not
  refetched, so no corpus #9 Ki gate can drift). See CLAUDE.md Source provenance (corpus #10).
- `tools/sourcing/apply_brand_names.py` — merges the LLM-extracted eu/fr brands (`brand_judged.json`) into
  `drugs_data.jsonl`, quote-gating each name verbatim on its FR page and tagging the first `fr`, the rest
  `eu` (na from Stahl is kept). Idempotent. See CLAUDE.md Source provenance (corpus #10).
- `tools/fetch/fetch_pharmacokinetics.py` — stdlib. Scans each drug's Stahl page span (from `INDEX.md`)
  for elimination half-life + active-metabolite lines, pre-parsing durations to hours, into a candidate
  worklist (`tools/generated_cache/pk_worklist.json`) for the LLM that extracts each drug's T½ +
  metabolites. See CLAUDE.md Drugs (Half-life + active metabolites).
- `tools/sourcing/apply_pharmacokinetics.py` — merges the LLM-extracted T½ + metabolites
  (`pk_judged.json`) into `drugs_data.jsonl`, quote-gating each value verbatim on its Stahl page and
  resolving a metabolite's `drug_id` by norm-name match (never self-link). Idempotent, sole writer of
  `half_life`/`metabolites`. See CLAUDE.md Drugs (Half-life + active metabolites).
- `tools/fetch/fetch_metabolite_bindings.py` — `uv run` (deps: beautifulsoup4). Reuses
  `fetch_wikipedia_pharmacology` as a library to mine each non-modeled active metabolite's own English
  Wikipedia article (an allow-list of confirmed own-articles; the rest fall back to the parent article
  for prose only, filtered to sentences naming the metabolite) into `metabolite_bindings_worklist.json`
  (Ki-table rows + candidate action sentences) for the LLM pass. See CLAUDE.md Drugs.
- `tools/sourcing/apply_metabolite_bindings.py` — `uv run` (deps: beautifulsoup4). Merges the
  LLM-extracted metabolite bindings (`metabolite_bindings_judged.json`) into `drugs_data.jsonl`:
  quote-gates each action sentence, resolves the target, attaches a Ki (PDSP measured preferred, else
  the Wikipedia table value), and adds every remaining Ki-table target as `affinity_only`. Idempotent,
  sole writer of a metabolite's `bindings`. See CLAUDE.md Drugs.
- `tools/fetch/pdf_to_pages.py` — splits a PDF into one `<page>.md` per page (the quote-gate text);
  `uv run`, `--layout` for OCR.
- `tools/fetch/build_toc_index.py` — `INDEX.md` from a PDF's embedded TOC (generic). `uv run`.
- `tools/fetch/build_index.py` — Stahl-specific page index (by `THERAPEUTICS` heading). `uv run`.
- `tools/update_readme_stats.py` — rewrites the README `SOURCING_STATS` + `SOURCES_TABLE` blocks
  (and the headline %) from `meta`; `--check` exits 1 if stale (CI). Idempotent.
- `tools/fetch/fetch_molecules.py` — downloads each drug's molecule SVG into `public/data/molecules/`;
  writes `tools/generated_cache/molecules_sources.json`. See CLAUDE.md Images.
- `tools/fetch/fetch_structure_images.py` — resolves the *url* of each structure's (and wiki-linked
  circuit's) Wikipedia hero + gallery images into `tools/{structure,circuit}_images_sources.json`
  (`--target structures|circuits|all`); downloads no bytes. See CLAUDE.md Images.
- `tools/generated_cache/{molecules,structure_images,circuit_images}_sources.json` — provenance/attribution for
  the fetch tools (the image ones are read by `generate_data.py` offline; not served).
- `tools/git-hooks/` — repo-tracked git hooks (see CLAUDE.md Git hooks).

## Data contract (emitted `public/data/`)

The field list of each emitted file. The viewer reads exactly these shapes; the generator
emits them. Every claim carries its own quote-level source (see CLAUDE.md Source provenance);
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
  `receptor_class_labels`, `synaptic_labels`), the drug maps (`drug_category_labels` key order =
  Drugs legend order, `drug_actions` action->{label,effect}, `drug_effect_colors`,
  `drug_effect_labels`, `drug_targets` = every non-receptor target + every receptor id; a target
  with a direction-flipping `vesicular`/`sign`/`synaptic` flag also carries `polarity_provenance`
  (+ optional `polarity_sources`), its own graded node kind `target_polarity`; a `receptor_group`
  target also carries `subtypes` (its modeled subtype receptor ids, a sourceless taxonomy the
  viewer lists as per-subtype drug dropdowns); a target with an Allen profile carries the same
  `density` object as a receptor),
  `enzymes` (metabolic isoform id -> {label, wikipedia}), `enzyme_roles`
  (role -> {label, `direction`: what it does to a co-prescribed substrate's level}) and
  `enzyme_strengths` + `enzyme_reactions` (the chemical step by which an enzyme makes an
  active metabolite; see CLAUDE.md Drug metabolism),
  `target_type_labels`/`target_type_colors`, `source_corpora`, `uncertainty_reasons` (the closed
  vocabulary a node's `uncertainty[]` bullets draw from, each `{source, absence, args}`),
  `density_min_reliability` (the
  cross-donor r floor every published profile clears), `provenance_stats` (the sourcing
  tally; see CLAUDE.md Source provenance).
- `translations.fr.json` — the deduplicated French side table, `{english: french}` with sorted
  keys, covering every emitted display string whose French differs from its English. Fetched by
  the viewer only in French (English users skip it); a missing key falls back to the English
  string. Written last by `write_artifacts` from the externalize pass (see docs/I18N.md).
- `quotes.jsonl` — the deduplicated source-quote side table, one quote node per line sorted by
  `id` (a `q_<12 hex>` content hash): `id`, `corpus`, `page`, `quote`, optional `species`, optional
  `llm` (the model that extracted+judged the quote, `haiku`/`sonnet`/`opus`; absent = unknown). Every
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
  CLAUDE.md Expression density), optional `description{en,fr}` + `wikipedia`(+prov). Empty
  locations + no description = a deliberate stub (listed, not focusable).
- `drugs.jsonl` — `id`, `name`, `categories`, `category_provenance` (+ optional
  `category_sources`), optional `nbn{en,fr}` (+ `nbn_sources`, + `nbn_nonstandard:true` when the
  value is Stahl's class descriptor not a formal NbN), `bindings[]` (each: `target`, `action`,
  optional `effect`/`note{en,fr}`/`tentative`/`sources[{corpus,page,quote,provenance}]`/`ki`
  (measured PDSP affinity)/`affinity_only:true` (Ki but no known direction, panel-only)/
  `uncertainty[]` (each: `kind` (a `meta.uncertainty_reasons` key), optional `args` (the i18n
  sentence's slots), and either `sources[]` or `absence:true`; non-empty = the orange ⚠ badge
  takes the pill over, see CLAUDE.md Source provenance)),
  optional `half_life` (`{hours, hours_max?}`, elimination T½) + `half_life_sources[]`, optional
  `enzymes[]` (each: `enzyme` (a `meta.enzymes` key), `role`, optional `strength`, `sources[]`;
  one node per (enzyme, role) pair, kind `drug_enzymes`, merged in from the committed
  `generated_cache/drug_enzymes.json` + `drug_enzymes_wikipedia.json`, never authored),
  `metabolites[]` (each: `name`, optional `half_life`(+`half_life_sources`), `sources[]`, optional
  `drug_id` linking a modeled drug, optional `bindings[]` for a non-modeled metabolite: same shape as a
  drug binding, kind `drug_metabolite_bindings`; optional `formed_by[]` (each: `enzyme`, optional
  `reaction` (a `meta.enzyme_reactions` key), `sources[]`), one node per (parent, metabolite, enzyme),
  kind `drug_metabolite_enzyme`, hand-curated in `data_generators/quotes/metabolism.py`),
  optional `wikipedia`(+prov), optional `structure_image` (vendored `data/molecules/<id>.svg`,
  only when the file exists), `focusable`. No drug-level source: provenance is per-claim (see
  CLAUDE.md Source provenance).
- `molecules/<id>.svg` — vendored per-drug structure diagrams (`fetch_molecules.py`). Structure
  illustrations are NOT vendored (hot-linked, see CLAUDE.md Images).

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
