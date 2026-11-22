"""Functional areas (BETA): named sets of brain structures a reader searches by function.

Node kind ``functional_areas`` (one node per area, ``functional_areas.jsonl``). The first
family is the human Brodmann areas, listed as on Wikipedia's "Brodmann area" article
(section "For humans and other primates"; areas 13, 14, 15 and 49, found only in other
primates or rodents, are left out). Each area names the modeled structures (base ids) it
lies in and, where a book states it, one quote tying the area number to its place or
role (Nolte #26, Nieuwenhuys #6, Kandel #2). An area no book names ships unsourced.

The modeled brain is coarser than the areas (each lobe is one structure), so until an
area has its own drawn sub-structure (``own_shape``) the viewer lights the lobe(s) it
lies in and greys the area's row. Cutting those sub-structures is gradual (see CLAUDE.md
"Structure granularity").

Built with the help of Claude Code.
"""
from __future__ import annotations

from typing import Any

from .provenance import _kandel, _nieuwenhuys, _nolte

WIKI = "https://en.wikipedia.org/wiki/"

# Shared sentences (one quote object per sentence, cited by several areas).
_N_PERIARCHI = _nieuwenhuys(367,
    "it can be said that the periarchicortex comprises the infralimbic cortex (area 25), "
    "the anterior cingulate cortex (area 24), the retrosplenial areas 29 and 30 and the "
    "entorhinal cortex (area 28; Fig. 12.3).")
_N_CINGULATE = _nieuwenhuys(515,
    "They are the source of thalamic fibres to the cingulate gyrus (areas 23, 24, 32), "
    "including the retrosplenial areas 29 and 30")
_N_PERIRHINAL = _nieuwenhuys(390,
    "The medial temporal lobe is a morphologically heterogeneous structure, which "
    "encompasses the well-differentiated temporal portion of the hippocampal formation, "
    "the entorhinal cortex, the areas TH and TF and the perirhinal areas 35 and 36 "
    "(Fig. 12.3).")
_N_DLPFC = _nieuwenhuys(450,
    "The dorsolateral prefrontal loop originates principally in Brodmann’s areas 9 and 46.")
_N_ORBITO = _nieuwenhuys(623,
    "the caudal orbitofrontal cortex (areas 12, 13, 14 and caudal part of area 11)")
_N_PARIETAL = _nieuwenhuys(516,
    "This area includes the caudal part of the superior parietal lobule (area 7), most of "
    "the inferior parietal lobule (areas 39 and 40)")
_N_ANGULAR = _nieuwenhuys(613,
    "the extension of areas 39 and 40 of Brodmann correspond roughly to those of the "
    "angular and supramarginal gyri, respectively.")
_N_INFEROTEMPORAL = _nieuwenhuys(413,
    "The visual association cortex, which occupies most of the inferior part of the "
    "temporal lobe (areas 20 and 21)")
_N_BROCA = _nieuwenhuys(603,
    "It is generally accepted that areas 44 and 45 of Brodmann in the inferior part of the "
    "frontal lobe constitute the cytoarchitectonic correlates of Broca’s speech region.")
_NO_VISUAL_ASSOC = _nolte(550,
    "areas 18 and 19, which surround the primary visual cortex, are part of the visual "
    "association cortex.")


def _a(num: str, title: str, en: str, fr: str, structures: list[str],
       sources: list[dict] | None = None) -> dict[str, Any]:
    return {"id": "ba" + num.replace(", ", "_").replace(" and ", "_"), "number": num,
            "name": {"en": en, "fr": fr}, "structures": structures,
            "wikipedia": WIKI + title.replace(" ", "_"), "sources": sources or []}


