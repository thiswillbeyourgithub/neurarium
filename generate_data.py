#!/usr/bin/env python
"""Generate the Neurarium brain visualizer data artifacts.

This script is the *single source of truth* for the anatomy shown by the
viewer. Editing the structures/projections lists here and re-running keeps the
two consumed artifacts in sync without duplicating anatomical data:

- ``data/brain.jsonl`` : one JSON object per line. Each line is either a
  ``structure`` (a brain region: id, group, anatomical position, color, ...) or
  a ``projection`` (a directed neuron pathway between two structures). The
  viewer reads this to know *what* to draw and *how things relate*.
- ``shapes/<name>.json``: one file per distinct *form* (ellipsoid radii +
  organic deformation parameters). The actual mesh deformation happens in JS
  (see ``js/shapes.js``); these files just carry the parameters so the form of a
  region can be tweaked independently of its position/relationships. Symmetric
  left/right pairs share a single right-side file (the left member reflects it
  via a ``mirror`` flag), so there is no per-side duplication; midline
  structures each have their own file.

Why a generator instead of hand-written files: the project is expected to grow
complex, and most regions come in symmetric left/right pairs. Defining a region
once here and mirroring it avoids the duplication that hand-authoring ~20 files
would create. The generated files are committed so the static site can fetch
them directly; regenerate them whenever this script changes.

Stdlib-only on purpose (argparse/json/pathlib): this is build tooling that must
run offline with a bare ``python`` interpreter, so it avoids the usual
click/loguru dependencies.

Usage
-----
    python generate_data.py            # writes into ./data and ./shapes
    python generate_data.py --root /some/dir
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("generate_data")


# ---------------------------------------------------------------------------
# Anatomy definition (the single source of truth)
#
# Coordinate convention (arbitrary units, brain centered on the origin):
#   x : left (-) .. right (+)
#   y : inferior/down (-) .. superior/up (+)
#   z : posterior/back (-) .. anterior/front-of-face (+)
#
# Each "half" entry below is given with a RIGHT-hemisphere position (x > 0) and
# is mirrored to the left automatically: the left member reuses the same shape
# file reflected across x (a true geometric mirror, not a copy), so asymmetric
# forms like the C-shaped caudate flip sides correctly. Midline structures are
# listed separately and emitted once (never mirrored).
# ---------------------------------------------------------------------------

# Per-structure shape params (default "blob" = noise-deformed ellipsoid):
#   radii  : (rx, ry, rz) ellipsoid half-extents before deformation
#   seed   : integer making the organic deformation deterministic & unique
#   detail : icosphere subdivision level (higher = smoother/more vertices)
#   noise  : deformation amplitude as a fraction of radius (0 = clean ellipsoid)
#
# An entry may instead carry an explicit ``shape=dict(type=...)`` payload for a
# non-ellipsoid form. Currently the only other type is "curve": a tapered tube
# swept along a Catmull-Rom spline (see js/shapes.js buildCurveGeometry), used
# for the strongly C-shaped caudate. Its params:
#   points  : spine control points [(x,y,z), ...] head -> tail (local coords)
#   profile : tube radius sampled head -> tail (interpolated along the spine)
#   seed/noise/radial_segments/tubular_segments : surface wobble + tessellation

# name, group, right-side position, color, radii, seed, detail, noise
PAIRED: list[dict[str, Any]] = [
    # --- Cortical lobes (large, outer shell) ---
    dict(base="frontal", name="Frontal lobe", group="lobe",
         # Cortical lobes share a muted pink palette (low saturation so they read
         # as one cortex, not "pop" colors), each a slightly different hue so the
         # four stay tellable apart: frontal=rose, parietal=pink, temporal=salmon,
         # occipital=mauve-pink.
         pos=(1.3, 1.0, 2.2), color="#c58c9a",
         # Largest lobe; gyrified cortex rendered with ridged multi-octave noise
         # so the surface reads as winding gyri/sulci rather than random lumps.
         # Anterior-superior quadrant of the hemisphere; `medial` gives it a flat
         # wall at the midline so left+right meet at the longitudinal fissure.
         # Lobes are sized to overlap their neighbors so the union reads as one
         # continuous cortical surface (no gaps) when assembled at explode 0.
         radii=(1.6, 1.8, 2.1), seed=11, detail=6, noise=0.20,
         octaves=2, ridged=True, frequency=3.6, medial=True),
    dict(base="parietal", name="Parietal lobe", group="lobe",
         pos=(1.25, 1.8, -0.2), color="#c69597",
         # Superior-posterior quadrant, behind the frontal and above the
         # occipital; gyrified, with a flat medial wall at the fissure.
         radii=(1.6, 1.7, 1.8), seed=12, detail=6, noise=0.20,
         octaves=2, ridged=True, frequency=3.6, medial=True),
    dict(base="temporal", name="Temporal lobe", group="lobe",
         pos=(1.95, -0.75, 0.6), color="#c79a8e",
         # Inferior-lateral, elongated antero-posteriorly (a finger-shaped lobe);
         # gyrified, gyri stretch along its long axis. It sits below the Sylvian
         # fissure so it is NOT medial (stays lateral, not at the midline); its
         # top is clipped flat (ymax) to seat under the fronto-parietal mass.
         radii=(1.25, 1.1, 2.15), seed=13, detail=6, noise=0.18,
         octaves=2, ridged=True, frequency=3.6,
         clip=dict(ymax=0.95)),
    dict(base="occipital", name="Occipital lobe", group="lobe",
         pos=(1.1, 0.75, -2.9), color="#bf8da6",
         # Smallest lobe, the posterior pole; compact and gyrified, behind the
         # parietal and above the cerebellum, with a flat medial wall.
         radii=(1.45, 1.5, 1.6), seed=14, detail=6, noise=0.20,
         octaves=2, ridged=True, frequency=3.6, medial=True),
    dict(base="insula", name="Insula", group="lobe",
         pos=(2.5, 0.05, 0.55), color="#ae7aa3",
         # The hidden 5th lobe: cortex buried deep to the lateral (Sylvian)
         # sulcus, overlying the putamen, walled off by the fronto-parietal +
         # temporal opercula. Small lateral patch (flattened mediolaterally), NOT
         # medial. Gyrified like the other lobes (so it gets the gyrus bump). It
         # is mostly tucked inside at explode 0 and revealed by blowing out.
         # NOTE: as a `lobe` blob it takes part in the same-group jigsaw clip
         # against the big lobes; its small size means the seams cut a fair bit
         # off it. Position/size are an anatomical guess: tune in a browser.
         radii=(0.5, 1.0, 1.25), seed=15, detail=6, noise=0.16,
         octaves=2, ridged=True, frequency=3.6),
    # --- Basal ganglia & deep nuclei (small, inner) ---
    dict(base="caudate", name="Caudate nucleus", group="basal_ganglia",
         pos=(1.2, 1.2, 0.8), color="#ff9da7",
         # Genuinely C-shaped: a bulbous head (anterior-superior) arching over
         # and back, then a thin tail curling down and forward. Modeled as a
         # tapered tube along a parasagittal (x~0) spline so it reads as the
         # comma it is rather than a convex blob. Spine runs head -> tail; z is
         # anterior(+), y is superior(+).
         shape=dict(
             type="curve",
             points=[
                 (0.0, 0.55, 1.05),   # head: anterior + superior, bulbous
                 (0.0, 0.90, 0.45),   # rising
                 (0.0, 0.92, -0.35),  # top of the arch, heading posterior
                 (0.0, 0.55, -1.00),  # descending at the back
                 (0.0, -0.20, -1.00), # down the posterior wall
                 (0.0, -0.80, -0.50), # bottom, curling forward
                 (0.0, -0.98, 0.25),  # tail moving anteriorly
                 (0.0, -0.85, 0.90),  # tail tip (toward the temporal lobe)
             ],
             profile=[0.48, 0.40, 0.33, 0.29, 0.25, 0.20, 0.13, 0.06],
             seed=21, noise=0.1, radial_segments=14, tubular_segments=110,
         )),
    dict(base="putamen", name="Putamen", group="basal_ganglia",
         pos=(2.0, 0.2, 0.6), color="#f28e2b",
         # Rounded shell, the most lateral nucleus: flattened mediolaterally
         # (thin x), taller/deeper. Smooth surface (higher detail, low noise so
         # it reads as a clean lens, not a faceted potato).
         radii=(0.45, 1.05, 1.2), seed=22, detail=5, noise=0.06),
    dict(base="globus_pallidus", name="Globus pallidus", group="basal_ganglia",
         pos=(1.5, 0.0, 0.2), color="#76b7b2",
         # Smaller wedge sitting medial to the putamen; smooth. Together with the
         # putamen it forms the lens-shaped lentiform nucleus.
         radii=(0.4, 0.72, 0.82), seed=23, detail=5, noise=0.06),
    dict(base="thalamus", name="Thalamus", group="basal_ganglia",
         pos=(0.9, 0.4, -0.6), color="#bab0ac",
         # Large ovoid "egg", the biggest deep nucleus; smooth, slightly
         # elongated antero-posteriorly.
         radii=(0.82, 0.78, 1.1), seed=24, detail=5, noise=0.05),
    dict(base="subthalamic_nucleus", name="Subthalamic nucleus",
         group="basal_ganglia",
         pos=(1.3, -0.9, -0.6), color="#d37295",
         # Tiny biconvex lens; flattened in y, smooth.
         radii=(0.34, 0.26, 0.52), seed=25, detail=5, noise=0.05),
    dict(base="substantia_nigra", name="Substantia nigra",
         group="basal_ganglia",
         pos=(1.0, -1.4, -1.2), color="#3d3d3d",
         # A thin lamina/band in the midbrain: flat in y, elongated in z.
         radii=(0.5, 0.18, 0.68), seed=26, detail=5, noise=0.05),
    dict(base="accumbens", name="Nucleus accumbens", group="basal_ganglia",
         pos=(0.95, -0.5, 1.0), color="#e0997e",
         # Ventral striatum, where the head of the caudate meets the putamen
         # ventrally and anteriorly (the reward hub, target of the mesolimbic
         # dopamine pathway). Small smooth nucleus, anterior + low + fairly
         # medial. Position is an anatomical guess: tune in a browser.
         radii=(0.4, 0.34, 0.44), seed=27, detail=5, noise=0.06),
    dict(base="claustrum", name="Claustrum", group="basal_ganglia",
         pos=(2.5, 0.1, 0.5), color="#8d97ab",
         # Thin vertical sheet of grey matter between the insula (lateral) and the
         # putamen (medial), separated from each by a white-matter capsule. Modeled
         # as an ellipsoid squashed mediolaterally (very thin x) so it reads as a
         # lamina, not a lump. NOTE: thin + same-group as the putamen, so the
         # jigsaw clip may pare it; tune position/size in a browser.
         radii=(0.07, 0.7, 0.95), seed=28, detail=5, noise=0.05),
    # --- Limbic / diencephalon ---
    dict(base="hippocampus", name="Hippocampus", group="limbic",
         pos=(1.3, -0.7, -0.2), color="#b3823e",
         # Curved allocortical structure in the floor of the temporal lobe; runs
         # antero-posteriorly with the tail curling up toward the splenium, so a
         # tapered tube (curve) reads as the seahorse it is, not a blob. Spine is
         # parasagittal (local x~0) so the _L member mirrors correctly. Sits
         # medially inside the temporal lobe at explode 0.
         shape=dict(
             type="curve",
             points=[
                 (0.0, -0.15, 1.10),   # head: anterior + inferior (pes)
                 (0.0, -0.05, 0.50),
                 (0.0, 0.05, -0.10),   # body
                 (0.0, 0.20, -0.70),
                 (0.0, 0.45, -1.15),   # tail: posterior, curling up
             ],
             profile=[0.34, 0.32, 0.28, 0.22, 0.13],
             seed=51, noise=0.08, radial_segments=12, tubular_segments=80,
         )),
    dict(base="amygdala", name="Amygdala", group="limbic",
         pos=(1.45, -0.35, 0.95), color="#9b7bb0",
         # Almond-shaped nucleus in the medial temporal lobe, just anterior and
         # superior to the head of the hippocampus (emotion/fear hub). Small
         # smooth blob. Sits inside the temporal lobe at explode 0. Position is an
         # anatomical guess: tune in a browser.
         radii=(0.42, 0.4, 0.42), seed=54, detail=5, noise=0.06),
    dict(base="cingulate", name="Cingulate gyrus", group="limbic",
         pos=(0.5, 0.6, 0.0), color="#6fa39c",
         # The limbic-lobe arch: a C-shaped band of cortex on the medial wall,
         # curving over the corpus callosum from the subgenual front, up and over,
         # to the splenial back. Modeled as a tapered tube along a parasagittal
         # (local x~0) arch so it reads as the gyrus it is; the _L member mirrors
         # it. Hugs the midline (small pos.x). Position is a guess: tune in a
         # browser, especially against the (commissural) corpus-callosum arrow.
         shape=dict(
             type="curve",
             points=[
                 (0.0, -0.5, 1.3),    # subgenual, anterior + low
                 (0.0, 0.4, 1.5),     # rising in front of the genu
                 (0.0, 1.0, 0.95),    # anterior arch
                 (0.0, 1.2, 0.0),     # top of the arch
                 (0.0, 1.0, -0.95),   # posterior arch
                 (0.0, 0.3, -1.5),    # descending toward the splenium
                 (0.0, -0.45, -1.25), # isthmus, posterior + low
             ],
             profile=[0.18, 0.3, 0.34, 0.34, 0.32, 0.28, 0.18],
             seed=55, noise=0.07, radial_segments=12, tubular_segments=96,
         )),
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
         # Small elongated bulb on the orbital underside of the frontal lobe,
         # running antero-posteriorly along the cribriform plate (the front end of
         # the olfactory tract). Stretched in z, near the midline. Position is a
         # guess: tune in a browser.
         radii=(0.18, 0.16, 0.45), seed=57, detail=5, noise=0.05),
    dict(base="septal_nuclei", name="Septal nuclei", group="limbic",
         pos=(0.3, 0.1, 0.85), color="#7f9cc0",
         # Small paramedian grey matter below the rostrum of the corpus callosum,
         # anterior to the thalamus and above the hypothalamus (a Papez/limbic
         # relay). Near the midline. Position is a guess: tune in a browser.
         radii=(0.2, 0.32, 0.22), seed=58, detail=5, noise=0.05),
    dict(base="hypothalamus", name="Hypothalamus", group="diencephalon",
         pos=(0.45, -0.45, 0.3), color="#c98ac9",
         # Small nucleus cluster below and anterior to the thalamus, hugging the
         # third ventricle (small x). Smooth (high detail, low noise).
         radii=(0.4, 0.4, 0.55), seed=52, detail=5, noise=0.05),
    dict(base="mammillary", name="Mammillary bodies", group="diencephalon",
         pos=(0.35, -0.8, -0.2), color="#c6b06a",
         # Tiny paired bumps at the posterior base of the hypothalamus (the
         # Papez node between the fornix and the anterior thalamus). Small smooth
         # blob, kept just clear of the hypothalamus so they don't fuse. Position
         # is a guess: tune in a browser.
         radii=(0.18, 0.17, 0.2), seed=71, detail=4, noise=0.04),
]

# Midline structures (emitted once, no hemisphere suffix)
MIDLINE: list[dict[str, Any]] = [
    dict(base="pituitary", name="Pituitary gland", group="diencephalon",
         pos=(0.0, -1.0, 0.35), color="#d2a06e",
         # Midline gland hanging below the hypothalamus on the infundibular stalk,
         # seated in the sella turcica. Tiny smooth blob; hides centrally at
         # explode 0 and is revealed by blowing out. Position is a guess: tune in
         # a browser.
         radii=(0.2, 0.22, 0.2), seed=72, detail=4, noise=0.04),
    dict(base="cerebellum", name="Cerebellum", group="hindbrain",
         pos=(0.0, -1.95, -3.3), color="#b07aa1",
         # Composite: two foliated hemispheres flanking a narrower central
         # vermis, the cerebellum's real "butterfly" form, instead of a single
         # wide ellipsoid. Each part stacks fine near-horizontal folia via a
         # strong y-frequency skew (aniso). Sits below/behind the occipital
         # lobes (under the tentorium) with the brainstem in front of it.
         shape=dict(
             type="composite",
             parts=[
                 # Left hemisphere.
                 dict(radii=[1.4, 1.05, 1.55], seed=31, detail=6, noise=0.13,
                      octaves=3, ridged=True, frequency=4.6,
                      aniso=[0.3, 4.4, 0.6], offset=[-1.05, 0.0, 0.0]),
                 # Right hemisphere.
                 dict(radii=[1.4, 1.05, 1.55], seed=41, detail=6, noise=0.13,
                      octaves=3, ridged=True, frequency=4.6,
                      aniso=[0.3, 4.4, 0.6], offset=[1.05, 0.0, 0.0]),
                 # Vermis: narrow, slightly taller central ridge joining them.
                 dict(radii=[0.55, 1.12, 1.5], seed=37, detail=5, noise=0.1,
                      octaves=3, ridged=True, frequency=5.4,
                      aniso=[0.25, 5.0, 0.5], offset=[0.0, 0.0, 0.05]),
             ],
         )),
    dict(base="brainstem", name="Brainstem", group="hindbrain",
         pos=(0.0, -2.4, -0.8), color="#9c755f",
         # Tall vertical stalk modeled as a curve so it tapers like the real
         # midbrain -> pons -> medulla column instead of a symmetric egg. The
         # spine runs top -> bottom; the profile bulges at the pons (anterior,
         # +z) and narrows down the medulla. Midline structure, so the curve's
         # parasagittal-spine caveat doesn't apply (it is never mirrored).
         shape=dict(
             type="curve",
             points=[
                 (0.0, 2.3, 0.05),    # midbrain (top), continuous with thalamus
                 (0.0, 1.2, 0.18),    # rising bulge toward the pons
                 (0.0, 0.15, 0.32),   # pons: fullest, bulging anteriorly
                 (0.0, -0.95, 0.1),   # upper medulla, drawing back in
                 (0.0, -2.15, -0.05), # medulla (bottom), toward the cord
             ],
             profile=[0.46, 0.58, 0.8, 0.52, 0.34],
             seed=32, noise=0.05, radial_segments=16, tubular_segments=90,
         )),
]

# Reference registry. A pathway cites one or more of these by short key (see the
# ``sources`` field on PROJECTIONS); the generator expands each key into the full
# ``{citation, url}`` object inside every projection record, so a reference shared
# by several pathways is written exactly once here (no duplication) yet the
# emitted data stays self-contained (the viewer never resolves keys).
#
# These are landmark/textbook references for the classic circuitry. The ``url``
# is left as the literal "TODO" rather than a guessed DOI: fill in a verified
# link per entry. (The viewer renders a source with a real http(s) url as a
# clickable link and a "TODO" url as plain text.)
SOURCES: dict[str, dict[str, str]] = {
    "kemp_powell1971": {
        "citation": "Kemp JM, Powell TPS (1971). The cortico-striate projection "
                    "in the monkey. Brain 94(3):525-546.",
        "url": "TODO",
    },
    "alexander1986": {
        "citation": "Alexander GE, DeLong MR, Strick PL (1986). Parallel "
                    "organization of functionally segregated circuits linking "
                    "basal ganglia and cortex. Annu Rev Neurosci 9:357-381.",
        "url": "TODO",
    },
    "albin1989": {
        "citation": "Albin RL, Young AB, Penney JB (1989). The functional anatomy "
                    "of basal ganglia disorders. Trends Neurosci 12(10):366-375.",
        "url": "TODO",
    },
    "delong1990": {
        "citation": "DeLong MR (1990). Primate models of movement disorders of "
                    "basal ganglia origin. Trends Neurosci 13(7):281-285.",
        "url": "TODO",
    },
    "parent1995": {
        "citation": "Parent A, Hazrati LN (1995). Functional anatomy of the basal "
                    "ganglia. Brain Res Rev 20(1):91-154.",
        "url": "TODO",
    },
    "smith1998": {
        "citation": "Smith Y, Bevan MD, Shink E, Bolam JP (1998). Microcircuitry "
                    "of the direct and indirect pathways of the basal ganglia. "
                    "Neuroscience 86(2):353-387.",
        "url": "TODO",
    },
    "nambu2002": {
        "citation": "Nambu A, Tokuno H, Takada M (2002). Functional significance "
                    "of the cortico-subthalamo-pallidal 'hyperdirect' pathway. "
                    "Neurosci Res 43(2):111-117.",
        "url": "TODO",
    },
    "middleton2000": {
        "citation": "Middleton FA, Strick PL (2000). Basal ganglia and cerebellar "
                    "loops: motor and cognitive circuits. Brain Res Rev "
                    "31(2-3):236-250.",
        "url": "TODO",
    },
    "aboitiz1992": {
        "citation": "Aboitiz F, Scheibel AB, Fisher RS, Zaidel E (1992). Fiber "
                    "composition of the human corpus callosum. Brain Res "
                    "598(1-2):143-153.",
        "url": "TODO",
    },
    "schmahmann2006": {
        "citation": "Schmahmann JD, Pandya DN (2006). Fiber Pathways of the "
                    "Brain. Oxford University Press.",
        "url": "TODO",
    },
    "papez1937": {
        "citation": "Papez JW (1937). A proposed mechanism of emotion. Arch "
                    "Neurol Psychiatry 38(4):725-743.",
        "url": "TODO",
    },
}

# Directed neuron projections drawn as arrows. Each entry is a connection with
# metadata so the viewer can show what the pathway is and what supports it:
#   from, to        : structure ids (e.g. "putamen_R"); the arrow points from->to
#   kind            : functional/transmitter class, selects the arrow color
#                     (key of PROJECTION_COLORS in js/arrows.js + the legend)
#   neurotransmitter: the specific transmitter molecule (Glutamate/GABA/Dopamine)
#   label           : short pathway name
#   description     : one-line plain-language summary (shown in the info panel)
#   sources         : list of SOURCES keys backing the connection (expanded to
#                     full citations in the emitted data)
#   bidirectional   : optional; True draws a cone at BOTH ends (reciprocal /
#                     commissural pathways like the corpus callosum)
#   symmetric       : optional generator hint (default True); see below
#
# Bilateral by default: each entry is auto-mirrored to the left hemisphere (``_R``
# <-> ``_L`` on both endpoints, midline endpoints kept), so a symmetric pathway is
# defined once on the right. Set ``"symmetric": False`` for a pathway that already
# spans both sides (e.g. a commissure with explicit _L and _R endpoints) so it is
# not mirrored into a duplicate. ``symmetric`` is stripped from the emitted data.
PROJECTIONS: list[dict[str, Any]] = [
    # --- Corticostriatal input (glutamate): cortex drives the striatum ---
    dict(**{"from": "frontal_R", "to": "putamen_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (motor)",
         description="Sensorimotor frontal cortex drives the putamen, the motor "
                     "input nucleus of the basal ganglia.",
         sources=["alexander1986", "kemp_powell1971"]),
    dict(**{"from": "frontal_R", "to": "caudate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (associative)",
         description="Prefrontal cortex drives the caudate (associative striatum).",
         sources=["alexander1986", "kemp_powell1971"]),
    dict(**{"from": "parietal_R", "to": "caudate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (parietal)",
         description="Posterior parietal association cortex projects to the caudate.",
         sources=["kemp_powell1971"]),
    dict(**{"from": "temporal_R", "to": "caudate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (temporal)",
         description="Temporal association cortex projects to the striatum.",
         sources=["kemp_powell1971"]),
    # --- Hyperdirect (glutamate): cortex excites the STN directly ---
    dict(**{"from": "frontal_R", "to": "subthalamic_nucleus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Hyperdirect (corticosubthalamic)",
         description="Cortex excites the subthalamic nucleus directly, the fast "
                     "'hyperdirect' brake on movement.",
         sources=["nambu2002"]),
    # --- Direct pathway (GABA): striatum inhibits the output nuclei ---
    dict(**{"from": "putamen_R", "to": "globus_pallidus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatopallidal (direct)",
         description="Direct-pathway striatal neurons inhibit the internal "
                     "pallidum, releasing (disinhibiting) the thalamus.",
         sources=["albin1989", "smith1998"]),
    dict(**{"from": "caudate_R", "to": "globus_pallidus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatopallidal (direct)",
         description="Caudate direct-pathway output to the internal pallidum.",
         sources=["albin1989", "smith1998"]),
    dict(**{"from": "putamen_R", "to": "substantia_nigra_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatonigral (direct)",
         description="Direct-pathway striatal output to the substantia nigra "
                     "pars reticulata.",
         sources=["albin1989", "parent1995"]),
    dict(**{"from": "caudate_R", "to": "substantia_nigra_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatonigral (direct)",
         description="Caudate direct-pathway output to the substantia nigra.",
         sources=["albin1989", "parent1995"]),
    # --- Indirect pathway (GABA out, glutamate back via STN) ---
    dict(**{"from": "globus_pallidus_R", "to": "subthalamic_nucleus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Pallidosubthalamic (indirect)",
         description="External pallidum inhibits the STN in the indirect pathway.",
         sources=["albin1989", "parent1995"]),
    dict(**{"from": "subthalamic_nucleus_R", "to": "globus_pallidus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Subthalamopallidal",
         description="The STN excites the pallidum, amplifying basal-ganglia "
                     "output (indirect/hyperdirect pathways).",
         sources=["albin1989", "parent1995"]),
    # --- Dopaminergic modulation (nigrostriatal) ---
    dict(**{"from": "substantia_nigra_R", "to": "putamen_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Nigrostriatal",
         description="Substantia nigra pars compacta dopamine sets the balance "
                     "between the direct and indirect striatal pathways.",
         sources=["delong1990", "parent1995"]),
    dict(**{"from": "substantia_nigra_R", "to": "caudate_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Nigrostriatal",
         description="Dopaminergic modulation of the caudate.",
         sources=["delong1990", "parent1995"]),
    # --- Basal-ganglia output to the thalamus (GABA) ---
    dict(**{"from": "globus_pallidus_R", "to": "thalamus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Pallidothalamic",
         description="The internal pallidum tonically inhibits the motor "
                     "thalamus, the output gate of the loop.",
         sources=["alexander1986", "parent1995"]),
    dict(**{"from": "substantia_nigra_R", "to": "thalamus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Nigrothalamic",
         description="Substantia nigra pars reticulata inhibitory output to the "
                     "thalamus.",
         sources=["parent1995"]),
    # --- Thalamocortical closure + sensory corticothalamic (glutamate) ---
    dict(**{"from": "thalamus_R", "to": "frontal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Thalamocortical",
         description="Motor thalamus excites frontal cortex, closing the "
                     "cortico-basal-ganglia-thalamo-cortical loop.",
         sources=["alexander1986"]),
    dict(**{"from": "occipital_R", "to": "thalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticothalamic (visual)",
         description="Occipital (visual) cortex reciprocally connects with the "
                     "thalamus (pulvinar / lateral geniculate).",
         sources=["schmahmann2006"]),
    # --- Cortico-ponto-cerebellar and cerebellar output ---
    dict(**{"from": "frontal_R", "to": "brainstem"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticopontine",
         description="Cortex projects to the pontine nuclei (brainstem), the "
                     "first leg of the cortico-ponto-cerebellar route.",
         sources=["middleton2000", "schmahmann2006"]),
    dict(**{"from": "brainstem", "to": "cerebellum"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Pontocerebellar (mossy fibers)",
         description="Pontine nuclei send mossy fibers to the cerebellar cortex.",
         sources=["middleton2000"]),
    dict(**{"from": "cerebellum", "to": "thalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Cerebellothalamic (dentatothalamic)",
         description="Deep cerebellar nuclei drive the motor thalamus, feeding "
                     "the cerebellar loop back to cortex.",
         sources=["middleton2000", "schmahmann2006"]),
    # --- Limbic (Papez) circuit ---
    dict(**{"from": "temporal_R", "to": "hippocampus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Perforant path",
         description="Entorhinal (medial temporal) cortex drives the hippocampus "
                     "via the perforant path.",
         sources=["schmahmann2006"]),
    dict(**{"from": "hippocampus_R", "to": "hypothalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Fornix",
         description="Major hippocampal output, arching via the fornix to the "
                     "mammillary bodies of the hypothalamus (Papez circuit).",
         sources=["papez1937", "schmahmann2006"]),
    dict(**{"from": "hypothalamus_R", "to": "thalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Mammillothalamic tract",
         description="Mammillary bodies to the anterior thalamus, continuing the "
                     "Papez circuit.",
         sources=["papez1937"]),
    # --- Interhemispheric commissures (bidirectional, defined once across the
    #     midline so symmetric=False keeps them from mirroring into duplicates) ---
    dict(**{"from": "frontal_L", "to": "frontal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corpus callosum (frontal)", bidirectional=True, symmetric=False,
         description="Homotopic callosal fibers linking the two frontal lobes.",
         sources=["aboitiz1992", "schmahmann2006"]),
    dict(**{"from": "parietal_L", "to": "parietal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corpus callosum (parietal)", bidirectional=True, symmetric=False,
         description="Homotopic callosal fibers linking the two parietal lobes.",
         sources=["aboitiz1992", "schmahmann2006"]),
    dict(**{"from": "occipital_L", "to": "occipital_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corpus callosum (splenium / occipital)", bidirectional=True,
         symmetric=False,
         description="Splenial callosal fibers linking the two occipital lobes.",
         sources=["aboitiz1992", "schmahmann2006"]),
    dict(**{"from": "temporal_L", "to": "temporal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Anterior commissure", bidirectional=True, symmetric=False,
         description="Older commissure linking the temporal lobes (and olfactory "
                     "structures).",
         sources=["schmahmann2006"]),
]

# Named circuits: curated bundles of structures that, together, form a classic
# functional loop. The viewer adds a "Circuits" section to the legend; clicking a
# circuit isolates exactly its structures and lights only the projections *between
# them* (every other structure + arrow fades), so a whole pathway can be inspected
# at once.
#
# A circuit lists structures by their **base** id (no ``_R``/``_L`` suffix); the
# generator expands each to whatever was actually emitted (both hemispheres for a
# paired structure, the bare id for a midline one) and writes a ``circuit`` record
# with the concrete ids. The arrows are derived in the viewer (an arrow belongs to
# the circuit when *both* its endpoints are circuit structures), so circuits never
# duplicate the projection list: edit a pathway once in PROJECTIONS and the
# circuits that span it follow. ``structures`` must name real bases (the generator
# raises on a typo).
CIRCUITS: list[dict[str, Any]] = [
    dict(id="bg_direct", name="Direct pathway (motor)",
         # Cortex -> striatum -> GPi/SNr -> thalamus -> cortex: the movement-
         # promoting basal-ganglia loop (plus the nigrostriatal dopamine input).
         structures=["frontal", "putamen", "globus_pallidus",
                     "substantia_nigra", "thalamus"]),
    dict(id="bg_indirect", name="Indirect pathway",
         # The movement-suppressing loop, routing through the subthalamic nucleus
         # (and the cortico-subthalamic "hyperdirect" shortcut).
         structures=["frontal", "putamen", "globus_pallidus",
                     "subthalamic_nucleus", "thalamus"]),
    dict(id="nigrostriatal", name="Nigrostriatal (dopamine)",
         # The dopaminergic projection whose loss causes Parkinson's, with the
         # reciprocal striatonigral return.
         structures=["substantia_nigra", "putamen", "caudate"]),
    dict(id="cerebellar_motor", name="Cortico-cerebellar (motor)",
         # Cortex -> pons -> cerebellum -> thalamus -> cortex: the coordination
         # loop running through the brainstem and cerebellum.
         structures=["frontal", "brainstem", "cerebellum", "thalamus"]),
    dict(id="limbic_memory", name="Hippocampal / limbic (Papez)",
         # The medial-temporal memory loop: cortex -> hippocampus -> fornix ->
         # hypothalamus (mammillary) -> thalamus. (Routed through the structures
         # the current projections use; the fornix/cingulate meshes are not yet
         # wired into pathways.)
         structures=["temporal", "hippocampus", "hypothalamus", "thalamus"]),
    dict(id="commissures", name="Commissures (interhemispheric)",
         # The left-right cortical bridges: corpus callosum + anterior commissure.
         # Only same-lobe cross-midline arrows fall *between* these structures.
         structures=["frontal", "parietal", "temporal", "occipital"]),
]


def _structure_record(entry: dict[str, Any], structure_id: str, name: str,
                      position: tuple[float, float, float], shape_id: str,
                      mirror: bool = False) -> dict[str, Any]:
    """Build one ``structure`` JSONL record (the non-geometric metadata).

    Parameters
    ----------
    entry
        Source definition from :data:`PAIRED` / :data:`MIDLINE`.
    structure_id
        Final id including hemisphere suffix (e.g. ``"putamen_R"``).
    name
        Display name including hemisphere prefix where relevant.
    position
        Final ``(x, y, z)`` after any mirroring.
    shape_id
        Basename of the shared geometry file (``shapes/<shape_id>.json``). The
        two members of a symmetric pair point at the *same* right-side file; the
        left member sets ``mirror`` so the viewer reflects it across x.
    mirror
        When True, emit ``"mirror": true`` so ``js/shapes.js`` reflects the
        geometry across the sagittal plane (used only for the left member of a
        symmetric pair, never for midline structures).

    Returns
    -------
    dict
        Record ready to be JSON-serialized as one line of ``brain.jsonl``.
    """
    record = {
        "type": "structure",
        "id": structure_id,
        "name": name,
        "group": entry["group"],
        "position": [round(c, 3) for c in position],
        "color": entry["color"],
        "shape_file": f"shapes/{shape_id}.json",
    }
    if mirror:
        record["mirror"] = True
    return record


# Half-width of the longitudinal fissure: each cortical lobe's medial face is
# cut flat at world x = +/- this, so the left and right hemispheres meet along a
# thin midline gap instead of overlapping into one ball. Small = tight fissure.
MIDLINE_GAP = 0.12


def _shape_record(entry: dict[str, Any], px: float) -> dict[str, Any]:
    """Build the geometric ``shapes/<id>.json`` payload for a structure.

    Most structures are ``blob``s (a noise-deformed ellipsoid) described by the
    ``radii``/``seed``/``detail``/``noise`` keys. An entry may instead provide a
    ready-made ``shape`` dict (e.g. ``type="curve"`` or ``type="composite"``), in
    which case it is used verbatim; see ``js/shapes.js`` for the consumers.

    Parameters
    ----------
    entry
        Source definition from :data:`PAIRED` / :data:`MIDLINE`.
    px
        The right-side ``x`` position the shared shape is built for (paired
        entries) or the structure's own ``x`` (midline). A ``medial`` lobe's
        flat cut plane is derived from it; the left member reuses the same file
        mirrored across x, which flips the plane to the correct side.
    """
    if "shape" in entry:
        return dict(entry["shape"])
    blob: dict[str, Any] = {
        "type": "blob",
        "radii": list(entry["radii"]),
        "seed": entry["seed"],
        "detail": entry["detail"],
        "noise": entry["noise"],
    }
    # Optional surface-character knobs (see buildBlobGeometry in js/shapes.js).
    # Only emitted when set, so plain smooth nuclei keep a minimal payload:
    #   octaves   : fBm layers (>1 = layered wrinkles, e.g. gyrified cortex)
    #   ridged    : fold the noise into sharp gyri/folia creases
    #   frequency : noise lattice frequency (higher = finer folds)
    #   aniso     : per-axis frequency skew (parallel folia)
    #   clip      : explicit flat cut planes (rarely set by hand)
    for key in ("octaves", "ridged", "frequency", "aniso", "clip"):
        if key in entry:
            blob[key] = entry[key]
    # `medial` lobes get a flat wall at the midline so the hemispheres lock
    # together along the longitudinal fissure. The shared shape is always built
    # for the right side (px >= 0), so the cut is an `xmin` plane expressed in
    # the blob's *local* space (it is centered at the structure position), hence
    # the `- px` shift. The left member reuses this same file mirrored across x
    # (see build_records), which flips the wall to the correct (xmax) side
    # automatically, so we never need to author the left clip separately.
    if entry.get("medial"):
        blob.setdefault("clip", {})["xmin"] = round(MIDLINE_GAP - px, 3)
    return blob


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


def _mirror_id(structure_id: str) -> str:
    """Flip a structure id to the other hemisphere (``_R`` <-> ``_L``).

    Midline ids (no hemisphere suffix) are returned unchanged, so a projection
    that touches a midline structure mirrors only its lateralized endpoint.
    """
    if structure_id.endswith("_R"):
        return structure_id[:-2] + "_L"
    if structure_id.endswith("_L"):
        return structure_id[:-2] + "_R"
    return structure_id


def _expand_sources(keys: list[str]) -> list[dict[str, str]]:
    """Resolve a list of :data:`SOURCES` keys to full citation objects.

    Pathways cite shared references by short key so a citation lives once in
    :data:`SOURCES`; this expands each key into the ``{citation, url}`` object the
    viewer renders, keeping ``data/brain.jsonl`` self-contained (the client never
    resolves keys). Raising on an unknown key makes a typo fail the build instead
    of silently dropping a reference.

    Parameters
    ----------
    keys
        Source keys listed on a projection's ``sources`` field.

    Returns
    -------
    list of dict
        One ``{citation, url}`` dict per key, in order.
    """
    expanded: list[dict[str, str]] = []
    for key in keys:
        if key not in SOURCES:
            raise KeyError(f"projection references unknown source '{key}'")
        expanded.append(dict(SOURCES[key]))
    return expanded


def _projection_records(proj: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one projection definition into its JSONL record(s).

    Projections are bilateral by default: each is emitted as given and, unless
    it sets ``"symmetric": False``, also as a hemisphere-flipped twin (``_R`` <->
    ``_L`` on both endpoints). The twin is skipped when flipping changes nothing
    (e.g. a purely midline pathway) so no duplicate is produced. ``symmetric`` is
    a generator hint and is stripped from the emitted records.

    The ``sources`` key (a list of :data:`SOURCES` keys) is expanded in place to
    full citation objects, and the expanded metadata (``neurotransmitter``,
    ``label``, ``description``, ``bidirectional``, ...) is carried onto the
    mirrored twin unchanged so both hemispheres show the same details.
    """
    symmetric = proj.get("symmetric", True)
    fields = {k: v for k, v in proj.items() if k != "symmetric"}
    if "sources" in fields:
        fields["sources"] = _expand_sources(fields["sources"])
    records = [{"type": "projection", **fields}]
    if symmetric:
        mirrored = {**fields,
                    "from": _mirror_id(fields["from"]),
                    "to": _mirror_id(fields["to"])}
        if (mirrored["from"], mirrored["to"]) != (fields["from"], fields["to"]):
            records.append({"type": "projection", **mirrored})
    return records


