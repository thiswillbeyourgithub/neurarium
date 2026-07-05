"""diencephalon region records (split from generate_data.py, verbatim).

Exposes PAIRED and MIDLINE (either may be empty) in original order.
"""
from typing import Any

PAIRED: list[dict[str, Any]] = [
    dict(base="hypothalamus", name="Hypothalamus", group="diencephalon",
         pos=(0.45, -0.45, 0.3), color="#c98ac9",
         scale=(0.6, 0.45, 0.5),  # anatomical: a small ~11x10x12mm region
         # SDF (self-authored atlas, see geometry_refinements/). Small nucleus
         # cluster below and anterior to the thalamus, forming the floor + lower
         # walls of the third ventricle (hugs the midline, small pos.x). Its
         # characteristic feature is the INFUNDIBULAR FUNNEL: the floor (tuber
         # cinereum / median eminence) tapers downward and medially toward the
         # midline pituitary stalk. Modeled as a rounded mass smooth-unioned with a
         # short inferior funnel angled medially, under a light displace; res 72.
         # The mirrored _L funnel angles the other way, so the pair converges on the
         # midline. Position is a guess: tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=72,
             root=dict(op="displace", amp=0.012, freq=3.2, seed=52, nodes=[
                 dict(op="smoothUnion", k=0.14, nodes=[
                     dict(prim="ellipsoid", center=[0.0, 0.06, 0.0],
                          radii=[0.38, 0.34, 0.50]),       # the bulk
                     dict(prim="roundcone",
                          a=[0.0, -0.16, 0.04], r1=0.20,
                          b=[-0.22, -0.46, 0.04], r2=0.08),  # infundibular funnel
                 ]),
             ])),
         ),
    dict(base="mammillary", name="Mammillary bodies", group="diencephalon", fr_gender="mp",
         pos=(0.35, -0.8, -0.2), color="#c6b06a",
         scale=0.55,  # anatomical: pea-sized ~5mm bodies
         # Tiny paired bumps at the posterior base of the hypothalamus (the
         # Papez node between the fornix and the anterior thalamus). Small smooth
         # blob, kept just clear of the hypothalamus so they don't fuse. Position
         # is a guess: tune in a browser.
         radii=(0.18, 0.17, 0.2), seed=71, detail=4, noise=0.04),
]

MIDLINE: list[dict[str, Any]] = [
    dict(base="pituitary", name="Pituitary gland", group="diencephalon",
         pos=(0.0, -1.0, 0.35), color="#d2a06e",
         scale=(0.9, 0.5, 0.7),  # anatomical: ~10x9x6mm (bean-sized)
         # SDF (self-authored atlas, see geometry_refinements/). The defining shape
         # is GLAND-ON-A-STALK: a small bean-shaped gland (wider mediolaterally than
         # tall) seated in the sella turcica, with a thin INFUNDIBULAR STALK rising
         # from its top toward the hypothalamus above. Modeled as a bean ellipsoid
         # smooth-unioned with a slender tapered roundcone stalk, under a faint
         # displace; res 72, tight bounds for the thin stalk. Midline (no mirror).
         # Hides centrally at explode 0, revealed on blow-out. Position is a guess:
         # tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=72,
             bounds=[[-0.28, -0.28, -0.28], [0.28, 0.62, 0.30]],
             root=dict(op="displace", amp=0.008, freq=5.0, seed=72, nodes=[
                 dict(op="smoothUnion", k=0.08, nodes=[
                     dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                          radii=[0.22, 0.18, 0.20]),       # the bean gland
                     dict(prim="roundcone",
                          a=[0.0, 0.10, 0.04], r1=0.07,
                          b=[0.0, 0.50, 0.0], r2=0.05),     # infundibular stalk
                 ]),
             ])),
         ),
]

