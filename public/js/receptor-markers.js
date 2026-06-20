// Receptor "expression dots": when a receptor is focused (its legend row), this
// scatters a cluster of small glowing dots over the surface of every structure
// where that receptor is expressed, so you can see at a glance which regions
// carry it. It is the visual half of the receptor focus (the dimming of the rest
// of the brain is handled by the selection controller, see js/main.js); this
// module owns only the dots.
//
// The dots cling to each structure's surface and track it for free: they are a
// THREE.Points cloud sampled from the structure mesh's own geometry vertices
// (pushed a hair off the surface along the vertex normal) and parented to that
// mesh, so they inherit its explode / mirror / position transform with zero
// per-frame work, exactly like the selection halo and the circuit node-flash
// shells. Because a Points cloud is a child of the mesh, it also disappears
// automatically when the mesh is hidden ("See inside" cull, ?only=), so the dots
// never float over a region that isn't drawn.
//
// Additive blending + a crisp sparkle sprite make them read as shiny gems, not
// paint: a hard bright core with a tight glow and a faint 4-point star flare, so
// dense dots stay distinct points of light instead of merging into a stain. The
// dot colour is the receptor's sign colour (excitatory red / inhibitory blue /
// modulatory grey), lightened; each dot gets a little random brightness so the
// field reads as scattered faceted gems, and a gentle global pulse (tick) keeps
// them twinkling.
//
// No new dependency: three.js only.

import * as THREE from "three";

// Dot size in world units (sizeAttenuation on, so dots shrink with distance like
// real gems set in the surface).
const DOT_SIZE = 0.22;
// Dot density. Each lit structure gets a count scaled by its surface area (so a
// big cortical lobe and a tiny nucleus look about equally peppered), clamped to
// this range. A structure with fewer vertices than the chosen count just uses all
// of them.
const MIN_DOTS = 28;
const MAX_DOTS = 160;
// Roughly dots per world unit of bounding-sphere surface area; tuned so a small
// nucleus lands near MIN_DOTS and a cortical lobe near MAX_DOTS.
const DOT_DENSITY = 6;
// Push each dot this far off the surface along the vertex normal so it sits just
// proud of the mesh instead of z-fighting with it.
const SURFACE_OFFSET = 0.05;
// Per-dot brightness varies in this range (multiplied into the tint) so the gems
// glint at different strengths instead of forming a uniform wash.
const BRIGHT_MIN = 0.55;
const BRIGHT_MAX = 1.0;
// Gentle breathing of the whole dot field (opacity), so the markers shimmer. Kept
// bright at the trough so a focused receptor stays clearly visible.
const PULSE_MIN = 0.72;
const PULSE_MAX = 1.0;
const PULSE_PERIOD_MS = 1600;

const WHITE = new THREE.Color(0xffffff);

