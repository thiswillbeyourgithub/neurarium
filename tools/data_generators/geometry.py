"""Shared cortical-dome geometry helpers used by the region records.

Extracted from generate_data.py so data_generators.regions can build the
cortical-lobe SDF sectors without importing the CLI module (a cycle).
"""

import math
from typing import Any

# Half-width of the longitudinal fissure: each cortical lobe's medial face is
# cut flat at world x = +/- this, so the left and right hemispheres meet along a
# thin midline gap instead of overlapping into one ball. Small = tight fissure.
MIDLINE_GAP = 0.06

# --- Cortical dome (SDF) -----------------------------------------------------
# The cerebral cortex is authored as ONE shared right-hemisphere ellipsoid (the
# "cortical mantle"); each lobe is a sector of it carved by shared cut planes, so
# at explode 0 the lobes reassemble into a single continuous dome instead of
# reading as a cluster of separate balls. The gyral relief is a gentle GEOMETRIC
# displace (lumpy silhouette) sampled from one shared WORLD-space fold field, so
# the folds line up across seams; the brainy sulcus ink is still the swirl
# shader on top. (See geometry_refinements/.)
CORTEX_DOME_CENTER = (1.15, 0.55, -0.15)  # world coords, right hemisphere
CORTEX_DOME_RADII = (1.55, 2.0, 3.4)      # M-L, S-I, A-P (anteroposterior longest)
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

# Shared lobe-boundary planes (world coords; the listed normal points INTO the
# kept side). Reused across lobes so their cut faces are coincident and the lobes
# abut exactly. The fissures are tilted (oblique) so the seams read like the real
# central / Sylvian fissures, not axis-aligned slabs.
_CENTRAL_PT = (1.15, 0.55, 0.4)      # central sulcus: frontal (anterior) | parietal
_CENTRAL_N_FRONT = (0.0, 0.32, 1.0)  # -> into the frontal side; tilt = slopes forward going down
_SYLVIAN_PT = (1.15, -0.1, 0.2)      # lateral (Sylvian) fissure: fronto-parietal | temporal
_SYLVIAN_N_UP = (0.0, 1.0, 0.18)     # -> into the upper side; tilt = rises posteriorly
_PAR_OCC_Z = -1.9                    # parieto-occipital: occipital is the posterior cap
_TEMPORAL_MEDIAL_X = 0.95            # temporal stays lateral of this parasagittal plane


def _neg(v):
    return (-v[0], -v[1], -v[2])


# The temporal "bite": the region below the Sylvian fissure AND lateral of the
# temporal parasagittal plane. Subtracted from the frontal + parietal lobes so
# they keep their inferomedial / orbital surface (which reaches the base medially)
# while the temporal owns just this lateral inferior wedge (so it no longer slabs
# across the midline). The same plane definitions feed the temporal's own
# intersect, so the shared faces are coincident and the lobes abut.
_TEMPORAL_BITE = [("plane", _neg(_SYLVIAN_N_UP), _SYLVIAN_PT),
                  ("x", ">", _TEMPORAL_MEDIAL_X)]


def _cut_to_plane(cut, pos):
    """One territory cut -> an SDF half-space ``plane`` node (in local coords).

    Two forms (both in WORLD coords; ``local = world - pos``):
      * axis-aligned ``("z", ">", 0.4)`` keeps ``axis > value`` (or ``"<"``);
      * oblique ``("plane", inward_normal, point)`` keeps the half-space the
        inward normal points into.
    Returns ``(plane_node, axis_clamp)`` where ``axis_clamp`` is
    ``(index, side, value)`` for AABB tightening, or ``None`` (oblique: the dome
    AABB already bounds it).
    """
    if cut[0] in _AXIS_INDEX:
        axis, side, value = cut
        i = _AXIS_INDEX[axis]
        normal = [0.0, 0.0, 0.0]
        normal[i] = -1.0 if side == ">" else 1.0
        local_value = value - pos[i]
        offset = -local_value if side == ">" else local_value
        return dict(prim="plane", normal=normal, offset=round(offset, 4)), (i, side, value)
    _, n_in, p = cut
    normal = [-n_in[0], -n_in[1], -n_in[2]]  # sdPlane inside = dot(local, n) < offset
    offset = -sum(n_in[k] * (p[k] - pos[k]) for k in range(3))
    return dict(prim="plane", normal=[round(v, 4) for v in normal], offset=round(offset, 4)), None


