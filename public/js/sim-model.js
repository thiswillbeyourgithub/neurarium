// The drug-combination simulation model: pure functions, no DOM, no three.js, so
// the maths can be tested on its own (node --test, tools/tests/sim_model.test.mjs)
// and the tab (js/simulation.js) only draws what comes out of here.
//
// WHAT THIS IS FOR, both directions of one question about receptor occupancy:
//   forward, what a combination of drugs does to the receptors ("these three drugs
//   at this ratio, which receptors end up engaged and which way"); and backward,
//   which combination would produce a wanted profile ("I want this much of these
//   receptors and none of those, what should I take"), the second being the same
//   matrix solved the other way (`solveCombination`).
//
// WHAT IT ACTUALLY COMPUTES IS NOT OCCUPANCY, and point 5 below says what it would
// take to make it so. It is an engagement INDEX: a signed, ratio-weighted potency
// that ranks receptors against each other and moves the right way with dose, but is
// not a percentage of receptors bound and must never be read as one.
//
// What is simulated, and what is deliberately NOT (every shortcut below is also
// listed for the visitor in the tab's warnings box, keyed `sim.warn.*`, which says
// in its own first line that the list is not exhaustive):
//
//   1. Pharmacokinetics. Only two durations are in the data (no dose, no
//      bioavailability, no protein binding, no brain penetration), so each ligand gets
//      a one-compartment oral single-dose curve (Bateman), normalized to a peak of 1
//      and scaled by the ratio the visitor set: an elimination half-life sets how it
//      falls, and the drug's own sourced time-to-peak (`drug.tmax`, kind `drug_tmax`)
//      sets how it rises. A drug for which no corpus states a peak keeps the single
//      assumed one (`TMAX_HOURS`), so the two populations are mixed on one plot and
//      only the T½ tells them apart. Either duration's range (`hours` + `hours_max`)
//      is collapsed to its midpoint. An active metabolite is formed by the parent's
//      elimination (its absorption rate = the parent's ke) and cleared by its own T½,
//      with a formed fraction of 1 (unknown in the data).
//
//   2. Receptor engagement. Per (ligand, target) the potency is 1/Ki (nM^-1) from the
//      measured median Ki, signed by the binding's net effect: boost +1, block -1,
//      modulate +0.5 (a partial agonist raises tone at a quiet receptor and lowers it
//      at a driven one, so the midpoint is the honest guess). A direction-less
//      (affinity_only) binding is NOT signed: it goes into a separate "unknown" band so
//      the visitor sees an occupied receptor whose effect nobody sourced, instead of
//      a silently missing one. A directed binding with no measured Ki is kept at an
//      assumed pKi (`ASSUMED_PKI`, i.e. 100 nM) and flagged.
//
//   3. Combination. Potencies add linearly across ligands (ratio-weighted), which is
//      what makes the inverse problem linear: profile = A·x with A the target×drug
//      matrix and x the ratio vector, so "which drugs give me this profile" is a
//      non-negative least squares solve (`solveCombination`). Competition between
//      ligands at one receptor, efficacy, tolerance and every drug-drug interaction
//      are ignored (the enzyme-sharing ones are at least flagged, see `pkFlags`).
//
//   4. Display axis. Values span 6 orders of magnitude, so the bar height is a
//      symmetric log: sign(v)·log10(1 + |v|/P_FLOOR), with P_FLOOR the potency of a
//      10 µM Ki (the PDSP cut-off below which an assay is dropped as inactive). Ki
//      1 nM at ratio 1 then reads 4, and multiplying a ratio by 10 adds ~1.
//
//   5. Why this is not occupancy, and what would make it so. Occupancy at one
//      receptor is a saturating function of the CONCENTRATION AT THAT RECEPTOR, and
//      with several ligands a competitive one:
//
//          occupancy_i = (C_i/Ki_i) / (1 + Σ_j C_j/Ki_j)
//
//      Ki gives the denominators of those ratios and nothing else, so a Ki without a
//      C is a potency, never a percentage: the missing half is entirely
//      pharmacokinetic, and it is per drug, not per receptor. Reaching a real C at
//      the receptor needs, on top of the T½ this dataset has: the DOSE actually taken
//      and the molar mass to put it in nM, the oral bioavailability F, the volume of
//      distribution Vd (dose + F + Vd is what sets the plasma level at all), the
//      plasma free fraction fu (bound drug binds no receptor), the unbound
//      brain-to-plasma ratio Kp,uu (the blood-brain barrier and its efflux pumps
//      make this vary ~100-fold between CNS drugs). Tmax, the one piece of that chain
//      that a corpus does state, is now sourced per drug (point 1), which fixes the
//      SHAPE of the curve and nothing about its height. Two further
//      terms are not PK at all and would still be missing: the endogenous ligand a
//      drug competes with (dopamine at D2 is why an in-vivo occupancy never matches
//      an in-vitro Ki), and efficacy, since occupancy is not effect.
//
//      This is also why the potencies simply ADD in point 3 instead of competing: the
//      competitive form above is only meaningful once every C is on one real scale,
//      and it would break the linearity the inverse solve rests on. The index is the
//      honest thing to compute from a Ki alone. Adding the per-drug PK fields above
//      (a graded node kind each, sourced from the labels) is what would turn the
//      plot's unit from "index" into "% occupied"; until then the axis is deliberately
//      unitless and the caption says so.

