# Data checks

> Reference detail moved out of [`CLAUDE.md`](../CLAUDE.md) to keep that file a terse map. This is the full text for this subsystem.

## Data checks

`tools/check_data.py` (stdlib) runs over the **emitted** `public/data/`,
independent of `generate_data.py`. Exit 0 = no errors (warnings allowed), 1 =
errors. Functions take loaded data as args (unit-testable). Six families:

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
  higher grade. TODOs never fail the run.
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
  Also checks each binding's `ki`: its source corpus resolves, an `affinity_only`
  binding carries a `ki`, and (author-side, skipped on a clone) the cited `ki_id` row
  is really in the corpus CSV with that value (the PDSP analogue of the quote gate).
- **Structure connectivity** (warns, never errors): isolated / inward-only /
  outward-only structures from the projection endpoints (`bidirectional` counts
  both ways). Source nuclei + olfactory bulb are expected outward-only, pituitary
  inward-only; the point is to flag a region wired one-way (e.g. a missing return pathway).
