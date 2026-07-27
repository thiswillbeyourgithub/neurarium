# Sourcing gaps: what is not yet `verified`, why, and how to tackle it

The dataset grades every **node** (any sourceable datum, see `CLAUDE.md` "Nodes")
`llm` < `sourced` < `verified`. `verified` is the top grade: a quote was
programmatically confirmed present in a cited source page (or a Ki row in the PDSP
CSV). This document lists everything **not** at `verified`, says **why**, and gives an
**idea to tackle it**. Numbers come straight from `meta.provenance_stats` (regenerate
with `python tools/generate_data.py`, print the table with `python tools/check_data.py`),
so re-derive them after any data change rather than trusting the counts below forever.

Made with the help of Claude Code.

## Snapshot (2026-07-27, after the GtoPdb classification pass and the metabolism pass)

Headline: **3799 / 3969 knowledge nodes backed (96%)**. In the tally a bare `llm`
grade counts as **missing** ("an LLM asserted it from memory" = no document), so
"missing" below means `llm` or no source at all. 170 knowledge nodes are missing.

> **What the GtoPdb classification pass (corpus #12) just did, same day:** 232 missing to
> 170, 94% to 96%. `receptor_class` 30 to **55 / 56** (only sigma-1 left, a GtoPdb
> `other_protein` whose type does not assert our "chaperone"), `receptor_sign` 13 to
> **43 / 56**, `receptors` family 54 to **56 / 56** (5-HT1E and 5-HT1F, which the Essential
> corpus never names), `targets` 16 to **20 / 20**, plus the last `target_polarity` (the α2
> autoreceptor sentence, Stahl Essential p271) and the last 2 `references` (a Wikipedia link
> for the tuberomammillary nucleus). `receptor_synaptic` is untouched: GtoPdb has no
> pre/post-synaptic field at all.
>
> **The metabolism pass, same day**, added 109 `drug_enzymes` nodes from the Wikipedia CYP sweep
> (62 drugs Stahl has no monograph for) plus 17 `drug_metabolite_enzyme` nodes, a new kind for which
> enzyme forms each active metabolite. All verified, so they grow the denominator without touching
> the gap: 3843 to 3969 nodes, the same 170 missing, still 96%. The table below is unchanged by them.
>
> **The earlier drop from 96% (1673 / 1743) to 94% is still worth naming**, because the
> denominator grew faster than the gap for two structural reasons:
> - **The receptor classification node was split into four independent sub-claims**
>   (neurotransmitter `family`, mechanism `receptor_class`, `sign`, `synaptic` site). One
>   grade per receptor became four, and the attributes a quote never actually asserted
>   stopped riding the family quote's grade. That split was 117 missing nodes; the GtoPdb
>   pass closed 55 of them and 62 remain. They were never new ignorance; they were ignorance
>   that used to be hidden.
> - **70 drugs were added outside Stahl's roster** (the roster pass at the end of this file,
>   v3.28 to v3.29). Stahl is where the class line and most binding quotes come from, so each
>   non-Stahl drug arrives with an unsourceable `drug_categories` node, and the barbiturates
>   and benzodiazepines arrive with a GABA-A binding no affinity database assays.
>
> **Node kinds that landed since, all at 100%:** `drug_brands` (469), `drug_half_life` (185),
> `drug_enzymes` (268), `drug_metabolite_bindings` (48), `drug_metabolites` (36),
> `drug_metabolite_enzyme` (17),
> `receptor_density` (36), `target_density` (17). Each shipped quote-gated from the start,
> which is why none of them contributes to the gap.
>
> Two counts also changed shape: `projections` totals **58** rather than 103 because a
> mirrored pathway is now **one** node (emitted once with `mirror: true`), and `structures`
> is 54 rather than 52 (the tuberomammillary nucleus).