export const TMAX_HOURS = 2; // assumed oral time-to-peak, for a drug with no sourced one
export const ASSUMED_PKI = 7; // a directed binding with no Ki: assumed 100 nM
export const P_FLOOR = 1e-4; // 1/Ki at 10 µM, the PDSP "inactive" cut-off
export const LN2 = Math.log(2);

// Net-effect -> sign. `modulate` covers partial agonists + allosteric modulators.
export const EFFECT_SIGN = { boost: 1, block: -1, modulate: 0.5 };

/** The signed direction of one resolved binding, or null when unknown. */
export function bindingSign(b) {
  if (!b || b.affinityOnly) return null;
  const s = EFFECT_SIGN[b.effect];
  return s === undefined ? null : s;
}

/** 1/Ki in nM^-1 from a resolved Ki, else the assumed potency (and a flag). */
export function bindingPotency(b) {
  const med = b && b.ki && b.ki.median;
  if (med > 0) return { p: 1 / med, assumed: false };
  return { p: Math.pow(10, ASSUMED_PKI - 9), assumed: true };
}

/** Symmetric log axis (see header, point 4). Inverse: `fromAxis`. */
export function toAxis(v) {
  return Math.sign(v) * Math.log10(1 + Math.abs(v) / P_FLOOR);
}
export function fromAxis(y) {
  return Math.sign(y) * P_FLOOR * (Math.pow(10, Math.abs(y)) - 1);
}

/**
 * A stored `{hours, hours_max?}` duration as a single number: the midpoint of a
 * range, null when absent. Used for both per-drug durations, which share that shape
 * (a T½ of "21-54 h" is 37.5 h here, a Tmax of "1-3 h" is 2 h).
 */
export function halfLifeHours(hl) {
  if (!hl || !(hl.hours > 0)) return null;
  return hl.hours_max > hl.hours ? (hl.hours + hl.hours_max) / 2 : hl.hours;
}

/**
 * The time-to-peak to draw a drug's rise with: its own sourced `tmax` where the
 * dataset has one, else the model-wide `TMAX_HOURS` assumption. Only ~30% of the
 * roster states a peak anywhere (see docs/SOURCING_GAPS.md), so the fallback is not
 * an edge case and the warnings box keeps saying so.
 */
export function tmaxHours(drug) {
  return halfLifeHours(drug && drug.tmax) || TMAX_HOURS;
}