// A shiny-gem sprite, built once and shared by every dot material: a crisp bright
// core with a tight glow falloff, plus a faint 4-point star flare, so each dot
// twinkles like a faceted gem catching the light rather than reading as a soft
// smear. Drawn on a canvas (no image asset); additive blending turns the alpha
// into glow.
let SPRITE = null;
function dotSprite() {
  if (SPRITE) return SPRITE;
  const size = 64;
  const c = size / 2;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  // A compact bright core (the body of the gem), kept small so the star shine on
  // top stays the dominant read even when the dot is tiny on screen.
  const core = ctx.createRadialGradient(c, c, 0, c, c, c * 0.55);
  core.addColorStop(0.0, "rgba(255,255,255,1)");
  core.addColorStop(0.35, "rgba(255,255,255,0.85)");
  core.addColorStop(1.0, "rgba(255,255,255,0)");
  ctx.fillStyle = core;
  ctx.fillRect(0, 0, size, size);
  // Sparkle shine: a bold 4-point star over the core (composite "lighter"), the
  // arms wide enough at the centre to survive downscaling, so each dot reads as a
  // shiny twinkling gem rather than a flat round spot. The arms taper to points.
  ctx.globalCompositeOperation = "lighter";
  ctx.translate(c, c);
  const arm = () => {
    const g = ctx.createLinearGradient(-c, 0, c, 0);
    g.addColorStop(0.0, "rgba(255,255,255,0)");
    g.addColorStop(0.5, "rgba(255,255,255,1)");
    g.addColorStop(1.0, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    // A diamond-tapered streak: fat at the centre, points at the tips.
    ctx.beginPath();
    ctx.moveTo(-c, 0);
    ctx.lineTo(0, -5);
    ctx.lineTo(c, 0);
    ctx.lineTo(0, 5);
    ctx.closePath();
    ctx.fill();
  };
  arm();              // horizontal
  ctx.rotate(Math.PI / 2);
  arm();              // vertical
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  SPRITE = new THREE.CanvasTexture(canvas);
  return SPRITE;
}

/**
 * How many dots to scatter on a structure: scaled by its surface area so big and
 * small regions look about equally dense, clamped to [MIN_DOTS, MAX_DOTS].
 * @param {THREE.BufferGeometry} geometry
 * @returns {number}
 */
function dotCountFor(geometry) {
  if (!geometry.boundingSphere) geometry.computeBoundingSphere();
  const r = geometry.boundingSphere ? geometry.boundingSphere.radius : 1;
  const area = 4 * Math.PI * r * r;
  return Math.max(MIN_DOTS, Math.min(MAX_DOTS, Math.round(area * DOT_DENSITY)));
}

/**
 * Sample up to `n` surface points (local space) of a mesh's geometry, each pushed
 * a touch off the surface along its vertex normal so the dots sit just above it.
 * Spreads the picks evenly across the vertex list (a fixed stride) so the dots
 * scatter over the whole form rather than clustering wherever the vertices happen
 * to be dense. Falls back to the bare vertex position when no normals exist.
 * @param {THREE.BufferGeometry} geometry
 * @param {number} n
 * @returns {Float32Array} flat [x,y,z, ...] positions
 */
function sampleSurface(geometry, n) {
  const pos = geometry.getAttribute("position");
  const nrm = geometry.getAttribute("normal");
  const count = pos.count;
  const take = Math.min(n, count);
  const out = new Float32Array(take * 3);
  // Stride across the vertex array so the picks are spread, not the first `take`.
  const stride = Math.max(1, Math.floor(count / take));
  for (let i = 0; i < take; i++) {
    const v = (i * stride) % count;
    let x = pos.getX(v), y = pos.getY(v), z = pos.getZ(v);
    if (nrm) {
      x += nrm.getX(v) * SURFACE_OFFSET;
      y += nrm.getY(v) * SURFACE_OFFSET;
      z += nrm.getZ(v) * SURFACE_OFFSET;
    }
    out[i * 3] = x;
    out[i * 3 + 1] = y;
    out[i * 3 + 2] = z;
  }
  return out;
}

/**
 * Build the receptor-marker controller. One per scene, ticked once per frame in
 * the render loop. Driven by js/main.js: `show(meshes, color)` from a receptor
 * legend row, `hide()` when the focus leaves that receptor.
 * @param {{scene: THREE.Scene}} deps
 */
export function createReceptorMarkers({ scene }) {
  // One Points cloud per lit structure, parented to that structure's mesh.
  let clouds = []; // { points, material, meshes:Set } -- meshes tracked for matches()
  let litMeshes = new Set(); // the structure meshes currently lit (for matches())

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
     * Scatter glowing dots over every mesh in `structureMeshes`, in `color`
     * (a hex string, the receptor's sign colour). Replaces any current markers.
     * @param {THREE.Mesh[]} structureMeshes
     * @param {string} color
     */
    show(structureMeshes, color) {
      clear();
      const tint = new THREE.Color(color).lerp(WHITE, 0.35);
      const sprite = dotSprite();
      for (const mesh of structureMeshes) {
        if (!mesh.geometry) continue;
        const positions = sampleSurface(mesh.geometry, dotCountFor(mesh.geometry));
        if (positions.length === 0) continue;
        const geom = new THREE.BufferGeometry();
        geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        // Per-dot brightness variation (baked into a vertex-colour attribute) so
        // the gems glint at different strengths instead of a flat uniform field.
        const count = positions.length / 3;
        const colors = new Float32Array(count * 3);
        for (let i = 0; i < count; i++) {
          const b = BRIGHT_MIN + Math.random() * (BRIGHT_MAX - BRIGHT_MIN);
          colors[i * 3] = tint.r * b;
          colors[i * 3 + 1] = tint.g * b;
          colors[i * 3 + 2] = tint.b * b;
        }
        geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));
        const material = new THREE.PointsMaterial({
          vertexColors: true,
          size: DOT_SIZE,
          map: sprite,
          transparent: true,
          opacity: PULSE_MAX,
          depthWrite: false, // a glow must not occlude what's behind it
          blending: THREE.AdditiveBlending,
          sizeAttenuation: true,
        });
        const points = new THREE.Points(geom, material);
        points.raycast = () => {}; // pure decoration, never pickable
        // Parent to the structure so the dots inherit its transform (and vanish
        // when it is hidden), like the halo/flash shells.
        mesh.add(points);
        clouds.push({ points, material });
        litMeshes.add(mesh);
      }
    },

    /** Remove every dot. Safe to call when nothing is shown. */
    hide() {
      clear();
    },

    /**
     * True iff the dots are currently lighting exactly `meshSet` (the live isolate
     * set). Lets the viewer keep the markers while the focus is still this
     * receptor and drop them the moment it becomes anything else, the same way the
     * circuit animation tracks its arrow set. An empty/absent set never matches.
     * @param {Set<THREE.Mesh>|null|undefined} meshSet
     */
    matches(meshSet) {
      if (!meshSet || litMeshes.size === 0 || meshSet.size !== litMeshes.size) {
        return false;
      }
      for (const m of litMeshes) if (!meshSet.has(m)) return false;
      return true;
    },

    /** Whether any markers are currently shown. */
    get active() {
      return clouds.length > 0;
    },

    /** Pulse the dot field's brightness. Call once per frame in the render loop. */
    tick() {
      if (clouds.length === 0) return;
      const phase = (performance.now() % PULSE_PERIOD_MS) / PULSE_PERIOD_MS;
      const k = 0.5 - 0.5 * Math.cos(phase * Math.PI * 2); // 0..1..0
      const opacity = PULSE_MIN + (PULSE_MAX - PULSE_MIN) * k;
      for (const c of clouds) c.material.opacity = opacity;
    },
  };
}
