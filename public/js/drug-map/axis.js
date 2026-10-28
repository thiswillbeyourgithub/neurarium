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

/** Arch score (%) from which the caption warns that one axis mostly bends the other. A
 * rough rule: past about a third of an axis explained by a parabola of the other, reading
 * the two as independent directions misleads. */
export const ARCH_HIGH = 30;

/**
 * The arch ("horseshoe") score: how much one axis is a bent copy of the other, i.e. the
 * better R² of the least-squares fits PC2 ~ a + b PC1 + c PC1² and PC1 ~ a + b PC2 + c PC2².
 * PCA makes the two axes linearly uncorrelated, so whatever a fit explains is curvature: a
 * long gradient folded into an arch, whose two ends bend towards each other. Both ways,
 * since the gradient need not be PC1: an arch opening sideways ("<", both ends on one side)
 * is PC1 bent by PC2. 0 = no arch, 1 = every drug on one parabola.
 * e.g. PC1 [-2,-1,0,1,2], PC2 [2,-1,-2,-1,2] -> ≈ 1.
 * @param {Iterable<{x: number, y: number}>} points
 * @returns {number|null}  null below 4 points or with a flat axis
 */
export function archScore(points) {
  const pts = [...points];
  const a = parabolaR2(pts), b = parabolaR2(pts.map(({ x, y }) => ({ x: y, y: x })));
  return a === null ? b : b === null ? a : Math.max(a, b);
}

// R² of y ~ a + b x + c x² (see archScore), null when it cannot be fitted.
function parabolaR2(pts) {
  const n = pts.length;
  if (n < 4) return null;
  // Normal equations of y = a + b x + c x², solved by Cramer's rule (3 x 3).
  let s1 = 0, s2 = 0, s3 = 0, s4 = 0, t0 = 0, t1 = 0, t2 = 0, my = 0;
  for (const { x, y } of pts) {
    const x2 = x * x;
    s1 += x; s2 += x2; s3 += x2 * x; s4 += x2 * x2;
    t0 += y; t1 += x * y; t2 += x2 * y;
  }
  my = t0 / n;
  const det3 = (m) => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
    - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
    + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  const A = [[n, s1, s2], [s1, s2, s3], [s2, s3, s4]];
  const d = det3(A);
  if (Math.abs(d) < 1e-12) return null;
  const col = (i) => A.map((r, k) => r.map((v, j) => (j === i ? [t0, t1, t2][k] : v)));
  const [a, b, c] = [0, 1, 2].map((i) => det3(col(i)) / d);
  let ssRes = 0, ssTot = 0;
  for (const { x, y } of pts) {
    ssRes += (y - (a + b * x + c * x * x)) ** 2;
    ssTot += (y - my) ** 2;
  }
  return ssTot > 0 ? Math.max(0, 1 - ssRes / ssTot) : null;
}