/**
 * The absorption rate that puts a one-compartment curve's peak at `tmax` given
 * elimination rate `ke`. Tmax = ln(ka/ke)/(ka-ke) is monotonic decreasing in ka on
 * (ke, inf) and tends to 1/ke as ka -> ke, so a peak later than ~1.44·T½ is
 * unreachable: the peak is then clamped just under that bound (a very short-lived
 * drug simply peaks early). Bisection on log(ka).
 */
export function absorptionRate(ke, tmax) {
  const tCap = 0.99 / ke;
  const t = Math.min(tmax, tCap);
  let lo = Math.log(ke * 1.000001), hi = Math.log(ke * 1e6);
  for (let i = 0; i < 80; i++) {
    const mid = (lo + hi) / 2, ka = Math.exp(mid);
    const tm = Math.log(ka / ke) / (ka - ke);
    if (tm > t) lo = mid; else hi = mid;
  }
  return Math.exp((lo + hi) / 2);
}

/**
 * A normalized one-compartment curve: `{ka, ke, tmax, at(t)}` with at(tmax) = 1.
 * `ka` may be passed (a metabolite formed at the parent's ke); else derived from
 * `TMAX_HOURS`. Returns null when the half-life is unknown.
 */
export function pkCurve(halfLifeH, { ka = null, tmax = TMAX_HOURS } = {}) {
  if (!(halfLifeH > 0)) return null;
  const ke = LN2 / halfLifeH;
  let kA = ka;
  if (!(kA > 0)) kA = absorptionRate(ke, tmax);
  // Equal rates make the Bateman form 0/0; nudge apart (the limit is t·k·e^-kt).
  if (Math.abs(kA - ke) < 1e-9 * ke) kA = ke * 1.001;
  const raw = (t) => (t <= 0 ? 0 : Math.exp(-ke * t) - Math.exp(-kA * t));
  const tPeak = Math.log(kA / ke) / (kA - ke);
  const peak = raw(tPeak) || 1;
  return { ka: kA, ke, tmax: tPeak, at: (t) => raw(t) / peak };
}

/**
 * The ligands a chosen drug puts in circulation: itself plus (when `metabolites`)
 * each active metabolite with a T½. Each ligand: `{key, name, drug, metabolite?,
 * bindings, curve}` where `curve` may be null (no T½: the ligand still binds, it
 * just draws no PK line and weighs 1 at every time).
 */
export function ligandsOf(drug, { metabolites = true } = {}) {
  const tmax = tmaxHours(drug);
  const own = pkCurve(halfLifeHours(drug.halfLife), { tmax });
  const out = [{ key: drug.id, name: drug.name, drug, metabolite: null,
    bindings: drug.bindings || [], curve: own }];
  if (!metabolites) return out;
  for (const m of drug.metabolites || []) {
    const hl = halfLifeHours(m.halfLife);
    // A metabolite rides the parent's absorption where the parent draws a curve at
    // all; with no parent T½ there is no ke to borrow, so it falls back to the
    // parent's time-to-peak (the metabolite appears as the parent is absorbed).
    const curve = hl && own ? pkCurve(hl, { ka: own.ke })
      : hl ? pkCurve(hl, { tmax }) : null;
    out.push({ key: `${drug.id}/${m.name}`, name: m.name, drug, metabolite: m,
      bindings: m.bindings || [], curve });
  }
  return out;
}

/**
 * Fold one ligand's bindings into per-target accumulators.
 * `signed`/`unknown`: Map target -> potency sum (signed, resp. direction-less);
 * `flags`: assumed-Ki + unknown-direction notes for the warnings box.
 */
export function accumulate(ligand, weight, signed, unknown, flags) {
  for (const b of ligand.bindings) {
    if (!b || !b.target) continue;
    const { p, assumed } = bindingPotency(b);
    const s = bindingSign(b);
    if (s === null) {
      unknown.set(b.target, (unknown.get(b.target) || 0) + p * weight);
      flags.push({ kind: "unknownDirection", ligand: ligand.name, target: b.targetName || b.target });
      continue;
    }
    signed.set(b.target, (signed.get(b.target) || 0) + s * p * weight);
    if (assumed) flags.push({ kind: "assumedKi", ligand: ligand.name, target: b.targetName || b.target });
  }
}

