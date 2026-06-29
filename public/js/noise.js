// Deterministic gradient (Perlin) noise + its fractal (fBm / ridged) variant.
//
// Pure math, ZERO imports (no three.js): so this module can be loaded both on the
// main thread (via shapes.js) AND inside the SDF meshing Web Worker, which has no
// import map and therefore cannot resolve the bare "three" specifier. Keeping the
// noise here, dependency-free, is what lets the worker reuse the exact same fold
// field the main-thread blob/SDF builders use (no duplicated Perlin, identical
// surfaces). See js/sdf-worker.js and geometry_refinements/.

// Cheap deterministic integer hash -> uint32, seeded so each structure's surface
// is unique but stable. Shared by the gradient picker below.
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
export function gradientNoise(x, y, z, seed) {
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
export function fractalNoise(nx, ny, nz, seed, octaves, ridged, frequency, aniso) {
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
