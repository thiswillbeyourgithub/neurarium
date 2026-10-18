// Region meshes at load: baked geometry first (tools/bake_meshes.mjs), the SDF
// worker pool for whatever the bake does not cover, the cheap shapes meshed
// synchronously. Drives the loading bar's second half.

import { buildStructureMesh } from "../shapes.js";
import { createSdfPool } from "../sdf-pool.js";
import { geometryFromArrays } from "../sdf.js";
import { loadBakedMeshes } from "../baked-meshes.js";
import { createMeshBudget } from "../sdf-quality.js";

const { t } = window.__I18N__;

/**
 * Build every structure's mesh and add it to the scene.
 * @param {{data: object, scene: object, loading: object}} deps
 * @returns {Promise<{meshes: object[], meshById: Map<string, object>}>}
 */
export async function buildStructureMeshes({ data, scene, loading }) {
  // Mesh the SDF shapes off the main thread (a small Web Worker pool), so
  // assembling the brain's ~40 SDF meshes at load never freezes the page. The
  // cheap shapes (blob/curve/composite) stay synchronous. The pool falls back to
  // synchronous meshing per-spec if workers are unavailable (see js/sdf-pool.js),
  // so the brain always renders; this is a pure performance path.
  // One job per DISTINCT spec, not per structure: a symmetric structure's two
  // hemispheres share one shape file (js/data.js dedupes the fetch, so the twins
  // hold the very same spec object), and the left is the right's geometry flipped
  // by `mirrorGeometryX`, not a different solid. Meshing both sides re-ran an
  // identical marching-cubes pass for 20 of the 46 structures: 44% of the field
  // samples at load, spent to produce a duplicate. The twin gets a `clone()`
  // below, since `buildStructureMesh` mirrors in place.
  const sdfBySpec = new Map(); // spec object -> the id that carries its geometry
  const sdfItems = [];
  for (const s of data.structures) {
    if (!s.shape || s.shape.type !== "sdf") continue;
    if (sdfBySpec.has(s.shape)) continue;
    sdfBySpec.set(s.shape, s.id);
    sdfItems.push({ id: s.id, spec: s.shape, shapeFile: s.shape_file });
  }

  // Baked geometry first (tools/bake_meshes.mjs): downloading the meshes replaces
  // ~3.8s of worker meshing with a decode of a few tens of ms, and the download is
  // paid once (sw.js then revalidates it to a bodyless 304) where the meshing was
  // paid on every single load. Whatever the bake does not cover falls through to
  // the runtime mesher below, so a tree that was never baked still runs.
  const sdfGeoms = new Map();
  const baked = await loadBakedMeshes("data", ({ loaded, total }) => {
    loading.setProgress(0.5 + 0.4 * (total ? loaded / total : 1),
      t("loading.geometry", { done: loaded, total }));
  });
  const toMesh = [];
  for (const item of sdfItems) {
    const mesh = baked.get(item.shapeFile);
    if (mesh) sdfGeoms.set(item.id, geometryFromArrays(mesh.positions, mesh.indices));
    else toMesh.push(item);
  }

  // Runtime meshing, for whatever the bake did not supply. On a fully baked build
  // this list is empty and neither the worker pool nor the quality budget is ever
  // constructed; it is the fallback path, not the normal one.
  if (toMesh.length) {
    if (toMesh.length !== sdfItems.length) {
      console.info(`baked meshes: ${toMesh.length} of ${sdfItems.length} structure(s) ` +
        "missing from the bake; meshing those in the browser");
    }
    const pool = createSdfPool();
    // Mesh cheapest-first under a wall-time budget: the small nuclei double as a
    // throughput probe, and if the machine turns out to be too slow to finish the
    // heavy lobes at authored resolution, the budget coarsens the ones still
    // queued (see js/sdf-quality.js). Measured, never sniffed from the user agent.
    const budget = createMeshBudget();
    try {
      const meshed = await pool.meshAll(
        budget.order(toMesh),
        ({ id, done, total, frac }) => {
          budget.note(frac); // feed the throughput measurement back to the budget
          // `frac` is cost-weighted and includes the in-flight structures' own
          // progress, so on a slow phone the bar keeps moving through a single
          // heavy mesh; the "(n/total)" counter says how far along the batch is,
          // so a long pause still reads as progress rather than a freeze.
          const name = data.byId.get(id)?.base_name || id;
          loading.setProgress(0.5 + 0.45 * frac, t("loading.meshing", { name, done, total }));
          if (budget.degraded) loading.notice(t("loading.reducedQuality"));
        },
        budget.adjust,
      );
      for (const [id, geom] of meshed) sdfGeoms.set(id, geom);
    } catch (err) {
      console.warn("sdf pool meshing failed; falling back to synchronous", err);
    } finally {
      pool.dispose(); // geometry is built once at load; free the workers after
    }
  }

  // Build region meshes and index them for the arrows. SDF structures get their
  // pre-meshed geometry; everything else is meshed synchronously inside the call.
  const meshes = [];
  const meshById = new Map();
  const geomUsed = new Set();
  for (const structure of data.structures) {
    // Resolve through the spec, so a mirrored twin picks up the geometry meshed
    // under its right-side partner's id. Every consumer after the first gets a
    // clone: `buildStructureMesh` mirrors (and so mutates) what it is handed, and
    // a clone is a memcpy against a million-sample re-mesh.
    let geom = sdfGeoms.get(sdfBySpec.get(structure.shape) ?? structure.id);
    if (geom) {
      if (geomUsed.has(geom)) geom = geom.clone();
      else geomUsed.add(geom);
    }
    const mesh = buildStructureMesh(structure, geom);
    meshes.push(mesh);
    meshById.set(structure.id, mesh);
    scene.add(mesh);
  }
  return { meshes, meshById };
}
