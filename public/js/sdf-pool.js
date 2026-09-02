// SDF worker pool: meshes a batch of `sdf` shape specs across a small pool of
// Web Workers (js/sdf-worker.js), so the brain's SDF geometry is built off the
// main thread at load instead of freezing it for ~2s.
//
// Graceful degradation, always: if module workers are unavailable (old browser,
// file:// origin, CSP) or a worker errors on a spec, that spec is meshed
// SYNCHRONOUSLY on the main thread instead (buildSdfGeometry). So the brain always
// renders; the worker pool is a pure performance path, never a correctness one.

import { buildSdfGeometry, geometryFromArrays } from "./sdf.js";
import { estimateSdfCost } from "./sdf-core.js";
import { gradientNoise, fractalNoise } from "./noise.js";

const SYNC_DEPS = { noise3d: gradientNoise, fractalNoise };

/**
 * @param {object} [opts]
 * @param {number} [opts.size]  worker count (default: cores - 1, clamped 2..6).
 * @returns {{ meshAll(items:Array<{id:string, spec:object}>, onProgress?:(p:{id:string|null,done:number,total:number,frac:number})=>void, adjustSpec?:(spec:object)=>object): Promise<Map<string, THREE.BufferGeometry>>, dispose():void }}
 */
export function createSdfPool(opts = {}) {
  /** @type {Array<{w:Worker, busy:boolean, jobId:number}>|false|null} */
  let pool = null; // null = not yet built, false = unusable (sync fallback)
  let nextId = 1;
  const pending = new Map(); // jobId -> { resolve, reject }
  const queue = []; // { jobId, id, spec, cost }

  // Progress bookkeeping for the whole batch, shared by pump/onMessage (which sit
  // outside meshAll). `frac` is COST-weighted, not done/total: it keeps creeping
  // while a single big structure (hippocampus at 112^3) grinds on a slow phone
  // instead of standing still between two whole-item ticks, AND it stays honest
  // when the batch is meshed cheapest-first (see js/sdf-quality.js), where 40 of
  // 46 items done can still be a minority of the actual work.
  let report = null; // set by meshAll: (id|null) => void
  let adjustSpec = null; // set by meshAll: (spec) => spec, the quality budget
  const itemFrac = new Map(); // jobId -> 0..1
  const itemCost = new Map(); // jobId -> grid samples, the progress weight

  function build() {
    if (pool !== null) return pool;
    try {
      const cores = (typeof navigator !== "undefined" && navigator.hardwareConcurrency) || 4;
      const n = opts.size || Math.max(2, Math.min(cores - 1, 6));
      pool = [];
      for (let i = 0; i < n; i++) {
        const w = new Worker(new URL("./sdf-worker.js", import.meta.url), { type: "module" });
        const slot = { w, busy: false, jobId: 0 };
        w.onmessage = (e) => onMessage(slot, e.data);
        w.onerror = (e) => onWorkerError(slot, e);
        pool.push(slot);
      }
    } catch (err) {
      console.warn("sdf-pool: Web Workers unavailable; meshing on the main thread", err);
      pool = false;
    }
    return pool;
  }

  function pump() {
    if (!pool) return;
    for (const slot of pool) {
      if (slot.busy || queue.length === 0) continue;
      const job = queue.shift();
      slot.busy = true;
      slot.jobId = job.jobId;
      // Adjusted at DISPATCH, not at enqueue: that is the last moment before the
      // work is committed, so the decision sees every measurement taken so far
      // (js/sdf-quality.js decides mid-batch whether the rest must be coarser).
      const spec = adjustSpec ? adjustSpec(job.spec) : job.spec;
      slot.w.postMessage({ id: job.jobId, spec });
      report?.(job.id); // name the structure being built, not the last one finished
    }
  }

  function onMessage(slot, data) {
    // A `progress` message is a mid-mesh tick: the job is still running, so the
    // slot stays busy and nothing is resolved.
    if (data.progress !== undefined) {
      itemFrac.set(data.id, data.progress);
      report?.(null);
      return;
    }
    slot.busy = false;
    slot.jobId = 0;
    itemFrac.delete(data.id); // done: `done` counts it whole from here on
    const p = pending.get(data.id);
    if (p) {
      pending.delete(data.id);
      if (data.error) p.reject(new Error(data.error));
      else p.resolve(geometryFromArrays(data.positions, data.indices));
    }
    pump();
  }

  // A worker-level error (parse/import failure, crash) rejects the in-flight job;
  // the caller's per-spec catch meshes it synchronously. The dead slot is left
  // !busy so the queue keeps draining through the survivors.
  function onWorkerError(slot, e) {
    console.warn("sdf-pool: worker error; that spec falls back to the main thread", e.message || e);
    itemFrac.delete(slot.jobId);
    const p = slot.jobId && pending.get(slot.jobId);
    if (p) {
      pending.delete(slot.jobId);
      p.reject(new Error("sdf worker error"));
    }
    slot.busy = false;
    slot.jobId = 0;
    pump();
  }

  function meshOne(id, spec, cost) {
    if (!build()) return Promise.reject(new Error("no pool")); // -> sync fallback
    const jobId = nextId++;
    itemCost.set(jobId, cost);
    return new Promise((resolve, reject) => {
      pending.set(jobId, { resolve, reject });
      queue.push({ jobId, id, spec });
      pump();
    });
  }

  async function meshAll(items, onProgress = null, adjust = null) {
    const out = new Map();
    if (!items.length) return out;
    let done = 0;
    let doneCost = 0;
    const total = items.length;
    itemFrac.clear();
    itemCost.clear();
    adjustSpec = adjust;
    // Priced ONCE from the authored spec, so the weights (and hence the bar) stay
    // fixed even if `adjustSpec` later coarsens some of them; a degraded batch
    // then simply finishes ahead of its own bar rather than rewriting history.
    const costs = items.map((it) => estimateSdfCost(it.spec));
    const totalCost = costs.reduce((a, b) => a + b, 0) || 1;
    // `id` names the structure to caption: the one just dispatched (several are in
    // flight at once), or null on a mid-mesh tick, which leaves the caller's name
    // standing. `done` counts finished items for the "(n/total)" readout, while
    // `frac` (which includes the in-flight fractions) drives the bar itself.
    let lastId = items[0].id;
    report = onProgress
      ? (id) => {
          if (id) lastId = id;
          // A finished item is counted whole by `doneCost` and its itemFrac entry
          // is dropped on completion, so the two never double-count.
          let sum = doneCost;
          for (const [jobId, f] of itemFrac) sum += f * (itemCost.get(jobId) || 0);
          onProgress({ id: lastId, done, total, frac: Math.min(1, sum / totalCost) });
        }
      : null;
    await Promise.all(items.map(async ({ id, spec }, i) => {
      try {
        out.set(id, await meshOne(id, spec, costs[i]));
      } catch {
        // Worker path failed for this spec: mesh it here so the brain is whole.
        // Degradation applies on this path too, else a fallback would be the one
        // spec that ignores the budget, on the very device that needed it.
        out.set(id, buildSdfGeometry(adjustSpec ? adjustSpec(spec) : spec, SYNC_DEPS));
      }
      done += 1;
      doneCost += costs[i];
      report?.(id);
    }));
    report = null;
    adjustSpec = null;
    return out;
  }

  function dispose() {
    if (Array.isArray(pool)) for (const slot of pool) slot.w.terminate();
    pool = null;
    pending.clear();
    queue.length = 0;
    itemFrac.clear();
    itemCost.clear();
    report = null;
    adjustSpec = null;
  }

  return { meshAll, dispose };
}