| Node kind | Missing | Total | Share of the gap | Difficulty | Best lever |
| --- | ---: | ---: | ---: | --- | --- |
| `receptor_synaptic` (pre/post site) | 48 | 56 | 28.2% | Hard | no database has the field; textbook prose |
| `drug_categories` | 36 | 235 | 21.2% | limit | 25 non-Stahl drugs + 9 recreational + 2 flagged |
| `drug_bindings` | 33 | 1688 | 19.4% | Hard | no database assays the GABA-A site; primary lit |
| `receptor_locations` | 23 | 383 | 13.5% | limit | off-atlas bases + Allen not-detected |
| `target_locations` | 14 | 96 | 8.2% | limit | SERT/NET terminals: mRNA sits at the source nucleus |
| `receptor_sign` (excit./inhib.) | 13 | 56 | 7.6% | Hard | GtoPdb's transduction is mixed/absent for these |
| `projections` | 2 | 58 | 1.2% | Hard | claustrum primary lit |
| `receptor_class` (GPCR/ionotropic) | 1 | 56 | 0.6% | limit | sigma-1 is a GtoPdb `other_protein` |
| `references` | 0 | 371 | not in headline | done | closed |
| everything else | 0 | 1341 | closed | done | see "Kinds now closed" below |

**The shape of the problem: no single lever dominates any more.** The GtoPdb classification
pass took the 121-node block that used to be half the gap and left 62 of it, of which 48 are
the one attribute no database carries. What is left is four roughly equal piles, three of them
documented limits rather than oversights: **48 `receptor_synaptic`** (pre/post site, needs
textbook prose, a fraction will honestly stay `llm`), **36 `drug_categories`** and **33
`drug_bindings`** (both mostly the non-Stahl roster meeting corpora that do not cover it),
and **37 expression-location nodes** (off-atlas bases, or transporter mRNA sitting at the
source nucleus). The residue is small and specific: 13 `receptor_sign` GtoPdb could not map,
sigma-1's `receptor_class`, and the 2 claustrum `projections`.

Twelve corpora are wired into `SOURCE_CORPORA` today: five books (`stahl`, `kandel`,
`stahl_essential`, `carlat`, `nieuwenhuys`) and seven data sources (the `pdsp_ki` CSV, the
`gtopdb` tissue API, the `allen_ahba` microarray, `wikipedia_pharm`, `wikipedia_fr`,
`gtopdb_ki`, and `gtopdb_class`). The book-prose wins they allow are essentially exhausted
(see the sourcing memory). What remains needs a **neuropharmacology textbook** read for
pre/post site, a corpus that covers **non-Stahl marketed drugs** (the class lines), or
**primary literature** (the claustrum pathways, a handful of subtype affinities).

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

### 1. `receptor_synaptic`, 48 / 56 missing (**28% of the whole gap**)

**What.** The pre- versus postsynaptic site sub-claim, one of the four a receptor's
classification is split into. Its three siblings are now essentially closed by the GtoPdb
classification pass (corpus #12): `family` 56 / 56, `receptor_class` 55 / 56,
`receptor_sign` 43 / 56. This one it could not touch at all.

**Why it is not verified.** Two independent reasons, and neither is an oversight:
- **No database carries the field.** GtoPdb states type, family, transduction, tissue
  distribution and ligand affinities, and never where on the neuron the receptor sits.
  Grepping the 47 cached raw target responses found ~10 mentions of "presynaptic" or
  "postsynaptic", mostly inside reference *titles*. Allen is mRNA. PDSP is affinity.
- **Running prose states it rarely, and a compound value needs two quotes.** A Stahl
  Essential quote grades **only** the attributes listed in
  `RECEPTOR_CLASSIFICATION_COVERAGE` for that receptor, assigned conservatively, and the
  book names a receptor's site only when the site is the point of the passage (the 5-HT1A
  somatodendritic autoreceptor, the 5-HT1B/D terminal autoreceptor). A `synaptic="both"`
  needs **two** quotes, one per site, which is why only 8 are closed.

