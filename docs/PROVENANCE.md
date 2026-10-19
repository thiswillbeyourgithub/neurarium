# Source provenance

How every node is graded and sourced, in full. Split out of `CLAUDE.md` (which keeps a terse summary) to keep that file small; this project is built with the help of Claude Code. Section names referenced below (Nodes, Drugs, Drug metabolism, ...) are sections of `CLAUDE.md`, whose full drug detail lives in [`DRUGS.md`](DRUGS.md).

How every **node** (any sourceable datum, see Nodes) is graded + sourced. Every node's source/reference
carries a **provenance grade** (the dataset is LLM-assisted, not yet human-checked), rendered as a
coloured **pill**; the grade is **data**. Grades (`PROVENANCE_LEVELS`, weakest to strongest):

- **`llm`** (grey **?**): LLM from memory, unchecked, may be a hallucination.
- **`sourced`** (yellow **~**): LLM given the source document, not quote-verified.
- **`verified`** (green **✓**): an LLM extracted a quote, it was *programmatically* confirmed present in
  the source, and a separate LLM agreed it supports the claim. Highest grade; still LLM-driven.
- absence -> a red **✕** pill (`NOSOURCE_GLYPH`, `.src-todo`). Not a stored grade.
- a neutral dashed **◌** pill (`.src-prov-dataset`) is not a grade at all: it marks an addon whose
  `basis` is `dataset` (`meta.addon_bases`), a statement about this dataset itself (e.g. "the enzyme list
  is not exhaustive"), which no corpus could ever source. Such a node is **excluded from the tally** (and
  from the Data browser, whose counts must match it): it is not knowledge, so counting it as missing would
  understate coverage and counting it as backed would overstate it. The flag is authored data, never a
  special case by id, and `check_data.py` rejects one that carries sources.
- **UNKNOWN** (blue **∅**, `.src-prov-unknown`, token `--sem-unknown`): not a grade, a **search result**. A red ✕ means "no source found yet" (a to-do); ∅ means every corpus the node's kind requires was searched on a recorded date and none states the claim (a finding about the literature as of that date). It is earned only through a committed **search log**, `tools/generated_cache/unknown_searches.json`, one entry per claim keyed by its citation site (`drug:<id>/bindings[<target>]`, `metabolite:<id>/bindings[<target>]`, or owner-level `receptor:<id>/effects` / `target:<id>/effects`), listing every corpus searched with its lookup key or query, the hit count, the abstracts read, the date and the harness + model that ran it. `tools/data_generators/unknown.py` (`apply_unknown`, run by `generate_data.py`) emits a compact `unknown: {searched, corpora}` stamp on the claim, which the pill's tooltip prints ("Searched on 2026-10-12, no source states it:" + the corpora). Three rules: a **real source wins** (only a still-unsourced claim is stamped; a log entry whose claim gained a source is ignored), the search must cover every corpus `UNKNOWN_REQUIRED_SOURCES` lists for the kind (`check_data.py` family 4; a kind with no entry cannot be UNKNOWN; today `drug_binding_action`: `pdsp_ki`, `gtopdb_ki`, `wikipedia_pharm`, `wikipedia_fr`, `europepmc`; and `receptor_effect`: `wikipedia_pharm`, `gtopdb_function`, `stahl_essential`, `europepmc`, stamped as `effects_unknown` on an owner with no `effects[]` at all, shown as one ∅ row in its Effects section and never in the effect index; its Europe PMC search is `fetch_europepmc.py --effect-search`, its log entries `apply_receptor_effects.py --unknown-log`), and it **expires** after `FRESHNESS_MAX_MONTHS` like a cited page (family 13, so the `pre-push` `--only freshness` run catches it). In the tally it is its own `unknown` bucket **outside** `total`: neither backed nor missing, so it leaves the headline denominator; the Sources popup and the README state the count separately. Built with Claude Code.
- **`uncertain`** (orange **⚠**): not a stored grade either but a **display grade**, taken by a node
  whose `uncertainty` bullets are non-empty (see below). It replaces the green ✓ on the pill and in the
  tally, and buckets as **backed** (the quote really was checked).

