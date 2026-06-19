// Turns a shape payload (shapes/<id>.json) into a three.js mesh.
//
// Real anatomical meshes can be swapped in later, but for now each region is an
// organic "blob": an icosphere whose vertices are pushed in/out by a smooth,
// deterministic noise field and then scaled to the region's ellipsoid radii.
// Keeping the deformation here (rather than baking vertices into the data files)
// means the data files stay tiny and the look can be retuned without
// regenerating anything.

import * as THREE from "three";

// Cheap deterministic integer hash -> uint32, seeded so each structure's
// surface is unique but stable. Shared by the gradient picker below.
function hash3(ix, iy, iz, seed) {
  let h = ix * 374761393 + iy * 668265263 + iz * 2147483647 + seed * 982451653;
  h = (h ^ (h >>> 13)) * 1274126177;
  h = h ^ (h >>> 16);
  return h >>> 0;
}

// Perlin's 12 edge-of-cube gradient directions (plus 4 repeats to fill 16, the
// standard trick so a 4-bit hash selects one). `gradDot` returns the chosen
// gradient dotted with the offset vector without ever building a Vector3.
function gradDot(hash, x, y, z) {
  switch (hash & 15) {
    case 0:  return  x + y;
    case 1:  return -x + y;
    case 2:  return  x - y;
    case 3:  return -x - y;
    case 4:  return  x + z;
    case 5:  return -x + z;
    case 6:  return  x - z;
    case 7:  return -x - z;
    case 8:  return  y + z;
    case 9:  return -y + z;
    case 10: return  y - z;
    case 11: return -y - z;
    case 12: return  x + y;
    case 13: return -y + z;
    case 14: return -x + y;
    default: return -y - z;
  }
}

/**
 * Deterministic 3D gradient (Perlin) noise, roughly in [-1, 1]. Self-contained
 * (no external noise lib) so the project keeps zero JS deps beyond three.js.
 *
 * Why gradient noise and not the simpler value noise: the surface displacement
 * folds this field into sharp ridges (see fractalNoise's `ridged` path) to fake
 * gyri/folia. Value noise is only smoothstep-interpolated between random lattice
 * *values*, so its ridges crease along the cubic lattice and the mesh looks like
 * a cut gemstone. Gradient noise interpolates lattice *gradients* with a quintic
 * fade (C2 continuous), so its zero-set (where the ridges live) is a smooth,
 * winding curve, which is what makes the ridged surface flow like real cortex.
 *
 * @param {number} x
 * @param {number} y
 * @param {number} z
 * @param {number} seed
 * @returns {number}
 */
function gradientNoise(x, y, z, seed) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = x - xi, yf = y - yi, zf = z - zi;
  // Quintic fade (Perlin "improved noise"): zero 1st and 2nd derivatives at the
  // cell boundaries, so no creases leak in from the interpolation itself.
  const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
  const u = fade(xf), v = fade(yf), w = fade(zf);
  const lerp = (a, b, t) => a + (b - a) * t;
  const corner = (cx, cy, cz, fx, fy, fz) =>
    gradDot(hash3(xi + cx, yi + cy, zi + cz, seed), fx, fy, fz);

  const x00 = lerp(corner(0, 0, 0, xf, yf, zf),       corner(1, 0, 0, xf - 1, yf, zf), u);
  const x10 = lerp(corner(0, 1, 0, xf, yf - 1, zf),   corner(1, 1, 0, xf - 1, yf - 1, zf), u);
  const x01 = lerp(corner(0, 0, 1, xf, yf, zf - 1),   corner(1, 0, 1, xf - 1, yf, zf - 1), u);
  const x11 = lerp(corner(0, 1, 1, xf, yf - 1, zf - 1), corner(1, 1, 1, xf - 1, yf - 1, zf - 1), u);
  const y0 = lerp(x00, x10, v), y1 = lerp(x01, x11, v);
  return lerp(y0, y1, w);
}

// How many noise lattice cells wrap around the unit sphere. Higher = more,
// smaller lumps. Chosen to read as gyri-ish bumpiness without looking noisy.
const NOISE_FREQUENCY = 2.4;