/**
 * The receptor profile of a drug list at time `t` (hours after a shared dose; null
 * = every ligand at its own peak). `entries`: `[{drug, ratio}]`.
 * Returns `{rows: [{target, boost, block, unknown, perLigand}], flags}` where
 * boost/block/unknown are potency sums (nM^-1, ratio-weighted) and `perLigand` the
 * signed contribution of each ligand key (for the per-drug colouring of a bar).
 * Rows with nothing engaged are dropped.
 */
export function receptorProfile(entries, { t = null, metabolites = true } = {}) {
  const boost = new Map(), block = new Map(), unknown = new Map();
  const per = new Map();
  const flags = [];
  for (const { drug, ratio } of entries) {
    for (const lig of ligandsOf(drug, { metabolites })) {
      const w = ratio * (t === null || !lig.curve ? 1 : lig.curve.at(t));
      if (!(w > 0)) continue;
      const signed = new Map();
      accumulate(lig, w, signed, unknown, flags);
      for (const [target, v] of signed) {
        (v > 0 ? boost : block).set(target, ((v > 0 ? boost : block).get(target) || 0) + v);
        if (!per.has(target)) per.set(target, new Map());
        per.get(target).set(lig.key, (per.get(target).get(lig.key) || 0) + v);
      }
    }
  }
  const targets = new Set([...boost.keys(), ...block.keys(), ...unknown.keys()]);
  const rows = [...targets].map((target) => ({
    target,
    boost: boost.get(target) || 0,
    block: block.get(target) || 0,
    unknown: unknown.get(target) || 0,
    perLigand: per.get(target) || new Map(),
  }));
  return { rows, flags };
}

/**
 * Enzyme-sharing flags between the chosen drugs, the one drug-drug interaction the
 * dataset can see: two drugs cleared by the same isoform, or one drug an
 * inhibitor/inducer of an isoform that clears another. Reads each drug's resolved
 * `enzymes` rows (`{enzyme, role}`; role substrate/inhibitor/inducer).
 */
export function pkFlags(entries) {
  const out = [];
  const drugs = entries.map((e) => e.drug);
  for (let i = 0; i < drugs.length; i++) {
    for (let j = 0; j < drugs.length; j++) {
      if (i === j) continue;
      const a = drugs[i], b = drugs[j];
      for (const ra of a.enzymes || []) {
        for (const rb of b.enzymes || []) {
          if (ra.enzyme !== rb.enzyme) continue;
          if (ra.role === "substrate" && rb.role === "substrate" && i < j) {
            out.push({ kind: "sharedSubstrate", a: a.name, b: b.name, enzyme: ra.enzyme });
          } else if (ra.role !== "substrate" && rb.role === "substrate") {
            out.push({ kind: ra.role === "inhibitor" ? "inhibits" : "induces",
              a: a.name, b: b.name, enzyme: ra.enzyme });
          }
        }
      }
    }
  }
  return out;
}

/**
 * Build the signed potency matrix over `targets` (row order) for every candidate
 * drug, at peak (each ligand weight 1, metabolites per the toggle). Returns
 * `{cols: [{drug, vec: Float64Array}]}`; a drug engaging none of the rows is
 * skipped. Direction-less bindings are not in the matrix (see header, point 2).
 */
export function buildMatrix(candidates, targets, { metabolites = true } = {}) {
  const idx = new Map(targets.map((tg, i) => [tg, i]));
  const cols = [];
  for (const drug of candidates) {
    const vec = new Float64Array(targets.length);
    let any = false;
    for (const lig of ligandsOf(drug, { metabolites })) {
      for (const b of lig.bindings) {
        const i = idx.get(b && b.target);
        if (i === undefined) continue;
        const s = bindingSign(b);
        if (s === null) continue;
        vec[i] += s * bindingPotency(b).p;
        any = true;
      }
    }
    if (any) cols.push({ drug, vec });
  }
  return { cols };
}