# Area -> where it lies among the modeled structures, in Wikipedia's order.
AREAS: list[dict[str, Any]] = [
    _a("3, 1 and 2", "Brodmann areas 3, 1 and 2", "Primary somatosensory cortex",
       "Cortex somatosensoriel primaire", ["parietal"],
       [_nolte(661, "postcentral gyrus is the site of the primary somatosensory cortex "
                    "(Brodmann areas 3, 1, and 2).")]),
    _a("4", "Brodmann area 4", "Primary motor cortex", "Cortex moteur primaire", ["frontal"],
       [_nolte(554, "Primary motor cortex corresponds to Brodmann’s area 4, occupying a "
                    "tapering strip in the precentral gyrus, mostly in the anterior wall of "
                    "the central sulcus.")]),
    _a("5", "Brodmann area 5", "Superior parietal lobule (somatosensory association)",
       "Lobule pariétal supérieur (association somatosensorielle)", ["parietal"],
       [_nieuwenhuys(610, "except for its most anterior part (area 5), which forms the "
                          "(unimodal) somatosensory association cortex.")]),
    _a("6", "Brodmann area 6", "Premotor cortex and supplementary motor area",
       "Cortex prémoteur et aire motrice supplémentaire", ["frontal"],
       [_nolte(555, "Movements can be elicited by stimulating area 6 on the lateral surface "
                    "of the hemisphere (premotor cortex)")]),
    _a("7", "Brodmann area 7", "Superior parietal lobule (visuo-motor coordination)",
       "Lobule pariétal supérieur (coordination visuomotrice)", ["parietal"], [_N_PARIETAL]),
    _a("8", "Brodmann area 8", "Frontal eye fields", "Champs oculomoteurs frontaux",
       ["frontal"],
       [_nieuwenhuys(270, "is reciprocally connected with the frontal eye field (area 8) "
                          "and entire prefrontal cortex")]),
    _a("9", "Brodmann area 9", "Dorsolateral prefrontal cortex",
       "Cortex préfrontal dorsolatéral", ["frontal"], [_N_DLPFC]),
    _a("10", "Brodmann area 10", "Anterior prefrontal cortex (frontal pole)",
       "Cortex préfrontal antérieur (pôle frontal)", ["frontal"],
       [_nieuwenhuys(617, "the frontal pole (area 10)")]),
    _a("11", "Brodmann area 11", "Orbitofrontal cortex", "Cortex orbitofrontal",
       ["frontal"], [_N_ORBITO]),
    _a("12", "Brodmann area 12", "Orbitofrontal cortex (between the superior frontal gyrus "
       "and the inferior rostral sulcus)", "Cortex orbitofrontal (entre gyrus frontal "
       "supérieur et sillon rostral inférieur)", ["frontal"], [_N_ORBITO]),
    _a("16", "Brodmann area 16", "Insular cortex", "Cortex insulaire", ["insula"]),
    _a("17", "Brodmann area 17", "Primary visual cortex (V1)", "Cortex visuel primaire (V1)",
       ["occipital"],
       [_nolte(650, "Its upper and lower banks contain the primary visual cortex "
                    "(Brodmann area 17).")]),
    _a("18", "Brodmann area 18", "Secondary visual cortex (V2)",
       "Cortex visuel secondaire (V2)", ["occipital"], [_NO_VISUAL_ASSOC]),
    _a("19", "Brodmann area 19", "Associative visual cortex (V3, V4, V5)",
       "Cortex visuel associatif (V3, V4, V5)", ["occipital"], [_NO_VISUAL_ASSOC]),
    _a("20", "Brodmann area 20", "Inferior temporal gyrus", "Gyrus temporal inférieur",
       ["temporal"], [_N_INFEROTEMPORAL]),
    _a("21", "Brodmann area 21", "Middle temporal gyrus", "Gyrus temporal moyen",
       ["temporal"], [_N_INFEROTEMPORAL]),
    _a("22", "Brodmann area 22", "Superior temporal gyrus (Wernicke's area)",
       "Gyrus temporal supérieur (aire de Wernicke)", ["temporal"],
       [_nolte(667, "posterior part of the superior temporal gyrus (Brodmann area 22)")]),
    _a("23", "Brodmann area 23", "Ventral posterior cingulate cortex",
       "Cortex cingulaire postérieur ventral", ["cingulate"], [_N_CINGULATE]),
    _a("24", "Brodmann area 24", "Ventral anterior cingulate cortex",
       "Cortex cingulaire antérieur ventral", ["cingulate"], [_N_PERIARCHI]),
    _a("25", "Brodmann area 25", "Subgenual area", "Aire subgénuale", ["cingulate"],
       [_N_PERIARCHI]),
    _a("26", "Brodmann area 26", "Ectosplenial area", "Aire ectospléniale", ["cingulate"]),
    _a("27", "Brodmann area 27", "Presubiculum", "Présubiculum", ["hippocampus"]),
    _a("28", "Brodmann area 28", "Ventral entorhinal cortex", "Cortex entorhinal ventral",
       ["temporal"], [_N_PERIARCHI]),
    _a("29", "Brodmann area 29", "Retrosplenial cortex", "Cortex rétrosplénial",
       ["cingulate"], [_N_PERIARCHI]),
    _a("30", "Brodmann area 30", "Retrosplenial cortex (subdivision)",
       "Cortex rétrosplénial (subdivision)", ["cingulate"], [_N_PERIARCHI]),
    _a("31", "Brodmann area 31", "Dorsal posterior cingulate cortex",
       "Cortex cingulaire postérieur dorsal", ["cingulate"]),
    _a("32", "Brodmann area 32", "Dorsal anterior cingulate cortex",
       "Cortex cingulaire antérieur dorsal", ["cingulate"], [_N_CINGULATE]),
    _a("33", "Brodmann area 33", "Anterior cingulate cortex (pregenual)",
       "Cortex cingulaire antérieur (prégénual)", ["cingulate"]),
    _a("34", "Brodmann area 34", "Dorsal entorhinal cortex", "Cortex entorhinal dorsal",
       ["temporal"]),
    _a("35", "Brodmann area 35", "Perirhinal cortex", "Cortex périrhinal", ["temporal"],
       [_N_PERIRHINAL]),
    _a("36", "Brodmann area 36", "Perirhinal cortex (ectorhinal)",
       "Cortex périrhinal (ectorhinal)", ["temporal"], [_N_PERIRHINAL]),
    _a("37", "Brodmann area 37", "Fusiform gyrus", "Gyrus fusiforme", ["temporal"],
       [_nieuwenhuys(608, "the entire inferotemporal cortex, composed of areas 37, 20 and "
                          "21, are included in the ventral stream.")]),
    _a("38", "Brodmann area 38", "Temporal pole", "Pôle temporal", ["temporal"],
       [_nieuwenhuys(620, "which corresponds to area 38 of Brodmann, is commonly "
                          "designated as a paralimbic structure.")]),
    _a("39", "Brodmann area 39", "Angular gyrus", "Gyrus angulaire", ["parietal"],
       [_N_ANGULAR]),
    _a("40", "Brodmann area 40", "Supramarginal gyrus", "Gyrus supramarginal", ["parietal"],
       [_N_ANGULAR]),
    _a("41 and 42", "Brodmann areas 41 and 42", "Auditory cortex", "Cortex auditif",
       ["temporal"],
       [_nolte(554, "One or two transverse temporal gyri (of Heschl; see Fig. 14.18) cross "
                    "the posterior part of this surface and form Brodmann’s areas 41 and "
                    "42.")]),
    _a("43", "Brodmann area 43", "Gustatory cortex (parietal operculum)",
       "Cortex gustatif (opercule pariétal)", ["parietal"],
       [_kandel(499, "is located on the upper bank of the lateral sulcus (Sylvian fissure) "
                     "and on the parietal operculum; it covers Brodmann’s area 43.")]),
    _a("44", "Brodmann area 44", "Broca's area (pars opercularis)",
       "Aire de Broca (pars opercularis)", ["frontal"], [_N_BROCA]),
    _a("45", "Brodmann area 45", "Broca's area (pars triangularis)",
       "Aire de Broca (pars triangularis)", ["frontal"], [_N_BROCA]),
    _a("46", "Brodmann area 46", "Dorsolateral prefrontal cortex (area 46)",
       "Cortex préfrontal dorsolatéral (aire 46)", ["frontal"], [_N_DLPFC]),
    _a("47", "Brodmann area 47", "Orbital part of the inferior frontal gyrus",
       "Partie orbitaire du gyrus frontal inférieur", ["frontal"],
       [_nieuwenhuys(633, "also includes the inferior prefrontal region corresponding to "
                          "area 47")]),
    _a("48", "Brodmann area 48", "Retrosubicular area", "Aire rétrosubiculaire",
       ["temporal"]),
    _a("52", "Brodmann area 52", "Parainsular area", "Aire parainsulaire",
       ["temporal", "insula"]),
]

