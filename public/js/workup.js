// Pre-prescription workup (BETA): the drug panel's "Monitoring (French SmPC)"
// section (node kind drug_workup, BDPM RCP corpus #24; mapped in js/data.js). One node
// per (drug, test, timing), the test and timing labels coming from meta.workup_tests /
// meta.workup_timings. Pure helpers only (no DOM), so tools/tests/workup.test.mjs can
// pin the grouping and the wording. Built with the help of Claude Code.

/** Display order of the two timings (the generator already sorts each drug's rows). */
const WORKUP_TIMINGS = ["before", "during"];

/**
 * Split a drug's workup rows by timing, keeping the authored order inside each group.
 * Empty groups are dropped, so a drug asked only for monitoring shows one group.
 * @param {Array<{timing: string}>} rows
 * @returns {Array<{timing: string, rows: Array}>}
 */
export function groupWorkup(rows) {
  return WORKUP_TIMINGS
    .map((timing) => ({ timing, rows: (rows || []).filter((r) => r.timing === timing) }))
    .filter((g) => g.rows.length);
}

/**
 * One node as a single line, for the node browser and the Sources popup:
 * "ECG (QT interval), before starting".
 */
export function formatWorkup(n, onlyIf = "only if:") {
  const base = `${n.testLabel}, ${n.timingLabel}`;
  const cond = formatConditions(n, onlyIf);
  return cond ? `${base}, ${cond}` : base;
}

/**
 * The "only if" clause of a conditional node (the label asks for the check only in
 * some patients), its verbatim French spans joined: "only if: chez le sujet âgé".
 * Empty for an unconditional node.
 */
export function formatConditions(n, onlyIf = "only if:") {
  const c = (n && n.conditions) || [];
  return c.length ? `${onlyIf} ${c.join("; ")}` : "";
}
