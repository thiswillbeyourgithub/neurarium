# Sourcing gaps: what is not yet `verified`, why, and how to tackle it

The dataset grades every **node** (any sourceable datum, see `CLAUDE.md` "Nodes")
`llm` < `sourced` < `verified`. `verified` is the top grade: a quote was
programmatically confirmed present in a cited source page (or a Ki row in the PDSP
CSV). This document lists everything **not** at `verified`, says **why**, and gives an
**idea to tackle it**. Numbers come straight from `meta.provenance_stats` (regenerate
with `python tools/generate_data.py`, print the table with `python tools/check_data.py`),
so re-derive them after any data change rather than trusting the counts below forever.

Made with the help of Claude Code.

## Snapshot (2026-07-03, after the drug-class win)

Headline: **1077 / 1665 knowledge nodes backed (65%)**. In the tally a bare `llm`
grade counts as **missing** ("an LLM asserted it from memory" = no document), so
"missing" below means `llm` or no source at all. 588 knowledge nodes are missing.

> **Update: `drug_categories` is done.** 156 of 158 drug class classifications are now
> `verified` against Stahl's "Class" section (Haiku extracted each verbatim class
> descriptor, Sonnet judged it supports our category IDs, `apply_category_sources.py`
> re-found and wrote the quotes, `check_data.py` re-verified). Headline 55% to 65%
> (+156 verified nodes). Two stay unsourced: `naltrexonebupropion` (Stahl classes it a
> "weight management medication", not our `substance_use`, so a flagged mismatch) and
> `serdexmethylphenidate` (no standalone class-descriptor bullet in Stahl, only its NbN
> line). The table below is the post-win state.

| Node kind | Missing | Total | Share of the gap | Difficulty | Best lever |
| --- | ---: | ---: | ---: | --- | --- |
| `receptor_locations` | 383 | 383 | 65.1% | Hard | expression atlas |
| `target_locations` | 124 | 124 | 21.1% | Hard | expression atlas |
| `receptors` (mechanism) | 26 | 56 | 4.4% | Medium | IUPHAR Guide to Pharmacology |
| `projections` | 17 | 103 | 2.9% | Hard | connectivity atlas |
| `drug_bindings` | 12 | 632 | 2.0% | Medium | PDSP refresh + primary lit |
| `projection_groups` | 10 | 10 | 1.7% | Medium | one defining quote per system |
| `circuits` | 6 | 6 | 1.0% | **Easy-ish** | Kandel prose (loop exists) |
| `targets` (classification) | 4 | 25 | 0.7% | **Easy** | IUPHAR / textbook |
| `structures` (anatomy) | 4 | 52 | 0.7% | Hard | non-Kandel neuroanatomy atlas |
| `drug_categories` | 2 | 158 | 0.3% | **DONE** (156/158) | Stahl "Class" line |
| `references` (Wikipedia links) | 2 | 298 | (not in headline) | **Trivial** | add two URLs |

**The shape of the problem:** with the drug-class win banked, two kinds are now **86%**
of the remaining gap, both per-region "expression" claims (`receptor_locations` +
`target_locations` = 507 nodes) that need a brain expression atlas we do not yet have
wired. Everything else combined is 14% of the gap and is mostly "the four books we hold
do not state it in prose."

Four corpora are wired into `SOURCE_CORPORA` today (`stahl`, `kandel`, `stahl_essential`,
`carlat`) plus the `pdsp_ki` CSV. The book-prose wins those four allow are largely
exhausted (see the sourcing memory); the remaining gaps mostly need a **new kind of
source**: an expression atlas, a receptor-classification database, or a connectivity
atlas.

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

### 4. `projections`, 17 / 103 missing (11 claim-families)

**What.** 17 pathway arrows (11 distinct L/R families) with no source: the fornix chain
(hippocampus to fornix to mammillary), hippocampo-septal, septo-hypothalamic,
olfactory-bulb to amygdala, the temporal anterior commissure, insula to cingulate
("salience"), and the four claustrum pathways (claustro-frontal, claustro-insular).

**Why not verified.** Kandel genuinely does not state these **directionally in prose**:
the claustrum never appears in Kandel; the fornix is only a figure label; the salience
link is stated only symmetrically; olfactory to amygdala is split across two sentences.
They were not forced (correctly).

**How to tackle.** Needs a **connectivity source** beyond Kandel:
- **Nieuwenhuys, "The Human Central Nervous System"** (systematic tract-by-tract prose),
  covers the fornix, commissures, claustrum connectivity.
- A **white-matter tractography atlas** (e.g. the Catani/Thiebaut de Schotten atlas) for
  the association/commissural pathways.
