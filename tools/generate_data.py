#!/usr/bin/env python
"""Generate the neurarium brain visualizer data artifacts.

This script is the *single source of truth* for the anatomy shown by the
viewer. Editing the structures/projections lists here and re-running keeps the
consumed artifacts in sync without duplicating anatomical data:

- ``data/`` : the dataset, split by record type for clarity (one file per kind;
  the file a record lives in encodes its type, so there is no ``type`` field on
  the lines). ``meta.json`` is a single object carrying the presentation maps
  (arrow colours + legend headings); ``structures.jsonl`` (one brain region per
  line: id, group, anatomical position, color, ...), ``projections.jsonl`` (one
  directed neuron pathway between two structures per line) and ``circuits.jsonl``
  (one named functional loop per line) are JSONL. The viewer reads these to know
  *what* to draw and *how things relate*.
- ``data/shapes/<name>.json``: one file per distinct *form* (ellipsoid radii +
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
    python tools/generate_data.py            # writes into ../public/data/ (meta.json + *.jsonl + shapes/)
    python tools/generate_data.py --root /some/dir
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
# Presentation maps (emitted into the data so the dataset is self-describing)
#
# Display metadata, not anatomy, but the viewer reads them straight from the
# data (``meta.json``) rather than hardcoding them in JS: a projection
# ``kind`` -> arrow colour, and a structure ``group`` -> legend heading. Keeping
# them here (the single source of truth) means another engine consuming the
# dataset gets the colours + headings for free, with no copy to keep in sync
# in the viewer. build_records() validates that every kind/group used by the
# data has an entry here, so an unmapped value fails loudly at generation.
# ---------------------------------------------------------------------------

# The presentation maps (PROJECTION_COLORS / KIND_TO_SIGN / SIGN_COLORS /
# SYSTEM_FLOW_KINDS + the SIGN_LABELS / GROUP_LABELS / RECEPTOR_FAMILY_LABELS /
# RECEPTOR_CLASS_LABELS / SYNAPTIC_LABELS label maps) + the per-structure WIKIPEDIA
# link table were split out verbatim into data_generators.presentation (emitted into
# meta.json; imported at the use sites below).
from data_generators.presentation import (  # noqa: E402
    GROUP_LABELS,
    KIND_TO_SIGN,
    PROJECTION_COLORS,
    RECEPTOR_CLASS_LABELS,
    RECEPTOR_FAMILY_LABELS,
    SIGN_COLORS,
    SIGN_LABELS,
    SYNAPTIC_LABELS,
    SYSTEM_FLOW_KINDS,
    WIKIPEDIA,
)


# ---------------------------------------------------------------------------
# Drug presentation maps + binding vocabularies (DRUG_* + DRUG_TARGETS +
# TARGET_TYPE_*) live in data_generators.drugs.
# ---------------------------------------------------------------------------
from data_generators.drugs import (  # noqa: E402
    DRUG_ACTIONS,
    DRUG_ALIASES,
    DRUG_CATEGORY_LABELS,
    DRUG_EFFECT_COLORS,
    DRUG_EFFECT_LABELS,
    DRUG_TARGETS,
    ENZYMES,
    ENZYME_REACTIONS,
    ENZYME_ROLES,
    ENZYME_STRENGTHS,
    TARGET_TYPE_COLORS,
    TARGET_TYPE_LABELS,
    TONE_RULES,
)

# ---------------------------------------------------------------------------
# Source provenance: grades, override registries, SOURCE_CORPORA + the quote /
# binding / Ki source validators live in data_generators.provenance.
# ---------------------------------------------------------------------------
from data_generators.provenance import (  # noqa: E402
    DEFAULT_PROVENANCE,
    DENSITY_MIN_RELIABILITY,
    DRUG_CATEGORY_PROVENANCE,
    PROVENANCE_LEVELS,
    RECEPTOR_CLASSIFICATION_SOURCES,
    RECEPTOR_DENSITY,
    RECEPTOR_LOCATION_SOURCES,
    RECEPTOR_PROVENANCE,
    SOURCE_CORPORA,
    STRUCTURE_PROVENANCE,
    TARGET_CLASSIFICATION_SOURCES,
    TARGET_DENSITY,
    TARGET_LOCATION_SOURCES,
    TARGET_POLARITY_PROVENANCE,
    TARGET_PROVENANCE,
    WIKIPEDIA_DEFAULT_PROVENANCE,
    _kandel,
    _nieuwenhuys,
    _stahl_ess,
    WIKIPEDIA_PROVENANCE,
    _GRADE_RANK,
    _binding_sources,
    _drug_brands,
    _half_life,
    _ki_annotation,
    _density_node,
    _location_sources,
    _lookup_provenance,
    _provenance,
    _provenance_stats,
    _quote_sources,
    _receptor_provenance,
    _structure_provenance,
    _target_polarity_provenance,
    _target_provenance,
    _wiki_provenance,
)


# ---------------------------------------------------------------------------
# Internationalization (en / fr): the FR translation table, the _t()/_side_name
# wrappers and the missing-translation guard live in data_generators.i18n.
# ---------------------------------------------------------------------------
from data_generators.i18n import (  # noqa: E402
    FR,
    TRANSLATIONS,
    _FR_LEFT,
    _FR_RIGHT,
    _MISSING_TRANSLATIONS,
    _side_name,
    _t,
    externalize,
    reset_translations,
)
# Serialization-time quote externalization: the per-node source quotes are
# collapsed into a single deduplicated public/data/quotes.jsonl side table.
from data_generators.quote_table import (  # noqa: E402
    QUOTES,
    externalize_quotes,
    quote_lines,
    reset_quotes,
)

# The per-version "what's new" bullets, authored under docs/changelog/ and emitted
# to public/data/changelog.json (docs/ is not web-exposed, so the emit is what makes
# them reachable).
from data_generators.changelog import load_changelog  # noqa: E402

# The receptor classification records (pure data, one module per neurotransmitter
# family) live in the data_generators.receptors package. See the schema comment at
# the RECEPTORS use-site below.
from data_generators.receptors import RECEPTORS  # noqa: E402

# Connectivity node literals (defined in data_generators.connectivity to keep this
# module smaller; no import cycle, connectivity imports only provenance). The
# pathway quote-source constants (``_KQ_*``) it also holds are consumed by the
# PROJECTION_QUOTES registry, now in data_generators.quotes.
from data_generators.connectivity import (  # noqa: E402
    CIRCUITS,
    PROJECTIONS,
    PROJECTION_GROUPS,
)
# Verified quote registries (Kandel/Nieuwenhuys anatomy + Stahl Essential
# receptor/target classification). Split into data_generators.quotes to keep this
# module smaller; no import cycle (quotes imports only provenance + connectivity).
from data_generators.quotes import (  # noqa: E402
    PROJECTION_QUOTES,
    STRUCTURE_QUOTES,
    STAHL_ESSENTIAL_RECEPTOR_QUOTES,
    STAHL_ESSENTIAL_TARGET_QUOTES,
    RECEPTOR_ATTR_QUOTES,
    TARGET_POLARITY_QUOTES,
    RECEPTOR_CLASSIFICATION_COVERAGE,
    CLASSIFICATION_ATTRS,
    METABOLITE_ENZYME_QUOTES,
)

# Every METABOLITE_ENZYME_QUOTES key consumed while building the drugs, so a key naming
# a metabolite no drug carries (a rename, a dropped metabolite) raises instead of
# silently publishing nothing. Reset per build; checked once the drug loop is done.
_METABOLITE_ENZYME_SEEN: set[tuple[str, str]] = set()


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

# Cortical-dome geometry helpers and the brain-region anatomy records were split
# out verbatim into data_generators.geometry and data_generators.regions.
# MIDLINE_GAP is reused by the blob clip logic further below.
from data_generators.geometry import (  # noqa: E402
    MIDLINE_GAP,
    _bisecting_clip_planes,
    _scale_sdf,
    _scale_triple,
)
from data_generators.regions import MIDLINE, PAIRED  # noqa: E402

# Neurotransmitter receptors. Each entry is one receptor (the clinically relevant
# brain receptors from Wikipedia's "Example neurotransmitter receptors" table plus
# a few major psychiatric ones it omits: CB1, A2A, sigma-1, MT1/MT2). The viewer
# lists them in a legend section grouped by ``family`` (the neurotransmitter
# system); focusing a receptor dims the brain and lights glowing dots on every
# structure in ``locations`` (both hemispheres), and opens an info panel built
# from these fields. See "Changing the data" in CLAUDE.md.
#
#   id              : short slug (also the DOM-safe handle in the viewer)
#   name            : technical display name (language-neutral, e.g. "5-HT2A")
#   family          : neurotransmitter system, key of RECEPTOR_FAMILY_LABELS
#   neurotransmitter: the endogenous ligand (translatable)
#   receptor_class  : "ionotropic" | "metabotropic" | "chaperone"
#                     (key of RECEPTOR_CLASS_LABELS)
#   sign            : "excitatory" | "inhibitory" | "modulatory" (reuses the arrow
#                     SIGN_COLORS / SIGN_LABELS so the legend swatch matches)
#   synaptic        : "presynaptic" | "postsynaptic" | "both"
#                     (key of SYNAPTIC_LABELS)
#   locations       : list of structure *base* ids where it is expressed, OR the
#                     sentinel "ALL" for a brain-wide receptor (emitted as
#                     ``ubiquitous`` so the viewer lights every structure). An
#                     EMPTY list (no description) is a deliberate "stub": a
#                     receptor with no meaningful CNS/psychiatric role, listed for
#                     completeness but not focusable.
#   description     : one-line {en}; description_fr is its French (authored inline,
#                     unique per receptor, so it bypasses the shared FR table).
#                     Omitted on stubs.
#   wikipedia       : source article (rendered as a link in the info panel)
#
# Sourced from each receptor's linked Wikipedia article (the receptor info panel
# shows that link). Locations were mapped onto the modeled structures (e.g.
# striatum -> caudate+putamen, "cortex" -> the four lobes, raphe/locus coeruleus/
# VTA -> the new source nuclei); peripheral-only sites (gut, heart, retina, spinal
# cord, immune) were dropped as out of scope for a brain viewer.
# RECEPTORS (the 63 per-family classification dicts) is imported at the top
# from data_generators.receptors; the field schema is documented above.


def _structure_record(entry: dict[str, Any], structure_id: str,
                      name: dict[str, str], base_name: dict[str, str],
                      position: tuple[float, float, float], shape_id: str,
                      mirror: bool = False,
                      images: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build one ``structure`` JSONL record (the non-geometric metadata).

    Parameters
    ----------
    entry
        Source definition from :data:`PAIRED` / :data:`MIDLINE`.
    structure_id
        Final id including hemisphere suffix (e.g. ``"putamen_R"``).
    name
        Bilingual ``{"en", "fr"}`` display name including the hemisphere
        prefix/suffix where relevant (``Right putamen`` / ``Putamen droit``).
    base_name
        Bilingual ``{"en", "fr"}`` base name without any hemisphere marker, used
        for the legend row so the two hemispheres collapse to one entry without
        the viewer string-stripping a language-specific "Right "/"Left " prefix.
    position
        Final ``(x, y, z)`` after any mirroring.
    shape_id
        Basename of the shared geometry file (``data/shapes/<shape_id>.json``). The
        two members of a symmetric pair point at the *same* right-side file; the
        left member sets ``mirror`` so the viewer reflects it across x.
    mirror
        When True, emit ``"mirror": true`` so ``js/shapes.js`` reflects the
        geometry across the sagittal plane (used only for the left member of a
        symmetric pair, never for midline structures).
    images
        Map of base id -> image record (see :func:`_load_structure_images` /
        ``tools/fetch/fetch_structure_images.py``); a match adds a ``structure_image`` url
        (the hero) and, when present, a ``structure_image_gallery`` list of further
        gif/svg urls the panel reveals on "show more". A non-match omits both.

    Returns
    -------
    dict
        Record ready to be JSON-serialized as one line of ``structures.jsonl``.
    """
    record = {
        "id": structure_id,
        "name": name,
        "base_name": base_name,
        "group": entry["group"],
        "position": [round(c, 3) for c in position],
        "color": entry["color"],
        "shape_file": f"data/shapes/{shape_id}.json",
        # Source grade backing this region's anatomy (its existence / group /
        # position), keyed by base so both hemispheres share one grade. Textbook
        # anatomy, so "llm" by default; override in STRUCTURE_PROVENANCE. Shown as
        # the panel's "Source" pill and counted in the coverage tally.
        "classification_provenance": _structure_provenance(entry["base"]),
    }
    # Attach a verified Kandel quote-source for the region's anatomy (keyed by base,
    # shared by both hemispheres) and upgrade the classification grade to match, so
    # the panel's Source pill carries the verbatim quote and the tally counts it.
    anatomy_quote = STRUCTURE_QUOTES.get(entry["base"])
    if anatomy_quote is not None:
        record["sources"] = [dict(anatomy_quote)]
        if _GRADE_RANK[anatomy_quote["provenance"]] > _GRADE_RANK[
                record["classification_provenance"]]:
            record["classification_provenance"] = anatomy_quote["provenance"]
    # External reference link (same article for both hemispheres of a pair),
    # tagged with its provenance grade for the source pill (see _wiki_provenance).
    wiki = WIKIPEDIA.get(entry["base"])
    if wiki:
        record["wikipedia"] = wiki
        record["wikipedia_provenance"] = _wiki_provenance(entry["base"])
    rec = images.get(entry["base"]) if images else None
    if rec and rec.get("url"):
        # Wikimedia url (not a local path): the GIFs are too large to vendor, so
        # the viewer hot-links them at runtime (spinner / silent-fail, see
        # showStructure). Keyed by base so both hemispheres share the one URL, and
        # only set when its base was resolved (so a structure without one renders no
        # image, no broken placeholder). The gallery (other gif/svg from the EN+FR
        # articles) rides alongside for the panel's "show more".
        record["structure_image"] = rec["url"]
        gallery = [g["url"] for g in rec.get("gallery", []) if g.get("url")]
        if gallery:
            record["structure_image_gallery"] = gallery
    if mirror:
        record["mirror"] = True
    return record


