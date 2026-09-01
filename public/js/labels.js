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
 *   setShowAll: (on: boolean, restrictMeshes?: Set<THREE.Mesh>|null,
 *                restrictArrows?: Set<object>|null) => void,
 *   setHovered: (mesh: THREE.Mesh|null) => void,
 *   setPinned: (meshOrList: THREE.Mesh|THREE.Mesh[]|null) => void,
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
  // Named so the stylesheet can hide the overlay together with the canvas in
  // panel-only mode (body.no-3d), which the renderer knows nothing about.
  dom.id = "labels-layer";
  dom.style.position = "fixed";
  dom.style.top = "0";
  dom.style.left = "0";
  dom.style.pointerEvents = "none";
  parentEl.appendChild(dom);

  for (const mesh of meshes) {
    const el = document.createElement("div");
    el.className = "structure-label";
    // The hemisphere-stripped base name ("Frontal lobe", not "Right frontal
    // lobe"): the L/R prefix is what made "show all names" illegible, and a
    // label sits on its own hemisphere's mesh so the side is already obvious
    // from position. Midline structures have base_name === name.
    el.textContent = mesh.userData.structure.base_name || mesh.userData.structure.name;
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
  // The selected structure's label(s), kept visible regardless of hover for as
  // long as that structure stays the active selection (set via setPinned from the
  // selection controller's highlight). So picking a structure (3D click, search,
  // or a related-structure panel row) keeps its name on screen, and hovering
  // another region *adds* its label on top instead of replacing the pinned one.
  // A set, not one mesh: selecting a structure isolates its whole L/R base pair,
  // so BOTH hemispheres get their name pinned (not just the clicked side).
  let pinned = new Set();
  // Optional sets that scope "show all" to just the current selection: when
  // non-null, only these meshes / arrows get a label while show-all is on (so
  // naming a focused circuit or isolated region doesn't flood the screen with
  // every other name). Null means "show all" really means all.
  let scopeMeshes = null;
  let scopeArrows = null;

  const meshInScope = (mesh) => showAll && (!scopeMeshes || scopeMeshes.has(mesh));
  const arrowInScope = (arrow) => showAll && (!scopeArrows || scopeArrows.has(arrow));

  function refresh() {
    for (const mesh of meshes) {
      const label = mesh.userData.label;
      // A hidden structure (e.g. isolated-view screenshots) never shows its
      // label, even when "show all" is on.
      if (label) label.visible = mesh.visible
        && (meshInScope(mesh) || mesh === hovered || pinned.has(mesh));
    }
    // Connection labels: only with "show all" (arrows have no hover), and never
    // for an arrow hidden in an isolated view (group.visible=false).
    for (const arrow of arrows) {
      if (arrow.label) arrow.label.visible = arrowInScope(arrow) && arrow.group.visible;
    }
  }

  return {
    /**
     * Force every label on/off. Optionally scope it to a selection: pass Sets of
     * the meshes / arrows to name (null = all), so "show all names" can be
     * narrowed to just the focused structures when something is selected.
     */
    setShowAll(on, restrictMeshes = null, restrictArrows = null) {
      showAll = on;
      scopeMeshes = restrictMeshes;
      scopeArrows = restrictArrows;
      refresh();
    },
    setHovered(mesh) {
      if (mesh === hovered) return;
      hovered = mesh;
      refresh();
    },
    /**
     * Pin the selected structure's label(s) on: pass a mesh, an array of meshes
     * (a structure's whole L/R base pair, so both hemispheres are named), or null
     * to clear. They stay visible independent of hover until the selection
     * changes, so a picked structure keeps its name and hovering another region
     * adds, not replaces.
     */
    setPinned(meshOrList) {
      const next = meshOrList == null ? []
        : Array.isArray(meshOrList) ? meshOrList : [meshOrList];
      // Idempotent: onHighlight re-fires this every apply(), so bail on no change.
      if (next.length === pinned.size && next.every((m) => pinned.has(m))) return;
      pinned = new Set(next);
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
