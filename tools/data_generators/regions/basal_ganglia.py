"""basal_ganglia region records (split from generate_data.py, verbatim).

Exposes PAIRED and MIDLINE (either may be empty) in original order.
"""
from typing import Any

PAIRED: list[dict[str, Any]] = [
    # --- Basal ganglia & deep nuclei (small, inner) ---
    dict(base="caudate", name="Caudate nucleus", group="basal_ganglia",
         # Retracted (y was 1.9, an earlier "emerge through the fronto-parietal
         # seam" experiment) so the bulbous head now sits below the cortical
         # surface and stays hidden inside the assembled brain at explode 0,
         # surfacing only as the lobes blow apart: anatomically deeper and no
         # longer poking out between the lobes.
         pos=(1.2, 1.1, 0.8), color="#ff9da7",
         scale=(0.95, 0.67, 0.66),  # anatomical: ~14x38x42mm (was too tall/long)
         # SDF (self-authored atlas, see geometry_refinements/). The caudate is
         # the comma/tadpole of the basal ganglia, wrapping over + behind the
         # thalamus along the lateral ventricle: a large BULBOUS HEAD (anterior +
         # superior, bulging into the frontal horn), the body arching up + back
         # over the thalamus, then a long WISPY TAIL descending at the back and
         # hooking down + forward into the temporal lobe (toward the amygdala).
         # Modeled as a slim tapered `tube` on a 3D comma spline (the tail swings
         # gently LATERAL as it dives into the temporal horn, so no orthogonal
         # view collapses to a flat C) smooth-unioned with a distinct head bulb,
         # under a light displace. Mirroring negates x, so the _L tail swings
         # lateral on the left too. Authored in local space (z anterior+, y
         # superior+); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=112,
             bounds=[[-0.42, -1.45, -1.35], [0.52, 1.2, 1.6]],
             root=dict(op="displace", amp=0.006, freq=5.0, seed=21, nodes=[
                 dict(op="smoothUnion", k=0.12, nodes=[
                     # Body + tail: slim tube tapering head -> wispy tail along the
                     # comma; the head end is modest (the bulb below adds the heft).
                     # The tail descends the posterior wall then HOOKS DOWNWARD into
                     # the temporal horn (it does NOT run forward under the head), so
                     # the comma's opening faces INFERIOR, not anterior.
                     dict(prim="tube",
                          points=[
                              [0.0, 0.45, 0.92],    # head/body junction (anterior)
                              [0.02, 0.72, 0.58],   # body rising
                              [0.05, 0.88, 0.15],
                              [0.07, 0.93, -0.30],  # arch peak (superior)
                              [0.10, 0.82, -0.70],  # starting to descend
                              [0.15, 0.45, -1.00],  # descending posterior, swinging lateral
                              [0.20, -0.12, -1.08], # down the posterior wall (most posterior)
                              [0.23, -0.66, -0.90], # rounding the back-bottom corner
                              [0.22, -1.00, -0.45], # into the temporal horn, well below the body
                              [0.18, -1.10, 0.08],  # tail running forward along the horn floor
                              [0.14, -1.28, 0.34],  # tail tip hooking DOWN (caudal extremity)
                          ],
                          profile=[0.18, 0.165, 0.155, 0.15, 0.14, 0.125,
                                   0.105, 0.085, 0.065, 0.05, 0.035]),
                     # Bulbous head: a tall ovoid (taller than wide, per the front
                     # view) bulging anterosuperiorly into the frontal horn.
                     dict(prim="ellipsoid", center=[0.0, 0.42, 1.06],
                          radii=[0.30, 0.44, 0.40]),
                 ]),
             ])),
         ),
    dict(base="putamen", name="Putamen", group="basal_ganglia",
         pos=(1.9, 0.2, 0.6), color="#f28e2b",
         scale=(0.69, 0.48, 0.55),  # anatomical: ~14x24x32mm (was ~2x too tall)
         # SDF (self-authored atlas, see geometry_refinements/). The putamen is
         # the most lateral basal nucleus: a rounded lens/shell flattened
         # mediolaterally (thin x), taller (y) and deep (z), gently scalloped on
         # its medial face where the globus pallidus nests. Authored in local
         # space (centered on origin); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=72,
             root=dict(op="displace", amp=0.018, freq=3.2, seed=22, nodes=[
                 dict(op="subtract", k=0.18, nodes=[
                     # Lens body, nudged a touch lateral so the medial scoop bites
                     # the inner face, not the centre.
                     dict(prim="ellipsoid", center=[0.06, 0, 0],
                          radii=[0.45, 1.05, 1.2]),
                     # Scoop the medial (-x) face concave, cradling the globus
                     # pallidus that nests against it.
                     dict(prim="sphere", center=[-1.18, 0.0, -0.1], radius=0.95),
                 ]),
             ]),
         )),
    dict(base="globus_pallidus", name="Globus pallidus", group="basal_ganglia",
         pos=(1.5, 0.0, 0.2), color="#76b7b2",
         scale=(0.5, 0.65, 0.8),  # anatomical: ~10x16x20mm
         # SDF (self-authored atlas, see geometry_refinements/). The inner, medial
         # part of the lentiform nucleus: a WEDGE/cone tapering to a medial apex
         # (pointing toward the internal capsule / thalamus) with a convex lateral
         # face nesting into the putamen's medial scoop. Modeled as a
         # medially-tapering roundcone (the wedge taper) intersected with a tall,
         # AP-extended ellipsoid (the envelope + convex lateral face), the join
         # rounded by smoothIntersect, under a light displace. Together with the
         # putamen it reads as the lens-shaped lentiform nucleus. Authored in local
         # space (x lateral+); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=72,
             root=dict(op="displace", amp=0.012, freq=3.4, seed=23, nodes=[
                 dict(op="smoothIntersect", k=0.1, nodes=[
                     # Mediolateral taper: fat lateral end -> pointed medial apex.
                     dict(prim="roundcone", a=[0.3, 0.0, 0.0], r1=0.55,
                          b=[-0.5, 0.0, 0.0], r2=0.1),
                     # Tall, AP-extended envelope (convex lateral face for the scoop).
                     dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                          radii=[0.42, 0.72, 0.82]),
                 ]),
             ])),
         ),
    dict(base="thalamus", name="Thalamus", group="basal_ganglia",
         pos=(0.9, 0.4, -0.6), color="#bab0ac",
         scale=(0.87, 0.77, 0.62),  # anatomical: ~25x22x32mm (AP was too long)
         # SDF (self-authored atlas, see geometry_refinements/). The biggest deep
         # nucleus: an elongated EGG with a narrower anterior pole (the anterior
         # tubercle) and a bulbous posterior PULVINAR overhanging the geniculate
         # bodies, the long axis running anteromedial -> posterolateral. Modeled as
         # a main ovoid smooth-unioned with a posterolateral pulvinar sphere
         # (asymmetry = the egg taper + the tilt), under a light displace; the
         # anterior ellipsoid is nudged medial, the pulvinar lateral. Mirroring
         # negates x, so the _L tilt is correct on the left. Authored in local
         # space (z anterior+, x lateral+); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=80,
             # A single tapered roundcone = a clean teardrop egg (narrow rounded
             # anterior pole -> bulbous posterior pulvinar), no fused-balls waist.
             # The axis is tilted anteromedial(up) -> posterolateral(down).
             root=dict(op="displace", amp=0.012, freq=3.0, seed=24, nodes=[
                 dict(prim="roundcone",
                      a=[-0.07, 0.04, 0.66], r1=0.39,    # anterior pole (narrow)
                      b=[0.10, -0.04, -0.53], r2=0.60),  # posterior pulvinar (bulbous)
             ])),
         ),
    dict(base="subthalamic_nucleus", name="Subthalamic nucleus",
         group="basal_ganglia",
         pos=(0.75, -0.35, -0.55), color="#d37295",
         scale=0.3,  # anatomical: a tiny ~5-7mm lens (was ~4x too big)
         # SDF (self-authored atlas, see geometry_refinements/). The tiny biconvex
         # LENS (lentil) of the subthalamus: two large spheres offset along the
         # thin (DV) axis, intersected so their overlap is a lens with a crisp
         # equatorial edge (the lens character a rounded ellipsoid lacks), then
         # clipped by an AP-elongated ellipsoid so it is longer front-to-back than
         # wide, under a faint displace; res 60. Authored in local space (y thin);
         # `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=60,
             root=dict(op="displace", amp=0.008, freq=4.5, seed=25, nodes=[
                 dict(op="smoothIntersect", k=0.05, nodes=[
                     dict(prim="sphere", center=[0.0, 0.55, 0.0], radius=0.78),
                     dict(prim="sphere", center=[0.0, -0.55, 0.0], radius=0.78),
                     # AP-elongated, ML-narrow clip (the lens outline).
                     dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                          radii=[0.34, 0.5, 0.54]),
                 ]),
             ])),
         ),
    dict(base="substantia_nigra", name="Substantia nigra",
         group="basal_ganglia", fr_gender="f",
         pos=(0.55, -0.6, -0.6), color="#3d3d3d",
         scale=(0.6, 0.45, 0.45),  # anatomical: a thin ~9x5x17mm band
         # SDF (self-authored atlas, see geometry_refinements/). A thin, gently
         # CURVED lamina in the midbrain hugging the back of the cerebral peduncle
         # (concave anteromedially), not a flat lens. Modeled as three flattened
         # (thin-DV) ellipsoids smooth-unioned along an antero-posterior arc whose
         # middle is bowed laterally, so the band is concave toward the midline,
         # under a light displace; res 64. Mirroring negates x, so the _L band is
         # concave-medial too. Authored in local space (z anterior+, x lateral+,
         # y thin); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=64,
             root=dict(op="displace", amp=0.01, freq=4.0, seed=26, nodes=[
                 dict(op="smoothUnion", k=0.30, nodes=[
                     dict(prim="ellipsoid", center=[0.06, 0.03, -0.44],
                          radii=[0.34, 0.16, 0.34]),   # posterior end
                     dict(prim="ellipsoid", center=[0.22, 0.0, 0.0],
                          radii=[0.36, 0.16, 0.34]),   # middle, bowed lateral
                     dict(prim="ellipsoid", center=[0.06, -0.03, 0.44],
                          radii=[0.32, 0.16, 0.32]),   # anterior end
                 ]),
             ])),
         ),
    dict(base="accumbens", name="Nucleus accumbens", group="basal_ganglia",
         pos=(0.95, -0.5, 1.0), color="#e0997e",
         scale=(0.5, 0.32, 0.42),  # anatomical: ~10x9x8mm (was ~3x too tall)
         # SDF (self-authored atlas, see geometry_refinements/). Ventral striatum,
         # where the head of the caudate meets the putamen ventrally and anteriorly
         # (the reward hub, target of the mesolimbic dopamine pathway). It has no
         # distinctive standalone silhouette: a rounded mass that is the inferior
         # corner of the striatum, so it is modeled as a gentle TEARDROP, a
         # roundcone fat at the free ventral pole tapering dorsally (and slightly
         # posterolateral) into the striatum, under a light displace; res 64.
         # Position is an anatomical guess: tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=64,
             root=dict(op="displace", amp=0.012, freq=3.6, seed=27, nodes=[
                 dict(prim="roundcone",
                      a=[0.0, -0.28, 0.10], r1=0.42,   # fat ventral pole
                      b=[0.06, 0.40, -0.16], r2=0.16),  # taper up into the striatum
             ])),
         ),
    dict(base="claustrum", name="Claustrum", group="basal_ganglia",
         pos=(2.3, 0.1, 0.5), color="#8d97ab",
         scale=0.62,  # anatomical: a thin curved ~4x21x28mm sheet, seated medial
         # to the insula (was poking out lateral to it). Uniform on purpose: this is
         # a spherical-shell construction whose surface sits at (center + radius), so
         # anisotropic scaling (center per-axis, scalar radius by the mean) would
         # slide the shell off its bounds and mesh to nothing.
         # SDF (self-authored atlas, see geometry_refinements/). A thin, gently
         # curved vertical lamina of grey matter between the insula (lateral) and
         # the putamen (medial): a thin spherical SHELL (so it is curved, concave
         # toward the medial putamen it drapes over, not a flat slab) clipped by an
         # ellipsoid to the claustrum's tall, narrow y/z patch. Explicit tight
         # bounds keep the ~0.09-thick sheet well-resolved cheaply. Authored in
         # local space; `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=96,
             bounds=[[-0.25, -0.95, -1.2], [0.25, 0.95, 1.2]],
             # smoothIntersect rounds the thin shell-meets-clip rim (a hard
             # intersect leaves a shallow-angle edge that marching cubes steps).
             root=dict(op="smoothIntersect", k=0.06, nodes=[
                 # ~0.09-thick curved shell (outer ~x=0.06, inner ~x=-0.03).
                 dict(op="subtract", nodes=[
                     dict(prim="sphere", center=[-2.3, 0, 0], radius=2.36),
                     dict(prim="sphere", center=[-2.3, 0, 0], radius=2.27),
                 ]),
                 # Clip the shell to the claustrum's tall, narrow patch.
                 dict(prim="ellipsoid", center=[0, 0, 0], radii=[1.0, 0.72, 0.95]),
             ]),
         )),
]

MIDLINE: list[dict[str, Any]] = [
]

