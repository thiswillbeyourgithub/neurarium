"""hindbrain region records (split from generate_data.py, verbatim).

Exposes PAIRED and MIDLINE (either may be empty) in original order.
"""
from typing import Any

PAIRED: list[dict[str, Any]] = [
]

MIDLINE: list[dict[str, Any]] = [
    dict(base="cerebellum", name="Cerebellum", group="hindbrain",
         pos=(0.0, -1.55, -3.3), color="#b07aa1",
         scale=(0.88, 0.85, 0.74),  # anatomical: ~103x48x55mm (was a bit large/deep)
         # SDF (self-authored atlas, see geometry_refinements/). The cerebellum's
         # "butterfly": two hemispheres flanking a narrower, slightly taller central
         # VERMIS, smooth-unioned into ONE continuous mass (soft paravermian valleys,
         # not three separate balls). The signature transverse FOLIA are PAINTED ON,
         # not carved: `pattern="folia"` tells the viewer to cel-shade it like the
         # cortex and ink stacked near-horizontal fold lines (CEREBELLUM_FOLIA in
         # shapes.js). So the geometry stays a cheap SMOOTH mass (only a faint
         # displace for an organic surface) at a modest ISOTROPIC resolution, instead
         # of the costly ridged displace + anisotropic [Nx,Ny,Nz] grid the carved
         # folia needed. Sits below/behind the occipital lobes (under the tentorium)
         # with the brainstem in front of it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=56, pattern="folia",
             bounds=[[-2.65, -1.40, -1.78], [2.65, 1.40, 1.78]],
             root=dict(op="displace", amp=0.03, freq=2.6, octaves=1,
                       unit=1.0, seed=31, nodes=[
                 dict(op="smoothUnion", k=0.35, nodes=[
                     dict(prim="ellipsoid", center=[-1.12, 0.0, 0.0],
                          radii=[1.33, 1.0, 1.5]),     # left hemisphere
                     dict(prim="ellipsoid", center=[1.12, 0.0, 0.0],
                          radii=[1.33, 1.0, 1.5]),     # right hemisphere
                     dict(prim="ellipsoid", center=[0.0, 0.0, -0.08],
                          radii=[0.46, 1.2, 1.5]),     # vermis (narrow, taller ridge)
                 ]),
             ]))),
    # The brainstem, cut into its three anatomical levels (midbrain -> pons ->
    # medulla) as separate midline structures instead of one swept tube, so each
    # is selectable and they come apart on explode. The three curve segments share
    # their boundary spine points (round-capped tubes that overlap a hair at the
    # joints), so at explode 0 they still read as one continuous tapering column
    # where the old single brainstem sat. Each carries its own pos at its centre so
    # it explodes radially on its own. Midline structures, never mirrored. (The pons
    # is the level the modeled corticopontine + pontocerebellar pathways actually
    # name, which is what justified splitting the column out, see "Drugs"/CLAUDE.md
    # granularity note.)
    dict(base="midbrain", name="Midbrain", group="hindbrain",
         pos=(0.0, -0.51, -0.66), color="#9c755f",
         scale=(0.74, 0.4, 0.7),  # anatomical: short ~18-20mm segment (was ~55mm tall)
         # SDF (self-authored atlas, see geometry_refinements/). Top brainstem
         # segment, continuous with the diencephalon/thalamus above. Its signature
         # is the dorsal TECTAL (quadrigeminal) PLATE: four colliculi, the superior +
         # inferior pair each side, bulging posteriorly (toward the cerebellum).
         # Modeled as a vertical roundcone body (narrower at the top, widening down
         # to meet the pons) smooth-unioned with four small colliculus spheres on the
         # posterior (-z) dorsal surface, under a light displace; res 80. Midline.
         # Provenance: llm.
         shape=dict(
             type="sdf", resolution=80,
             root=dict(op="displace", amp=0.012, freq=3.2, seed=32, nodes=[
                 dict(op="smoothUnion", k=0.12, nodes=[
                     dict(prim="roundcone",
                          a=[0.0, 0.70, -0.08], r1=0.44,    # top, under the thalamus
                          b=[0.0, -0.60, 0.10], r2=0.56),   # tail, meeting the pons
                     # tectal plate: superior + inferior colliculi, both sides.
                     dict(prim="sphere", center=[0.20, 0.18, -0.40], radius=0.17),
                     dict(prim="sphere", center=[-0.20, 0.18, -0.40], radius=0.17),
                     dict(prim="sphere", center=[0.18, -0.16, -0.46], radius=0.15),
                     dict(prim="sphere", center=[-0.18, -0.16, -0.46], radius=0.15),
                 ]),
             ])),
         ),
    dict(base="pons", name="Pons", group="hindbrain",
         pos=(0.0, -1.43, -0.45), color="#8c6a58",
         scale=0.87,  # anatomical: ~27mm tall (already close); raised to meet midbrain
         # SDF (self-authored atlas, see geometry_refinements/). Middle brainstem
         # segment, the fullest. Its defining feature is the BASIS PONTIS: a rounded
         # belly bulging ANTERIORLY (+z) that a radially-symmetric curve tube cannot
         # make. Modeled as a body ellipsoid (wider mediolaterally, tapering up/down
         # to meet the midbrain + medulla) smooth-unioned with an anterior belly
         # ellipsoid, under a light displace; res 80. Midline. Provenance: llm.
         shape=dict(
             type="sdf", resolution=80,
             root=dict(op="displace", amp=0.014, freq=3.0, seed=33, nodes=[
                 dict(op="smoothUnion", k=0.30, nodes=[
                     dict(prim="ellipsoid", center=[0.0, 0.0, -0.05],
                          radii=[0.72, 0.64, 0.46]),       # body
                     dict(prim="ellipsoid", center=[0.0, -0.05, 0.30],
                          radii=[0.60, 0.50, 0.36]),       # anterior belly
                 ]),
             ])),
         ),
    dict(base="medulla", name="Medulla", group="hindbrain",
         pos=(0.0, -2.61, -0.75), color="#7d5f4e",
         scale=(0.74, 0.55, 0.8),  # anatomical: ~30mm tall (was ~55mm); raised to meet pons
         # SDF (self-authored atlas, see geometry_refinements/). Bottom brainstem
         # segment, narrowing toward the spinal cord. Its ventral surface carries the
         # two PYRAMIDS (longitudinal ridges flanking the anterior median fissure)
         # and, ventrolaterally on the upper medulla, the OLIVES (the inferior
         # olivary bumps). Modeled as a vertical roundcone body (tapering down to the
         # cord) smooth-unioned with two ventral pyramid ridges (slim roundcones) +
         # two olive ellipsoids, under a light displace; res 84. Midline.
         # Provenance: llm.
         shape=dict(
             type="sdf", resolution=84,
             root=dict(op="displace", amp=0.012, freq=3.4, seed=34, nodes=[
                 dict(op="smoothUnion", k=0.10, nodes=[
                     dict(prim="roundcone",
                          a=[0.0, 0.72, 0.14], r1=0.52,     # head, meeting the pons
                          b=[0.0, -0.72, -0.08], r2=0.32),  # tail, toward the cord
                     # ventral pyramids (paramedian longitudinal ridges).
                     dict(prim="roundcone", a=[0.16, 0.55, 0.36], r1=0.13,
                          b=[0.14, -0.60, 0.24], r2=0.10),
                     dict(prim="roundcone", a=[-0.16, 0.55, 0.36], r1=0.13,
                          b=[-0.14, -0.60, 0.24], r2=0.10),
                     # olives (ventrolateral, upper medulla).
                     dict(prim="ellipsoid", center=[0.40, 0.22, 0.14],
                          radii=[0.16, 0.26, 0.18]),
                     dict(prim="ellipsoid", center=[-0.40, 0.22, 0.14],
                          radii=[0.16, 0.26, 0.18]),
                 ]),
             ])),
         ),
]

