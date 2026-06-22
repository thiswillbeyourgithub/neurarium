// Circuit "traveling pulse" animation: a volley of glowing beads rides each arrow
// of an isolated circuit from its source region to its target, sweeping outward
// from a seed node and looping, so a curated loop (the direct pathway, the Papez
// memory circuit, ...) reads as signal *flowing* around it instead of a static set
// of arrows. The volley's size/speed/brightness keys off the arrow's sign (see
// BURST): excitatory pathways fire a bigger, faster, dramatic burst; inhibitory a
// smaller, slower, dimmer one.
//
// As each bead lands, a "wash of light" spreads across the target region's surface
// from the exact point it hit (a surface echo, in the pathway's own colour), so the
// hand-off from arrow to arrow around the loop is legible, not just the beads, and
// the region reads as lighting up *from where the signal arrived* rather than
// blinking inert. The wash itself is the shared surface-wash primitive (see
// js/surface-wash.js, also used by the per-drug glow).
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
import { buildWashShell, washStrength } from "./surface-wash.js";

// Bead size (the arrow tube is TUBE_RADIUS 0.1, the cone 0.22): big enough to
// read as a packet riding the shaft, small enough not to swallow the arrowhead.
const PULSE_RADIUS = 0.17;
// Duration of one BFS-depth ring, i.e. how long a single arrow's bead takes to
// travel tail->head. The whole loop is numSteps * STEP_MS.
const STEP_MS = 650;
// Shared sphere for every bead (per-bead colour lives on the per-bead material).
const PULSE_GEOMETRY = new THREE.SphereGeometry(PULSE_RADIUS, 12, 12);
const WHITE = new THREE.Color(0xffffff);

// Node echo: as a bead lands on its target, a wash of light spreads from the point
// it hit across that region's surface, then dissolves (see js/surface-wash.js). One
// wash shell per distinct target node, reusing the structure geometry (parented to
// it, so it tracks the explode/mirror transform for free, like the selection halo).
// WASH_MS is one ripple's lifetime, a bit under STEP_MS so a node settles again
// before the next ring lights it.
const WASH_MS = 620;
// The bead is "landing" once it is this far along its arc: crossing here while the
// node's previous ripple has finished triggers a fresh wash from the impact point.
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
  // Target region -> its wash echo. One per distinct node that receives an arrow,
  // so a node hit by several arrows shares one wash (retriggered by whichever bead
  // last landed, in that arrow's colour). `age` >= WASH_MS means idle (no ripple).
  let nodeWashes = new Map(); // toMesh -> { mesh, wash, age, bright }
  let playing = null; // the circuitArrows array currently animating (identity key)
  let numSteps = 1;
  let elapsed = 0;
  let lastTime = null;
  // Reused scratch so triggering a wash allocates nothing per landing.
  const tmpPoint = new THREE.Vector3();

  function clearVisuals() {
    for (const p of pulses) {
      scene.remove(p.mesh);
      p.material.dispose();
    }
    pulses = [];
    for (const f of nodeWashes.values()) f.wash.dispose();
    nodeWashes.clear();
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
      // One wash shell per distinct target region (parented to it, so it tracks
      // the structure's explode/mirror transform for free, like the halo). Starts
      // idle (age past WASH_MS); a landing bead seeds + retriggers it.
      for (const arrow of circuitArrows) {
        const target = arrow.toMesh;
        if (nodeWashes.has(target)) continue;
        const wash = buildWashShell(target, target.userData.structure.color);
        if (!wash) continue;
        nodeWashes.set(target, { mesh: target, wash, age: WASH_MS, bright: 0 });
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

      // Age every node wash; once it passes WASH_MS it is idle (ripple finished)
      // and the next landing bead may retrigger it. Capped so it can't drift huge.
      for (const f of nodeWashes.values()) {
        if (f.age < WASH_MS) f.age = Math.min(WASH_MS, f.age + dt);
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
        // As the bead lands, seed a fresh wash from the impact point in this
        // arrow's colour, but only if the node's previous ripple has finished, so
        // a volley's first bead fires the echo and the rest don't restart it
        // (the next loop's bead retriggers once this one has dissolved). Scaled by
        // the sign's brightness, so excitatory volleys echo harder.
        if (t >= ARRIVAL_ZONE) {
          const f = nodeWashes.get(p.arrow.toMesh);
          if (f && f.age >= WASH_MS) {
            p.arrow.curve.getPoint(1, tmpPoint); // arc head, in world space
            p.arrow.toMesh.worldToLocal(tmpPoint); // -> the target's local frame
            f.wash.setOrigin(tmpPoint);
            f.wash.setColor(p.arrow.material.color);
            f.bright = p.bright;
            f.age = 0;
          }
        }
      }

      // Drive each wash from its age: the wavefront expands across the surface and
      // the half-sine envelope fades it in then out over WASH_MS.
      for (const f of nodeWashes.values()) {
        if (f.age >= WASH_MS) {
          f.wash.setWave(0, 0);
          continue;
        }
        const progress = f.age / WASH_MS;
        f.wash.setWave(progress * f.wash.maxRadius, washStrength(progress) * f.bright);
      }
    },
  };
}
