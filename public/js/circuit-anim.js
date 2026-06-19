// Circuit "traveling pulse" animation: a volley of glowing beads rides each arrow
// of an isolated circuit from its source region to its target, sweeping outward
// from a seed node and looping, so a curated loop (the direct pathway, the Papez
// memory circuit, ...) reads as signal *flowing* around it instead of a static set
// of arrows. The volley's size/speed/brightness keys off the arrow's sign (see
// BURST): excitatory pathways fire a bigger, faster, dramatic burst; inhibitory a
// smaller, slower, dimmer one.
//
// As each bead lands, the target region briefly brightens (a "node flash"), so
// the hand-off from arrow to arrow around the loop is legible, not just the beads.
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

// Node flash: as a bead lands on its target, that region's rim brightens, then
// fades. A dedicated back-side additive shell reusing the structure geometry (the
// same trick as the selection halo, see js/main.js), but owned here and sized a
// touch larger so it reads as an extra pulse on top of any steady isolate halo.
const FLASH_SCALE = 1.12;
const FLASH_MAX_OPACITY = 0.7;
// Time for a full flash (level 1) to fade back to nothing; a bit under STEP_MS so
// a node dims again before the next ring lights it.
const FLASH_DECAY_MS = 520;
// The bead is "landing" once it is this far along its arc: past here it tops up
// the target node's flash, ramping to full as it reaches the surface (t = 1).
const ARRIVAL_ZONE = 0.8;

// Burst character per projection sign: an excitatory arrow fires a bigger, faster,
// brighter volley of beads; an inhibitory one a smaller, slower, dimmer trickle;
// modulatory sits between. Each arrow releases `count` beads spaced `gap` apart
// (in arc fraction) at the start of its slot; the lead advances at `speed` x the
// slot rate (> 1 lands the volley early, so it reads as a burst then a pause).
// `scale` sizes the bead vs PULSE_RADIUS and `bright` scales its glow + the node
// flash it delivers. Deliberately modest, not over the top.
const BURST = {
  excitatory: { count: 4, speed: 1.6, gap: 0.10, scale: 1.05, bright: 1.0 },
  inhibitory: { count: 2, speed: 1.15, gap: 0.18, scale: 0.82, bright: 0.6 },
  modulatory: { count: 3, speed: 1.3, gap: 0.14, scale: 0.95, bright: 0.85 },
};
const burstFor = (sign) => BURST[sign] || BURST.modulatory;

/**
 * Build the circuit traveling-pulse controller. One per scene; ticked once per
 * frame in the render loop. Driven by js/main.js: `play(circuitArrows)` from the
 * circuit legend row, `stop()` (or the focus-change watcher) when the focus
 * leaves that circuit.
 * @param {{scene: THREE.Scene}} deps
 */
