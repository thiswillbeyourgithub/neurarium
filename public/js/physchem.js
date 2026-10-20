// CNS penetration (a Pharmacokinetics subsection): the drug panel's lipophilicity, polar-surface and
// blood-brain-barrier chips (node kinds drug_lipophilicity / drug_polar_surface /
// drug_bbb, PubChem corpus #21 + B3DB corpus #22; mapped in js/data.js). Built on the
// Pharmacokinetics block's own `valueChip` (js/tdm.js), so a chip reads, wraps and
// carries its pill exactly like a T½ chip. The wording helpers are shared with the node
// browser so a value reads the same in both places.
//
// Built with the help of Claude Code.

import { formatNumber, valueChip } from "./tdm.js";

/** "3.2" / "−0.4" from a mapped XLogP3 (a locale number, "3,2" in French). */
export function formatLogP(v, lang) {
  return formatNumber(v, lang).replace(/^-/, "−");
}

/** "36.3 Å²" from a mapped topological polar surface area. */
export function formatTpsa(v, lang) {
  return `${formatNumber(v, lang)} Å²`;
}

/** "BBB+", "BBB+ (logBB 0.99)" or "BBB+ (logBB 0.78 to 0.8)" from a mapped `drug.bbb`;
 *  `t` supplies the range word. */
export function formatBbb(b, t, lang) {
  if (b.logbb == null) return b.label;
  const lo = formatLogP(b.logbb, lang);
  const val = b.logbbMax == null ? lo
    : t("drug.bbbRange", { lo, hi: formatLogP(b.logbbMax, lang) });
  return `${b.label} (logBB ${val})`;
}

/**
 * Append the drug's XLogP3, TPSA and BBB chips to `host`. Each label carries the
 * tooltip saying how to read the value (and that the first two are computed estimates,
 * the third curated measurement data). `h` = the panel's own helpers
 * {el, nodePill, t, lang} (js/main.js).
 */
export function appendPhyschemChips(host, drug, h) {
  const { t, lang } = h;
  const chip = (node, label, tip, value) => host.appendChild(valueChip(h, {
    label, tip, value, provenance: node.provenance, sources: node.sources,
    uncertainty: node.uncertainty }));
  if (drug.xlogp) {
    chip(drug.xlogp, t("drug.xlogp"), t("drug.xlogpTip"), formatLogP(drug.xlogp.value, lang));
  }
  if (drug.tpsa) {
    chip(drug.tpsa, t("drug.tpsa"), t("drug.tpsaTip"), formatTpsa(drug.tpsa.value, lang));
  }
  if (drug.bbb) {
    chip(drug.bbb, t("drug.bbb"), t("drug.bbbTip"), formatBbb(drug.bbb, t, lang));
  }
}

/** True when the drug carries any of the three (the section is skipped otherwise). */
export function hasPhyschem(drug) {
  return Boolean(drug.xlogp || drug.tpsa || drug.bbb);
}
