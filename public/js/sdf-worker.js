// SDF meshing worker: runs the O(resolution^3) field fill + marching-cubes pass
// OFF the main thread, so assembling the brain's ~40 SDF meshes at load never
// freezes the page. One message in (a shape spec), one message out (the raw
// {positions, indices} typed arrays, transferred zero-copy).
//
// This is a MODULE worker, and it imports NO three at all: the meshing core, the
// self-authored marcher (js/marching-cubes.js) and the noise field are all
// THREE-free modules shared verbatim with the main thread. That is deliberate:
// module workers do not inherit the document's import map, and (more importantly)
// each worker is its own realm, so pulling in three here would make every worker
// separately load + parse the 1.3MB three.js, which dwarfs the per-structure
// meshing cost and regressed load time. Importing nothing heavy keeps worker
// startup ~instant.

import { meshSdfToArrays } from "./sdf-core.js";
import { gradientNoise, fractalNoise } from "./noise.js";

// Same fold field the main-thread blob/SDF builders use (js/noise.js).
const deps = { noise3d: gradientNoise, fractalNoise };

self.onmessage = (e) => {
  const { id, spec } = e.data;
  try {
    const { positions, indices } = meshSdfToArrays(spec, deps);
    // Transfer the backing buffers (zero-copy) rather than structured-cloning them.
    self.postMessage({ id, positions, indices }, [positions.buffer, indices.buffer]);
  } catch (err) {
    self.postMessage({ id, error: String((err && err.message) || err) });
  }
};
