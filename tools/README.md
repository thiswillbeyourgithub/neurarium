# Authoring & data tooling

Runbooks for editing the dataset and refreshing external assets, plus the reference
for **what each tool is** (Tool reference, below) and the **emitted data contract**
(Data contract, below). Both moved here from [`../CLAUDE.md`](../CLAUDE.md) to keep that
file terse; CLAUDE.md keeps the viewer/runtime map and the non-obvious rules. Author-side
corpus locations are in `CLAUDE.local.md`.

## Changing the data

1. Edit the relevant list in `generate_data.py` (or `tools/drugs_data.json` for drugs).
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
     Hypothetical section). Projections are bilateral by default (define once on the right);
     `symmetric: False` keeps a one-sided pathway. `kind` must be a `PROJECTION_COLORS` key
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
   - **Drugs**: edit `tools/drugs_data.json`. Each: `id`, `name`, `categories`, optional
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
   which rewrites `drugs_data.json`'s `ki` annotations + `affinity_only` bindings.
5. Commit the generator change + the regenerated artifacts together.

The legend is generated at runtime from the data, so it updates automatically.

## Refreshing external data (author-side)

To re-pull every third-party asset the dataset hot-links or vendors, run these (all
network, idempotent, polite; each touches only what changed). Always finish with
`generate_data.py` so the emitted `public/data/` picks up the new urls/files:

1. `python tools/fetch_molecules.py` — new per-drug molecule SVGs into
   `public/data/molecules/` (only drugs missing one); writes `tools/molecules_sources.json`.
2. `python tools/fetch_structure_images.py` — re-resolve each structure's **and**
   wiki-linked circuit's Wikipedia hero + gallery image **urls** into
   `tools/structure_images_sources.json` + `tools/circuit_images_sources.json` (no bytes
   downloaded; the gif/svg is hot-linked at runtime). `--target structures|circuits`
   scopes to one.
3. **PDSP Ki**: re-download the whole-DB CSV from
   `https://pdspdb.unc.edu/databases/kiDownload/download.php` over
   `sources/books/pdsp_ki/KiDatabase.csv` (author-side; see that dir's `README.md`), then
   `python tools/fetch_ki.py --apply` to rewrite `drugs_data.json`'s `ki` + `affinity_only`.
4. **GtoPdb receptor expression** (the `receptor_locations` sources): `python
   tools/fetch_gtopdb.py` re-pulls each receptor's tissue comments (caches to
   `sources/gtopdb/`, author-side), then run the confirm-only judge over
   `sources/gtopdb/worklist.json` and `python tools/apply_location_sources.py --judged <f>`
   to merge new `verified` sources into `tools/location_sources.json`. See CLAUDE.md Source provenance (corpora #7/#8).
5. **Allen AHBA expression** (the `target_locations` + residual `receptor_locations`
   sources): `python tools/fetch_allen.py` re-pulls each donor's microarray PACall (caches
   to `sources/allen/`, author-side; ~2GB across donors), then `python
   tools/apply_location_sources.py --corpus allen` merges the deterministic `verified`
   sources (no judge) into `tools/location_sources.json`. See CLAUDE.md Source provenance (corpora #7/#8).
6. `python tools/generate_data.py` — regenerate `public/data/` from all of the above.
7. `python tools/update_readme_stats.py` — refresh the README sourcing table
   (CI runs it `--check`).

Panel **descriptions** need no refresh script: each fetches the current Wikipedia lead
at runtime (`js/wiki.js`), so they stay current on their own.

## Tool reference

What each authoring / fetch / check script in `tools/` is (one line each). The dev/runtime
tooling (`serve.py`, `shot.py`, `demos/`) is also summarized in `../CLAUDE.md` (Running,
Screenshots).

- `generate_data.py` — single source of truth for the anatomy (stdlib-only, offline):
  defines every region/projection/receptor once, emits the artifacts below. Drugs are the
  exception (authored in `tools/drugs_data.json`, read by `_load_drugs`). Display strings are
  `{en,fr}` via `_t()` (see CLAUDE.md I18n).
- `tools/drugs_data.json` — the authored drug dataset (from Stahl 8th ed.), read by
  `_load_drugs`, emitted to `data/drugs.jsonl`. Edit to add/change a drug.
- `tools/check_data.py` — stdlib integrity checker over emitted `public/data/` (see CLAUDE.md Data checks).
- `tools/serve.py` — stdlib dev server, `Cache-Control: no-store`, roots at `public/` (see CLAUDE.md Running).
- `tools/shot.py` — Playwright screenshot helper (see CLAUDE.md Screenshots).
- `tools/demos/` — Playwright demo-video recorder: `recorder.py` (a `Demo` API) + `neurarium.py`
  (the showcase tour, writes the README hero `docs/preview.gif`). Needs ffmpeg+gifski+GPU; see
  `tools/demos/README.md`.
- `tools/build_source_worklist.py` — lists not-yet-sourced drug bindings with Stahl page ranges
  (input to the source-extraction workflow; resumable).
- `tools/apply_source_quotes.py` — applies the extraction workflow's accepted quotes onto
  bindings (re-finds the quote in the page range; idempotent).
- `tools/apply_nbn_sources.py` — sources each drug's NbN line (greps Stahl's verbatim line,
  substring-confirms, no judge); falls back to the drug **Class** line (`nbn_nonstandard`) for a
  newer drug with no NbN line. Idempotent.
- `tools/apply_category_sources.py` — sources each drug's class classification (`drug_categories`)
  from an extract/judge results file (a judge is needed: our coarse `categories` re-map Stahl's
  free-text class line, unlike the fixed NbN field). Idempotent.
