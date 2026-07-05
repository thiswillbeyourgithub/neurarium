"""limbic region records (split from generate_data.py, verbatim).

Exposes PAIRED and MIDLINE (either may be empty) in original order.
"""
from typing import Any

PAIRED: list[dict[str, Any]] = [
    # --- Limbic / diencephalon ---
    dict(base="hippocampus", name="Hippocampus", group="limbic",
         pos=(1.3, -0.7, -0.2), color="#b3823e",
         scale=(0.95, 0.6, 0.8),  # anatomical: ~15x24x40mm (was too tall)
         # SDF (self-authored atlas, see geometry_refinements/). Curved
         # allocortical "seahorse" in the floor of the temporal lobe, swept on a
         # genuinely 3D spline so no orthogonal view collapses to a bulb-on-a-shaft:
         #   - sagittal (y-z): a strong comma. Head hooks down + under at the
         #     antero-inferior tip; body sweeps up + posterior; tail hooks up +
         #     forward toward the splenium.
         #   - transverse (x): head sits LATERAL, the body/tail curve MEDIALLY as
         #     they run back (the paired tails converge toward the splenium). This
         #     is what makes the front/top silhouettes read as a curved form, and it
         #     is anatomically right. Mirroring negates x, so the _L member curves
         #     the other way (correct: its head is lateral on the left).
         # Slender (length >> caliber, the head only modestly wider than the body).
         # Anatomical detail: a beaded dentate-gyrus ridge along the inferomedial
         # edge (the "teeth" the dentate is named for), three pes digitations, all
         # under a light displace so the detail survives. Authored in local space;
         # `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=112,
             root=dict(op="displace", amp=0.006, freq=5.5, seed=51, nodes=[
                 # Outer join: hang the dentate beads off the body as distinct teeth.
                 dict(op="smoothUnion", k=0.045, nodes=[
                     dict(op="smoothUnion", k=0.10, nodes=[
                         # Slim tapered body on the 3D comma spline.
                         dict(prim="tube",
                              points=[
                                  [0.20, -0.50, 1.02],   # head: lateral + anterior + inferior
                                  [0.16, -0.60, 0.64],   # head curls under (lowest)
                                  [0.08, -0.46, 0.24],   # body rising + going medial
                                  [-0.02, -0.16, -0.18],
                                  [-0.10, 0.20, -0.54],  # sweeping medial + up + posterior
                                  [-0.13, 0.52, -0.82],  # tail
                                  [-0.10, 0.82, -0.66],  # tail tip hooks up + forward
                              ],
                              profile=[0.13, 0.15, 0.16, 0.145, 0.125, 0.095, 0.055]),
                         # Pes hippocampi: small flattened base paw + three finger-like
                         # digitations fanned around the lateral head tip (tight k ->
                         # distinct bumps).
                         dict(op="smoothUnion", k=0.05, nodes=[
                             dict(prim="ellipsoid", center=[0.16, -0.52, 0.78],
                                  radii=[0.15, 0.12, 0.18]),
                             dict(prim="sphere", center=[0.06, -0.57, 0.97], radius=0.09),
                             dict(prim="sphere", center=[0.17, -0.61, 1.03], radius=0.095),
                             dict(prim="sphere", center=[0.28, -0.57, 0.96], radius=0.09),
                         ]),
                     ]),
                     # Dentate-gyrus beading: a row of small spheres along the
                     # inferomedial (-x, -y) edge of the body, from anterior body to
                     # tail; the tight outer k=0.045 keeps them as a scalloped ridge.
                     dict(prim="sphere", center=[0.02, -0.54, 0.30], radius=0.075),
                     dict(prim="sphere", center=[-0.06, -0.34, 0.06], radius=0.075),
                     dict(prim="sphere", center=[-0.14, -0.10, -0.22], radius=0.07),
                     dict(prim="sphere", center=[-0.19, 0.16, -0.48], radius=0.07),
                     dict(prim="sphere", center=[-0.22, 0.38, -0.68], radius=0.065),
                     dict(prim="sphere", center=[-0.20, 0.56, -0.82], radius=0.055),
                 ]),
             ]),
         )),
    dict(base="amygdala", name="Amygdala", group="limbic", fr_gender="f",
         pos=(1.45, -0.35, 0.95), color="#9b7bb0",
         scale=(0.75, 0.5, 0.6),  # anatomical: an ~14x12x18mm almond
         # SDF (self-authored atlas, see geometry_refinements/). The ALMOND
         # (amygdala = "almond"): an elongated nut, rounded and fat at its
         # antero-superior pole, tapering postero-inferiorly to a blunter point
         # where it caps the head of the hippocampus, in the medial temporal lobe
         # (emotion/fear hub). Modeled as a roundcone (tapered capsule) along that
         # AS -> PI axis, under a light displace; res 64. Sits inside the temporal
         # lobe at explode 0. Position is an anatomical guess: tune in a browser.
         # Provenance: llm.
         shape=dict(
             type="sdf", resolution=64,
             root=dict(op="displace", amp=0.012, freq=3.4, seed=54, nodes=[
                 dict(prim="roundcone",
                      a=[0.0, 0.14, 0.30], r1=0.40,    # fat antero-superior pole
                      b=[0.06, -0.26, -0.34], r2=0.22),  # blunt postero-inferior tip
             ])),
         ),
    dict(base="cingulate", name="Cingulate gyrus", group="limbic",
         pos=(0.5, 0.6, 0.0), color="#6fa39c",
         # SDF (self-authored atlas, see geometry_refinements/). The limbic-lobe
         # arch: a C-shaped band of cortex on the medial wall, curving over the
         # corpus callosum from the subgenual front, up and over, to the splenial
         # back. A GYRUS is a ribbon, not a worm, so it is modeled as a swept tube
         # along the parasagittal (local x~0) arch INTERSECTED with a thin-x slab:
         # the result is a flattened band, thin mediolaterally (~0.22) and tall
         # radially (the tube diameter), reading as the gyrus it is. Under a gentle
         # displace; res 100 to resolve the thin ribbon over the long arch. Hugs the
         # midline (small pos.x); the _L member mirrors it. Position is a guess:
         # tune in a browser, especially against the (commissural) corpus-callosum
         # arrow. Provenance: llm.
         shape=dict(
             type="sdf", resolution=100,
             bounds=[[-0.26, -0.95, -1.72], [0.26, 1.62, 1.72]],
             root=dict(op="displace", amp=0.02, freq=2.6, seed=55, nodes=[
                 dict(op="intersect", nodes=[
                     dict(prim="tube",
                          points=[
                              [0.0, -0.5, 1.3],    # subgenual, anterior + low
                              [0.0, 0.4, 1.5],     # rising in front of the genu
                              [0.0, 1.0, 0.95],    # anterior arch
                              [0.0, 1.2, 0.0],     # top of the arch
                              [0.0, 1.0, -0.95],   # posterior arch
                              [0.0, 0.3, -1.5],    # descending toward the splenium
                              [0.0, -0.45, -1.25],  # isthmus, posterior + low
                          ],
                          profile=[0.18, 0.3, 0.34, 0.34, 0.32, 0.28, 0.18]),
                     # thin-x slab: flattens the round tube into a gyrus ribbon.
                     dict(prim="box", center=[0.0, 0.35, 0.0],
                          half=[0.11, 1.25, 1.65], round=0.02),
                 ]),
             ])),
         ),
    dict(base="fornix", name="Fornix", group="limbic",
         pos=(0.4, 0.2, -0.3), color="#d9d2c4",
         # The hippocampal output tract: a thin white-matter arch sweeping from
         # the hippocampus (posterior) up under the corpus callosum and forward,
         # then down as the columns toward the mammillary bodies. A slender
         # parasagittal curve (mirrored for the _L side). Position is a guess:
         # tune in a browser.
         shape=dict(
             type="curve",
             points=[
                 (0.0, -0.1, -1.0),   # crus, by the hippocampal tail (posterior)
                 (0.0, 0.6, -0.55),   # arching up
                 (0.0, 0.8, 0.2),     # body, under the callosum
                 (0.0, 0.15, 0.6),    # the descending column (anterior)
                 (0.0, -0.65, 0.5),   # toward the mammillary body
             ],
             profile=[0.1, 0.12, 0.12, 0.1, 0.08],
             seed=56, noise=0.05, radial_segments=10, tubular_segments=80,
         )),
    dict(base="olfactory_bulb", name="Olfactory bulb", group="limbic",
         pos=(0.45, -1.05, 2.7), color="#9aa86f",
         scale=(0.6, 0.6, 1.0),  # anatomical: thin bulb+tract, ~5mm wide (was too fat)
         # SDF (self-authored atlas, see geometry_refinements/). A match-stick on
         # the orbital underside of the frontal lobe: a swollen anterior BULB (on
         # the cribriform plate) tapering into a thin posterior olfactory TRACT that
         # rises gently as it runs back toward the brain. Modeled as an ovoid bulb
         # smooth-unioned with a slender tapered roundcone tract, under a faint
         # displace; res 80, tight bounds to resolve the thin tract. Near the
         # midline. Position is a guess: tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=80,
             bounds=[[-0.26, -0.26, -0.62], [0.26, 0.30, 0.56]],
             root=dict(op="displace", amp=0.008, freq=5.0, seed=57, nodes=[
                 dict(op="smoothUnion", k=0.10, nodes=[
                     dict(prim="ellipsoid", center=[0.0, 0.0, 0.22],
                          radii=[0.19, 0.18, 0.24]),     # the bulb (anterior)
                     dict(prim="roundcone",
                          a=[0.0, 0.0, 0.10], r1=0.11,
                          b=[0.0, 0.06, -0.50], r2=0.05),  # the tract (posterior)
                 ]),
             ])),
         ),
    dict(base="septal_nuclei", name="Septal nuclei", group="limbic", fr_gender="mp",
         pos=(0.3, 0.1, 0.85), color="#7f9cc0",
         scale=(0.9, 0.6, 0.9),  # anatomical: small paramedian nuclei, ~10mm (was tall)
         # SDF (self-authored atlas, see geometry_refinements/). Small paramedian
         # grey matter below the rostrum of the corpus callosum, anterior to the
         # thalamus and above the hypothalamus (a Papez/limbic relay). It has no
         # distinctive silhouette: a small ovoid set in the thin septal wall, so it
         # is a vertical ellipsoid flattened mediolaterally (thin in x), under a
         # faint displace; res 56. Near the midline. Position is a guess: tune in a
         # browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=56,
             root=dict(op="displace", amp=0.01, freq=4.0, seed=58, nodes=[
                 dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                      radii=[0.20, 0.34, 0.22]),
             ])),
         ),
]

MIDLINE: list[dict[str, Any]] = [
]

