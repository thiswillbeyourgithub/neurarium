// Wire format for a baked mesh: the geometry the SDF mesher used to rebuild in
// every visitor's browser is now built once, author-side, and shipped.
//
// Encoder AND decoder live in this one file on purpose. They are the two halves
// of a single format, and splitting them across `tools/` and `public/` is how a
// format silently drifts: a change to one half would be reviewable without the
// other in front of you. The encoder is a few hundred bytes of unused code in the
// browser, which is a cheap price for that. THREE-free and Node-free (plain
// Uint8Array, explicit little-endian), so the same module runs in both.
//
// Why not raw typed arrays: int16 positions + uint32 indices gzip to 2.45 MB.
// The coding below gets the same meshes to 1.30 MB, which is the difference
// between roughly tripling and roughly doubling a first load. Two standard mesh
// tricks, no external codec (no npm encoder, no wasm decoder to vendor):
//
//   - positions are quantised to 16 bits over the mesh's OWN bounding box, then
//     delta-coded against the previous vertex. 1/65535 of one structure's extent
//     is ~6e-5 scene units, two orders below the mesher's own weld tolerance
//     (voxel/8), so this is below the resolution of the geometry itself.
//   - vertices are reordered into first-use order, so a triangle's indices are
//     near the running maximum and the index stream delta-codes against that
//     high-water mark. Reordering also makes neighbouring vertices adjacent in
//     the stream, which is what makes the position deltas small.
//
// Both streams are zigzag + LEB128 varints, so a small delta costs one byte and
// gzip/zstd then squeezes the rest. Bump FORMAT_VERSION if any of this changes;
// the decoder rejects a version it does not know rather than misreading bytes.

const MAGIC = 0x484d534e; // "NMSH" little-endian
export const FORMAT_VERSION = 1;
/** Header: magic u32, version u8, flags u8, pad u16, counts 2x u32, bbox 6x f32. */
const HEADER_BYTES = 4 + 1 + 1 + 2 + 4 + 4 + 24;
const QUANT_MAX = 65535;

// ---------------------------------------------------------------------------
// Varints. Zigzag maps a signed delta onto the naturals (-1 -> 1, 1 -> 2), so a
// small negative costs one byte instead of ten.
// ---------------------------------------------------------------------------

const zigzag = (n) => (n << 1) ^ (n >> 31);
const unzigzag = (n) => (n >>> 1) ^ -(n & 1);

/** Growable byte sink; plain array of bytes, packed once at the end. */
function writer() {
  let buf = new Uint8Array(1024);
  let len = 0;
  return {
    byte(b) {
      if (len === buf.length) {
        const next = new Uint8Array(buf.length * 2);
        next.set(buf);
        buf = next;
      }
      buf[len++] = b;
    },
    varint(v) {
      // `v` is already zigzagged, so it is a non-negative 32-bit value.
      v >>>= 0;
      while (v > 0x7f) {
        this.byte((v & 0x7f) | 0x80);
        v >>>= 7;
      }
      this.byte(v);
    },
    get length() { return len; },
    bytes() { return buf.subarray(0, len); },
  };
}

/** Cursor over a byte range; `pos` is public so the caller can chain streams. */
function reader(bytes, pos = 0) {
  return {
    pos,
    varint() {
      let shift = 0, out = 0, b;
      do {
        b = bytes[this.pos++];
        out |= (b & 0x7f) << shift;
        shift += 7;
      } while (b & 0x80);
      return out >>> 0;
    },
  };
}

// ---------------------------------------------------------------------------
// Encode / decode
// ---------------------------------------------------------------------------

/**
 * @param {Float32Array|number[]} positions  xyz triples, world units.
 * @param {Uint32Array|number[]} indices     triangle list into `positions`.
 * @returns {Uint8Array}
 */
