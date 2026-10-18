# Sourcing gaps: what is not yet `verified`, why, and how to tackle it

The dataset grades every **node** (any sourceable datum, see `CLAUDE.md` "Nodes")
`llm` < `sourced` < `verified`. `verified` is the top grade: a quote was
programmatically confirmed present in a cited source page (or a Ki row in the PDSP
CSV). This document lists everything **not** at `verified`, says **why**, and gives an
**idea to tackle it**. Numbers come straight from `meta.provenance_stats` (regenerate
with `python tools/generate_data.py`, print the table with `python tools/check_data.py`),
so re-derive them after any data change rather than trusting the counts below forever.

Made with the help of Claude Code.

## Quote-quality audit (2026-07-28, the sulpiride follow-up)

A `verified` grade only ever meant "this sentence is really on that page". It never
meant "this sentence is about this drug", which is exactly how the sulpiride mistake
got in. Three questions were asked of all 3233 stored quotes; what each turned up:

**1. Is the quote on the right drug's pages?** Yes, everywhere: all Stahl quotes on
all 158 monographed drugs fall inside that drug's own page span. This is now a gate
rather than a finding, `check_data.py` family 5 reads Stahl's generated `INDEX.md` and
errors on a quote cited outside its drug's monograph, so the answer stays yes.

**2. Is the quote a whole sentence?** 29 were stored mid-sentence, with the subject
left behind on the other side of the cut. 20 were widened back to the full sentence.
The remaining 9 stay clipped on purpose: their preceding words are a PDF artifact (a
figure label `(B)`, a running head `Pharmacokinetics**`, a hyphen-broken word), which
reads worse than the fragment. 14 book quotes still open on a lowercase letter, but
almost all of those open on the drug's own lowercase name ("daridorexant binds to
orexin 1 and orexin 2 receptors ..."), which is the subject the audit was looking for.