export function createCircuitAnimation({ scene }) {
  let pulses = []; // { arrow, phase, mesh, material, offset, speed, bright }
  // Target region -> its flash shell + current brightness. One per distinct node
  // that receives an arrow, so a node hit by several arrows shares one flash.
  let nodeFlashes = new Map(); // toMesh -> { mesh, shell, material, level }
  let playing = null; // the circuitArrows array currently animating (identity key)
  let numSteps = 1;
  let elapsed = 0;
  let lastTime = null;

  function clearVisuals() {
    for (const p of pulses) {
      scene.remove(p.mesh);
      p.material.dispose();
    }
    pulses = [];
    for (const f of nodeFlashes.values()) {
      f.mesh.remove(f.shell);
      f.material.dispose();
    }
    nodeFlashes.clear();
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
        const burst = burstFor(arrow.projection.sign);
        // Lighten the arrow's own colour toward white so the bead reads as a
        // bright packet of *that* pathway. Additive + no depth write so it glows
        // over the (possibly dimmed) arrow rather than being occluded by it.
        const color = arrow.material.color.clone().lerp(WHITE, 0.55);
        for (let i = 0; i < burst.count; i++) {
          const material = new THREE.MeshBasicMaterial({
            color: color.clone(),
            transparent: true,
            opacity: 0,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          });
          const mesh = new THREE.Mesh(PULSE_GEOMETRY, material);
          mesh.scale.setScalar(burst.scale);
          mesh.visible = false;
          mesh.raycast = () => {}; // pure decoration, never pickable
          scene.add(mesh);
          pulses.push({
            arrow, phase, mesh, material,
            offset: i * burst.gap, speed: burst.speed, bright: burst.bright,
          });
        }
      }
      // One flash shell per distinct target region (parented to it, so it tracks
      // the structure's explode/mirror transform for free, like the halo).
      for (const arrow of circuitArrows) {
        const target = arrow.toMesh;
        if (nodeFlashes.has(target)) continue;
        const material = new THREE.MeshBasicMaterial({
          color: new THREE.Color(target.userData.structure.color).lerp(WHITE, 0.6),
          side: THREE.BackSide, // only the rim poking past the real mesh shows
          transparent: true,
          opacity: 0,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        });
        const shell = new THREE.Mesh(target.geometry, material); // reuse geometry
        shell.scale.setScalar(FLASH_SCALE);
        shell.visible = false;
        shell.raycast = () => {};
        target.add(shell);
        nodeFlashes.set(target, { mesh: target, shell, material, level: 0 });
      }
      playing = circuitArrows;
    },

    /** Remove every bead + flash and halt. Safe to call when not playing. */
    stop() {
      clearVisuals();
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

    /** Advance the beads + node flashes. Call once per frame in the render loop. */
    tick() {
      if (!playing) return;
      const now = performance.now();
      if (lastTime === null) lastTime = now;
      const dt = now - lastTime;
      lastTime = now;
      elapsed = (elapsed + dt) % (numSteps * STEP_MS);

      // Fade every node flash toward nothing; an arriving bead tops it back up.
      for (const f of nodeFlashes.values()) {
        f.level = Math.max(0, f.level - dt / FLASH_DECAY_MS);
      }

      const clock = elapsed / STEP_MS; // position in "steps", [0, numSteps)
      for (const p of pulses) {
        // This arrow's slot is active for local in [phase, phase+1); each bead in
        // the volley rides the arc offset behind the lead and a touch faster.
        const local = clock - p.phase;
        if (local < 0 || local >= 1 || !p.arrow.group.visible) {
          p.mesh.visible = false;
          continue;
        }
        const t = local * p.speed - p.offset; // this bead's position along the arc
        if (t < 0 || t > 1) {
          p.mesh.visible = false;
          continue;
        }
        p.mesh.position.copy(p.arrow.curve.getPoint(t));
        p.mesh.visible = true;
        // Fade in/out at the ends of the run so beads don't pop, but stay bright
        // across the middle so the hand-off at each node reads clearly.
        const edge = 0.12;
        const k = Math.min(t / edge, (1 - t) / edge, 1);
        p.material.opacity = (0.2 + 0.8 * Math.max(0, k)) * p.bright;
        // As the bead lands, brighten its target region, ramping to full at t = 1
        // (scaled by the sign's brightness, so excitatory volleys hit harder).
        if (t >= ARRIVAL_ZONE) {
          const f = nodeFlashes.get(p.arrow.toMesh);
          if (f) {
            const intensity = ((t - ARRIVAL_ZONE) / (1 - ARRIVAL_ZONE)) * p.bright;
            if (intensity > f.level) f.level = intensity;
          }
        }
      }

      // Push the decayed / topped-up levels onto the flash shells.
      for (const f of nodeFlashes.values()) {
        const opacity = f.level * FLASH_MAX_OPACITY;
        f.material.opacity = opacity;
        f.shell.visible = f.mesh.visible && opacity > 0.01;
      }
    },
  };
}