# Areas with their own drawn shape: the lobe's SDF (in its local frame) intersected with
# half-spaces ``{normal, offset}`` keeping ``dot(p, normal) <= offset``, so the area is
# exactly a piece of its lobe. Approximate placements read off the cited sentence; the
# rest light their whole lobe, row greyed. Add one area at a time.
AREA_SHAPES: dict[str, dict[str, Any]] = {
    # "a tapering strip in the precentral gyrus, mostly in the anterior wall of the
    # central sulcus": a band along the frontal lobe's tilted posterior cut (the sulcus,
    # 0.32 y + z = -1.944), above the lateral fissure.
    "ba4": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, 0.32, 1.0], "offset": -1.394},
        {"normal": [0.0, -1.0, 0.0], "offset": 0.6}]},
    # Premotor cortex, "area 6 on the lateral surface", the band just anterior to BA4.
    "ba6": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": 1.394},
        {"normal": [0.0, 0.32, 1.0], "offset": -0.794},
        {"normal": [0.0, -1.0, 0.0], "offset": 0.6}]},
    # The rest of the frontal lobe, banded by s = 0.32 y + z (distance in front of the
    # central sulcus, s = -1.944) and height y: dorsal (frontal eye field, then
    # dorsolateral prefrontal), ventrolateral (Broca's 44 / 45, then 47), the frontal pole
    # (10) and the orbital floor (11).
    # frontal eye field (area 8)
    "ba8": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": 0.794},
        {"normal": [0.0, 0.32, 1.0], "offset": -0.2},
        {"normal": [0.0, -1.0, 0.0], "offset": -0.2}]},
    # dorsolateral prefrontal (area 9)
    "ba9": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": 0.2},
        {"normal": [0.0, 0.32, 1.0], "offset": 0.6},
        {"normal": [0.0, -1.0, 0.0], "offset": -0.4}]},
    # dorsolateral prefrontal (area 46), below area 9
    "ba46": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": 0.2},
        {"normal": [0.0, 0.32, 1.0], "offset": 0.6},
        {"normal": [0.0, -1.0, 0.0], "offset": 0.6},
        {"normal": [0.0, 1.0, 0.0], "offset": 0.4}]},
    # frontal pole (area 10)
    "ba10": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": -0.6},
        {"normal": [0.0, -1.0, 0.0], "offset": 0.9}]},
    # orbitofrontal (area 11), the frontal floor
    "ba11": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": 0.6},
        {"normal": [0.0, 1.0, 0.0], "offset": -0.9}]},
    # Broca's area, pars opercularis (44)
    "ba44": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": 1.0},
        {"normal": [0.0, 0.32, 1.0], "offset": -0.45},
        {"normal": [0.0, -1.0, 0.0], "offset": 1.3},
        {"normal": [0.0, 1.0, 0.0], "offset": -0.6}]},
    # Broca's area, pars triangularis (45)
    "ba45": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": 0.45},
        {"normal": [0.0, 0.32, 1.0], "offset": 0.05},
        {"normal": [0.0, -1.0, 0.0], "offset": 1.3},
        {"normal": [0.0, 1.0, 0.0], "offset": -0.6}]},
    # orbital part of the inferior frontal gyrus (47)
    "ba47": {"lobe": "frontal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": -0.05},
        {"normal": [0.0, 0.32, 1.0], "offset": 0.6},
        {"normal": [0.0, -1.0, 0.0], "offset": 1.3},
        {"normal": [0.0, 1.0, 0.0], "offset": -0.6}]},
    # "the postcentral gyrus is the site of the primary somatosensory cortex": the
    # parietal strip just behind the same central-sulcus plane (0.32 y + z = 0.2 here).
    "ba3_1_2": {"lobe": "parietal", "cuts": [
        {"normal": [0.0, -0.32, -1.0], "offset": 0.35},
        {"normal": [0.0, -1.0, 0.0], "offset": 1.4}]},
    # "Its upper and lower banks [the calcarine sulcus] contain the primary visual
    # cortex": the medial face of the occipital lobe, its posterior part and the pole.
    "ba17": {"lobe": "occipital", "cuts": [
        {"normal": [1.0, 0.0, 0.0], "offset": 0.1},
        {"normal": [0.0, 0.0, 1.0], "offset": 0.1}]},
    # "areas 18 and 19, which surround the primary visual cortex": 18 the lateral
    # posterior occipital lobe beside BA17, 19 its anterior part.
    "ba18": {"lobe": "occipital", "cuts": [
        {"normal": [-1.0, 0.0, 0.0], "offset": -0.1},
        {"normal": [0.0, 0.0, 1.0], "offset": 0.45}]},
    "ba19": {"lobe": "occipital", "cuts": [
        {"normal": [0.0, 0.0, -1.0], "offset": -0.45}]},
}


