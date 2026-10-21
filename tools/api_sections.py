"""How each stored field of each /api page kind is presented: the one declarative table
``render_api.py`` lays a page out from, so the Markdown wears the viewer's own words.

Every label is an i18n key of ``public/js/i18n/en.js`` (read by ``lib.i18n_catalogue``),
never a copy of its text, so a UI rename ("Brands" -> "Proprietary names") reaches the
Markdown with no edit here. ``FIELDS`` is in panel order: a page lists its sections in
that order, then any field the table does not know (which ``tests/test_panel_md_parity.py``
refuses, so a new stored field or a new panel section forces a decision here).

- ``FIELDS[kind]``: ``field -> Label``. ``Label.key`` is the heading (a section) or the
  row label (a Facts line) the panel shows for it; ``sub`` its subtitle; ``parent`` the
  panel section it sits inside; ``section`` renders a list of plain values as its own
  section (the panel gives it a heading) rather than a Facts line. A field the panel
  shows with no label of its own has ``key=None`` and says why.
- ``HIDDEN``: stored fields never rendered (presentation only), with the reason.
- ``FOLDED``: per-attribute grade maps whose entries ride the attribute's own Facts line,
  as the panel's pills do.
- ``VALUE_LABELS``: the ``meta.json`` map the panel words a stored value with.
- ``SLOT_PLACE``: where each addon slot (``meta.addon_slots``) lands on a page.
- ``VIEWER_ONLY``: panel headings with no Markdown twin, each with the reason (the viewer
  derives that section in the browser; see ``render_api``'s docstring).

Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.i18n_catalogue import catalogue, fill  # noqa: E402

EN = catalogue("en")


class Label(NamedTuple):
    key: str | None          # i18n key of the heading / row label; may hold {record field}
    sub: str | None = None   # i18n key of the subtitle
    parent: str | None = None  # i18n key(s) of the enclosing panel section, " > " joined
    section: bool = False    # a plain-value list the panel heads as a section of its own
    why: str = ""            # when key is None: why the panel shows no label for it


_NOLABEL_SOURCES = Label(None, why="the panel shows it as the grade pill on the claim it backs")
_REFERENCE = Label("info.reference")
_DESCRIPTION = Label(None, why="the panel's lead paragraph, under the title")
_GENE = Label(None, why="only feeds the panel's external lookup links (UniProt, ClinPGx)")
_ALIASES = Label(None, why="search-only aliases: the panel never shows them")
_ADMIN, _PK, _PHYSCHEM = "drug.admin", "drug.pkTiming", "drug.pkTiming > drug.physchem"
_METAB, _FOUND = "drug.metabolism", "receptor.foundIn"
# The panel sections that only group other fields' rows: heading key -> subtitle key.
PARENTS: dict[str, str | None] = {
    "drug.admin": "drug.adminSub", "drug.pkTiming": "drug.pkTimingSub",
    "drug.physchem": "drug.physchemSub", "drug.metabolism": "drug.metabolismSub",
    "drug.pharmacogenomics": "drug.pharmacogenomicsSub", "drug.actsOn": "drug.actsOnSub",
    "receptor.foundIn": "receptor.foundInSub", "effects.heading": "effects.headingSub",
}


def _expression(regions: str) -> dict[str, Label]:
    """The expression + BETA sections a receptor and a non-receptor target share."""
    return {
        regions: Label("receptor.foundIn", "receptor.foundInSub", section=True),
        "ubiquitous": Label("receptor.ubiquitous", parent=_FOUND),
        "location_uncertainty": Label(None, why="the panel flags each doubted region in its "
                                                "Regional distribution row"),
        "density": Label("receptor.density", parent=_FOUND),
        "effects": Label("effects.heading", "effects.headingSub"),
        "effects_unknown": Label("effects.unknown", parent="effects.heading"),
        "release_modulation": Label("relmod.heading", "relmod.headingSub"),
        "demographics": Label("demog.heading", "demog.headingSub"),
        "variants": Label("variant.heading", "variant.headingSub"),
    }


_DRUG_PK = {
    "half_life": Label("drug.halfLife", parent=_PK),
    "tmax": Label("drug.tmax", parent=_PK),
}

FIELDS: dict[str, dict[str, Label]] = {
    "drug": {
        "categories": Label("drug.class", parent=_ADMIN),
        "nbn": Label("drug.nomenclature", parent=_ADMIN),
        "nbn_nonstandard": Label(None, why="the panel words it as a note on the Nomenclature row"),
        "originator": Label("drug.originator", parent=_ADMIN),
        "originator_country": Label(None, why="a chip on the panel's Originator row"),
        "first_approval": Label("drug.firstApproval", parent=_ADMIN),
        "withdrawals": Label("drug.withdrawn", parent=_ADMIN),
        "holders": Label("drug.holders", parent=_ADMIN),
        "brands": Label("drug.brands", "drug.brandsSub", parent=_ADMIN),
        "constituents": Label("drug.combo"),
        "prodrug": Label("drug.prodrug", parent="drug.actsOn"),
        **_DRUG_PK,
        "therapeutic_range": Label("drug.therapeuticRange", parent=_PK),
        "alert_level": Label("drug.alertLevel", parent=_PK),
        "formulations": Label("drug.formulations", "drug.formulationsSub", parent=_PK),
        "xlogp": Label("drug.xlogp", parent=_PHYSCHEM),
        "tpsa": Label("drug.tpsa", parent=_PHYSCHEM),
        "bbb": Label("drug.bbb", parent=_PHYSCHEM),
        "bindings": Label("drug.actsOn", "drug.actsOnSub"),
        "metabolites": Label("drug.metabolites", "drug.metabolitesSub", parent=_METAB),
        "enzymes": Label("drug.metabEnzymes", "drug.metabEnzymesSub", parent=_METAB),
        "pgx": Label("drug.pgx", "drug.pgxSub", parent="drug.pharmacogenomics"),
        "workup": Label("drug.workup", "drug.workupSub"),
        "wikipedia": _REFERENCE,
        "aliases": _ALIASES,
        "name_qualifier": Label(None, why="folded into the panel title"),
    },
    "metabolite": {
        **_DRUG_PK,
        "bindings": Label("drug.actsOn", "drug.actsOnSub"),
        "drug_id": Label(None, why="the panel opens the metabolite's own drug record"),
    },
    "receptor": {
        "family": Label("receptor.system"),
        "neurotransmitter": Label("receptor.neurotransmitter"),
        "receptor_class": Label("receptor.type"),
        "sign": Label("receptor.effect"),
        "synaptic": Label("receptor.synaptic"),
        **_expression("locations"),
        "description": _DESCRIPTION,
        "wikipedia": _REFERENCE,
        "gene": _GENE,
    },
    "target": {
        "type": Label("receptor.type"),
        "system": Label("receptor.system"),
        "vesicular": Label("target.polarityVesicular"),
        "polarity": Label("target.polarity"),
        "sign": Label("receptor.effect"),
        "synaptic": Label("receptor.synaptic"),
        "classification_provenance": _NOLABEL_SOURCES,
        "sources": _NOLABEL_SOURCES,
        **_expression("regions"),
        "subtypes": Label(None, why="the panel only uses it to group interacting drugs by "
                                    "subtype (By receptor subtype, derived)"),
        "description": _DESCRIPTION,
        "wikipedia": _REFERENCE,
        "gene": _GENE,
    },
    "structure": {
        "base_name": Label(None, why="the panel title"),
        "group": Label(None, why="the panel's identity line, worded by meta.group_labels"),
        "classification_provenance": _NOLABEL_SOURCES,
        "sources": _NOLABEL_SOURCES,
        "aliases": _ALIASES,
        "wikipedia": _REFERENCE,
    },
    "projection": {
        "from": Label(None, why="the panel's route line (from -> to)"),
        "to": Label(None, why="the panel's route line (from -> to)"),
        "bidirectional": Label(None, why="the route line's double arrow"),
        "kind": Label(None, why="the colour swatch line, worded by meta.kind_labels"),
        "neurotransmitter": Label(None, why="the line under the colour swatch"),
        "label": Label(None, why="the panel title"),
        "description": _DESCRIPTION,
        "claims": Label(None, why="the grade pills on the kind and neurotransmitter lines"),
        "uncertainty": Label(None, why="the doubt bullets in the route pill's tooltip"),
        "tentative": Label(None, why="worded in the route pill's tooltip"),
        "sources": _NOLABEL_SOURCES,
    },
    "circuit": {
        "sources": Label("circuit.heading"),
        "structures": Label("circuit.structures", section=True),
        "description": _DESCRIPTION,
        "wikipedia": _REFERENCE,
    },
    "group": {
        "sources": Label("group.{mode}Heading", "group.{mode}HeadingSub"),
        "mode": Label(None, why="picks the identity line's wording (by sign / by neurotransmitter)"),
        "key": Label(None, why="the member-pathway filter (derived list)"),
        "classification_provenance": _NOLABEL_SOURCES,
        "description": _DESCRIPTION,
        "wikipedia": _REFERENCE,
    },
    # Not stored fields: the two lists of the derived BETA effect page (render_api.effect_page).
    "effect": {
        "owners": Label("effect.owners", "effects.hint"),  # {n}: filled by effect_page
        "drugs": Label("effect.drugs", "effect.drugsHint"),
    },
}

HIDDEN: dict[str, str] = {
    "id": "the page address", "name": "the page title",
    "color": "a colour means nothing in text", "position": "3D geometry",
    "shape_file": "3D geometry", "shape": "3D geometry",
    "focusable": "a viewer flag (whether the scene can focus it)",
    "mirror": "said once in the page header (paired hemispheres)",
    "structure_image": "an image", "structure_image_gallery": "images",
    "receptor": "on a non-receptor target page it is always empty",
}

FOLDED = {("receptor", "classification")}

VALUE_LABELS: dict[tuple[str, str], str] = {
    ("drug", "categories"): "drug_category_labels",
    ("receptor", "family"): "receptor_family_labels",
    ("receptor", "receptor_class"): "receptor_class_labels",
    ("receptor", "sign"): "sign_labels", ("target", "sign"): "sign_labels",
    ("receptor", "synaptic"): "synaptic_labels", ("target", "synaptic"): "synaptic_labels",
    ("target", "type"): "target_type_labels", ("target", "system"): "receptor_family_labels",
    ("structure", "group"): "group_labels",
}

# Addon slot -> (page kind, the fields whose section holds it, first present wins).
# No field, or none present: the top of the page, as the panel's `*.top` slots.
# A `section.*` slot is owned by a panel section, so it lands on every page showing it.
SLOT_PLACE: dict[str, tuple[str, tuple[str, ...]]] = {
    "drug.top": ("drug", ()), "receptor.top": ("receptor", ()),
    "target.top": ("target", ()), "structure.top": ("structure", ()),
    "drug.timing": ("drug", ("half_life", "tmax")),
    "drug.metabolism": ("drug", ("enzymes",)),
    "section.metabolism": ("drug", ("enzymes",)),
    "section.projections": ("projection", ()),
}

DERIVED = "derived in the browser from stored facts, deliberately not rendered (see render_api)"
VIEWER_ONLY: dict[str, str] = {
    "drug.tone": f"net neurotransmission estimate, {DERIVED}",
    "drug.pkInteractions": f"drug -> drug enzyme interactions, {DERIVED}",
    "effects.drugHeading": f"a drug's possible effects, {DERIVED}; the /api/effect pages list them",
    "relmod.drugHeading": f"a drug's presynaptic modulation, {DERIVED}",
    "variant.drugHeading": "a reverse join of the receptor pages' variants (ClinPGx), which "
                           "the receptor and target pages render",
    "targets.interactingDrugs": "a reverse join of drug bindings; each drug page states its own",
    "targets.bySubtype": "the same reverse join, grouped by subtype",
    "structure.expressed": "a reverse join of receptor/target regions; each receptor page "
                           "states its own",
    "info.connections": "a reverse join of projections; each pathway has its own page",
    "circuit.pathways": "member pathways are derived, never stored (projections with both "
                        "endpoints in the circuit)",
    "group.pathways": "member pathways are derived, never stored (projections of that kind/sign)",
    "group.actingDrugs": f"drugs acting on the system, {DERIVED}",
    "receptor.foundOther": "a grouping sub-heading of Regional distribution by brain group; the "
                           "Markdown lists the regions flat",
    "enzyme.forms": "enzyme panels have no /api page yet (meta.enzymes, no record collection)",
    "enzyme.variability": "enzyme panels have no /api page yet",
    "enzyme.drugs": "enzyme panels have no /api page yet",
}


def text(key: str | None, rec: dict[str, Any] | None = None, **values: Any) -> str | None:
    """The English UI string for ``key`` (``{field}`` filled from ``rec`` first), else
    None when the key is None or (a mode-built subtitle) not in the catalogue."""
    if key is None:
        return None
    key = key.format(**(rec or {})) if "{" in key else key
    return fill(EN[key], **values) if key in EN else None


def label(kind: str, field: str) -> Label | None:
    return FIELDS.get(kind, {}).get(field)


def parent_text(lab: Label) -> str | None:
    """The enclosing panel section(s), as the panel words them, each with its subtitle
    ("Pharmacokinetics (Absorption, ...) > CNS penetration (How readily ...)"), or None."""
    if not lab.parent:
        return None
    return " > ".join(EN[k] + (f" ({EN[PARENTS[k]]})" if PARENTS[k] else "")
                      for k in lab.parent.split(" > "))


def order(kind: str, rec: dict[str, Any]) -> list[str]:
    """``rec``'s keys in panel order (the table's), unknown ones after, in record order."""
    known = list(FIELDS.get(kind, {}))
    return [k for k in known if k in rec] + [k for k in rec if k not in FIELDS.get(kind, {})]