def build_records() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Expand the anatomy definition into JSONL lines and shape payloads.

    Paired entries are emitted twice (``_R`` and ``_L``) but share a *single*
    right-side shape file: the left member references the same file and is
    reflected across x at load time (``mirror``), so the two hemispheres are
    true mirror images rather than copies, and there is exactly one geometry
    file per distinct form (no duplication). Midline entries are emitted once.
    Projections are appended after the structures.

    Returns
    -------
    jsonl_records
        Ordered list of structure/projection dicts (one per JSONL line).
    shapes
        Mapping of shape-file basename -> shape payload dict.
    """
    jsonl: list[dict[str, Any]] = []
    shapes: dict[str, dict[str, Any]] = {}

    # Same-group blob neighbours for the inter-region jigsaw clipping. Only
    # default blobs take part: curve/composite forms have no clip support and the
    # C-shaped caudate / cerebellum sit apart anyway. Pairs are kept within a
    # group so the small deep nuclei still nest inside the cortex (a lobe is never
    # carved by a nucleus); within a group, overlap is detected per pair.
    blob_groups: dict[str, list[dict[str, Any]]] = {}
    for entry in PAIRED:
        if "shape" not in entry:
            blob_groups.setdefault(entry["group"], []).append(entry)

    for entry in PAIRED:
        x, y, z = entry["pos"]
        base = entry["base"]
        # One shared shape file, built for the RIGHT side. Because the left
        # member is reflected across x (mirror=True), building from the right
        # side also flips the medial clip plane to the correct side for free.
        shape = _shape_record(entry, x)
        if "shape" not in entry:
            planes = _bisecting_clip_planes(entry, blob_groups[entry["group"]])
            if planes:
                shape["clip_planes"] = planes
        shapes[base] = shape
        lname = entry["name"].lower()
        jsonl.append(
            _structure_record(entry, f"{base}_R", f"Right {lname}", (x, y, z), base))
        jsonl.append(
            _structure_record(entry, f"{base}_L", f"Left {lname}", (-x, y, z), base,
                              mirror=True))

    for entry in MIDLINE:
        sid = entry["base"]
        jsonl.append(
            _structure_record(entry, sid, entry["name"], entry["pos"], sid))
        shapes[sid] = _shape_record(entry, entry["pos"][0])

    for proj in PROJECTIONS:
        jsonl.extend(_projection_records(proj))

    # Circuits: expand each base structure id to whatever was emitted (both
    # hemispheres for a paired form, the bare id for a midline one). Built from
    # the structure records already in `jsonl`, so it can't reference a structure
    # that doesn't exist.
    structure_ids = {r["id"] for r in jsonl if r["type"] == "structure"}
    for circuit in CIRCUITS:
        ids: list[str] = []
        for base in circuit["structures"]:
            members = [sid for sid in (base, f"{base}_R", f"{base}_L")
                       if sid in structure_ids]
            if not members:
                raise KeyError(
                    f"Circuit {circuit['id']!r} references unknown structure "
                    f"{base!r} (no {base}, {base}_R or {base}_L emitted).")
            ids.extend(members)
        jsonl.append({
            "type": "circuit",
            "id": circuit["id"],
            "name": circuit["name"],
            "structures": ids,
        })

    return jsonl, shapes


def write_artifacts(root: Path) -> None:
    """Write ``data/brain.jsonl`` and ``shapes/*.json`` under ``root``.

    The ``shapes`` directory is cleared of stale ``*.json`` first so removing a
    structure here also removes its orphaned shape file.
    """
    jsonl, shapes = build_records()

    data_dir = root / "data"
    shapes_dir = root / "shapes"
    data_dir.mkdir(parents=True, exist_ok=True)
    shapes_dir.mkdir(parents=True, exist_ok=True)

    for stale in shapes_dir.glob("*.json"):
        stale.unlink()

    jsonl_path = data_dir / "brain.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for record in jsonl:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info("wrote %s (%d lines)", jsonl_path, len(jsonl))

    for sid, payload in shapes.items():
        path = shapes_dir / f"{sid}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log.info("wrote %d shape files to %s/", len(shapes), shapes_dir)


def main() -> None:
    """CLI entry point: parse ``--root`` and regenerate the artifacts."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Project root to write data/ and shapes/ into (default: script dir).",
    )
    args = parser.parse_args()
    write_artifacts(args.root)


if __name__ == "__main__":
    main()