def _box(lobe: str, **lim: float) -> dict[str, Any]:
    """An area as an axis box in its host's local frame: ``x_min=0.2`` keeps x >= 0.2,
    ``s_max`` bounds s = 0.32 y + z (distance in front of the parietal central-sulcus
    plane). A host with no limit given is the whole host (insula, BA16)."""
    axes = {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0],
            "s": [0.0, 0.32, 1.0]}
    cuts = []
    for key, v in lim.items():
        ax, side = key.split("_")
        n = axes[ax]
        cuts.append({"normal": n, "offset": v} if side == "max"
                    else {"normal": [-c for c in n], "offset": -v})
    return {"lobe": lobe, "cuts": cuts}


# The remaining areas, placed from the location their cited sentence (or Wikipedia's
# list) gives, in each host's local frame: parietal (s from the central sulcus, y up),
# temporal (x lateral, y up with its top at y ~ 0.58 - 0.18 z, z anterior: pole near z 2.6), the cingulate arc (z anterior,
# y up), the insula whole, the hippocampus' posterior end for the presubiculum.
AREA_SHAPES.update({
    "ba5": _box("parietal", s_min=-0.85, s_max=-0.35, y_min=-0.4),
    "ba7": _box("parietal", s_max=-0.85, y_min=-0.4),
    "ba40": _box("parietal", s_min=-0.9, s_max=-0.35, y_min=-2.0, y_max=-0.4),
    "ba39": _box("parietal", s_max=-0.9, y_min=-2.0, y_max=-0.4),
    "ba43": _box("parietal", s_min=-0.6, y_max=-1.4),
    "ba38": _box("temporal", z_min=1.4),
    "ba22": _box("temporal", y_min=0.1, z_min=-1.5, z_max=1.4),
    "ba41_42": _box("temporal", y_min=0.25, x_max=0.2, z_min=-0.9, z_max=0.1),
    "ba21": _box("temporal", x_min=0.0, y_min=-0.2, y_max=0.1, z_min=-1.8, z_max=1.4),
    "ba20": _box("temporal", x_min=-0.6, y_max=-0.2, z_min=-1.5, z_max=1.4),
    "ba37": _box("temporal", y_max=0.5, z_max=-1.5),
    "ba28": _box("temporal", x_max=-0.6, y_max=0.0, z_min=0.6, z_max=1.9),
    "ba34": _box("temporal", x_max=-0.6, y_min=0.0, y_max=0.6, z_min=0.6, z_max=1.9),
    "ba35": _box("temporal", x_max=-0.6, y_max=0.3, z_min=-0.4, z_max=0.6),
    "ba36": _box("temporal", x_min=-0.6, x_max=-0.2, y_max=0.3, z_min=-0.4, z_max=0.6),
    "ba48": _box("temporal", x_max=-0.6, y_max=0.3, z_min=-1.5, z_max=-0.4),
    "ba24": _box("cingulate", z_min=0.3, y_min=0.0, y_max=0.95),
    "ba32": _box("cingulate", z_min=0.3, y_min=0.95),
    "ba25": _box("cingulate", z_min=0.9, y_max=-0.1),
    "ba33": _box("cingulate", z_min=1.2, y_min=-0.1, y_max=0.6),
    "ba23": _box("cingulate", z_min=-1.0, z_max=-0.2, y_max=0.9),
    "ba31": _box("cingulate", z_min=-1.0, z_max=-0.2, y_min=0.9),
    "ba29": _box("cingulate", z_max=-1.0, y_max=0.0),
    "ba30": _box("cingulate", z_max=-1.0, y_min=0.0),
    "ba26": _box("cingulate", z_max=-1.2, y_max=-0.2),
    "ba16": _box("insula"),
    "ba27": _box("hippocampus", z_max=-0.2),
})
OWN_SHAPE: set[str] = set(AREA_SHAPES)


def area_shape(area_id: str, lobe_shape: dict[str, Any]) -> dict[str, Any]:
    """The SDF shape file of an area: its lobe's shape cut by the area's half-spaces."""
    cut = AREA_SHAPES[area_id]["cuts"]
    out = {k: lobe_shape[k] for k in ("resolution", "bounds", "margin") if k in lobe_shape}
    return {"type": "sdf", **out,
            "root": {"op": "intersect", "nodes": [lobe_shape["root"], *(
                {"prim": "plane", "normal": c["normal"], "offset": c["offset"]} for c in cut)]}}
