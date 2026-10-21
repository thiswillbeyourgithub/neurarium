# Data checks

> Reference detail moved out of [`CLAUDE.md`](../CLAUDE.md) to keep that file a terse map. This is the full text for this subsystem.

## Data checks

`tools/check_data.py` (stdlib) runs over the **emitted** `public/data/`,
independent of `generate_data.py`. Exit 0 = no errors (warnings allowed), 1 =
errors. It is only the CLI: each family is its own module under `tools/checks/` (shared report + loaders in `checks/common.py`, family 5's per-node-kind quote walks under `checks/sources/`), and every `check_*` takes loaded data as args (unit-testable). Fourteen families (numbered
0-13 in the output):

Three severities: `[ERROR]` fails the run, `[warn]` is printed for a human to act on, and `[review]` is an eyeball list whose flags are mostly intended (family 8's flow-vs-binding split, family 7's per-drug "no measured Ki"): counted in the summary but listed only with `python tools/check_data.py --verbose`, so the default run's warnings stay few enough to read. The short-quote warning (family 5) skips any flattened table row (`cell | cell`) and one-cell facts on the owner's own page (a brand, class label, duration, metabolism cell, tissue line); it still fires on a short binding or pathway quote, where an incidental substring is plausible.

- **Quote table** (referential integrity of the externalized `quotes.jsonl`): every node's
  `{quote_id, provenance}` source must resolve to a quote node, and every quote node must be
  referenced by at least one node (no orphans) = error either way. The loader rehydrates each
  reference in place first (mirror of the viewer), so the families below see inline sources.
- **Duplicates** (per collection + projections by `from -> to`): exact or
  normalized id/key collision = error (`normalize_for_match` lowercases + strips
  non-alphanumerics, so `mao_a`/`mao-a` collide); normalized display-name collision
  = warning.
- **Reachability**: every cross-reference must resolve (drug binding `target`,
  projection endpoints/kind, circuit/receptor/target structure refs, projection-
  group `kind`/`sign` key, receptor classification keys, target type + region bases,
  every receptor also a `drug_targets` key). The region-base check is what
  guarantees the panels' "Locations" rows are clickable. Dangling refs = error.
  Addon nodes are checked from both ends here: the anchored node must exist in its
  kind's pool AND the `slot`/`display`/`tone` must be in the emitted vocabularies
  (an addon in a slot no panel offers would ship graded, counted and invisible).
- **TODOs** (provenance-aware): a literal `"TODO"` outside a source url, or a
  focusable target with no `wikipedia`, = warning. A source *url* left `"TODO"` is
  `[ok]` for an `llm` citation (expected) but **warned** if the source claims a
  higher grade. TODOs never fail the run. A source *corpus* with no `url` at all is
  expected (a book has no free landing page); a corpus url that is present but not a
  real link is an **error**.
- **Provenance grades**: every `provenance` (incl. per-binding sources, `nbn_sources`,
  circuit + projection-group sources), every `classification_provenance`, every
  `wikipedia_provenance` must be a known grade (`llm`/`sourced`/`verified`) or
  error. Re-confirms `meta.provenance_stats` is self-consistent (per-kind sums,
  totals, recomputed `pct_backed`) or error. An UNKNOWN stamp (`unknown` on a binding,
  see [`PROVENANCE.md`](PROVENANCE.md)) is an error on a binding that states a direction,
  or when its search skipped a corpus `UNKNOWN_REQUIRED_SOURCES` lists for its kind.