/**
 * Lawson-Hanson non-negative least squares: argmin ||A x - y|| with x >= 0.
 * `A` is column-major (`cols[j]` a Float64Array of length m). Small (m ~ 60,
 * n ~ 300) so a dense active-set solve is instant. Returns Float64Array x.
 */
export function nnls(cols, y, { maxIter = null, tol = 1e-10 } = {}) {
  const n = cols.length, m = y.length;
  const x = new Float64Array(n);
  if (!n || !m) return x;
  const P = new Set();
  const w = new Float64Array(n);
  const residual = (xx) => {
    const r = Float64Array.from(y);
    for (let j = 0; j < n; j++) if (xx[j]) for (let i = 0; i < m; i++) r[i] -= cols[j][i] * xx[j];
    return r;
  };
  const gradient = (r) => { for (let j = 0; j < n; j++) { let s = 0; for (let i = 0; i < m; i++) s += cols[j][i] * r[i]; w[j] = s; } };
  // Unconstrained least squares restricted to the passive set, via normal equations
  // with a tiny ridge (columns can be near-collinear: two drugs with alike profiles).
  const lsq = () => {
    const ids = [...P];
    const k = ids.length;
    const G = Array.from({ length: k }, () => new Float64Array(k));
    const b = new Float64Array(k);
    for (let a = 0; a < k; a++) {
      const ca = cols[ids[a]];
      for (let c = a; c < k; c++) {
        const cc = cols[ids[c]];
        let s = 0; for (let i = 0; i < m; i++) s += ca[i] * cc[i];
        G[a][c] = s; G[c][a] = s;
      }
      let s = 0; for (let i = 0; i < m; i++) s += ca[i] * y[i];
      b[a] = s;
      G[a][a] += 1e-12 * (G[a][a] || 1);
    }
    // Gaussian elimination with partial pivoting.
    for (let a = 0; a < k; a++) {
      let piv = a;
      for (let r = a + 1; r < k; r++) if (Math.abs(G[r][a]) > Math.abs(G[piv][a])) piv = r;
      [G[a], G[piv]] = [G[piv], G[a]]; [b[a], b[piv]] = [b[piv], b[a]];
      const d = G[a][a] || 1e-300;
      for (let r = a + 1; r < k; r++) {
        const f = G[r][a] / d;
        if (!f) continue;
        for (let c = a; c < k; c++) G[r][c] -= f * G[a][c];
        b[r] -= f * b[a];
      }
    }
    const z = new Float64Array(n);
    for (let a = k - 1; a >= 0; a--) {
      let s = b[a];
      for (let c = a + 1; c < k; c++) s -= G[a][c] * z[ids[c]];
      z[ids[a]] = s / (G[a][a] || 1e-300);
    }
    return z;
  };
  const limit = maxIter || 3 * n;
  let iter = 0;
  gradient(residual(x));
  while (iter++ < limit) {
    let jmax = -1, wmax = tol;
    for (let j = 0; j < n; j++) if (!P.has(j) && w[j] > wmax) { wmax = w[j]; jmax = j; }
    if (jmax < 0) break;
    P.add(jmax);
    let z = lsq();
    // Inner loop: pull the step back until every passive coefficient is positive.
    let guard = 0;
    while (guard++ < n + 1) {
      let ok = true;
      for (const j of P) if (z[j] <= 0) { ok = false; break; }
      if (ok) break;
      let alpha = Infinity;
      for (const j of P) if (z[j] <= 0) { const a = x[j] / (x[j] - z[j]); if (a < alpha) alpha = a; }
      for (let j = 0; j < n; j++) x[j] += alpha * (z[j] - x[j]);
      for (const j of [...P]) if (x[j] <= tol) { P.delete(j); x[j] = 0; }
      z = lsq();
    }
    for (let j = 0; j < n; j++) x[j] = P.has(j) ? z[j] : 0;
    gradient(residual(x));
  }
  return x;
}

