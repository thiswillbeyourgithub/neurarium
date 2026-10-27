// See-inside: fade the shell meshes (lobes, cerebellum) the camera sits inside or
// right behind, so the deep nuclei stay visible (which meshes a pick may land on is js/scene/pick-filter.js).

import * as THREE from "three";

// "See inside": how far past the orbit-centre plane (toward the camera) an
// outer-shell structure's centre must sit before it fades. Small and positive, so a
// shell straddling the plane stays solid rather than flickering at every crossing.
const NEAR_CULL_BIAS = 0.3;

// The opacity a near shell fades to: faint enough to see the nuclei through, still
// there as a ghost so the brain keeps its outline. Eased per frame, never popped.
const SEE_INSIDE_OPACITY = 0.08;

const SEE_INSIDE_EASE = 0.18; // per-frame approach fraction toward the target fade

// The outer shell: the structures big enough to wrap the core and hide it. Only
// these are ever faded. Fading by position alone (the whole near half, deep nuclei
// included) reads backwards: from a lateral view it dropped the near hippocampus,
// amygdala and striatum - the very things you opened the mode to see - while keeping
// the near frontal and parietal lobes, whose centres sit close to the midline, so the
// brain still looked whole. Fading only the shell is the anatomical cutaway instead:
// the near cortex turns to glass, every nucleus stays, and the far cortex remains as
// the backdrop that gives them their place.
const SHELL_STRUCTURE_IDS = new Set(["cerebellum"]); // the one non-lobe that wraps

const isShellMesh = (mesh) =>
  mesh.userData.structure?.group === "lobe"
  || SHELL_STRUCTURE_IDS.has(mesh.userData.id);

/**
 * The one writer of a structure mesh's opacity: the lower of what the focus wants
 * (`userData.focusOpacity`, set by the selection's apply) and the "See inside" fade
 * (`userData.insideFade`, set by createSeeInside), so the two compose whichever moved.
 * @param {THREE.Mesh} mesh
 */
export function writeMeshOpacity(mesh) {
  const op = Math.min(mesh.userData.focusOpacity ?? 1, mesh.userData.insideFade ?? 1);
  mesh.material.opacity = op;
  mesh.material.depthWrite = op >= 0.99;
}

/**
 * Toggleable "see inside" mode: fade the cortical shell between you and the core to
 * glass so the deep nuclei aren't blocked by the near cortex. Which shells fade is
 * recomputed every frame from the live camera/target, so it follows as you orbit, and
 * each one eases toward its target (no pop). Off by default.
 *
 * @param {{meshes:THREE.Mesh[], camera:THREE.Camera,
 *          controls:import("three/addons/controls/OrbitControls.js").OrbitControls}} deps
 */
export function createSeeInside({ meshes, camera, controls }) {
  let enabled = false;
  const shells = meshes.filter(isShellMesh);
  const viewOut = new THREE.Vector3();
  const toMesh = new THREE.Vector3();
  return {
    setEnabled(on) {
      enabled = on;
    },
    /** Per-frame: ease each shell toward faint when its centre is more than
     *  NEAR_CULL_BIAS past the orbit-centre plane toward the camera, else toward solid
     *  (always solid when off). Returns whether any fade moved, to keep rendering. */
    tick() {
      viewOut.copy(camera.position).sub(controls.target);
      const haveView = viewOut.lengthSq() > 1e-9;
      if (haveView) viewOut.normalize();
      let moving = false;
      for (const m of shells) {
        toMesh.copy(m.position).sub(controls.target);
        const near = enabled && haveView && toMesh.dot(viewOut) > NEAR_CULL_BIAS;
        const want = near ? SEE_INSIDE_OPACITY : 1;
        const cur = m.userData.insideFade ?? 1;
        if (cur === want) continue;
        const next = Math.abs(want - cur) < 0.01 ? want : cur + (want - cur) * SEE_INSIDE_EASE;
        m.userData.insideFade = next;
        writeMeshOpacity(m);
        moving = true;
      }
      return moving;
    },
  };
}
