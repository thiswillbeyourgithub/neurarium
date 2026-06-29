// SDF worker pool: meshes a batch of `sdf` shape specs across a small pool of
// Web Workers (js/sdf-worker.js), so the brain's SDF geometry is built off the
// main thread at load instead of freezing it for ~2s.
//
// Graceful degradation, always: if module workers are unavailable (old browser,
// file:// origin, CSP) or a worker errors on a spec, that spec is meshed
// SYNCHRONOUSLY on the main thread instead (buildSdfGeometry). So the brain always
// renders; the worker pool is a pure performance path, never a correctness one.

import { buildSdfGeometry, geometryFromArrays } from "./sdf.js";
import { gradientNoise, fractalNoise } from "./noise.js";

const SYNC_DEPS = { noise3d: gradientNoise, fractalNoise };

/**
 * @param {object} [opts]
 * @param {number} [opts.size]  worker count (default: cores - 1, clamped 2..6).
 * @returns {{ meshAll(items:Array<{id:string, spec:object}>, onItem?:(id:string,done:number,total:number)=>void): Promise<Map<string, THREE.BufferGeometry>>, dispose():void }}
 */
export function createSdfPool(opts = {}) {
  /** @type {Array<{w:Worker, busy:boolean, jobId:number}>|false|null} */
  let pool = null; // null = not yet built, false = unusable (sync fallback)
  let nextId = 1;
  const pending = new Map(); // jobId -> { resolve, reject }
  const queue = []; // { jobId, spec }

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
      slot.w.postMessage({ id: job.jobId, spec: job.spec });
    }
  }

  function onMessage(slot, data) {
    slot.busy = false;
    slot.jobId = 0;
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
    const p = slot.jobId && pending.get(slot.jobId);
    if (p) {
      pending.delete(slot.jobId);
      p.reject(new Error("sdf worker error"));
    }
    slot.busy = false;
    slot.jobId = 0;
    pump();
  }

  function meshOne(spec) {
    if (!build()) return Promise.reject(new Error("no pool")); // -> sync fallback
    const jobId = nextId++;
    return new Promise((resolve, reject) => {
      pending.set(jobId, { resolve, reject });
      queue.push({ jobId, spec });
      pump();
    });
  }

  async function meshAll(items, onItem = null) {
    const out = new Map();
    if (!items.length) return out;
    let done = 0;
    const total = items.length;
    await Promise.all(items.map(async ({ id, spec }) => {
      try {
        out.set(id, await meshOne(spec));
      } catch {
        // Worker path failed for this spec: mesh it here so the brain is whole.
        out.set(id, buildSdfGeometry(spec, SYNC_DEPS));
      }
      onItem?.(id, (done += 1), total); // drive the startup loading bar
    }));
    return out;
  }

  function dispose() {
    if (Array.isArray(pool)) for (const slot of pool) slot.w.terminate();
    pool = null;
    pending.clear();
    queue.length = 0;
  }

  return { meshAll, dispose };
}
