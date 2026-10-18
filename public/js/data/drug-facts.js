// The per-drug scalar facts: description, NbN, class, kinetics, formulations,
// regulatory history, TDM, physicochemistry, workup. One graded node each.

import { localize } from "./localize.js";
import { strongestGrade, mapSources, mapUncertainty } from "./sources.js";

/** Resolve one drug's fact fields in place. */
export function resolveDrugFacts(d, v) {
  const { drugCategoryLabels, releaseLabels, historyCountries, historyAgencies,
          historyScopes, withdrawalReasons, workupTests, workupTimings } = v;
  d.description = d.description ? localize(d.description) : "";
  // Provenance grade of the description (llm synthesis vs a sourced Wikipedia
  // lead); the panel shows a pill beside it.
  d.descriptionProvenance = d.description_provenance || null;
  d.nbn = d.nbn ? localize(d.nbn) : "";
  // The NbN is quote-sourced like a binding (verbatim Stahl line); the panel
  // shows a provenance pill next to it. Null grade when unsourced.
  d.nbnSources = mapSources(d.nbn_sources);
  d.nbnProvenance = strongestGrade(d.nbn_sources);
  // True when the "nomenclature" is Stahl's drug-class descriptor, not a formal
  // Neuroscience-based Nomenclature (a newer drug Stahl gives no NbN); the panel
  // flags it so the value isn't misread as an official NbN code.
  d.nbnNonstandard = !!d.nbn_nonstandard;
  d.categoryLabels = (d.categories || []).map((c) => drugCategoryLabels[c] || c);
  d.category = d.categoryLabels[0] || "";
  // The drug's class classification ("this drug is an SSRI/...") is its own graded
  // node: the panel shows a provenance pill on the Class row. Default "llm" (LLM-
  // authored); `category_sources` (quote-level, if any) upgrade the emitted grade.
  d.categorySources = mapSources(d.category_sources);
  d.categoryProvenance = d.category_provenance || "llm";
  // Vendored molecular-structure SVG path (data/molecules/<id>.svg), set by the
  // generator only when the file was fetched; the drug panel embeds it as an
  // <img>. Null when no SVG is available (no image shown).
  d.structureImage = d.structure_image || null;
  // Elimination half-life (T½): {hours, hours_max?} passed through raw; the panel
  // formats it via formatHalfLife (js/main.js). Its own sourced node, so carry the
  // strongest grade + sources for the pill next to it.
  d.halfLife = d.half_life || null;
  d.halfLifeSources = mapSources(d.half_life_sources);
  d.halfLifeProvenance = strongestGrade(d.half_life_sources);
  // Time to peak plasma concentration (Tmax), same shape and same treatment: its
  // own sourced node, and the other end of the curve js/sim-model.js draws (the T½
  // sets the fall, this sets the rise). Null on the ~70% of drugs no corpus states
  // a peak for; the simulation then uses its single assumed peak.
  d.tmax = d.tmax || null;
  d.tmaxSources = mapSources(d.tmax_sources);
  d.tmaxProvenance = strongestGrade(d.tmax_sources);
  // Formulations: one per release type a source names, each its own graded node
  // (the release) holding the brands / Tmax / T½ measured or sold for THAT product.
  // Molecule-level `brands` / `tmax` / `halfLife` above are what no source ties to
  // one product. See docs/DRUGS.md "Formulations".
  d.formulations = (d.formulations || []).map((f) => ({
    release: f.release,
    label: releaseLabels[f.release] || f.release,
    releaseSources: mapSources(f.release_sources),
    releaseProvenance: strongestGrade(f.release_sources),
    brands: (f.brands || []).map((b) => ({ ...b, release: f.release })),
    tmax: f.tmax || null,
    tmaxSources: mapSources(f.tmax_sources),
    tmaxProvenance: strongestGrade(f.tmax_sources),
    halfLife: f.half_life || null,
    halfLifeSources: mapSources(f.half_life_sources),
    halfLifeProvenance: strongestGrade(f.half_life_sources),
  }));
  // Regulatory history: the earliest approval the source states (one node) and
  // each market withdrawal (one node each; none at all when never withdrawn).
  // Labels resolved here so the panel and the node browser share one wording.
  const fa = d.first_approval;
  d.firstApproval = fa ? {
    year: fa.year,
    countryLabel: fa.country ? historyCountries[fa.country] || fa.country : null,
    agencyLabel: fa.agency ? historyAgencies[fa.agency] || fa.agency : null,
    // The earliest approval in that one country (a regulator's own register).
    national: !!fa.national,
    sources: mapSources(d.first_approval_sources),
    provenance: strongestGrade(d.first_approval_sources),
  } : null;
  // Who the drug comes from (kinds drug_originator / drug_originator_country /
  // drug_holders): the originator lab (its `now` name cited apart, shown in its
  // tooltip, graded by the name's own sources), that lab's country, and the current
  // marketing-authorisation holders, one node per market.
  const og = d.originator;
  d.originator = og ? {
    name: og.name,
    now: og.now || null,
    sources: mapSources([...(d.originator_sources || []), ...(d.originator_now_sources || [])]),
    provenance: strongestGrade(d.originator_sources),
    country: d.originator_country ? {
      label: historyCountries[d.originator_country] || d.originator_country,
      sources: mapSources(d.originator_country_sources),
      provenance: strongestGrade(d.originator_country_sources),
    } : null,
  } : null;
  d.holders = (d.holders || []).map((h) => ({
    market: h.market,
    marketLabel: historyCountries[h.market] || h.market,
    names: h.names,
    sources: mapSources(h.sources),
    provenance: strongestGrade(h.sources),
    uncertainty: mapUncertainty(h.uncertainty),   // e.g. a curated `contradicted`
  }));
  // Prodrug flag (kind drug_prodrug): its own graded claim; the borrowed
  // bindings are wired by the prodrug pass above this loop.
  d.prodrug = d.prodrug ? {
    sources: mapSources(d.prodrug_sources),
    provenance: strongestGrade(d.prodrug_sources),
  } : null;
  // A salt's declared composition (kind drug_constituents): its own graded claim,
  // pilled on the combo box; the borrowed bindings are wired above this loop.
  d.constituentsClaim = (d.constituents || []).length ? {
    sources: mapSources(d.constituents_sources),
    provenance: strongestGrade(d.constituents_sources),
  } : null;
  // Therapeutic drug monitoring (kinds drug_therapeutic_range / drug_alert_level,
  // AGNP corpus #19): each its own graded node, both from one Table 5 row.
  const trr = d.therapeutic_range;
  d.therapeuticRange = trr ? {
    low: trr.low, high: trr.high, unit: trr.unit, analyte: trr.analyte || null,
    tdmLevel: trr.tdm_level || null,
    sources: mapSources(d.therapeutic_range_sources),
    provenance: strongestGrade(d.therapeutic_range_sources),
  } : null;
  const al = d.alert_level;
  d.alertLevel = al ? {
    value: al.value, unit: al.unit, analyte: al.analyte || null,
    sources: mapSources(d.alert_level_sources),
    provenance: strongestGrade(d.alert_level_sources),
  } : null;
  // Physicochemistry and brain entry (kinds drug_lipophilicity / drug_polar_surface /
  // drug_bbb, PubChem #21 + B3DB #22), one graded node each, rendered by
  // js/physchem.js. `xlogp` / `tpsa` arrive as bare numbers, so they are wrapped.
  const physNode = (srcs, rest) => ({
    ...rest, sources: mapSources(srcs), provenance: strongestGrade(srcs) });
  d.xlogp = d.xlogp != null ? physNode(d.xlogp_sources, { value: d.xlogp }) : null;
  d.tpsa = d.tpsa != null ? physNode(d.tpsa_sources, { value: d.tpsa }) : null;
  d.bbb = d.bbb ? physNode(d.bbb_sources, {
    label: d.bbb.label, logbb: d.bbb.logbb ?? null, logbbMax: d.bbb.logbb_max ?? null,
  }) : null;
  // Pre-prescription workup (kind drug_workup, BETA): one node per (test, timing) the
  // French label (RCP 4.2 / 4.3 / 4.4) asks for, rendered by js/workup.js + main.js.
  d.workup = (d.workup || []).map((w) => ({
    test: w.test, timing: w.timing,
    testLabel: workupTests[w.test] || w.test,
    timingLabel: workupTimings[w.timing] || w.timing,
    conditions: w.conditions || [],   // verbatim French spans: a conditional ask
    sources: mapSources(w.sources),
    provenance: strongestGrade(w.sources),
    uncertainty: mapUncertainty(w.uncertainty),   // e.g. a curated `contradicted`
  }));
  d.withdrawals = (d.withdrawals || []).map((w) => ({
    year: w.year,
    country: w.country,
    countryLabel: historyCountries[w.country] || w.country,
    // A market scope ("worldwide", "most markets") rather than one country: the
    // panel lists it first in a grouped row (js/drug-history.js groupWithdrawals).
    scope: historyScopes.has(w.country),
    reason: w.reason,
    reasonLabel: withdrawalReasons[w.reason] || w.reason,
    sources: mapSources(w.sources),
    provenance: strongestGrade(w.sources),
  }));
}