/**
 * Fractal (multi-octave) version of {@link gradientNoise}. Summing several octaves
 * of noise at doubling frequency and halving amplitude (classic fBm) turns the
 * single big lumps of one-octave noise into layered detail: a broad form with
 * progressively finer wrinkles on top, which is what keeps a cortical lobe from
 * looking like a smooth potato or a spongy blob.
 *
 * With `ridged`, each octave is folded as `1 - |n|` and recentred, so the
 * surface gains sharp raised creases along the noise's zero-crossings instead of
 * rounded bumps. Those creases read as the gyri/sulci of cortex and the thin
 * parallel folia of the cerebellum, the single biggest thing distinguishing a
 * brain surface from a lump of dough.
 *
 * @param {number} nx   Unit-sphere x (~[-1,1]); base frequency is applied here.
 * @param {number} ny   Unit-sphere y.
 * @param {number} nz   Unit-sphere z.
 * @param {number} seed
 * @param {number} octaves     How many noise layers to sum (1 = single octave).
 * @param {boolean} ridged     Fold each octave into sharp ridges (cortex/folia).
 * @param {number} frequency   Base lattice frequency (higher = smaller folds).
 * @param {number[]} aniso     Per-axis frequency multipliers [ax, ay, az]. Equal
 *   values give isotropic, meandering folds (cortex). Skewing them stretches the
 *   ridges along the low-multiplier axes: e.g. a high y multiplier with low x/z
 *   stacks near-parallel transverse bands, which is what makes the cerebellum's
 *   fine folia instead of brain-like gyri.
 * @returns {number} Roughly in [-1, 1], 0-mean for the smooth case.
 */
function fractalNoise(nx, ny, nz, seed, octaves, ridged, frequency, aniso) {
  const [ax, ay, az] = aniso;
  let x = nx;
  let y = ny;
  let z = nz;
  // Domain warp (ridged only): before sampling, nudge the point by a
  // *low-frequency* noise vector (independent of the ridge frequency). Plain
  // value-noise ridges snap to its cubic integer lattice and look crystalline;
  // warping the input in unit space makes the ridge lines meander and branch
  // broadly like real gyri/folia. Smooth blobs don't reveal the lattice, so
  // they skip this to stay cheap.
  if (ridged) {
    const wf = 1.6; // warp sampling frequency: broad, slow undulations
    const w = 0.55; // warp strength in unit-sphere space
    x += w * gradientNoise(nx * wf + 11.3, ny * wf + 4.7, nz * wf + 2.1, seed + 313);
    y += w * gradientNoise(nx * wf + 5.2, ny * wf + 9.1, nz * wf + 7.4, seed + 727);
    z += w * gradientNoise(nx * wf + 1.7, ny * wf + 3.3, nz * wf + 12.9, seed + 911);
  }
  let amplitude = 1;
  let freq = frequency;
  let sum = 0;
  let norm = 0;
  // Ridged-multifractal weight: how strongly the *previous* octave's ridge was
  // raised here (1 on a crest line, ~0 in a trough). Starts at 1 so the first
  // octave is unweighted. Each finer octave is multiplied by it, so high
  // frequencies only crease where a coarser fold already rises and troughs stay
  // smooth, instead of every octave laying sharp creases everywhere (the old
  // "crinkled foil" look that read as faceting). Ignored for smooth blobs.
  let weight = 1;
  for (let o = 0; o < octaves; o++) {
    // Offset the seed per octave so layers are decorrelated, not scaled copies.
    // Per-axis aniso skews the sampling so ridges can be stretched into bands.
    let n = gradientNoise(x * freq * ax, y * freq * ay, z * freq * az, seed + o * 101);
    if (ridged) {
      // Uncentred ridge strength in [0, 1]: 1 along the base noise's zero set,
      // 0 at its extremes. Gate this octave by the coarser octave's strength,
      // then recentre to [-1, 1] so the field still pushes the surface both in
      // and out (zero-mean) rather than only inflating it.
      const r = 1 - Math.abs(n);
      n = (2 * r - 1) * weight;
      weight = Math.min(1, r * 2);
    }
    sum += amplitude * n;
    norm += amplitude;
    amplitude *= 0.5;
    freq *= 2;
  }
  return sum / norm;
}