**How to tackle.** A **neuropharmacology textbook** read is the only route: Rang and Dale,
Katzung, or the Stahl Essential autoreceptor figures the prose pass skipped. The α2 polarity
node closed exactly this way (Stahl Essential p271, "when presynaptic α2 receptors recognize
NE, they turn off further release of NE"), so the pattern works where the book makes the
site the subject. Budget for a minority of the 48, not all of them: for a receptor whose
site the literature genuinely does not commit to, `llm` is the honest grade.

### 1b. `receptor_sign`, 13 / 56 missing, and `receptor_class`, 1 / 56 missing (the classification residue)

**What is left after the GtoPdb pass.** The applier maps a receptor's **sign** from GtoPdb's
transduction table under a deliberately narrow rule (one unambiguous primary transducer
family, or several primary rows that agree). 13 counted receptors do not clear it, in three
groups:
- **7 ligand-gated ion channels** (5-HT3, AMPA, NMDA, kainate, glycine, nAChR α4β2, nAChR α7)
  have **no transduction row at all**: GtoPdb's transduction table is a GPCR-only structure,
  so an ion channel returns nothing to map. (GABA-A is already verified against Stahl
  Essential, which is the route these want.)
- **2 with an empty table** for their own reasons: GABA-B (a GPCR GtoPdb lists without a
  transduction row) and sigma-1 (`other_protein`).
- **4 reported conflicts**, below.

`receptor_class` has exactly one left: **sigma-1**, which GtoPdb types as `other_protein`.
That does not assert our "chaperone" value, so the applier writes nothing rather than
stretching the mapping.

**The 4 conflicts the pass reported and deliberately did not resolve.** a2a, cb1, mt1 and mt2
are `modulatory` in our data, while their transduction implies a direction (Gs for a2a, Gi/Go
for the other three; h4 is the same case but is an uncounted stub). A sourcing pass never
rewrites data to match a source, so these stayed `llm` and are flagged here instead. Two
readings are possible and picking one is a data decision, not a sourcing one: either
`modulatory` is the right call for a receptor whose net effect depends on where it sits (cb1
as a retrograde presynaptic brake), or these are genuinely inhibitory and the value should
change. Resolve it against a textbook, then re-run the applier and the sign closes with it.

**How to tackle the 7 ionotropic signs.** An ion channel's sign is its permeant ion (cation
influx depolarizes, chloride influx hyperpolarizes), which Stahl Essential does state in
prose for the big ones. That is a small, targeted quote hunt, not a corpus.

### 2. `drug_categories`, 36 / 235 missing (199 verified against Stahl)

**What.** One node per drug: its class classification ("this drug is an SSRI / TCA / SGA /
..."), `category_provenance`. Stahl's Prescriber's Guide prints the class verbatim under each
monograph's "## Class" heading, which is how the 199 were closed (Haiku extract, Sonnet judge,
`apply_category_sources.py` re-find + write, `check_data.py` re-verify).

**Why the 36 are not verified.** All three groups are structural, not oversights:
- **25 drugs outside Stahl's roster** (added by the roster pass below): amantadine,
  amobarbital, azacyclonol, baclofen, calcium_carbimide, cyclobarbital, doxylamine,
  glutethimide, ketanserin, melatonin, mesoridazine, naloxone, ondansetron, perampanel,
  phenazepam, phenobarbital, pramipexole, prochlorperazine, prothipendyl, ropinirole,
  rotigotine, rubidium_chloride, tizanidine, tropatepine, xanomeline. Stahl's 8th edition has
  no monograph for them, so there is no class line to quote.
- **9 recreational drugs** (LSD, MDMA, cocaine, DMT, methamphetamine, nicotine, THC, caffeine,
  methaqualone): the "Recreational / psychoactive" category is ours; the Prescriber's Guide
  covers prescription psychiatric drugs and has no class line for them by construction. Their
  *bindings* are fully PDSP-Ki-verified; only the label is unsourced, and honestly so.
- **2 long-flagged**: `naltrexonebupropion` (Stahl says "weight management medication", which
  does not back our `substance_use` category, a genuine mismatch to review rather than a quote
  to paper over) and `serdexmethylphenidate` (no standalone class bullet).

