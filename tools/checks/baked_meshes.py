"""Family 11: the baked SDF meshes match the shapes they were baked from.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import hashlib
import json

from .common import DATA_DIR


def check_baked_meshes(report, structures):
    """Family 11: the baked SDF geometry is current for the shapes it was baked from.

    The bake (tools/bake_meshes.mjs) replaces ~3.8s of in-browser meshing with a
    download, which means the geometry a visitor sees is no longer derived from the
    shape file at run time. So an edited shape with a stale bake would silently ship
    last week's brain, and look like nothing at all went wrong. The manifest records
    each shape file's SHA-256, and this re-hashes the file: that catches a stale bake
    without needing Node here (re-meshing to compare would mean a Python marching
    cubes, which is exactly the duplication the bake tool exists to avoid).

    Absence is fine, not an error: the viewer falls back to meshing in the browser
    (js/baked-meshes.js), so an unbaked clone is slow, not broken."""
    report.header("11. Baked meshes (pre-built SDF geometry)")
    mesh_dir = DATA_DIR / "meshes"
    manifest_path = mesh_dir / "index.json"
    if not manifest_path.exists():
        report.warn("public/data/meshes/index.json absent: the viewer will mesh the "
                    "brain in the browser (slower, but correct). Run: node tools/bake_meshes.mjs")
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"meshes/index.json is not valid JSON: {exc}")
        return

    baked = manifest.get("meshes") or {}
    # Every DISTINCT sdf shape file, the same set the bake tool collects.
    wanted = {}
    for row in structures:
        shape_file = row.get("shape_file")
        if not shape_file or shape_file in wanted:
            continue
        path = DATA_DIR.parent / shape_file
        if not path.exists():
            continue
        try:
            raw = path.read_bytes()
            if json.loads(raw.decode("utf-8")).get("type") != "sdf":
                continue
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        wanted[shape_file] = hashlib.sha256(raw).hexdigest()

    stale = []
    for shape_file, digest in sorted(wanted.items()):
        entry = baked.get(shape_file)
        if entry is None:
            stale.append(f"{shape_file}: no baked mesh")
            continue
        if entry.get("spec_sha256") != digest:
            stale.append(f"{shape_file}: shape edited since the bake")
        blob = mesh_dir / str(entry.get("file") or "")
        if not blob.exists():
            stale.append(f"{shape_file}: {entry.get('file')} is missing")
        elif blob.stat().st_size != entry.get("bytes"):
            stale.append(f"{shape_file}: {entry.get('file')} size disagrees with the manifest")
    for orphan in sorted(set(baked) - set(wanted)):
        stale.append(f"{orphan}: baked, but no structure uses it any more")

    if stale:
        for line in stale:
            report.error(f"baked mesh out of date: {line}")
        report.error("run `node tools/bake_meshes.mjs` and commit public/data/meshes/")
        return
    total = sum(int(e.get("bytes") or 0) for e in baked.values())
    report.ok(f"{len(baked)} baked mesh(es) current with their shape files "
              f"({total / 1024 / 1024:.2f} MB, served compressed)")
