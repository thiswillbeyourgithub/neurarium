# Authoring & data tooling

Runbooks for editing the dataset and refreshing external assets. The map of what
each script is lives in [`../CLAUDE.md`](../CLAUDE.md) (File map); this file is the
step-by-step *how*. Author-side corpus locations are in `CLAUDE.local.md`.

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
     value needs its label map entry (+ FR). Mechanism grade overridable in
     `RECEPTOR_PROVENANCE`; an individual expression region is sourced (above `llm`) by
     adding a `{receptor_id: {base: [quote-source]}}` entry to `RECEPTOR_LOCATION_SOURCES`.
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
   to merge new `verified` sources into `tools/location_sources.json`. See Expression locations.
5. **Allen AHBA expression** (the `target_locations` + residual `receptor_locations`
   sources): `python tools/fetch_allen.py` re-pulls each donor's microarray PACall (caches
   to `sources/allen/`, author-side; ~2GB across donors), then `python
   tools/apply_location_sources.py --corpus allen` merges the deterministic `verified`
   sources (no judge) into `tools/location_sources.json`. See Expression locations.
6. `python tools/generate_data.py` — regenerate `public/data/` from all of the above.
7. `python tools/update_readme_stats.py` — refresh the README sourcing table
   (CI runs it `--check`).

Panel **descriptions** need no refresh script: each fetches the current Wikipedia lead
at runtime (`js/wiki.js`), so they stay current on their own.
