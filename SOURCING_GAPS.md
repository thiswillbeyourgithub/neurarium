# Sourcing gaps: what is not yet `verified`, why, and how to tackle it

The dataset grades every **node** (any sourceable datum, see `CLAUDE.md` "Nodes")
`llm` < `sourced` < `verified`. `verified` is the top grade: a quote was
programmatically confirmed present in a cited source page (or a Ki row in the PDSP
CSV). This document lists everything **not** at `verified`, says **why**, and gives an
**idea to tackle it**. Numbers come straight from `meta.provenance_stats` (regenerate
with `python tools/generate_data.py`, print the table with `python tools/check_data.py`),
so re-derive them after any data change rather than trusting the counts below forever.

Made with the help of Claude Code.

## Snapshot (2026-07-04, after the drug-class + circuits/groups/refs + Nieuwenhuys wins)

Headline: **1110 / 1665 knowledge nodes backed (67%)**. In the tally a bare `llm`
grade counts as **missing** ("an LLM asserted it from memory" = no document), so
"missing" below means `llm` or no source at all. 555 knowledge nodes are missing.

> **Recently closed.** Several smaller kinds are now fully (or nearly) sourced:
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
> Headline 55% (pre-drug-class) to 67%. The table below is the post-win state.

| Node kind | Missing | Total | Share of the gap | Difficulty | Best lever |
| --- | ---: | ---: | ---: | --- | --- |
| `receptor_locations` | 383 | 383 | 69.0% | Hard | expression atlas |
| `target_locations` | 124 | 124 | 22.3% | Hard | expression atlas |
| `receptors` (mechanism) | 26 | 56 | 4.7% | Medium | IUPHAR Guide to Pharmacology |
| `drug_bindings` | 12 | 632 | 2.2% | Medium | PDSP refresh + primary lit |
| `projections` | 4 | 103 | 0.7% | Hard | claustrum primary lit |
| `targets` (classification) | 4 | 25 | 0.7% | **Easy** | IUPHAR / textbook |
| `drug_categories` | 2 | 158 | 0.4% | flagged | Stahl "Class" line |
| `structures` (anatomy) | 0 | 52 | **DONE** (52/52) | done | Kandel + Nieuwenhuys |
| `circuits` | 0 | 6 | **DONE** (6/6) | done | Kandel prose |
| `projection_groups` | 0 | 10 | **DONE** (10/10) | done | Stahl Essential / Kandel |
| `references` (Wikipedia links) | 0 | 298 | **DONE** (not in headline) | done | Wikipedia URLs |

**The shape of the problem:** two kinds are now **91%** of the remaining gap, both
per-region "expression" claims (`receptor_locations` + `target_locations` = 507 nodes)
that need a brain expression atlas we do not yet have wired. Everything else combined is
9% of the gap and is mostly "the books we hold do not state it in prose."

Five book corpora are wired into `SOURCE_CORPORA` today (`stahl`, `kandel`,
`stahl_essential`, `carlat`, `nieuwenhuys`) plus the `pdsp_ki` CSV. The book-prose wins
those allow are largely exhausted (see the sourcing memory); the remaining gaps mostly
need a **new kind of source**: an expression atlas, a receptor-classification database,
or (for the last two claustrum pathways) primary literature.

---

## The gaps, biggest lever first

### 1. `receptor_locations`, 383 / 383 missing (the single biggest gap)

**What.** One node per `(receptor, region)` pair: the claim "receptor R is expressed in
region B" (the panel's "Found in" rows). All 383 are `llm` (which regions express a
receptor was asserted from memory), none quote-checked.

**Why not verified.** None of the four wired book corpora is an expression atlas. Stahl
Essential localizes a handful of receptors in figures, not a per-region table we can
quote-gate. So there is no document to check these against.

**How to tackle.** Needs a structured **brain expression atlas**, then a fetch+join tool
modeled on `fetch_ki.py` (which already solved the "join an external table onto our ids,
cite one representative row, quote-gate it author-side" problem):
- **Allen Human Brain Atlas** / Allen Mouse Brain Atlas (ISH + microarray expression by
  region), the canonical regional-expression source, has an API.
- **Human Protein Atlas** (brain section: regional protein/RNA expression, downloadable
  TSV, permissive licence), probably the cleanest to vendor + cite.
- **IUPHAR/BPS Guide to Pharmacology**, each receptor page has a "Tissue Distribution"
  section with primary-lit citations.
The hard part is **granularity mismatch**: atlases parcellate finely (dozens of nuclei)
while we model coarse lobes/nuclei, so the join needs a hand-curated atlas-region to
`base` map (like `fetch_ki.py`'s `ALIAS` map). Start with the transporters/enzymes and
the well-mapped monoamine receptors where the atlas is unambiguous; leave the ambiguous
ones `llm`. This is the biggest single lever on the headline %.

### 2. `target_locations`, 124 / 124 missing

**What.** The `target_locations` mirror of #1 for non-receptor targets (SERT, MAO-A/B,
VMAT2, ion channels, ...): "target T is expressed in region B." All `llm`.

**Why not verified.** Same as #1: no expression atlas wired.

**How to tackle.** Same atlas + join as #1, and **do it in the same tool** (the emitter
`_location_sources` + validation is already shared between receptors and targets, so one
fetch tool feeds both). Transporters and metabolic enzymes are better characterized and
more coarsely distributed than fine receptor subtypes, so these 124 are likely the
**easier half** of the expression problem, a good place to prove the atlas pipeline
before tackling the 383.

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
6. **`target_locations` (124), then `receptor_locations` (383)**, the big prize (91% of
   the remaining gap) and the hardest. Build the expression-atlas fetch+join tool (model
   on `fetch_ki.py`), prove it on the coarser target expression, then extend to receptors.
   This is the one that needs real new infrastructure and the atlas-region to `base` map.
7. **`drug_bindings` (12) + the last 2 `projections`**, opportunistic: a PDSP refresh for
   the bindings, claustrum-specific primary lit for claustrum to frontal / insula; some may
   honestly stay `tentative`/`llm`.

**Books/sources we likely still need (beyond the five wired):**
- a **brain expression atlas** (Allen Brain Atlas / Human Protein Atlas), unlocks the 507
  location nodes, by far the largest lever;
- **IUPHAR/BPS Guide to Pharmacology** (free, online, citable), receptor + target
  classifications (30 nodes) and per-target tissue-distribution citations;
- **NCBI/PubMed primary literature** as the genuine last resort for the handful of claims
  (claustrum-to-frontal/insula connectivity, a few tentative subtype affinities) no
  reference book states.