/**
 * Build a structure's geometry from its shape payload. Dispatches on
 * `shape.type` so different regions can use different geometry models:
 *   - "blob"  (default): a noise-deformed ellipsoid (buildBlobGeometry).
 *   - "curve": a tapered tube swept along a 3D spline (buildCurveGeometry),
 *     for strongly curved structures the ellipsoid can't represent (e.g. the
 *     C-shaped caudate nucleus).
 *   - "composite": a union of several sub-shapes merged into one mesh
 *     (buildCompositeGeometry), for regions that aren't a single convex lump
 *     (e.g. the cerebellum's two hemispheres + vermis).
 * @param {object} shape  Shape payload from shapes/<id>.json.
 * @returns {THREE.BufferGeometry}
 */
export function buildGeometry(shape) {
  if (shape.type === "curve") return buildCurveGeometry(shape);
  if (shape.type === "composite") return buildCompositeGeometry(shape);
  return buildBlobGeometry(shape);
}

// Inter-region "jigsaw" clipping. When two neighbouring regions are sized to
// overlap (the lobes especially, so their union reads as one continuous cortex),
// the overlap shows up as one colour's surface poking through the other, which
// reads as "two balls jammed together" rather than puzzle pieces. To fix that,
// generate_data.py emits a `clip_planes` list on each blob: the bisecting planes
// against its overlapping same-group neighbours. Each plane clamps any vertex on
// the neighbour's side back onto it, so adjacent regions get flat mating faces
// and tile flush at explode 0, then separate like jigsaw pieces as they explode.
// This flag is the A/B switch: `enabled:false` ignores `clip_planes` entirely
// (regions overlap as before) without needing to regenerate the data. The
// axis-aligned `clip` (the lobes' flat medial wall) is independent and always
// applied, so toggling this never reopens the longitudinal fissure.
const JIGSAW_CLIP = { enabled: true };

/**
 * Build the deformed-ellipsoid geometry for a "blob" shape payload.
 *
 * The base form is an ellipsoid (per-axis `radii`); its surface is then pushed
 * in/out by {@link fractalNoise}. The optional fields let each region pick a
 * surface character instead of every blob sharing one lumpy look:
 *
 * @param {object} shape
 * @param {number[]} shape.radii   Ellipsoid half-extents (rx, ry, rz).
 * @param {number} shape.seed      Deterministic noise seed.
 * @param {number} shape.detail    Icosphere subdivision (higher = smoother base,
 *   needed so fine ridged folds have enough vertices to resolve).
 * @param {number} shape.noise     Displacement amplitude (fraction of radius).
 * @param {number} [shape.octaves=1]   fBm octaves; >1 layers finer wrinkles on
 *   the broad form (cortex), 1 keeps a clean nucleus.
 * @param {boolean} [shape.ridged=false]  Crease the noise into gyri/folia ridges.
 * @param {number} [shape.frequency]  Lattice frequency override (smaller folds
 *   at higher values); defaults to {@link NOISE_FREQUENCY}.
 * @param {number[]} [shape.aniso=[1,1,1]]  Per-axis frequency skew; unequal
 *   values stretch ridges into near-parallel bands (cerebellar folia).
 * @param {object} [shape.clip]  Axis-aligned flat cut planes, any of
 *   `{xmin,xmax,ymin,ymax,zmin,zmax}`: vertices past a bound are clamped onto it,
 *   producing a flat face. Used to give the cortical lobes a flat medial wall at
 *   the midline so the two hemispheres meet along the longitudinal fissure.
 * @param {{point:number[], normal:number[]}[]} [shape.clip_planes]  Arbitrary
 *   (non-axis-aligned) cut planes in *local* space: each is a `point` on the
 *   plane and a unit `normal` pointing toward the half-space to remove. A vertex
 *   on the removed side is projected onto the plane, flattening that side into a
 *   mating face. generate_data.py fills these with the bisecting planes between a
 *   region and its overlapping same-group neighbours so adjacent regions tile
 *   flush (the jigsaw look); honoured only when {@link JIGSAW_CLIP}.enabled.
 * @returns {THREE.BufferGeometry}
 */
