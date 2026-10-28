// A PCA axis caption: which way the drugs move along it, and why. DOM-free (node tests).
//
// A principal component is a weight per feature (`loadings`, every target / tone / effect
// in the profile), and a drug's coordinate is its centred profile dotted with them. A plain
// "A, B vs C, D" list of the heaviest weights misleads once profiles are SIGNED (the default:
// a block is a negative value, see model.js EFFECT_SIGN): blocking a positively weighted
// target moves a drug to the NEGATIVE end. So each heavy feature is placed at the end its
// drugs actually reach, worded by what they mostly do to it:
//   loadings [{target:"orexin", w:+0.45, mean:-0.3}, {target:"h1", w:-0.35, mean:-0.5},
//             {target:"gaba_a", w:+0.40, mean:+0.2}]   (mean = the raw profile mean, so its
//   sign is what most drugs in view do to that feature)
//   -> up:   [GABA-A boosted, H1 blocked]   (+0.40 x +, and -0.35 x -: both positive)
//      down: [orexin blocked]               (+0.45 x -)
// "boost" / "block" are the binding's effect on transmission (model.js EFFECT_SIGN), not on
// the protein: an SSRI blocks SERT but is stored as a serotonin "boost", so SERT reads
// "boosted". An unsigned feature (effects, or targets with Signed off) has a positive mean, so it lands
// on the side of its weight and carries no action word.

import { isTargetKey, TONE_PREFIX } from "./model.js";

/** Features named at each end of an axis caption; the hover lists them all. */
export const POLE_ITEMS = 3;

/**
 * The action word a feature gets: what the drugs in view mostly do to it, or null when the
 * feature has no direction (an effect, a target with Signed off).
 * @param {{target: string, mean: number}} l
 * @param {boolean} signed
 * @returns {"boost"|"block"|"raise"|"lower"|null}
 */
export function actionOf(l, signed) {
  if (l.target.startsWith(TONE_PREFIX)) return l.mean < 0 ? "lower" : "raise";
  if (signed && isTargetKey(l.target)) return l.mean < 0 ? "block" : "boost";
  return null;
}

/**
 * Split an axis' loadings (sorted by |w|, as model.js pca returns them) into the features
 * that pull drugs towards its positive and its negative end.
 * @param {{target: string, w: number, mean: number}[]} loadings
 * @param {boolean} signed
 * @param {number} [n]  features kept per end
 * @returns {{pos: {target: string, act: string|null}[], neg: {target: string, act: string|null}[]}}
 */
export function axisPoles(loadings, signed, n = POLE_ITEMS) {
  const pos = [], neg = [];
  for (const l of loadings) {
    const act = actionOf(l, signed);
    // A drug doing what most do to this feature moves along sign(w) x sign(mean).
    const side = l.w * (l.mean < 0 ? -1 : 1) > 0 ? pos : neg;
    if (side.length < n) side.push({ target: l.target, act });
    if (pos.length >= n && neg.length >= n) break;
  }
  return { pos, neg };
}

/**
 * One end's words: consecutive features sharing an action are grouped under one word,
 * "GABA-A, α2A boosted, H1 blocked".
 * @param {{target: string, act: string|null}[]} items
 * @param {(key: string) => string} nameOf
 * @param {Function} t  i18n lookup; "drugmap.act.<act>" templates take {list}
 * @returns {string}
 */
export function poleText(items, nameOf, t) {
  const runs = [];
  for (const it of items) {
    const last = runs[runs.length - 1];
    if (last && last.act === it.act) last.names.push(nameOf(it.target));
    else runs.push({ act: it.act, names: [nameOf(it.target)] });
  }
  return runs.map((r) => (r.act ? t(`drugmap.act.${r.act}`, { list: r.names.join(", ") }) : r.names.join(", ")))
    .join(", ") || "-";
}

/**
 * The caption, "PC2 (25% of variance): ↑ GABA-A boosted, H1 blocked · ↓ orexin blocked".
 * PC1 is the horizontal axis (→ / ←), PC2 the vertical one (↑ / ↓).
 * @param {{share: number, loadings: object[]}} ax
 * @param {number} i  0 for PC1, 1 for PC2
 * @param {{signed: boolean, nameOf: (key: string) => string, t: Function}} ctx
 * @returns {string}
 */
export function axisCaption(ax, i, { signed, nameOf, t }) {
  const { pos, neg } = axisPoles(ax.loadings, signed);
  const [up, down] = i ? ["↑", "↓"] : ["→", "←"];
  return t("drugmap.axis", {
    n: i + 1, share: Math.round(ax.share * 100), up, down,
    pos: poleText(pos, nameOf, t), neg: poleText(neg, nameOf, t),
  });
}

/**
 * The hover: every loading, largest first, one per line, with what the drugs do to it.
 * "+0.45  Orexin receptors (OX1R/OX2R): mostly blocked"
 * @param {{loadings: object[]}} ax
 * @param {number} i
 * @param {{signed: boolean, nameOf: (key: string) => string, t: Function}} ctx
 * @returns {string}
 */
export function axisTooltip(ax, i, { signed, nameOf, t }) {
  const lines = ax.loadings.map((l) => {
    const act = actionOf(l, signed);
    const w = `${l.w > 0 ? "+" : "−"}${Math.abs(l.w).toFixed(2)}`;
    return act ? t("drugmap.axisTipRowAct", { w, name: nameOf(l.target), act: t(`drugmap.actTip.${act}`) })
      : t("drugmap.axisTipRow", { w, name: nameOf(l.target) });
  });
  return [t(signed ? "drugmap.axisTipSigned" : "drugmap.axisTip", { n: i + 1 }), ...lines].join("\n");
}
