#!/usr/bin/env node
// Bake the SDF structures' geometry author-side, so a visitor downloads the
// meshes instead of rebuilding them.
//
// Why this exists: meshing the atlas in the browser costs ~3.8s of worker time on
// a desktop and tens of seconds on a phone, and it is paid on EVERY load, whereas
// the download is paid once and then revalidated as a bodyless 304 by sw.js. The
// shapes are settled, so that trade is now worth making.
//
// Why Node and not generate_data.py: the mesher is JavaScript (js/sdf-core.js +
// js/marching-cubes.js + js/noise.js). Re-implementing marching cubes and the
// noise field in Python would duplicate the one thing that must not drift, so
// this tool imports the very modules the browser fallback runs. generate_data.py
// stays stdlib-only and knows nothing about the bake.
//
// Run from the repo root, after generate_data.py (it reads the emitted data):
//
//     node tools/bake_meshes.mjs            # write public/data/meshes/
//     node tools/bake_meshes.mjs --check    # verify the bake is current, write nothing
//
// `--check` is what CI and tools/check_data.py lean on: every shape file's bytes
// are hashed into the manifest, so an edited shape with a stale bake fails loud
// instead of silently shipping last week's geometry.

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

import { meshSdfToArrays } from "../public/js/sdf-core.js";
import { gradientNoise, fractalNoise } from "../public/js/noise.js";
import { encodeMesh, decodeMesh, FORMAT_VERSION } from "../public/js/mesh-codec.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PUBLIC = path.join(ROOT, "public");
const OUT_DIR = path.join(PUBLIC, "data", "meshes");
const MANIFEST = path.join(OUT_DIR, "index.json");
/** Same noise the main thread and the SDF worker inject; see js/sdf.js. */
const DEPS = { noise3d: gradientNoise, fractalNoise };

const sha256 = (buf) => crypto.createHash("sha256").update(buf).digest("hex");

/**
 * Every DISTINCT sdf shape file, in the order the structures first mention it.
 * Distinct, not per structure: a symmetric structure's hemispheres share one
 * file (the left is the right mirrored at runtime), so baking per structure
 * would ship 20 duplicate meshes.
 */
function collectShapeFiles() {
  const lines = fs.readFileSync(path.join(PUBLIC, "data", "structures.jsonl"), "utf8")
    .trim().split("\n");
  const out = new Map();
  for (const line of lines) {
    const s = JSON.parse(line);
    if (!s.shape_file || out.has(s.shape_file)) continue;
    const abs = path.join(PUBLIC, s.shape_file);
    const raw = fs.readFileSync(abs);
    const spec = JSON.parse(raw.toString("utf8"));
    if (spec.type !== "sdf") continue;
    out.set(s.shape_file, { spec, specHash: sha256(raw) });
  }
  return out;
}

/**
 * Round-trip a freshly encoded mesh through the very decoder the browser runs,
 * and prove the geometry survived. This is the bake's own safety net: there is no
 * JS test harness in this repo, and a codec that quietly mangles a structure would
 * ship geometry nobody reviewed, so the check runs on every bake rather than
 * living in a suite someone has to remember.
 *
 * It compares TRIANGLE CORNER POSITIONS, not the raw arrays. The encoder reorders
 * vertices into first-use order on purpose (see mesh-codec.js), so the arrays are
 * legitimately not elementwise equal; what must hold is that every triangle still
 * has the same three corners in space. Tolerance is one quantisation bucket per
 * axis, which is what the format promises and is ~2 orders below the mesher's own
 * weld tolerance.
 */
function verifyRoundTrip(name, positions, indices, encoded) {
  const mesh = decodeMesh(encoded);
  if (mesh.indices.length !== indices.length || mesh.positions.length !== positions.length) {
    throw new Error(`bake_meshes: ${name} round-trip changed the mesh size ` +
      `(${positions.length / 3}v/${indices.length / 3}t -> ` +
      `${mesh.positions.length / 3}v/${mesh.indices.length / 3}t)`);
  }
  const span = [0, 1, 2].map((a) => {
    let lo = Infinity, hi = -Infinity;
    for (let i = a; i < positions.length; i += 3) {
      if (positions[i] < lo) lo = positions[i];
      if (positions[i] > hi) hi = positions[i];
    }
    return (hi - lo) || 1;
  });
  const tol = span.map((s) => s / 65535);
  let worst = 0;
  for (let i = 0; i < indices.length; i++) {
    const a = indices[i] * 3;
    const b = mesh.indices[i] * 3;
    for (let k = 0; k < 3; k++) {
      const d = Math.abs(positions[a + k] - mesh.positions[b + k]);
      if (d > tol[k]) {
        throw new Error(`bake_meshes: ${name} round-trip moved a triangle corner by ` +
          `${d.toExponential(2)} on axis ${k} (tolerance ${tol[k].toExponential(2)})`);
      }
      if (d / tol[k] > worst) worst = d / tol[k];
    }
  }
  return worst;
}

