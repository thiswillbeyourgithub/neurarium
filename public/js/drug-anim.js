// Per-drug "what it does to the brain" animation. When a drug is focused (its
// Drugs legend/list row, a drug search result), this scatters glowing gem dots
// over the regions each of the drug's targets sits in, coloured by that binding's
// net effect (boost = emerald, block = rose, modulate = violet, from the data's
// drug_effect_colors), and animates each cloud so the effect reads as motion:
//
//   - boost  (agonist / reuptake inhibitor / releaser / PAM / enzyme inhibitor):
//     the dots swell and brighten in a quick, strong pulse, as if turning the
//     region "up".
//   - block  (antagonist / inverse agonist / NAM / channel blocker): the dots
//     throb dim and small in a slow, shallow pulse, as if damping the region
//     "down".
//   - modulate (partial agonist / generic modulator): a gentle middling shimmer.
//
// It is the visual half of a drug focus (the dimming of the rest of the brain is
// handled by the selection controller in js/main.js via setCircuit, exactly like
// a receptor focus); this module owns only the animated dots. It reuses the gem
// cloud builder from js/receptor-markers.js (buildGemCloud), so the gem look is
// defined in one place; here we add the per-binding colour + the per-effect pulse.
//
// One controller per scene, ticked once per frame in the render loop (like the
// intro/focus tweens, the circuit pulse and the receptor markers). No new
// dependency: three.js only.

import { buildGemCloud, GEM_DOT_SIZE } from "./receptor-markers.js";

// Per-effect pulse character. `period` ms is the breathing cycle; opacity swings
// between [opMin, opMax] and the dot size between [sizeMin, sizeMax] * GEM_DOT_SIZE
// over that cycle. Boost is fast/bright/swelling, block slow/dim/shrunk, modulate
// in between, so the three effects read distinctly even in one drug's view.
const PULSE = {
  boost: { period: 1050, opMin: 0.55, opMax: 1.0, sizeMin: 0.95, sizeMax: 1.55 },
  block: { period: 2100, opMin: 0.22, opMax: 0.66, sizeMin: 0.7, sizeMax: 1.0 },
  modulate: { period: 1550, opMin: 0.5, opMax: 0.9, sizeMin: 0.85, sizeMax: 1.2 },
};
const FALLBACK = PULSE.modulate;

/**
 * Build the per-drug animation controller.
 * @param {{scene: THREE.Scene}} _deps  (kept for symmetry; clouds parent to the
 *   structure meshes, not the scene, so the scene isn't needed directly)
 */
export function createDrugAnimation(_deps = {}) {
  // One gem cloud per (binding, mesh): { points, material, baseSize, pulse,
  // phase }. `litMeshes` is the union of structure meshes lit (for matches()).
  let clouds = [];
  let litMeshes = new Set();

  function clear() {
    for (const c of clouds) {
      c.points.parent?.remove(c.points);
      c.points.geometry.dispose();
      c.material.dispose();
    }
    clouds = [];
    litMeshes = new Set();
  }

  return {
    /**
     * Light + animate every region a drug acts on. For each binding, a gem cloud
     * in the binding's effect colour is scattered on each region carrying that
     * target, pulsing per the action's effect. Replaces any current animation.
     * @param {object} drug  a normalized drug record (its resolved `bindings`,
     *   each with `structureIds`, `effect` and `effectColor`)
     * @param {Map<string, THREE.Mesh>} meshById  structure id -> mesh
     */
    show(drug, meshById) {
      clear();
      let phaseSeed = 0;
      for (const binding of drug.bindings || []) {
        const pulse = PULSE[binding.effect] || FALLBACK;
        for (const id of binding.structureIds || []) {
          const mesh = meshById.get(id);
          if (!mesh) continue;
          const cloud = buildGemCloud(mesh, binding.effectColor);
          if (!cloud) continue;
          // Spread the starting phases so the regions don't all pulse in lockstep
          // (a wave of activity reads better than a single global blink).
          clouds.push({
            ...cloud,
            baseSize: cloud.material.size,
            pulse,
            phase: (phaseSeed % 8) / 8,
          });
          litMeshes.add(mesh);
          phaseSeed += 1;
        }
      }
    },

    /** Remove every dot. Safe to call when nothing is shown. */
    hide() {
      clear();
    },

    /**
     * True iff the animation is currently lighting exactly `meshSet` (the live
     * isolate set), so the viewer can keep it while the focus is still this drug
     * and drop it the moment the focus becomes anything else, the same way the
     * receptor markers + circuit pulse track their sets. An empty set never matches.
     * @param {Set<THREE.Mesh>|null|undefined} meshSet
     */
    matches(meshSet) {
      if (!meshSet || litMeshes.size === 0 || meshSet.size !== litMeshes.size) {
        return false;
      }
      for (const m of litMeshes) if (!meshSet.has(m)) return false;
      return true;
    },

    /** Whether any drug animation is currently shown. */
    get active() {
      return clouds.length > 0;
    },

    /** Advance the per-effect pulses. Call once per frame in the render loop. */
    tick() {
      if (clouds.length === 0) return;
      const now = performance.now();
      for (const c of clouds) {
        const p = c.pulse;
        const phase = ((now / p.period) + c.phase) % 1;
        const k = 0.5 - 0.5 * Math.cos(phase * Math.PI * 2); // 0..1..0
        c.material.opacity = p.opMin + (p.opMax - p.opMin) * k;
        c.material.size = c.baseSize * (p.sizeMin + (p.sizeMax - p.sizeMin) * k);
      }
    },
  };
}
