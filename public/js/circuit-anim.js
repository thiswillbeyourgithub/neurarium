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
import { animSettings } from "./anim-settings.js";

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

// Continuous drug-flow stream (drug focus only, when `flowSystems` is passed):
// instead of the sequential BFS volley a curated circuit uses, every engaged pathway
// streams beads end-to-end without stopping, so the *relative* density and speed
// across systems read at a glance. Both are normalized per drug (js/data.js `rel`,
// the strongest engaged system = 1): dosage is variable, so what matters is the
// relative "dirtiness" of activity across systems, not an absolute magnitude. A
// stronger system rides more beads, faster; a weaker one fewer, slower.
const STREAM_MIN_BEADS = 3;
const STREAM_MAX_BEADS = 7;
// A drug's flow beads share the screen with the bright, pulsing per-region gem-dot
// clouds (drug-anim.js) and ride dimmed arrows, so the band is pitched to read next to
// a circuit's brisk volley. The floor is high enough that even the weakest engaged
// system is clearly *moving* (never an immobile crawl), and the ceiling stays calm
// enough to follow with the eye. The min<max ratio still carries the *relative* speed
// across a drug's systems (affinity itself is compared on a pKi scale in js/data.js,
// so the perceptual widening lives here in the output band, not in that ramp).
const STREAM_MIN_SPEED = 0.55; // arcs/sec (weakest system): clearly moving, not immobile
const STREAM_MAX_SPEED = 1.05; // arcs/sec (strongest system): brisk but still followable
// And lift the stream's glow a touch, for the same reason: the beads compete with
// the gem-dot clouds, so they need a little more presence to read as clearly as a
// circuit's beads do on their own.
const STREAM_BRIGHT = 1.2;
const lerp = (a, b, t) => a + (b - a) * t;

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
  let continuous = false; // drug flow: beads stream end-to-end instead of BFS volleys
  let streamSec = 0; // continuous-mode clock, in seconds (unbounded; per-bead mod 1)
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
     *
     * `flowSystems` (drug focus only) maps a projection kind to `{direction, weight}`
     * (js/data.js): direction +1 = the drug raises that transmitter's tone, -1 =
     * lowers it; weight (0..1) = the drug's affinity on that system. It recolours +
     * scales the volley per arrow (a boost reads warm/bright/fast + dense, a damp
     * cool/dim/slow + sparse), so an SSRI and a buspirone animate the serotonergic
     * fan in opposite directions. Empty (a curated circuit) = the plain sign-keyed
     * burst below.
     * @param {import("./arrows.js").ProjectionArrow[]} circuitArrows
     * @param {Object<string,{direction:number,weight:number}>} [flowSystems]
     */
    play(circuitArrows, flowSystems) {
      this.stop();
      if (!circuitArrows || circuitArrows.length === 0) return;
      // Animations off: the traveling pulse is pure motion, so don't build any
      // beads/washes. The circuit's arrows are still pinned + the rest dimmed by
      // the selection controller, so the circuit still reads, just held still.
      if (!animSettings.enabled) return;
      // Drug focus (flowSystems passed) streams continuously so relative density +
      // speed read; a curated circuit keeps its sequential BFS volley.
      continuous = !!flowSystems;
      const { phased, numSteps: steps } = scheduleCircuit(circuitArrows);
      numSteps = steps;
      elapsed = 0;
      streamSec = 0;
      lastTime = null;
      for (const { arrow, phase } of phased) {
        const burst = burstFor(arrow.projection.sign);
        // Per-system flow direction/weight (drug focus); null for a plain circuit.
        const flow = flowSystems ? flowSystems[arrow.projection.kind] : null;
        // Whiten less for a damping flow so the bead stays cool + saturated (reads
        // as "pulling the system down") vs the bright near-white boost/circuit bead.
        const whiten = flow ? (flow.direction > 0 ? 0.55 : 0.22) : 0.55;
        const color = arrow.material.color.clone().lerp(WHITE, whiten);

        // A bidirectional pathway (corpus callosum, claustro links) streams beads
        // BOTH ways so it reads as a two-way connection, not a one-way arrow; a
        // one-way pathway keeps a single forward stream.
        const dirs = arrow.projection.bidirectional ? [false, true] : [false];

        if (continuous) {
          // Relative intensity (0..1), normalized across the drug's systems so the
          // strongest streams fullest (js/data.js `rel`); both bead count (density)
          // and travel speed track it, a damp reads a touch slower/dimmer.
          const rel = flow ? (flow.rel != null ? flow.rel : flow.weight) : 1;
          const dir = flow ? flow.direction : 1;
          const beadCount = Math.max(1, Math.round(
            lerp(STREAM_MIN_BEADS, STREAM_MAX_BEADS, rel) * animSettings.quality));
          const streamSpeed = lerp(STREAM_MIN_SPEED, STREAM_MAX_SPEED, rel) * (dir < 0 ? 0.82 : 1);
          const bright = STREAM_BRIGHT * burst.bright * (dir > 0 ? 1 : 0.72);
          for (const reverse of dirs) for (let i = 0; i < beadCount; i++) {
            const material = new THREE.MeshBasicMaterial({
              color: color.clone(), transparent: true, opacity: 0,
              blending: THREE.AdditiveBlending, depthWrite: false,
            });
            const mesh = new THREE.Mesh(PULSE_GEOMETRY, material);
            mesh.scale.setScalar(burst.scale);
            mesh.visible = false;
            mesh.raycast = () => {};
            scene.add(mesh);
            // Even spacing along the arc so the stream looks steady, not clumped.
            pulses.push({ arrow, mesh, material, streamOffset: i / beadCount, streamSpeed, bright, reverse });
          }
          continue;
        }

        // Weight (affinity) thins a weak volley; a damp also dims + slows it.
        const countScale = flow ? 0.5 + 0.5 * flow.weight : 1;
        const bright = burst.bright * (flow ? (flow.direction > 0 ? 1 : 0.6) * (0.55 + 0.45 * flow.weight) : 1);
        const speed = burst.speed * (flow && flow.direction < 0 ? 0.8 : 1);
        // Scale the volley size by the adaptive quality (and flow weight) so a
        // struggling GPU or a weak affinity rides fewer beads (always at least one).
        const beadCount = Math.max(1, Math.round(burst.count * countScale * animSettings.quality));
        for (const reverse of dirs) for (let i = 0; i < beadCount; i++) {
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
            offset: i * burst.gap, speed, bright, reverse,
          });
        }
      }
      // One wash shell per distinct region (parented to it, so it tracks the
      // structure's explode/mirror transform for free, like the halo). Starts idle
      // (age past WASH_MS); a landing bead seeds + retriggers it. A bidirectional
      // pathway washes BOTH ends (a reverse bead lands on the source).
      for (const arrow of circuitArrows) {
        const ends = arrow.projection.bidirectional ? [arrow.toMesh, arrow.fromMesh] : [arrow.toMesh];
        for (const target of ends) {
          if (nodeWashes.has(target)) continue;
          const wash = buildWashShell(target, target.userData.structure.color);
          if (!wash) continue;
          nodeWashes.set(target, { mesh: target, wash, age: WASH_MS, bright: 0 });
        }
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

    /** Whether a traveling pulse is currently running (mirrors drugAnim/receptorMarkers
     *  `active`), so the viewer can show the speed slider only while something animates. */
    get active() {
      return !!playing;
    },

    /** Advance the beads + node flashes. Call once per frame in the render loop.
     *  Returns true while playing, so the on-demand render loop keeps drawing. */
    tick() {
      if (!playing) return false;
      const now = performance.now();
      if (lastTime === null) lastTime = now;
      // Scale the wall-clock delta by the user's speed multiplier: everything downstream
      // (bead phase, wash aging, the continuous stream) is driven by dt, so this one
      // multiply re-paces the whole animation with no phase jump on a live change.
      const dt = (now - lastTime) * animSettings.speed;
      lastTime = now;
      elapsed = (elapsed + dt) % (numSteps * STEP_MS);

      // Age every node wash; once it passes WASH_MS it is idle (ripple finished)
      // and the next landing bead may retrigger it. Capped so it can't drift huge.
      for (const f of nodeWashes.values()) {
        if (f.age < WASH_MS) f.age = Math.min(WASH_MS, f.age + dt);
      }

      if (continuous) streamSec += dt / 1000;
      const clock = elapsed / STEP_MS; // position in "steps", [0, numSteps)
      for (const p of pulses) {
        let t;
        if (continuous) {
          // Continuous stream: every bead is always on the arc, wrapping tail->head,
          // so the steady density + speed read (no start/stop volley).
          if (!p.arrow.group.visible) { p.mesh.visible = false; continue; }
          t = (streamSec * p.streamSpeed + p.streamOffset) % 1;
          if (t < 0) t += 1;
        } else {
          // This arrow's slot is active for local in [phase, phase+1); each bead in
          // the volley rides the arc offset behind the lead and a touch faster.
          const local = clock - p.phase;
          if (local < 0 || local >= 1 || !p.arrow.group.visible) {
            p.mesh.visible = false;
            continue;
          }
          t = local * p.speed - p.offset; // this bead's position along the arc
          if (t < 0 || t > 1) {
            p.mesh.visible = false;
            continue;
          }
        }
        // A reverse bead (on a bidirectional pathway) rides the arc head->tail, so
        // its curve parameter is mirrored; `t` stays the 0->1 travel progress used
        // for the fade + landing below, identical in both directions.
        const pos = p.reverse ? 1 - t : t;
        p.arrow.curve.getPoint(pos, tmpPoint); // reuse the scratch vec (no per-bead alloc)
        p.mesh.position.copy(tmpPoint);
        p.mesh.visible = true;
        // Fade in/out at the ends of the run so beads don't pop, but stay bright
        // across the middle so the hand-off at each node reads clearly (symmetric
        // in the travel progress t, so it works either direction).
        const edge = 0.12;
        const k = Math.min(t / edge, (1 - t) / edge, 1);
        p.material.opacity = (0.2 + 0.8 * Math.max(0, k)) * p.bright;
        // As the bead lands, seed a fresh wash from the impact point in this
        // arrow's colour, but only if the node's previous ripple has finished, so
        // a volley's first bead fires the echo and the rest don't restart it
        // (the next loop's bead retriggers once this one has dissolved). Scaled by
        // the sign's brightness, so excitatory volleys echo harder. A reverse bead
        // lands on the SOURCE node (the arc tail) instead of the target.
        if (t >= ARRIVAL_ZONE) {
          const landMesh = p.reverse ? p.arrow.fromMesh : p.arrow.toMesh;
          const f = nodeWashes.get(landMesh);
          if (f && f.age >= WASH_MS) {
            p.arrow.curve.getPoint(p.reverse ? 0 : 1, tmpPoint); // the arc end it lands on
            landMesh.worldToLocal(tmpPoint); // -> that node's local frame
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
      return true;
    },
  };
}