Every node's grade rides its own row/heading (`makeProvenancePill(level)`), never a separate bottom
"Sources" block (a source only ever grades one node); a node with no source shows `NOSOURCE`, never a
blank. The pill's tooltip leads with the grade in words (`prov.name.*`, a one-line gloss, so a bare ✕
still says "No source"), then the concrete source (the verbatim quote + citation), then an explicit
call to action ("Click to read how every piece of information in neurarium is sourced",
`makeDetailsCue`) that opens the Sources & provenance popup: that popup is the single
place explaining what each grade means, so the verbose per-grade paragraph is not inlined into every
pill (it stays only as the pill's `aria-label`, `info.prov*`). The popup's tally is
**progressive-disclosure** (`buildAboutSourcing`): one global bar over all knowledge nodes by default,
clickable to reveal the per-node-kind bars, each of which is in turn clickable to reveal its grade counts
+ one clickable **example node** (`buildKindExample`: a representative datum rendered as a knowledge
triplet, its notion in quotation marks, that navigates to the real drug/receptor/structure/circuit/group).
The grade key lists only `NOSOURCE` / UNKNOWN / `llm` / `uncertain` / `verified` (the `~sourced` and
live-Wikipedia rows were dropped: no knowledge node is ever graded `sourced`). How the tally buckets
these grades (and why `llm` counts as unbacked): see The "% sourced" figure.

**The sourcing model.** A verified quote node may carry an optional `llm` (`haiku`/`sonnet`/`opus`,
`SOURCING_LLMS`) naming the model that extracted+judged it, so a reader can weigh a quote by that
model's capability; it is quote-node metadata (not part of the id hash), absent = unknown. Any new
sourcing/recheck pass must stamp it (a non-LLM deterministic source like Allen's PACall omits it).
A batch recheck (`tools/sourcing/recheck_quotes.py`, run as a Sonnet workflow) writes a central
`generated_cache/quote_llm.json` (`{quote_id: {citation_site: llm}}`) that the generator applies per
citation (an override wins over a source-level `llm`): a verdict covers only the sites the judge was
shown, so a quote newly cited somewhere else ships **unjudged** there until rechecked
(`recheck_quotes.py build --unjudged`). A verdict can pass some sites and reject others
(`rejected_sites`): the rest are stamped and only the rejected sites land in
`quote_recheck_flagged.json` (row `sites`), which `demote_quotes.py --flagged` demotes.

**A verdict is about a claim, not a sentence (the citation site).** A quote id is a content hash, so
one sentence reaching two claims is one id, and the excerpt table stays deduplicated for it. What that
costs is the ability to say the useful thing, *this backs the binding and not the class*, so a
**citation site** (`tools/sourcing/citation_site.py`) names one place a quote is cited from
(`drug:clozapine/bindings[5ht2a:antagonist]`, `receptor:5ht1a/locations[amygdala]`).
`recheck_quotes.py` prefixes each reconstructed claim with it and `demote_quotes.py --sites` demotes
only the citations named, so the quote's other claims keep their source and the quote keeps its stamp.
It rides the citation for the same reason the grade and the `pipeline` do. A site names a **node**, not
a slot, so where one owner carries two nodes the key carries the distinction (a binding by target AND
action: amisulpride antagonises D2 and partially agonises it; an enzyme row by isoform AND role).

**The converse: a claim several quotes back TOGETHER is not asking each of them for the whole claim.**
A compound value earns its green check only when every part is attested (5-HT1B's `synaptic="both"` is
one presynaptic quote plus one postsynaptic one, a two-category class is one sentence per category), so
a judge shown one quote beside the whole claim rejects the citation that carries its share. Every claim
line therefore states how many citations share it, and asks the judge to weigh this one on its share. A claim the dataset
**already** doubts arrives with its `uncertainty` bullets spelled out in that same line, in the reader's
own words (scraped from `js/i18n.js`, so there is one copy): a judge not shown the flag re-derives the
doubt for itself and hands it back as a rejection, which would demote a citation over something the
dataset was already honest about.

**The rule: no LLM-picked quote ships unjudged by Sonnet or better.** A sentence a model *chose* out of
prose is the one that can be chosen wrongly (right page, wrong claim), so it is not backed until a
second model, which never saw the first one's reasoning, has agreed it supports the claim, and that
second model is `sonnet` or `opus`, never `haiku`. `check_data.py` family 5 fails on any citation whose
pipeline has an `extract_llm` step and no `judge_llm` step, so a new extraction pass cannot ship its
quotes and leave the judging for later. A quote **code** copied out of a table has no such failure mode
and needs no judge. A stamp names the **strongest** model that has confirmed a quote, so a second,
weaker read can only corroborate it; a weaker model *doubting* one is a disagreement, parked in
`quote_recheck_disputed.json` until the stamping model is re-asked (see `recheck_quotes.py`).

**How a quote got here (the chain of custody).** The grade says how well a claim is backed; the
**pipeline** says by what mechanism, which is a different question with a different failure mode. Every
citation carries a `pipeline` key resolved by `quote_pipeline()` from three facts it never has to
restate: whether the corpus is a **`machine`** store (PDSP #5, GtoPdb #7/#11/#12, Allen #8: no prose to
read, so every quote from it is a copied record line), whether the writing pass stamped
`extraction: "code"` on the source (the only authored bit, because who found the sentence is the only
unrecoverable one: Stahl's *Brands* and *Neuroscience-based Nomenclature* greps do), and whether the
quote carries an `llm` stamp (a judge ran). `QUOTE_PIPELINES` maps each key to its ordered steps,
emitted whole as `meta.quote_pipelines` and rendered at the bottom of every source tooltip as
`raw data -> deterministic extraction -> ... -> neurarium`; the step names are `quotechain.<step>` i18n
keys, so a new pipeline is one entry plus its translations and never a viewer edit. It rides the
**citation**, not the quote node, for the same reason the grade does: one sentence can honestly reach
two claims by two routes (Stahl's Class line is model-picked for the drug's class and code-grepped as
the NbN fallback).

**Where the grade lives.** One source shape, quote-level `{corpus, page, quote, provenance}` against a
`SOURCE_CORPORA` corpus (`page` is a book page unless the corpus sets `page_kind`, e.g. `pmid` / `setid` / `gene`, labelled by `info.sourcePage.<kind>` in `js/i18n.js`; the tooltip links the exact page via the corpus's `page_urls[page]` (read from each fetched page's header by `tools/data_generators/page_links.py`: a Wikipedia revision permalink, a paper's DOI, a Drugs@FDA application page; committed as `tools/generated_cache/page_links.json` by `stamp_fetch_dates.py`), else its `page_url` template with `{page}`, else the corpus `url` landing page, a book's DOI or its ISBN on WorldCat); `provenance` defaults `DEFAULT_PROVENANCE` (`"llm"`), a sourceless node is
`NOSOURCE`. Each `wikipedia` reference emits a sibling `wikipedia_provenance` (`WIKIPEDIA_PROVENANCE`
registry); a **present** link defaults `"sourced"` (`WIKIPEDIA_DEFAULT_PROVENANCE`), not `llm` (a real
reference the viewer live-fetches). `_provenance` validates every grade; upgrading a source is a data edit.

**Where a quote sits (the book heading).** A quote node from a **book** corpus may carry a derived
`heading`: a **trail** of headings, outermost first (`["Clozapine", "Side effects", "How Drug Causes
Side Effects"]`, capped to its 3 deepest levels), rendered as a breadcrumb above the passage in the
source tooltip and handed to the LLM judge in `recheck_quotes.py`'s batches. A flat list, not named
levels, because the books do not share a shape (a Stahl monograph, a Kandel part/chapter/section, a
Nieuwenhuys chapter), so the viewer only joins it. It is **context, not a claim** (not a node, not
graded, not tallied), and it is what makes a quote judgeable rather than merely checkable: the same
sentence under *How the Drug Works* is Stahl attributing a mechanism to that drug, under *How Drug
Causes Side Effects* it is a subject-less rule (the distinction the `uncertain` badge rests on).
Derived by `tools/fetch/fetch_quote_headers.py` into the committed
`generated_cache/quote_headers.json` and applied by id in `quote_table` (like `quote_llm.json`).
Two resolvers: the four outline-bearing books (Kandel, Stahl Essential, Carlat, Nieuwenhuys) take
the ancestor chain of their `INDEX.md` entry covering the page; **Stahl** has no usable outline, so
its trail is read off the page text (monograph title from `INDEX.md`, then positional subsection,
then **section = a subsection -> section majority vote over all 158 monographs**, since the
extraction drops ~30 section headings and the nearest surviving one then leaks in from the previous
section or drug). A corpus is a "book" exactly when its page tree has an `INDEX.md`, which is what
excludes the flat stores (GtoPdb, Allen, Wikipedia) where a chapter has no meaning. An unresolved
level is **omitted**, never guessed. `check_data.py` family 5 checks the shape, then re-derives the
checkable half offline (a Stahl trail must open with the monograph containing the cited page),
which catches a stale or hand-edited cache.

**Freshness (when an online page was downloaded).** A book page does not change under a citation, but a Wikipedia article or a live database does: a quote checked against last year's download may be gone from today's page, and the value beside it may have been corrected. So each corpus record in `SOURCE_CORPORA` says whether it is `editable`. Editable: `wikipedia_pharm` (#9), `wikipedia_fr` (#10), `pdsp_ki` (#5), `gtopdb` / `gtopdb_ki` / `gtopdb_class` / `gtopdb_function` (#7/#11/#12/#23), `allen_ahba` (#8), `pharmfreq` (#13), `dailymed` (#14), `cpic` (#15), `bdpm` (#16), `drugsfda` (#18), `clinpgx` (#20), `pubchem` (#21), `b3db` (#22). Not editable: the books (#1-#4, #6), `europepmc` (#17, a published abstract is fixed once printed) and `agnp_tdm` (#19, a published guideline). Every cited page of an editable corpus carries the date it was downloaded (`fetched`), read by one helper, `tools/data_generators/freshness.py`: a page fetched one by one (a Wikipedia article, a GtoPdb target, a DailyMed label, a BDPM product) carries the `fetched:` / `fetched_at:` line its fetcher stamps in the page header; a corpus downloaded in bulk (the PDSP CSV, GtoPdb's `interactions.csv`, the Allen donor zips, the CPIC, PharmFreq and ClinPGx exports) dates every page by that one download (`BULK_DATES`). Those pages are author-side, so `python tools/fetch/stamp_fetch_dates.py` freezes the dates into the committed ledger `tools/generated_cache/fetch_dates.json`, and `generate_data.py` stamps `fetched` on each quote node (or inline on a quote-less source such as a PDSP Ki row), so a clone emits and checks the same dates. The viewer appends the date to the source pill's tooltip ("Wikipedia (English), ..., p. vortioxetine, downloaded 2026-07-13"; FR "téléchargé le ..."). `check_data.py` family 13 fails when a cited page has no date or is older than `FRESHNESS_MAX_MONTHS` (12), and `pre-push` runs that family unskippably: refetch the corpus (`tools/README.md`, "Refreshing external data"), then restamp and regenerate.

**Doubting a `verified` claim (the `uncertain` badge).** `verified` says the sentence is on the page; it
never said the sentence is *about this node*. A node whose quote does not attribute the claim carries an
`uncertainty[]` array (drug bindings + projections, `tools/data_generators/quotes/uncertainty.py`), which
takes over its pill: orange ⚠, tooltip = "Here are LLM-written reasons to be uncertain about this claim:"
then one bullet per reason, then the node's own source as usual. **Every bullet is itself a badged,
sourced claim**: a `kind` from the closed `UNCERTAINTY_REASONS` vocabulary (emitted as
`meta.uncertainty_reasons`) + slot `args`, and either a real quote-gated source (the kind declares whether
it reuses the owner's own quote or its Ki) or `absence: true`, which renders the red ✕ and reads "the
corpus does not say this". No prose is stored: the sentence comes from an `uncertain.<kind>` i18n key, so
a new kind means a new string in **both** catalogues. Forgetting a source raises at generation
(`_uncertainty_bullet`) and errors in `check_data.py` family 5, which also gates each bullet quote
verbatim and stands its subject-less-quote guard down for a binding that declares uncertainty (the two
answer the same problem). **The three flags about a quote's REACH are derived, never authored per
site**: `apply_binding_uncertainty` / `apply_projection_uncertainty` compute both the flags and the
bullets from the emitted data, so a data edit cannot leave a stale flag behind and a new drug or arrow
is covered the day it lands. Six flags today, and a node hit by any is uncertain:
- **the subject-less side-effect rule** (89 bindings): the quote's heading trail ends in Stahl's *How Drug
  Causes Side Effects* and the sentence does not attribute the action to the drug (`_attributes_to_drug`:
  it neither names it, nor uses a pronoun subject, nor elides the subject in Stahl's telegraphic style).
  This is what the heading trails were resolved for. Repetition across monographs is deliberately not a
  signal: Stahl prints "Blocks dopamine 2 receptors, reducing positive symptoms of psychosis" on every
  antipsychotic, and every one does block D2; a bad quote is marked by its section plus a drug lacking
  the property.
- **the family-level claim** (`family_claim`, +22): one source sentence covers several of the drug's
  bindings on subtypes of one family (same id stem) and names none of them individually, so the split into
  subtypes is ours, not the book's ("Blockade of alpha adrenergic 1 receptors" -> alpha1A/B/D). Bearable
  when a measured Ki pins the subtype down, so it only flags a subtype **with no Ki**.
- **the blanket pathway claim** (`blanket_claim`, 33 projections): the projection twin of the above. An
  anatomy book states a diffuse system by its sweep ("project to virtually every part of the neuraxis"),
  so one sentence sources several arrows out of one nucleus while naming none of their targets: which
  regions the sweep is drawn to is our reading. Same `>= 2 siblings, none named` construction, over
  regions; a target the sentence *does* name (raphe -> thalamus) keeps its green check.
- **the set-level sub-claim** (`set_claim`, 12 projection transmitter/sign sub-claims): the many-ORIGINS twin of `blanket_claim`, riding on the sub-claim (`claims.transmitter` / `claims.sign`) rather than the pathway. A sentence naming neither endpoint ("the cerebral cortex" -> "the striatum") that backs the same claim on pathways from two or more structures states it for a set; drawing it onto one lobe -> caudate arrow is our split (`apply_set_claim_uncertainty`). The fetcher only offers such a sentence for the documented `SET_LEVEL_PAIRS` (cortex -> striatum).
- **the contradicted claim** (`contradicted`, 3 `drug_enzymes` rows, 3 `drug_enzyme_strength` tiers, 5 receptor classification attributes, 2 drug bindings, 2 `drug_metabolites` links): the odd one out, and the only
  flag about a quote's *truth* rather than its reach. Two quote-gated corpora say opposite things
  (Stahl's bare "Inhibits CYP3A4" vs the article's "in vivo ... do not significantly affect ...
  CYP3A4", the recurring in-vitro-vs-in-vivo split), so both ship and the row carries the denial in
  its tooltip: picking a winner would assert a judgement neither corpus makes. Its bullet is the only
  one citing an OUTSIDE source (`source: "given"`), and it is **hand-curated** in
  `tools/data_generators/quotes/contradictions.py`, because the same scan derived returns 50% false
  positives (a caveat scoped to two named substrates, an exception clause reading as a negation), and
  a flag that encodes its own errors as doubt is worse than the silence it replaces.
  **One table, `CONTRADICTIONS`, keyed by the doubted node's citation site** (the `tools/sourcing/citation_site.py` grammar a judge verdict names, resolved through `citation_site.node_index`), each site mapping to one denying source or a list of them (one bullet citing all). One pass, `apply_contradictions`, walks every node kind, so contradicting a binding, a metabolite binding, a receptor effect, a workup row or any other node-shaped site is a data-only edit. A flat `*_sources` facet (`half_life`, `tmax`, `nbn`) has no node dict to carry a bullet, so naming one fails like a stale site. The generator raises and `check_data.py` family 5 errors when a site names no emitted node (or two), and family 5 also errors when the named node does not wear the badge (stale `data/`), so a fetcher re-run cannot drop the doubted claim and leave the contradiction marking nothing.
  The site sets the precision. A sub-claim (`receptor:<id>/classification[<attr>]`, `drug:<id>/enzymes[<enzyme>:<role>]/strength`) carries the bullet on itself, so only that pill turns orange. A binding is keyed by target AND action, so one of two bindings on a target can be doubted alone: amisulpride's tentative D2 partial agonism (Stahl p31 "May be a partial agonist at dopamine 2 receptors") is contradicted by Tadori 2012's functional D2 assay (antagonist), GtoPdb's curated D2 rows (Antagonist) and its article ("functions primarily as a dopamine D 2 and D 3 receptor antagonist"), while its D2 blockade stays unflagged. Etomidate's GABA-A site (Wikipedia's beta+/alpha- transmembrane site vs Stahl Essential p338's "same sites as neuroactive steroids") gets the bullet appended after its derived ones. An active-metabolite link a corpus denies is active (`drug:<id>/metabolites[<metabolite>]`, the per-parent entry: Stahl p604's two active samidorphan metabolites vs the Lybalvi label's "Neither metabolite contributes to the pharmacological effects of samidorphan") carries it on the link, never on the shared metabolite record. A denied claim with no document of its own (a bare `llm` sign or site) keeps its grey pill and stays **missing** in the tally: the bullet shows in its tooltip, but a denial is not a backing (`bucket` in `provenance.py`, `shownGrade` in `js/node-browser.js`).
- **the animal-only claim** (`animal_evidence`, `tools/data_generators/quotes/animal_evidence.py`): every source of the node that records a species names a non-primate animal and none a human or monkey (a rat Ki, a rat GtoPdb tissue line, a mouse Europe PMC paper). The grade stays; the bullet lists the species. One vocabulary (`tools/lib/species.py`) folds GtoPdb `species`, PDSP Ki `species` (cell lines included) and Europe PMC MeSH species (`generated_cache/europepmc_species.json`, written by `fetch_europepmc.py --species`); a source recording no species (a book, Wikipedia) leaves the claim unflagged. Covers drug + metabolite bindings, projection routes + transmitter/sign sub-claims, and "Found in" regions, whose bullets ride `location_uncertainty` (keyed like `location_sources`).
- **the isolated-tissue effect** (`isolated_tissue`, `data_generators/receptor_effects.py`): a `receptor_effect` node whose every source reports only an isolated human tissue preparation (a vessel ring, a mucosa strip). The picker records each pick's reading (`evidence`: `in_vivo` | `isolated_tissue`, closed `EFFECT_EVIDENCE`) in `receptor_effects_judged.json`, the applier refuses a pick without one, and the reading rides the cached source; the node's grade stays.
The first three run as a post-pass (not `_binding_record` / `_projection_records`) because the bullets look across
siblings: `class_wide` counts the drugs the same sentence is printed on, `family_claim` the subtypes one
sentence covers, `blanket_claim` the arrows.

**Per-claim sources + the verify gate.** The nodes carrying such a source: a
binding's `sources[]`, a drug's `nbn_sources[]`, a projection/circuit/group quote (`KANDEL_QUOTES`), a
receptor/target location/classification, region anatomy. `corpus` keys the source-agnostic
`SOURCE_CORPORA` registry (`{ref, citation, url, pages_dir|tsv_dir}`, emitted as `meta.source_corpora`; the
full citation is resolved from there, not denormalized onto the ~429 bindings). `_quote_sources` /
`_binding_sources` validate corpus + grade (a `verified` source needs page + quote). `verified` is
earned by a two-step (LLM extract + LLM judge supports), then `check_data.py`'s source-quote check
confirms the quote is really on the page (the backstop against a hallucination). **Page files are
author-side (see `CLAUDE.local.md`), so the quote gate is skipped + warned on a clone that lacks them**
(true for every corpus below except #13, whose tables are committed). A binding with no quote source falls back to its **Ki** (verified), else
`NOSOURCE`. The **NbN** is simpler: `apply_nbn_sources.py` greps Stahl's verbatim
"Neuroscience-based Nomenclature: <value>" line and confirms the dataset `nbn` is a substring (stronger
than a judge for this fixed field); a newer drug with no NbN line falls back to Stahl's **Class** line
under the same gate, marked `nbn_nonstandard`. **Brands** are gated the same way:
`apply_brand_sources.py` reads each drug's Stahl "Brands?" dump list and confirms each brand appears
verbatim on the drug's page range (region `na`, `verified`); a brand not found verbatim is dropped, not
guessed. The eu/fr brands come from Wikipedia (corpus #10 `wikipedia_fr`), region-tagged only for ordering.

The corpora (`SOURCE_CORPORA`), each quote-gated author-side as above unless noted:
- **#1 Stahl (`stahl`) / #2 Kandel (`kandel`) / #3 Stahl Essential (`stahl_essential`) / #4 Carlat (`carlat`) / #6 Nieuwenhuys (`nieuwenhuys`)** are `pages_dir` book
  corpora (`page` = a page number): drug bindings/NbN/class (Stahl), pathways + region anatomy (Kandel,
  Nieuwenhuys), receptor/target mechanism (Stahl Essential); see `CLAUDE.local.md` for the trees.
- **#5 PDSP Ki** (`pdsp_ki`) has a `csv` path, not `pages_dir` (measured Ki values, not paged text). A
  binding's `ki.source` cites a **Ki id** (a CSV row) instead of a page; `check_data.py` confirms the
  row exists with that value. A verified Ki backs `_binding_grade`. Refresh `fetch_ki.py --apply`.
- **#7 GtoPdb** (`gtopdb`, `page` = a GtoPdb targetId) is the source for **receptor** "Found in"
  regions. A confirm-only LLM judge maps a cached quote (by index) to each existing region (never
  adds/drops one); `apply_location_sources.py` writes the `verified` source into
  `tools/generated_cache/location_sources.json`. Each quote carries the assay **`species`** (Human/Rat/Mouse/Monkey,
  validated in `_quote_sources`); a non-human-only region shows an amber "· <species>" tag.
- **#8 Allen AHBA** (`allen_ahba`, `page` = an HGNC gene) is the complement covering **non-receptor
  targets** + the receptors/regions GtoPdb misses. `fetch_allen.py` turns the microarray **PACall**
  boolean across human donors into a deterministic present/absent (**no judge**);
  `apply_location_sources.py --corpus allen` writes the `verified`, `species: Human` source. The panel's
  species tag prefers Human (`locationEntry`), so an Allen confirmation clears the amber tag. **Caveat:**
  microarray = mRNA in cell bodies, so a transporter confirms at its source nucleus (SERT->raphe,
  NET->LC) and its terminal-region claims honestly stay `llm`.
- **#9 Wikipedia pharm** (`wikipedia_pharm`, `page` = the article slug) backs a binding **Ki** where PDSP
  (#5) has none (a *fallback*, never overriding a measured assay). `fetch_wikipedia_pharmacology.py` stores
  the whole English article author-side (pinned to a revision id) and mines its pharmacodynamics binding
  table; a Ki source's `quote` is the verbatim table row, gated exactly like a book page. A tertiary
  source citing the primary literature: the grade attests quote-presence, the corpus label conveys tier.
  It also backs **`drug_categories`** for drugs Stahl has no monograph for: the infobox "Drug class" row or
  a lead sentence, offered by `fetch_category_worklist.py`, picked by index, gated by
  `apply_category_sources.py --wikipedia`, then judged by `recheck_quotes.py` (#10 FR leads are the fallback).
  And, from the receptor's / target's **own** article (alongside Stahl Essential #3 prose), the classification
  residue GtoPdb #12 cannot reach: `receptor_synaptic` (a `both` needs one quote per site), an ion channel's
  `receptor_sign`, sigma-1's `receptor_class`, and `targets` type. Offered by `fetch_classification_worklist.py`,
  picked by index, gated by `apply_classification_sources.py --prose`, then judged by `recheck_quotes.py`.
- **#10 Wikipedia FR** (`wikipedia_fr`, `page` = the FR article slug) is the source for a drug's
  **European / French** commercial brands (`eu`/`fr` region; na comes from Stahl). The FR infobox holds
  only chemistry, so the trade names live in prose; `fetch_brand_names.py` resolves each drug's FR article
  (via the EN article's langlinks), stores it author-side under `data_sources/wikipedia/pages_fr/`, and
  emits a candidate-sentence worklist; an LLM extracts each drug's ordered trade names, and
  `apply_brand_names.py` quote-gates every name verbatim on the FR page (the hallucination backstop),
  writing the first as `fr` and the rest as `eu`. A brand source's `quote` is the brand name.
- **#11 GtoPdb ligand interactions** (`gtopdb_ki`, `page` = the GtoPdb ligand slug) is GtoPdb's
  *other* half (#7 is its tissue API) and complements PDSP (#5) where a radioligand panel
  structurally cannot reach: **targets PDSP does not assay** (the GABA-A benzodiazepine site,
  MAO-A/B, acetylcholinesterase, orexin, melatonin, SV2A, Nav) and the **direction** of an
  `affinity_only` binding. One versioned bulk CSV (`DATA/interactions.csv`), so
  `fetch_gtopdb_ki.py` is deterministic (no judge): it joins on **gene symbol** (case-folded, a
  rodent row reads `Scn2a`), flattens each matched compound's rows into
  `data_sources/gtopdb/pages_ki/<slug>.md`, and a proposal's `quote` is one verbatim row line, so
  the normal quote gate applies unchanged. `apply_gtopdb_ki.py` merges **confirm-only** (never
  adds a target) and **PDSP-first** (a Ki only where there is none; a stated direction always
  wins), reporting rather than resolving a disagreement. The same pass covers each non-modeled active
  metabolite's own GtoPdb ligand record (keyed by metabolite name, chirality-guarded like a drug's),
  writing only onto bindings the metabolite already lists. Only a pKi/pKd becomes a `ki`: a
  functional potency (pIC50/pEC50) rides along as the direction's citation. Contents CC BY-SA 4.0,
  database ODbL.
- **Citing GtoPdb (#7, #11, #12).** GtoPdb's "How to cite" page (`guidetopharmacology.org/citing.jsp`) asks a general citation of its current Nucleic Acids Research database paper (Harding SD, Armstrong JF, Faccenda E, Southan C, Alexander SPH, Davenport AP, Spedding M, Davies JA. The IUPHAR/BPS Guide to PHARMACOLOGY in 2026. Nucleic Acids Res. 2026;54(D1):D1446-D1456, doi:10.1093/nar/gkaf1067), plus the relevant section of the Concise Guide to PHARMACOLOGY 2025/26 (Br J Pharmacol) for work on target data; its contents are CC BY-SA 4.0. These live once in `tools/data_generators/corpora.py` (`GTOPDB_*_CITATION`) and ride each corpus as `required_citations` (the target corpora #7/#12 add the Concise Guide, the ligand corpus #11 does not), which the viewer prints under every source pill of those corpora and in the Sources popup, and `update_readme_stats.py` lists under the README sources table. Read 2026-10-12 from the page's 2026-07-31 snapshot (the live site was down for maintenance). Added with Claude Code.
- **#12 GtoPdb target classification** (`gtopdb_class`, `page` = the GtoPdb targetId) is GtoPdb's
  third slice, backing the *mechanism* nodes: a target's `type` (gpcr/lgic/vgic/enzyme) is a
  receptor's `receptor_class` and a non-receptor target's `type`, read directly; a GPCR's `sign`
  is **mapped** from its transduction table (`transducers` + `effectors`) under the narrow table
  in `apply_classification_sources.py` (Gi/Go -> inhibitory, Gs / Gq/G11 -> excitatory; anything
  mixed or unmapped writes nothing), since GtoPdb states the transduction and never a sign. No
  judge: `fetch_gtopdb_class.py` flattens both fields into `data_sources/gtopdb/pages_class/
  <targetId>.md` and the applier is **confirm-only** (writes only where GtoPdb agrees with the
  value we already state, reporting a disagreement instead of rewriting the data). The sources
  **add to** a book quote rather than replacing it, so an attribute both cover shows two
  citations. GtoPdb has **no pre/post-synaptic field**, so `synaptic` is out of its reach.
- **#13 PharmFreq** (`pharmfreq`, `page` = the HGNC gene) is the one corpus whose raw tables are
  **committed** (`tools/data/pharmfreq/`), so it declares `tsv_dir` and no `pages_dir` and its quote
  is gated by re-derivation rather than by a page lookup: see Drug metabolism, Population variability.
- **#14 DailyMed** (`dailymed`, `page` = a label **set id**) is the US prescribing label (NLM Structured
  Product Labels), and the only **primary regulatory** source here. It exists for the time-to-peak node
  (`drug_tmax`): a label's section 12.3 states a Tmax for essentially every oral drug marketed in the US,
  where the stored prose corpora state it for a third of the roster. `fetch_dailymed.py` picks ONE label
  per drug (plain-oral forms preferred, since a modified-release product states a real Tmax for a
  different product) and stores that label's pharmacokinetics sections as the author-side page, so the
  normal verbatim-quote gate applies unchanged. A set id resolves to a public page
  (`dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=<page>`). Its limit is jurisdictional: a drug never
  marketed in the US has no SPL at all. Content is a US government work under no copyright restriction.
  A few more labels are stored by set id only so a hand-curated quote can cite them (`fetch_dailymed.QUOTE_LABELS`, e.g. the Lybalvi combination label behind a `CONTRADICTIONS` metabolite-link entry): they never enter `dailymed_labels.json`, the only list `fetch_tmax.py` reads, so a combination's kinetics can never become one drug's Tmax.
- **#16 BDPM** (`bdpm`, `page` = a product **CIS** code) is the French public drug database (ANSM, Licence Ouverte), the jurisdictional complement to #14: a drug marketed in France but never in the US has no SPL, yet its French RCP (Résumé des Caractéristiques du Produit) section 5.2 states its pharmacokinetics. `fetch_bdpm.py` joins each roster drug to its single-active, marketed, non-homeopathic products by exact INN (French spellings, salts and inverted salt names folded; a stereo-qualified id joins only via `FR_ALIASES`, so a racemate never stands in for an enantiomer), picks ONE plain systemic RCP (modified-release, patches and local routes never supply it) and stores its section 5.2 as the author-side page. It backs three node kinds: `drug_tmax` and `drug_half_life` (offered by `fetch_tmax.py` / `fetch_half_life.py` like any other page, then index-picked and judged), and `drug_brands` region `fr`, a **code** read of the product denomination (`extraction: "code"`, no judge), where an INN-named generic, a house-lab name (`GENERIC_LABS`) or a local-route product is never a brand. Added with Claude Code.
- **#17 Europe PMC** (`europepmc`, `page` = a PubMed id) is primary literature, for the few claims only a study measures and no book, label or article on disk states (lithium's brain half-life by 7Li MRS, Plenge et al. 1994: 28 h in brain vs 16 h in serum). Not a crawl: `fetch_europepmc.py` stores the abstract of each paper hand-listed in its `PAPERS` registry (which names the claim it was added for) as `data_sources/europepmc/pages/<pmid>.md`, one sentence per line under a provenance header; a PMID resolves to `europepmc.org/article/MED/<page>`. The abstract is served for every indexed paper; where the record says open access (`isOpenAccess: Y` with a PMC id) the page also carries Europe PMC's own OA full text (`fullTextXML`, never a publisher site) after a `## Full text` marker: section headings, paragraphs one per line, figure captions, and every table as its caption then one `cell | cell | ...` row per line (the Wikipedia table convention). The licence comes from the record (e.g. `CC BY-NC`) and is stamped in the page header and on every Ki source quoting the full text (`licence`), so the reuse is credited. Author-side like every `pages/` tree. Quotes are prose or table lines, model-picked and judged like any other, including the human PET / SPECT availability findings of `receptor_demographic` (see docs/DRUGS.md) and a Ki picked out of a paper (`tools/sourcing/apply_ki_prose.py`: Ki / Kd only, confirm-only onto Ki-less bindings, the value must be written in the quote; its source carries `extraction: "llm"`, so it needs a judge unlike a table-copied Ki). Added with Claude Code.
- **#18 Drugs@FDA** (`drugsfda`, `page` = an application number such as `NDA019839`) is the FDA's own register of approved applications, read from openFDA's bulk `drug/drugsfda` export (public domain; www.fda.gov refuses scripted downloads, `download.open.fda.gov` does not). It backs one fact, a drug's first **US** approval, and only as the fallback where Wikipedia (#9/#10) dates no first approval: `fetch_drugsfda.py` takes the earliest original (`ORIG`, status `AP`) approval among the NDAs whose single active ingredient is the drug (never an ANDA, never a combination; salt words dropped, US names via `FDA_NAMES`, stereo-aware through `tools/lib/chirality.py`), and publishes nothing when a matching NDA is undated (Drugs@FDA holds no date for most pre-1982 applications) or when that NDA is not classed a new molecular entity (the export misses some old applications, so a "new dosage form" NDA means the real first one is out of reach). The quote is the product row (`application | brand | ingredient | form | ORIG approved <date>`) copied by code (`extraction: "code"`, no judge) onto `data_sources/drugsfda/pages/<appl>.md`, whose header stamps the download date (freshness). The node carries `national: true`, so the viewer labels it "First national approval". Added with Claude Code.
- **#19 AGNP TDM consensus guideline** (`agnp_tdm`, `page` = the PDF page) is Hart XM, Gründer G, Hiemke C et al., "Consensus Guidelines for Therapeutic Drug Monitoring in Neuropsychopharmacology: Update 2026" (Pharmacopsychiatry 2026;59:166-295, doi 10.1055/a-2860-7861, open access), the AGNP TDM task force's guideline. A published article, so a book-like corpus: the PDF split by `tools/fetch/pdf_to_pages.py` into `data_sources/books/agnp_tdm_2026/pages/` (author-side), not `editable`. `tools/fetch/fetch_agnp_tdm.py` reads two tables by cell rectangle (pymupdf), so every quote is the table row copied by code (`extraction: "code"`, no judge) and gated on its page. **Table 5** (pp. 20-52) gives each drug's therapeutic reference range (kind `drug_therapeutic_range`, carrying the guideline's level of recommendation to use TDM, 1 strongly recommended to 4 potentially useful) and laboratory alert level (kind `drug_alert_level`); only a drug's first row and only a cell holding one unambiguous value is read, so a cell with two ranges (desipramine's depression vs pain), a range qualified by population or dose, or "Not established" publishes nothing. **Table 1** (pp. 7-11) lists the isoforms metabolising each drug and is read confirm-only: its quote joins a `drug_enzymes` substrate row another corpus already states, never adds one (rows left out in `docs/SOURCING_GAPS.md` "Metabolism coverage"; a difference is one side silent, never a denial). The guideline gives no dose ranges and no phenotype frequencies by population. Added with Claude Code.
- **#20 ClinPGx clinical annotations** (`clinpgx`, `page` = the clinical annotation id, resolving to `clinpgx.org/clinicalAnnotation/<page>`) is ClinPGx's (formerly PharmGKB) curated gene-variant / drug-response associations, licensed **CC BY-SA 4.0** (ShareAlike covers the shipped subset; the licence text sits beside the export). `tools/fetch/fetch_clinpgx.py` downloads the bulk `clinicalAnnotations.zip` (author-side under `data_sources/clinpgx/`) and keeps the annotations whose gene encodes a modeled receptor or target (`genes.GENE_OWNERS`: a receptor's own gene first, then any gene a target lists, plus `CHRNB2` -> α4β2) at levels **1A-3**; level 4 (case reports, non-significant or in-vitro evidence) is dropped, and almost every kept row is level 3, which the panel's level chip says. One node per annotation (kind `receptor_variant`), its citations ClinPGx's own per-genotype sentences copied by code (`extraction: "code"`, `machine`, no judge). The kept rows are committed as `tools/data/clinpgx/clinical_annotations.json`, sha256-pinned (`tools/generated_cache/clinpgx_variants.json`) and re-derived field for field by `check_data.py` family 12 (`check_clinpgx_variants`), so the gate runs on every clone. Upstream drug names join the roster through `fetch_cpic.roster()` plus a racemate-only `NAME_ALIASES`; a class ("opioids") stays a name, and only an annotation naming a drug itself reaches that drug's panel. No allele frequencies (neither this export nor PharmFreq ships them for these genes) and no GtoPdb variants (free text behind the API key). Added with Claude Code.
- **#21 PubChem** (`pubchem`, `page` = a PubChem CID, resolving `pubchem.ncbi.nlm.nih.gov/compound/<page>`) is NCBI's open chemistry database (Kim et al., Nucleic Acids Res 2025). It backs two computed descriptors per drug: XLogP3 (`drug_lipophilicity`, the log10 octanol/water partition coefficient) and the topological polar surface area (`drug_polar_surface`, in Å²). `tools/fetch/fetch_physchem.py` reads the drug's CID off the first id of its stored Wikipedia drugbox's `PubChem CID` row (via `lib.corpora.wikipedia.page_for`), pulls PubChem's property table and writes one page per CID under `data_sources/pubchem/pages/<cid>.md` (header with source URL + `fetched:`); the quote is the property line, copied by code (`extraction: "code"`, no judge). Combination products, salts and mixtures (a `.` in the InChI formula) and inorganics (no carbon) are skipped, so lithium, xenon or sodium oxybate get no value. Both numbers are computed estimates, which the panel tooltip says. Added with Claude Code.
- **#22 B3DB** (`b3db`, `page` = the PubChem CID the drug was joined on) is the Blood-Brain Barrier Database (Meng et al., Sci Data 2021), a curated benchmark of about 7800 compounds compiled from 50 published sources, each row carrying a BBB+/BBB- label and, where a study measured it, logBB (log10 of the brain/blood concentration ratio). It backs `drug_bbb`. The same fetcher downloads the classification TSV once (`data_sources/b3db/B3DB_classification.tsv`) and joins it by CID, else by exact case-folded name through the chirality guard (`tools/lib/chirality.py`); every kept row must match the drug's own InChI formula + connectivity (hydrogen and stereo layers dropped, so a tautomer passes), which refuses the dataset's mis-structured rows (bremelanotide, disulfiram, cocaine, naloxone, olanzapine, scopolamine each had one). Rows that disagree on the label publish nothing; several logBB values become a range. One quote per row (`B3DB row <n>: ... | BBB+ | group A | references ...`, code copy, no judge) on `data_sources/b3db/pages/<cid>.md`. Freshness reads the TSV's download date (`BULK_DATES`). Added with Claude Code.
- **#23 GtoPdb target function** (`gtopdb_function`, `page` = the GtoPdb targetId) is GtoPdb's fourth slice, backing `receptor_effect`: the curated prose of three target-page sections, "Physiological Functions" (`/function`: property + tissue + species), "Clinically-Relevant Mutations and Pathophysiology" (`/pathophysiology`: per human disease its role, side effects, use, drugs, comments and mutation descriptions) and "Physiological Consequences of Altering Gene Expression" (`/alteredExpression`: property + species), plus each section's comments. `fetch_gtopdb_function.py` flattens them into `data_sources/gtopdb/pages_function/<targetId>.md` (header with source URL and `fetched:`, then one statement per line, each naming its section and, where GtoPdb records one, its species), so a quote reads on its own. Unlike #7 / #11 / #12 the quote is **picked by an LLM** (not `machine`), so it follows the four-step receptor-effect pipeline and must be judged. Species: a row whose species GtoPdb states is offered as a candidate only when it is human or primate (most function rows are rat / mouse, nearly every altered-expression row is a knockout mouse), and the species rides the source like corpus #7's; pathophysiology rows state none (the section is clinical) and carry none. A group target sharing its representative gene with a modeled receptor (`muscarinic` -> CHRM1) is skipped, so an M1 row never backs the whole family. Added with Claude Code.
- **#24 BDPM RCP sections 4.2-4.4** (`bdpm_rcp`, `page` = the product CIS (or an EPAR's EMA product number, see below), resolving `base-donnees-publique.medicaments.gouv.fr/medicament/<page>/extrait`) is the same official French label as #16, read for what it asks a prescriber to check before starting a drug and during treatment (`drug_workup`). A sibling corpus rather than more lines on #16's pages, because a corpus has one `pages_dir` keyed by `page` and the same CIS is cited by both with different text and a different download date. `tools/fetch/fetch_bdpm_rcp.py` downloads nothing: it reads #16's own RCP download or the sibling justelesRCP checkout's re-scrape of the live ANSM site (read only; dated by its scrape manifest's `last_fetch`, else the file mtime; never its frozen `CIS_RCP.csv`), the freshest copy winning, and the page header names the copy and how its date was read. A drug whose every French product is centrally authorised (Briviact, Brintellix, Selincro, Champix: ANSM publishes no text of its own) falls back to EMA's French SmPC as justelesRCP stored it (`data/eu/<cis>.html.gz`, dated by its EMA scrape manifest), and that page links to the EMA PDF instead (`page_links`, licence "EMA, reproduction authorised, source acknowledged"). Levodopa is joined through its only French forms, the combinations with carbidopa or benserazide (`fetch_bdpm_rcp.COMBO_PARTNERS`). A drug with no French CIS product at all (EU-authorised but not marketed in France: Intuniv, Reagila, Latuda) is joined BY NAME on EMA's published EPAR tables (`medicines-output-medicines_json-report_en.json` + `documents-output-epar_documents_json-report_en.json`, cached under `data_sources/ema/raw/`, `tools/fetch/fetch_ema_epar.py`): a human, authorised EPAR whose active substance is exactly the drug's molecule (salt words stripped, a combination never matching a single drug, stereo guarded through `lib.corpora.bdpm.drug_keys` + `tools/lib/chirality.py`), the brand the drug already lists first, then the originator, then the oldest. Its French (else English) SmPC is justelesRCP's converted copy when it holds that PDF, else downloaded from EMA once and converted with justelesRCP's `src/ema_pdf.py`; the page is keyed by the EMA product number (`page` = `EMEA-H-C-003759`, hence `page_kind` `product`), links to the EMA PDF through `page_links`, and the chosen EPAR (product, holder, number, status, dates, EPAR url) is recorded under `ema` in `tools/generated_cache/bdpm_rcp_labels.json`. The line is LLM-picked by index, so every citation is judged (`recheck_quotes.py`, Opus). Licence Ouverte, as #16.
- **#15 CPIC** (`cpic`, `page` = the guideline's ClinPGx id, e.g. `PA166251445`) is the prescribing
  guidance a metabolizer phenotype implies, the only corpus here that says what a *clearance speed means
  for a prescription* rather than stating a fact about a molecule or a brain. It backs one node kind,
  `drug_pgx`, one node per (drug, gene, phenotype), and that node carries **two** citations rather than
  splitting in two: CPIC's `implications` sentence and the `drugrecommendation` that follows from it are
  one claim read in one go, and the recommendation is unreadable without the implication. Committed like
  #13 (`tools/data/cpic/cpic_recommendations.json`, `tsv_dir`, no `pages_dir`), gated by re-derivation,
  `machine` + `extraction: "code"` so no judge is owed. Three limits are structural: CPIC files tricyclic
  and SRI dosing on **two** genes at once, so a row kept under one gene records `assumes` the other is a
  normal metabolizer (55 of 104 rows); its uncertainty phenotypes (`Likely`/`Possible` Intermediate,
  `Indeterminate`, `No Result`) are dropped, having no frequency to pair with; and a gene with no
  metabolizer-frequency profile here (HLA-A, HLA-B, SCN1A, the urea-cycle genes) is out of scope, since
  the readout exists to put a base rate on a row. It also backs a few `drug_enzymes` rows, but only
  where CPIC's own sentence names the gene and the drug together ("Consider alternative drug not
  metabolized by CYP2C19; If clomipramine is warranted, ..."): the *level* of a pair is a verdict
  rather than a sentence, so it is never quoted as one. CC0 1.0, attribution requested (see
  `tools/data/cpic/README.md`).

**Descriptions** are not a node kind (not tallied). Drugs, structures and non-receptor targets carry
**no baked description**: their panel fetches the **current Wikipedia lead** (CC BY-SA) at runtime via
`liveWikiDescription` over `js/wiki.js` `fetchWikiLead(url, lang)` (locale lead, English fallback), so
the dataset ships no copyrighted prose (a panel whose live lead fails shows none). Receptors + projection
groups carry a short **authored** `description` as the offline fallback, overridden best-effort by the
live lead. The lead shows collapsed: its first paragraph clipped to ~300 characters at a word boundary (`wiki.js` `clipLead`), with an inline "Read more" / "Show less" toggle (`.wiki-more`) expanding the whole intro in place. Needs the `connect-src https://*.wikipedia.org` CSP allowance.

**The live-Wikipedia source link (green, viewer-only).** A live-fetched lead shows its provenance as the
**Wikipedia link itself**, relocated (by `liveWikiDescription`) to the end of the description in place of a
grade pill and styled as a green pill-link (`.wiki-src`, reusing `.src-prov-wikipedia`): a live fetch is a
verbatim programmatic read that cannot drift, so it earns the green tier, and the link (not a cryptic ✓)
makes plain the text is *from* Wikipedia and clicks through to it. `appendWiki` stashes the reference link
as `wrap._refLink`; on a successful fetch it moves up and the emptied reference row is dropped (any lookup
links stay). It is a **presentation**, **not** a stored grade and **not** tallied; the green ✓
`PROVENANCE_PILLS.wikipedia` pill (`info.provWikipedia`) remains only as a fallback if the link can't be
moved. Asymmetry: a **baked** Wikipedia snapshot stays yellow `sourced` (a stored copy *can* drift); only
the **live** read earns the green link. When the live fetch fails, the baked description keeps its stored
pill and the reference link stays in its own row; a missing link shows `NOSOURCE`.

**The "% sourced" figure.** `_provenance_stats` reduces every node + reference to its strongest grade and
buckets it into **verified** (quote-checked) / **uncertain** (quote-checked, but its `uncertainty[]`
bullets say the quote does not attribute the claim) / **sourced** (from a document) / **missing** (no
document). A bare `llm` grade *is* missing (an LLM asserting from memory has no document), so it buckets
with a sourceless node (the viewer still shows them differently, grey `?` vs orange `NOSOURCE`).
`uncertain` counts as **backed** (a real document exists), so flagging a claim leaves `pct_backed`
untouched and only moves the node out of the green count. It tallies per
node kind (drug bindings, NbN, drug class, projections, circuits, projection groups, receptor/target
classifications, receptor/target expression regions, region anatomy, wikipedia references), plus a
headline `pct_backed` over the **knowledge nodes** (references excluded, a reference points *at* a node).
The `references` kind stays in `by_kind` but the viewer does **not** render it as a coverage bar (a
reference is not a knowledge node, and every present link defaults to `sourced`, so the bar was uniformly
yellow noise); it is emitted as `meta.provenance_stats` (key `nodes`). Each expression region is its own node, individually
upgradeable. **The live per-kind figures live in the README `SOURCING_STATS` block (auto-written by
`update_readme_stats.py`, CI runs it `--check`) and the Sources & provenance popup; they are not repeated
here, to avoid drift.** `check_data.py` re-confirms the tally is self-consistent (coverage columns M/S/S+V).
Separately, `meta.provenance_stats.ki_coverage` tracks **measured-affinity (PDSP Ki) coverage** (bindings
with a Ki, drugs with none; combos excluded): NOT a grade (a quote-only binding is still sourced), but the
honest complement surfacing where a measured affinity was never looked up. Rendered in the sourcing popup +
README block, warned per-drug by `check_data.py` family 7.