- Claustrum connectivity is genuinely thin in the literature; those four may stay
  `tentative`/`llm` honestly, or lean on a claustrum review (Crick & Koch 2005 and
  successors) via primary lit / NCBI.

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

### 6. `projection_groups`, 10 / 10 missing

**What.** The 10 legend "system" nodes (7 per-transmitter groups + 3 per-sign groups):
"the serotonergic ascending system", "excitatory projections", etc. All unsourced.

**How to tackle.** Each is a real, well-defined neuropharmacology concept. Add one
defining quote per group from **Stahl Essential** (the transmitter systems) or **Kandel**
(the sign groupings) via the existing `_expand_sources` quote-source mechanism; the
`PROJECTION_GROUPS` entries already accept a `sources` list. 10 nodes, one quote each.

### 7. `circuits`, 6 / 6 missing (**easy-ish**)

**What.** The 6 functional circuits (Papez, basal-ganglia direct/indirect loop, reward,
...). All unsourced.

**How to tackle.** **Kandel describes several of these in prose** (the Papez circuit and
the basal-ganglia loops especially). Run the **existing `KANDEL_QUOTES`-style loop**
(search Kandel pages, judge, programmatic quote-check, store) that already sourced 86
projections; `CIRCUITS` entries already accept a `sources` list. 6 nodes; the tooling is
built. A natural companion pass to #6.

### 8. `targets` (classification), 4 / 25 missing (**easy**)

**What.** Four non-receptor target classification nodes: carbonic anhydrase, PDE5, T-type
Ca channel (`cav_t`), melanocortin receptor group.

**Why not verified.** Absent from Stahl Essential.

**How to tackle.** All four are textbook-standard targets, one **IUPHAR/BPS** page or a
pharmacology-textbook sentence each (same corpus as #3, so do them together). 4 nodes.

### 9. `structures` (anatomy), 4 / 52 missing

**What.** Claustrum (L/R) and fornix (L/R) region-anatomy nodes.

**Why not verified.** The claustrum has **0 hits** in Kandel; the fornix appears only as
a figure label. 48 of 52 structures are verified against Kandel; these 4 are the residue.

**How to tackle.** A **non-Kandel neuroanatomy atlas** that describes them in prose:
**Nieuwenhuys**, Gray's Anatomy, or Netter's atlas text. Pairs naturally with #4 (same
claustrum/fornix sources). 4 nodes.

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

### 11. `references`, 2 Wikipedia links missing (**trivial, not in headline**)

**What.** `carbonic_anhydrase` and `pde5` (both non-receptor targets) carry no `wikipedia`
link. References are tallied separately and excluded from the headline %, but the panel
shows them `NOSOURCE`.

**How to tackle.** Add the two Wikipedia URLs to their `DRUG_TARGETS` entries in
`generate_data.py`. Two-line fix.

---

## Recommended attack order

Ordered by **value per unit effort**, not by raw node count:

1. ~~`drug_categories`~~ **DONE** (156/158 verified via `apply_category_sources.py`;
   headline 55% to 65%).
2. **`references` (2) + `targets` (4) + `structures` (4) claustrum/fornix (4)**, small
   hand-fixable batches; the 2 refs are two URLs, the targets/structures are a handful of
   IUPHAR/Nieuwenhuys quotes.
3. **`circuits` (6) + `projection_groups` (10)**, one Kandel/Stahl quote each via the loop
   and quote-source mechanisms that already exist. ~16 nodes, tooling built.
4. **`receptors` mechanism (26) + `targets` (4)**, wire **IUPHAR/BPS Guide to
   Pharmacology** as corpus #6; it closes both in one integration.
5. **`target_locations` (124), then `receptor_locations` (383)**, the big prize (86% of
   the remaining gap) and the hardest. Build the expression-atlas fetch+join tool (model
   on `fetch_ki.py`), prove it on the coarser target expression, then extend to receptors.
   This is the one that needs real new infrastructure and the atlas-region to `base` map.
6. **`projections` (17) + `drug_bindings` (12)**, opportunistic: a PDSP refresh for the
   bindings, a connectivity atlas or primary lit for the pathways; some may honestly stay
   `tentative`.

**Books/sources we likely still need (beyond the four wired):**
- a **brain expression atlas** (Allen Brain Atlas / Human Protein Atlas), unlocks the 507
  location nodes, by far the largest lever;
- **IUPHAR/BPS Guide to Pharmacology** (free, online, citable), receptor + target
  classifications (30 nodes) and per-target tissue-distribution citations;
- a **systematic connectivity/neuroanatomy atlas** (Nieuwenhuys), the claustrum/fornix
  structures + the association/commissural pathways;
- **NCBI/PubMed primary literature** as the genuine last resort for the handful of claims
  (claustrum connectivity, a few tentative subtype affinities) no reference book states.