- **Source quotes** (the heart of sourcing): each quote-level drug source
  (`{corpus,page,quote,provenance}`): `corpus` must resolve to `meta.source_corpora`,
  a `verified` source must carry page + quote, and the normalized quote must be an
  exact substring of the normalized cited page text. Page material is author-side
  (see CLAUDE.local.md); the quote check is skipped + warned on a clone without it.
  A quote not on its page = error (the gate that keeps the LLM extraction honest), and so
  is a page file missing (or a path-like page id) inside a page tree that is present.
  Coverage does not depend on the node walks knowing a kind: `checks/sources/sweep.py`
  also looks up every `quotes.jsonl` row and every quote-shaped source committed under
  `tools/generated_cache/*.json` + `tools/data/*.jsonl` (a cached quote nothing emits,
  such as a removed owner's, otherwise goes stale unseen), for every corpus with a
  `pages_dir` (`tools/tests/test_quote_sweep.py` enumerates them off `SOURCE_CORPORA`).
  A corpus that ships its own raw tables declares `tsv_dir` instead of `pages_dir`, and
  the page lookup **stands down** for it rather than being skipped: there is no prose page
  to read, and a page generated out of the same numbers as the quote could not gate
  anything. Those quotes are proved by re-derivation instead, in the enzyme-variability
  family below.
  This walks every quote-level source the emitted data carries, `meta.enzymes[*].variability`
  included: a node kind nobody routed through here would ship `verified` with nothing
  checking it.
  Verbatim-on-the-page is not the same as about-this-drug, so two more gates ask the
  second question: a binding quote may not be one of Stahl's subject-less class rules
  ("Blocking X can cause Y", the sulpiride mistake), and every Stahl quote on a drug
  must cite a page inside that drug's own monograph (read from the book's generated
  `INDEX.md`, author-side, skipped + warned on a clone). A quote lifted off the
  neighbouring drug's entry is verbatim on the page it cites and still says nothing
  about this drug, so only the range check can catch it. The subject-less gate **stands
  down** for a binding that declares `uncertainty[]`: the orange badge answers the same
  question out loud instead of banning the quote (see docs/PROVENANCE.md). Those
  bullets are then gated in turn: the `kind` must be in `meta.uncertainty_reasons`, each
  bullet source goes through the same verbatim quote check, and a bullet with no source
  must declare `absence: true` (a silent blank reads exactly like "the corpus is silent"
  while meaning the source was forgotten; citing a source *and* claiming absence is an
  error too). A source's derived `heading` (the trail of book headings the passage sits
  under) is checked in two passes: its shape (a non-empty list of non-blank strings, since
  a blank crumb reads like a heading the book actually prints), then, for a Stahl quote,
  the half that is re-derivable offline: the trail must open with the monograph the cited
  page actually falls in. That catches a stale or hand-edited
  `generated_cache/quote_headers.json`, which would otherwise print a confident and wrong
  breadcrumb over a genuine quote.
  Every citation must also name a `pipeline` in `meta.quote_pipelines` (its chain of
  custody, see docs/PROVENANCE.md), and **no LLM-picked quote may ship unjudged**:
  a pipeline with an `extract_llm` step and no `judge_llm` step is an error, because a
  sentence a model chose out of prose is the one that can be chosen wrongly and nothing has
  yet said otherwise. The rule is read off the chains rather than restated as a list of
  pipeline names, so it keeps holding as pipelines are added. A quote code copied out of a
  table has no such failure mode and is not asked for a judge.
  Also checks each binding's `ki`: its source corpus resolves, an `affinity_only`
  binding carries a `ki`, and (author-side, skipped on a clone) the cited `ki_id` row
  is really in the corpus CSV with that value (the PDSP analogue of the quote gate).
- **Structure connectivity** (warns, never errors): isolated / inward-only /
  outward-only structures from the projection endpoints (`bidirectional` counts
  both ways). Source nuclei + olfactory bulb are expected outward-only, pituitary
  inward-only; the point is to flag a region wired one-way (e.g. a missing return pathway).
- **Measured-affinity (Ki) coverage** (warns, never errors): lists each drug with
  bindings but **zero** PDSP Ki across all of them (combos excluded), and cross-checks
  `meta.provenance_stats.ki_coverage` against a recompute. A quote-only binding is still
  sourced, so this is not a grade gate: it surfaces where a *measured* affinity was never
  looked up, the honest complement to "% sourced".
- **Drug flow vs. binding consistency** (warns, never errors): where the derived
  by-mechanism flow overlay and a drug's own bindings tell different stories (a
  postsynaptic-only engagement, or a system whose tone the drug raises into regions
  where it blocks that same transmitter's receptors). Mostly the intended
  presynaptic-tone vs. postsynaptic-block split, so it is a review list, not a gate.
- **Innervation coverage** (warns, never errors): per transmitter system, the regions
  that **express** it (receptor `locations` + non-receptor target `regions`) but that
  **no projection of that kind reaches**. The two layers have very different coverage
  (expression is sourced in bulk from GtoPdb/Allen, a pathway needs its own textbook
  quote), so a region can carry six adrenergic receptors with no noradrenergic arrow
  near it: the viewer then says "acts here" while drawing no supply. Usually a missing
  *pathway* from an existing source nucleus, occasionally a missing *structure* (this is
  the shape of hole the nucleus basalis filled). Also reports the mirror case (a pathway
  landing where the system has no recorded receptor: an *expression* gap) and any
  receptor family with no projection kind at all (no modeled source nucleus; expected
  for a local neuromodulator like opioid or cannabinoid). Glutamate + GABA are outside
  `system_flow_kinds` by design and never appear.