export function encodeMesh(positions, indices) {
  const vertexCount = positions.length / 3;
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positions.length; i += 3) {
    for (let a = 0; a < 3; a++) {
      const v = positions[i + a];
      if (v < min[a]) min[a] = v;
      if (v > max[a]) max[a] = v;
    }
  }
  // A degenerate axis (a perfectly flat mesh) would divide by zero; span 1 then
  // quantises every vertex to the same bucket, which is exactly right for it.
  const span = [0, 1, 2].map((a) => (max[a] - min[a]) || 1);
  const quant = new Int32Array(positions.length);
  for (let i = 0; i < positions.length; i += 3) {
    for (let a = 0; a < 3; a++) {
      const t = (positions[i + a] - min[a]) / span[a];
      quant[i + a] = Math.max(0, Math.min(QUANT_MAX, Math.round(t * QUANT_MAX)));
    }
  }

  // Vertices in first-use order, indices remapped onto it.
  const remap = new Int32Array(vertexCount).fill(-1);
  const order = new Int32Array(vertexCount);
  const remapped = new Uint32Array(indices.length);
  let seen = 0;
  for (let i = 0; i < indices.length; i++) {
    const v = indices[i];
    if (remap[v] < 0) {
      remap[v] = seen;
      order[seen] = v;
      seen++;
    }
    remapped[i] = remap[v];
  }
  // A vertex no triangle references (the weld can leave none, but the format
  // must not lose data if it ever does) is appended so counts stay truthful.
  for (let v = 0; v < vertexCount; v++) if (remap[v] < 0) order[seen++] = v;

  const pos = writer();
  const prev = [0, 0, 0];
  for (let k = 0; k < seen; k++) {
    const v = order[k];
    for (let a = 0; a < 3; a++) {
      const q = quant[v * 3 + a];
      pos.varint(zigzag(q - prev[a]));
      prev[a] = q;
    }
  }
  const idx = writer();
  let high = 0;
  for (let i = 0; i < remapped.length; i++) {
    const v = remapped[i];
    idx.varint(zigzag(v - high));
    if (v > high) high = v;
  }

  const out = new Uint8Array(HEADER_BYTES + pos.length + idx.length);
  const view = new DataView(out.buffer);
  view.setUint32(0, MAGIC, true);
  view.setUint8(4, FORMAT_VERSION);
  view.setUint8(5, 0); // flags, reserved
  view.setUint16(6, 0, true); // pad, keeps the f32 bbox 4-byte aligned
  view.setUint32(8, vertexCount, true);
  view.setUint32(12, indices.length, true);
  for (let a = 0; a < 3; a++) {
    view.setFloat32(16 + a * 4, min[a], true);
    view.setFloat32(28 + a * 4, max[a], true);
  }
  out.set(pos.bytes(), HEADER_BYTES);
  out.set(idx.bytes(), HEADER_BYTES + pos.length);
  return out;
}

/**
 * Vertices come back in the encoder's first-use order with the indices remapped
 * to match: the mesh is geometrically identical to what was encoded, but the two
 * arrays are NOT elementwise equal to the originals. Nothing downstream cares
 * (the geometry is fed straight to `geometryFromArrays`, whose normals come from
 * the triangles), so do not "fix" this: the reorder is what makes the index
 * deltas small, and it is half the compression.
 *
 * @param {ArrayBuffer|Uint8Array} data
 * @returns {{positions: Float32Array, indices: Uint32Array}}
 * @throws if the bytes are not a baked mesh this build understands.
 */
export function decodeMesh(data) {
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
  if (bytes.length < HEADER_BYTES) throw new Error("baked mesh: truncated header");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (view.getUint32(0, true) !== MAGIC) throw new Error("baked mesh: bad magic");
  const version = view.getUint8(4);
  if (version !== FORMAT_VERSION) {
    throw new Error(`baked mesh: format v${version}, this build reads v${FORMAT_VERSION}`);
  }
  const vertexCount = view.getUint32(8, true);
  const indexCount = view.getUint32(12, true);
  const min = [view.getFloat32(16, true), view.getFloat32(20, true), view.getFloat32(24, true)];
  const max = [view.getFloat32(28, true), view.getFloat32(32, true), view.getFloat32(36, true)];
  const span = [0, 1, 2].map((a) => (max[a] - min[a]) || 1);

  const r = reader(bytes, HEADER_BYTES);
  const positions = new Float32Array(vertexCount * 3);
  const prev = [0, 0, 0];
  for (let k = 0; k < vertexCount; k++) {
    for (let a = 0; a < 3; a++) {
      const q = (prev[a] += unzigzag(r.varint()));
      positions[k * 3 + a] = min[a] + (q / QUANT_MAX) * span[a];
    }
  }
  const indices = new Uint32Array(indexCount);
  let high = 0;
  for (let i = 0; i < indexCount; i++) {
    const v = high + unzigzag(r.varint());
    indices[i] = v;
    if (v > high) high = v;
  }
  return { positions, indices };
}
