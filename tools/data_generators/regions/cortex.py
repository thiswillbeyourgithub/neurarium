"""cortex region records (split from generate_data.py, verbatim).

Exposes PAIRED and MIDLINE (either may be empty) in original order.
"""
from typing import Any

from data_generators.geometry import (
    _CENTRAL_N_FRONT, _CENTRAL_PT, _SYLVIAN_N_UP, _SYLVIAN_PT,
    _TEMPORAL_BITE, _TEMPORAL_MEDIAL_X, _cortex_lobe_entry, _neg,
)

PAIRED: list[dict[str, Any]] = [
    # --- Cortical lobes (large, outer shell) ---
    # The four main lobes are sectors of ONE shared cortical dome (see
    # _cortex_lobe), carved by planes they share so they reassemble seamlessly at
    # explode 0. The fissures are OBLIQUE (tilted) so the seams read like the real
    # central / Sylvian fissures, not axis-aligned slabs (world coords):
    #   central  through (1.15,0.55,0.4), tilted forward going down -> frontal
    #            (anterior) | parietal (posterior)
    #   Sylvian  through (1.15,-0.1,0.2), rising posteriorly -> fronto-parietal
    #            (above) | temporal (below), but ONLY lateral of x=0.95: the
    #            temporal is a LATERAL inferior wedge (the _TEMPORAL_BITE), so the
    #            frontal+parietal keep their inferomedial / orbital surface and the
    #            temporal no longer slabs across the midline.
    #   par-occ  z = -1.90 -> occipital is the whole posterior cap.
    # Muted pink palette, low saturation so they read as one cortex; each a
    # slightly different hue (frontal=rose, parietal=pink, temporal=salmon,
    # occipital=mauve-pink) so the four stay tellable apart. Provenance: llm.
    _cortex_lobe_entry("frontal", "Frontal lobe", "#c58c9a", (0.85, 1.0, 2.2),
                       [("plane", _CENTRAL_N_FRONT, _CENTRAL_PT), ("z", ">", -0.7)], 11,
                       subtract_regions=[_TEMPORAL_BITE]),
    _cortex_lobe_entry("parietal", "Parietal lobe", "#c69597", (0.85, 1.8, -0.2),
                       [("plane", _neg(_CENTRAL_N_FRONT), _CENTRAL_PT),
                        ("z", ">", -1.9), ("z", "<", 1.3)], 12,
                       subtract_regions=[_TEMPORAL_BITE]),
    _cortex_lobe_entry("temporal", "Temporal lobe", "#c79a8e", (2.1, -0.75, 0.6),
                       [("plane", _neg(_SYLVIAN_N_UP), _SYLVIAN_PT),
                        ("z", ">", -1.9), ("x", ">", _TEMPORAL_MEDIAL_X),
                        ("y", "<", 0.5)], 13),
    _cortex_lobe_entry("occipital", "Occipital lobe", "#bf8da6", (0.72, 0.75, -2.9),
                       [("z", "<", -1.9)], 14),
    dict(base="insula", name="Insula", group="lobe", fr_gender="f",
         pos=(1.95, 0.3, 0.5), color="#ae7aa3",
         # The hidden 5th lobe: insular cortex buried deep to the lateral
         # (Sylvian) sulcus, overlying the putamen. Now that the four big lobes
         # are SOLID dome sectors abutting at the Sylvian plane (no lateral gap),
         # the deep nuclei are already covered, so the insula only has to (a) stay
         # buried INSIDE the cortical surface at explode 0 and (b) read as a small
         # gyrified patch when the lobes blow apart. A mediolaterally-thin SDF
         # ellipsoid with gentle gyri: its lateral edge sits at x ~ 2.35, inside
         # the cortex (whose gyral troughs here reach ~2.5), so it no longer pokes
         # out. It reveals laterally on explode (pos is the radial anchor).
         shape=dict(type="sdf", resolution=64,
                    bounds=[[-0.6, -1.2, -1.35], [0.6, 1.2, 1.35]],
                    root=dict(op="displace", octaves=2, freq=2.6, amp=0.1,
                              unit=1.1, seed=15,
                              nodes=[dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                                          radii=[0.4, 0.95, 1.1])]))),
]

MIDLINE: list[dict[str, Any]] = [
]

