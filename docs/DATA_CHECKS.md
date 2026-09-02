# Data checks

> Reference detail moved out of [`CLAUDE.md`](../CLAUDE.md) to keep that file a terse map. This is the full text for this subsystem.

## Data checks

`tools/check_data.py` (stdlib) runs over the **emitted** `public/data/`,
independent of `generate_data.py`. Exit 0 = no errors (warnings allowed), 1 =
errors. Functions take loaded data as args (unit-testable). Eleven families (numbered
0-10 in the output):

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
  guarantees the panels' "Found in" rows are clickable. Dangling refs = error.
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
  totals, recomputed `pct_backed`) or error.
- **Source quotes** (the heart of sourcing): each quote-level drug source
  (`{corpus,page,quote,provenance}`): `corpus` must resolve to `meta.source_corpora`,
  a `verified` source must carry page + quote, and the normalized quote must be an
  exact substring of the normalized cited page text. Page material is author-side
  (see CLAUDE.local.md); the quote check is skipped + warned on a clone without it.
  A quote not on its page = error (the gate that keeps the LLM extraction honest).
  Verbatim-on-the-page is not the same as about-this-drug, so two more gates ask the
  second question: a binding quote may not be one of Stahl's subject-less class rules
  ("Blocking X can cause Y", the sulpiride mistake), and every Stahl quote on a drug
  must cite a page inside that drug's own monograph (read from the book's generated
  `INDEX.md`, author-side, skipped + warned on a clone). A quote lifted off the
  neighbouring drug's entry is verbatim on the page it cites and still says nothing
  about this drug, so only the range check can catch it. The subject-less gate **stands
  down** for a binding that declares `uncertainty[]`: the orange badge answers the same
  question out loud instead of banning the quote (see CLAUDE.md Source provenance). Those
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
