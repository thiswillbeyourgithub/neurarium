// Provenance grades: the one home for their orderings and the small rules built
// on them (strongest grade wins, the display grade, the "backed" tally).

// Stored grade ordering (weakest -> strongest): what a source's `provenance`
// can hold. The strongest among a record's sources colours its summary pill.
export const GRADE_RANK = { llm: 1, sourced: 2, verified: 3 };

// Sort rank of the DISPLAY grade, weakest to strongest (a distinct concept: it
// also ranks the non-stored grades). `uncertain` sits between sourced and
// verified for the same reason the Sources popup's bar does: the quote really
// was checked, it just may not attribute the claim. `unknown` (searched, nothing
// states it) sorts just above nosource: still no source, but a finding rather
// than a to-do.
export const DISPLAY_GRADE_ORDER = {
  nosource: 0, unknown: 0.5, llm: 1, sourced: 2, uncertain: 3, verified: 4,
};

/** Strongest stored grade among `sources` (by `s.provenance`), null when none. */
export const strongestGrade = (sources) => {
  let best = null;
  let rank = 0;
  for (const s of sources || []) {
    const r = GRADE_RANK[s.provenance] || 0;
    if (r > rank) { rank = r; best = s.provenance; }
  }
  return best;
};

/**
 * The grade a node displays: "uncertain" when it carries doubt bullets AND rests on a
 * document, else its own grade. A bare llm claim another corpus denies is still
 * missing its own source (the tally buckets it so too, provenance.py `bucket`), so
 * its bullets show in the tooltip without lifting its pill to the backed orange.
 * @param {string|null|undefined} grade the node's own grade
 * @param {object[]|null|undefined} uncertainty its bullets
 * @returns {string|null|undefined}
 */
export function shownGrade(grade, uncertainty) {
  const isBacked = grade === "verified" || grade === "sourced";
  return uncertainty && uncertainty.length && isBacked ? "uncertain" : grade;
}

/** Nodes in a grade-count tally that rest on a document (verified + uncertain + sourced). */
export const backed = (counts) =>
  (counts.verified || 0) + (counts.uncertain || 0) + (counts.sourced || 0);
