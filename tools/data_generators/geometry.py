"""Shared cortical-dome geometry helpers used by the region records.

Extracted from generate_data.py so data_generators.regions can build the
cortical-lobe SDF sectors without importing the CLI module (a cycle).
"""

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
