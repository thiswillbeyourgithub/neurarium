# Sourcing gaps: what is not yet `verified`, why, and how to tackle it

The dataset grades every **node** (any sourceable datum, see `CLAUDE.md` "Nodes")
`llm` < `sourced` < `verified`. `verified` is the top grade: a quote was
programmatically confirmed present in a cited source page (or a Ki row in the PDSP
CSV). This document lists everything **not** at `verified`, says **why**, and gives an
**idea to tackle it**. Numbers come straight from `meta.provenance_stats` (regenerate
with `python tools/generate_data.py`, print the table with `python tools/check_data.py`),
so re-derive them after any data change rather than trusting the counts below forever.

Made with the help of Claude Code.

## Snapshot (2026-07-04, after the Stahl-Essential receptor-mechanism pass)

Headline: **1673 / 1743 knowledge nodes backed (96%)**. In the tally a bare `llm`
grade counts as **missing** ("an LLM asserted it from memory" = no document), so
"missing" below means `llm` or no source at all. 70 knowledge nodes are missing.

> **Recently closed.** Several smaller kinds are now fully (or nearly) sourced:
> - `receptors` (mechanism) 54/56 verified: **30 more** subtypes closed against **Stahl
>   Essential** by adding verbatim classification quotes to `STAHL_ESSENTIAL_RECEPTOR_QUOTES`
>   (serotonin 2A/2C/4/6/7 + 1A/5A via one sign sentence, 2B + 7 individually; the adrenergic
>   α1/α2B/α2C/β1-3 via the NE-receptor enumeration; the opioid μ/δ/κ, CB1, adenosine A2A,
>   σ1, MT1/MT2, H3/H4; plus mGluR6, muscle nAChR, GABA-A-ρ reusing existing umbrella quotes).
>   The 2 that stay `llm` are 5-HT1E and 5-HT1F, which never appear in the Essential corpus.
>   (α2D is a stub, not a counted node.)
> - `receptor_locations` 360/383 verified: **Phase 1** wired the **Guide to Pharmacology**
>   tissue-distribution API (corpus #7 `gtopdb`, 197 regions with an assay species), then
>   **Phase 2b** ran the Allen microarray (corpus #8) over the receptor genes to source the
>   residual 163. Where Allen confirms a region GtoPdb had only in a rat/mouse assay, both
>   sources back it and the panel prefers the Human tag (91 of 109 amber receptor tags
>   cleared). The 23 that stay `llm` are Allen's honest limits: off-atlas bases (olfactory
>   bulb, pituitary, subthalamic nucleus, unsampled) + regions sampled but not detected.
> - `target_locations` 108/124 verified: **Phase 2a** wired the **Allen Human Brain
>   Atlas** microarray (corpus #8 `allen_ahba`). `fetch_allen.py` aggregates Allen's
>   `PACall` present/absent detection boolean across the 5 available human donors into a
>   deterministic present/absent per (gene, region) (no judge), and the confirm-only merge
>   upgraded 108 existing "Found in" regions across 22 non-receptor targets. The 16 that
>   stay `llm` are honest microarray limits: SERT + NET **terminal** regions (their mRNA is
>   in the raphe / locus-coeruleus cell bodies, which DO confirm, not the cortical/limbic
>   terminals) + the melatonin receptor group. Every Allen source is `species: "Human"`.
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
> (Allen Phase 2a) to 95% (Allen Phase 2b) to 96% (Stahl-Essential receptor mechanisms).
> The table below is the current state.

| Node kind | Missing | Total | Share of the gap | Difficulty | Best lever |
| --- | ---: | ---: | ---: | --- | --- |
| `receptor_locations` | 23 | 383 | 32.9% | limit | 360 done (GtoPdb + Allen); the 23 are off-atlas / not-detected |
| `target_locations` | 16 | 124 | 22.9% | limit | 108 done via Allen; the 16 are mRNA-at-source honest `llm` |
| `drug_bindings` | 12 | 703 | 17.1% | Medium | PDSP refresh + primary lit |
| `drug_categories` | 9 | 165 | 12.9% | limit | 7 are the recreational drugs (no Stahl class) + 2 flagged |
| `projections` | 4 | 103 | 5.7% | Hard | claustrum primary lit |
| `targets` (classification) | 4 | 25 | 5.7% | limit | absent from Stahl Essential; needs IUPHAR/textbook |
| `receptors` (mechanism) | 2 | 56 | 2.9% | limit | 54 done (Stahl Essential); 5-HT1E/1F absent from corpus |
| `receptor_locations` (done) | 0 | 360 | closed | done | GtoPdb (corpus #7) + Allen (corpus #8) |
| `target_locations` (done) | 0 | 108 | closed | done | Allen AHBA (corpus #8) |
| `receptors` (done) | 0 | 54 | closed | done | Stahl Essential (corpus #3) |
| `structures` (anatomy) | 0 | 52 | **DONE** (52/52) | done | Kandel + Nieuwenhuys |
| `circuits` | 0 | 6 | **DONE** (6/6) | done | Kandel prose |
| `projection_groups` | 0 | 10 | **DONE** (10/10) | done | Stahl Essential / Kandel |
| `references` (Wikipedia links) | 0 | 298 | **DONE** (not in headline) | done | Wikipedia URLs |

**The shape of the problem:** both the expression-location gap (Phases 1, 2a, 2b) and the
receptor-mechanism gap are now essentially closed, so the 70 residual nodes are spread thin
and no single lever dominates, and most of what remains is a **hard limit rather than a gap to
chase**: the 23 `receptor_locations` + 16 `target_locations` are off-atlas / unsampled bases or
a transporter's mRNA sitting at the source nucleus not the terminal; the 9 `drug_categories`
are the 7 recreational drugs (a category Stahl has no class line for) + the 2 long-flagged
mismatches; the 4 `targets` + 2 `receptors` (5-HT1E/1F) are simply absent from Stahl Essential.
Only the 12 `drug_bindings` and 4 `projections` are genuine gaps a fresh PDSP pull or primary
literature could close.

Five book corpora + three data corpora are wired into `SOURCE_CORPORA` today (`stahl`,
`kandel`, `stahl_essential`, `carlat`, `nieuwenhuys`, plus the `pdsp_ki` CSV, the `gtopdb`
tissue API, and the `allen_ahba` microarray). The book-prose wins those allow are now
essentially exhausted (see the sourcing memory); the remaining gaps mostly need a
receptor-classification database (for the last 6 classification nodes: 5-HT1E/1F + the 4
non-receptor targets), a fresh PDSP pull (the 12 bindings), or primary literature (the last
two claustrum pathways). The 7 recreational `drug_categories` have no Stahl class line by
construction and the two expression-location residuals are hard atlas limits, so neither is a
book-prose gap.

---

## Phase 2 plan: Allen AHBA expression sourcing (the 310 remaining expression nodes)

> **Status: Phase 2 COMPLETE** (2a targets + 2b receptors both shipped, corpus #8
> `allen_ahba`). `target_locations` 108/124 verified, `receptor_locations` 360/383 verified
> (197 GtoPdb + 163 Allen). The residual 39 expression nodes are Allen's honest limits
> (off-atlas / unsampled bases + not-detected + transporter-terminal mRNA), not a gap to
> chase. The section below is kept as the design record of how the pipeline was built.

**Goal (met).** Source the **310** expression nodes GtoPdb (Phase 1) could not reach: the
**186** residual `receptor_locations` (across 44 receptors GtoPdb had no tissue data for;
Phase 2b, now 163 verified + the rest off-atlas) + the **124** `target_locations` (Phase 2a,
now 108 verified + 16 honest microarray-limit `llm`), against the **Allen Human Brain Atlas
(AHBA) microarray**. Same shape as Phase 1: **confirm-only** (upgrade the grade on an
*existing* LLM-authored "Found in" region, never add or drop a region), one graded node per
`(gene, region)` pair, quote-gated author-side.

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
- `tools/fetch/fetch_allen.py` — resolve each gene's probe(s), download the per-donor microarray +
  `PACall` + `SampleAnnot` + `Ontology` from the Allen API (`api.brain-map.org`) /
  `human.brain-map.org` bulk, apply the crosswalk, aggregate PACall over each base's samples,
  emit `sources/allen/pages/<gene>.md` + `sources/allen/worklist.json`. Stdlib urllib, polite,
  idempotent, `--only`/`--refresh` (mirror `fetch_gtopdb.py`). Filters to our genes' probes
  early so it caches only the slice, not the multi-hundred-MB full CSVs.
- The Allen->base **crosswalk** + **`TARGET_GENES`** map (live in `fetch_allen.py`).
- **Apply step** — extend `tools/sourcing/apply_location_sources.py` with a deterministic
  `--corpus allen` mode (no judged file: it reads the worklist + the *existing* location
  lists straight from the emitted data and confirms) rather than a second tool, so the
  merge-into-`location_sources.json` + dedup logic is not duplicated. Handles **both**
  receptors and targets (the emitter is already shared).
- `allen_ahba` **corpus #8** in `SOURCE_CORPORA` (`generate_data.py`) with the Hawrylycz
  citation; emitted into `meta.source_corpora`; the README `SOURCES_TABLE` picks it up.
- **Attribution**: Hawrylycz 2012 in the About panel's sources block.
- **Author-side `sources/allen/` tree** (gitignored: `raw/` download cache, `pages/<gene>.md`,
  `worklist.json`), documented in `CLAUDE.local.md` alongside the `sources/gtopdb/` tree.
- **Docs**: `CLAUDE.md` (corpus #8 in Source provenance) + `tools/README.md` (Tool reference), this file, the
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

### 3. `receptors` (mechanism classification), 2 / 56 missing (**mostly DONE**)

**What.** The per-receptor mechanism node (neurotransmitter / ionotropic-vs-metabotropic
/ excit-inhib-modulatory / pre-post). **54 of 56 are now verified against Stahl Essential.**

**How it was closed.** A second Stahl-Essential pass added verbatim classification quotes
to `STAHL_ESSENTIAL_RECEPTOR_QUOTES` in `generate_data.py` for 30 more subtypes: one 5HT
sign sentence (p136) covers 5-HT2A/2C/4/6/7 (excitatory) + 5-HT1A/5A (inhibitory), with 5-HT2B
(p131) and 5-HT7 (p146) individually; the adrenergic α1/α2B/α2C/β1-3 reuse the NE-receptor
enumeration sentence (p270); the opioid μ/δ/κ (p575), CB1 (p581), adenosine A2A (p457), σ1
(p311), MT1/MT2 (p455), and H3/H4 (p421-2) each name their receptor; and mGluR6, muscle nAChR,
and GABA-A-ρ reuse the existing metabotropic-glutamate / nicotinic / GABAA-C umbrella quotes.
Each quote passes `check_data.py`'s verbatim on-page gate (the "table-cell gate" approach:
the gate strips markdown, so a table cell already matches, though in practice all 30 came from
running prose).

**The 2 that stay `llm`.** 5-HT1E and 5-HT1F: neither receptor is named anywhere in the
Stahl Essential corpus (they appear only inside binding-affinity table cells for 5-HT1E, and
not at all for 5-HT1F), so there is no classification sentence to quote. They would need
**IUPHAR/BPS Guide to Pharmacology** (canonical receptor-classification database) or a
neuropharmacology textbook (Katzung, Rang & Dale). 2 nodes; not forced.

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

### 8. `targets` (classification), 4 / 25 missing

**What.** Four non-receptor target classification nodes: carbonic anhydrase, PDE5, T-type
Ca channel (`cav_t`), melanocortin receptor group.

**Why not verified.** Confirmed absent from Stahl Essential during the receptor-mechanism
pass: "anhydrase"/"carbonic" never appears, "T-type" calcium channel is never named (the
book discusses only N, P/Q, and L-type VSCCs), and "melanocortin" appears only inside
"pro-opiomelanocortin (POMC)" (a peptide precursor), never as the receptor class. The only
"phosphodiesterase" mention is about PDE9/10 in a schizophrenia passage, not PDE5, so citing
it for PDE5 would misattribute the isoform (rejected as dishonest to the gate).

**How to tackle.** All four are textbook-standard targets, one **IUPHAR/BPS** page or a
pharmacology-textbook sentence each (same lever as #3's residual 5-HT1E/1F). 4 nodes.

### 9. `structures` (anatomy), DONE (52 / 52 verified)

**What.** Every region-anatomy node is now verified.

**How it was closed.** 48 of 52 were already verified against Kandel; the last four
(claustrum + fornix, which Kandel does not describe in prose) were closed against the
newly-wired **Nieuwenhuys** atlas (corpus #6): the claustrum as "a thin sheet of grey
matter ... between the putamen and the insular cortex" (p421) and the fornix as "a large
fibre system that connects the hippocampal formation with the septum and the hypothalamus"
(p64). Same Sonnet judge + verbatim on-page gate as the pathways.

### 10. `drug_categories`, 9 / 165 missing (156 verified against Stahl)

**What.** One node per drug: its class classification ("this drug is an SSRI / TCA /
SGA / ..."), `category_provenance`.

**The 7 recreational drugs stay `llm` by construction.** LSD, MDMA, cocaine, DMT,
methamphetamine, nicotine, THC were added under a new **"Recreational / psychoactive"**
category that Stahl's Prescriber's Guide has no class line for (the guide covers prescription
psychiatric drugs), so there is no verbatim class descriptor to quote. Their *bindings* are
fully PDSP-Ki-verified; only the category label is unsourced, and honestly so.

**How it was closed.** Stahl's Prescriber's Guide prints the class verbatim in the
bullet(s) under each drug's "## Class" heading. A Haiku pass extracted each drug's
verbatim class descriptor (with a fallback for 9 drugs whose descriptor was displaced by
the PDF-to-Markdown layout scramble), a Sonnet pass judged whether that descriptor
supports our category IDs (catching mis-mappings, the way the NbN gate does), and the new
`tools/sourcing/apply_category_sources.py` re-found each accepted quote in the drug's Stahl page
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
5. ~~`receptors` mechanism (30 of 32)~~ **DONE** (verbatim classification quotes added to
   `STAHL_ESSENTIAL_RECEPTOR_QUOTES`; 54/56 verified; headline 95% to 96%). The residual
   6 classification nodes (5-HT1E/1F + the 4 non-receptor `targets`) are absent from Stahl
   Essential and would need **IUPHAR/BPS Guide to Pharmacology** or a pharmacology textbook.
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

## Candidate new data *dimensions* (surveyed 2026-07-26)

The sections above are about grading nodes we already have. This one is about node kinds we
do **not** have: axes the dataset could gain. Each entry says what exists in the world, what
it would cost, and the verdict, so a later session does not re-survey it.

### Receptor expression **density** (how much, not just where)

Today a "Found in" region is a boolean: a receptor is in a region or it is not. So M5 reads as
equally at home in a dozen regions, which is not what the biology says. Three candidate sources:

- **Allen AHBA microarray intensity** (corpus #8, *already downloaded*). `fetch_allen.py` reads
  only `PACall.csv` (the present/absent boolean) and deliberately skips the ~400 MB
  `MicroarrayExpression.csv` sitting in the same donor zips. That matrix gives a continuous
  per-sample value; z-scored within donor and averaged per base region it yields a **relative**
  expression profile. Measured feasibility over the 5 local donors (84 genes, 76 owners),
  scoring each gene by the median pairwise cross-donor Pearson r of its per-region profile:

  | cross-donor r | genes | owners (receptors / targets) |
  |---|---|---|
  | >= 0.7 | 54 / 84 | 50 (29 / 21) |
  | >= 0.5 | 68 / 84 | 62 (37 / 25) |
  | >= 0.3 | 78 / 84 | 70 (45 / 25) |

  The profiles reproduce textbook anatomy: `SLC6A3` peaks at substantia nigra (+4.7) and VTA
  (+4.1), `SLC6A4` at raphe (+5.8), `DRD2` at putamen / caudate / accumbens, `HTR2A` across
  cortex with cerebellum lowest (-1.9). **`CHRM5` (r = +0.86) peaks at substantia nigra (+2.5)
  and VTA (+2.2)** and is lowest in caudate / cerebellum, matching M5's known role on midbrain
  dopamine neurons: the M5 question has a real answer in data we already hold. The low-r genes
  (`HTR2B` -0.09, `HTR3A` -0.03, `CHRM2` +0.05, `ADRB1` +0.16, `HRH1` +0.37) sit near the array
  noise floor, so the reliability score doubles as an **honesty gate**: publish a density
  profile only where the donors agree, leave the rest boolean.
  Caveats that must ship with it: it is **mRNA, not protein**, it is **relative, not fmol/mg**,
  and (the already-documented Allen caveat) transcript sits in **cell bodies, not terminals**,
  which is exactly why SERT peaks at raphe rather than at the cortex where the protein works.
- **EBRAINS / siibra quantitative autoradiography** (Zilles, Palomero-Gallagher, Amunts): real
  **protein** density in fmol/mg. But only **16 receptor types**, of which 12 map onto our 62
  (`5ht1a`, `5ht2a`, `ampa`, `d1`, `gaba_a`, `gaba_b`, `m1`, `m2`, `m3`, `nmda`, `kainate`,
  `mglur2`), they are subtype-blind ("5-HT2", not 5-HT2A), and they are resolved on
  **cytoarchitectonic cortical areas** of the Julich-Brain, so none of our deep nuclei are
  covered. Notably there is **no M4 and no M5** (no selective radioligand), so the source that
  would be most authoritative cannot answer the question that prompted this survey.
- **PET tracer maps** (Hansen et al. 2022, `netneurolab/hansen_receptors`): 19
  receptors/transporters, in-vivo human, but cortical parcellations (Schaefer / Lausanne) and
  **CC BY-NC-SA 4.0**, whose ShareAlike is a poorer fit than Allen's cite-and-use terms.

**Verdict: adopted.** Shipped as two graded node kinds (`receptor_density` / `target_density`)
reusing the corpus #8 quote-gate pipeline: the whole profile (per-region z plus the cross-donor
`r`) is written into the quote itself, so the verbatim gate covers the numbers a reader would
use to judge it, and the panel's pill tooltip exposes them inside the app. The floor shipped at
**r >= 0.5** (`DENSITY_MIN_R` in `tools/fetch/fetch_allen.py`), yielding **53 published profiles
(36 receptors, 17 targets)**; a gene below it publishes nothing, so a noisy profile never
reaches the viewer. Rendered as a per-region bar plus the signed z, never as fmol/mg.

### Drug **blood-brain-barrier** penetration

- **B3DB** (`theochem/B3DB`, **CC0**, TSV on GitHub) is the best open dataset: 7982 compounds
  with a BBB+/BBB- label, 1058 with a numeric `logBB`. Matching it by name + brand against our
  179 drugs gives **130 with a label, 59 with a numeric logBB**.
- Both figures are **traps for this corpus**, which is why this is not adopted:
  1. The label is degenerate. Of the 130 matched, **125 are BBB+ and 5 BBB-**: a psychiatric
     corpus is pre-selected for brain penetration, so the flag carries almost no information.
     It is also noisy at the edges (B3DB labels **propranolol** BBB-, the textbook *penetrant*
     beta-blocker; 4 of our drugs get conflicting labels across its source rows).
  2. `logBB` is the **wrong parameter**. It is a *total* brain:plasma ratio, so it tracks
     lipophilicity and non-specific tissue binding rather than free drug at the receptor. In
     our own matched set escitalopram sits at -0.37 and sertraline at +1.60, a ~100x spread
     between two SSRIs with comparable clinical SERT occupancy. Presenting that as "how much
     reaches the brain" would actively mislead.
- The parameter that *is* meaningful is **Kp,uu,brain**, the *unbound* brain-to-plasma ratio
  (1.0 = free equilibrium, < 1 net efflux, > 1 net influx; industry treats > 0.3-0.5 as
  penetrant). See Loryan et al. 2022, *Pharm Res* (PMC9246790). But there is **no open
  machine-readable Kp,uu database**: that paper is an industry survey with no compound table,
  and the compiled sets live in small paywalled tables (Kalvass 2007, 34 drugs; Liu 2009, 18
  compounds), mostly **rodent**. Corpus-scale coverage is not attainable.

**Verdict: do not add a corpus-wide numeric field.** The honest version is a small
hand-curated, quote-gated fact on the few drugs where brain entry is actually a clinical
story (P-gp substrates such as paliperidone; the poorly-penetrant benzamides sulpiride /
amisulpride; peripherally-restricted agents), sourced from Stahl's pharmacokinetics prose
like any other node, rather than a number pinned to all 179.

### Drug **metabolism**: which CYP a drug touches, and which enzyme makes a metabolite

Two halves of one ask: (a) be able to look up which drug interacts with which CYP, and
(b) when we list an active metabolite, record which enzyme produced it. Both are
pharmacokinetics, so neither has a place in the 3D scene (hepatic enzymes are not brain
regions, and the brain's own CYP expression is a separate and far weaker story). They are
panel + browse data.

**What the corpora we already hold contain.** Measured, not guessed:

- **Stahl (corpus #1) is the natural source and it is already structured.** All 158
  monographs carry a `Pharmacokinetics?` block and a `Drug Interactions?` block; **92**
  and **80** of them respectively name a CYP isoform, in terse role-explicit lines
  ("Substrate for CYP2D6 and CYP1A2", "Metabolized primarily by CYP1A2", "Inhibits
  CYP2C19", "CYP3A4 inducers may increase clearance of ..."). Feasibility against the
  existing quote gate was measured directly: of the CYP-bearing bullets, **109/113 (96%)**
  of the pharmacokinetics ones and **176/191 (92%)** of the interaction ones are already
  **verbatim** on that drug's page range, so `pages_dir` gating applies unchanged. The
  misses are page-break artifacts (a wrapped line, a spliced-in DOI footer), fixable by
  shortening the quote.
- **Wikipedia EN (corpus #9)**, already stored for 220 of our 235 drugs: **128** name at
  least one isoform (median 2 per page, max 9). It adds **51 drugs Stahl has no CYP line
  for**, which is exactly the non-Stahl roster (the European benzodiazepines, the
  barbiturates, the recreational agents). Prose, not a table, so it needs the same
  extract-then-judge pass a binding gets.
- **Union coverage of the two: 137 / 235 drugs.** Isoform spread is the expected one:
  3A4 (61), 2D6 (44), 1A2 (25), 2C19 (16), 2C9 (10), then a tail.
- **Third-party interaction tables** (FDA's "Table of Substrates, Inhibitors and
  Inducers", Indiana's Flockhart table, DrugBank). The FDA one is US-government work and
  so reusable, and it is where the strong/moderate/weak vocabulary comes from, but it
  lists *index and example* drugs rather than a full roster, and it is HTML with no
  machine-readable download. Its page 404'd from this session, so this paragraph is
  recalled, not verified: re-check before relying on it. Flockhart and DrugBank are not
  openly licensed. **None is needed to start**: the corpora we already hold cover more of
  *our* roster than an index-drug list would.

**The metrics.** Three, in increasing cost, and the recommendation is to stop after two:

1. **role** (categorical, always stated): `substrate` / `inhibitor` / `inducer`. This is
   the axis that carries the clinical meaning, and the only one every source states.
2. **strength** (ordinal, often stated): for a substrate `major` / `minor` (Stahl writes
   "primarily", "minor route"); for an inhibitor or inducer the regulatory `strong` /
   `moderate` / `weak` tiers. Ordinal on purpose. The fold-change in the victim drug's AUC
   that defines those tiers is essentially never in our corpora, and publishing a number
   we cannot source would repeat the `logBB` mistake above.
3. **a quantitative Ki / IC50 on the enzyme**: exists in the literature, scattered across
   papers, no open corpus-scale table. Skip, exactly as with Kp,uu. The ordinal tier is
   what a prescriber actually reasons with.

**The node kinds.** Two, both ordinary graded nodes under the existing contract:

- **`drug_enzymes`**, one node per (drug, enzyme, role) triple, on the drug as
  `enzymes[]`: `{enzyme, role, strength?, sources[]}`. Yield from the Stahl
  pharmacokinetics block alone: **75 substrate drugs, 20 inhibitors, 5 inducers = 86
  drugs**; a few hundred nodes once the interaction block and Wikipedia are folded in.
  Small enough not to swamp the headline the way per-region density would have.
- **`drug_metabolite_enzyme`**, the second half of the ask, on the existing metabolite row
  as `formed_by`: `{enzyme, reaction?, sources[]}`. **This one is genuinely thin.** Of our
  36 metabolite rows only **8** have a Stahl line naming both the metabolite and the
  forming enzyme ("Metabolized to an active metabolite, nortriptyline ... by demethylation
  via CYP1A2"), and most Wikipedia matches turn out to be the metabolite *inhibiting* an
  enzyme rather than being *made* by one. Expect roughly 10-15 of 36 sourceable and the
  rest honestly `NOSOURCE`. Still worth having: it is the prodrug story (why a CYP2D6 poor
  metabolizer gets no effect from codeine or tramadol). Do it as a small hand-curated set,
  not a pipeline.

Name the field **`enzyme`, not `cyp`**, and validate it against an `ENZYMES` vocabulary in
`generate_data.py` emitted into `meta.json` (like `drug_targets`): the non-CYP routes are
common and already show up in the corpus (UGT glucuronidation, plasma esterases, MAO-A/B,
flavin monooxygenase). Keep the reaction verb when the source states one ("demethylation",
"hydroxylation", "hydrolysis of the valine ester"), since it is what makes the row readable.

**Where it surfaces.** `showDrug` gains a **Metabolism** section beside the T½ chip, one
row per enzyme carrying a role glyph, the strength, and its own grade pill, shaped like
the Acts-on list. Each row is clickable into a new **Enzymes** browse section (mirroring
Receptors & targets) whose panel lists that enzyme's substrates, inhibitors and inducers.

**The payoff is derived, not stored.** An inhibitor (or inducer) of enzyme X plus a
substrate of X is a predicted pharmacokinetic interaction. Measured on the Stahl
pharmacokinetics lines *alone* that is already **1014 drug -> drug edges**. Compute it in
`js/data.js` like `flowSystems` and circuit membership, never author it, so it cannot
drift from the nodes; render the direction (A raises / lowers B's level). It must ship
with the caveat, in the caption and not only in a tooltip: an overlap is a flag to check,
never a contraindication, and the absence of an edge is not a safety claim. This is a
knowledge map, not a prescribing aid.

**Verdict: adopt, in two steps.** Step 1, the drug <-> enzyme roles out of Stahl's
pharmacokinetics block: it is regular enough to grep, so it needs **no LLM judge at all**
(the same argument that makes `apply_nbn_sources.py` stronger than a judge for the NbN
line), and it lands 86 drugs. Step 2, the Wikipedia sweep for the 51 drugs Stahl does not
reach, plus the metabolite `formed_by` hand-curation. Do **not** open with an external
interaction table.

## Candidate new *sources* for data we already hold (surveyed 2026-07-26)

Unlike the section above, this is not a new axis: it is a second opinion on nodes that already
exist. Same format, same purpose (do not re-survey it).

### GtoPdb ligand interactions as a **binding-affinity + direction** source

GtoPdb (IUPHAR/BPS Guide to Pharmacology) is already wired as corpus #7 for receptor expression
regions, through its `tissueDistribution` API. Its *other* half, the hand-curated
ligand-target interaction table, is a candidate second affinity source next to PDSP Ki (#5) and
the Wikipedia pharmacodynamics table (#9).

**What it is.** One versioned bulk file,
[`DATA/interactions.csv`](https://www.guidetopharmacology.org/DATA/interactions.csv) (7 MB,
24599 rows at version 2026.2, published 2026-06-15), so this is a PDSP-shaped corpus (one CSV,
one row per claim), not another paged-text corpus. Each row carries the target with its **gene
symbol** (the join we already use), the species, `Type` + `Action` (Agonist / Antagonist /
Inhibitor / Allosteric modulator, and Full agonist / Partial agonist / Inverse agonist /
Positive / Inhibition), the affinity as a pX **and** in nM, and a `PubMed ID` (21373 of 24599
rows have one). Affinity unit mix across the whole file: pIC50 9706, pKi 7116, pEC50 2655, pKd
2278, pKB 147, pA2 75.

**Measured against our corpus** (script kept out of the repo; numbers recomputed from the bulk
CSV, gene join case-folded because rodent rows use `Scn2a` where human rows use `SCN2A`):

| question | answer |
|---|---|
| our drug bindings GtoPdb has a usable affinity for | **454 / 1511** |
| of those, bindings that have **no Ki today** | **51** |
| bindings still with no Ki and nothing in GtoPdb | 221 |
| of the **58 drugs with zero measured Ki**, drugs GtoPdb reaches | **33** |
| `affinity_only` bindings GtoPdb could give a **direction** to | **193** |
| binding pairs GtoPdb knows that we do not model at all | 66 |
| non-modeled metabolites present in GtoPdb | **3 / 24** (norfluoxetine, norquetiapine, norzotepine) |

**It agrees with what we already hold.** On the 388 bindings where PDSP and GtoPdb both have a
Ki, the median disagreement is **1.5x** (77% within 3x, 92% within 10x), which is ordinary
inter-assay spread and good independent corroboration of the PDSP medians. On direction, where
we already state an action and GtoPdb states one: **224 identical, 25 compatible, 11 genuine
conflicts**. The conflicts are the interesting part, not noise: aripiprazole at 5-HT2A/2C/7
(we say antagonist from Stahl, GtoPdb says partial agonist), clozapine at 5-HT1A (agonist) and
M1 (positive allosteric, not antagonist), amisulpride and lumateperone at D2, nalmefene at
delta/kappa, levetiracetam at SV2A.

**Where the real value is.** Not bulk Ki fill (PDSP already covers 83% of bindings and GtoPdb
overlaps it heavily), but the two places PDSP structurally cannot reach:
1. **Targets radioligand-displacement panels do not assay.** The 33 drugs it unblocks are the
   GABA-A benzodiazepine site (diazepam pKi 7.8 human, clonazepam 8.7, flumazenil 9.0,
   alprazolam, flunitrazepam, triazolam), MAO-A/B (selegiline, phenelzine, tranylcypromine,
   moclobemide), acetylcholinesterase (donepezil, galantamine, rivastigmine), orexin
   (suvorexant, lemborexant, daridorexant), melatonin (melatonin, ramelteon, tasimelteon,
   agomelatine), plus SV2A, Nav, carbonic anhydrase and PDE5.
2. **Direction for the 816 `affinity_only` bindings**, which today are listed but never
   animated because PDSP says only *that* a drug binds. A curated `Type`/`Action` with a PubMed
   id would turn 193 of them into real directional bindings.

**What it will not fix.** 25 of the 58 Ki-less drugs stay empty, and they are a coherent set:
most benzodiazepines and Z-drugs (lorazepam, temazepam, oxazepam, midazolam, chlordiazepoxide,
estazolam, flurazepam, quazepam, clorazepate, zaleplon, zopiclone, eszopiclone), the
neurosteroids (brexanolone, zuranolone), and the broad anticonvulsants (valproate,
carbamazepine, oxcarbazepine, gabapentin, pregabalin). GtoPdb has ligand records for most of
them but curates **no interaction row**, because its tables are built per target family from
selected literature and are deliberately not exhaustive. Metabolite coverage is likewise thin
(3 of 24). Name resolution needs an alias map like the Wikipedia one: GtoPdb files INN spellings
(benzatropine, pipotiazine, flupentixol, dosulepin), markup-bearing names
(`<i>N</i>-desalkylquetiapine`) and separate enantiomer entries.

**Licensing.** The database is **ODbL**, its contents **CC BY-SA 4.0** (already stated in
`fetch_gtopdb.py`). CC BY-SA is the licence we hold Wikipedia prose and molecule images under, so
that half is settled; ODbL's share-alike on a *derived database* is the new part, and it is
satisfied in practice because the emitted `public/data/` is published openly in an AGPL repo.
Wiring this means adding the attribution + licence line to the corpus registry entry.

**Verdict: adopted.** Shipped in v3.26.0 as corpus #11 `gtopdb_ki`, scoped to what PDSP cannot
reach. It reuses the existing `pages_dir` quote gate unchanged (the bulk CSV is flattened to one
quotable row line per interaction under `data_sources/gtopdb/pages_ki/<slug>.md`), and joins our
targets by gene symbol exactly like corpus #7. Priority is PDSP first, GtoPdb second, Wikipedia
third, so no existing `verified` Ki moved.

What actually landed: **35 Ki-less bindings gained a measured affinity** (393 already had one and
were left alone), and **193 `affinity_only` bindings gained a curated direction**, written as
`provisional_action`. Corpus-wide, measured-Ki coverage went **83% -> 86%** and the drugs with no
measured affinity at all **58 -> 37**; the 37 that remain are the ones no binding database reaches
(benzodiazepines and Z-drugs at the GABA-A modulatory site, neurosteroids, broad-mechanism
anticonvulsants). The applier reports **28 compatible refinements** (inverse-agonist vs
antagonist, partial-agonist vs agonist: same effect, finer wording) and **10 genuine direction
conflicts** separately, resolving neither: ours wins in the data, and the disagreement is printed
for a human.

Those 193 newly-directional bindings **do** drive the 3D layer (decided in v3.27.0). The effect is
a deepening rather than an unlock: no drug became newly focusable, but 37 of the 40 affected drugs
light at least one more region (amitriptyline +9, its five muscarinic sites; risperidone,
haloperidol and ketanserin +6), and 17 gain an ascending flow system through a canonical
autoreceptor (clozapine histaminergic via H3, amitriptyline cholinergic via M2, chlorpromazine
noradrenergic via alpha2A/B/C, several serotonergic via 5-HT1A/1B/1D). Because per-drug flow
intensity is normalized to the strongest engaged system, this also re-scales the overlays that
were already there.

## Drug-roster coverage: what the Wikipedia lists have that we do not (surveyed 2026-07-26)

Not a sourcing gap but a **coverage** gap, kept here because it is the same kind of survey
(measure once, write it down, do not re-survey). Prompted by noticing bromazepam and
clotiazepam were absent.

**Method.** Every generic name on the three English Wikipedia roster pages
([List of psychotropic medications](https://en.wikipedia.org/wiki/List_of_psychotropic_medications),
[List of psychiatric medications](https://en.wikipedia.org/wiki/List_of_psychiatric_medications),
[List of psychiatric medications by condition treated](https://en.wikipedia.org/wiki/List_of_psychiatric_medications_by_condition_treated))
diffed against our 179 drug ids, with an alias map for the spellings that differ
(dextroamphetamine -> `amphetamine_d`, valproic acid / sodium valproate / divalproex ->
`valproate`, flupentixol -> `flupenthixol`, pipotiazine -> `pipothiazine`, allopregnanolone ->
`brexanolone`, ...). **68 names** come back missing.

**The lists are themselves incomplete**, so this is a lower bound, not a target: clotiazepam
appears on none of the three, which is exactly how it went unnoticed. The upper bound worth
aiming at is a marketing-status list (EMA / ANSM / FDA), not a wiki roster.

Sorted by whether adding one would actually teach a visitor something:

**Tier 1: marketed, mechanistically or geographically distinct (35).** The real gap. Mostly
European/Japanese agents a US-centric corpus (Stahl 8th ed.) omits, so each needs the non-Stahl
sourcing route (Wikipedia pharm #9 + PDSP #5 + GtoPdb #11 + FR brands #10), the one already used
for cyamemazine / tropatepine / loflazepate.

| family | missing |
|---|---|
| benzodiazepines + relatives | bromazepam, clotiazepam, clobazam, nitrazepam, lormetazepam, loprazolam, brotizolam, prazepam, tofisopam |
| conventional antipsychotics | benperidol, bromperidol, pipamperone, melperone, prothipendyl, perazine, chlorprothixene, levomepromazine, fluspirilene, prochlorperazine |
| sedating antihistamines | promethazine, alimemazine, niaprazine |
| anticonvulsants used in psychiatry | phenobarbital, primidone, phenytoin, perampanel |
| anticholinergic / antiparkinsonian | biperiden, scopolamine |
| other anxiolytics + hypnotics | meprobamate, clomethiazole |
| substance-use + adjuncts | baclofen, cytisine, naloxone, ondansetron, tizanidine |

Highest value inside Tier 1: the conventional antipsychotics (they would populate D2/5-HT2A/H1/M1
binding space we already model), then the benzodiazepines (cheap: one `gaba_a` PAM binding each,
and the class is currently 15 members with several European mainstays absent).

**Tier 2: obsolete or withdrawn, historically real (21).** Worth adding only if the goal becomes
"the history of psychopharmacology": mesoridazine, zimelidine, indalpine, alpidem, methaqualone,
chloral hydrate, glutethimide, sulfonmethane, azacyclonol, clorgiline, pargyline, calcium
carbimide, rubidium chloride, phenazepam, nimetazepam, and the barbiturates amobarbital,
butobarbital, cyclobarbital, pentobarbital, secobarbital, thiopental.

**Tier 3: never marketed / research compounds (12).** Skip. Almost all are the abandoned
non-benzodiazepine GABA-A modulator programme: divaplon, fasiplon, indiplon, lorediplon,
necopidem, ocinaplon, pagoclone, panadiplon, pazinaclone, saripidem, suriclone, taniplon.

**Not psychiatric (1).** itopride (a prokinetic; it is on the list for its D2 antagonism).