function buildBlobGeometry(shape) {
  const {
    radii,
    seed,
    detail,
    noise,
    octaves = 1,
    ridged = false,
    frequency = NOISE_FREQUENCY,
    aniso = [1, 1, 1],
    clip = null,
    clip_planes: clipPlanes = null,
  } = shape;
  // Start from a unit icosphere so vertices are evenly distributed.
  const geometry = new THREE.IcosahedronGeometry(1, detail);
  const pos = geometry.attributes.position;
  const v = new THREE.Vector3();

  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i).normalize();
    // Displace along the radial direction by the noise field, then stretch to
    // the per-axis radii to get an organic ellipsoid. The base frequency is
    // applied inside fractalNoise so its domain warp can run in unit space.
    const d = 1 + noise * fractalNoise(
      v.x,
      v.y,
      v.z,
      seed,
      octaves,
      ridged,
      frequency,
      aniso,
    );
    let px = v.x * d * radii[0];
    let py = v.y * d * radii[1];
    let pz = v.z * d * radii[2];
    if (clip) {
      // Clamp onto each requested plane: everything beyond the bound collapses
      // onto it, flattening that side of the blob into a face.
      if (clip.xmin !== undefined) px = Math.max(px, clip.xmin);
      if (clip.xmax !== undefined) px = Math.min(px, clip.xmax);
      if (clip.ymin !== undefined) py = Math.max(py, clip.ymin);
      if (clip.ymax !== undefined) py = Math.min(py, clip.ymax);
      if (clip.zmin !== undefined) pz = Math.max(pz, clip.zmin);
      if (clip.zmax !== undefined) pz = Math.min(pz, clip.zmax);
    }
    if (clipPlanes && JIGSAW_CLIP.enabled) {
      // Half-space clip against each bisecting plane: a vertex on the removed
      // side (positive signed distance along the unit normal) is pushed back
      // onto the plane, so the overlap with that neighbour collapses into a flat
      // mating face. Planes are applied in sequence; for the near-orthogonal
      // seams between adjacent regions the order does not matter in practice.
      for (const plane of clipPlanes) {
        const [ox, oy, oz] = plane.point;
        const [nx, ny, nz] = plane.normal;
        const signed = (px - ox) * nx + (py - oy) * ny + (pz - oz) * nz;
        if (signed > 0) {
          px -= signed * nx;
          py -= signed * ny;
          pz -= signed * nz;
        }
      }
    }
    pos.setXYZ(i, px, py, pz);
  }
  geometry.computeVertexNormals();
  return geometry;
}

/**
 * Build a "composite" geometry: several sub-shapes merged into a single mesh.
 *
 * Each part is itself a shape payload (blob/curve/composite, resolved through
 * {@link buildGeometry}) plus an optional rigid placement within the parent:
 * `offset` [x,y,z], `scale` [sx,sy,sz], `rotate` [rx,ry,rz] (Euler radians). The
 * parts' triangles are concatenated (a visual union; interiors stay hidden under
 * opaque shading), letting a region be built from multiple lumps instead of one
 * convex ellipsoid, e.g. the cerebellum = left hemisphere + right hemisphere +
 * vermis. Self-contained float concatenation, so no BufferGeometryUtils dep.
 *
 * @param {{parts: object[]}} shape  Each part: a shape payload with optional
 *   `offset`/`scale`/`rotate`.
 * @returns {THREE.BufferGeometry}
 */
