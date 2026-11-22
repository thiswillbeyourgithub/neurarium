// Functional-area overlay (BETA): while a drawn area (`own_shape`) is focused, its own
// mesh is laid over each hemisphere of the lobe it lies in, so the reader sees the
// area itself rather than the whole lobe lit. The area's shape is a piece of its lobe
// in the lobe's local frame (tools/data_generators/functional_areas.py), so the mesh is
// added as a CHILD of the lobe mesh: it follows the explode spread and the left
// hemisphere's mirror for free. Geometry comes from the bake, else is meshed here once.

import * as THREE from "three";
import { loadBakedMesh } from "../baked-meshes.js";
import { buildSdfGeometry, geometryFromArrays } from "../sdf.js";
import { mirrorGeometryX } from "../shapes.js";
import { gradientNoise, fractalNoise } from "../noise.js";
import { fetchJson } from "../net.js";
import { requestRepaint } from "./setup.js";

const ACCENT = "#ffd166";

/**
 * @param {{meshById: Map<string, THREE.Mesh>}} deps
 * @returns {{show: (area: object) => Promise<void>, hide: () => void}}
 */
export function createAreaOverlay({ meshById }) {
  const geomByFile = new Map(); // shape_file -> Promise<THREE.BufferGeometry|null>
  let current = []; // [{parent, mesh}]
  let token = 0;

  const geometryOf = (shapeFile) => {
    if (!geomByFile.has(shapeFile)) {
      geomByFile.set(shapeFile, (async () => {
        const baked = await loadBakedMesh("data", shapeFile);
        if (baked) return geometryFromArrays(baked.positions, baked.indices);
        const spec = await fetchJson(shapeFile);
        return buildSdfGeometry(spec, { noise3d: gradientNoise, fractalNoise });
      })().catch((err) => {
        console.error("area shape unavailable", shapeFile, err);
        return null;
      }));
    }
    return geomByFile.get(shapeFile);
  };

  const hide = () => {
    token += 1;
    for (const { parent, mesh } of current) {
      parent.remove(mesh);
      mesh.geometry.dispose();
      mesh.material.dispose();
    }
    if (current.length) requestRepaint();
    current = [];
  };

  const show = async (area) => {
    hide();
    if (!area.own_shape || !area.shape_file) return;
    const mine = token;
    const geom = await geometryOf(area.shape_file);
    if (!geom || mine !== token) return;
    for (const id of area.structures) {
      const parent = meshById.get(id);
      if (!parent) continue;
      const g = geom.clone();
      if (parent.userData.structure && parent.userData.structure.mirror) mirrorGeometryX(g);
      const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
        color: ACCENT, emissive: ACCENT, emissiveIntensity: 0.45, roughness: 0.6,
        side: THREE.DoubleSide,
        // The area shares its lobe's outer surface: pull it forward so it wins.
        polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
      }));
      mesh.renderOrder = 2;
      mesh.raycast = () => {}; // picking stays on the lobe
      parent.add(mesh);
      current.push({ parent, mesh });
    }
    requestRepaint();
  };

  return { show, hide };
}
