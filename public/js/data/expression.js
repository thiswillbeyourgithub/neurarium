// Expression nodes: one "Found in" region entry and a relative-density profile,
// shared by receptors and non-receptor targets (same node shapes).

import { strongestGrade } from "./sources.js";

// Build one "Found in" region entry (its per-region expression provenance +
// the assay species). An expression source (e.g. a GtoPdb tissue-distribution
// quote) carries the species it was checked in; the panel flags a non-human
// claim amber, like the Ki chip, and shows the species in the pill tooltip.
// Shared by receptor + non-receptor-target location lists so the species logic
// lives once (both kinds carry the same location_sources node shape).
// `uncertainty` is the region's own bullets (an animal-only claim, see
// quotes/animal_evidence.py), kept raw like `sources`: they turn its pill orange.
export const locationEntry = (base, name, sources, uncertainty) => {
  const srcs = sources || [];
  const speciesList = srcs.map((s) => s.species).filter(Boolean);
  // Prefer a Human assay when any source carries one: a region we have confirmed
  // in human tissue is not a "non-human only" claim, so it must not keep the amber
  // tag just because another source (e.g. a rat GtoPdb quote) also backs it.
  const species = speciesList.includes("Human")
    ? "Human"
    : (speciesList[0] || "");
  return {
    base, name, sources: srcs,
    provenance: strongestGrade(srcs) || "llm",
    uncertainty: uncertainty || [],
    species,
    nonHuman: !!species && species !== "Human",
  };
};

// Normalize an owner's relative-expression density node (a receptor's or a
// non-receptor target's; identical shape) for the panel. The emitted `profile` maps a
// region base -> a z-score against that gene's own brain-wide average, so the numbers
// are comparable WITHIN one owner and not across owners; `rel` therefore scales each
// region against this owner's own strongest/weakest region, which is the only bar width
// that means anything. A floor keeps the weakest region a visible sliver rather than
// reading as "absent" (it is present: that is what the presence node said).
export const densityEntry = (density) => {
  if (!density || !density.profile) return null;
  const zs = Object.values(density.profile);
  if (zs.length < 2) return null;
  const min = Math.min(...zs);
  const max = Math.max(...zs);
  const span = max - min;
  const rel = {};
  for (const [base, z] of Object.entries(density.profile)) {
    rel[base] = span > 0 ? 0.08 + 0.92 * ((z - min) / span) : 1;
  }
  return {
    profile: density.profile,
    rel,
    reliability: density.reliability,
    donors: density.donors,
    provenance: density.grade || "llm",
    sources: density.sources || [],
  };
};