function buildCompositeGeometry(shape) {
  const chunks = [];
  let total = 0;
  const matrix = new THREE.Matrix4();
  for (const part of shape.parts) {
    // Recurse so a part can be any shape type, then flatten any indexed
    // geometry (e.g. a curve part) so all chunks are plain position triples.
    let geo = buildGeometry(part);
    if (geo.index) geo = geo.toNonIndexed();
    const off = part.offset || [0, 0, 0];
    const scl = part.scale || [1, 1, 1];
    const rot = part.rotate || [0, 0, 0];
    matrix.compose(
      new THREE.Vector3(off[0], off[1], off[2]),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(rot[0], rot[1], rot[2])),
      new THREE.Vector3(scl[0], scl[1], scl[2]),
    );
    geo.applyMatrix4(matrix);
    const arr = geo.getAttribute("position").array;
    chunks.push(arr);
    total += arr.length;
  }

  const merged = new Float32Array(total);
  let offset = 0;
  for (const arr of chunks) {
    merged.set(arr, offset);
    offset += arr.length;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(merged, 3));
  // Recompute normals on the merged surface so lighting is consistent across
  // parts (each part's own normals are discarded with its other attributes).
  geometry.computeVertexNormals();
  return geometry;
}

/**
 * Build a tapered, curved tube geometry for a "curve" shape payload.
 *
 * Sweeps a circular cross-section of varying radius along a smooth 3D spline
 * (Catmull-Rom through `points`, head -> tail) and applies the same value-noise
 * wobble used by the blobs so the surface still looks organic. This is what
 * lets a structure be genuinely C-shaped (e.g. the caudate's bulbous head
 * curling into a thin tail) instead of a convex ellipsoid. The mesh is built in
 * local coordinates centered near the origin, exactly like the blobs, so
 * positioning and the explode layout treat it identically.
 *
 * @param {{points:number[][], profile:number[], seed:number, noise:number,
 *          radial_segments?:number, tubular_segments?:number}} shape
 *   `points`  spine control points [[x,y,z], ...] from head to tail.
 *   `profile` tube radius sampled head -> tail (linearly interpolated along
 *             the spine), so the head can be fat and the tail thin.
 * @returns {THREE.BufferGeometry}
 */