def _region_node(region, pos):
    """A set of cuts -> one SDF node that is solid inside their intersection."""
    planes = [_cut_to_plane(c, pos)[0] for c in region]
    return planes[0] if len(planes) == 1 else dict(op="intersect", nodes=planes)


def _cortex_lobe(pos, cuts, *, seed, subtract_regions=None, resolution=92):
    """SDF spec for one cortical lobe: a sector of the shared cortical dome.

    ``cuts`` selects this lobe's territory as the intersection of the dome with a
    set of half-space cuts (see ``_cut_to_plane``). ``subtract_regions`` removes
    further regions (each a list of cuts intersected together) AFTER the
    intersection: this is how the temporal "bite" (below Sylvian AND lateral) is
    carved out of the frontal/parietal lobes so they keep their inferomedial /
    orbital surface while the temporal stays a lateral wedge. The dome ellipsoid,
    its gyral ``displace`` and every plane are translated into the lobe's local
    frame; the displace samples a shared WORLD-space fold field (``origin = pos``)
    so the gyri are continuous across seams. A flat medial wall (world
    ``x = MIDLINE_GAP``) is subtracted last. ``bounds`` is the wedge AABB tightened
    by the axis-aligned cuts (oblique cuts fall back to the dome extent).
    """
    c, r = CORTEX_DOME_CENTER, CORTEX_DOME_RADII
    lo = [c[i] - r[i] for i in range(3)]
    hi = [c[i] + r[i] for i in range(3)]
    lo[0] = max(lo[0], MIDLINE_GAP)  # the medial wall trims the AABB
    plane_nodes = []
    for cut in cuts:
        node, clamp = _cut_to_plane(cut, pos)
        plane_nodes.append(node)
        if clamp:
            i, side, value = clamp
            if side == ">":
                lo[i] = max(lo[i], value)
            else:
                hi[i] = min(hi[i], value)
    dome = dict(prim="ellipsoid",
                center=[round(c[i] - pos[i], 4) for i in range(3)], radii=list(r))
    folded = dict(op="displace", octaves=2, freq=2.2, amp=0.13, unit=1.9, seed=seed,
                  origin=[round(pos[i], 4) for i in range(3)], nodes=[dome])
    wedge = dict(op="intersect", nodes=[folded, *plane_nodes])
    medial = dict(prim="plane", normal=[1.0, 0.0, 0.0],
                  offset=round(MIDLINE_GAP - pos[0], 4))
    cut_nodes = [medial] + [_region_node(rg, pos) for rg in (subtract_regions or [])]
    margin = 0.2  # cover the gyral displace (amp 0.13) pushing past the AABB
    bounds = [[round(lo[i] - pos[i] - margin, 3) for i in range(3)],
              [round(hi[i] - pos[i] + margin, 3) for i in range(3)]]
    return dict(type="sdf", resolution=resolution, bounds=bounds,
                root=dict(op="subtract", nodes=[wedge, *cut_nodes]))


def _cortex_lobe_entry(base, name, color, pos, cuts, seed, subtract_regions=None):
    """A PAIRED cortical-lobe entry whose shape is a sector of the shared dome.

    ``pos`` is written once and threaded into both the entry and the SDF
    local-frame translation, so the two can never drift apart.
    """
    return dict(base=base, name=name, group="lobe", pos=pos, color=color,
                shape=_cortex_lobe(pos, cuts, seed=seed, subtract_regions=subtract_regions))


