# Sourcing gaps: what is not yet `verified`, why, and how to tackle it

The dataset grades every **node** (any sourceable datum, see `CLAUDE.md` "Nodes")
`llm` < `sourced` < `verified`. `verified` is the top grade: a quote was
programmatically confirmed present in a cited source page (or a Ki row in the PDSP
CSV). This document lists everything **not** at `verified`, says **why**, and gives an
**idea to tackle it**. Numbers come straight from `meta.provenance_stats` (regenerate
with `python tools/generate_data.py`, print the table with `python tools/check_data.py`),
so re-derive them after any data change rather than trusting the counts below forever.

Made with the help of Claude Code.

## Snapshot (2026-07-04, after the Allen target-expression Phase 2a)

Headline: **1415 / 1665 knowledge nodes backed (85%)**. In the tally a bare `llm`
grade counts as **missing** ("an LLM asserted it from memory" = no document), so
"missing" below means `llm` or no source at all. 250 knowledge nodes are missing.

> **Recently closed.** Several smaller kinds are now fully (or nearly) sourced:
> - `target_locations` 108/124 verified: **Phase 2a** wired the **Allen Human Brain
>   Atlas** microarray (corpus #8 `allen_ahba`). `fetch_allen.py` aggregates Allen's
>   `PACall` present/absent detection boolean across the 5 available human donors into a
>   deterministic present/absent per (gene, region) (no judge), and the confirm-only merge
>   upgraded 108 existing "Found in" regions across 22 non-receptor targets. The 16 that
>   stay `llm` are honest microarray limits: SERT + NET **terminal** regions (their mRNA is
>   in the raphe / locus-coeruleus cell bodies, which DO confirm, not the cortical/limbic
>   terminals) + the melatonin receptor group. Every Allen source is `species: "Human"`.
> - `receptor_locations` 197/383 verified: **Phase 1** of the expression-sourcing work
>   wired the **Guide to Pharmacology** tissue-distribution API (corpus #7 `gtopdb`). A
>   confirm-only judge mapped 197 existing "Found in" regions across 49 receptors to a
>   verified tissue quote (never adding/dropping a region), each carrying its assay
>   **species** (the viewer flags a non-human assay with an amber tag). The remaining 186
>   `receptor_locations` are **Phase 2b** (Allen AHBA, reusing the cached donor zips).
> - `structures` 52/52 verified: the last four (claustrum + fornix) closed against the
>   newly-wired **Nieuwenhuys** atlas (corpus #6), which Kandel does not describe in prose.
> - `projections` 99/103 verified: 7 limbic/olfactory/commissural families closed against
>   Nieuwenhuys (fornix chain, hippocampo-septal, septo-hypothalamic, olfactory-bulb to
>   amygdala, temporal anterior commissure, insula to cingulate). Only claustrum to frontal
>   and claustrum to insula remain (no single Nieuwenhuys page states them; not forced).
> - `drug_categories` 156/158 verified against Stahl's "Class" section (Haiku extract,
>   Sonnet judge, `apply_category_sources.py` re-find + write, `check_data.py` re-verify;
>   the 2 left are `naltrexonebupropion` (Stahl "weight management medication" vs our
>   `substance_use`, a flagged mismatch) and `serdexmethylphenidate` (no class bullet)).
> - `circuits` 6/6 verified: the two basal-ganglia loops from new Kandel p983 quotes, the
>   other four reusing quotes already verified for their member projections.
> - `projection_groups` 10/10 verified: glutamate/GABA from Stahl Essential, the monoamine
>   + cholinergic + neuroendocrine + modulatory systems from Kandel (the sign groups reuse
>   the transmitter quotes).
> - `references` 2/2 closed: Wikipedia links added for the carbonic-anhydrase + PDE5 targets.
>
> Headline 55% (pre-drug-class) to 67% (Nieuwenhuys) to 78% (GtoPdb Phase 1) to 85%
> (Allen Phase 2a). The table below is the post-Phase-2a state.

| Node kind | Missing | Total | Share of the gap | Difficulty | Best lever |
| --- | ---: | ---: | ---: | --- | --- |
| `receptor_locations` | 186 | 383 | 74.4% | Hard | Allen AHBA (Phase 2b); 197 done via GtoPdb |
| `receptors` (mechanism) | 26 | 56 | 10.4% | Medium | IUPHAR Guide to Pharmacology |
| `target_locations` | 16 | 124 | 6.4% | limit | 108 done via Allen; the 16 are mRNA-at-source honest `llm` |
| `drug_bindings` | 12 | 632 | 4.8% | Medium | PDSP refresh + primary lit |
| `projections` | 4 | 103 | 1.6% | Hard | claustrum primary lit |
| `targets` (classification) | 4 | 25 | 1.6% | **Easy** | IUPHAR / textbook |
| `drug_categories` | 2 | 158 | 0.8% | flagged | Stahl "Class" line |
| `target_locations` (done) | 0 | 108 | closed | done | Allen AHBA (corpus #8) |
| `receptor_locations` (done) | 0 | 197 | closed | done | GtoPdb (corpus #7) |
| `structures` (anatomy) | 0 | 52 | **DONE** (52/52) | done | Kandel + Nieuwenhuys |
| `circuits` | 0 | 6 | **DONE** (6/6) | done | Kandel prose |
| `projection_groups` | 0 | 10 | **DONE** (10/10) | done | Stahl Essential / Kandel |
| `references` (Wikipedia links) | 0 | 298 | **DONE** (not in headline) | done | Wikipedia URLs |

**The shape of the problem:** one kind is now **~74%** of the remaining gap (186 of 250):
the residual `receptor_locations` GtoPdb had no tissue data for. Closing them is **Phase 2b**
below: rerun `fetch_allen.py` over the receptor genes (the donor zips are already cached),
exactly like the target run just did for Phase 2a. Next after that is the 26 `llm` receptor
mechanism classifications. The 16 residual `target_locations` are a hard microarray limit,
not a gap to chase (transporter mRNA is at the source nucleus, not the terminal).

Five book corpora + three data corpora are wired into `SOURCE_CORPORA` today (`stahl`,
`kandel`, `stahl_essential`, `carlat`, `nieuwenhuys`, plus the `pdsp_ki` CSV, the `gtopdb`
tissue API, and the `allen_ahba` microarray). The book-prose wins those allow are largely
exhausted (see the sourcing memory); the remaining gaps mostly need the expression atlas
(Phase 2b below), a receptor-classification database, or (for the last two claustrum
pathways) primary literature.

---

## Phase 2 plan: Allen AHBA expression sourcing (the 310 remaining expression nodes)

> **Status: Phase 2a DONE** (target_locations, corpus #8 `allen_ahba` wired, 108/124
> verified; the tooling `fetch_allen.py` + `apply_location_sources.py --corpus allen` is
> built and validated end-to-end). **Phase 2b is next**: rerun `fetch_allen.py` over the
> receptor genes to source the 186 residual `receptor_locations`; the 5 donor zips are
> already cached, so it is only compute. **Phase 2c** (deep-nuclei residuals) folds into 2b.

**Goal.** Source the **310** expression nodes GtoPdb (Phase 1) could not reach: the **186**
residual `receptor_locations` (across 44 receptors GtoPdb had no tissue data for) + the
**124** `target_locations` (Phase 2a, now 108 verified + 16 honest microarray-limit `llm`),
against the **Allen Human Brain Atlas (AHBA) microarray**. Same shape as Phase 1:
**confirm-only** (upgrade the grade on an *existing* LLM-authored "Found in" region, never
add or drop a region), one graded node per `(gene, region)` pair, quote-gated author-side.

**Why Allen, and only Allen.** Four candidate sources were evaluated (see the
`expression-source-options` sourcing memory); Allen is the only one that fits our anatomy:
- **Resolves all 29 base regions, including the deep nuclei that are the dataset's
  signature** (locus coeruleus, substantia nigra, VTA, subthalamic, raphe, mammillary,
  septal, claustrum, fornix). The clean-licence alternatives are too coarse: HPA (CC BY 4.0)
  and GTEx collapse our 6 cortical lobes into one "cerebral cortex" and our 5 basal-ganglia
  nuclei into one "basal ganglia", and resolve none of the small nuclei. Allen is the only
  path to the deep nuclei.
- **Whole-transcriptome, so it covers non-receptor targets too** (SERT=`SLC6A4`, MAO-A/B,
  VMAT2=`SLC18A2`, the ion channels), which GtoPdb (receptor-only; SERT/MAO-A returned
  empty) cannot. One source closes both `receptor_locations` and `target_locations`.
- **Human tissue (6 adult donors)**, so every Allen source is `species: "Human"` (no amber
  non-human tag; strengthens coverage versus GtoPdb's rat-heavy quotes).
- **Ships a PACall present/absent boolean** per (probe, sample): a non-interpretive
  "expressed here / not" bit, the cleanest possible basis for a *verified* location. No
  expression threshold to invent (HPA's nTPM would need binarizing).

**Licence: the one go/no-go.** Allen data is **copyright-reserved, non-commercial research
use with required citation** (Hawrylycz et al. 2012, Nature 489:391), **not** CC-BY. This
project is AGPL, free, non-commercial and educational, which is within Allen's terms, and we
do **not** redistribute the atlas: we vendor only a **minimal cited slice** (the handful of
present/absent booleans we actually cite, per gene x region) plus a fetch script, exactly as
`abagen` / `neuromaps` do under attribution. Add the Hawrylycz citation to `SOURCE_CORPORA`
and the About panel's attribution line. **If the user rejects a non-commercial source**, the
fallback is HPA (CC BY 4.0) + GTEx, accepting that the cortical lobes + basal-ganglia nuclei
collapse and the deep nuclei stay `llm` (roughly half the 310 unreachable). This is the only
decision that changes the plan; everything below assumes Allen.

**Data model: `allen_ahba` = corpus #8, built exactly like `gtopdb` (a `pages_dir`
corpus), NOT like PDSP.** Reusing the GtoPdb shape means zero new code in `check_data.py` and
one source shape everywhere:
- `fetch_allen.py` writes a cached page per gene, `sources/allen/pages/<gene>.md`, whose
  lines are the regions Allen calls **present** for that gene (one line each, e.g.
  `SLC6A4 present in raphe (probe A_23_P..., 11/12 samples, donors 9861/10021)`).
- A location source is the usual `{corpus:"allen_ahba", page:<gene>, quote:<that line>,
  provenance:"verified", species:"Human"}`. `check_data.py`'s existing verbatim-quote gate
  (`normalize_for_match` substring against `pages/<page>.md`) then covers it unchanged,
  author-side, skipped + warned on a clone (like the Stahl + GtoPdb pages).
- **No LLM judge needed** (unlike GtoPdb prose): the confirm is deterministic. For each
  existing `llm` `(gene, region)` node, if Allen has a present call for that gene in that
  region -> write the verified source citing the line; else leave it `llm`. This is stricter
  and cheaper than Phase 1 (no judge tokens, no drift).

**The hand-authored artifacts (the real work).**
1. **Allen `structure_id` -> our 29 `base` crosswalk.** Allen's ontology is hierarchical, so
   each base maps to an ontology **subtree**; a tissue sample counts toward a base if its
   structure sits in that subtree. ~half the ids are known from the Phase-2 research
   (LC 9148, SN 9072, VTA 9002, STN 4517, mammillary 4671, septal 13002, raphe 9455,
   claustrum 4321, fornix 9249); the cortical lobes, thalamus, hypothalamus, amygdala,
   hippocampus, cerebellum, caudate, putamen, pallidum, accumbens, midbrain, pons, medulla,
   olfactory bulb, insula and cingulate still need pinning from `Ontology.csv`. This is the
   analogue of `fetch_ki.py`'s `ALIAS` map, and it is one-time.
2. **Gene maps.** Receptors already have `RECEPTOR_GENES` (in `fetch_gtopdb.py`, reuse it).
   Add a **`TARGET_GENES`** map for the 25 non-receptor targets (single genes: `sert`=SLC6A4,
   `mao_a`=MAOA, `vmat2`=SLC18A2, ...). The nine **`receptor_group`** targets (muscarinic =
   CHRM1-5, nicotinic, `alpha1`=ADRA1A/B/D, `alpha2`, `beta`, glutamate, melatonin =
   MTNR1A/B, orexin = HCRTR1/2, melanocortin) map to **several** genes: a group is "present
   in region B" if **any** member gene has a present call there.
3. **Sampling sanity check.** Some small nuclei (raphe, LC, fornix white matter) are
   under-sampled across the 6 donors, and the **pituitary is outside Allen's brain sampling**
   entirely; a base with no samples in any donor simply cannot be confirmed and stays `llm`.
   The fetch script must **`log()` every such un-confirmable (gene, base)** rather than
   silently dropping it, so the residual `llm` set is honest.

**Deliverables.**
- `tools/fetch_allen.py` — resolve each gene's probe(s), download the per-donor microarray +
  `PACall` + `SampleAnnot` + `Ontology` from the Allen API (`api.brain-map.org`) /
  `human.brain-map.org` bulk, apply the crosswalk, aggregate PACall over each base's samples,
  emit `sources/allen/pages/<gene>.md` + `sources/allen/worklist.json`. Stdlib urllib, polite,
  idempotent, `--only`/`--refresh` (mirror `fetch_gtopdb.py`). Filters to our genes' probes
  early so it caches only the slice, not the multi-hundred-MB full CSVs.
- The Allen->base **crosswalk** + **`TARGET_GENES`** map (live in `fetch_allen.py`).
- **Apply step** — extend `tools/apply_location_sources.py` with a deterministic
  `--corpus allen` mode (no judged file: it reads the worklist + the *existing* location
  lists straight from the emitted data and confirms) rather than a second tool, so the
  merge-into-`location_sources.json` + dedup logic is not duplicated. Handles **both**
  receptors and targets (the emitter is already shared).
- `allen_ahba` **corpus #8** in `SOURCE_CORPORA` (`generate_data.py`) with the Hawrylycz
  citation; emitted into `meta.source_corpora`; the README `SOURCES_TABLE` picks it up.
- **Attribution**: Hawrylycz 2012 in the About panel's sources block.
- **Author-side `sources/allen/` tree** (gitignored: `raw/` download cache, `pages/<gene>.md`,
  `worklist.json`), documented in `CLAUDE.local.md` alongside the `sources/gtopdb/` tree.
- **Docs**: `CLAUDE.md` (corpus #8 in File map + Source provenance), this file, the
  `expression-source-options` memory (mark Phase 2 done), README stats refresh.

**Sub-phasing (prove cheap, then scale).**
- **2a - the 124 `target_locations`** (25 non-receptor targets). Coarser distribution,
  mostly single dominant genes, currently 0/124 = the biggest untouched kind; best proof of
  the pipeline. Includes authoring `TARGET_GENES` + the group-gene aggregation.
- **2b - the 186 residual `receptor_locations`** (44 receptors). Reuse `RECEPTOR_GENES`;
  same tool, `--only` the receptors GtoPdb missed.
- **2c - the deep-nuclei rows** only Allen reaches (overlaps 2b: the monoamine source
  nuclei), the payoff for choosing Allen over the CC-BY sources.

**Coverage estimate.** Allen has every gene and every region, so the ceiling is high; realistic
haircuts are (i) `(gene, base)` pairs Allen calls absent (correctly left `llm`), (ii)
under-sampled small nuclei, (iii) the pituitary (unsampled). Rough expectation: **~210-270 of
310** confirmable, lifting the headline from **78% to roughly 88-93%**. Treat as a target, not
a promise; the sampling check in step 3 gives the real number before any grades are written.

**Effort.** ~1 focused session: the crosswalk + `TARGET_GENES` authoring and the Allen
download/probe-selection plumbing are the bulk; the apply/confirm/gate reuse Phase 1 wholesale.
Probe selection is the one open design detail (a gene has several probes): recommend "present if
the best-expressed probe has PACall present in >= half the base's samples", citing that probe +
counts, mirroring `fetch_ki.py`'s representative-row choice.

---

## The gaps, biggest lever first

### 1. `receptor_locations`, 186 / 383 missing (197 closed by GtoPdb Phase 1)

**What.** One node per `(receptor, region)` pair: the claim "receptor R is expressed in
region B" (the panel's "Found in" rows). **Phase 1 verified 197** of these against the
Guide to Pharmacology tissue API (corpus #7 `gtopdb`, species-flagged); the remaining
**186** (across 44 receptors GtoPdb had no tissue comment for) are still `llm`.

**Why the residual 186 are not verified.** GtoPdb is receptor-only and its tissue-comment
coverage is patchy: many receptor subtypes have no comment, and several comments are too
generic ("brain", "cerebrum") to confirm a specific base. So there is no GtoPdb quote to
gate them against.

**How to tackle.** **Phase 2 (Allen AHBA), scoped in full above.** Allen resolves the
deep nuclei GtoPdb + the CC-BY atlases cannot, and its PACall boolean is a clean verified
basis. The 186 are sub-phase **2b**.

### 2. `target_locations`, 124 / 124 missing

**What.** The `target_locations` mirror of #1 for the 25 non-receptor targets (SERT,
MAO-A/B, VMAT2, ion channels, the receptor groups): "target T is expressed in region B."
All `llm`; GtoPdb (Phase 1) is receptor-only, so none were reachable there.

**Why not verified.** No whole-transcriptome expression atlas wired yet; GtoPdb does not
cover transporters/enzymes/channels.

**How to tackle.** **Phase 2 (Allen AHBA), scoped in full above**, sub-phase **2a** (do
these first: coarser distribution, single dominant genes, biggest untouched kind, best
proof of the Allen pipeline before the 186 receptors). The emitter `_location_sources` +
validation is already shared between receptors and targets, so one fetch tool feeds both.

### 3. `receptors` (mechanism classification), 26 / 56 missing

**What.** The per-receptor mechanism node (neurotransmitter / ionotropic-vs-metabotropic
/ excit-inhib-modulatory / pre-post). 30 are verified against Stahl Essential; 26 remain
`llm`: the serotonin subtypes (5-HT1A/1E/1F/2A/2B/2C/4/5A/6/7), adrenergic subtypes
(a1a/a1b/a1d, a2b/a2c, b1/b2), the opioids (mu/delta/kappa), CB1, A2A (adenosine), sigma1,
and MT1/MT2.

**Why not verified.** Stahl Essential classifies these subtypes in **tables**, not prose,
so the sentence-level quote gate had nothing to grab (the 30 that passed are the ones the
book discusses in running text).

**How to tackle.**
- **IUPHAR/BPS Guide to Pharmacology** is the canonical, free, citable receptor-
  classification database (G-protein coupling, ionotropic/metabotropic, endogenous
  agonist). Wire it as corpus #6; every one of these 26 has a page there. Best fit.
- Or extend the quote gate to accept a **table-cell** citation (page + the cell text) so
  Stahl Essential's own tables become quotable.
- Or a neuropharmacology textbook with prose subtype descriptions (Katzung, Rang & Dale).

### 4. `projections`, 4 / 103 missing (2 claim-families, mostly closed)

**What.** Just 4 pathway arrows (2 distinct L/R families) remain unsourced: claustrum to
frontal and claustrum to insula. The fornix chain (hippocampus to fornix to mammillary),
hippocampo-septal, septo-hypothalamic, olfactory-bulb to amygdala, the temporal anterior
commissure, and insula to cingulate were **closed against the Nieuwenhuys atlas** (corpus
#6): a Sonnet judge confirmed each verbatim single-page quote asserts the directed pathway.

**Why the last two are not verified.** The Nieuwenhuys atlas states claustrum-to-neocortex
connectivity only **in aggregate**: the sentence naming the specific frontal areas (motor,
premotor, prefrontal area 46, orbitofrontal area 12) sits on a different PDF page than the
connecting verb, so no single quotable page asserts "claustrum to frontal", and no page
asserts a claustrum-insula **fibre projection** at all (only that the claustrum is
adjacent to and developmentally derived from the insular cortex). The judge rejected the
generic "many neocortical areas" sentence for both, so they were not forced.

**How to tackle.** These two need a **claustrum-specific** source: a claustrum connectivity
review (Crick & Koch 2005 and successors) via primary lit / NCBI, or a tract-tracing paper.
Given how thin claustrum connectivity is in the literature, they may honestly stay `llm`.

### 5. `drug_bindings`, 12 / 632 missing

**What.** 12 bindings with neither a quote source nor a Ki. Mostly `tentative` subtype
affinities (blonanserin to D3, amitriptyline/trimipramine to various,
perospirone/zuclopenthixol to 5-HT), plus a few non-tentative (carbamazepine to
glutamate-modulator, maprotiline to muscarinic, sertraline to sigma1, sulpiride to H1,
trimipramine to Nav).

**Why not verified.** Stahl states the drug but not the specific subtype affinity; Carlat
is too concise; PDSP has no Ki row that resolves for these drug x target pairs.

**How to tackle.** Re-run **`fetch_ki.py --apply`** after a fresh PDSP CSV download; sigma1,
H1, and Nav affinities in particular may now be in PDSP and would auto-verify. The truly
`tentative` subtype ones need a specific pharmacology paper (NCBI/PubMed) or stay flagged
tentative. Low node count; do it opportunistically alongside the next PDSP refresh.

### 6. `projection_groups`, DONE (10 / 10 verified)

**What.** The 10 legend "system" nodes (7 per-transmitter groups + 3 per-sign groups):
"the serotonergic ascending system", "excitatory projections", etc.

**How it was closed.** One defining quote per group via the existing `_expand_sources`
quote-source mechanism: glutamate/GABA from **Stahl Essential**, the dopamine (reusing the
verified nigrostriatal quote), acetylcholine, neuroendocrine, serotonin, noradrenaline and
modulatory systems from **Kandel**. The two sign groups excitatory/inhibitory reuse their
dominant transmitter's quote, so no quote text is duplicated. A Sonnet judge confirmed each
mapping; `check_data.py` re-confirms each quote on-page.

### 7. `circuits`, DONE (6 / 6 verified)

**What.** The 6 functional circuits (Papez, basal-ganglia direct/indirect loop,
nigrostriatal, cortico-cerebellar, commissures).

**How it was closed.** The two basal-ganglia loops got new **Kandel** p983 quotes naming
the direct / indirect pathways (Albin scheme); the other four reuse quotes already verified
for their member projections (nigrostriatal p982, corticopontine p958, Papez p1096, corpus
callosum p549), so no quote text is duplicated. Same judge + on-page gate as #6.

### 8. `targets` (classification), 4 / 25 missing (**easy**)

**What.** Four non-receptor target classification nodes: carbonic anhydrase, PDE5, T-type
Ca channel (`cav_t`), melanocortin receptor group.

**Why not verified.** Absent from Stahl Essential.

**How to tackle.** All four are textbook-standard targets, one **IUPHAR/BPS** page or a
pharmacology-textbook sentence each (same corpus as #3, so do them together). 4 nodes.

### 9. `structures` (anatomy), DONE (52 / 52 verified)

**What.** Every region-anatomy node is now verified.

**How it was closed.** 48 of 52 were already verified against Kandel; the last four
(claustrum + fornix, which Kandel does not describe in prose) were closed against the
newly-wired **Nieuwenhuys** atlas (corpus #6): the claustrum as "a thin sheet of grey
matter ... between the putamen and the insular cortex" (p421) and the fornix as "a large
fibre system that connects the hippocampal formation with the septum and the hypothalamus"
(p64). Same Sonnet judge + verbatim on-page gate as the pathways.

### 10. `drug_categories`, DONE (156 / 158 verified)

**What.** One node per drug: its class classification ("this drug is an SSRI / TCA /
SGA / ..."), `category_provenance`.

**How it was closed.** Stahl's Prescriber's Guide prints the class verbatim in the
bullet(s) under each drug's "## Class" heading. A Haiku pass extracted each drug's
verbatim class descriptor (with a fallback for 9 drugs whose descriptor was displaced by
the PDF-to-Markdown layout scramble), a Sonnet pass judged whether that descriptor
supports our category IDs (catching mis-mappings, the way the NbN gate does), and the new
`tools/apply_category_sources.py` re-found each accepted quote in the drug's Stahl page
range and wrote it as a `verified` `category_sources` entry. `check_data.py`'s quote gate
re-confirms all of them on-page. This mirrors the drug-binding extract/judge/quote-check
pipeline; a programmatic-only pass was not enough because our `categories` are a coarse
re-mapping of Stahl's class line, which is exactly what the judge validates.

**The 2 left unsourced (flagged, not forced):**
- `naltrexonebupropion`: Stahl's class line calls it a "weight management medication",
  which does not back our `substance_use` category. A genuine mismatch to review, not a
  quote to paper over.
- `serdexmethylphenidate`: Stahl gives no standalone class-descriptor bullet (only its
  NbN line "dopamine, norepinephrine multimodal stimulant" and prodrug-formulation
  notes), so there is no clean class sentence to quote.

### 11. `references`, DONE (0 missing, not in headline)

**What.** `carbonic_anhydrase` and `pde5` (both non-receptor targets) carried no
`wikipedia` link, so their panel showed `NOSOURCE`.

**How it was closed.** Added the two Wikipedia URLs to their `DRUG_TARGETS` entries in
`generate_data.py` (the live panel fetch follows redirects, so `/wiki/PDE5` resolves to the
enzyme article). `references` is now 100%.

---

## Recommended attack order

Ordered by **value per unit effort**, not by raw node count:

1. ~~`drug_categories`~~ **DONE** (156/158 verified via `apply_category_sources.py`;
   headline 55% to 65%).
2. ~~`references` (2)~~ **DONE** (Wikipedia URLs for carbonic anhydrase + PDE5).
3. ~~`circuits` (6) + `projection_groups` (10)~~ **DONE** (16 nodes verified against Kandel
   + Stahl Essential via the existing quote-source mechanism; headline to 66%).
4. ~~`structures` (4) + `projections` (13 of 17)~~ **DONE** (claustrum + fornix structures
   and 7 limbic/olfactory/commissural pathway families verified against the newly-wired
   **Nieuwenhuys** atlas, corpus #6; headline 66% to 67%). Only claustrum to frontal +
   claustrum to insula remain (not stated on any single Nieuwenhuys page; folded into #7).
5. **`receptors` mechanism (26) + `targets` (4)**, wire **IUPHAR/BPS Guide to
   Pharmacology** as corpus #7; it closes both in one integration.
6. ~~`receptor_locations` Phase 1 (197)~~ **DONE** (GtoPdb corpus #7; species-flagged;
   headline 67% to 78%). **Phase 2: `target_locations` (124) then the residual
   `receptor_locations` (186)**, still ~87% of the remaining gap and the hardest. Build
   `fetch_allen.py` against the **Allen Human Brain Atlas** (the one source that reaches the
   deep nuclei AND covers non-receptor targets), prove on targets (2a) then receptors (2b).
   Full scope in the "Phase 2 plan" section above.
7. **`drug_bindings` (12) + the last 2 `projections`**, opportunistic: a PDSP refresh for
   the bindings, claustrum-specific primary lit for claustrum to frontal / insula; some may
   honestly stay `tentative`/`llm`.

**Books/sources we likely still need (beyond the seven wired):**
- the **Allen Human Brain Atlas** (microarray + PACall), the Phase 2 pick, unlocks the 310
  remaining location nodes incl. the deep nuclei; by far the largest lever left (scoped above).
- **IUPHAR/BPS Guide to Pharmacology** for the 30 remaining **classification** nodes (26
  `receptors` mechanism + 4 `targets`): note its **tissue-distribution** API is already wired
  as corpus #7 `gtopdb` (Phase 1), but its receptor *classification* pages are a separate,
  still-open use.
- **NCBI/PubMed primary literature** as the genuine last resort for the handful of claims
  (claustrum-to-frontal/insula connectivity, a few tentative subtype affinities) no
  reference book states.
