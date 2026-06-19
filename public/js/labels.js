// Floating structure-name labels, rendered as HTML on top of the WebGL canvas.
//
// We use three.js's CSS2DRenderer so each label is a real DOM element that
// tracks its structure's 3D position automatically (including while the scene
// auto-rotates or the regions explode, since labels are children of the
// meshes). One label is created per structure and hidden by default; the
// caller decides which are visible:
//   - on mouse hover, only the hovered structure's label shows;
//   - the "show all names" button reveals every label at once.
// Keeping both behaviors driven by the same set of labels avoids duplicating
// any name text or positioning logic.

import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

/**
 * Create the label overlay and attach hidden labels to structures and arrows.
 *
 * Structure labels ride each region mesh and show on hover or "show all".
 * Connection labels ride each arrow's `labelAnchor` (its arc midpoint) and show
 * only with "show all" (there is no per-arrow hover), so toggling "show all
 * names" labels the pathways too. Both kinds share one overlay + visibility
 * pass so nothing is duplicated.
 *
 * @param {THREE.Mesh[]} meshes  Structure meshes; each must carry
 *   `userData.structure.name`. A `CSS2DObject` is added as a child of each so
 *   the label rides along with the mesh.
 * @param {import("./arrows.js").ProjectionArrow[]} arrows  Projection arrows;
 *   each must expose `labelAnchor`, `group`, and `projection`.
 * @param {HTMLElement} parentEl  Element to mount the overlay into (e.g. body).
 * @returns {{
 *   setShowAll: (on: boolean) => void,
 *   setHovered: (mesh: THREE.Mesh|null) => void,
 *   render: (scene: THREE.Scene, camera: THREE.Camera) => void,
 *   resize: () => void,
 *   refresh: () => void,
 * }}
 */
export function createLabels(meshes, arrows, parentEl) {
  const renderer = new CSS2DRenderer();
  renderer.setSize(window.innerWidth, window.innerHeight);
  // The overlay sits over the canvas; pointer-events:none lets all mouse/touch
  // input fall through to OrbitControls so labels never block rotation.
  const dom = renderer.domElement;
  dom.style.position = "fixed";
  dom.style.top = "0";
  dom.style.left = "0";
  dom.style.pointerEvents = "none";
  parentEl.appendChild(dom);

  for (const mesh of meshes) {
    const el = document.createElement("div");
    el.className = "structure-label";
    el.textContent = mesh.userData.structure.name;
    // Outline each floating name in its structure's own color (consumed by the
    // .structure-label text-shadow in index.html) so the label ties back to the
    // region it points at.
    el.style.setProperty("--label-color", mesh.userData.structure.color);
    const label = new CSS2DObject(el);
    // Local origin of the mesh = the structure's center, so the label pins to it.
    label.position.set(0, 0, 0);
    label.visible = false;
    mesh.add(label);
    mesh.userData.label = label;
  }

  // One floating label per arrow, riding its midpoint anchor. Outlined in the
  // arrow's own color so it ties back to the pathway it sits on.
  for (const arrow of arrows) {
    const el = document.createElement("div");
    el.className = "connection-label";
    el.textContent = arrow.projection.label;
    el.style.setProperty(
      "--label-color",
      arrow.projection.color || "#ffffff",
    );
    const label = new CSS2DObject(el);
    label.position.set(0, 0, 0);
    label.visible = false;
    arrow.labelAnchor.add(label);
    arrow.label = label;
  }

  // Visibility is a pure function of these two bits of state, recomputed on any
  // change so the two triggers (hover, show-all) can never get out of sync.
  let showAll = false;
  let hovered = null;

  function refresh() {
    for (const mesh of meshes) {
      const label = mesh.userData.label;
      // A hidden structure (e.g. isolated-view screenshots) never shows its
      // label, even when "show all" is on.
      if (label) label.visible = mesh.visible && (showAll || mesh === hovered);
    }
    // Connection labels: only with "show all" (arrows have no hover), and never
    // for an arrow hidden in an isolated view (group.visible=false).
    for (const arrow of arrows) {
      if (arrow.label) arrow.label.visible = showAll && arrow.group.visible;
    }
  }

  return {
    setShowAll(on) {
      showAll = on;
      refresh();
    },
    setHovered(mesh) {
      if (mesh === hovered) return;
      hovered = mesh;
      refresh();
    },
    // Recompute visibility against the current mesh.visible flags. Call after
    // changing which meshes are shown (e.g. isolated screenshot views).
    refresh,
    render(scene, camera) {
      renderer.render(scene, camera);
    },
    resize() {
      renderer.setSize(window.innerWidth, window.innerHeight);
    },
  };
}