/**
 * The inverse problem: which candidate drugs, at which ratios, best reproduce a
 * target profile. `target`: Map target -> desired signed potency (linear, use
 * `fromAxis` on a slider value). `fixed`: `[{drug, ratio}]` already chosen, held
 * at their ratio (their contribution is part of the estimate, never re-fitted).
 * Options:
 *   `onlyListed`  fit only the rows the visitor set (else every target the
 *                 candidates engage is a row with a 0 target, penalizing off-target
 *                 engagement);
 *   `maxDrugs`    keep the strongest K coefficients and re-solve on them (NNLS is
 *                 sparse by nature but not capped).
 *
 * The visitor judges the fit on the log axis (`toAxis`), where a 100 nM hit on a
 * receptor meant to stay at 0 costs about as much as being 10× off on the main
 * target. A plain linear least squares gets that backwards (the 100 nM hit is
 * 0.01 nM^-1, invisible next to a 1 nM^-1 target), and relative weights get it
 * backwards the other way (a 0 target then weighs 10,000× a 1 nM one). So the
 * solve is iteratively reweighted: each row's weight is the secant slope of the
 * axis map between its target and the current estimate, i.e. the linear error is
 * rescaled to the axis-domain error it stands for, and NNLS is re-run until the
 * weights settle (a few rounds; each solve is milliseconds). Returns `{picks:
 * [{drug, ratio}], fit: 0..1 (1 - axis-domain relative residual), residual}`;
 * picks sorted by ratio desc.
 */