def _shape_record(entry: dict[str, Any], px: float) -> dict[str, Any]:
    """Build the geometric ``data/shapes/<id>.json`` payload for a structure.

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
        shape = dict(entry["shape"])
        # Optional anatomical rescale (scalar or [sx, sy, sz]): shrink/grow a
        # structure to its correct relative size without re-authoring primitives.
        # Applied here (once, on the shared right-side shape) so the mirrored left
        # member inherits it. SDF only; the lone `curve` (fornix) is left as-is.
        if entry.get("scale") is not None and shape.get("type") == "sdf":
            s = _scale_triple(entry["scale"])
            shape["root"] = _scale_sdf(shape["root"], s)
            if "bounds" in shape:
                lo, hi = shape["bounds"]
                shape["bounds"] = [[round(lo[i] * s[i], 4) for i in range(3)],
                                   [round(hi[i] * s[i], 4) for i in range(3)]]
        return shape
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
    # Optional anatomical rescale for a blob: scale the ellipsoid half-extents
    # (and any flat clip offsets, which live in local space) per axis.
    if entry.get("scale") is not None:
        s = _scale_triple(entry["scale"])
        blob["radii"] = [round(blob["radii"][i] * s[i], 4) for i in range(3)]
        if "clip" in blob:
            axis = {"x": 0, "y": 1, "z": 2}
            blob["clip"] = {k: round(v * s[axis[k[0]]], 4)
                            for k, v in blob["clip"].items()}
    return blob


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


def _expand_sources(keys: list[Any], what: str = "projection") -> list[dict[str, Any]]:
    """Validate a projection/circuit/group ``sources`` list (quote-level dicts only).

    Every source is an inline ``{corpus, page, quote, provenance}`` dict against a
    :data:`SOURCE_CORPORA` corpus, the *same* shape a drug binding uses, validated by
    :func:`_quote_sources` (a ``verified`` grade needs a page + quote, which
    ``check_data.py`` confirms is really on that page). This is how a pathway earns a
    ``verified`` grade, e.g. a Kandel quote from :data:`PROJECTION_QUOTES`.

    Fabricated bibliographic citations are no longer carried: a pathway/circuit/group
    with no quote source is left ungraded (its provenance pill reads NOSOURCE), rather
    than cite an unverifiable paper an LLM produced from memory.
    """
    return _quote_sources(list(keys), what)


def _projection_records(proj: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one projection definition into its JSONL record(s).

    Projections are bilateral by default: rather than emit each pathway twice
    (the ``_R`` record plus a hand-mirrored ``_L`` twin, which bloated the file
    with pure duplicates), a symmetric pathway is emitted **once** carrying
    ``"mirror": true``, and the consumer (``js/data.js``, ``check_data.py``)
    reflects it to the other hemisphere by flipping ``_R`` <-> ``_L`` on both
    endpoints. The flag is set only when flipping would actually change the
    endpoints (a purely midline pathway keeps no flag, since its twin would be
    identical). ``symmetric: False`` (a commissure, an explicitly one-sided
    pathway) emits no flag. ``symmetric`` is a generator-side authoring hint and
    is not itself emitted.

    The ``sources`` key (a list of quote-level ``{corpus, page, quote, provenance}``
    dicts) is validated in place, and the metadata (``neurotransmitter``,
    ``label``, ``description``, ``bidirectional``, ...) is carried onto the
    mirrored twin unchanged so both hemispheres show the same details. The
    translatable display fields (``label``, ``description``, ``neurotransmitter``)
    are wrapped bilingually with :func:`_t` so the data file is self-describing in
    both languages.
    """
    symmetric = proj.get("symmetric", True)
    fields = {k: v for k, v in proj.items() if k != "symmetric"}
    # Merge this pathway's verified Kandel quote-source (keyed by the right-side
    # endpoints in PROJECTION_QUOTES) into its source list, so it is expanded + carried
    # onto the mirrored twin like any other source.
    src_keys = list(fields.get("sources", []))
    kandel_quote = PROJECTION_QUOTES.get((fields["from"], fields["to"]))
    if kandel_quote is not None:
        src_keys.append(kandel_quote)
    if src_keys:
        fields["sources"] = _expand_sources(
            src_keys, f"projection {fields.get('from')}->{fields.get('to')}")
    for key in ("label", "description", "neurotransmitter"):
        if key in fields:
            fields[key] = _t(fields[key])
    if symmetric:
        mfrom, mto = _mirror_id(fields["from"]), _mirror_id(fields["to"])
        if (mfrom, mto) != (fields["from"], fields["to"]):
            fields["mirror"] = True
    return [fields]