**3. Does the quote actually assert the claim?** This is the sulpiride shape. 46 (drug,
quote) claims are sentences Stahl prints in its **How Drug Causes Side Effects** block,
which states rules without a subject ("Blockade of alpha adrenergic 1 receptors may
explain dizziness, sedation, and hypotension"). Of those, 6 name the drug and 5
attribute the action with a pronoun ("By blocking X, **it** can cause Y"); both are
fine. **33 have no subject at all**, and because one such sentence sources every subtype
it mentions (m1-m5, alpha1a/b/d), they carry **89 individual bindings** across 17 drugs.
Count them at the claim level, not the binding level: 33 editorial decisions, not 89.
(An earlier pass over the same material counted 35 claims / 99 bindings; that detector
also caught sentences outside the side-effect block and verb-first ones like "Blocks
histamine 1 receptors", which do read as statements about the drug. 33 / 89 is the
number actually shipped, in `UNCERTAIN_BINDING_CLAIMS`.) They were kept, on evidence
rather than convenience:

- Unlike the three class-wide antipsychotic lines already stripped (printed on 17 to 28
  monographs including benzamides that lack the property), these lines are printed
  selectively: the alpha-1 one on 13 monographs, the anticholinergic one on 10, the
  antihistamine one on 12, all tricyclics and all genuinely carrying the property.
- Half are independently backed by a measured PDSP Ki on the same binding (44 of the 89
  bindings carry one; a whole claim without any is the exception, e.g. clomipramine's
  m1-m5 on p.180).
- Stripping them would not improve the data anyway: PDSP only holds a generic
  "Muscarinic Acetylcholine Receptor" / "adrenergic Alpha1" assay for these compounds,
  which the m1-m5 / alpha1a-b-d granularity we model cannot consume. This is the same
  granularity gap `tools/sourcing/apply_binding_sources.py` documents.

**Repetition across monographs is not itself a red flag**, and a check keyed on it
would be wrong: "Blocks dopamine 2 receptors, reducing positive symptoms of psychosis"
appears on 29 pages because Stahl writes it on every antipsychotic, and every one of
them does block D2. What distinguished the sulpiride case was the section it sat in
plus a drug that lacked the property, not the repetition.

**Resolved (2026-07-28) by making the doubt legible rather than by deleting or blessing
the claims:** all 33 now carry an **uncertain** badge (orange `⚠`) in place of the green
check, and its tooltip gives the reasons to doubt them, each reason itself a badged,
quote-gated node (the sentence explains a side effect; it is printed on N other
monographs; a measured Ki backs it, or there is none; Stahl never lists the action among
the drug's mechanisms). See `docs/PROVENANCE.md` for the badge, the tally
bucket and the bullet contract, and `tools/data_generators/quotes/uncertainty.py` for the
vocabulary. The nodes stay *backed* (a real document does exist, so the headline is
unchanged) but leave the green `verified` count.

**Made automatic (2026-07-28), which closes the "curated stand-in" caveat this section
used to end on.** The badge started as a hand-written list of the 33 claims. It is now
**derived** from the emitted data: the quote's heading trail (see `CLAUDE.md` "Where a
quote sits") says the sentence is in the *How Drug Causes Side Effects* block, and
`_attributes_to_drug` says it has no subject. The derivation reproduces the audit's 33
claims / 89 bindings exactly, binding for binding, which is the strongest evidence either
of them is right. New drugs are now covered the day they land, and the list cannot go
stale against a data edit.

A second derived flag was added at the same time, from the same insight, for a different
way a quote can fail to be about the node: the **family-level claim**. One sentence covers
several of the drug's bindings on subtypes of one family and names none of them
individually ("Blockade of alpha adrenergic 1 receptors" -> alpha1A/B/D, "Anticholinergic
activity" -> M1-M5), so the split into subtypes is our reading, not the book's. That is
bearable when a measured Ki reaches the subtype (prazosin's alpha1A/B/D are each assayed),
so it only flags a subtype **with no Ki of its own**: nortriptyline has an alpha1A assay
and nothing for alpha1B or alpha1D, which are left resting on a sentence that says
"alpha 1". +22 bindings, taking the badge to 111.

**Still open here:**

- The **11 attributed claims** (6 naming the drug, 5 using a pronoun) are fine as they
  stand and are deliberately **not** flagged. Re-read them if the badge's vocabulary
  grows a kind that fits them better.
- Detecting a claim that is genuinely *wrong* (rather than weakly stated) still needs
  independent evidence the drug lacks the property, which today only exists as a Ki for
  the coarse target we do not model. The badge makes weak claims visible; it does not
  adjudicate them.

## Snapshot (2026-07-27, after the GtoPdb classification, metabolism and drug-binding passes)

Headline: **3820 / 3969 knowledge nodes backed (96%)**. In the tally a bare `llm`
grade counts as **missing** ("an LLM asserted it from memory" = no document), so
"missing" below means `llm` or no source at all. 149 knowledge nodes are missing.

> **The uncertain badge (2026-07-28) does not move any figure in this section.** It moved
> 89 `drug_bindings` out of `verified` into their own `uncertain` bucket; both are backed,
> so the headline, the per-kind coverage and the gap are unchanged. The live numbers are in
> the README `SOURCING_STATS` block and the in-app Sources popup, never re-typed here.

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
> **The drug-binding pass, same day**, closed 21 of the 33 unsourced bindings by hand
> (`tools/sourcing/apply_binding_sources.py`) after confirming PDSP and GtoPdb are exhausted for
> all 33: 170 missing to **149**, `drug_bindings` 33 to **12 / 1688**. The 12 left are the 7
> GABA-A modulatory-site PAMs, prochlorperazine's 3 α1 subtypes, tropatepine at H1, and
> trimipramine at Nav (see section 3).
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
| `receptor_synaptic` (pre/post site) | 48 | 56 | 32.2% | Hard | no database has the field; textbook prose |
| `drug_categories` | 13 | 301 | (2026-10-10, after the snapshot) | limit | 6 unfetched articles + 6 silent leads + 1 label mismatch (section 2) |
| `receptor_locations` | 23 | 383 | 15.4% | limit | off-atlas bases + Allen not-detected |
| `target_locations` | 14 | 96 | 9.4% | limit | SERT/NET terminals: mRNA sits at the source nucleus |
| `receptor_sign` (excit./inhib.) | 13 | 56 | 8.7% | Hard | GtoPdb's transduction is mixed/absent for these |
| `drug_bindings` | 12 | 1688 | 8.1% | Hard | no database assays the GABA-A site; primary lit |
| `projections` | 2 | 110 | (2026-10-10, after the snapshot) | Hard | claustrum primary lit |
| `projection_transmitter` | 18 | 116 | (2026-10-13, after the snapshot) | Hard | Europe PMC abstracts, mostly rodent; locus coeruleus/raphe still unnamed (section 6) |
| `projection_sign` | 8 | 38 | (2026-10-13, after the snapshot) | Hard | same (section 6) |
| `drug_enzyme_strength` (major/minor, strong/moderate/weak) | 13 | 147 | (2026-10-10, after the snapshot) | limit | tier only implied by a percentage or by contrast (section 6b) |
| `receptor_class` (GPCR/ionotropic) | 1 | 56 | 0.7% | limit | sigma-1 is a GtoPdb `other_protein` |
| `references` | 0 | 371 | not in headline | done | closed |
| everything else | 0 | 1341 | closed | done | see "Kinds now closed" below |

**The shape of the problem: no single lever dominates any more.** The GtoPdb classification
pass took the 121-node block that used to be half the gap and left 62 of it, of which 48 are
the one attribute no database carries. What is left is four roughly equal piles, three of them
documented limits rather than oversights: **48 `receptor_synaptic`** (pre/post site, needs
textbook prose, a fraction will honestly stay `llm`) and `drug_categories` (36 at the snapshot, 13 since the
Wikipedia-lead pass and the 2026-10-10 relabels, see section 2),
and **37 expression-location nodes** (off-atlas bases, or transporter mRNA sitting at the
source nucleus). The residue is small and specific: 13 `receptor_sign` GtoPdb could not map,
sigma-1's `receptor_class`, and the 2 claustrum `projections`.

Thirteen corpora are wired into `SOURCE_CORPORA` today: five books (`stahl`, `kandel`,
`stahl_essential`, `carlat`, `nieuwenhuys`) and eight data sources (the `pdsp_ki` CSV, the
`gtopdb` tissue API, the `allen_ahba` microarray, `wikipedia_pharm`, `wikipedia_fr`,
`gtopdb_ki`, `gtopdb_class`, and the committed `pharmfreq` metabolizer export). The book-prose wins they allow are essentially exhausted
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
2. **Gene maps.** Receptors already have `RECEPTOR_GENES` (in `tools/lib/gene_maps.py`, reuse it).
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
- The Allen->base **crosswalk** + **`TARGET_GENES`** map (crosswalk in `fetch_allen.py`, `TARGET_GENES` in `tools/lib/gene_maps.py`).
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
- **Docs**: `docs/PROVENANCE.md` (corpus #8) + `tools/README.md` (Tool reference), this file, the
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

### 1. `receptor_synaptic`, 14 / 56 missing

**What.** The pre- versus postsynaptic site sub-claim, one of the four a receptor's classification is split into. GtoPdb (corpus #12) has no field for it, so it is closed from prose only: the receptor's own English Wikipedia article (corpus #9) and Stahl Essential (corpus #3), via `fetch_classification_worklist.py` -> by-index picks in `classification_judged.json` -> `apply_classification_sources.py --prose` -> an Opus `recheck_quotes.py` judge. That pass (2026-10-10) took it from 8 to **42 / 56** verified. A `synaptic="both"` needs **two** quotes, one per site, and the applier refuses a pick that covers only one.

**Why the rest stays `llm`.** Each was read and left null, not missed:
- **One site found, value says both:** nAChR α4β2 (Stahl p523/524 says "The α4β2 subtype is postsynaptic"), GABA-B (presynaptic only, Stahl p570), δ-opioid (postsynaptic only, Stahl p575), α2C (only the generic α2 autoreceptor sentence).
- **Source contradicts the value (kept, flagged `contradicted`, 2026-10-10):** 5-HT5A (we say postsynaptic, its Wikipedia article says it "appears to serve as a presynaptic serotonin autoreceptor"); the site stays `llm` (a denial is not a backing) but its pill tooltip leads with the denial (`RECEPTOR_CONTRADICTIONS` in `quotes/contradictions.py`). mGluR6 (we say postsynaptic) was NOT flagged: the Opus judge rejected the group-level sentence ("groups II and III are mostly located on presynaptic elements"), which never names mGluR6, ends "found on both pre- and postsynaptic membranes", and is followed by a line singling mGluR6 out as distributed differently.
- **No sentence names a site:** β2, β3, GABA-A-rho, α2D, 5-HT1E, 5-HT1F, 5-HT4, and the modulatory stubs (a2a, sigma-1, mt1/mt2, h4).

**How to tackle.** A neuropharmacology textbook read (Rang and Dale, Katzung) for the "no sentence" group; the 5-HT5A contradiction is a data decision.

### 1b. `receptor_sign`, 5 / 56 missing, `receptor_class` closed (the classification residue)

**What the prose pass closed (2026-10-10).** The 7 ligand-gated ion channels (5-HT3, AMPA, NMDA, kainate, glycine, nAChR α4β2, nAChR α7) that have no GtoPdb transduction row now carry their sign from the permeant ion, quoted from their Wikipedia articles (e.g. NMDA "a non-specific cation channel", GlyR "produces its effects through chloride currents") or Stahl Essential (p117 AMPA/kainate "allowing sodium to enter the neuron to depolarize it", p327 5-HT3 "always excitatory"). GABA-B closed on its article's "usually considered as inhibitory receptors" (the next sentence notes it can also be excitatory). `receptor_class` is **56 / 56**: sigma-1's "chaperone" from its article ("The receptor's architecture supports its function as a chaperone").

**What is left: sigma-1 plus the 5 reported conflicts, deliberately not resolved.** a2a, cb1, h4, mt1 and mt2 are `modulatory` in our data while the sources state a direction; a sourcing pass never rewrites data to match a source. What the sources say:
- **cb1** (Wikipedia `cannabinoid_receptor_1`): "Upon activation, CB 1 receptor exhibits its effects mainly through activation of G i , which decreases intracellular cAMP concentration", "The activation of CB 1 in the human body generally inhibits neurotransmitter release", "Acting as a neuromodulator, the CB 1 receptor inhibits the release of both excitatory and inhibitory neurotransmitters". Stahl Essential p579: endocannabinoids "travel retrograde to presynaptic CB1 receptors" and inhibit the release of the classic neurotransmitter. Reading: inhibitory at the terminal, net effect on the circuit depends on which transmitter it brakes, which is the case for `modulatory`.
- **a2a** (Wikipedia `adenosine_a2a_receptor`): "The A 2A receptor binds with the G s protein at the intracellular site of the receptor", adenylyl cyclase activation and cAMP synthesis. Points to excitatory (Gs).
- **mt1 / mt2**: their Wikipedia articles state no transduction at all (infobox and navbox only). Stahl Essential p455 speaks of "MT1-mediated inhibition of neurons in the suprachiasmatic nucleus (SCN)", which points to inhibitory for MT1 only.

a2a and mt1 now carry the `contradicted` badge on their sign (2026-10-10, Opus-judged denials: the a2a Gs sentence above, Stahl Essential p455 for mt1); the value stays ours and the sign stays `llm`. h4 and mt2 carry it too (2026-10-12), each on its GtoPdb corpus #12 transduction row ("transduction: Gi/Go family", the only primary transducer, code-copied, so no judge). cb1 stays unflagged: its GtoPdb row also lists Gs as a secondary mechanism, and its sources describe an inhibitory brake on excitatory and inhibitory release alike, whose circuit effect is genuinely modulatory. Resolve against a textbook as a data decision, then re-run the worklist + applier and the sign closes with it. sigma-1's sign stays `llm`: nothing states one (it is a chaperone, not a channel or GPCR).

**Targets (`targets`, 25 / 25, closed 2026-10-13).** The same pass closed COMT (Stahl Essential p96), GABA-T (p274) and AADC (its Wikipedia article: "AADC catalyzes ... L-DOPA to dopamine"). The last two closed on 2026-10-13. NKCC1 closed on its own article's "The carboxy-terminal of the NKCC1 cotransporter contains ...": the type is named only in passing, which the Opus judge accepted as weak. The earlier "transporter" sentence stays rejected. The CGRP receptor closed on the CALCRL article (the receptor title redirects to the gene, `PAGE_ALIASES` in `fetch_classification_worklist.py`): "with RAMP1 : produces a CGRP receptor ... linked to the G protein G s". Stahl Essential p399 ("calcitonin G-related peptide (CGRP) and its receptors CGRP-R") was kept as a second, weak quote.

### 2. `drug_categories`, 13 / 301 missing (288 verified: Stahl, then Wikipedia leads)

**What.** One node per drug: its class classification ("this drug is an SSRI / TCA / SGA /
..."), `category_provenance`. Stahl's Prescriber's Guide prints the class verbatim under each
monograph's "## Class" heading, which closed most of the roster (Haiku extract, Sonnet judge,
`apply_category_sources.py` re-find + write, `check_data.py` re-verify). The drugs Stahl has
no monograph for were then closed from the lead of their stored Wikipedia article (EN corpus
#9, FR corpus #10 as fallback): `tools/fetch/fetch_category_worklist.py` offers the infobox
"Drug class" row and lead sentences by index, an LLM picks confirm-only into
`tools/generated_cache/category_judged.json`, `apply_category_sources.py --wikipedia` gates
and writes, and `recheck_quotes.py` stamps the judge (Opus: 51 of 54 quotes supported, 46
drugs closed).

**Why the 13 are not verified.**
- **No stored article** (6): furosemide, bumetanide, cannabidiol, cannabinol, nabilone,
  rimonabant. Their EN and FR pages were never fetched; one
  `fetch_wikipedia_pharmacology.py --drug <id>` each, then rerun the pass.
- **The lead does not state our class** (6): cyclobarbital (only the Reladorm combination is
  indicated for insomnia), serdexmethylphenidate (a prodrug, "stimulant" never said),
  tasimelteon (non-24 indication, not a hypnotic class), rubidium_chloride (chemistry only),
  tiapride and xanomeline (the lead says "benzamide antipsychotics" / the Cobenfy combination
  treats schizophrenia, neither our conventional / atypical label).
- **Label mismatch left honest** (1): `naltrexonebupropion` carries `substance_use` +
  `appetite_suppressant`, but its article only ever calls it an obesity drug, so the Opus judge
  rejected the lead sentence for the `substance_use` half (a category node is graded as one set)
  and the pick was dropped. Closing it means either a weight-management category or dropping
  `substance_use`; neither is done silently.
- **Relabelled and re-sourced (2026-10-10)**: `ondansetron` `other` -> `antiemetic` (infobox
  "Drug class | Antiemetic" row), `prothipendyl` `antipsychotic_conventional` -> `anxiolytic` +
  `antiemetic` (the lead: "an anxiolytic, antiemetic, and antihistamine"), `calcium_carbimide`
  re-picked on the abstinence-rate sentence. All three Opus-judged supported; none had a Stahl
  source asserting a removed label.

### 3. `drug_bindings`, 12 / 1688 missing (**mostly closed**)

**What.** 12 bindings with neither a quote source nor a Ki (`affinity_only` bindings are
excluded: they are listed but never animated). Was 33; a hand-curated pass
(`tools/sourcing/apply_binding_sources.py`) closed 21 of them, after confirming PDSP and
GtoPdb are genuinely exhausted for all 33 (PDSP has several of these compounds but only at
coarse target names, "alpha1" and "Muscarinic Acetylcholine Receptor", where the dataset models
subtypes; GtoPdb's bulk CSV has no matching interaction row at all).

**What closed.** Carbamazepine at glutamate and maprotiline at M1-M5 and sulpiride at H1 from
Stahl prose; tropatepine at M1-M5, prothipendyl at D2 + H1, chlorprothixene at α1A/B/D, and
levomepromazine at 5-HT2A + α1A/B/D from each drug's own English Wikipedia pharmacodynamics
(corpus #9). Two of those apply the pre-existing house convention that one coarse sentence
backs every modeled subtype of the family it names ("anticholinergic activity" -> M1-M5,
"blocking ... adrenergic receptors" -> α1A/B/D), as Stahl's lines already do on imipramine and
chlorpromazine.

**Why the 12 stay `llm`.** Structural, exactly as predicted:
- **The GABA-A modulatory site, 7 bindings** (glutethimide, phenazepam, nimetazepam,
  butobarbital, cyclobarbital, secobarbital, brotizolam). No radioligand panel assays it the
  way PDSP assays a receptor, and GtoPdb curates no interaction row for these older agents.
  This is the same set the GtoPdb survey below predicted would stay empty.
- **Prochlorperazine at α1A/B/D** (3): its article's pharmacodynamics prose names only the
  dopamine blockade, and its Ki table's α1 row is a coarse family value, not a subtype assay.
- **Tropatepine at H1**: the one sentence its article carries is anticholinergic-only.
- **Trimipramine at Nav** (tentative): Stahl says only "blockade of ion channels", and the
  existing Nav precedent requires an explicit sodium-channel statement.

**Europe PMC follow-up (2026-10-12, Claude Code + Opus).** Abstract searches (ligand AND GABA-A AND a modulation word) closed brotizolam (PMID 2569655, enhances GABA-stimulated chloride influx through the benzodiazepine receptor), plus meprobamate (PMID 9067327), chloral hydrate (PMID 18383504), etomidate and brivaracetam (their own article prose). The independent judge refused glutethimide (an abstract that only shows it weakly enhances GABA *binding* while inhibiting diazepam binding) and phenazepam (listed among "agonists" in a fish-brain ATPase assay); butobarbital, cyclobarbital, nimetazepam and secobarbital returned no abstract stating it at all. These are directed bindings, so they stay red ✕ rather than UNKNOWN (only a missing *direction* can be UNKNOWN today).

**Known conflict, deliberately not resolved.** Stahl p788 explains sulpiride's sedation and dry
mouth by antihistaminic and muscarinic blockade (the source now on H1, matching its already
sourced M1-M5 and α1 siblings), while the English Wikipedia article states a "lack of α1
adrenergic, histamine and muscarinic acetylcholine receptor affinity". The applier prints this
on every run rather than arbitrating it.

**How to tackle the rest.** Primary literature only. Some will honestly stay unsourced:
publishing a binding we cannot cite is worse than an `NOSOURCE` pill.

### 3b. `drug_binding_action` on affinity-only bindings: the UNKNOWN search (2026-10-12)

Every binding with a measured Ki but no direction (709: 666 drug + 43 metabolite) was searched for its direction across the five corpora `unknown.UNKNOWN_REQUIRED_SOURCES` requires: PDSP (#5, Ki rows only, never a direction), GtoPdb's action column (#11), the EN Wikipedia article's Ki-table Action column and prose (#9), the FR article (#10), and Europe PMC (#17, `ligand AND target AND direction word`, top 5 abstracts stored). An Opus picker answered by index, an independent Opus judge rechecked; recipe in `tools/README.md`.

- **52 directions landed** (40 antagonist, 9 agonist, 2 reuptake inhibitor, 1 each inverse agonist / partial agonist / releaser, minus the 2 the judge refused: (-)-propranolol is one enantiomer, and thiothixene's H2 sentence only says the antagonism was *studied*).
- **1 direction found later by the GtoPdb ligand pass:** GtoPdb records norfluoxetine at 5-HT2B as an antagonist (pKi 5.3, PMID 11104741); once `apply_gtopdb_ki.py` covered active metabolites (3.104.0) it landed with that page as its source.
- **656 are UNKNOWN** (∅ pill, logged in `tools/generated_cache/unknown_searches.json`, out of the headline denominator). 306 of them returned not a single Europe PMC abstract; the other 350 were offered sentences (198 bindings) none of which states the direction for that exact ligand and target. The typical miss: an abstract uses the drug as a tool compound, a sentence names the receptor family not the subtype, or "DMT" means dexmedetomidine.
- The searches expire after 12 months (`check_data.py` family 13), so the log has to be re-run by 2027-10-12.

### 3c. Binding Ki from the papers Wikipedia cites (surveyed 2026-10-12)

**What.** 253 directional bindings carried no Ki (PDSP, GtoPdb and the Wikipedia Ki tables all empty for the pair). Some drug articles state a Ki in prose and cite the paper it comes from (viloxazine: "K i = 3,900 nM and 6,400 nM" at 5-HT2B / 5-HT2C, citing Yu et al. 2020). `python tools/fetch/fetch_europepmc.py --ki-prose` follows those citations: it keeps each article paragraph that states an affinity (a Ki / Kd next to a concentration or pK value; an IC50 alone does not count, as in the GtoPdb pass), stores each cited paper (abstract, plus the open-access full text when Europe PMC has one), and offers every line that may state an affinity (a sentence, a table caption, or every numeric row of a table whose caption or header names a Ki / Kd) in `tools/generated_cache/ki_prose_worklist.json`. One pick by index (`ki_prose_judged.json`), then `tools/sourcing/apply_ki_prose.py` gates and writes, then an independent judge (`recheck_quotes.py`).

**Yield: 2** (viloxazine 5-HT2B 3900 nM, 5-HT2C 6400 nM, from Table 3's title in the OA full text of PMID 32943948 = PMC7473988, CC BY-NC; Opus judged). The paper's own Results prose swaps the two values; the table's occupancies settle it for the title, and the source `note` says so. The paper never states how or in which species those Ki were obtained. Of the 18 cited papers only 5 are open access (licences: CC BY-NC for the viloxazine paper; the other four, reviews, bring no Ki for a missing pair). The other 8 drugs stay Ki-less:
- most candidates measure other drugs (the abstract compares a panel of antidepressants);
- amantadine's Ki (20 µM, Kornhuber 1993) is at the sigma site, not NMDA; the OA review (PMID 33624170) compiles its in vitro potencies in a Table 4 that the XML ships only as an image (nothing to quote), and its prose gives NMDA effects as IC50s, not a Ki;
- niaprazine's "alpha 1 (Ki = 77 nM)" and "5-HT2 (Ki = 25 nM)" name a subtype-less α1 and 5-HT2 site (the PDSP pass drops exactly these rows) and leave open whether the value is the racemate's or the (+) isomer's;
- trimipramine's "KI 10-60 nM" is one range across 5-HT2, α1A/B and D2 together, not a value for α1B.

**Why so little.** The values live in the papers' tables, and most cited papers are 1980s-1990s pharmacology with no open-access copy: their full text cannot be read under the "OA only, never a publisher site" rule.

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

### 6. `projections`: `projection_transmitter` 18 / 116, `projection_sign` 8 / 38 missing

**What.** A pathway is three graded claims: the route, its transmitter, and (glutamate/GABA only) its sign. A transmitter or sign claim is graded off any of the pathway's sources whose quote carries the stored value's word (`attestation.pattern_for`). The by-index pass (2026-10-10) works like the classification one. `tools/fetch/fetch_projection_worklist.py` offers sentences from Kandel, Nieuwenhuys and Stahl Essential that name both endpoints, and an LLM answers by index in `projection_judged.json`. `tools/sourcing/apply_projection_sources.py` then gates the picks, confirm-only, and writes `projection_sources.json`, which the generator appends to each pathway. An Opus `recheck_quotes.py` judge runs last. The pass moved transmitter from 56 to **71**, sign from 9 to **19**, and route from 56 to **60** verified. Two of those four route nodes were NOSOURCE: septum to hippocampus (Nieuwenhuys p469, "a substantial cholinergic projection to the hippocampus") and amygdala to hypothalamus (Kandel p1100, Stahl Essential p286). `blanket_claim` fell from 35 to **33**, because the nigrostriatal pair gained a sentence naming the caudate and the putamen (Nieuwenhuys p218). The judge rejected one pick: the "thalamocortical projections ... are glutamatergic" sentence (Nieuwenhuys p446) for thalamus to cingulate, because it describes VA/VL and MD only. Its thalamus to frontal use was then re-judged on its own by an independent Opus judge (its first verdict had been copied from the cingulate note): supported, the antecedent being VA/VL to motor/premotor/supplementary motor areas and MD to prefrontal cortex, all frontal.

**Innervation pass (2026-10-10).** `check_data.py` family 10 flags a region that expresses a transmitter's receptors when no pathway of that transmitter reaches it. Fifteen new pathways close some of those gaps, all through the same worklist, applier and Opus judge, with no rejections. Each one is route-verified on a sentence that names both endpoints:

- raphe to cerebellum (Nieuwenhuys p892), medulla (Kandel p1046), septum and olfactory bulb (Nieuwenhuys p896);
- locus coeruleus to pons and midbrain (Nieuwenhuys p898), and to medulla (p900);
- VTA to temporal (Kandel p1047), cingulate (Nieuwenhuys p218), thalamus and hypothalamus (Kandel p1052), raphe and locus coeruleus (Nieuwenhuys p900);
- pons (pedunculopontine/laterodorsal tegmental) to VTA (Kandel p1115) and substantia nigra (Nieuwenhuys p443).

Five of the fifteen keep an `llm` transmitter, because their sentence names no transmitter: raphe to septum and olfactory bulb, VTA to temporal, locus coeruleus to pons and midbrain. Pages 898 and 900 describe rat data.

Family 10 went from cholinergic 10 / dopaminergic 15 / serotonergic 11 / noradrenergic 9 to **8 / 9 / 7 / 6**. Melatonergic 1 (the pituitary) is deliberate. What stays, and why:

- **Pituitary dopamine:** the tuberoinfundibular pathway (Stahl Essential p101, Kandel p410) runs hypothalamus to pituitary, and that from/to pair is already the neuroendocrine arrow. A second arrow on the same pair is a duplicate.
- **Intrinsic sources the model does not draw as arrows:** striatal acetylcholine (interneurons), olfactory-bulb dopamine (A16 periglomerular cells), olfactory-bulb acetylcholine (horizontal limb of the diagonal band, not the nucleus basalis).
- **Contested:** dopamine to the cerebellum, which Nieuwenhuys p901 calls controversial.
- **No naming sentence found in the books:** dopamine to the occipital lobe, septum (Kandel p982 omits the VTA), pons, midbrain and medulla; serotonin to the subthalamic nucleus, claustrum and VTA; noradrenaline to the accumbens and VTA; acetylcholine to the hypothalamus, mammillary bodies, midbrain and medulla. The Nieuwenhuys sentences that do name some of them (p900 A10 to the periaqueductal grey, p901/902 Ch5 to the tectum, lateral hypothalamus and medullary reticular formation) describe rat data and were not used.

**Primate literature pass (2026-10-12, Europe PMC corpus #17, primate tract-tracing only).** Six new arrows, each route quote Opus-judged: raphe to globus pallidus (PMID 27028222 primate review, also states serotonin; PMID 6766111 macaque HRP in the internal pallidum), locus coeruleus to caudate and putamen (PMID 6664490, squirrel monkey retrograde), to the globus pallidus (PMID 6766111) and to the substantia nigra (PMID 6315152, squirrel monkey), VTA to the parietal lobe (PMID 2896323, Macaca fascicularis, dopaminergic neurons labeled; the paper pools substantia nigra and VTA). The four locus coeruleus arrows keep an `llm` transmitter (the abstracts name the nucleus, not noradrenaline). Family 10 went to cholinergic 8 / dopaminergic 8 / serotonergic 6 / noradrenergic 2. Still nothing citable: dopamine to the occipital lobe (PMID 33558867 says occipito-parietal cortex gets weak innervation from a VTA injection that spread into the substantia nigra, read but not used), serotonin to the subthalamic nucleus (PMIDs 1707079 and 7284825 found no dorsal raphe label after monkey subthalamic injections; others show 5-HT fibres without naming the raphe), serotonin to the claustrum (PMID 11489351 names no raphe), and every cholinergic gap (no primate abstract names both ends).

**Europe PMC transmitter/sign pass (2026-10-13, corpus #17).** Twenty abstracts were added to `PAPERS`, each with its claim and species. The books had already been exhausted for these sub-claims, and nothing primate states them in an abstract, so most of the evidence is from rodents or cats. The independent Opus judge confirmed all 20 picks, plus 4 projection-group and 3 target quotes, with 0 rejections. The pass took `projection_transmitter` from 28 to **18** `llm` and `projection_sign` from 15 to **8**:

- frontal to pons, glutamate: PMID 1374872 (review, "(glutamatergic) corticopontine fibers").
- pons to cerebellum, glutamate: PMID 2422596 (rat). Excitatory: PMID 9133571 (rat, mossy fibres).
- cerebellum to thalamus, glutamate: PMID 6147261 (cat). Excitatory: PMID 15558250 (human, "disynaptic excitatory pathways through the ventral thalamus") and 6147261.
- temporal to hippocampus, glutamate: PMID 20421986 (rat, perforant path from entorhinal layer III).
- hippocampus to fornix, excitatory: PMID 1981215 (rat, hippocamposeptal excitatory amino acid terminals, fimbria-fornix transection).
- fornix to mammillary, glutamate: PMID 32019 (rat, uptake lost after fornix transection).
- mammillary to thalamus, glutamate: PMID 19535593 (mouse). Excitatory: PMID 12576145 (rat).
- hippocampus to septum, excitatory: PMID 2808769 (rat).
- accumbens to globus pallidus, inhibitory: PMID 15740723 (rat, ventral pallidum) and Stahl Essential p128.
- amygdala to accumbens, excitatory: PMID 36653189 (mouse).
- frontal commissure, glutamate: PMID 22357796 (human TMS, "interhemispheric glutamatergic projections between motor cortices").
- parietal and occipital commissures, glutamate: PMID 32769158 (mouse, "glutamatergic callosal projections"). All three commissures keep the `set_claim` flag.
- raphe to olfactory bulb, serotonin: Nieuwenhuys p351 (dorsal raphe serotoninergic input) and PMID 27335411 (mouse).

Read but not used: the anterior commissure (temporal) has only the callosal sentence, which names the wrong tract. Septum to hypothalamus has two mouse papers (PMIDs 36642737 and 39150998, "LS GABAergic projection to the lateral hypothalamus"), but they write the septum only as "LS", so the endpoint filter never offers them. A `septal_nuclei` alias for "LS" would be too loose to add.

**Why the rest stays.** The candidates were read, not missed:

- **Claustrum to frontal / insula (route NOSOURCE):** the books give only topography and development ("situated between the putamen and the insular cortex"). No sentence states a claustral projection. Retried for the insula on 2026-10-12 against Europe PMC: the one primate sentence (PMID 2860583, "the insular lobe has connections with ... claustrum") was rejected by the Opus judge (no direction), and the directional ones are mouse (PMID 30534060), so the route stays NOSOURCE.
- **Cortex to striatum, closed as set-level (2026-10-10):** Nieuwenhuys p435 ("glutamatergic fibres from the cerebral cortex") and Kandel p986 ("Signals received by the striatum from the cerebral cortex and thalamus are conveyed by excitatory glutamatergic neurotransmission") now back the transmitter (both) and sign (Kandel) of frontal to caudate/putamen and parietal/temporal to caudate, via a documented allowance in `fetch_projection_worklist.py` (`SET_LEVEL_PAIRS`: lobes -> caudate/putamen, transmitter/sign only, never route). Opus-judged, no rejection. Each of those 8 sub-claims carries the derived `set_claim` badge (one sentence naming neither end, shared by pathways from 2+ origins), so they bucket **uncertain**, not verified. The same derivation also flags the sign of the 4 interhemispheric cortical commissures (frontal/parietal/temporal/occipital L->R), whose only sign sentence is the set-level "continuous network of excitatory elements potentially involving the entire neocortex": verified -> uncertain.
- **33 `blanket_claim` arrows (raphe, locus coeruleus, tuberomammillary, nucleus basalis to the lobes):** the books describe these systems by their sweep ("the entire neocortex", "the cerebral cortex"). No sentence names a single lobe as the target. The nucleus-basalis lobes got their transmitter from such a sentence, but the flag stays.
- **No transmitter/sign sentence for this pathway, in the books or an abstract (after 2026-10-13):** the sign of corticopontine and of fornix to mammillary, glutamate for thalamus to cingulate, both for cingulate to hippocampus, olfactory bulb to amygdala, insula to cingulate and septum to hypothalamus, GABA for amygdala to hypothalamus, glutamate for the anterior commissure (temporal), serotonin for raphe to accumbens, substantia nigra and septum, noradrenaline for the six locus coeruleus arrows, and dopamine for VTA to temporal. None of the six kinds here supports the UNKNOWN grade (`UNKNOWN_REQUIRED_SOURCES` lists only `drug_binding_action`), so these stay `llm` rather than becoming ∅.

**Contradictions:** none. Nieuwenhuys p391 and p387 call the septohippocampal projection cholinergic **and GABAergic**. That is consistent with our Acetylcholine value, but it is incomplete, and it is not reflected in the data.

**How to tackle.** Use a tract-tracing review for the claustrum. Decide whether a "cortex to striatum" sentence may source each lobe's striatal arrow. Read a systems-neuroscience text (e.g. Purves) for the Papez and cerebellar loops.

### 6b. `drug_enzyme_strength`, 13 / 147 missing (131 verified, 3 uncertain)

**What.** The tier on a drug's enzyme row (`claims.strength`): a substrate's `major` / `minor`, an inhibitor's or inducer's `strong` / `moderate` / `weak`. It is graded by a word test (`ENZYME_STRENGTH_WORDS` in `data_generators/quotes/attestation.py`) over the row's own quotes. The 2026-10-10 pass took it from 87 to **134**: 44 rows were already cited on a sentence stating the tier in words the test did not know ("mainly", "mostly", "predominantly", "largely", "almost exclusively", "most important", "to a lesser extent", "minimally", "slightly", "mild"), and 3 gained a sentence through the new tier pass of `apply_cyp_sources.py` (`cyp_strength_judged.json`, confirm-only: it never creates a row or changes a tier) or a better role pick. An independent Opus judge read every newly attested tier.

**Why the rest stays `llm`.** Read, not missed:

- **Tier given only as a percentage:** zolpidem CYP1A2 / CYP2C9 / CYP2C19 / CYP2D6 minor ("CYP3A4 (61%) CYP2C9 (22%), CYP1A2 (14%), CYP2D6 (<3%)"), clonidine CYP1A2 minor ("CYP2D6 (66%), CYP1A2 (10-20%)"), tizanidine CYP1A2 major ("CYP1A2 , 95%"). A number a reader must bucket is not a stated tier.
- **Tier only implied by contrast:** lofexidine CYP2D6 major and pitolisant CYP2D6 major (Stahl: "Metabolized by CYP2D6 and to a lesser extent by ...", "Extensively metabolized by CYP2D6"); nicotine CYP2B6 minor ("mostly CYP2A6 , and also by CYP2B6"), zonisamide CYP3A5 minor ("mostly by CYP3A4 , but also CYP3A7 and CYP3A5"). The judge rejected the nicotine and lofexidine tier explicitly.
- **Sole route, no tier word:** lorazepam / oxazepam UGT major ("only liver glucuronidation", "simply metabolized by glucuronidation").
- **Weaker wording:** xanomeline CYP2D6 major ("significantly contributes").

**Sources contradicting a stored tier (kept, flagged `contradicted` on the tier sub-claim only, 2026-10-10, Opus-judged; `CONTRADICTIONS`):** so 131 verified + 3 uncertain. clozapine CYP2D6 `minor` (Stahl p210 "to a lesser extent by CYP2D6") vs its Wikipedia drugbox "Liver , by several CYP isozymes mainly via CYP2D6"; fluvoxamine CYP1A2 `major` vs Wikipedia fluvoxamine "metabolized primarily by CYP2D6 and to a minor extent by CYP1A2"; sertraline CYP2D6 inhibitor `weak` (Stahl p770 "weakly at low doses") vs Wikipedia sertraline "Sertraline is a moderate inhibitor of CYP2D6 and CYP2B6 in vitro".

**FDA table, skipped.** FDA's "Drug Development and Drug Interactions" CYP table lists *sensitive* substrates (a strong inhibitor raises the AUC 5-fold or more). That is an interaction-exposure class, not a statement of an isoform's share of clearance, so it does not map onto `major` and was not used.

**How to tackle.** A label's clinical-pharmacology section (DailyMed, corpus #14) often states the fraction metabolized in words; a `fetch_cyp_worklist.py` DailyMed input would reach the percentage-only rows.

### 6c. `drug_first_approval`, 100 / 301 drugs carry none (surveyed 2026-10-11)

The regulatory-history pass (`fetch_drug_history.py` -> index picks -> `apply_drug_history.py` -> Opus judge, see `docs/DRUGS.md`) dates the first approval of 201 drugs (all `verified`) and records 31 market withdrawals over 17 drugs. The node exists only where a source dates it, so the 100 others are not counted as missing in the tally; they split into:

- **52 drugs whose stored EN and FR articles have no year-bearing approval or withdrawal sentence at all** in their lead or history-like sections (most of the older benzodiazepines and barbiturates, the phenothiazines, the recreational and anaesthetic substances, the Parkinson adjuncts). A next source would be a regulator's own record (Drugs@FDA for a US approval date, the BDPM `CIS_bdpm.txt` AMM date already on disk for France), which would date the approval in that one country, not the first one anywhere.
- **48 drugs whose candidates were refused**: patent or synthesis dates only; a later approval whose own page names an earlier market (sertraline UK 1990 vs US 1991, zolpidem, methadone, primidone, disulfiram); "1963 or 1964" style years; or recreational substances never approved.

**Earliest dated approval wins (2026-10-12).** An earlier dated approval proves a later one was not the first, so `history.earliest_wins` lets the Drugs@FDA year (corpus #18) displace a later Wikipedia "first approval", shown with the "first national approval" wording since a US date is not proven first worldwide; both appliers apply the rule, so their order does not matter. It replaced four: loxapine (Wikipedia 1978 France -> FDA 1975), midazolam (1986 France -> FDA 1985), pimozide (1985 US -> FDA 1984), pethidine (1943 -> FDA 1942). Their Wikipedia sentences stay in the judged file and win back if a refetch ever dates them earlier.

Withdrawals skipped on purpose: a brand or formulation discontinued (thioridazine's branded product, Palladone, the pipotiazine depot), a scheduling ban (phenazepam, tianeptine in Italy), and a withdrawal sentence naming no country (bupropion 1986, indalpine 1985, tolcapone 1998).

### 6d. `drug_enzymes` against the AGNP TDM guideline's Table 1 (cross-checked 2026-10-12)

The AGNP consensus guideline (corpus #19, `tools/fetch/fetch_agnp_tdm.py`) lists per drug the CYP / UGT / FMO3 isoforms metabolising it in its Table 1 (PDF pages 7-11). It ranks **last** among the metabolism sources (`tdm.merge_enzymes`): where it names a substrate isoform one of our corpora (Stahl, Wikipedia, CPIC) already states, its row is added as a second quote on that `drug_enzymes` node (184 rows); where none does, it becomes a substrate row of its own (141 rows over 78 drugs, 34 of which had no substrate row before). No `strength` is written: the table's bold marks an in vivo >= 50 % level change under a representative perpetrator, not a major route. Restricted to the isoform families Table 1 can name (CYP, UGT, FMO3), over the 152 roster drugs where at least one side names one, the cross-check before the merge read: **44 identical sets, 184 isoforms in agreement, 70 only in our data, 145 only in Table 1** (36 drugs had no substrate row of ours at all; 28 more are named in Table 1 with no isoform on either side). Of the 145, 141 are now rows; the 4 left out: paliperidone CYP3A4 + UGT (the stored page prints the drug cell as "9-hydroxyrisperi<u>done)</u>", so the joined "drug + cell" quote is never found and the fetcher writes none), nicotine UGT1A2 (a pseudogene in humans, UGT1A2P) and lamotrigine UGT3B7 (no such human isoform, likely UGT2B7), both listed in `tdm.NOT_ADDED`. Six isoforms joined `ENZYMES` for it (CYP1A1, UGT1A1, UGT1A3, UGT1A6, UGT2B4, UGT2B10). A named isoform supersedes a generic `UGT` row by the existing rule, so lorazepam, olanzapine and oxazepam lost theirs.

None of these is a `contradicted` flag: every difference is one side naming an isoform the other is silent on, and silence is not a denial (a table row lists the main routes, not every one). A generic `UGT` row of ours against Table 1's named UGT isoforms (or the reverse) is the same claim at two granularities, not a disagreement.

**How to tackle.** The "Only AGNP Table 1" column below is now AGNP-sourced rows (bar the 4 above); a second corpus confirming them would make them two-source. The "only ours" column is where Table 1 is silent, worth a look only where our row is a weak Wikipedia mention.

| Drug | Agree | Only ours | Only AGNP Table 1 |
|---|---|---|---|
| agomelatine | CYP1A2, CYP2C19 | CYP2C9 | - |
| amitriptyline | CYP1A2, CYP2C19, CYP2D6, CYP3A4 | - | CYP2C9, UGT1A3, UGT1A4, UGT2B10 |
| amphetamine_d | - | CYP2D6, FMO3 | - |
| amphetamine_dl | CYP2D6 | FMO3 | - |
| atomoxetine | CYP2C19, CYP2D6 | UGT | - |
| brivaracetam | - | CYP2C19 | - |
| bromazepam | - | - | CYP2C19, CYP3A4 |
| bromocriptine | - | - | CYP3A4 |
| bromperidol | - | - | CYP3A4 |
| brotizolam | - | - | CYP3A4 |
| buprenorphine | CYP2C8, CYP3A4, UGT2B7 | - | UGT1A3 |
| cabergoline | - | - | CYP3A4 |
| caffeine | CYP1A2 | CYP2C8, CYP2C9, CYP2E1, CYP3A4 | CYP2A6 |
| cannabidiol | - | - | CYP2C19, CYP2C9, CYP3A4 |
| carbamazepine | CYP3A4 | - | CYP1A2, CYP2C8, UGT2B7 |
| chloral_hydrate | - | - | UGT |
| chlordiazepoxide | - | - | CYP3A4, UGT |
| clobazam | CYP2C19, CYP3A4 | CYP2B6 | - |
| clomethiazole | - | - | CYP2A6, CYP3A4 |
| clomipramine | CYP1A2, CYP2C19, CYP2D6 | - | CYP3A4, UGT2B10 |
| clorazepate | - | - | CYP3A4, UGT |
| clozapine | CYP1A2, CYP3A4 | CYP2D6 | CYP2C19 |
| codeine | CYP2D6, CYP3A4, UGT2B7 | - | UGT2B4 |
| cyamemazine | - | - | CYP1A2, CYP2C19, CYP2C8, CYP2C9, CYP3A4 |
| desipramine | CYP2D6 | CYP1A2 | - |
| desvenlafaxine | CYP3A4 | CYP2C19 | UGT |
| diazepam | CYP2B6, CYP2C19, CYP3A4 | CYP2C9 | UGT2B7 |
| diphenhydramine | CYP2D6 | CYP1A2, CYP2C19, CYP2C9 | UGT1A4, UGT2B10 |
| disulfiram | - | - | CYP1A2, CYP2A6, CYP2B6, CYP2E1, CYP3A4 |
| donepezil | CYP2D6, CYP3A4 | UGT | - |
| dothiepin | CYP2D6 | UGT | CYP2C19 |
| doxepin | CYP2C19, CYP2C9, CYP2D6 | CYP1A2, CYP3A4 | - |
| doxylamine | - | CYP1A2, CYP2C9, CYP2D6 | - |
| entacapone | - | - | UGT1A9 |
| esketamine | CYP2B6, CYP2C9, CYP3A4 | CYP2C19 | - |
| estazolam | - | - | CYP3A4 |
| fenfluramine | - | - | CYP1A2, CYP2B6, CYP2D6 |
| flunitrazepam | CYP3A4 | - | CYP2C19 |
| fluoxetine | CYP2D6 | - | CYP2B6, CYP2C19, CYP2C9 |
| flupenthixol | - | - | CYP2D6 |
| fluphenazine | - | - | CYP2D6 |
| flurazepam | - | - | CYP2C19, CYP3A4 |
| fluspirilene | - | - | CYP3A4 |
| fluvoxamine | CYP1A2, CYP2D6 | CYP2C19, CYP3A4 | - |
| guanfacine | CYP3A4 | CYP3A5 | UGT |
| haloperidol | CYP3A4 | - | CYP2D6, UGT |
| heroin | - | - | UGT |
| hydroxyzine | CYP3A4 | CYP3A5 | - |
| imipramine | CYP1A2, CYP2C19, CYP2D6 | - | CYP3A4, UGT1A4, UGT2B10 |
| lacosamide | - | CYP2C9, CYP3A4 | CYP2C19 |
| lamotrigine | UGT1A4 | - | UGT3B7 |
| lemborexant | CYP3A4 | CYP3A5 | - |
| lisdexamfetamine | - | - | CYP2D6 |
| lorazepam | - | UGT | UGT2B15 |
| loxapine | CYP1A2, CYP2D6, CYP3A4 | - | CYP2C19, CYP2C8 |
| lumateperone | CYP1A2, CYP3A4, UGT | - | CYP2C8 |
| maprotiline | CYP2D6 | - | CYP1A2 |
| mdma | CYP2D6, CYP3A4 | - | CYP1A2, CYP2C19 |
| melatonin | CYP1A2 | CYP2C19 | - |
| mianserin | CYP2D6 | - | CYP1A2, CYP3A4 |
| midazolam | CYP3A4 | CYP3A5 | UGT1A4 |
| modafinil | CYP3A4 | CYP1A2, CYP2B6, CYP2C19, CYP2C9, CYP3A5 | - |
| morphine | UGT2B7 | - | CYP2C8, CYP3A4 |
| nabilone | - | - | CYP2C9 |
| nalmefene | - | - | UGT |
| naloxone | - | - | UGT2B7 |
| nicotine | CYP2A6 | CYP2B6, FMO3 | UGT1A1, UGT1A2, UGT2B10 |
| nortriptyline | CYP2D6 | CYP3A4 | - |
| olanzapine | CYP1A2, CYP2D6 | UGT | UGT1A4, UGT2B10 |
| oxazepam | - | UGT | UGT1A9, UGT2B15, UGT2B7 |
| oxcarbazepine | - | - | UGT2B15 |
| paliperidone | - | - | CYP3A4, UGT |
| paroxetine | CYP2D6 | - | CYP3A4 |
| perampanel | CYP3A4 | CYP3A5 | CYP2B6, UGT1A1, UGT1A4 |
| perazine | - | - | CYP1A2, CYP2C19, CYP2C9, CYP3A4 |
| perphenazine | - | - | CYP1A2, CYP2C19, CYP2D6, CYP3A4 |
| phenobarbital | CYP2C19 | - | CYP2C9, CYP2E1, UGT1A4 |
| phenytoin | CYP2C9 | - | CYP2C19, UGT2B15 |
| pimavanserin | CYP3A4 | CYP3A5 | - |
| prazepam | - | - | CYP3A4, UGT |
| primidone | - | - | CYP2C19, CYP2C9, CYP2E1 |
| promethazine | - | UGT | CYP2D6 |
| quazepam | - | CYP3A4 | - |
| quetiapine | CYP3A4 | - | CYP2D6 |
| ramelteon | CYP1A2, CYP3A4 | - | CYP2C19 |
| risperidone | CYP2D6 | - | CYP3A4 |
| rotigotine | - | - | CYP1A1, CYP1A2, CYP2C19, CYP2D6, CYP3A4, UGT |
| safinamide | UGT | CYP3A4 | - |
| selegiline | CYP2B6 | CYP2A6, CYP2C19 | - |
| sertraline | CYP2B6, CYP2C19, CYP2D6 | - | CYP2C9, CYP3A4, UGT1A1 |
| solriamfetol | - | - | CYP3A4 |
| suvorexant | CYP3A4 | CYP2C19 | - |
| temazepam | - | - | UGT2B7 |
| thioridazine | CYP2D6 | - | CYP1A2, CYP3A4 |
| tiagabine | CYP3A4 | UGT | - |
| topiramate | - | - | UGT |
| trazodone | CYP2D6, CYP3A4 | CYP1A2 | - |
| triazolam | - | - | CYP3A4 |
| trifluoperazine | - | - | UGT1A4 |
| trimipramine | CYP2C19, CYP2C9, CYP2D6 | - | CYP3A4, UGT2B10 |
| valproate | CYP2A6, CYP2B6, CYP2C9, UGT2B7 | CYP2C19, CYP3A5, UGT1A4, UGT1A9, UGT2B15 | UGT1A3, UGT1A6 |
| venlafaxine | CYP2D6 | - | CYP2C19, CYP2C9, CYP3A4 |
| vortioxetine | CYP2A6, CYP2C9, CYP2D6, CYP3A4 | CYP2B6, CYP2C19, CYP2C8, CYP3A5 | - |
| zolpidem | CYP1A2, CYP2C9, CYP3A4 | CYP2C19, CYP2D6 | - |
| zonisamide | CYP3A4 | CYP3A5 | - |
| zopiclone | CYP3A4 | CYP2E1 | CYP2C8 |
| zotepine | CYP1A2, CYP3A4 | - | CYP2D6 |
| zuclopenthixol | CYP2D6 | CYP3A4 | - |


### 7. Kinds now closed

Kept as a record of which lever worked, so a later session does not re-derive it:

- **`structures` 54/54.** Kandel for 48, then claustrum + fornix + tuberomammillary against
  **Nieuwenhuys** (corpus #6), which Kandel does not describe in prose.
- **`circuits` 6/6.** The two basal-ganglia loops from Kandel p983 (Albin scheme); the other
  four reuse quotes already verified for their member projections, so no quote is duplicated.
- **`projection_groups` 12/12.** Glutamate and GABA from Stahl Essential; the monoamine,
  neuroendocrine and modulatory systems from Kandel. The sign groups reuse their
  dominant transmitter's quote. Acetylcholine (Nieuwenhuys p545 + Kandel p1048) and
  noradrenaline (Stahl Essential p295 + Nieuwenhuys p545) closed on 2026-10-13, after their
  earlier Kandel quotes had been judge-rejected. Each quote covers only part of the
  description, e.g. the stress response is not stated.
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
- **`drug_enzymes` 428/428.** The four-step pipeline over two corpora: `fetch_cyp_worklist.py`
  offers candidate sentences from Stahl's Pharmacokinetics block and the stored English articles
  (corpus #9) with no verdict of its own, a model answers with a candidate **index** plus
  (enzyme, role, strength), and `apply_cyp_sources.py` gates the answer (the quote must name the
  claimed isoform, and be verbatim on the cited page). Stahl wins any pair both state. 172 drugs,
  342 substrate / 68 inhibitor / 18 inducer. This kind was the last one no model had ever read:
  two regex fetchers wrote it until 3.74.0, and replacing them added 88 nodes, mostly the plural
  and class-inclusion subjects a pattern cannot resolve ("Bupropion **and its metabolites** are
  inhibitors of CYP2D6", "Nitrobenzodiazepines **such as** nitrazepam ... are metabolically
  activated by CYP3A4"), while dropping four rows that stated the opposite of their own source.
- **`receptor_density` 36/36 and `target_density` 17/17.** Allen microarray intensity
  (corpus #8), one node per profile with the whole profile written into the quote, published
  only above the cross-donor reliability floor.
- **`receptors` (family) 56/56.** Stahl Essential for 54; the last two (5-HT1E and 5-HT1F,
  which the Essential corpus never names outside affinity-table cells) against GtoPdb's own
  family label (corpus #12), a direct read: "5-Hydroxytryptamine receptors" *is* serotonergic.
- **`targets` (classification) 25/25.** NKCC1 and the CGRP receptor closed last (see #1b). Stahl Essential for 16; carbonic anhydrase, PDE5, the
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
families, all four `targets`, the α2 `target_polarity`, the last 2 `references`), and the **hand-curated drug-binding pass** (21 of the 33 unsourced bindings). Headline
over that run: 55% to 67% to 78% to 95% to 96%, then down to 94% as the receptor split and
the roster expansion enlarged the denominator, then back to **96%** (see the snapshot).

1. ~~**The non-Stahl `drug_categories`.**~~ **Done** (46 closed from stored Wikipedia leads,
   see section 2). The 16 left are 6 unfetched articles, 6 leads that do not state our class,
   and 4 label mismatches to review.
2. ~~**`drug_bindings` (33), opportunistic.**~~ **Done** (21 of 33 closed by hand from Stahl
   and Wikipedia pharmacodynamics prose; see section 3). The 12 left need primary literature:
   the 7 GABA-A modulatory-site bindings will not close because no database assays that site,
   and the other 5 are prose gaps in the drugs' own articles.
3. ~~**The classification residue.**~~ **Mostly done** (2026-10-10 prose pass, see #1b):
   the 7 ion-channel signs, GABA-B and sigma-1's class closed; the 4 sign conflicts wait on a
   *data* decision.
4. **`receptor_synaptic` (14 left of 48).** The same prose pass closed 34 (see #1); the rest
   need a neuropharmacology textbook read or a data decision (2 contradictions), and a
   fraction will honestly stay `llm`.
5. **The last 2 `projections`**, claustrum-specific primary literature; may honestly stay
   `llm`.
6. **The 37 expression-location nodes: do not chase.** Off-atlas bases and transporter mRNA
   sitting at the source nucleus are properties of the assay. Only a protein-level atlas
   would move them, at a licence and parcellation cost out of proportion to the count.

**Sources we still need (beyond the thirteen wired):**
- **A neuropharmacology textbook** (Rang and Dale, Katzung) for the 14 `receptor_synaptic`
  nodes in step 4. This is the only gap left that a whole new corpus would address, and even
  it will not close completely.
- **NCBI/PubMed primary literature** (wired as Europe PMC, corpus #17) as the genuine last
  resort for the handful of claims no reference book states. It closed 17 projection
  sub-claims on 2026-10-13 (see #6). It still lacks claustrum connectivity with a direction, the
  locus coeruleus arrows' noradrenaline, and a few subtype affinities.
- Nothing else. Every other gap in this document is a documented limit of a source we already
  hold, and adding a corpus to chase it would cost more than the honesty of the `llm` pill.

## Candidate new data *dimensions* (surveyed 2026-07-26)

The sections above are about grading nodes we already have. This one is about node kinds we
do **not** have: axes the dataset could gain. Each entry says what exists in the world, what
it would cost, and the verdict, so a later session does not re-survey it.

### Drug **time-to-peak (Tmax)**, and the wider PK the simulation would need (surveyed 2026-09-16)

> **Shipped (3.87.0, extended in 3.88.0).** Both passes below are done: the prose one, then
> DailyMed as corpus #14. `fetch_tmax.py` -> `apply_tmax.py` -> `recheck_quotes.py` put a
> sourced Tmax on **136 drugs** (kind `drug_tmax`, all 136 `verified`), and `js/sim-model.js`
> rises to a drug's own peak where one exists. The gap this section measures is therefore the
> **165 drugs still on the assumed 2 h**, and it is now mostly a jurisdictional one: a drug
> never marketed in the US has no SPL, and the label of one that is states a peak for a
> formulation or population the claim cannot generalise from.

Asked for the simulation tab, which gave **every** drug one assumed 2 h time-to-peak
(`TMAX_HOURS` in `js/sim-model.js`), so a drug that peaks in 20 minutes and one that peaks in
8 hours drew the same curve. Per-drug Tmax is the cheapest real fix, and unlike the rest of the
PK list below it is genuinely sourceable.

**Measured coverage over the 301 roster drugs**, against the corpora already on disk (a
sentence counts only when it names a peak AND carries a duration):

| source | drugs reached | shape |
| --- | --- | --- |
| Wikipedia article prose (corpus #9, 295 stored) | **104** | "reaches peak levels after 1.0 to 2.5 hours" |
| Stahl monograph span (corpus #1, 158 indexed) | 13 | mostly the newer monographs' PK bullets |
| DailyMed label section 12.3 (corpus #14, 75 labels) | **67** | "reaching peak plasma concentrations in 1.5 hours" |
| union of the three | **169** (56%) | 56 of them only the label states, 132 drugs state it nowhere |

The Wikipedia **drugbox** is NOT the shortcut it looks like. It has no Tmax row at all (0 of
295), and its `Onset of action` row is a *different fact*: of its 76 rows only **16** are
explicitly annotated as a peak ("1-2 hours (T max)"), the other 60 being clinical onset
(alprazolam's "30-60 minutes" is when it works, not when it peaks). Taking that row as Tmax
would silently publish onset as peak on 60 drugs, so a code extraction is worth only those 16
and the real pass is prose.

**How it went, in two passes.** Both are the same four-step shape as every other pass here
(worklist of candidate sentences -> one LLM pass answering by index -> quote-gated applier ->
recheck), riding the existing `fetch_pharmacokinetics.py` machinery since it already scans for
durations.

*Pass 1, the stored prose (3.87.0).* The fetcher offered 113 drugs / 171 candidate lines, the
extraction claimed 92 (21 skipped as a metabolite's peak, a depot formulation, a
subjective-effects time course, or a range the duration parser cannot express), and the Sonnet
judge rejected 2 more (the dextroamphetamine sentence is about the mixed-salts product, the
dimenhydrinate one gives its diphenhydramine moiety's peak), leaving 90.

*Pass 2, DailyMed as corpus #14 (3.88.0).* `fetch_dailymed.py` searched the 211 drugs without a
Tmax and stored 75 labels (67 have no SPL at all, 66 have one whose PK section never names a
peak, 4 are roster combos it skips). That offered 79 more drugs / 140 candidate lines; the
extraction claimed 50 and the Sonnet judge rejected 4, all for the same reason and a useful one
to record: a label states a peak **conditionally**, so the sentence that names a figure often
names it for one tablet strength (donepezil 23 mg vs 10 mg), one population (midazolam's
pediatric syrup study), one route (fentanyl's sublingual ABSTRAL) or one state (sumatriptan
during an attack vs between them), and none of those is the drug's general Tmax. 46 landed,
for 136 in total.

**What is left is jurisdictional, not technical.** A roster drug never marketed in the US
(alpidem, many EU-only agents) has no SPL, and the EMA's SmPC equivalent is PDF.

*Pass 3, BDPM as corpus #16 (3.95.0, Claude Code).* The French public drug database closes part of that jurisdictional gap with machine-readable RCPs. Of 301 drugs, 162 join a single-active French product and 60 get a usable RCP (135 have no French product at all, 4 exist only in combinations, 5 only as modified-release or patch: prazosin, hydromorphone, flunarizine, rotigotine, bupropion). 35 Tmax picks were judged by Opus, 4 rejected (prazepam, clorazepate, tetrabenazine: a metabolite's peak; ethosuximide: a child-only value), for **167** drugs with a Tmax (from 136). Half-life gains only bumetanide (275), but the RCPs disagree with 12 existing values (e.g. ondansetron 5.7 h vs 3 h, furosemide 2 h vs 50 min), left unchanged. The same pass adds 116 French brands to 70 drugs (fr brand nodes 79 -> 195; drugs with any brand 185 -> 230).

**The rest of the PK list is a different story, and it is worth writing down why.** The
simulation cannot report occupancy, only a relative engagement index, because occupancy is
`(C/Ki)/(1 + Σ C/Ki)` and a Ki supplies only the denominators. Turning the index into a
percentage needs, per drug: dose + molar mass, bioavailability F, volume of distribution Vd,
plasma free fraction fu, and the unbound brain-to-plasma ratio **Kp,uu**. The drugbox does
carry two of them as structured rows (bioavailability 221 of 295, protein binding 183), but
the chain is only as strong as its weakest link and **Kp,uu is the link with no open source at
all** (see "Drug blood-brain-barrier penetration" below: no machine-readable database exists,
the compiled sets are small, paywalled and mostly rodent). Dose is not a drug property either;
it is a prescription. So the index is not a stopgap: it is the honest ceiling of what a Ki
plus a T½ can say, and the tab says so in as many words.

### Drug **elimination half-life (T½)** beyond Stahl (surveyed 2026-10-08)

> **Shipped (3.92.0).** `fetch_half_life.py` -> `apply_half_life.py` -> `recheck_quotes.py`
> took `drug_half_life` from **230 to 274 of 301** drugs (269 `verified`). The gap this
> section measures is the **27 drugs that still state none**, and it is a roster-edge
> problem, not a corpus one.

The half-life came from one place, `apply_pharmacokinetics.py` reading a Stahl monograph's
Pharmacokinetics bullets, so the question "why does caffeine have no half-life?" had one
answer for a whole class of drugs: **Stahl has no monograph for a drug nobody prescribes**.
158 of the 301 roster drugs are indexed in the Prescriber's Guide; the other 143 were on
whatever their Stahl-less record happened to carry. That left three distinct shapes:

- **no monograph at all**: every recreational and research substance (caffeine, nicotine,
  cocaine, MDMA, LSD, THC, DMT, salvinorin A, PCP), the dopamine agonists and
  antiparkinson agents (pramipexole, ropinirole, rotigotine, bromocriptine, cabergoline,
  apomorphine, rasagiline, safinamide, amantadine), the non-psychiatric CNS agents
  (furosemide, domperidone, doxylamine, cyproheptadine), and the drugs withdrawn or
  never US-marketed (alpidem, pipothiazine, zotepine, perospirone, ketanserin);
- **a monograph with no PK line**, which is why phenelzine and perospirone looked like
  oversights rather than absences;
- **a number with no source**, 8 drugs carrying an `llm` value nobody had ever checked.
  Three now carry a quote; flupenthixol's unsourced 192 h turned out to be the decanoate
  depot's, replaced by the oral compound's sourced 35 h.

The fetcher is `fetch_tmax`'s duration scan with one pattern swapped, over the same three
stored corpora, so the pass cost nothing to build. Coverage it found: Wikipedia prose +
drugbox (corpus #9) reached 44 of the 48 it offered, Stahl 2, DailyMed 2. **The drugbox is
the shortcut here that it is not for Tmax**: its `Elimination half-life` row is the fact
itself, not an adjacent one, which is why this pass landed in a single batch where the peak
needed two.

**The residual 27, by why they are missing.** 25 state no half-life in any stored corpus:
either the drug has no English Wikipedia pharmacokinetics section (`azacyclonol`,
`calcium_carbimide`, `caprylidene`, `indalpine`, `prothipendyl`, `sulfonmethane`,
`tropatepine`, `perazine`, `bromperidol`, `fluspirilene`, `butobarbital`, `cyclobarbital`,
`clorgiline`, `pargyline`, `xanomeline`, `rimonabant`, `cannabinol`, `rubidium_chloride`,
`reserpine`, `benserazide`, `bumetanide`, `rimegepant`), or **no half-life is the right
answer**: a gas titrated to effect has none to state (`nitrous_oxide`, `xenon`), and a
combination product's is per constituent (`naltrexonebupropion`). Two more were offered and
deliberately refused: **ethanol** eliminates at a constant rate, so the article's
"4.0-4.5 hours at very high concentrations" is not a half-life, and **nabilone**'s sentence
gives 2 h for the drug and 35 h for total radioactivity, of which only the 35 h parses.

**5 drugs keep an unsourced value on purpose**: the four combination products
(`dextromethorphanbupropion`, `dextromethorphanquinidine`, `phenterminetopiramate`,
`deutetrabenazine` as a deuterated variant) and `methylfolate_l`, whose only corpus
sentence qualifies itself to the *d,l* racemate while the same page warns the L form may
not follow typical drug kinetics. Closing these needs a per-constituent model, not a
better corpus.

### Enzyme **metabolizer-phenotype variability** past PharmFreq (surveyed 2026-10-08)

**5 of the 18 isoforms we model carry a profile** (`cyp2b6`, `cyp2c9`, `cyp2c19`, `cyp2d6`,
`cyp3a5`), and the two the drug roster leans on hardest are not among them: **CYP3A4 clears
109 of the 301 drugs** here and **CYP1A2 46**. 3.92.1 makes that absence visible in the
panel instead of silent; this records why it cannot simply be filled.

**PharmFreq stops where CPIC stops.** It indexes the CPIC **level A** gene-drug pairs: 21
genes, 658 alleles ([Tremmel et al., *Nucleic Acids Res* 2025;53:D1498](https://doi.org/10.1093/nar/gkae1016)).
CYP3A4, CYP1A2, CYP2A6, CYP2E1 and every UGT but UGT1A1 are absent **by design**, so there
is no fresher export to download. PharmVar's own 2026 CYP1A2 GeneFocus says it outright:
"The Pharmacogenetic Allele Frequency (PharmFreq) database currently does also not contain
any information on CYP1A2" ([*Clin Pharmacol Ther*, doi:10.1002/cpt.70286](https://doi.org/10.1002/cpt.70286)).
The export on disk does hold a 6th gene, **UGT1A1**, that `GENE_ENZYMES` deliberately does
not map: no roster drug's glucuronidation is attributed to UGT1A1 specifically, and the 22
drugs on the generic `ugt` bucket name no gene at all, so there is nothing to attach it to
without inventing a specificity the drugbox does not state.

**The blocker is the translation table, not the frequencies.** A PM/IM/NM/RM/UM profile
needs an agreed diplotype-to-phenotype mapping, and CPIC publishes one only for its
guideline genes. For these two that is a fact about the biology, not a hole in the
literature: CYP1A2's clinically dominant variance is **induction** (smoking, cruciferous
vegetables, omeprazole) and the `*1F` promoter variant modulates inducibility rather than
defining a phenotype class, while CYP3A4's is induction/inhibition by co-medication, which
is the one axis this dataset already models (the drug-to-drug edges in `docs/DRUGS.md`).

**What is sourceable, and in what shape** (each tested, not assumed):

| claim | source | what it actually gives | verdict |
| --- | --- | --- | --- |
| PM/IM/NM/RM/UM frequency per population | PharmFreq, corpus #13 | the shipped profile | done, 5 isoforms, closed |
| which CYP3A4 allele matters + its function | [Pratt et al., *J Mol Diagn* 2023;25(9):619-629](https://doi.org/10.1016/j.jmoldx.2023.06.008) (PMID 37419245, AMP/CPIC/CAP/DPWG/ESPT/PharmGKB joint consensus, free PMC) | tier 1 = `CYP3A4*22`, decreased function, defining variant rs35599367, multiethnic AF **0-9%**; tier 2 = `CYP3A4*20` | citable and quotable, but its frequency column is a **range across ethnicities**, not a per-group profile |
| per-ancestry frequency of that allele | gnomAD v4 GraphQL (`https://gnomad.broadinstitute.org/api`, no key, tested) | rs35599367 = `7-99768693-G-A`: overall **3.17%**, nfe 4.92, asj 5.82, amr 2.55, mid 1.70, sas 0.91, afr 0.88, **eas 0.00** | machine-readable, and its ancestry groups map onto PharmFreq's 8; it is an **allele** frequency, not a phenotype one |
| rsid to GRCh38 position (what gnomAD is keyed by) | dbSNP `efetch` (no key, tested) | per-study MAFs + position | the resolver a star-allele pass would need |
| allele definitions past the AMP tier-1 list | PharmVar | the REST API needs a key (401 on an anonymous call); the per-gene download is the usable route | only needed if the pass goes past tier 1 |

**Verdict: reachable, but it is a second claim shape, so it is a decision, not a chore.**
A `CYP3A4*22 is carried by ~5% of Europeans and ~0% of East Asians` node is honest,
genuinely interesting (it is the mirror image of CYP3A5*3) and two tested free sources
away. It is **not** the same claim as the stacked bar: one says how common a *speed* is,
the other how common an *allele* is, and rendering them in the same section would let a
reader read an allele frequency as a phenotype frequency. It therefore wants its own node
kind (`enzyme_allele`, one node per (isoform, allele)) and its own display, plus corpus #15
(gnomAD) and a quote shape for a number pulled from an API rather than a page.

Two gotchas to design around before writing any of it: a defining SNV's frequency equals
its allele's only when nothing else on the haplotype matters, and **a whole-gene deletion
is invisible to gnomAD's SNV frequencies**, so `CYP2A6*4` (the 15-20% East Asian deletion
that drives nicotine clearance) and CYP2D6's CNVs cannot be reached this way at all. An
allele-frequency pass would therefore cover the SNV-defined alleles and have to say so.

### What CPIC levels that we deliberately do not import (surveyed 2026-10-09)

Corpus #15 ships 104 rows over 18 drugs and 4 genes. CPIC levels more than that, and every
exclusion below is printed by `tools/fetch/fetch_cpic.py` on each run rather than left to be
rediscovered:

- **Genes with no metabolizer-frequency profile here.** HLA-A and HLA-B (carbamazepine,
  oxcarbazepine, phenytoin), SCN1A, and the urea-cycle genes with valproate. These are not
  clearance speeds at all: an HLA allele is a hypersensitivity risk, so corpus #13 has nothing
  to pair a row with and the readout would be guidance with no base rate beside it. Importing
  them would need a different frequency source **and** a different panel, since the section's
  whole shape is "how fast does this person clear it".
- **CPIC's uncertainty phenotypes:** `Likely Intermediate`, `Possible Intermediate`,
  `Indeterminate`, `No Result`. Same reason: PharmFreq reports five speeds, so these have no
  frequency to sit next to.
- **Pairs CPIC has levelled but written no guideline for yet**: aripiprazole, brivaracetam,
  pitolisant, risperidone. Nothing to quote; re-running the fetcher picks them up the day CPIC
  publishes the text.
- **Ondansetron**, whose CYP2D6 rows CPIC files under tropisetron, so the guideline's own
  sentences do not name the drug we would attach them to.
- **`pediatrics`** as a population: the panel reads one population per pair out of `general` /
  `adults` / `PHT naive`, and a paediatric row states different kinetics for a reader this site
  is not written for.

The one real hole the import surfaced rather than created, now **closed** (3.93.1): CPIC levelled
clomipramine/CYP2C19 while our enzyme data had no CYP2C19 row for clomipramine, so that guidance
block sat over an Enzymes section that never mentioned the gene. 28 of the 29 frequency-covered
pairs matched; this was the 29th. Nothing else here states the route: Stahl attributes the
demethylation to CYP1A2 ("by demethylation via CYP1A2", p. 181), the English Wikipedia article
names only CYP2D6 (live article checked 2026-10-09, no CYP2C19 anywhere in it), Carlat's
pharmacogenetic table lists clomipramine only under CYP2D6, and the DailyMed label is a pre-2006
one that names no isoform at all. CPIC itself does state it, in the faster-metabolizer
recommendation: *"Consider alternative drug not metabolized by CYP2C19; If clomipramine is
warranted, utilize therapeutic drug monitoring to guide dose adjustment."* That sentence names
the gene **and** the drug, so `cpic.enzyme_claims_for` reads it as the route, and only that
phrasing: a levelled pair with no such sentence still adds nothing (5 pairs qualify, 4 of which
already had the row from another corpus and keep it).

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
Stahl bullet, so `lib/corpora/wikipedia.py` imports `fetch_cyp.py`'s role/strength/victim rules and
adds only what a long prose paragraph needs: a sentence split, a negation veto, a rule that the
drug's own name must appear before the verb with no `which` / `that` / paren / comma between. Those
rules are what stops the wrong claims a paragraph offers: "Smoking induces CYP1A2" read as
clozapine inducing it, a co-prescribed victim drug's profile read as the subject's
("... mirtazapine, which is mainly metabolized by ..."), and a reference-list title read as prose.
Yield: **190 nodes over 101 drugs**, of which **109 over 62 drugs** survive the Stahl-first merge
(Stahl already stated the rest), taking `drug_enzymes` from 159/86 to **268 nodes over 119 drugs**,
all verified.

**Audited 2026-07-28 (the "does alcohol induce anything?" question), +5 nodes.** Re-running the
pass's own rules over every stored article and printing the *rejected* role sentences showed 26
drops, 22 of them right. The four wrong ones were two over-broad vetoes, both now fixed in
`lib/corpora/wikipedia.py`:
- the **victim frame was tested on the whole sentence**, so a genuine claim was vetoed by its own
  consequence clause ("Escitalopram weakly inhibits CYP2D6, and hence may increase plasma levels
  of some CYP2D6 substrates"). It is tested on the **head** only now: what follows the verb is
  that claim's consequence, not a second subject.
- the **two-roles-in-one-sentence veto** dropped every "a weak inducer of CYP3A4 and a weak
  inhibitor of CYP2C19". Split by position instead: each enzyme belongs to the role verb it
  follows, each role is qualified from its own segment, and a later verb counts only while it
  stays coordinated with the first (a comma / `that` / paren in between still hands the verb
  someone else, which is what keeps nefazodone's "medications that are metabolized by CYP3A4" out).

Alcohol itself was **not** a data error: no corpus we hold states that ethanol *induces* anything
(the CYP2E1 induction claim lives on the CYP2E1 article, and the pass reads only the drug's own
article), so publishing it would have been unsourced. The audit did find a real miss next to it:
ethanol's own drugbox row names **alcohol dehydrogenase** beside CYP2E1, and the extractor only
ever looked for `CYP`, so the route we already model as `adh` was invisible. Fixed, and the field
was named `enzyme` for exactly this.

**Still open there:** two known limits, both yield rather than correctness.
- **Non-CYP vocabulary: mostly closed** (2026-09-07, Claude Code). `ENZYMES` now carries CES1,
  FMO3 and the UGTs (a generic `ugt` for a source that names no isoform, plus UGT1A4 / 1A9 /
  2B7 / 2B15), and the role patterns govern them exactly as they do a cytochrome, so the routes
  are read from the drugbox row AND from prose. That was not a yield question: methylphenidate,
  cleared almost entirely by CES1, read as *unmetabolized* rather than as metabolized elsewhere.
  It also gave Stahl's own pass the two UGT rows it had been dropping from viloxazine's quote.
  **Still out:** AKR, SULT, DBH (rare, one drugbox each), and MAO, which is deliberately left
  alone: it is a modeled drug *target* too, so a sentence naming it is usually about the drug
  acting on the enzyme, not being cleared by it. Splitting those two senses needs more than a
  phrase pattern.
- **Pronoun subjects.** Three genuine claims are unreachable because the sentence says "It"
  (reboxetine, selegiline at CYP2B6, clomethiazole at CYP2B6/2A6). Resolving the antecedent
  is what the subject rule deliberately refuses to guess; hand-curating those three is the
  cheaper answer if they are ever wanted.

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


### Beyond psychiatry: the CNS families the roster pass could not see (surveyed 2026-09-06)

Same kind of survey as the section above, and the same rule: measure once, write it down.
Prompted by noticing morphine and tramadol were absent. **Cause:** both growth routes were
psychiatry-shaped (Stahl's 158 monographs, then the three Wikipedia *psychotropic /
psychiatric medications* lists), so a CNS-active drug that no psychiatrist prescribes was
never a candidate. The absence was an artefact of the sources, not a scope decision.

**Status: opioid analgesics acted on (v3.60.0)**, taking the roster to 259 drugs. The mu,
delta and kappa receptors were already modeled, and PDSP (#5) plus GtoPdb ligand
interactions (#11) cover the family well, so the pass cost no new targets. Then
**antiparkinson (v3.65.0)** and **migraine (v3.67.0)**, the latter costing the one new
target the table priced it at (CGRP, a peptide receptor). Four families remain, cheapest
first:

| family | missing | what it needs first |
|---|---|---|
| antiemetics + antihistamines | metoclopramide, meclizine, dimenhydrinate, granisetron | nothing: D2/H1/5-HT3 all modeled |
| antiepileptics | vigabatrin, ethosuximide, lacosamide, brivaracetam | GABA-T and a T-type calcium channel target (SV2A exists) |
| psychedelics + dissociatives | psilocybin, mescaline, ibogaine, salvinorin A, 2C-B, nitrous oxide, phencyclidine | nothing: 5-HT2A and NMDA modeled; overlaps the `recreational` category |
| anesthetics | propofol, sevoflurane, isoflurane, etomidate, xenon | nothing, but the volatiles have no PDSP panel, so most land affinity-only or unbound |

Already covered, so not a gap: the dementia drugs, the Tier-1 European antipsychotics and
benzodiazepines from the roster pass above, and the loose CNS set (baclofen, modafinil,
pitolisant, prazosin, biperiden, meprobamate, clonidine, guanfacine, atomoxetine).

**The loose ends are closed too (v3.68.0).** The same survey left a tail that fit no family
heading: the appetite / sympathomimetic drugs (phentermine, fenfluramine, ephedrine,
pseudoephedrine, sibutramine, yohimbine) and four singletons (tiapride, opipramol, atropine,
betahistine). All ten are in, on the modeled targets, at the cost of one new class
(`appetite_suppressant`). Phentermine had been reachable only as half of the
phentermine/topiramate combo.

**Deliberately skipped: loperamide.** It is a mu agonist, but a peripherally restricted one
that does not cross the blood-brain barrier at therapeutic doses. Adding it would light brain
regions the drug never reaches, and the dataset has no BBB-penetration dimension to say so
(that candidate dimension is surveyed above). Revisit if BBB penetration is ever modeled.