def _scale_sdf(node: dict[str, Any], s: list[float]) -> dict[str, Any]:
    """Recursively scale an SDF node tree about the local origin by ``s`` =
    ``[sx, sy, sz]`` (lengths along each axis scale by the matching factor).

    Used by :func:`_shape_record` to seat a structure at an anatomically-correct
    size without re-authoring every primitive. Scalar-radius primitives (sphere,
    round-cone/capsule, tube) and the isotropic blend/relief knobs (``k``,
    displace ``amp``/``unit``) can only take ONE factor, so they use the mean of
    ``s`` (an anisotropic swept tube would need an elliptic cross-section the SDF
    cannot express); displace ``freq`` scales inversely so the surface texture
    scales WITH the shape. Returns a NEW node, does not mutate the input. Every
    value is rounded to 4 decimals to keep the emitted JSON clean.
    """
    sm = sum(s) / 3.0
    r = lambda v: round(v, 4)

    def sc(v):  # scale a 3-vector coordinate / extent
        return [r(v[0] * s[0]), r(v[1] * s[1]), r(v[2] * s[2])]

    n = dict(node)
    prim = n.get("prim")
    if prim == "sphere":
        n["center"] = sc(n["center"]); n["radius"] = r(n["radius"] * sm)
    elif prim == "ellipsoid":
        n["center"] = sc(n["center"]); n["radii"] = sc(n["radii"])
    elif prim == "box":
        n["center"] = sc(n["center"]); n["half"] = sc(n["half"])
        if n.get("round") is not None:
            n["round"] = r(n["round"] * sm)
    elif prim in ("capsule", "roundcone"):
        n["a"] = sc(n["a"]); n["b"] = sc(n["b"])
        for key in ("r1", "r2", "radius"):
            if n.get(key) is not None:
                n[key] = r(n[key] * sm)
    elif prim == "tube":
        n["points"] = [sc(p) for p in n["points"]]
        if n.get("profile") is not None:
            n["profile"] = [r(p * sm) for p in n["profile"]]
        if n.get("radius") is not None:
            n["radius"] = r(n["radius"] * sm)
    elif prim == "plane":
        # Half-space cut moves with the geometry: the offset is along the
        # (un-normalized) normal, so scale it by the factor along that direction.
        nm = n["normal"]
        ln = math.sqrt(nm[0] ** 2 + nm[1] ** 2 + nm[2] ** 2) or 1.0
        f = (abs(nm[0]) * s[0] + abs(nm[1]) * s[1] + abs(nm[2]) * s[2]) / ln
        if n.get("offset") is not None:
            n["offset"] = r(n["offset"] * f)
    else:
        # Op node: scale the blend radius + any displacement, recurse into kids.
        if n.get("k") is not None:
            n["k"] = r(n["k"] * sm)
        if n.get("op") == "displace":
            if n.get("amp") is not None:
                n["amp"] = r(n["amp"] * sm)
            if n.get("freq"):
                n["freq"] = r(n["freq"] / sm)
            if n.get("unit"):
                n["unit"] = r(n["unit"] * sm)
            if n.get("origin"):
                n["origin"] = sc(n["origin"])
        if n.get("nodes") is not None:
            n["nodes"] = [_scale_sdf(c, s) for c in n["nodes"]]
        if n.get("node") is not None:
            n["node"] = _scale_sdf(n["node"], s)
    return n


def _scale_triple(scale: Any) -> list[float]:
    """Normalize a ``scale`` (scalar or ``[sx, sy, sz]``) to a 3-list."""
    if isinstance(scale, (int, float)):
        return [float(scale)] * 3
    return [float(c) for c in scale]