def _receptor_record(rec: dict[str, Any],
                     known_bases: set[str]) -> dict[str, Any]:
    """Build one ``receptor`` JSONL record from a :data:`RECEPTORS` entry.

    Validates the ``family`` / ``receptor_class`` / ``sign`` / ``synaptic`` keys
    against the presentation maps and every ``locations`` base against the known
    structure bases (so a typo fails the build). The translatable
    ``neurotransmitter`` is wrapped bilingually via :func:`_t`; ``description`` is
    already authored as an English/French pair inline on the entry (unique per
    receptor, so it bypasses the shared FR table) and is copied to an
    ``{"en", "fr"}`` object. A ``locations`` of the sentinel ``"ALL"`` marks a
    brain-wide receptor: it is emitted with ``ubiquitous: true`` and an empty
    location list, which the viewer expands to every structure. An empty
    ``locations`` with no ``description`` is a deliberate stub (a receptor with no
    meaningful CNS role) and is emitted as-is, focusable by nothing.
    """
    for key, table, what in (
        ("family", RECEPTOR_FAMILY_LABELS, "RECEPTOR_FAMILY_LABELS"),
        ("receptor_class", RECEPTOR_CLASS_LABELS, "RECEPTOR_CLASS_LABELS"),
        ("sign", SIGN_LABELS, "SIGN_LABELS"),
        ("synaptic", SYNAPTIC_LABELS, "SYNAPTIC_LABELS"),
    ):
        if rec[key] not in table:
            raise KeyError(
                f"Receptor {rec['id']!r} has {key}={rec[key]!r} with no {what} "
                f"entry")
    out: dict[str, Any] = {
        "id": rec["id"],
        "name": rec["name"],
        "family": rec["family"],
        "neurotransmitter": _t(rec["neurotransmitter"]),
        "receptor_class": rec["receptor_class"],
        "sign": rec["sign"],
        "synaptic": rec["synaptic"],
    }
    # A receptor's classification is FOUR independent graded sub-claims (family /
    # receptor_class / sign / synaptic), NOT one: a single Stahl quote is attached
    # only to the attributes it actually substantiates (RECEPTOR_CLASSIFICATION_
    # COVERAGE), so e.g. a sign quote never lends its grade to the GPCR or
    # pre/postsynaptic claim. Each attribute defaults to the base grade (llm unless
    # RECEPTOR_PROVENANCE lifts it) and is upgraded only when a covering quote is
    # present. The panel renders one pill per attribute row from this dict.
    base_grade = _receptor_provenance(rec["id"])
    rq = STAHL_ESSENTIAL_RECEPTOR_QUOTES.get(rec["id"])
    covered = set(RECEPTOR_CLASSIFICATION_COVERAGE.get(rec["id"], ()))
    attr_quotes = RECEPTOR_ATTR_QUOTES.get(rec["id"], {})
    classification: dict[str, dict[str, Any]] = {}
    gtopdb_attrs = RECEPTOR_CLASSIFICATION_SOURCES.get(rec["id"], {})
    for attr in CLASSIFICATION_ATTRS:
        entry: dict[str, Any] = {"grade": base_grade}
        # A per-attribute override wins; else the main quote if COVERAGE lists this attr.
        srcs = attr_quotes.get(attr)
        if srcs is None and rq is not None and attr in covered:
            srcs = [rq]
        # A machine-sourced classification fact (GtoPdb, corpus #12) *adds to* the book
        # quote rather than replacing it: an attribute both state is doubly cited.
        if gtopdb_attrs.get(attr):
            srcs = list(srcs or []) + list(gtopdb_attrs[attr])
        if srcs:
            entry["sources"] = [dict(s) for s in srcs]
            best = max((s["provenance"] for s in srcs), key=lambda p: _GRADE_RANK[p])
            if _GRADE_RANK[best] > _GRADE_RANK[entry["grade"]]:
                entry["grade"] = best
        classification[attr] = entry
    out["classification"] = classification
    locations = rec["locations"]
    if locations == "ALL":
        out["ubiquitous"] = True
        out["locations"] = []
    else:
        for base in locations:
            if base not in known_bases:
                raise KeyError(
                    f"Receptor {rec['id']!r} location {base!r} is not a known "
                    f"structure base")
        out["locations"] = list(locations)
        # Per-region expression sources (upgrade individual "Found in" regions above
        # the default llm). Omitted when nothing is sourced, so a plain receptor's
        # every region honestly grades as llm in the viewer + the coverage tally.
        loc_sources = _location_sources(
            RECEPTOR_LOCATION_SOURCES, rec["id"], out["locations"], "Receptor")
        if loc_sources:
            out["location_sources"] = loc_sources
        # Relative expression density across those regions ("concentrated where?"), its
        # own graded node (kind receptor_density). Omitted when unmeasured, so a receptor
        # without one simply reads as present/absent, as before.
        density = _density_node(
            RECEPTOR_DENSITY, rec["id"], out["locations"], "Receptor")
        if density:
            out["density"] = density
    if "description" in rec:
        out["description"] = {"en": rec["description"], "fr": rec["description_fr"]}
    if "wikipedia" in rec:
        out["wikipedia"] = rec["wikipedia"]
        out["wikipedia_provenance"] = _wiki_provenance(rec["id"])
    return out


def _check_drug_aliases(drug_ids: set[str]) -> None:
    """Fail loud if a search alias is keyed on a drug id that does not exist.

    An alias keyed on a typo is silently inert (nothing ever looks it up), which
    would read as "GHB still doesn't find it" with nothing to grep for.
    """
    unknown = sorted(set(DRUG_ALIASES) - drug_ids)
    if unknown:
        raise SystemExit(
            f"DRUG_ALIASES keys are not drug ids: {unknown}; "
            f"fix the id or drop the entry"
        )


def _check_tone_rules() -> None:
    """Fail loud if a tone rule names an action the drug vocabulary does not have.

    A rule keyed on a typo is invisible at runtime: the action simply never matches,
    the binding contributes no tone, and the drug quietly loses its flow overlay. So
    the keys are confirmed against :data:`DRUG_ACTIONS` at generation instead, where a
    mistake stops the build (the same fail-loud rule the rest of the generator uses).
    """
    for bucket, rules in TONE_RULES.items():
        for action, rule in rules.items():
            if action not in DRUG_ACTIONS:
                raise SystemExit(
                    f"TONE_RULES[{bucket!r}] names unknown action {action!r}; "
                    f"add it to DRUG_ACTIONS or fix the typo"
                )
            if len(rule) != 2 or rule[0] not in (1, -1):
                raise SystemExit(
                    f"TONE_RULES[{bucket!r}][{action!r}] must be [+1|-1, mechanism]"
                )