function buildCurveGeometry(shape) {
  const {
    points,
    profile,
    seed,
    noise,
    radial_segments: radialSegments = 12,
    tubular_segments: tubularSegments = 80,
  } = shape;

  // centripetal Catmull-Rom avoids the self-intersections/overshoot a uniform
  // spline can produce on a tightly curled path like the caudate.
  const curve = new THREE.CatmullRomCurve3(
    points.map((p) => new THREE.Vector3(p[0], p[1], p[2])),
    false,
    "centripetal",
  );
  const frames = curve.computeFrenetFrames(tubularSegments, false);

  // Radius at spine fraction t in [0,1], linearly interpolated from `profile`.
  const radiusAt = (t) => {
    const f = t * (profile.length - 1);
    const i0 = Math.min(profile.length - 1, Math.floor(f));
    const i1 = Math.min(profile.length - 1, i0 + 1);
    return profile[i0] + (profile[i1] - profile[i0]) * (f - i0);
  };

  const positions = [];
  const center = new THREE.Vector3();
  const dir = new THREE.Vector3();
  // Build a ring of (radialSegments+1) vertices at each of (tubularSegments+1)
  // stations along the spine. The seam vertex is duplicated (j = 0 and
  // j = radialSegments) to keep the index logic simple.
  for (let i = 0; i <= tubularSegments; i++) {
    const t = i / tubularSegments;
    curve.getPointAt(t, center);
    const normal = frames.normals[i];
    const binormal = frames.binormals[i];
    const baseRadius = radiusAt(t);
    for (let j = 0; j <= radialSegments; j++) {
      const v = (j / radialSegments) * Math.PI * 2;
      // Unit direction on the cross-section circle (normal/binormal plane).
      dir.copy(normal).multiplyScalar(Math.cos(v)).addScaledVector(binormal, Math.sin(v));
      const n = 1 + noise * gradientNoise(
        (center.x + dir.x) * NOISE_FREQUENCY,
        (center.y + dir.y) * NOISE_FREQUENCY,
        (center.z + dir.z) * NOISE_FREQUENCY,
        seed,
      );
      const r = baseRadius * n;
      positions.push(center.x + dir.x * r, center.y + dir.y * r, center.z + dir.z * r);
    }
  }

  const indices = [];
  const ring = radialSegments + 1;
  for (let i = 1; i <= tubularSegments; i++) {
    for (let j = 1; j <= radialSegments; j++) {
      const a = ring * (i - 1) + (j - 1);
      const b = ring * i + (j - 1);
      const c = ring * i + j;
      const d = ring * (i - 1) + j;
      indices.push(a, b, d, b, c, d);
    }
  }

  // Round end caps. Without them the tube reads as a cut pipe with hollow,
  // flat openings (visible on the caudate's bulbous head). We add one apex
  // vertex just past each end of the spine, pushed outward along the tangent by
  // the local radius so the cap is a rounded dome, then fan-triangulate the end
  // ring to it. The tail's near-zero profile makes its cap a fine point; the
  // fatter head gets a rounded bulb.
  // Apex extension as a fraction of the local radius: <1 keeps the cap a
  // shallow rounded dome rather than a long cone (a full radius looked pointed).
  const CAP_DOME = 0.6;
  const tangent = new THREE.Vector3();
  const capApex = (t, sign) => {
    curve.getPointAt(t, center);
    curve.getTangentAt(t, tangent);
    const apex = center.clone().addScaledVector(tangent, sign * radiusAt(t) * CAP_DOME);
    positions.push(apex.x, apex.y, apex.z);
    return positions.length / 3 - 1; // index of the just-pushed apex
  };

  // Head cap: apex behind ring 0 (against the tangent), fan over the first ring.
  const headApex = capApex(0, -1);
  for (let j = 1; j <= radialSegments; j++) {
    indices.push(headApex, j - 1, j);
  }
  // Tail cap: apex past the last ring (along the tangent), winding reversed so
  // the cap faces outward.
  const tailApex = capApex(1, 1);
  const lastBase = ring * tubularSegments;
  for (let j = 1; j <= radialSegments; j++) {
    indices.push(tailApex, lastBase + j, lastBase + j - 1);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setIndex(indices);
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  return geometry;
}

/**
 * Reflect a geometry across the sagittal (x = 0) plane, in place.
 *
 * This is what makes the left member of a symmetric pair a *true mirror* of the
 * right one (so an asymmetric form like the C-shaped caudate genuinely flips
 * sides, and a lobe's gyral pattern mirrors) instead of being an identical copy
 * merely placed at -x. Generated data marks such structures with `mirror: true`
 * (see generate_data.py); midline structures are never marked, so they are
 * left untouched.
 *
 * A pure reflection inverts triangle winding, which would turn every face
 * inside out and break the lighting, so we also reverse the winding and
 * recompute normals. Handles both indexed (curve) and non-indexed
 * (blob/composite) geometries.
 * @param {THREE.BufferGeometry} geometry
 * @returns {THREE.BufferGeometry} the same geometry, mutated
 */
function mirrorGeometryX(geometry) {
  geometry.scale(-1, 1, 1);
  if (geometry.index) {
    // Reverse each triangle's winding by swapping its 2nd and 3rd indices.
    const idx = geometry.index.array;
    for (let i = 0; i < idx.length; i += 3) {
      const tmp = idx[i + 1];
      idx[i + 1] = idx[i + 2];
      idx[i + 2] = tmp;
    }
    geometry.index.needsUpdate = true;
  } else {
    // Non-indexed: swap the 2nd and 3rd vertex of every triangle, across all
    // attributes, so the winding reverses while each vertex keeps its own data.
    for (const attr of Object.values(geometry.attributes)) {
      const a = attr.array;
      const n = attr.itemSize;
      for (let tri = 0; tri < a.length; tri += n * 3) {
        for (let k = 0; k < n; k++) {
          const i1 = tri + n + k;
          const i2 = tri + 2 * n + k;
          const tmp = a[i1];
          a[i1] = a[i2];
          a[i2] = tmp;
        }
      }
      attr.needsUpdate = true;
    }
  }
  geometry.computeVertexNormals();
  return geometry;
}

// --- Procedural cortex "curl" normal map -----------------------------------
// The cortex's surface pattern is added as a *shading* detail (a procedural bump
// that perturbs the per-fragment normal) instead of as geometry. Keeping the
// mesh smooth means no faceting, while the lighting still shows the pattern, and
// it costs no extra triangles or texture assets. Only the cortical lobes use it
// (deep nuclei stay smooth; the cerebellum keeps its own anisotropic folia).
//
// The pattern is a stylized field of "little curls" rather than realistic gyri:
// a domain-warped fractal-noise field passed through sin() so its iso-bands
// close into swirling, fingerprint-like loops (the warp is what bends straight
// bands into curls). The shaded normal is then bent along the field's gradient,
// so the curls read as gentle raised swirls. Tunables (edit + reload to retune):
const GYRUS_BUMP = {
  enabled: true, // false skips the shader injection entirely (true off switch)
  scale: 0.6, // how hard the shaded normal is bent (0 = flat, but still compiled)
  freq: 1.1, // overall pattern frequency in local units (higher = smaller curls)
  warp: 3.0, // domain-warp strength: how much straight bands swirl into curls
  bands: 0.9, // sine bands per noise unit: how tightly the curl lines pack
  octaves: 2, // fractal-noise layers feeding the warp + base field (low = clean loops)
  eps: 0.02, // finite-difference step used to take the height gradient
};

// Format a JS number as a GLSL float literal (always with a decimal point so it
// is typed as a float, never an int).
const glslFloat = (x) => {
  const s = Number(x).toString();
  return /[.e]/.test(s) ? s : s + ".0";
};

/**
 * `onBeforeCompile` hook that injects a procedural ridged-fBm bump into a
 * MeshStandardMaterial so the cortex shades with fine winding gyri without any
 * extra geometry. The height field is sampled in *object* space (folds stay
 * locked to the surface as it rotates/explodes, and mirror with the left
 * hemisphere), its surface gradient is taken by finite differences, rotated
 * into view space via `normalMatrix`, and the shaded normal is bent along it.
 *
 * Used as a shared function reference for every lobe material so three.js
 * compiles a single program for them (their colours differ via the `diffuse`
 * uniform, not the shader source).
 * @param {object} shader  The shader descriptor three.js passes in.
 */
function injectGyrusBump(shader) {
  // Vertex: hand the object-space position + normal to the fragment stage.
  shader.vertexShader = shader.vertexShader
    .replace(
      "#include <common>",
      "#include <common>\nvarying vec3 vGyrPos;\nvarying vec3 vGyrNormal;",
    )
    .replace(
      "#include <begin_vertex>",
      "#include <begin_vertex>\n  vGyrPos = position;\n  vGyrNormal = normal;",
    );

  // Fragment prelude: varyings, the renderer-supplied normalMatrix (vertex-only
  // by default, so we declare it here to use it in the fragment), and a compact
  // value-noise field warped + banded into swirling "curls".
  const prelude = `
varying vec3 vGyrPos;
varying vec3 vGyrNormal;
uniform mat3 normalMatrix;
#define GYR_OCTAVES ${GYRUS_BUMP.octaves}
float gyrHash(vec3 p){
  p = fract(p * 0.3183099 + vec3(0.71, 0.113, 0.419));
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float gyrNoise(vec3 x){
  vec3 i = floor(x);
  vec3 f = fract(x);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(mix(gyrHash(i + vec3(0.0,0.0,0.0)), gyrHash(i + vec3(1.0,0.0,0.0)), f.x),
        mix(gyrHash(i + vec3(0.0,1.0,0.0)), gyrHash(i + vec3(1.0,1.0,0.0)), f.x), f.y),
    mix(mix(gyrHash(i + vec3(0.0,0.0,1.0)), gyrHash(i + vec3(1.0,0.0,1.0)), f.x),
        mix(gyrHash(i + vec3(0.0,1.0,1.0)), gyrHash(i + vec3(1.0,1.0,1.0)), f.x), f.y),
    f.z);
}
// Smooth fractal noise (plain fBm), centred ~[-1, 1].
float gyrFbm(vec3 p){
  float sum = 0.0, amp = 0.5, norm = 0.0;
  for (int o = 0; o < GYR_OCTAVES; o++){
    sum += amp * (gyrNoise(p) * 2.0 - 1.0);
    norm += amp;
    amp *= 0.5;
    p *= 2.0;
  }
  return sum / norm;
}
// Height of the "little curls" field at object point p, given a *precomputed*
// domain-warp offset wOff: a fractal field sampled at the warped coordinate
// (the warp is what swirls the bands), then sin() turns its smooth iso-levels
// into closed, fingerprint-like loops. wOff is passed in so the per-fragment
// finite-difference gradient below can reuse one warp for all four taps (the
// warp varies slowly, so holding it fixed across the tiny eps is invisible but
// roughly halves the noise-field evaluations: ~7 instead of ~16 per fragment).
float gyrBandedAt(vec3 p, vec3 wOff){
  float base = gyrFbm(p * ${glslFloat(GYRUS_BUMP.freq)} + wOff);
  return sin(base * ${glslFloat(GYRUS_BUMP.bands)} * 6.2831853);
}
`;

  // Bend the shaded normal along the surface gradient of the curl field. The
  // domain warp is computed once here and reused across the gradient taps.
  const perturb = `#include <normal_fragment_begin>
{
  float e = ${glslFloat(GYRUS_BUMP.eps)};
  vec3 q = vGyrPos * ${glslFloat(GYRUS_BUMP.freq)};
  vec3 wOff = ${glslFloat(GYRUS_BUMP.warp)} * vec3(
    gyrFbm(q),
    gyrFbm(q + vec3(5.2, 1.3, 2.8)),
    gyrFbm(q + vec3(2.1, 7.4, 3.5))
  );
  float h0 = gyrBandedAt(vGyrPos, wOff);
  vec3 grad = vec3(
    gyrBandedAt(vGyrPos + vec3(e, 0.0, 0.0), wOff) - h0,
    gyrBandedAt(vGyrPos + vec3(0.0, e, 0.0), wOff) - h0,
    gyrBandedAt(vGyrPos + vec3(0.0, 0.0, e), wOff) - h0
  ) / e;
  vec3 nObj = normalize(vGyrNormal);
  vec3 tang = grad - dot(grad, nObj) * nObj;  // tangential part, object space
  normal = normalize(normal - ${glslFloat(GYRUS_BUMP.scale)} * normalMatrix * tang);
}`;

  shader.fragmentShader =
    prelude +
    shader.fragmentShader.replace("#include <normal_fragment_begin>", perturb);
}

/**
 * Build a ready-to-add mesh for one structure record.
 *
 * The mesh is positioned at the structure's *assembled* (un-exploded) location;
 * the caller animates explosion by moving it along its stored explode
 * direction. We stash the base position + direction on `userData` so the
 * explode logic and the projection arrows can read them back.
 * @param {object} structure  A structure record with `position`, `color`,
 *   `shape`, and an optional `mirror` flag (left member of a symmetric pair).
 * @returns {THREE.Mesh}
 */
export function buildStructureMesh(structure) {
  const geometry = buildGeometry(structure.shape);
  // Symmetric pairs share one right-side shape file; the left member reflects
  // it so the two hemispheres are true mirror images. (Midline forms never set
  // this flag, so they are emitted once and never reflected.)
  if (structure.mirror) mirrorGeometryX(geometry);
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(structure.color),
    transparent: true,
    opacity: 1,
    roughness: 0.65,
    metalness: 0.05,
    // Render both sides so the inside stays visible once opacity drops.
    side: THREE.DoubleSide,
  });
  // Cortical lobes get fine gyri as a procedural normal-map bump (the geometry
  // itself stays a smooth broad fold; see GYRUS_BUMP). A shared function +
  // cache key means all lobes compile to one program.
  if (structure.group === "lobe" && GYRUS_BUMP.enabled) {
    material.onBeforeCompile = injectGyrusBump;
    material.customProgramCacheKey = () => "gyrus-bump";
  }
  const mesh = new THREE.Mesh(geometry, material);

  const base = new THREE.Vector3(...structure.position);
  mesh.position.copy(base);
  // Explosion pushes each region radially outward from the brain center. For a
  // region sitting exactly at the origin we fall back to "up" so it still moves.
  const dir = base.clone();
  if (dir.lengthSq() < 1e-6) dir.set(0, 1, 0);
  dir.normalize();

  mesh.userData = { id: structure.id, base, dir, structure };
  return mesh;
}
