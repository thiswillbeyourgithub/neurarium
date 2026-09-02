# Baked meshes

The brain's SDF structures are meshed **author-side** and the geometry is shipped, instead of
every visitor's browser rebuilding it on every load.

## Why

Meshing the atlas is marching cubes over a 3D field: ~26 distinct shapes, tens of millions of
field samples. It costs roughly **3.8 s of worker time on a desktop** and several times that on
a phone, and it was paid on *every* load, because a computation cannot be HTTP-cached. The
download of the result is paid **once** and then revalidated as a bodyless `304` by `sw.js`.

The shapes are settled, so the trade is now worth making. Measured, headless Chromium,
local server, the "loading the 3D shapes" phase:

| | geometry phase | ready |
|---|---|---|
| baked | 0.71 s | 1.50 s |
| runtime mesher (bake removed) | 2.95 s | 3.66 s |

The two renders are visually the same: 10 pixels out of 820,000 differ by more than 8/255,
all of them silhouette antialiasing from the position quantisation.

## The pieces

- **`tools/bake_meshes.mjs`** (Node) meshes every distinct `sdf` shape file and writes
  `public/data/meshes/<name>.bin` plus `index.json`. It **imports the browser's own modules**
  (`public/js/sdf-core.js`, `js/noise.js`), so the bake and the fallback cannot drift; this is
  also why it is Node and not `generate_data.py`, which stays stdlib-only and knows nothing
  about the bake.
- **`public/js/mesh-codec.js`** holds the encoder **and** the decoder, deliberately in one
  file: they are two halves of one format, and splitting them across `tools/` and `public/` is
  how a format silently drifts.
- **`public/js/baked-meshes.js`** loads the manifest and the files in the browser. It never
  throws: anything wrong (no manifest, unknown format version, a bad file, counts disagreeing
  with the manifest) just means "no baked mesh for that shape", and `js/main.js` meshes the
  remainder at runtime exactly as before.

## The format

`.bin`, little-endian, magic `NMSH`, a version byte the decoder refuses to guess past. Raw
int16 positions + uint32 indices gzip to 2.45 MB; this gets the same meshes to **1.30 MB**,
using two standard mesh tricks and no external codec (no npm encoder, no wasm decoder to
vendor):

- positions quantised to 16 bits over each mesh's **own** bounding box, then delta-coded
  against the previous vertex. One bucket is ~6e-5 scene units, two orders below the mesher's
  own weld tolerance.
- vertices reordered into **first-use order**, so an index sits near a running high-water mark
  and the index stream delta-codes against it. The reorder is also what makes neighbouring
  vertices adjacent, hence the position deltas small.

Both streams are zigzag + LEB128 varints; gzip/zstd then squeezes the rest.

Because of the reorder, a decoded mesh is **geometrically identical but not elementwise equal**
to what was encoded. Every bake round-trips each mesh through the real decoder and asserts every
triangle corner survives within one quantisation bucket, so a codec regression fails the bake
rather than shipping mangled geometry.

## Staleness

A bake that no longer matches its shape file would silently ship last week's geometry, so the
manifest records each shape file's `sha256` and **two** gates re-derive it:

```
node tools/bake_meshes.mjs --check   # exits 1 if any shape changed since the bake
python tools/check_data.py           # family 11, same hash comparison
```

Re-bake with `node tools/bake_meshes.mjs` (run after `generate_data.py`, since it reads the
emitted `public/data/structures.jsonl`). A missing bake is a **warning**, not an error: the
fallback is correct, only slow. This is what keeps `tools/serve.py` and the
`geometry_refinements/` loop working on a tree that has not been re-baked.

## Serving

`docker/Caddyfile` pins `/data/meshes/*.bin` to `application/octet-stream` and compresses by an
**explicit** content-type list. Caddy's built-in `encode` default omits octet-stream, so
relying on it would ship 2.69 MB instead of 1.29 MB and undo most of what baking bought.
`sw.js` needs no change: it already revalidates every same-origin GET conditionally, so the
meshes are downloaded once and then cost a bodyless `304`.