**How to tackle.** The 25 non-Stahl drugs are the only real target, and they need a corpus
covering marketed drugs Stahl omits: the **French Wikipedia articles are already stored**
author-side for these drugs (corpus #10, fetched for their brand names), and an article's
opening sentence almost always states the class ("un antipsychotique conventionnel de la
famille des phénothiazines"). That is the cheapest route: same quote gate, pages already on
disk, no new corpus. English Wikipedia (corpus #9) is stored for most of them too. Expect
roughly 20 of 25 closeable; the 9 recreational and 2 flagged stay.

### 3. `drug_bindings`, 33 / 1688 missing

**What.** 33 bindings with neither a quote source nor a Ki (`affinity_only` bindings are
excluded: they are listed but never animated).

**Why not verified.** Two clusters, both structural:
- **The GABA-A modulatory site, 7 bindings** (glutethimide, phenazepam, nimetazepam,
  butobarbital, cyclobarbital, secobarbital, brotizolam). No radioligand panel assays it the
  way PDSP assays a receptor, and GtoPdb curates no interaction row for these older agents.
  This is the same set the GtoPdb survey below predicted would stay empty.
- **Non-Stahl drugs' receptor profiles, 18 bindings** (tropatepine at M1-M5 + H1, prothipendyl
  at D2 + H1, chlorprothixene and levomepromazine and prochlorperazine at α1A/B/D,
  levomepromazine at 5-HT2A). The drug has no Stahl monograph to quote and PDSP has no assay
  under that name.
- **The long-standing 8**: carbamazepine at the glutamate modulator site, maprotiline at
  M1-M5, sulpiride at H1, trimipramine at Nav (tentative).

**How to tackle.** Opportunistic, in this order: (a) re-run `fetch_ki.py --apply` after a fresh
PDSP download, scoped with `--only` to these drugs; (b) the drug's own Wikipedia
pharmacodynamics prose (corpus #9), which is where the muscarinic profile of an older
antihistaminic antipsychotic is usually stated; (c) primary literature for the rest. Some will
honestly stay unsourced: publishing a binding we cannot cite is worse than an `NOSOURCE` pill.

### 4. `receptor_locations`, 23 / 383 missing (**limit, not a gap**)

**What.** One node per (receptor, region) pair: "receptor R is expressed in region B" (the
panel's "Found in" rows). **360 verified**: 197 against the Guide to Pharmacology tissue API
(corpus #7, species-flagged), then 163 more against the Allen microarray (corpus #8). Where
Allen confirms a region GtoPdb had only in a rat/mouse assay, both back it and the panel prefers
the Human tag (91 of 109 amber receptor tags cleared).

**Why the 23 stay `llm`.** Allen's honest limits, and they cluster exactly where you would
expect: **off-atlas bases** (olfactory bulb for 5-HT1E / D2 / D3 / H3 / M2, pituitary for MT1,
subthalamic nucleus for 5-HT1F) plus **regions sampled but not detected** (5-HT2B in
hypothalamus / frontal / amygdala, α2B in hippocampus / cerebellum, kappa in medulla, mu in
occipital). A microarray that did not sample a structure cannot confirm expression there, and
saying so is the point of the grade.

**How to tackle.** Nothing cheap. Autoradiography or a PET tracer atlas would reach some
(see the density survey below), at a licence and parcellation cost out of proportion to 23
nodes. Leave them.

### 5. `target_locations`, 14 / 96 missing (**limit, not a gap**)

**What.** The mirror of #4 for the 20 non-receptor targets. **82 verified** via Allen
(corpus #8), whose `PACall` present/absent boolean across 5 human donors is a deterministic
confirm with no judge.

**Why the 14 stay `llm`.** All of them are **SERT and NET terminal regions** (SERT at frontal,
temporal, cingulate, hippocampus, amygdala, thalamus, hypothalamus, accumbens; NET at frontal,
hippocampus, thalamus, hypothalamus, amygdala, cerebellum). Microarray measures **mRNA in cell
bodies**, so a transporter confirms at its source nucleus (SERT at raphe, NET at locus
coeruleus, both verified) and honestly cannot confirm the terminals where the protein works.
This is a property of the assay, not a hole in our sourcing.

**How to tackle.** Only a **protein-level** source (immunohistochemistry or a PET transporter
atlas) would confirm terminals. Not worth a corpus for 14 nodes; the caveat is already shipped
in the density caption.

### 6. `projections`, 2 / 58 missing

**What.** Two pathway arrows remain unsourced: claustrum to frontal, and claustrum to insula.
(The tally counts a mirrored pathway once, so these are 2 nodes, not 4.) The fornix chain,
hippocampo-septal, septo-hypothalamic, olfactory-bulb to amygdala, the temporal anterior
commissure and insula to cingulate were closed against the **Nieuwenhuys** atlas (corpus #6).

**Why not verified.** Nieuwenhuys states claustrum-to-neocortex connectivity only **in
aggregate**: the sentence naming the specific frontal areas sits on a different PDF page than
the connecting verb, so no single quotable page asserts "claustrum to frontal"; and no page
asserts a claustrum-insula **fibre projection** at all (only that the claustrum is adjacent to
and developmentally derived from insular cortex). The judge rejected the generic "many
neocortical areas" sentence for both, so they were not forced.

**How to tackle.** A claustrum-specific source: a connectivity review (Crick and Koch 2005 and
successors) or a tract-tracing paper, via NCBI. Given how thin claustrum connectivity is in the
literature, they may honestly stay `llm`.

### 7. Kinds now closed

Kept as a record of which lever worked, so a later session does not re-derive it:

- **`structures` 54/54.** Kandel for 48, then claustrum + fornix + tuberomammillary against
  **Nieuwenhuys** (corpus #6), which Kandel does not describe in prose.
- **`circuits` 6/6.** The two basal-ganglia loops from Kandel p983 (Albin scheme); the other
  four reuse quotes already verified for their member projections, so no quote is duplicated.
- **`projection_groups` 11/11.** Glutamate and GABA from Stahl Essential; the monoamine,
  cholinergic, neuroendocrine and modulatory systems from Kandel. The sign groups reuse their
  dominant transmitter's quote.
- **`drug_nbn` 116/116.** `apply_nbn_sources.py` greps Stahl's verbatim
  "Neuroscience-based Nomenclature:" line and confirms our value is a substring, which is
  stronger than a judge for a fixed field.
- **`drug_brands` 469/469.** Stahl's "Brands" list for `na` (verbatim on the drug's page
  range), French Wikipedia (corpus #10) for `eu` / `fr`. A brand not found verbatim is dropped,
  not guessed.
- **`drug_half_life` 185/185 and `drug_metabolites` 36/36.** Stahl's Pharmacokinetics block via
  the `fetch_pharmacokinetics.py` worklist, one LLM pass, then `apply_pharmacokinetics.py`
  quote-gates and merges.
- **`drug_metabolite_bindings` 48/48.** The metabolite's own Wikipedia pharmacology (corpus #9)
  for target + action, PDSP (corpus #5) for the affinity and for target discovery.
- **`drug_metabolite_enzyme` 17/17.** Which enzyme forms each active metabolite: hand-curated
  (Stahl + Wikipedia), covering 14 of the 36 metabolites, the rest left NOSOURCE. 100% of what
  exists, and the only kind here whose *coverage* is deliberately partial rather than complete.
- **`drug_enzymes` 268/268.** Two greps behind the same verbatim quote gate, **no LLM at all**:
  Stahl's Pharmacokinetics block is regular enough ("Substrate for CYP2D6", "Inhibits CYP2C19")
  for `fetch_cyp.py` (159 nodes over 86 drugs), and `fetch_cyp_wikipedia.py` adds the drugs Stahl
  has no monograph for out of the stored English articles (corpus #9; 109 further nodes over 62
  drugs). Stahl wins any pair both state. 119 drugs, 220 substrate / 37 inhibitor / 11 inducer.
- **`receptor_density` 36/36 and `target_density` 17/17.** Allen microarray intensity
  (corpus #8), one node per profile with the whole profile written into the quote, published
  only above the cross-donor reliability floor.
- **`receptors` (family) 56/56.** Stahl Essential for 54; the last two (5-HT1E and 5-HT1F,
  which the Essential corpus never names outside affinity-table cells) against GtoPdb's own
  family label (corpus #12), a direct read: "5-Hydroxytryptamine receptors" *is* serotonergic.
- **`targets` (classification) 20/20.** Stahl Essential for 16; carbonic anhydrase, PDE5, the
  T-type Ca channel and the melanocortin group against GtoPdb's `type` field (corpus #12).
  All four were confirmed absent from Stahl Essential first ("anhydrase" and "T-type" never
  appear; "melanocortin" only inside "pro-opiomelanocortin"; the only phosphodiesterase
  mention is PDE9/10, so citing it for PDE5 would misattribute the isoform).
- **`target_polarity` 2/2.** VMAT2 rode its own classification sentence (which does state
  packaging *into* vesicles). The α2 group closed against Stahl Essential p271, "when
  presynaptic α2 receptors recognize NE, they turn off further release of NE", one sentence
  carrying both halves of the flag (presynaptic site, inhibitory sign). This is the node the
  `provenance-silent-inheritance` memory is about: the flag used to ride the target's single
  classification grade, from a quote that never addressed direction.
- **`references` 371/371.** The last two were the tuberomammillary nucleus (left and right),
  which had no `wikipedia` link; one line in `presentation.py`.

---

## Recommended attack order

Ordered by **value per unit effort**, not by raw node count. Everything above step 1 is done:
`drug_categories` against Stahl, `circuits` + `projection_groups` + `structures` +
`projections` against Kandel and Nieuwenhuys, `receptors` family against Stahl Essential then
GtoPdb, `receptor_locations` against GtoPdb (Phase 1) then Allen (Phase 2b),
`target_locations` against Allen (Phase 2a), the whole drug-pharmacokinetics family (brands,
T½, metabolites, metabolite bindings, enzymes) quote-gated from the start, and the **GtoPdb
classification pass** (corpus #12: `receptor_class`, most of `receptor_sign`, the last two
families, all four `targets`, the α2 `target_polarity`, the last 2 `references`). Headline
over that run: 55% to 67% to 78% to 95% to 96%, then down to 94% as the receptor split and
the roster expansion enlarged the denominator, then back to **96%** (see the snapshot).

1. **The non-Stahl `drug_categories` (about 20 of 36 reachable).** Now the single biggest
   *closeable* pile. The French and English Wikipedia pages for these drugs are **already
   stored author-side** (corpora #10 and #9), and an article's opening sentence states the
   class. Cheap because there is no new corpus and no new gate; only an extract-and-judge
   pass over pages already on disk.
2. **`drug_bindings` (33), opportunistic.** A PDSP refresh scoped with `--only` to the
   affected drugs, then Wikipedia pharmacodynamics prose for the older antipsychotics'
   muscarinic and α1 profiles. The 7 GABA-A modulatory-site bindings will not close: no
   database assays that site.
3. **The classification residue (13 `receptor_sign` + 1 `receptor_class`), small and
   targeted.** 7 of the signs are ligand-gated ion channels whose sign is their permeant ion,
   which Stahl Essential states in prose; 4 are the reported conflicts, which need a *data*
   decision before any source can back them (see #1b). Not a corpus, a quote hunt.
4. **`receptor_synaptic` (48): the largest remaining pile, and the least tractable.** No
   database carries the field, so it needs a neuropharmacology textbook read, and a fraction
   will honestly stay `llm` (#1). Worth attempting only after steps 1 to 3.
5. **The last 2 `projections`**, claustrum-specific primary literature; may honestly stay
   `llm`.
6. **The 37 expression-location nodes: do not chase.** Off-atlas bases and transporter mRNA
   sitting at the source nucleus are properties of the assay. Only a protein-level atlas
   would move them, at a licence and parcellation cost out of proportion to the count.

**Sources we still need (beyond the twelve wired):**
- **A neuropharmacology textbook** (Rang and Dale, Katzung) for the 48 `receptor_synaptic`
  nodes in step 4. This is the only gap left that a whole new corpus would address, and even
  it will not close completely.
- **NCBI/PubMed primary literature** as the genuine last resort for the handful of claims no
  reference book states: claustrum-to-frontal and claustrum-to-insula connectivity, a few
  subtype affinities.
- Nothing else. Every other gap in this document is a documented limit of a source we already
  hold, and adding a corpus to chase it would cost more than the honesty of the `llm` pill.

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

**Verdict: adopted; all three steps shipped.** Step 1, the drug to enzyme roles out of
Stahl's pharmacokinetics block, landed in v3.30.0 to v3.31.1 exactly as scoped: regular enough
to grep, so `fetch_cyp.py` uses **no LLM judge at all** (the same argument that makes
`apply_nbn_sources.py` stronger than a judge for the NbN line). It emits **159 `drug_enzymes`
nodes over 86 drugs** (121 substrate, 29 inhibitor, 9 inducer; 3A4 58, 2D6 44, 1A2 22, 2C19 16,
2C9 9, then a tail), **all verified**, plus the derived drug-to-drug PK interaction edges
(`pkInteractionsOf`), a **Metabolism** and **Interactions** list in `showDrug`, and an
**Enzymes** browse section.

**Step 2, the Wikipedia sweep, also landed, and also with no LLM.** The survey expected an
extract-then-judge pass; the article's drugbox `Metabolism |` row turned out to be as regular as a
Stahl bullet, so `fetch_cyp_wikipedia.py` imports `fetch_cyp.py`'s role/strength/victim rules and
adds only what a long prose paragraph needs: a sentence split, a negation veto, a rule that the
drug's own name must appear before the verb with no `which` / `that` / paren / comma between, and a
two-roles-in-one-sentence veto. Those three rules are what stops the wrong claims a paragraph
offers: "Smoking induces CYP1A2" read as clozapine inducing it, a co-prescribed victim drug's
profile read as the subject's ("... mirtazapine, which is mainly metabolized by ..."), and a
reference-list title read as prose. Yield: **190 nodes over 101 drugs**, of which **109 over 62
drugs** survive the Stahl-first merge (Stahl already stated the rest), taking `drug_enzymes` from
159/86 to **268 nodes over 119 drugs**, all verified.

**Metabolite `formed_by` landed too, and the estimate held.** 14 of the 36 metabolites are covered
by **17 nodes** (kind `drug_metabolite_enzyme`, all verified), hand-curated in
`tools/data_generators/quotes/metabolism.py` exactly as the plan below said to do it. Sourcing it
by pattern was never on: the near misses a grep produces are all wrong in the same direction, and
all three appeared while reading the 36 rows. An enzyme that **clears** the metabolite instead of
making it (clobazam's own article states both in adjacent sentences). An enzyme named on the
metabolite's article with **no parent in the sentence** ("It is formed by dealkylation via CYP3A4"
on the mCPP page means from trazodone, not from nefazodone). An enzyme handling a **different**
metabolite of the same drug (valbenazine's CYP3A4/5 oxidation makes monooxidized valbenazine, not
the dihydrotetrabenazine we list). The other 22 stay NOSOURCE; primidone is the one worth quoting,
since its article says outright that the responsible P450s are still unknown, which is an answer
rather than a gap.

**What the survey below got wrong:** it expected the yield to come from Stahl. It came mostly from
Wikipedia (10 of the 17 rows), because Stahl states the forming enzyme only in the TCA monographs'
one stock sentence ("Metabolized to an active metabolite, X, ... by demethylation via CYP1A2").

**Still open:** nothing in this section. Kept for the record:
- **Metabolite `formed_by`.** All 36 metabolite rows still have none. Expect roughly 10 to 15
  sourceable from Stahl, hand-curated rather than piped, and the rest honestly `NOSOURCE`. It
  is the prodrug story (why a CYP2D6 poor metabolizer gets nothing from codeine or tramadol).

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

### GtoPdb target records as a **classification** source

> **Status: adopted, shipped as corpus #12 `gtopdb_class`** (2026-07-27). Same database, third
> slice, so the fetch/gate/merge plumbing was reuse rather than new build:
> `tools/fetch/fetch_gtopdb_class.py` -> `data_sources/gtopdb/pages_class/` ->
> `tools/sourcing/apply_classification_sources.py`.

The survey question was whether a structured database could source the receptor classification
attributes running prose keeps missing. Answer, measured rather than assumed: **partly**, and
knowing which part is the useful result.

- **`type` is a direct read.** `gpcr` *is* metabotropic, `lgic` *is* ionotropic. Same for a
  non-receptor target's `type` and, from the family label, a receptor's transmitter `family`.
- **`sign` has to be mapped from the transduction table** (Gi/Go, Gs, Gq/G11), which GtoPdb
  offers for GPCRs only. Under a narrow rule (one unambiguous primary transducer family, or
  primary rows that agree) it reaches 43 of 56; ion channels return no table at all.
- **Pre/post-synaptic site is simply not in the database.** No field, and the free-text
  comments mention it about ten times across 47 cached target records, mostly inside reference
  titles. Do not re-survey this hoping for a hidden endpoint: there is not one.

The three things worth knowing before touching it again: `/services/families/{id}` 404s (the
family name arrives on the target record instead); a transducer cell can list several
mechanisms, so it needs splitting on commas with "G protein independent mechanism" ignored (D2
reads "Gi/Go family, G protein independent mechanism"); and the pass reports 4 conflicts it
must not resolve (#1b).

## Drug-roster coverage: what the Wikipedia lists have that we do not (surveyed 2026-07-26)

Not a sourcing gap but a **coverage** gap, kept here because it is the same kind of survey
(measure once, write it down, do not re-survey). Prompted by noticing bromazepam and
clotiazepam were absent.

> **Status: acted on.** All 35 Tier-1 and all 21 Tier-2 names below are in the dataset
> (v3.28.0 added bromazepam + clotiazepam, v3.29.0 the other 54), taking the roster from 179
> to 235 drugs. Tier 3 stays skipped by design. The cost lands in this document's gap table:
> a non-Stahl drug has no class line to quote (`drug_categories` #2) and, for the
> barbiturates and benzodiazepines, a GABA-A binding no affinity database assays
> (`drug_bindings` #3). The survey below is kept as the record of what was chosen and why.

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