def _build_drug_targets(receptors: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build the emitted ``drug_targets`` map: DRUG_TARGETS + every receptor.

    A drug binding may target either one of the non-receptor :data:`DRUG_TARGETS`
    (transporters, enzymes, channels, ...) or any receptor id from
    ``receptors.jsonl`` directly. This merges both into one self-describing map the
    viewer reads: each entry is ``{name {en,fr}, system, receptor, regions,
    ubiquitous?}``. For a receptor-linked target the ``receptor`` field carries the
    receptor id and ``regions`` mirror the receptor's locations (so the viewer can
    just reuse that receptor's already-resolved lit regions); for a non-receptor
    target ``receptor`` is null and ``regions`` are the DRUG_TARGETS footprint.

    Parameters
    ----------
    receptors
        The already-built receptor records (each with ``id``/``name``/``family``/
        ``locations`` and optional ``ubiquitous``).

    Returns
    -------
    dict
        target id -> target descriptor, ready to emit into ``meta.json``.
    """
    targets: dict[str, dict[str, Any]] = {}
    for tid, spec in DRUG_TARGETS.items():
        targets[tid] = {
            "name": spec["name"],
            "type": spec["type"],
            "system": spec["system"],
            "receptor": None,
            "regions": list(spec["regions"]),
            # Source grade backing this target's classification (its type / system /
            # region footprint), shown as the panel's "Source" pill and counted in
            # the coverage tally. "llm" by default; override in TARGET_PROVENANCE.
            "classification_provenance": _target_provenance(tid),
        }
        # Optional tone-polarity hints the viewer's flow overlay reads (js/data.js
        # toneSignOf): `vesicular` marks a vesicular transporter (inhibiting it
        # depletes -> lowers tone), and `sign`/`synaptic` give a receptor_group the
        # presynaptic-autoreceptor character a specific receptor carries on its own
        # record (the α2 family). Absent for a target with no tone effect.
        # A receptor_group's modeled subtype receptor ids (α2 -> α2A/B/C/D): a
        # self-evident taxonomy, no source (see DRUG_TARGETS). The viewer lists each
        # subtype's own drugs in a dropdown under the group panel. Validate every id
        # names a real receptor so a typo can't dangle.
        subtypes = spec.get("subtypes")
        if subtypes:
            receptor_ids = {r["id"] for r in receptors}
            unknown = [s for s in subtypes if s not in receptor_ids]
            if unknown:
                raise SystemExit(
                    f"DRUG_TARGETS[{tid!r}].subtypes references unknown receptor id(s): "
                    f"{unknown}")
            targets[tid]["subtypes"] = list(subtypes)
        has_polarity = False
        for opt in ("vesicular", "sign", "synaptic"):
            if opt in spec:
                targets[tid][opt] = spec[opt]
                has_polarity = True
        # The tone-polarity flags above flip the flow-overlay direction, so the
        # claim "engaging this target raises/lowers tone" is its own graded node
        # (kind target_polarity), NOT an inheritance of the classification grade
        # from a quote that never spoke to direction. Emitted only when the target
        # actually carries a polarity flag. Default llm; a TARGET_POLARITY_QUOTES
        # quote (checked against the specific direction claim) upgrades it.
        if has_polarity:
            pol_grade = _target_polarity_provenance(tid)
            pq = TARGET_POLARITY_QUOTES.get(tid)
            if pq is not None:
                targets[tid]["polarity_sources"] = [dict(pq)]
                if _GRADE_RANK[pq["provenance"]] > _GRADE_RANK[pol_grade]:
                    pol_grade = pq["provenance"]
            targets[tid]["polarity_provenance"] = pol_grade
        # Per-region expression sources ("Found in"): each region is its own graded
        # node (kind target_locations), llm unless sourced here. Omitted when empty.
        tloc = _location_sources(
            TARGET_LOCATION_SOURCES, tid, spec["regions"], "Target")
        if tloc:
            targets[tid]["location_sources"] = tloc
        # ... and the relative-density profile over those regions (kind target_density),
        # the mirror of a receptor's. Omitted when unmeasured.
        tden = _density_node(TARGET_DENSITY, tid, spec["regions"], "Target")
        if tden:
            targets[tid]["density"] = tden
        if spec.get("wikipedia"):
            targets[tid]["wikipedia"] = spec["wikipedia"]
            targets[tid]["wikipedia_provenance"] = _wiki_provenance(tid)
        # Verified quote-sources for this target's classification: the Stahl Essential
        # sentence and/or the GtoPdb type line (corpus #12), whichever exist. They add
        # up rather than override, so a target both cover carries both citations.
        tsrcs = [dict(tq) for tq in ([STAHL_ESSENTIAL_TARGET_QUOTES[tid]]
                                     if tid in STAHL_ESSENTIAL_TARGET_QUOTES else [])]
        tsrcs += [dict(s) for s in TARGET_CLASSIFICATION_SOURCES.get(tid, [])]
        if tsrcs:
            targets[tid]["sources"] = tsrcs
            best = max((s["provenance"] for s in tsrcs), key=lambda p: _GRADE_RANK[p])
            if _GRADE_RANK[best] > _GRADE_RANK[
                    targets[tid]["classification_provenance"]]:
                targets[tid]["classification_provenance"] = best
    for rec in receptors:
        # A receptor id is also a valid target; link it so the viewer reuses the
        # receptor's lit regions. Receptor ids and DRUG_TARGETS keys never collide
        # (the latter are transporters/enzymes/channels), but guard anyway.
        if rec["id"] in targets:
            raise KeyError(f"Drug target id {rec['id']!r} collides with a receptor")
        targets[rec["id"]] = {
            "name": {"en": rec["name"], "fr": rec["name"]},
            "type": "receptor",
            "system": rec["family"],
            "receptor": rec["id"],
            "regions": list(rec.get("locations", [])),
            "ubiquitous": bool(rec.get("ubiquitous")),
        }
    return targets


def _normalize_binding(b: dict[str, Any], valid_targets: set[str], *,
                       owner_id: str, owner_label: str,
                       with_ki: bool) -> dict[str, Any]:
    """Validate + normalize one binding row (target/action/effect + sources + Ki).

    Shared by a drug's own ``bindings`` and a metabolite's inline ``bindings`` so the
    two never drift: both validate the target against the same ``valid_targets`` set
    (DRUG_TARGETS keys + receptor ids) and the action/effect against the drug
    vocabularies. An ``affinity_only`` binding is PDSP-derived: we know the owner
    binds the target (measured Ki) but not the functional direction, so it carries no
    action/effect and the viewer lists but never animates it.

    Parameters
    ----------
    b
        The authored binding dict.
    valid_targets
        Valid binding target ids.
    owner_id
        Id used for the Ki lookup (a drug id); ignored when ``with_ki`` is False.
    owner_label
        Human label for error/source messages (e.g. ``"Drug 'fluoxetine'"`` or
        ``"Drug 'fluoxetine' metabolite 'Norfluoxetine'"``).
    with_ki
        Whether to attach a PDSP ``ki`` annotation (drug bindings only; metabolite
        bindings have no measured Ki in this pass).

    Returns
    -------
    dict
        The emitted binding record.
    """
    if b["target"] not in valid_targets:
        raise KeyError(f"{owner_label} binding target {b['target']!r} "
                       f"is not a known target (DRUG_TARGETS key or receptor id)")
    if bool(b.get("affinity_only")):
        out_b: dict[str, Any] = {"target": b["target"], "affinity_only": True}
    else:
        if b["action"] not in DRUG_ACTIONS:
            raise KeyError(f"{owner_label} binding action {b['action']!r} "
                           f"has no DRUG_ACTIONS entry")
        out_b = {"target": b["target"], "action": b["action"]}
        if "effect" in b:
            if b["effect"] not in DRUG_EFFECT_COLORS:
                raise KeyError(f"{owner_label} binding effect "
                               f"{b['effect']!r} has no DRUG_EFFECT_COLORS entry")
            out_b["effect"] = b["effect"]
    if b.get("note"):
        out_b["note"] = b["note"]
    if b.get("tentative"):
        out_b["tentative"] = True
    # `provisional_action` (a direction GtoPdb gave to a binding PDSP had left
    # affinity-only) is deliberately NOT emitted: such a binding behaves like any
    # other, and its `sources` already name the corpus, so the flag would be a
    # derivable duplicate. It stays in drugs_data.jsonl for apply_gtopdb_ki.py's
    # idempotency (it recognises its own writes by it).
    # Per-claim sources ({corpus, page, quote, provenance}); the verbatim quote is
    # what check_data.py confirms is present in the cited corpus page.
    binding_sources = _quote_sources(b.get("sources"), f"{owner_label} binding "
                                     f"{b.get('target')!r}")
    if binding_sources:
        out_b["sources"] = binding_sources
    if with_ki:
        # PDSP measured binding affinity (its own verified source; see _ki_annotation).
        ki = _ki_annotation(owner_id, b)
        if ki:
            out_b["ki"] = ki
    return out_b


def _metabolite_enzymes(drug_id: str, name: str) -> list[dict[str, Any]]:
    """The enzymes that FORM this metabolite (one graded node each, kind
    ``drug_metabolite_enzyme``), shaped ``{enzyme, reaction?, sources[]}``.

    The mirror of :func:`_drug_enzymes`: there the drug is the substrate, here the
    metabolite is the product ("CYP2D6 turns venlafaxine into ODV"). Authored by hand in
    :data:`METABOLITE_ENZYME_QUOTES` rather than grepped, because the source states this
    as prose whose near misses are all wrong in the same direction (an enzyme that clears
    the metabolite, or makes a *different* one); the module docstring has the survey.

    ``enzyme`` must be an :data:`ENZYMES` key and ``reaction``, when present, an
    :data:`ENZYME_REACTIONS` key, so neither can ship a value the viewer has no label
    for. Several enzymes per metabolite is normal (one demethylation, several isoforms).
    """
    rows = METABOLITE_ENZYME_QUOTES.get((drug_id, name))
    if not rows:
        return []
    _METABOLITE_ENZYME_SEEN.add((drug_id, name))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        enzyme = row.get("enzyme")
        label = f"Drug {drug_id!r} metabolite {name!r} formed_by {enzyme!r}"
        if enzyme not in ENZYMES:
            raise ValueError(f"{label}: unknown enzyme (see ENZYMES)")
        if enzyme in seen:
            raise ValueError(f"{label}: duplicate enzyme row")
        seen.add(enzyme)
        rec: dict[str, Any] = {"enzyme": enzyme}
        reaction = row.get("reaction")
        if reaction is not None:
            if reaction not in ENZYME_REACTIONS:
                raise ValueError(f"{label}: unknown reaction {reaction!r} "
                                 "(see ENZYME_REACTIONS)")
            rec["reaction"] = reaction
        rec["sources"] = _quote_sources(
            [{k: v for k, v in row.items() if k in ("corpus", "page", "quote")}
             | {"provenance": "verified"}], what=label)
        out.append(rec)
    return out


def _drug_metabolites(drug_id: str, metabolites: Any,
                      valid_targets: set[str]) -> list[dict[str, Any]]:
    """Validate + normalize a drug's active ``metabolites`` (one graded node each).

    Each authored metabolite is ``{name, drug_id?, half_life?, half_life_sources?,
    bindings?, sources?}``:

    - ``name`` is a non-empty proper noun (not FR-translated; a chemical name).
    - ``drug_id`` links a metabolite that is ITSELF a modeled drug (desvenlafaxine,
      paliperidone, ...). The viewer then reuses that drug's bindings + T½ and links
      the row, so we deliberately do NOT duplicate them here. Its existence is
      cross-checked in check_data.py (which holds every drug id).
    - ``half_life`` is the metabolite's own elimination T½ (canonical hours), graded
      by its ``half_life_sources``.
    - ``bindings`` are inline receptor bindings for a NON-drug metabolite, sourced from
      the metabolite's own Wikipedia pharmacology by ``apply_metabolite_bindings.py``
      (corpus #9, target + action + Ki, PDSP Ki preferred). Validated + Ki-normalized
      exactly like a drug binding, so the receptor "Interacting drugs" list attributes
      them as "<name> (metab. of <drug>)". Empty for a metabolite Wikipedia does not
      cover.
    - ``sources`` grades the "<name> is an active metabolite of <drug_id>" identity
      claim (kind ``drug_metabolites``); a metabolite with no source is NOSOURCE.
    - ``formed_by`` is which enzyme(s) make it, from the hand-curated
      :data:`METABOLITE_ENZYME_QUOTES` rather than from this file (see
      :func:`_metabolite_enzymes`). Absent for the metabolites no corpus pins down.

    Parameters
    ----------
    drug_id
        Parent drug id (for error messages + the identity claim).
    metabolites
        The authored ``metabolites`` list (or None).
    valid_targets
        Valid binding target ids, for any inline metabolite bindings.

    Returns
    -------
    list of dict
        The emitted metabolite nodes (empty when none authored).
    """
    out: list[dict[str, Any]] = []
    for m in metabolites or []:
        name = m.get("name")
        if not (isinstance(name, str) and name.strip()):
            raise ValueError(f"Drug {drug_id!r} has a metabolite with no 'name'")
        name = name.strip()
        label = f"Drug {drug_id!r} metabolite {name!r}"
        rec: dict[str, Any] = {"name": name}
        if m.get("drug_id"):
            rec["drug_id"] = m["drug_id"]
        if m.get("half_life"):
            rec["half_life"] = _half_life(m["half_life"], what=label)
            hl_sources = _quote_sources(m.get("half_life_sources"),
                                        f"{label} half_life")
            if hl_sources:
                rec["half_life_sources"] = hl_sources
        # with_ki=True: a non-modeled metabolite's bindings carry their own measured/
        # literature Ki (PDSP or Wikipedia), authored by apply_metabolite_bindings.py,
        # exactly like a drug binding. owner_id is the parent drug id, used only in Ki
        # error messages (the Ki itself is already resolved onto the authored binding).
        m_bindings = [_normalize_binding(b, valid_targets, owner_id=drug_id,
                                         owner_label=label, with_ki=True)
                      for b in m.get("bindings") or []]
        if m_bindings:
            rec["bindings"] = m_bindings
        # Which enzyme MADE it (kind `drug_metabolite_enzyme`), a claim about the
        # (parent, metabolite) pair rather than about the molecule, so it is not shared
        # between two parents of the same metabolite the way `bindings` are.
        formed_by = _metabolite_enzymes(drug_id, name)
        if formed_by:
            rec["formed_by"] = formed_by
        sources = _quote_sources(m.get("sources"), label)
        if sources:
            rec["sources"] = sources
        out.append(rec)
    return out


def _drug_enzymes(drug_id: str, rows: Any) -> list[dict[str, Any]]:
    """Validate + normalize a drug's metabolising / inhibited / induced enzymes.

    One node per (enzyme, role) pair, kind ``drug_enzymes``, shaped
    ``{enzyme, role, strength?, sources[]}``:

    - ``enzyme`` must be an :data:`ENZYMES` key (``"cyp2d6"``), so a typo cannot ship
      an isoform the viewer has no label for.
    - ``role`` is an :data:`ENZYME_ROLES` key: what the drug is *to* that enzyme.
    - ``strength`` is optional and must belong to :data:`ENZYME_STRENGTHS`; a source
      that does not qualify the claim leaves it out rather than guessing a tier.
    - ``sources`` grades the claim like any other node (kind ``drug_enzymes``).

    These rows are not authored in ``drugs_data.jsonl``: they come from the committed
    ``tools/generated_cache/drug_enzymes.json`` that ``tools/fetch/fetch_cyp.py``
    writes deterministically from Stahl, so this is a validation pass over generated
    input, and a bad row is a bug in that fetcher rather than a typo to tolerate.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows or []:
        enzyme, role = row.get("enzyme"), row.get("role")
        label = f"Drug {drug_id!r} enzyme {enzyme!r}"
        if enzyme not in ENZYMES:
            raise ValueError(f"{label}: unknown enzyme (see ENZYMES)")
        if role not in ENZYME_ROLES:
            raise ValueError(f"{label}: unknown role {role!r} (see ENZYME_ROLES)")
        if (enzyme, role) in seen:
            raise ValueError(f"{label}: duplicate {role} row")
        seen.add((enzyme, role))
        rec: dict[str, Any] = {"enzyme": enzyme, "role": role}
        strength = row.get("strength")
        if strength is not None:
            if strength not in ENZYME_STRENGTHS:
                raise ValueError(f"{label}: unknown strength {strength!r}")
            rec["strength"] = strength
        rec["sources"] = _quote_sources(row.get("sources"), what=label)
        out.append(rec)
    return out


def _load_drug_enzymes() -> dict[str, list[dict[str, Any]]]:
    """The committed CYP-role caches merged, drug id -> its enzyme rows.

    Two deterministic fetchers write these, both committed so this offline generator
    (and a clone with no author-side trees) reproduces the same data:
    ``tools/fetch/fetch_cyp.py`` from Stahl's Pharmacokinetics block, and
    ``tools/fetch/fetch_cyp_wikipedia.py`` from the drug's English Wikipedia article
    (corpus #9), which is the only source for the 149 drugs outside Stahl's roster.

    **Stahl wins.** A (enzyme, role) pair Stahl already states keeps its Stahl quote;
    Wikipedia only fills pairs Stahl is silent on. Same discipline as the Ki fallback,
    where a Wikipedia value never overrides a measured PDSP assay.
    """
    cache = Path(__file__).resolve().parent / "generated_cache"
    merged: dict[str, list[dict[str, Any]]] = {}
    for name in ("drug_enzymes.json", "drug_enzymes_wikipedia.json"):
        src = cache / name
        if not src.exists():
            continue
        for drug_id, rows in json.loads(src.read_text(encoding="utf-8")).items():
            have = {(r["enzyme"], r["role"]) for r in merged.get(drug_id, [])}
            merged.setdefault(drug_id, []).extend(
                r for r in rows if (r["enzyme"], r["role"]) not in have)
    return {k: sorted(v, key=lambda r: (r["enzyme"], r["role"]))
            for k, v in merged.items()}


def _drug_record(drug: dict[str, Any], valid_targets: set[str],
                 known_bases: set[str],
                 molecule_ids: set[str],
                 enzyme_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Validate + normalize one authored drug into its ``drugs.jsonl`` record.

    The authored drug (from ``tools/data/drugs_data.jsonl``) is mostly passed through;
    this validates it against the drug vocabularies (categories / targets /
    actions / effect overrides). The drug's real provenance lives per-claim: each
    binding's quote ``sources`` + ``ki`` and the ``nbn_sources``, all against the
    Stahl corpus (:data:`SOURCE_CORPORA`); there is no drug-level citation node.
    Translatable free text (``description``, per-binding ``note``, ``nbn``) is
    authored inline as ``{en, fr}`` (or the literal ``"TODO"``), so it does not go
    through the shared FR table. A drug with no bindings at all is emitted
    ``focusable: false`` (listed but not clickable, like a receptor stub).

    Parameters
    ----------
    drug
        One authored drug dict: ``id``, ``name``, ``categories``, ``bindings``
        and optional ``nbn`` / ``description`` / ``wikipedia``.
    valid_targets
        The set of valid binding target ids (DRUG_TARGETS keys + receptor ids).
    known_bases
        Known structure base ids (unused targets validation is by id, kept for
        symmetry with the receptor builder).
    molecule_ids
        Drug ids that have a vendored structure SVG under
        ``public/data/molecules/`` (see :func:`_available_molecule_ids` /
        ``tools/fetch/fetch_molecules.py``); a match adds a ``structure_image`` path the
        viewer embeds, a non-match simply omits it.

    Returns
    -------
    dict
        Record ready to be JSON-serialized as one line of ``drugs.jsonl``.
    """
    for key in ("id", "name", "categories", "bindings"):
        if key not in drug:
            raise KeyError(f"Drug {drug.get('id', drug.get('name'))!r} missing "
                           f"required field {key!r}")
    for cat in drug["categories"]:
        if cat not in DRUG_CATEGORY_LABELS:
            raise KeyError(f"Drug {drug['id']!r} category {cat!r} has no "
                           f"DRUG_CATEGORY_LABELS entry")
    bindings = [_normalize_binding(b, valid_targets, owner_id=drug["id"],
                                   owner_label=f"Drug {drug['id']!r}", with_ki=True)
                for b in drug["bindings"]]
    out: dict[str, Any] = {
        "id": drug["id"],
        "name": drug["name"],
        "categories": list(drug["categories"]),
        "bindings": bindings,
        "focusable": len(bindings) > 0,
    }
    # The drug's class classification ("this drug is an SSRI/...") is its own graded
    # node (kind drug_categories), one per drug: default llm, overridable in
    # DRUG_CATEGORY_PROVENANCE, and upgraded by any quote-level `category_sources`
    # authored on the drug (validated + quote-checked like a binding). The emitted
    # grade is the stronger of the override and the sources.
    cat_provenance = _lookup_provenance(
        DRUG_CATEGORY_PROVENANCE, drug["id"], f"drug class for {drug['id']!r}")
    cat_sources = _quote_sources(
        drug.get("category_sources"), f"Drug {drug['id']!r} category")
    if cat_sources:
        out["category_sources"] = cat_sources
        best = max(cat_sources, key=lambda s: _GRADE_RANK[s["provenance"]])
        if _GRADE_RANK[best["provenance"]] > _GRADE_RANK[cat_provenance]:
            cat_provenance = best["provenance"]
    out["category_provenance"] = cat_provenance
    if drug.get("nbn"):
        out["nbn"] = drug["nbn"]
        # Newer drugs Stahl has not assigned a formal Neuroscience-based
        # Nomenclature to carry `nbn_nonstandard`: their nomenclature value is
        # Stahl's drug-*class* descriptor (sourced from the "Class" line, not an
        # "Neuroscience-based Nomenclature:" line), so the viewer can flag it as
        # non-standard. Set programmatically by apply_nbn_sources.py's fallback.
        if drug.get("nbn_nonstandard"):
            out["nbn_nonstandard"] = True
        # The NbN is quote-sourced like a binding: Stahl prints a verbatim
        # "Neuroscience-based Nomenclature: ..." line on each drug's first page
        # (the Class line for a non-standard entry).
        nbn_sources = _quote_sources(drug.get("nbn_sources"), f"Drug {drug['id']!r} nbn")
        if nbn_sources:
            out["nbn_sources"] = nbn_sources
    # Commercial brand names (Xanax, ...), each a graded node with its own source
    # (kind `drug_brands`). Region-tagged (na/eu/fr) only to order them per locale;
    # the viewer never shows the region. See _drug_brands + apply_brand_sources.py.
    brands = _drug_brands(drug["id"], drug.get("brands"))
    if brands:
        out["brands"] = brands
    # Elimination half-life (T½), stored as canonical hours (+ optional range); its
    # own sourced node (kind `drug_half_life`). Rendered between Brands and Acts-on,
    # formatted to days/hours/minutes by the viewer. See apply_pharmacokinetics.py.
    if drug.get("half_life"):
        out["half_life"] = _half_life(drug["half_life"],
                                      what=f"Drug {drug['id']!r}")
        hl_sources = _quote_sources(drug.get("half_life_sources"),
                                    f"Drug {drug['id']!r} half_life")
        if hl_sources:
            out["half_life_sources"] = hl_sources
    # Active metabolites named in the source (one graded node each, kind
    # `drug_metabolites`); a metabolite that is itself a modeled drug links via
    # drug_id and reuses its bindings/T½ (no duplication), see _drug_metabolites.
    metabolites = _drug_metabolites(drug["id"], drug.get("metabolites"),
                                    valid_targets)
    if metabolites:
        out["metabolites"] = metabolites
    # Metabolising / inhibited / induced enzymes (one graded node each, kind
    # `drug_enzymes`). Not authored in drugs_data.jsonl: the whole set is derived
    # deterministically from Stahl by fetch_cyp.py into the committed
    # generated_cache, so it is merged in here rather than hand-maintained.
    enzymes = _drug_enzymes(drug["id"], enzyme_rows.get(drug["id"]))
    if enzymes:
        out["enzymes"] = enzymes
    # Drug descriptions are intentionally NOT baked: the panel fetches the current
    # Wikipedia lead at runtime (js/wiki.js), exactly like a structure/target, so the
    # text stays up to date and the dataset ships no copyrighted prose. A drug whose
    # live lead fails to load simply shows no description.
    # Search-only alternate names (street names, chemical synonyms, INN/USAN
    # variants). Not a node: an alias says what people CALL the molecule, not
    # anything about the brain, so it carries no grade and is never displayed.
    aliases = DRUG_ALIASES.get(drug["id"])
    if aliases:
        out["aliases"] = list(aliases)
    if drug.get("wikipedia"):
        out["wikipedia"] = drug["wikipedia"]
        out["wikipedia_provenance"] = _wiki_provenance(drug["id"])
    if drug["id"] in molecule_ids:
        # Path from the site root (like a structure's shape_file); the viewer
        # embeds it as an <img>. Only set when the SVG was actually fetched, so a
        # drug without one renders no image (no broken-image placeholder).
        out["structure_image"] = f"data/molecules/{drug['id']}.svg"
    return out


def _available_molecule_ids() -> set[str]:
    """Drug ids that have a vendored structure SVG under ``public/data/molecules/``.

    Those files are produced by the authoring tool ``tools/fetch/fetch_molecules.py``
    (which hits the network); this offline generator only *checks for their
    presence*. The presence of ``<id>.svg`` is the single source of truth for
    whether a drug gets a ``structure_image`` (see :func:`_drug_record`), so the
    set of embedded molecules stays in lock-step with what was actually fetched.
    """
    mol_dir = Path(__file__).resolve().parent.parent / "public" / "data" / "molecules"
    if not mol_dir.exists():
        return set()
    return {p.stem for p in mol_dir.glob("*.svg")}


def _load_image_sources(filename: str) -> dict[str, dict[str, Any]]:
    """Map ``key -> image record`` from a ``tools/<filename>`` sources JSON.

    Unlike the drug molecule SVGs (vendored same-origin), the structure / circuit
    illustration GIFs are too large to commit, so the viewer **hot-links** them
    from Wikimedia at runtime (with a spinner / silent-fail, see ``showStructure`` /
    ``showCircuit``): only the URL is stored in the data, not the binary. The URLs are
    resolved author-side by ``tools/fetch/fetch_structure_images.py`` (which hits the
    network) and recorded in that small JSON; this offline generator just reads it, so
    an owner gets a ``structure_image`` (the lead hero) plus a
    ``structure_image_gallery`` (the other gif/svg from its EN+FR articles, for the
    panel's "show more") iff its key has an entry with a url. A missing file is fine
    (no images). Keyed by structure base id / circuit id respectively.
    """
    src = Path(__file__).resolve().parent / "generated_cache" / filename
    if not src.exists():
        return {}
    data = json.loads(src.read_text(encoding="utf-8"))
    return {key: rec for key, rec in data.items() if rec.get("url")}


def _load_structure_images() -> dict[str, dict[str, Any]]:
    """Structure image sources (see :func:`_load_image_sources`), keyed by base id."""
    return _load_image_sources("structure_images_sources.json")


def _load_circuit_images() -> dict[str, dict[str, Any]]:
    """Circuit image sources (see :func:`_load_image_sources`), keyed by circuit id."""
    return _load_image_sources("circuit_images_sources.json")


def _load_drugs() -> list[dict[str, Any]]:
    """Read the authored drug list from ``tools/data/drugs_data.jsonl`` (if present).

    The drug data is kept in a sibling JSONL file rather than inline in this
    module because it is large and comes from extraction (Stahl's Prescriber's
    Guide); keeping it separate keeps this generator readable. A missing file is
    not an error (the drugs feature is simply empty), so the generator still runs
    on a checkout without it.
    """
    import drugs_io
    if not drugs_io.DRUGS_PATH.exists():
        log.warning("no %s; drugs.jsonl will be empty", drugs_io.DRUGS_PATH.name)
        return []
    return drugs_io.load_drugs()


def build_records() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Expand the anatomy definition into the per-type record sets + shapes.

    Paired entries are emitted twice (``_R`` and ``_L``) but share a *single*
    right-side shape file: the left member references the same file and is
    reflected across x at load time (``mirror``), so the two hemispheres are
    true mirror images rather than copies, and there is exactly one geometry
    file per distinct form (no duplication). Midline entries are emitted once.

    Returns
    -------
    data
        ``{"meta": <dict>, "structures": [...], "projections": [...],
        "circuits": [...]}`` -- one entry per output file (``meta.json`` plus the
        three ``*.jsonl``). Records carry **no** ``type`` field: the file a record
        lives in encodes its type, so it is not duplicated onto every line.
    shapes
        Mapping of shape-file basename -> shape payload dict.
    """
    structures: list[dict[str, Any]] = []
    projections: list[dict[str, Any]] = []
    circuits: list[dict[str, Any]] = []
    projection_groups: list[dict[str, Any]] = []
    receptors: list[dict[str, Any]] = []
    drugs: list[dict[str, Any]] = []
    shapes: dict[str, dict[str, Any]] = {}

    # Same-group blob neighbours for the inter-region jigsaw clipping. Only
    # default blobs take part: curve/composite forms have no clip support and the
    # C-shaped caudate / cerebellum sit apart anyway. Pairs are kept within a
    # group so the small deep nuclei still nest inside the cortex; within a group,
    # overlap is detected per pair.
    blob_groups: dict[str, list[dict[str, Any]]] = {}
    for entry in PAIRED:
        if "shape" not in entry:
            blob_groups.setdefault(entry["group"], []).append(entry)

    # Wikimedia image records resolved author-side (offline read of the sources
    # JSON); a structure whose base has one gets a hot-linked structure_image (the
    # hero) + structure_image_gallery (the GIFs are too large to vendor, unlike the
    # drug molecule SVGs). Circuits get the same, keyed by circuit id.
    structure_images = _load_structure_images()
    circuit_images = _load_circuit_images()

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
        # Bilingual base name (e.g. {"en": "Putamen", "fr": "Putamen"}); the
        # per-hemisphere display names are composed from it (English prefix,
        # French gender/number-agreed suffix). ``fr_gender`` tunes the agreement.
        base_name = _t(entry["name"])
        gender = entry.get("fr_gender", "m")
        structures.append(
            _structure_record(entry, f"{base}_R", _side_name(base_name, gender, "R"),
                              base_name, (x, y, z), base,
                              images=structure_images))
        structures.append(
            _structure_record(entry, f"{base}_L", _side_name(base_name, gender, "L"),
                              base_name, (-x, y, z), base, mirror=True,
                              images=structure_images))

    for entry in MIDLINE:
        sid = entry["base"]
        # Midline structures have no hemisphere, so the full name is the base.
        name = _t(entry["name"])
        structures.append(
            _structure_record(entry, sid, name, name, entry["pos"], sid,
                              images=structure_images))
        shapes[sid] = _shape_record(entry, entry["pos"][0])

    for proj in PROJECTIONS:
        projections.extend(_projection_records(proj))
    # Typo guard: every PROJECTION_QUOTES key must address a real PROJECTIONS entry,
    # else its quote silently sources nothing.
    unmatched = set(PROJECTION_QUOTES) - {(p["from"], p["to"]) for p in PROJECTIONS}
    if unmatched:
        raise KeyError(
            f"PROJECTION_QUOTES keys match no PROJECTIONS entry: {sorted(unmatched)}")
    unmatched_bases = set(STRUCTURE_QUOTES) - {
        e["base"] for e in (*PAIRED, *MIDLINE)}
    if unmatched_bases:
        raise KeyError(
            f"STRUCTURE_QUOTES keys are not structure bases: "
            f"{sorted(unmatched_bases)}")
    unmatched_rq = set(STAHL_ESSENTIAL_RECEPTOR_QUOTES) - {r["id"] for r in RECEPTORS}
    if unmatched_rq:
        raise KeyError(
            f"STAHL_ESSENTIAL_RECEPTOR_QUOTES keys are not receptor ids: "
            f"{sorted(unmatched_rq)}")
    # Every quoted receptor needs a coverage entry (else its quote would grade
    # nothing) and vice-versa (a coverage entry with no quote grades nothing), and
    # each covered attribute must be a real classification attribute. This keeps the
    # per-attribute grading honest: a quote can only lift the attributes it names.
    cov_no_quote = set(RECEPTOR_CLASSIFICATION_COVERAGE) - set(STAHL_ESSENTIAL_RECEPTOR_QUOTES)
    quote_no_cov = set(STAHL_ESSENTIAL_RECEPTOR_QUOTES) - set(RECEPTOR_CLASSIFICATION_COVERAGE)
    if cov_no_quote or quote_no_cov:
        raise KeyError(
            "RECEPTOR_CLASSIFICATION_COVERAGE must match the receptor-quote keys "
            f"(coverage without quote: {sorted(cov_no_quote)}; quote without "
            f"coverage: {sorted(quote_no_cov)})")
    bad_attrs = {a for attrs in RECEPTOR_CLASSIFICATION_COVERAGE.values()
                 for a in attrs if a not in CLASSIFICATION_ATTRS}
    if bad_attrs:
        raise KeyError(
            f"RECEPTOR_CLASSIFICATION_COVERAGE has unknown attributes: "
            f"{sorted(bad_attrs)} (valid: {CLASSIFICATION_ATTRS})")
    # Per-attribute quote overrides must key real receptors and real attributes.
    aq_no_receptor = set(RECEPTOR_ATTR_QUOTES) - {r["id"] for r in RECEPTORS}
    if aq_no_receptor:
        raise KeyError(
            f"RECEPTOR_ATTR_QUOTES keys are not receptor ids: {sorted(aq_no_receptor)}")
    bad_aq_attrs = {a for m in RECEPTOR_ATTR_QUOTES.values()
                    for a in m if a not in CLASSIFICATION_ATTRS}
    if bad_aq_attrs:
        raise KeyError(
            f"RECEPTOR_ATTR_QUOTES has unknown attributes: {sorted(bad_aq_attrs)} "
            f"(valid: {CLASSIFICATION_ATTRS})")
    unmatched_tq = set(STAHL_ESSENTIAL_TARGET_QUOTES) - set(DRUG_TARGETS)
    if unmatched_tq:
        raise KeyError(
            f"STAHL_ESSENTIAL_TARGET_QUOTES keys are not DRUG_TARGETS ids: "
            f"{sorted(unmatched_tq)}")
    # A polarity quote must key a target that actually carries a polarity flag,
    # else it grades a direction claim that is never emitted.
    _polarity_ids = {tid for tid, spec in DRUG_TARGETS.items()
                     if any(f in spec for f in ("vesicular", "sign", "synaptic"))}
    unmatched_pq = set(TARGET_POLARITY_QUOTES) - _polarity_ids
    if unmatched_pq:
        raise KeyError(
            f"TARGET_POLARITY_QUOTES keys have no polarity flag in DRUG_TARGETS: "
            f"{sorted(unmatched_pq)}")
    unmatched_pp = set(TARGET_POLARITY_PROVENANCE) - _polarity_ids
    if unmatched_pp:
        raise KeyError(
            f"TARGET_POLARITY_PROVENANCE keys have no polarity flag in "
            f"DRUG_TARGETS: {sorted(unmatched_pp)}")

    # Circuits: expand each base structure id to whatever was emitted (both
    # hemispheres for a paired form, the bare id for a midline one). Built from
    # the structure records already collected, so it can't reference a structure
    # that doesn't exist.
    structure_ids = {r["id"] for r in structures}
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
        record = {
            "id": circuit["id"],
            "name": _t(circuit["name"]),
            "structures": ids,
        }
        if circuit.get("description"):
            record["description"] = {"en": circuit["description"],
                                     "fr": circuit["description_fr"]}
        if circuit.get("sources"):
            record["sources"] = _expand_sources(
                circuit["sources"], f"circuit {circuit['id']!r}")
        # Optional Wikipedia reference (+ its own grade), so the circuit panel shows
        # a "read more" link and live-fetches the current lead as a sourced
        # description, exactly like a structure/target. A present link defaults to
        # WIKIPEDIA_DEFAULT_PROVENANCE (sourced); override in WIKIPEDIA_PROVENANCE.
        if circuit.get("wikipedia"):
            record["wikipedia"] = circuit["wikipedia"]
            record["wikipedia_provenance"] = _wiki_provenance(circuit["id"])
        # Hot-linked Wikipedia illustration (hero + gallery), keyed by circuit id, the
        # same treatment a structure gets (see _load_circuit_images). Only set when the
        # circuit was resolved, so an unillustrated one renders no image.
        cimg = circuit_images.get(circuit["id"])
        if cimg and cimg.get("url"):
            record["structure_image"] = cimg["url"]
            cgallery = [g["url"] for g in cimg.get("gallery", []) if g.get("url")]
            if cgallery:
                record["structure_image_gallery"] = cgallery
        circuits.append(record)

    # Projection groups: the legend's per-pathway rows as a sourced data structure
    # (see PROJECTION_GROUPS). One record per group, in BOTH colour modes; the
    # member pathways are derived in the viewer (the projections whose kind / sign
    # matches), so a group never duplicates the projection list. ``key`` is
    # validated against the kind / sign vocabularies (typo guard).
    seen_group_ids: set[str] = set()
    for group in PROJECTION_GROUPS:
        mode, key = group["mode"], group["key"]
        if mode == "kind":
            if key not in PROJECTION_COLORS:
                raise KeyError(
                    f"Projection group references unknown kind {key!r}")
        elif mode == "sign":
            if key not in SIGN_LABELS:
                raise KeyError(
                    f"Projection group references unknown sign {key!r}")
        else:
            raise KeyError(f"Projection group {key!r} has unknown mode {mode!r}")
        gid = f"{mode}_{key}"
        if gid in seen_group_ids:
            raise KeyError(f"Duplicate projection-group id {gid!r}")
        seen_group_ids.add(gid)
        record = {
            "id": gid,
            "mode": mode,
            "key": key,
            "name": _t(group["name"]),
            "description": {"en": group["description"],
                            "fr": group["description_fr"]},
            "classification_provenance": _provenance(
                group.get("classification_provenance", DEFAULT_PROVENANCE),
                f"projection group {gid!r}"),
        }
        if group.get("wikipedia"):
            record["wikipedia"] = group["wikipedia"]
            record["wikipedia_provenance"] = _lookup_provenance(
                WIKIPEDIA_PROVENANCE, gid, f"wikipedia reference for {gid!r}",
                default=WIKIPEDIA_DEFAULT_PROVENANCE)
        if group.get("sources"):
            record["sources"] = _expand_sources(
                group["sources"], f"projection group {gid!r}")
        projection_groups.append(record)

    # Receptors: validate + normalize each against the known structure bases
    # (locations reference bases like circuits do; the viewer expands them to
    # both hemispheres). Duplicate ids fail the build.
    receptor_bases = {e["base"] for e in PAIRED} | {e["base"] for e in MIDLINE}
    seen_receptor_ids: set[str] = set()
    for rec in RECEPTORS:
        if rec["id"] in seen_receptor_ids:
            raise KeyError(f"Duplicate receptor id {rec['id']!r}")
        seen_receptor_ids.add(rec["id"])
        receptors.append(_receptor_record(rec, receptor_bases))

    # Drugs: authored in tools/data/drugs_data.jsonl, validated against the drug
    # vocabularies + the merged target map (DRUG_TARGETS + receptor ids). Every
    # DRUG_TARGETS region must be a known structure base (typo guard), like a
    # receptor location. Duplicate drug ids fail the build.
    for tid, spec in DRUG_TARGETS.items():
        if spec["type"] not in TARGET_TYPE_LABELS or spec["type"] == "receptor":
            raise KeyError(
                f"DRUG_TARGETS[{tid!r}] type {spec['type']!r} is not a "
                f"non-receptor TARGET_TYPE_LABELS key")
        wiki = spec.get("wikipedia")
        if wiki is not None and not str(wiki).startswith(("http://", "https://")):
            raise ValueError(
                f"DRUG_TARGETS[{tid!r}] wikipedia must be an http(s) URL or absent")
        for base in spec["regions"]:
            if base not in receptor_bases:
                raise KeyError(
                    f"DRUG_TARGETS[{tid!r}] region {base!r} is not a known "
                    f"structure base")
    drug_targets = _build_drug_targets(receptors)
    valid_targets = set(drug_targets.keys())
    molecule_ids = _available_molecule_ids()
    enzyme_rows = _load_drug_enzymes()
    seen_drug_ids: set[str] = set()
    for drug in _load_drugs():
        if drug["id"] in seen_drug_ids:
            raise KeyError(f"Duplicate drug id {drug['id']!r}")
        seen_drug_ids.add(drug["id"])
        drugs.append(
            _drug_record(drug, valid_targets, receptor_bases, molecule_ids,
                         enzyme_rows))
    _check_drug_aliases(seen_drug_ids)
    # A hand-curated formed_by row whose (drug, metabolite) key matched nothing: the
    # metabolite was renamed or dropped by an applier re-run, so the node silently
    # vanished. Raise rather than publish a quieter dataset than the author wrote.
    orphans = sorted(set(METABOLITE_ENZYME_QUOTES) - _METABOLITE_ENZYME_SEEN)
    if orphans:
        raise KeyError(
            "METABOLITE_ENZYME_QUOTES keys match no metabolite in drugs_data.jsonl: "
            + ", ".join(f"{d}/{n}" for d, n in orphans))

    # Fail loudly if the data uses a kind or group with no entry in the maps above.
    kinds = {r["kind"] for r in projections}
    missing_kinds = kinds - PROJECTION_COLORS.keys()
    if missing_kinds:
        raise KeyError(
            f"Projection kind(s) with no PROJECTION_COLORS entry: "
            f"{sorted(missing_kinds)}")
    groups = {r["group"] for r in structures}
    missing_groups = groups - GROUP_LABELS.keys()
    if missing_groups:
        raise KeyError(
            f"Structure group(s) with no GROUP_LABELS entry: "
            f"{sorted(missing_groups)}")
    known_bases = {e["base"] for e in PAIRED} | {e["base"] for e in MIDLINE}
    unknown_wiki = WIKIPEDIA.keys() - known_bases
    if unknown_wiki:
        raise KeyError(
            f"WIKIPEDIA entry for unknown structure base(s): "
            f"{sorted(unknown_wiki)}")
    # Every translatable string went through _t(); fail loudly (listing them all)
    # if any had no FR entry, so the data can't ship half-translated.
    if _MISSING_TRANSLATIONS:
        raise KeyError(
            "Missing FR translation for: "
            + "; ".join(repr(s) for s in sorted(_MISSING_TRANSLATIONS)))

    # Presentation metadata (its own meta.json) so a consumer reading the dataset
    # is self-contained: arrow colours + legend headings live in the data, not
    # only in the viewer's JS.
    meta = {
        # Both presentation maps are emitted bilingually: the kind->arrow colour
        # map is language-neutral, but kind_labels/group_labels carry {en, fr}
        # display strings the viewer resolves via window.__I18N__.pick.
        "projection_colors": PROJECTION_COLORS,
        "kind_labels": {kind: _t(kind) for kind in PROJECTION_COLORS},
        "group_labels": {g: _t(label) for g, label in GROUP_LABELS.items()},
        # Sign (excitatory / inhibitory) colour mode: kind->sign fold, sign->colour
        # swatch (language-neutral) and sign->{en,fr} legend heading. The viewer's
        # colour toggle reads these so neither palette nor labels are hardcoded.
        "kind_signs": KIND_TO_SIGN,
        "sign_colors": SIGN_COLORS,
        "sign_labels": {sign: _t(label) for sign, label in SIGN_LABELS.items()},
        # Drug target system -> projection kind, for the per-drug flow overlay (see
        # SYSTEM_FLOW_KINDS). Language-neutral keys both sides.
        "system_flow_kinds": SYSTEM_FLOW_KINDS,
        # Which bindings set a transmitter's tone, and which way (see TONE_RULES).
        # Emitted rather than transcribed because two consumers need the same rule:
        # the viewer animates it and check_data cross-checks it.
        "tone_rules": TONE_RULES,
        # Receptor legend maps: family -> heading, mechanism class -> label, and
        # pre/post-synaptic -> label (all bilingual). The per-receptor sign reuses
        # sign_colors / sign_labels above, so the receptor legend needs no extra
        # colour map. Object key order is the legend's family display order.
        "receptor_family_labels": {
            f: _t(label) for f, label in RECEPTOR_FAMILY_LABELS.items()},
        "receptor_class_labels": {
            c: _t(label) for c, label in RECEPTOR_CLASS_LABELS.items()},
        "synaptic_labels": {
            s: _t(label) for s, label in SYNAPTIC_LABELS.items()},
        # Drug legend + animation maps (already bilingual; see the drug schema
        # block near the top). drug_targets merges DRUG_TARGETS with every
        # receptor id so a binding can target either.
        "drug_category_labels": DRUG_CATEGORY_LABELS,
        # Merged binding-target map (DRUG_TARGETS + every receptor id), plus the
        # non-receptor target type -> {en,fr} tag and type -> swatch colour the
        # merged "Receptors & targets" legend reads (receptors keep their sign
        # swatch, so target_type_colors omits "receptor").
        "drug_targets": drug_targets,
        "target_type_labels": {
            ty: _t(label) for ty, label in TARGET_TYPE_LABELS.items()},
        "target_type_colors": TARGET_TYPE_COLORS,
        "drug_actions": DRUG_ACTIONS,
        "drug_effect_colors": DRUG_EFFECT_COLORS,
        "drug_effect_labels": DRUG_EFFECT_LABELS,
        # Drug metabolism vocabularies (see ENZYMES in data_generators.drugs): the
        # enzyme id -> {label, wikipedia} map the Metabolism rows and the Enzymes
        # browse section read, plus the role and strength labels. Self-describing so
        # the viewer never hardcodes an isoform name or a role heading.
        "enzymes": ENZYMES,
        "enzyme_roles": ENZYME_ROLES,
        "enzyme_strengths": ENZYME_STRENGTHS,
        "enzyme_reactions": ENZYME_REACTIONS,
        # Source corpora the per-binding (and later per-field) drug sources cite,
        # keyed by id (see SOURCE_CORPORA). The viewer reads citation/url to render
        # each binding's source; check_data.py reads pages_dir to confirm quotes.
        # Self-describing so a port needs no hardcoded citation.
        "source_corpora": SOURCE_CORPORA,
        # Cross-donor-agreement floor a relative-expression profile had to clear to be
        # published (see the density pass in tools/fetch/fetch_allen.py). Emitted so the
        # panel can state the real threshold instead of restating the constant. Absent
        # when no density has been applied.
        **({"density_min_reliability": DENSITY_MIN_RELIABILITY}
           if DENSITY_MIN_RELIABILITY is not None else {}),
        # Programmatic sourcing tally over the shipped data (per-kind + headline);
        # the About panel + README read it so the "% sourced" figure is a real
        # count, never hand-typed. See _provenance_stats.
        "provenance_stats": _provenance_stats(
            structures, projections, circuits, projection_groups,
            receptors, drugs, drug_targets),
    }

    return ({"meta": meta, "structures": structures,
             "projections": projections, "circuits": circuits,
             "projection_groups": projection_groups,
             "receptors": receptors, "drugs": drugs}, shapes)


def write_artifacts(root: Path) -> None:
    """Write the dataset under ``root`` (``data/`` + ``data/shapes/``).

    The dataset is split by record type for clarity: ``data/meta.json`` (a single
    object) plus one ``*.jsonl`` per collection (``structures``, ``projections``,
    ``circuits``); the file a record lives in encodes its type. The
    ``data/shapes`` directory is cleared of stale ``*.json`` first so removing a
    structure here also removes its orphaned shape file.
    """
    _check_tone_rules()
    data, shapes = build_records()

    data_dir = root / "data"
    shapes_dir = data_dir / "shapes"
    data_dir.mkdir(parents=True, exist_ok=True)
    shapes_dir.mkdir(parents=True, exist_ok=True)

    for stale in shapes_dir.glob("*.json"):
        stale.unlink()

    # Externalize every bilingual {en,fr} dict to its English string at write time,
    # collecting the en->fr pairs into a single deduplicated side table
    # (translations.fr.json). The emitted data is English-only; French is recovered
    # by the viewer from the side table (see externalize() + js/i18n.js). Reset the
    # accumulator first so a second run in the same process starts clean.
    reset_translations()
    # Collapse every embedded source quote into the deduplicated quotes.jsonl side
    # table, replacing it with a {quote_id, provenance} reference. Applied after the
    # i18n externalize (quote text is plain English, never bilingual); both the
    # viewer and check_data.py rehydrate it in memory. Reset first (idempotent run).
    reset_quotes()

    def _emit(record):
        return externalize_quotes(externalize(record))

    # meta is a single object -> pretty-printed meta.json; the collections are one
    # JSON object per line -> one *.jsonl each.
    meta_path = data_dir / "meta.json"
    meta_path.write_text(
        json.dumps(_emit(data["meta"]), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    log.info("wrote %s", meta_path)

    for name in ("structures", "projections", "circuits", "projection_groups",
                 "receptors", "drugs"):
        path = data_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for record in data[name]:
                fh.write(json.dumps(_emit(record), ensure_ascii=False) + "\n")
        log.info("wrote %s (%d lines)", path, len(data[name]))

    # The per-version "what's new" bullets, newest version first. Authored under
    # docs/changelog/<version>/changelog.md, which is not web-exposed; emitted here
    # so the viewer can fetch it, and only when its popup opens (it is not part of
    # the boot payload). Goes through _emit like everything else, so its French ends
    # up in translations.fr.json rather than duplicated in the file.
    changelog_path = data_dir / "changelog.json"
    releases = [_emit(release) for release in
                load_changelog(Path(__file__).resolve().parent.parent / "docs")]
    changelog_path.write_text(
        json.dumps({"versions": releases}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    log.info("wrote %s (%d versions)", changelog_path, len(releases))

    # The deduplicated quote table, one quote node per line, sorted by id for
    # stable diffs. Fetched by the viewer (rehydrated onto each source at load).
    quotes_path = data_dir / "quotes.jsonl"
    quotes_path.write_text(
        "".join(line + "\n" for line in quote_lines()), encoding="utf-8")
    log.info("wrote %s (%d quotes)", quotes_path, len(QUOTES))

    # The deduplicated French side table, keys sorted for stable diffs. Fetched by
    # the viewer only when the active language is French (see js/data.js).
    tr_path = data_dir / "translations.fr.json"
    tr_path.write_text(
        json.dumps(TRANSLATIONS, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    log.info("wrote %s (%d pairs)", tr_path, len(TRANSLATIONS))

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
        # This script lives in tools/; the data/ tree it generates (meta.json +
        # the *.jsonl + shapes/) is *served*, so it belongs under the public/ site root.
        default=Path(__file__).resolve().parent.parent / "public",
        help="Site root to write data/ (meta.json + *.jsonl + shapes/) into (default: ../public).",
    )
    args = parser.parse_args()
    write_artifacts(args.root)


if __name__ == "__main__":
    main()
