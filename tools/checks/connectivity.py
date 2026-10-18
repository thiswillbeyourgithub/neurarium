"""Family 6: structure connectivity (warns, never errors).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""


def check_connectivity(report, structures, projections):
    """Warn about structures the connectome leaves stranded or one-sided.

    A projection is directed ``from -> to`` (a ``bidirectional`` one counts both
    ways for both endpoints). This flags, as **warnings** (not errors; each can be
    legitimate, so it is an eyeball list, not a gate):

    * **isolated**: no projection touches the structure at all (it is only
      reachable via receptors / drug targets, with no modeled pathway yet);
    * **inward-only**: it receives projections but sends none (a pure sink);
    * **outward-only**: it sends projections but receives none (a pure source,
      e.g. the neuromodulatory source nuclei raphe / locus coeruleus / VTA, which
      are modeled as ascending sources, so these are expected here).

    The aim is the author's intuition that a structure wired in one direction only
    is worth a look, without hard-failing the genuinely one-directional cases."""
    report.header("6. Structure connectivity")
    structure_ids = {s.get("id") for s in structures}
    inward, outward = set(), set()
    for proj in projections:
        src, dst = proj.get("from"), proj.get("to")
        if src in structure_ids:
            outward.add(src)
        if dst in structure_ids:
            inward.add(dst)
        if proj.get("bidirectional"):
            if src in structure_ids:
                inward.add(src)
            if dst in structure_ids:
                outward.add(dst)

    isolated, in_only, out_only = [], [], []
    for structure in structures:
        sid = structure.get("id")
        has_in, has_out = sid in inward, sid in outward
        if not has_in and not has_out:
            isolated.append(sid)
        elif has_in and not has_out:
            in_only.append(sid)
        elif has_out and not has_in:
            out_only.append(sid)

    for sid in sorted(isolated):
        report.warn(f"structure {sid}: no projections touch it "
                    f"(isolated in the connectome)")
    for sid in sorted(in_only):
        report.warn(f"structure {sid}: only inward projections "
                    f"(receives, never projects out)")
    for sid in sorted(out_only):
        report.warn(f"structure {sid}: only outward projections "
                    f"(projects out, never receives)")

    flagged = len(isolated) + len(in_only) + len(out_only)
    if not flagged:
        report.ok(f"all {len(structures)} structures have both inward and outward "
                  f"projections")
    else:
        report.ok(f"{len(structures) - flagged} of {len(structures)} structures are "
                  f"two-way connected ({len(isolated)} isolated, {len(in_only)} "
                  f"inward-only, {len(out_only)} outward-only flagged above)")
