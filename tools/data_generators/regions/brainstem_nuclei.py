"""brainstem_nuclei region records (split from generate_data.py, verbatim).

Exposes PAIRED and MIDLINE (either may be empty) in original order.
"""
from typing import Any

PAIRED: list[dict[str, Any]] = [
    # --- Monoamine source nuclei (added for receptor expression) ---
    # The noradrenaline + dopamine source nuclei (raphe, the serotonin source, is
    # midline below). Small paired midbrain/pons nuclei tucked near the brainstem;
    # in their own `brainstem_nuclei` group so they don't take part in the
    # cortex/deep-nuclei jigsaw clipping. Positions are anatomical guesses: tune
    # in a browser.
    dict(base="locus_coeruleus", name="Locus coeruleus", group="brainstem_nuclei",
         pos=(0.3, -1.0, -0.95), color="#4a7fae",
         scale=(0.4, 1.0, 0.4),  # anatomical: thin ~2mm column; moved into the upper pons
         # SDF (self-authored atlas, see geometry_refinements/). "The blue spot":
         # the brain's main noradrenaline source, a thin ROD of cells in the dorsal
         # rostral pons (floor of the 4th ventricle). Modeled as a slim vertical
         # capsule (a roundcone with equal end radii) so it reads as the pencil-line
         # column it is, faint displace; res 56. Coloured blue as a nod to its name.
         # Carries the alpha-2 autoreceptors. Sits inside/behind the brainstem at
         # explode 0. Provenance: llm.
         shape=dict(
             type="sdf", resolution=56,
             root=dict(op="displace", amp=0.006, freq=5.0, seed=82, nodes=[
                 dict(prim="roundcone",
                      a=[0.0, -0.17, 0.0], r1=0.10,
                      b=[0.0, 0.17, 0.0], r2=0.085),  # slim near-vertical rod
             ])),
         ),
    dict(base="vta", name="Ventral tegmental area", group="brainstem_nuclei",
         fr_gender="f",
         pos=(0.3, -0.6, -0.5), color="#6cab5d",
         scale=0.4,  # anatomical: ~5mm midbrain nucleus; moved into the rescaled midbrain
         # The midbrain dopamine source medial to the substantia nigra; origin of
         # the mesolimbic / mesocortical pathways (reward, D2 autoreceptors).
         # Small smooth blob, dopamine-green to echo the dopaminergic arrows.
         radii=(0.26, 0.2, 0.3), seed=83, detail=5, noise=0.05),
]

MIDLINE: list[dict[str, Any]] = [
    dict(base="raphe", name="Raphe nuclei", group="brainstem_nuclei", fr_gender="mp",
         pos=(0.0, -1.5, -0.6), color="#b98ac9",
         scale=(0.5, 1.2, 0.5),  # anatomical: thin midline column spanning the brainstem
         # SDF (self-authored atlas, see geometry_refinements/). The brain's
         # serotonin source: a midline COLUMN of nuclei running the length of the
         # brainstem (the seam, "raphe"). Modeled as a slim vertical capsule (a
         # roundcone with near-equal end radii) hugging the midline so it reads as
         # the continuous column it is, faint displace; res 64. Emitted once, never
         # mirrored. Carries the 5-HT1A somatodendritic autoreceptors. Position/size
         # are a guess: tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=64,
             root=dict(op="displace", amp=0.008, freq=4.5, seed=81, nodes=[
                 dict(prim="roundcone",
                      a=[0.0, -0.48, 0.0], r1=0.13,
                      b=[0.0, 0.48, 0.0], r2=0.11),  # tall slim midline column
             ])),
         ),
]

