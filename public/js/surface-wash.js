// Surface "wash of light": a ripple of light that spreads across a structure's
// surface from an origin point, like a drop falling on water. It is the shared
// primitive behind two effects:
//
//   - the circuit node "echo" (js/circuit-anim.js): when a traveling bead lands on
//     its target region, a wash spreads outward from the exact point it hit, in the
//     pathway's own colour, so the hand-off reads as the surface lighting up *from
//     where the signal arrived* rather than the whole region blinking inert.
//   - the per-drug surface glow (js/drug-anim.js): each lit region breathes a
//     looping wash in its binding's effect colour (boost / block / modulate),
//     under the twinkling gem dots, so a focused drug's regions feel alive.
//
// Mechanism (a shader, no geometry / no triangles added to the form): a thin shell
// reusing the structure mesh's own geometry (the same geometry-reuse trick as the
// selection halo and the circuit node-flash), parented to the mesh so it tracks the
// explode / mirror transform and vanishes when the mesh is hidden, for free. The
// shell is pushed a hair proud of the surface along its normals and rendered
// additive, FrontSide, so it paints over the visible face. Its fragment shader
// lights a soft wavefront ring at radius `uRadius` from a local-space `uOrigin`,
// with a short glowing trail behind the front; driving `uRadius` outward and fading
// `uStrength` plays the ripple. Because the wash is pure colour added before
// nothing (it is its own pass), it never deforms the form, exactly like the cortex
// swirl is painted in the shader rather than modelled.
//
// No new dependency: three.js only.

import * as THREE from "three";

const WHITE = new THREE.Color(0xffffff);

// How far past the structure's own bounding radius the wavefront travels, as a
// multiple of that radius: 2x reaches from any surface point to the opposite side,
// so a ripple seeded anywhere on the surface still sweeps the whole form.
const MAX_RADIUS_FACTOR = 2.0;
// Wavefront softness (the lit ring's half-width) as a fraction of the bounding
// radius: wide enough to read as a wash, not a hard line.
const BAND_FACTOR = 0.5;
// How far proud of the surface the shell floats (fraction of bounding radius), so
// it sits just above the real mesh instead of z-fighting with it.
const INFLATE_FACTOR = 0.015;
// Lighten the source colour toward white so the wash glows rather than tinting.
const WHITE_MIX = 0.4;

// Vertex shader: pass the *unscaled* geometry-local position so the fragment can
// measure distance from the local-space origin, and inflate the rendered shell a
// touch along the surface normal so it floats just above the mesh.
const VERT = `
  uniform float uInflate;
  varying vec3 vLocal;
  void main() {
    vLocal = position;
    vec3 inflated = position + normal * uInflate;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(inflated, 1.0);
  }
`;

// Fragment shader: a soft expanding ring at uRadius from uOrigin (`front`) plus a
// short trail glowing just behind the front and fading inward (`trail`), the whole
// scaled by uStrength. Fragments ahead of the front (and faint ones) are discarded
// so the wash is only the moving wavefront + its wake, never a flat fill.
const FRAG = `
  uniform vec3 uOrigin;
  uniform vec3 uColor;
  uniform float uRadius;
  uniform float uBand;
  uniform float uStrength;
  varying vec3 vLocal;
  void main() {
    float d = distance(vLocal, uOrigin);
    float front = 1.0 - smoothstep(0.0, uBand, abs(d - uRadius));
    float trail = step(d, uRadius) * exp(-(uRadius - d) / (uBand * 2.5)) * 0.45;
    float a = (front + trail) * uStrength;
    if (a <= 0.002) discard;
    gl_FragColor = vec4(uColor * a, a);
  }
`;

/**
 * Build one wash shell over a structure mesh and parent it to that mesh. The shell
 * starts invisible (strength 0); the caller drives the ripple each frame with
 * `setWave` (and `setOrigin` / `setColor` to retarget / recolour it). Returns the
 * controller, or null if the mesh has no usable geometry. The caller owns disposal
 * (`dispose()`); the geometry is the mesh's own and is *not* disposed here.
 * @param {THREE.Mesh} mesh
 * @param {string} colorHex
 * @returns {{
 *   shell: THREE.Mesh, maxRadius: number, center: THREE.Vector3,
 *   setColor(hex: string): void, setOrigin(v: THREE.Vector3): void,
 *   setWave(radius: number, strength: number): void, dispose(): void
 * }|null}
 */
export function buildWashShell(mesh, colorHex) {
  const geom = mesh.geometry;
  if (!geom) return null;
  if (!geom.boundingSphere) geom.computeBoundingSphere();
  const bs = geom.boundingSphere;
  const r = bs ? bs.radius : 1;
  const center = bs ? bs.center.clone() : new THREE.Vector3();
  // uColor holds this Color object by reference, so setColor() mutating it in place
  // recolours the live wash (used by the circuit echo, which takes each arrow's
  // colour as the bead lands).
  const tint = new THREE.Color(colorHex).lerp(WHITE, WHITE_MIX);
  const uniforms = {
    uOrigin: { value: center.clone() },
    uColor: { value: tint },
    uRadius: { value: 0 },
    uBand: { value: r * BAND_FACTOR },
    uStrength: { value: 0 },
    uInflate: { value: r * INFLATE_FACTOR },
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: false, // a glow must not occlude what is behind it
    blending: THREE.AdditiveBlending,
    side: THREE.FrontSide, // paint over the visible (camera-facing) face
  });
  const shell = new THREE.Mesh(geom, material); // reuse geometry, like the halo
  shell.visible = false;
  shell.raycast = () => {}; // pure decoration, never pickable
  mesh.add(shell);
  return {
    shell,
    material,
    maxRadius: r * MAX_RADIUS_FACTOR,
    center,
    /** Recolour the live wash (lightened toward white), in place. */
    setColor(hex) {
      tint.set(hex).lerp(WHITE, WHITE_MIX);
    },
    /** Move the ripple's origin (a point in the mesh's local / geometry space). */
    setOrigin(v) {
      uniforms.uOrigin.value.copy(v);
    },
    /**
     * Set the wavefront radius + overall brightness for this frame. A strength at
     * or below ~0 hides the shell, so an idle wash costs nothing.
     */
    setWave(radius, strength) {
      uniforms.uRadius.value = radius;
      uniforms.uStrength.value = strength;
      shell.visible = strength > 0.001;
    },
    dispose() {
      shell.parent?.remove(shell);
      material.dispose();
      // geometry is the mesh's own (shared); do NOT dispose it here.
    },
  };
}

/**
 * Strength envelope over a ripple's normalized life [0, 1]: a smooth rise to a
 * peak then a fall (a half-sine), so a wash fades in as it leaves the origin and
 * dissolves as the front reaches the far edge. Shared so the circuit echo and the
 * drug wash pulse identically. Returns 0 outside (0, 1).
 * @param {number} progress
 * @returns {number}
 */
export function washStrength(progress) {
  if (progress <= 0 || progress >= 1) return 0;
  return Math.sin(progress * Math.PI);
}
