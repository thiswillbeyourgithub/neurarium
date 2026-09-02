// Load the author-side baked SDF geometry (tools/bake_meshes.mjs), so the brain's
// meshes are downloaded instead of rebuilt in the visitor's browser.
//
// Fallback is the whole design here. This module NEVER throws and never blocks
// the app: a missing manifest, an unknown format version, a failed file, a
// corrupt buffer, all just mean "no baked mesh for that shape", and js/main.js
// meshes whatever is missing at runtime through the SDF worker pool exactly as
// before. That keeps `tools/serve.py` and the geometry_refinements loop working
// on a tree that has not been re-baked, and it means a bad deploy degrades to
// slow rather than to blank.
//
// It is deliberately noisy about it (`console.info`), because a silent fallback
// is a 4-second regression nobody would ever notice.

import { decodeMesh, FORMAT_VERSION } from "./mesh-codec.js";

/**
 * @param {string} base  data directory, e.g. "data".
 * @param {(p:{loaded:number,total:number}) => void} [onProgress]
 * @returns {Promise<Map<string, {positions:Float32Array, indices:Uint32Array}>>}
 *   keyed by `shape_file` (the path as it appears on a structure), empty when no
 *   usable bake is present.
 */
export async function loadBakedMeshes(base, onProgress = null) {
  const out = new Map();
  let manifest;
  try {
    const res = await fetch(`${base}/meshes/index.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    manifest = await res.json();
  } catch (err) {
    console.info(`baked meshes: no manifest (${err.message}); meshing in the browser instead`);
    return out;
  }
  if (manifest?.format !== FORMAT_VERSION) {
    // A format bump ships new code and new bytes together, but a stale cached
    // manifest can outlive a deploy, so read the version rather than assume it.
    console.info(`baked meshes: manifest format v${manifest?.format} != v${FORMAT_VERSION}; ` +
      "meshing in the browser instead");
    return out;
  }

  const entries = Object.entries(manifest.meshes || {});
  const total = entries.length;
  let loaded = 0;
  onProgress?.({ loaded, total });
  await Promise.all(entries.map(async ([shapeFile, entry]) => {
    try {
      const res = await fetch(`${base}/meshes/${entry.file}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const mesh = decodeMesh(await res.arrayBuffer());
      // Cheap self-check: the manifest states what the file should hold, so a
      // truncated or mismatched download is caught here instead of rendering as
      // a mangled structure. The verbatim spec hash is checked author-side
      // (tools/bake_meshes.mjs --check), which is where a stale bake is caught.
      if (mesh.positions.length / 3 !== entry.vertices ||
          mesh.indices.length / 3 !== entry.triangles) {
        throw new Error("counts disagree with the manifest");
      }
      out.set(shapeFile, mesh);
    } catch (err) {
      console.info(`baked meshes: ${entry.file} unusable (${err.message}); ` +
        "that structure is meshed in the browser");
    } finally {
      onProgress?.({ loaded: (loaded += 1), total });
    }
  }));
  return out;
}
