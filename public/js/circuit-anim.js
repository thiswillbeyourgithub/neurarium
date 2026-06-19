// Circuit "traveling pulse" animation: a glowing bead rides each arrow of an
// isolated circuit from its source region to its target, sweeping outward from a
// seed node and looping, so a curated loop (the direct pathway, the Papez memory
// circuit, ...) reads as signal *flowing* around it instead of a static set of
// arrows.
//
// It sits entirely on top of the existing selection.setCircuit() focus: it only
// ever runs while a circuit is isolated, adds nothing to picking, and owns its
// own meshes. The viewer starts it from the circuit legend row and stops it the
// moment the focus changes to anything else (see js/main.js).
//
// Sequencing is *automatic*, not authored: scheduleCircuit (js/circuit-schedule.js,
// dependency-free so it can be tested on its own) gives each arrow a firing slot
// from a BFS over the circuit's directed graph. This module is just the rendering
// half: it turns those slots into beads riding each arrow's live curve and loops.
//
// No new dependency: just three.js and the curve each ProjectionArrow already
// exposes (arrow.curve, the live source->target arc).

import * as THREE from "three";
import { scheduleCircuit } from "./circuit-schedule.js";

// Bead size (the arrow tube is TUBE_RADIUS 0.1, the cone 0.22): big enough to
// read as a packet riding the shaft, small enough not to swallow the arrowhead.
const PULSE_RADIUS = 0.17;
// Duration of one BFS-depth ring, i.e. how long a single arrow's bead takes to
// travel tail->head. The whole loop is numSteps * STEP_MS.
const STEP_MS = 650;
// Shared sphere for every bead (per-bead colour lives on the per-bead material).
const PULSE_GEOMETRY = new THREE.SphereGeometry(PULSE_RADIUS, 12, 12);
const WHITE = new THREE.Color(0xffffff);

/**
 * Build the circuit traveling-pulse controller. One per scene; ticked once per
 * frame in the render loop. Driven by js/main.js: `play(circuitArrows)` from the
 * circuit legend row, `stop()` (or the focus-change watcher) when the focus
 * leaves that circuit.
 * @param {{scene: THREE.Scene}} deps
 */
export function createCircuitAnimation({ scene }) {
  let pulses = []; // { arrow, phase, mesh, material }
  let playing = null; // the circuitArrows array currently animating (identity key)
  let numSteps = 1;
  let elapsed = 0;
  let lastTime = null;

  function disposePulses() {
    for (const p of pulses) {
      scene.remove(p.mesh);
      p.material.dispose();
    }
    pulses = [];
  }

  return {
    /**
     * Start the traveling pulses for a circuit's arrow set. Replaces any running
     * animation. A no-op for an empty set.
     * @param {import("./arrows.js").ProjectionArrow[]} circuitArrows
     */
    play(circuitArrows) {
      this.stop();
      if (!circuitArrows || circuitArrows.length === 0) return;
      const { phased, numSteps: steps } = scheduleCircuit(circuitArrows);
      numSteps = steps;
      elapsed = 0;
      lastTime = null;
      for (const { arrow, phase } of phased) {
        // Lighten the arrow's own colour toward white so the bead reads as a
        // bright packet of *that* pathway. Additive + no depth write so it glows
        // over the (possibly dimmed) arrow rather than being occluded by it.
        const material = new THREE.MeshBasicMaterial({
          color: arrow.material.color.clone().lerp(WHITE, 0.55),
          transparent: true,
          opacity: 0,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        });
        const mesh = new THREE.Mesh(PULSE_GEOMETRY, material);
        mesh.visible = false;
        mesh.raycast = () => {}; // pure decoration, never pickable
        scene.add(mesh);
        pulses.push({ arrow, phase, mesh, material });
      }
      playing = circuitArrows;
    },

    /** Remove every bead and halt. Safe to call when not playing. */
    stop() {
      disposePulses();
      playing = null;
      lastTime = null;
    },

    /**
     * True iff currently animating exactly `arrowSet` (same arrows). Lets the
     * viewer keep the animation alive while the focus is still this circuit and
     * stop it the moment the focus becomes anything else. `arrowSet` is the
     * selection controller's live isolated-arrow Set.
     * @param {Set<object>|undefined} arrowSet
     */
    matches(arrowSet) {
      if (!playing || !arrowSet || arrowSet.size !== playing.length) return false;
      return playing.every((a) => arrowSet.has(a));
    },

    /** Advance the beads. Call once per frame in the render loop. */
    tick() {
      if (!playing) return;
      const now = performance.now();
      if (lastTime === null) lastTime = now;
      elapsed = (elapsed + (now - lastTime)) % (numSteps * STEP_MS);
      lastTime = now;

      const clock = elapsed / STEP_MS; // position in "steps", [0, numSteps)
      for (const p of pulses) {
        // This arrow is active during its one-step slot [phase, phase+1).
        const t = clock - p.phase;
        if (t < 0 || t >= 1 || !p.arrow.group.visible) {
          p.mesh.visible = false;
          continue;
        }
        p.mesh.position.copy(p.arrow.curve.getPoint(t));
        p.mesh.visible = true;
        // Fade in/out at the ends of the run so beads don't pop, but stay bright
        // across the middle so the hand-off at each node reads clearly.
        const edge = 0.12;
        const k = Math.min(t / edge, (1 - t) / edge, 1);
        p.material.opacity = 0.2 + 0.8 * Math.max(0, k);
      }
    },
  };
}
