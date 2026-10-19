// Selection state: the picked structure / connection halo, the isolate set, and the
// onIsolate watchers other controllers subscribe to.

import * as THREE from "three";
import { DECOR_RENDER_ORDER } from "../render-order.js";
import { writeMeshOpacity } from "./see-inside.js";

/**
 * Selection + isolation controller. Owns the per-structure highlight halos, the
 * structure/arrow opacity, and the legend-greying hook, so all three stay in one
 * consistent state.
 *
 * Two overlapping ideas, both surfaced through the halos built below:
 *   - a lightweight *highlight* (`select`): the single structure picked in the
 *     3D view (click / double-click / search). Halo only, no dimming, so the
 *     region is shown in context.
 *   - an *isolate* set (`toggleIsolate`, fed by clicking legend rows): while it
 *     is non-empty the scene focuses on those structures. Every other structure
 *     drops to a faint opacity, arrows that don't touch an isolated structure
 *     fade with them, the isolated structures keep full (slider) opacity + halo,
 *     and the legend greys its non-isolated rows (via the `onIsolate` callback).
 *     The reset button (`clear`) empties it.
 *
 * Opacity is composed here rather than in a standalone helper because the
 * isolate dimming and the transparency slider must combine into one final
 * opacity per mesh: `setBaseOpacity` records the slider value and every reapply
 * derives each mesh/arrow opacity from that base plus the isolate state.
 *
 * Each structure gets one hidden "shell" child for its halo: its own geometry,
 * scaled up a touch and drawn back-faces-only with an additive, non-depth-
 * writing material in a lightened version of the structure's colour. Rendering
 * only the back side of the slightly larger shell shows just the sliver poking
 * out past the real mesh (a coloured rim/aura), and additive blending makes it
 * read as light rather than a solid outline. Parenting the shell to the mesh
 * lets it inherit every transform (explode, mirror, position) for free, so the
 * halo tracks the structure with zero per-frame work, and it reuses the mesh
 * geometry (no clone). This keeps the no-build, single-pass renderer intact (no
 * EffectComposer / OutlinePass post-processing).
 *
 * @param {{meshes:THREE.Mesh[], arrows:import("./arrows.js").ProjectionArrow[]}} deps
 * @returns {{
 *   setBaseOpacity: (o:number) => void,
 *   select: (mesh: THREE.Mesh|null) => void,
 *   toggleIsolate: (group: THREE.Mesh[]) => void,
 *   clear: () => void,
 *   getSelected: () => {meshes:Set<THREE.Mesh>, arrows:Set<object>}|null,
 *   onIsolate: (fn: (isolated: Set<THREE.Mesh>|null) => void) => void,
 * }}
 */
