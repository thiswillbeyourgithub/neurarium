// Load-time mesh budget: keeps the startup SDF meshing within a time budget on a
// slow device by MEASURING the machine rather than guessing from it.
//
// Why measure, not sniff: `hardwareConcurrency` / user-agent say nothing useful
// about a phone's real throughput (throttling, background load, a fast 4-core vs.
// a slow 8-core), and the field fill is the one workload we can price exactly (a
// grid sample is one SDF-tree walk, so `estimateSdfCost` is a real relative cost).
// So we mesh the CHEAPEST structures first, watch how fast they actually go, and
// only then decide whether the expensive ones need to be coarser.
//
// The result is: a fast machine meshes everything at authored resolution and this
// module never fires; a slow one gets a whole brain in bounded time at slightly
// softer relief, and is TOLD so (the caller shows `notice`), because silently
// serving degraded geometry would misrepresent the atlas.
//
// three.js-free and DOM-free, so it is unit-testable and worker-safe.

import { estimateSdfCost } from "./sdf-core.js";

/** Meshing should be done inside this, or the remaining specs get coarser. */
const DEFAULT_BUDGET_MS = 7000;
/** Never scale a spec's resolution below this: past it the lobes read as blobs. */
const DEFAULT_MIN_SCALE = 0.55;
/**
 * Startup cost the rate must NOT be blamed for: booting 6 module workers (each
 * parsing sdf-core + noise in its own realm) is a fixed price paid once, so a rate
 * measured from t0 reads far too pessimistic and would coarsen a perfectly fast
 * machine. Past this, the throughput measurement is re-anchored (see `note`).
 */
const WARMUP_MS = 600;
/** Minimum span of the anchored window before its rate is trusted. */
const SAMPLE_MS = 400;
const SAMPLE_FRAC = 0.05;
/**
 * Only act on a CLEAR overshoot. The projection is a straight-line extrapolation
 * over a workload whose per-sample cost varies by shape, so a slim overrun is
 * inside the noise; degrading on that would trade real detail for nothing.
 */
const OVERSHOOT = 1.25;

/**
 * @param {object} [opts]
 * @param {number} [opts.budgetMs]  target wall time for the whole meshing phase.
 * @param {number} [opts.minScale]  floor on the resolution scale factor.
 * @param {() => number} [opts.now]  clock injection (tests).
 * @returns {{
 *   order(items: Array<{id:string, spec:object}>): Array<{id:string, spec:object}>,
 *   note(frac: number): void,
 *   adjust(spec: object): object,
 *   readonly degraded: boolean,
 *   readonly scale: number,
 * }}
 */
export function createMeshBudget(opts = {}) {
  const budgetMs = opts.budgetMs ?? DEFAULT_BUDGET_MS;
  const minScale = opts.minScale ?? DEFAULT_MIN_SCALE;
  const now = opts.now ?? (() => (typeof performance !== "undefined" ? performance.now() : Date.now()));

  let totalCost = 0;
  let startedAt = 0;
  let scale = 1; // 1 = authored resolution, < 1 = degraded
  // The measurement window, re-anchored once warmup is past (see WARMUP_MS).
  let anchorAt = 0;
  let anchorFrac = -1; // < 0 = not anchored yet

  /**
   * Cheapest first. Two reasons, both load-bearing: the budget needs a cheap
   * MEASUREMENT before it can judge the machine (so the small nuclei act as the
   * probe), and if it does have to degrade, the structures already meshed are the
   * small ones, so the detail that gets dropped is on shapes still to come rather
   * than retroactively lost. Sorting is stable on cost ties via the id, so a
   * reload meshes in the same order and the caption sequence is reproducible.
   */
  function order(items) {
    const priced = items.map((it) => ({ it, cost: estimateSdfCost(it.spec) }));
    totalCost = priced.reduce((s, p) => s + p.cost, 0);
    priced.sort((a, b) => a.cost - b.cost || (a.it.id < b.it.id ? -1 : 1));
    startedAt = now();
    return priced.map((p) => p.it);
  }

  /**
   * Feed the pool's cost-weighted completion fraction back in. From it and the
   * elapsed time we get the machine's real throughput, hence a projection of the
   * remaining work; if that overruns the budget, pick the scale that fits.
   * @param {number} frac  0..1 of the total cost done (in-flight fractions included).
   */
  function note(frac) {
    if (!totalCost || frac <= 0) return;
    const t = now();
    const elapsed = t - startedAt;
    if (elapsed < WARMUP_MS) return; // still paying worker startup; measures nothing
    if (anchorFrac < 0) { anchorAt = t; anchorFrac = frac; return; } // start the window

    const spanMs = t - anchorAt;
    const spanFrac = frac - anchorFrac;
    if (spanMs < SAMPLE_MS || spanFrac < SAMPLE_FRAC) return; // too small to trust

    const remaining = 1 - frac;
    if (remaining <= 0) return;
    // Rate over the anchored window, NOT since t0: that keeps the one-off worker
    // boot out of the throughput figure, which is what made a fast machine look
    // slow enough to degrade. Throughput reflects whatever scale has run so far,
    // so projecting the rest at authored resolution can only over-estimate the
    // time, never under: the conservative direction.
    const projected = (spanMs / spanFrac) * remaining;
    if (elapsed + projected <= budgetMs * OVERSHOOT) return;
    // Cost goes as the cube of the resolution scale (all three axes shrink), so
    // fitting `projected` into the time left wants the cube root of the ratio.
    const left = Math.max(budgetMs - elapsed, budgetMs * 0.25); // never demand the impossible
    const want = Math.cbrt(left / projected);
    // Monotonic: only ever coarsen. Re-upgrading mid-load would make neighbouring
    // structures flip detail on a rate blip, which reads as a glitch, not a fix.
    scale = Math.max(minScale, Math.min(scale, want));
  }

  /**
   * Called by the pool just before a spec is handed to a worker, so the decision
   * uses every measurement taken up to that moment. Returns the spec untouched
   * while undegraded, so the fast path allocates nothing.
   * @param {object} spec
   * @returns {object}
   */
  function adjust(spec) {
    if (scale >= 1) return spec;
    const res = spec.resolution;
    if (Array.isArray(res)) {
      return { ...spec, resolution: res.map((n) => Math.round(n * scale)) };
    }
    return { ...spec, resolution: Math.round((res || 64) * scale) };
  }

  return {
    order,
    note,
    adjust,
    get degraded() { return scale < 1; },
    get scale() { return scale; },
  };
}