def _directional_extent(radii: tuple[float, float, float], noise: float,
                        direction: tuple[float, float, float]) -> float:
    """How far a noise-inflated ellipsoid reaches along a unit ``direction``.

    The support of an axis-aligned ellipsoid with half-extents ``radii`` in a unit
    direction ``n`` is ``sqrt(sum (r_i * n_i)^2)``; the surface noise can push a
    vertex out by up to ``noise`` of the radius, so the reach is scaled by
    ``(1 + noise)``. Used to decide whether two regions overlap and where to seat
    the seam between them.

    Parameters
    ----------
    radii
        Ellipsoid half-extents ``(rx, ry, rz)`` before deformation.
    noise
        Deformation amplitude as a fraction of radius.
    direction
        Unit vector along which to measure the reach.

    Returns
    -------
    float
        Maximum distance from the centre to the surface along ``direction``.
    """
    rx, ry, rz = radii
    dx, dy, dz = direction
    return math.sqrt((rx * dx) ** 2 + (ry * dy) ** 2 + (rz * dz) ** 2) * (1 + noise)


def _bisecting_clip_planes(entry: dict[str, Any],
                           neighbours: list[dict[str, Any]]
                           ) -> list[dict[str, Any]]:
    """Local-space cut planes keeping ``entry`` from crossing its neighbours.

    For each same-group blob ``neighbour`` whose body would overlap ``entry``'s,
    place a flat cut plane at the radius-weighted boundary between the two centres
    with its normal pointing toward the neighbour. ``buildBlobGeometry`` clamps
    any vertex past such a plane onto it, so the two regions grow flat mating
    faces and tile flush instead of interpenetrating (the "jigsaw" look that sells
    the regions locking together at explode 0 and separating as they explode).

    Adjacency is derived from the geometry, not hand-listed: a pair gets a plane
    only when the centres are closer than the two bodies' combined reach toward
    each other, so non-touching pairs (e.g. frontal vs occipital) are skipped. The
    seam is split in proportion to each body's reach, so a large lobe keeps more
    of the shared volume than a small neighbour, and because the pair overlaps the
    seam always lies inside the overlap zone (never cutting past either surface,
    so no region is reduced to a sliver).

    Planes are authored in ``entry``'s *local* frame (its geometry is centred at
    the origin and positioned later), exactly like the medial wall. Paired entries
    are defined on the right hemisphere and the left member mirrors the whole
    geometry across x, which flips these planes to the correct side for free, so
    they are computed once from the right-side positions.

    Parameters
    ----------
    entry
        The blob whose planes are computed (must carry ``radii``/``noise``).
    neighbours
        Same-group blob entries to test for overlap (``entry`` itself is skipped).

    Returns
    -------
    list of dict
        ``{"point": [x, y, z], "normal": [x, y, z]}`` planes in local coords; the
        normal is a unit vector pointing toward the neighbour (the removed side).
    """
    planes: list[dict[str, Any]] = []
    cx, cy, cz = entry["pos"]
    for other in neighbours:
        if other is entry:
            continue
        ox, oy, oz = other["pos"]
        dx, dy, dz = ox - cx, oy - cy, oz - cz
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 1e-6:
            continue
        n = (dx / dist, dy / dist, dz / dist)
        reach_self = _directional_extent(entry["radii"], entry["noise"], n)
        reach_other = _directional_extent(
            other["radii"], other["noise"], (-n[0], -n[1], -n[2]))
        # No overlap along this axis: the surfaces never meet, nothing to cut.
        if dist >= reach_self + reach_other:
            continue
        # Seam distance from this centre toward the neighbour, split in proportion
        # to each body's reach. Since dist < reach_self + reach_other, this stays
        # < reach_self (and the complement < reach_other), so the cut sits inside
        # the overlap and never reaches past either surface.
        seam = dist * reach_self / (reach_self + reach_other)
        planes.append({
            "point": [round(n[0] * seam, 3), round(n[1] * seam, 3),
                      round(n[2] * seam, 3)],
            "normal": [round(n[0], 3), round(n[1], 3), round(n[2], 3)],
        })
    return planes