function main() {
  const check = process.argv.includes("--check");
  const shapes = collectShapeFiles();
  if (!shapes.size) {
    console.error("bake_meshes: no sdf shape files found; run generate_data.py first");
    process.exit(1);
  }

  const entries = {};
  const built = [];
  let bytes = 0;
  let worstRoundTrip = 0;
  const t0 = Date.now();
  for (const [shapeFile, { spec, specHash }] of shapes) {
    const name = path.basename(shapeFile, ".json");
    const { positions, indices } = meshSdfToArrays(spec, DEPS);
    const encoded = encodeMesh(positions, indices);
    worstRoundTrip = Math.max(worstRoundTrip, verifyRoundTrip(name, positions, indices, encoded));
    bytes += encoded.length;
    entries[shapeFile] = {
      file: `${name}.bin`,
      spec_sha256: specHash,
      vertices: positions.length / 3,
      triangles: indices.length / 3,
      bytes: encoded.length,
    };
    built.push([path.join(OUT_DIR, `${name}.bin`), encoded]);
  }
  // Sorted keys so a re-bake of unchanged shapes produces a byte-identical
  // manifest, and git sees no diff (this lands in history, so churn matters).
  const manifest = {
    format: FORMAT_VERSION,
    note: "Generated by tools/bake_meshes.mjs. Do not edit; see docs/BAKED_MESHES.md.",
    meshes: Object.fromEntries(Object.keys(entries).sort().map((k) => [k, entries[k]])),
  };
  const manifestText = JSON.stringify(manifest, null, 2) + "\n";

  if (check) {
    const current = fs.existsSync(MANIFEST) ? fs.readFileSync(MANIFEST, "utf8") : null;
    if (current !== manifestText) {
      console.error("bake_meshes --check: public/data/meshes/index.json is stale or missing.\n" +
        "  A shape file changed since the last bake, so the site would ship geometry\n" +
        "  that no longer matches its spec. Run: node tools/bake_meshes.mjs");
      process.exit(1);
    }
    for (const [file, encoded] of built) {
      if (!fs.existsSync(file) || !fs.readFileSync(file).equals(Buffer.from(encoded))) {
        console.error(`bake_meshes --check: ${path.relative(ROOT, file)} does not match its spec.\n` +
          "  Run: node tools/bake_meshes.mjs");
        process.exit(1);
      }
    }
    console.log(`bake_meshes --check: ${shapes.size} baked mesh(es) current ` +
      `(round-trip worst ${(worstRoundTrip * 100).toFixed(0)}% of one quantisation bucket).`);
    return;
  }

  fs.mkdirSync(OUT_DIR, { recursive: true });
  // Drop meshes for shapes that no longer exist, so a removed structure cannot
  // leave an orphan file being served forever.
  const keep = new Set(Object.values(manifest.meshes).map((m) => m.file));
  for (const f of fs.readdirSync(OUT_DIR)) {
    if (f.endsWith(".bin") && !keep.has(f)) {
      fs.unlinkSync(path.join(OUT_DIR, f));
      console.log(`  removed orphan ${f}`);
    }
  }
  for (const [file, encoded] of built) fs.writeFileSync(file, encoded);
  fs.writeFileSync(MANIFEST, manifestText);

  const mb = (b) => (b / 1024 / 1024).toFixed(2);
  const verts = Object.values(manifest.meshes).reduce((a, m) => a + m.vertices, 0);
  const tris = Object.values(manifest.meshes).reduce((a, m) => a + m.triangles, 0);
  console.log(`baked ${shapes.size} mesh(es): ${verts.toLocaleString()} vertices, ` +
    `${tris.toLocaleString()} triangles, ${mb(bytes)} MB in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  console.log(`  -> ${path.relative(ROOT, OUT_DIR)}/ (Caddy serves these gzip/zstd encoded)`);
  console.log(`  round-trip verified: worst corner moved ${(worstRoundTrip * 100).toFixed(0)}% ` +
    "of one quantisation bucket");
}

main();
