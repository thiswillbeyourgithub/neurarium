// Graded-node helpers shared by every loader stage: the strongest grade among a
// node's sources, and the normalized source / sub-claim / uncertainty shapes the
// panel renders.

// Provenance grade ordering (weakest -> strongest); the strongest grade among a
// record's sources colours its summary source pill. Null when there are none.
// Shared by projections (below) and drug bindings / NbN (further down), so the
// "strongest grade wins" rule lives in one place.
const GRADE_RANK = { llm: 1, sourced: 2, verified: 3 };
export const strongestGrade = (sources) => {
  let best = null;
  let rank = 0;
  for (const s of sources || []) {
    const r = GRADE_RANK[s.provenance] || 0;
    if (r > rank) {
      rank = r;
      best = s.provenance;
    }
  }
  return best;
};

// Normalize a quote-level sources list (a binding's `sources` or a drug's
// `nbn_sources`) into the shape the panel renders.
export const mapSources = (sources) =>
  (sources || []).map((s) => ({
    corpus: s.corpus,
    page: s.page != null ? s.page : null,
    quote: s.quote || "",
    provenance: s.provenance || "llm",
    // Where in the book the passage sits ({drug, section, subsection}, derived
    // by tools/fetch/fetch_quote_headers.py). Absent for a corpus with no page
    // structure (a Ki CSV row) and for a quote whose heading could not be
    // resolved: the tooltip then simply shows no breadcrumb.
    heading: s.heading || null,
    // How this quote came to be cited (see meta.quotePipelines): the tooltip ends
    // with the chain, so a reader can tell a parser copying a table cell from a
    // model reading a book page.
    pipeline: s.pipeline || null,
    // The page's download date (editable online corpora only, see withFetched).
    fetched: s.fetched || null,
    // The reuse licence of an open-access text quoted from (a Europe PMC full-text
    // paper, e.g. "CC BY-NC"), credited in the tooltip; null for every other source.
    licence: s.licence || null,
    // A PDSP CSV row cited in place of a quote (a measured Ki, or an inactive
    // ceiling a curated denial rests on): the tooltip spells the row out.
    kiRow: s.ki_id != null ? {
      id: s.ki_id, valueNm: s.value_nm, note: s.note || "", species: s.species || "",
      radioligand: s.radioligand || "", reference: s.reference || "",
    } : null,
  }));
// The per-claim split (tools/data_generators/quotes/attestation.py): a node that
// asserts several things at once carries one graded entry per part, so the part a
// quote does not name reads `llm` instead of borrowing the node's grade. Normalized
// like any other source list, since each entry's pill opens the same tooltip.
export const mapClaims = (claims) => {
  if (!claims) return null;
  const out = {};
  for (const [name, entry] of Object.entries(claims)) {
    out[name] = {
      grade: entry.grade || "llm",
      sources: mapSources(entry.sources),
      // A sub-claim can carry its own "uncertain" bullets (a denial, a set-level
      // sentence), independent of its owner's.
      uncertainty: mapUncertainty(entry.uncertainty),
    };
  }
  return out;
};
// Reasons the quote does not settle the claim (the orange "uncertain" badge; derived
// or curated in tools/data_generators/quotes/). Each bullet is a reason `kind` + slot
// `args` + its own source, or `absence` when the point IS that the corpus never says
// it; the sentence itself is an i18n string, so nothing here is stored prose. Always
// an array, so a panel can test `.length` with no guard.
export const mapUncertainty = (list) =>
  (list || []).map((u) => ({
    kind: u.kind,
    args: u.args || {},
    absence: !!u.absence,
    sources: mapSources(u.sources),
  }));
