// Ki-derived weights of one binding (dot-cloud engagement, share of a system's
// tone) and a drug's indicative tone per transmitter system. Pure, node-testable.

const AFFINITY_DEFAULT = 0.55;
/**
 * Relative engagement of one binding from its measured Ki (NOT an effect size):
 * 0.35 at Ki >= 1 uM, rising with pKi to 1 at Ki <= 0.1 nM; AFFINITY_DEFAULT without
 * a Ki. Weighs the dot cloud and the binding's share of its system's tone.
 * @param {{median:number}|null} ki
 */
export function affinityWeightOf(ki) {
  const t = kiRamp(ki);
  return t === null ? AFFINITY_DEFAULT : 0.35 + 0.65 * t;
}

// pKi ramp shared by both weights: 0 at Ki >= 1 uM, 1 at Ki <= 0.1 nM, null without a Ki.
function kiRamp(ki) {
  if (!ki || !(ki.median > 0)) return null;
  const pKi = 9 - Math.log10(ki.median); // median is in nM
  return Math.max(0, Math.min(1, (pKi - 6) / 4));
}

const TONE_WEIGHT_NO_KI = 0.5;
/**
 * A binding's weight in its system's indicative tone: the bare pKi ramp, 0 at
 * Ki >= 1 uM up to 1 at Ki <= 0.1 nM, TONE_WEIGHT_NO_KI (a 10 nM binding) without a
 * Ki. No floor, unlike affinityWeightOf (whose floor keeps a weak binding's dots
 * visible): with one, several micromolar hits summed past a sub-nanomolar one.
 * @param {{median:number}|null} ki
 */
export function toneWeightOf(ki) {
  const t = kiRamp(ki);
  return t === null ? TONE_WEIGHT_NO_KI : t;
}

/**
 * A drug's indicative tone per transmitter system (the "Pharmacodynamics: net neurotransmission"
 * section and the flow overlay): every tone-setting binding adds
 * `toneSign * toneFactor * toneWeight` to its system's sum; postsynaptic receptors carry
 * toneSign 0 and add nothing. A zero sum drops the system (opposing bindings cancel).
 * @param {object[]} bindings resolved bindings ({flowKind, toneSign, toneFactor, toneWeight})
 * @returns {Object<string, {direction:number, weight:number, sum:number,
 *   terms:object[]}>} per kind: sign of the sum, |sum| capped at 1, the raw sum, and
 *   the bindings that make it up (in binding order)
 */
export function toneBySystem(bindings) {
  const acc = new Map();
  for (const b of bindings) {
    if (!b.flowKind || !b.toneSign) continue;
    const e = acc.get(b.flowKind) || { sum: 0, terms: [] };
    e.sum += b.toneSign * (b.toneFactor ?? 1) * b.toneWeight;
    e.terms.push(b);
    acc.set(b.flowKind, e);
  }
  const out = {};
  for (const [kind, { sum, terms }] of acc) {
    if (!sum) continue;
    out[kind] = { direction: sum > 0 ? 1 : -1, weight: Math.min(1, Math.abs(sum)), sum, terms };
  }
  return out;
}