- **Changelog** (release notes per version): `public/data/changelog.json` must be
  well-formed, newest-version-first (the order the viewer relies on to show every
  release since a visitor's last one), with no duplicate version, a real `YYYY-MM-DD`
  date whose order matches the version order, a known category on
  every entry and a real sha on every commit ref. The one that bites: the version in
  `public/version.js` must have a `docs/changelog/<version>/changelog.md`, so bumping
  the version without writing notes fails here instead of shipping a What's new popup
  that announces an update it cannot describe.
- **Baked meshes** (pre-built SDF geometry): the manifest `public/data/meshes/index.json`
  records the `sha256` of every shape file it was baked from, and this re-hashes them. An
  edited shape with a stale bake is an **error**: the site would ship geometry that no longer
  matches its spec, which nothing else would catch (it renders fine, just wrong). Also checks
  each `.bin` exists and is non-empty, and reports orphans. A **missing** manifest is only a
  warning, since `js/baked-meshes.js` falls back to meshing in the browser: correct, just
  slower. `node tools/bake_meshes.mjs --check` is the same gate with byte-for-byte file
  comparison; see [`BAKED_MESHES.md`](BAKED_MESHES.md).
- **Enzyme variability** (profiles re-derived from the pinned export): the one quote gate
  that runs on a plain clone. PharmFreq (corpus #13) is the only corpus whose raw tables are
  committed (`tools/data/pharmfreq/`), so this re-hashes every file against the
  `export_sha256` pins in the corpus record, then rebuilds each isoform's whole
  metabolizer profile and its quote sentence straight from those files through the shared
  reader `tools/data_generators/pharmfreq.py`, and compares. A hand-edited frequency, a
  refreshed download nobody re-ran the fetcher over, or a quote that drifted from the
  numbers it claims to state is an **error**. Also reports the isoforms the export covers
  nothing for (CYP3A4 and CYP1A2, the two the dataset leans on hardest), so the gap keeps
  reading as a hole in the corpus rather than as a claim that they do not vary.
  The family's second half does the same for **CPIC prescribing guidance** (corpus #15,
  `tools/data/cpic/`): the pinned export is re-hashed, then every emitted `drug_pgx` row is
  rebuilt through `tools/data_generators/cpic.py` and compared field by field (gene, enzyme,
  level, guideline, phenotype, implication, recommendation, classification, assumption) along
  with both of the row's citations. Two citations on one node is the point: a recommendation
  separated from the implication it follows from would be advice with its reason missing, so
  the gate insists the row quotes CPIC's implication *then* its recommendation, in that order.
  It also re-derives the enzyme rows CPIC's wording states (`cpic.enzyme_claims_for`), both ways:
  an emitted enzyme row citing CPIC that the re-derivation does not produce is an **error**, since
  it would mean claiming a metabolic route CPIC never phrased, and such a row can only be a
  `substrate` one. The other direction is a **warning**, not an error: a gene CPIC doses a
  drug on that the drug's enzyme list does not carry means no corpus here states that route,
  which is a hole in the sources rather than a mistake in the data. It is worth a line all the
  same, because the panel then puts guidance about a patient's CYP2C19 speed over an Enzymes
  section that never names CYP2C19, and because the enzyme list feeds the derived drug -> drug
  edges, so a missing route quietly removes interactions (clomipramine's gained 11 when the row
  landed). Either side can open the gap: a CPIC refresh adding a pair, or a CYP fetcher re-run
  dropping a row.
- **Freshness** (editable corpora downloaded within 12 months): a book page or a published abstract does not change under a citation, but a Wikipedia article or a live database does, so every source of a corpus flagged `editable` in `meta.source_corpora` carries a `fetched` date (the day its page was downloaded, stamped by `generate_data.py` from the committed ledger `tools/generated_cache/fetch_dates.json`, see [`PROVENANCE.md`](PROVENANCE.md) "Freshness"). A cited page with no date, or one older than `FRESHNESS_MAX_MONTHS` (12, in `tools/data_generators/freshness.py`), is an **error**: refetch that corpus (recipe in [`tools/README.md`](../tools/README.md)). An UNKNOWN search (`unknown.searched`) older than the same limit is an **error** too: rerun the search. Author-side, a page whose own header date disagrees with the emitted one is an **error** too (refetched but not restamped). Runs on a clone (the dates are committed), and alone via `python tools/check_data.py --only freshness`, which the `pre-push` hook runs unskippably, so a stale corpus blocks a push even when the full data check is skipped.