export function solveCombination(target, candidates, {
  fixed = [], onlyListed = true, maxDrugs = 3, metabolites = true,
} = {}) {
  const fixedIds = new Set(fixed.map((f) => f.drug.id));
  const pool = candidates.filter((d) => !fixedIds.has(d.id));
  const targets = [...target.keys()];
  if (!onlyListed) {
    const seen = new Set(targets);
    for (const d of [...pool, ...fixed.map((f) => f.drug)]) {
      for (const lig of ligandsOf(d, { metabolites })) {
        for (const b of lig.bindings) {
          if (b && b.target && bindingSign(b) !== null && !seen.has(b.target)) {
            seen.add(b.target); targets.push(b.target);
          }
        }
      }
    }
  }
  const m = targets.length;
  const yFull = new Float64Array(m);
  targets.forEach((tg, i) => { yFull[i] = target.get(tg) || 0; });
  // What the fixed drugs already provide, at their ratios.
  const base = new Float64Array(m);
  if (fixed.length) {
    const fm = buildMatrix(fixed.map((f) => f.drug), targets, { metabolites });
    for (const col of fm.cols) {
      const ratio = fixed.find((f) => f.drug === col.drug).ratio;
      for (let i = 0; i < m; i++) base[i] += ratio * col.vec[i];
    }
  }
  const y = yFull.map((v, i) => v - base[i]);
  const { cols } = buildMatrix(pool, targets, { metabolites });
  // Secant slope of toAxis between the target and an estimate (the derivative when
  // they coincide), so a linear residual is weighted into axis units.
  const slope = (v, est) => {
    const dv = v - est;
    if (Math.abs(dv) < 1e-15) return 1 / (Math.LN10 * (P_FLOOR + Math.abs(v)));
    return Math.abs(toAxis(v) - toAxis(est)) / Math.abs(dv);
  };
  const estimate = (subset, xs) => {
    const est = Float64Array.from(base);
    subset.forEach((c, j) => { if (xs[j]) for (let i = 0; i < m; i++) est[i] += c.vec[i] * xs[j]; });
    return est;
  };
  // A coefficient at floating-point noise (1e-9 of the largest) is a zero the
  // active-set solve did not quite reach; it must not surface as a "pick".
  const activeOf = (subset, xs) => {
    const xmax = Math.max(0, ...xs);
    return subset.map((c, j) => ({ c, x: xs[j] })).filter((e) => e.x > 1e-9 * xmax);
  };
  // Axis-domain fit of an estimate: 1 - ||axis(y) - axis(est)|| / ||axis(y)||.
  const fitOf = (est) => {
    let rn = 0, yn = 0;
    for (let i = 0; i < m; i++) {
      const a = toAxis(yFull[i]);
      rn += (a - toAxis(est[i])) ** 2; yn += a * a;
    }
    return { fit: Math.max(0, 1 - Math.sqrt(rn) / (Math.sqrt(yn) || 1)), residual: Math.sqrt(rn) };
  };
  const irls = (subset) => {
    // Start from the plain linear solve: starting from the slope AT the target
    // makes every 0-target row weigh ~4000 (the log map is steepest at zero) and
    // the iteration never leaves that corner. From the linear solution the
    // estimate is off zero, the secants are finite, and it settles in a few rounds.
    // The rounds can oscillate between two solutions, so the best axis-domain fit
    // seen is what is returned, not the last.
    let w = new Float64Array(m).fill(1);
    let best = null;
    for (let round = 0; round < 10; round++) {
      const xs = nnls(subset.map((c) => c.vec.map((v, i) => v * w[i])), y.map((v, i) => v * w[i]));
      const est = estimate(subset, xs);
      const f = fitOf(est);
      if (!best || f.fit > best.fit) best = { xs, ...f };
      const w2 = yFull.map((v, i) => slope(v, est[i]));
      let change = 0;
      for (let i = 0; i < m; i++) change = Math.max(change, Math.abs(w2[i] - w[i]) / (w[i] || 1));
      w = w2;
      if (change < 1e-3) break;
    }
    return best;
  };
  // Forward greedy selection: add the one candidate that most improves the fit,
  // re-fitting every ratio each time, up to `maxDrugs` (or the whole pool when 0).
  // Truncating a many-drug NNLS solution to K picks is much worse (a drug can carry
  // a huge coefficient for one minor row), and greedy is directly "what should I
  // add to my list next". Each candidate solve is a handful of columns, so the
  // whole search is a few hundred milliseconds at most.
  let chosen = [];
  let current = { xs: new Float64Array(0), ...fitOf(base) };
  const limit = maxDrugs > 0 ? maxDrugs : cols.length;
  while (chosen.length < limit) {
    let bestCand = null;
    for (const c of cols) {
      if (chosen.includes(c)) continue;
      const r = irls([...chosen, c]);
      if (!bestCand || r.fit > bestCand.r.fit) bestCand = { c, r };
    }
    // Stop when nothing helps any more (a fit already at 1, or only noise left).
    if (!bestCand || bestCand.r.fit <= current.fit + 1e-4) break;
    chosen = [...chosen, bestCand.c];
    current = bestCand.r;
  }
  const active = activeOf(chosen, current.xs);
  // A pick can pull AGAINST a wish: when the fixed drugs already overshoot a
  // receptor, least squares adds an opposing ligand to come back down to it. That
  // is arithmetically right and reads wrong as a recommendation, so each pick names
  // the wished targets it opposes and the tab says so beside it.
  const opposesOf = (vec) => targets.filter((tg, i) =>
    target.has(tg) && yFull[i] !== 0 && Math.sign(vec[i]) === -Math.sign(yFull[i]));
  return {
    picks: active.map((e) => ({ drug: e.c.drug, ratio: e.x, opposes: opposesOf(e.c.vec) }))
      .sort((a, b) => b.ratio - a.ratio),
    fit: current.fit,
    residual: current.residual,
    // How many receptor rows the fit was judged over: a 100% over one wished row
    // is a much weaker statement than 80% over twenty.
    rows: m,
  };
}