export function createSelection({ meshes, arrows }) {
  // How far the halo shell extends past the real surface: small, so the rim is a
  // thin glow rather than a fat outline.
  const SCALE = 1.06;
  // Opacity that isolate mode drops everything *not* selected to (structures and
  // unrelated arrows alike): faint enough that the focus pops, but not fully
  // gone, so the rest of the brain still reads as context.
  const DIM = 0.12;
  // Opacity for *static context* arrows (a drug's postsynaptic-receptor pathways):
  // clearly visible so the engaged system reads, but below the flowing/pinned
  // arrows (full, itself capped at ARROW_MAX_OPACITY) so a "no tone change" system never looks
  // like the animated "sets the tone of".
  const CONTEXT_ARROW_OPACITY = 0.42;
  const white = new THREE.Color(0xffffff);

  for (const mesh of meshes) {
    // Lighten the structure's own colour toward white so the rim reads as light
    // regardless of how dark/saturated the region is, while still tying back to it.
    const color = new THREE.Color(mesh.userData.structure.color).lerp(white, 0.35);
    const material = new THREE.MeshBasicMaterial({
      color,
      side: THREE.BackSide, // only the rim poking past the real mesh shows
      transparent: true,
      opacity: 0.6,
      blending: THREE.AdditiveBlending, // brightens the background -> glow, not paint
      depthWrite: false, // a glow must not occlude anything behind it
    });
    const shell = new THREE.Mesh(mesh.geometry, material);
    shell.scale.setScalar(SCALE);
    shell.visible = false;
    shell.renderOrder = DECOR_RENDER_ORDER; // draw over the structures (see render-order.js)
    // Pure decoration: never let the halo intercept picking/hover raycasts.
    shell.raycast = () => {};
    mesh.add(shell);
    mesh.userData.halo = shell;
  }

  let highlighted = null; // single 3D-pick structure highlight (halo only)
  let highlightedArrow = null; // single picked arrow (halo only)
  const isolated = new Set(); // legend multi-select (drives the dimming)
  // Explicit arrow focus for circuits: when non-empty, *only* these arrows stay
  // opaque. When empty, isolate mode falls back to "arrows touching an isolated
  // structure" (so a plain structure isolate still lights up its connections).
  const isolatedArrows = new Set();
  // Static "context" arrows: pathways a focus engages but does NOT animate (a drug's
  // postsynaptic-receptor systems, see js/data.js contextKinds). Rendered at a
  // dimmed static opacity, brighter than the faded background but never full-opaque,
  // and deliberately kept OUT of isolatedArrows so the flow animation's exact-match
  // watcher (circuitAnim.matches) is unaffected and they carry no beads.
  const contextArrows = new Set();
  let baseOpacity = 1; // current transparency-slider value
  // Focus-change subscribers, each called on every apply() with the live isolate
  // state. Multiple because both the legend (greying) and the circuit pulse
  // animation (stop when the focus is no longer its circuit) need to react.
  const onIsolateSubs = [];
  // Highlight-change subscribers, each called with the single haloed structure
  // mesh (or null) on every apply(). The label overlay uses this to pin the
  // selected structure's name (a structure pick sets `highlighted`; an arrow /
  // target / drug focus or a clear nulls it), so the pinned name follows exactly
  // the active single-structure selection. Idempotent downstream (setPinned
  // early-returns on no change), so re-firing every apply() is cheap.
  const onHighlightSubs = [];
  // Fired whenever the user actively picks content (a structure, an arrow, a
  // legend isolate, or a circuit), but not on a clear. Used to stop auto-rotate
  // once the user reaches in to inspect something. Set via onPick().
  let onPickContent = () => {};

  const touchesIsolated = (arrow) =>
    isolated.has(arrow.fromMesh) || isolated.has(arrow.toMesh);
  // Is an arrow part of the current focus? Circuits/drugs pin an explicit arrow set;
  // otherwise any arrow touching an isolated structure counts. Once EITHER an explicit
  // pin or a static-context set exists we are in "explicit" mode, so the touch fallback
  // is off (a purely postsynaptic drug pins only context arrows and must not relight
  // every arrow grazing its regions).
  const arrowInFocus = (arrow) =>
    isolatedArrows.size > 0 || contextArrows.size > 0
      ? isolatedArrows.has(arrow)
      : touchesIsolated(arrow);

  // Recompute halos + opacity from the current highlight/isolate/base state. One
  // function so the triggers (3D pick, legend, circuits) can never drift apart.
  function apply() {
    const active = isolated.size > 0;
    for (const mesh of meshes) {
      const halo = mesh.userData.halo;
      if (halo) {
        halo.visible = mesh.visible && (mesh === highlighted || isolated.has(mesh));
      }
      // Isolated (or no isolation) -> the slider opacity; everything else faint.
      mesh.userData.focusOpacity = !active || isolated.has(mesh) ? baseOpacity : Math.min(baseOpacity, DIM);
      writeMeshOpacity(mesh);
    }
    // Arrows: keep those in the focus opaque, fade the rest into the background
    // with the dimmed structures; the picked arrow also lights its halo. The ones
    // the focus lights (pinned, static context, or - for a plain structure isolate -
    // touching it) are collected as they are found, so the "Show projections"
    // toggle can keep exactly those visible while the ambient tangle is hidden.
    const focusArrows = new Set();
    for (const arrow of arrows) {
      let op;
      if (!active || arrowInFocus(arrow)) op = 1;
      else if (contextArrows.has(arrow)) op = CONTEXT_ARROW_OPACITY;
      else op = DIM;
      if (active && op !== DIM) focusArrows.add(arrow);
      arrow.setOpacity(op);
      arrow.setHalo(arrow === highlightedArrow);
    }
    // A picked (haloed) arrow is a focus of one, so it shows through the same way.
    if (highlightedArrow) focusArrows.add(highlightedArrow);
    // Pass the pinned-arrow set too (empty unless a circuit/kind is focused) so
    // the legend can tell *which* projection-kind/circuit row is the active one,
    // then the lit set for the visibility composition above.
    for (const fn of onIsolateSubs) fn(active ? isolated : null, isolatedArrows, focusArrows);
    for (const fn of onHighlightSubs) fn(highlighted);
  }

  return {
    /** Record the transparency slider value (composes with isolate dimming). */
    setBaseOpacity(o) {
      baseOpacity = o;
      apply();
    },
    /** Is this mesh currently in the isolate/focus set? */
    isIsolated(mesh) {
      return isolated.has(mesh);
    },
    /** Lightweight single structure highlight from a 3D pick (null clears it). */
    select(mesh) {
      const next = mesh && mesh.userData.halo ? mesh : null;
      if (next === highlighted && highlightedArrow === null) return;
      highlighted = next;
      highlightedArrow = null; // a structure and an arrow halo are mutually exclusive
      apply();
      if (next) onPickContent();
    },
    /** Halo a single picked arrow (click/search); null clears it. */
    selectArrow(arrow) {
      if (arrow === highlightedArrow && highlighted === null) return;
      highlightedArrow = arrow || null;
      highlighted = null;
      apply();
      if (highlightedArrow) onPickContent();
    },
    /**
     * Toggle a group of meshes (a legend row's L/R pair, or a whole category) in
     * the isolate set: remove them if all are already isolated, else add them
     * all, so the click reads as a single on/off. Drops any circuit arrow-pin so
     * the focus reverts to "connections of the isolated structures".
     */
    toggleIsolate(group) {
      const allIn = group.length > 0 && group.every((m) => isolated.has(m));
      for (const m of group) {
        if (allIn) isolated.delete(m);
        else isolated.add(m);
      }
      isolatedArrows.clear();
      contextArrows.clear();
      apply();
      onPickContent();
    },
    /**
     * Replace the whole focus with an explicit circuit: just `meshes` opaque +
     * just `circuitArrows` opaque, everything else faint. Empty args clear it.
     * `staticArrows` (optional) are pinned at a dimmed *static* opacity (a drug's
     * postsynaptic-receptor pathways): highlighted but never animated, and kept out
     * of the pinned set so the flow animation's exact-match watcher is unaffected.
     */
    setCircuit(circuitMeshes, circuitArrows, staticArrows = []) {
      isolated.clear();
      isolatedArrows.clear();
      contextArrows.clear();
      for (const m of circuitMeshes) isolated.add(m);
      for (const a of circuitArrows) isolatedArrows.add(a);
      for (const a of staticArrows) if (!isolatedArrows.has(a)) contextArrows.add(a);
      highlighted = null;
      highlightedArrow = null;
      apply();
      if (circuitMeshes.length) onPickContent();
    },
    /** Clear every highlight + isolate, restoring default opacity everywhere. */
    clear() {
      highlighted = null;
      highlightedArrow = null;
      isolated.clear();
      isolatedArrows.clear();
      contextArrows.clear();
      apply();
    },
    /**
     * The currently focused meshes + arrows (whatever stays opaque): the isolate
     * set (legend / circuit / projection-group) plus any single halo'd structure,
     * and the in-focus arrows plus any single halo'd arrow. Returns null when
     * nothing is selected. Used to scope "show all names" to just the selection.
     */
    getSelected() {
      const sm = new Set(isolated);
      if (highlighted) sm.add(highlighted);
      const sa = new Set();
      if (isolated.size > 0) {
        for (const a of arrows) if (arrowInFocus(a)) sa.add(a);
      }
      if (highlightedArrow) sa.add(highlightedArrow);
      if (sm.size === 0 && sa.size === 0) return null;
      return { meshes: sm, arrows: sa };
    },
    /**
     * Re-emit the current state to every subscriber (halos/opacity/legend greying)
     * without changing it. Used after the legend is rebuilt (colour-mode toggle)
     * so the fresh rows reflect the live isolate set immediately.
     */
    refresh() {
      apply();
    },
    /**
     * Register a focus-change callback, invoked with the live isolate set (or
     * null when nothing is isolated) and the pinned-arrow set on every change.
     * Multiple may be registered (legend greying + circuit-pulse stop). Applied
     * once now so the new subscriber reflects the current state immediately.
     */
    onIsolate(fn) {
      onIsolateSubs.push(fn);
      apply();
    },
    /**
     * Register a callback fired with the single haloed structure mesh (or null)
     * whenever it changes. Used to pin the selected structure's floating name.
     * Applied once now so the subscriber reflects the current highlight.
     */
    onHighlight(fn) {
      onHighlightSubs.push(fn);
      fn(highlighted);
    },
    /**
     * Register a callback fired whenever the user actively picks content (a
     * structure, an arrow, a legend isolate, or a circuit) but not on a clear.
     * Used to stop auto-rotate once the user reaches in to inspect something.
     */
    onPick(fn) {
      onPickContent = fn;
    },
  };
}