- `tools/fetch_gtopdb.py` — fetches receptor tissue-distribution comments from the Guide to
  Pharmacology API (corpus #7 `gtopdb`), the source for **receptor expression regions**;
  `RECEPTOR_GENES` maps receptor->gene->targetId. Caches `sources/gtopdb/` + `worklist.json`
  (each quote carries assay species). See CLAUDE.md Source provenance (corpora #7/#8).
- `tools/fetch_allen.py` — fetches the Allen Human Brain Atlas microarray (corpus #8
  `allen_ahba`), the source for **target expression regions** + the receptor regions GtoPdb
  misses; a PACall detection-boolean vote per (gene, region), no judge. `TARGET_GENES` +
  `fetch_gtopdb.RECEPTOR_GENES` map owners to genes. Caches `sources/allen/` + `confirmed.json`.
  See CLAUDE.md Source provenance (corpora #7/#8).
- `tools/apply_location_sources.py` — merges accepted expression quotes into
  `tools/location_sources.json`, `--corpus {gtopdb,allen}` (gtopdb needs a judged file; allen is
  deterministic). Idempotent. See CLAUDE.md Source provenance (corpora #7/#8).
- `tools/location_sources.json` — machine-written bulk location sources, loaded by
  `generate_data.py` into `RECEPTOR_LOCATION_SOURCES` / `TARGET_LOCATION_SOURCES`. Not served.
- `tools/fetch_ki.py` — parses the PDSP Ki CSV (`sources/books/pdsp_ki/`, author-side) into
  per-drug binding affinities; `--apply` writes each `ki` + adds median-stronger `affinity_only`
  bindings. A curated `ALIAS` map recovers drugs PDSP lists under a related compound. See CLAUDE.md Drugs.
- `tools/pdf_to_pages.py` — splits a PDF into one `<page>.md` per page (the quote-gate text);
  `uv run`, `--layout` for OCR.
- `tools/build_toc_index.py` — `INDEX.md` from a PDF's embedded TOC (generic). `uv run`.
- `tools/build_index.py` — Stahl-specific page index (by `THERAPEUTICS` heading). `uv run`.
- `tools/update_readme_stats.py` — rewrites the README `SOURCING_STATS` + `SOURCES_TABLE` blocks
  (and the headline %) from `meta`; `--check` exits 1 if stale (CI). Idempotent.
- `tools/fetch_molecules.py` — downloads each drug's molecule SVG into `public/data/molecules/`;
  writes `tools/molecules_sources.json`. See CLAUDE.md Images.
- `tools/fetch_structure_images.py` — resolves the *url* of each structure's (and wiki-linked
  circuit's) Wikipedia hero + gallery images into `tools/{structure,circuit}_images_sources.json`
  (`--target structures|circuits|all`); downloads no bytes. See CLAUDE.md Images.
- `tools/{molecules,structure_images,circuit_images}_sources.json` — provenance/attribution for
  the fetch tools (the image ones are read by `generate_data.py` offline; not served).
- `tools/git-hooks/` — repo-tracked git hooks (see CLAUDE.md Git hooks).

## Data contract (emitted `public/data/`)

The field list of each emitted file. The viewer reads exactly these shapes; the generator
emits them. Every claim carries its own quote-level source (see CLAUDE.md Source provenance);
there is no node-level catch-all `sources` block.

- `meta.json` — presentation maps + tallies, so the dataset is self-describing (a port needs
  no hardcoded palette): `projection_colors`, `kind_labels`, `group_labels`, `kind_signs`,
  `sign_colors`, `sign_labels`, `system_flow_kinds` (drug target system -> projection kind),
  the receptor maps (`receptor_family_labels` key order = legend family order,
  `receptor_class_labels`, `synaptic_labels`), the drug maps (`drug_category_labels` key order =
  Drugs legend order, `drug_actions` action->{label,effect}, `drug_effect_colors`,
  `drug_effect_labels`, `drug_targets` = every non-receptor target + every receptor id; a target
  with a direction-flipping `vesicular`/`sign`/`synaptic` flag also carries `polarity_provenance`
  (+ optional `polarity_sources`), its own graded node kind `target_polarity`),
  `target_type_labels`/`target_type_colors`, `source_corpora`, `provenance_stats` (the sourcing
  tally; see CLAUDE.md Source provenance).
- `structures.jsonl` — `id`, `name{en,fr}`, `base_name{en,fr}` (hemisphere-stripped, legend
  row), `group`, `position`, `color`, `shape_file`, `classification_provenance`, optional
  `wikipedia`(+`_provenance`), optional `structure_image` (hot-linked Wikimedia url, shared by
  both hemispheres) + `structure_image_gallery`.
- `projections.jsonl` — `from`, `to`, `kind`, `label{en,fr}`, `neurotransmitter{en,fr}`,
  `description{en,fr}`, optional `sources[{corpus,page,quote,provenance}]` (from `KANDEL_QUOTES`),
  `bidirectional`, `tentative` (dotted, off-by-default section).
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
  the ubiquitous claim), optional `description{en,fr}` + `wikipedia`(+prov). Empty locations + no
  description = a deliberate stub (listed, not focusable).
- `drugs.jsonl` — `id`, `name`, `categories`, `category_provenance` (+ optional
  `category_sources`), optional `nbn{en,fr}` (+ `nbn_sources`, + `nbn_nonstandard:true` when the
  value is Stahl's class descriptor not a formal NbN), `bindings[]` (each: `target`, `action`,
  optional `effect`/`note{en,fr}`/`tentative`/`sources[{corpus,page,quote,provenance}]`/`ki`
  (measured PDSP affinity)/`affinity_only:true` (Ki but no known direction, panel-only)),
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
