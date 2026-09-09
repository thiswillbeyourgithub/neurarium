"""data_generators.addons: **addon nodes**, the panel-slot annotation kind.

Every other node kind answers a question the panel already asks ("what does this
drug bind?", "which enzymes clear it?"), so its place in the UI is implied by its
collection. An *addon* is the escape hatch for the claim that has no such home: a
caveat about a whole section, a flag on one drug, a note that only makes sense
sitting next to something else. It is a node like any other (it carries its own
quote-level ``sources`` and grade, it is tallied, it shows in the Data browser),
with one extra property: **it says where it goes**. The record carries the anchor
(which node's panel), the ``slot`` (where in that panel), and the ``display``
(how to draw it), so adding one is a data edit and never a viewer edit.

The three vocabularies below are closed and emitted into ``meta`` (``addon_slots``
/ ``addon_displays`` / ``addon_tones``), so the viewer reads the hook registry from
the data instead of hardcoding it and ``check_data.py`` can reject an unknown slot.

**A slot only exists if the viewer actually calls it.** Every key of
:data:`ADDON_SLOTS` has a matching ``appendAddons(...)`` call site in
``js/main.js``; adding a slot here without one would silently swallow the node.
"""

from __future__ import annotations

from typing import Any

from .provenance import _quote_sources

# Insertion points the viewer offers, slot -> the node kind whose panel it is in.
# The name is "<owner kind>.<where>", so a reader can see the anchor kind without
# looking it up. Each is one appendAddons() call in js/main.js; see the module
# docstring before adding one.
ADDON_SLOTS: dict[str, str] = {
    # Top of a drug panel, under the title/class and the combo warning: a caveat
    # about the drug as a whole (e.g. "does not cross the blood-brain barrier").
    "drug.top": "drug",
    # Inside the drug panel's Metabolism section, under its heading + caption and
    # above the first enzyme row: a caveat about how the drug is cleared, which
    # the per-isoform rows below cannot express (they state a role, not a curve).
    "drug.metabolism": "drug",
    # Top of a receptor / non-receptor-target / structure panel, same role as
    # drug.top for the other three panel kinds.
    "receptor.top": "receptor",
    "target.top": "target",
    "structure.top": "structure",
}

# How an addon draws. One form today; the dispatch (ADDON_RENDERERS in js/main.js)
# is what makes a second one (an inline icon + tooltip, say) a viewer addition
# rather than a rewrite.
ADDON_DISPLAYS: tuple[str, ...] = ("admonition",)

# Tone -> its glyph. The tone is the *claim's* register (a caution reads louder
# than a note), so it is data; the colour ramp each tone paints with is UI chrome
# and lives with the rest of the panel CSS in index.html.
ADDON_TONES: dict[str, str] = {
    "info": "ℹ",
    "caution": "⚠",
}


# ---------------------------------------------------------------------------
# The authored addons. Each is one sourceable claim, so it is graded like any
# other node: a `verified` source needs a page + a verbatim quote that
# check_data.py finds on that page.
# ---------------------------------------------------------------------------

ADDONS: list[dict[str, Any]] = [
    {
        "id": "paroxetine_nonlinear_pk",
        "owner_kind": "drug",
        "owner": "paroxetine",
        "slot": "drug.metabolism",
        "display": "admonition",
        "tone": "caution",
        "title": {
            "en": "Non-linear pharmacokinetics",
            "fr": "Pharmacocinétique non linéaire",
        },
        "text": {
            "en": "Paroxetine is a mechanism-based (\"suicide\") inhibitor of "
                  "CYP2D6, the isoform that clears it: it inactivates its own "
                  "route of elimination. Plasma levels therefore rise faster "
                  "than the dose, and the substrate + inhibitor rows below "
                  "describe a moving target rather than a fixed rate.",
            "fr": "La paroxétine est un inhibiteur suicide (dépendant du "
                  "mécanisme) du CYP2D6, l'isoforme qui l'élimine : elle "
                  "inactive sa propre voie d'élimination. Les concentrations "
                  "plasmatiques augmentent donc plus vite que la dose, et les "
                  "lignes substrat + inhibiteur ci-dessous décrivent une cible "
                  "mouvante plutôt qu'un débit fixe.",
        },
        "sources": [
            {
                "corpus": "wikipedia_pharm",
                "page": "paroxetine",
                "quote": "Paroxetine is a mechanism-based inhibitor of CYP2D6",
                "provenance": "verified",
                "llm": "opus",
            },
            {
                "corpus": "wikipedia_pharm",
                "page": "paroxetine",
                "quote": "It has an absolute bioavailability of about 50%, with "
                         "evidence of a saturable first pass effect",
                "provenance": "verified",
                "llm": "opus",
            },
        ],
    },
    {
        "id": "mdma_nonlinear_pk",
        "owner_kind": "drug",
        "owner": "mdma",
        "slot": "drug.metabolism",
        "display": "admonition",
        "tone": "caution",
        "title": {
            "en": "Non-linear pharmacokinetics",
            "fr": "Pharmacocinétique non linéaire",
        },
        "text": {
            "en": "MDMA inhibits the CYP2D6 that metabolises it "
                  "(autoinhibition), so clearance saturates as the dose rises: "
                  "kinetics become zero-order, and repeated doses give "
                  "disproportionately higher, longer-lasting levels. The "
                  "substrate row below is the mechanism, not the rate.",
            "fr": "La MDMA inhibe le CYP2D6 qui la métabolise "
                  "(auto-inhibition) : la clairance sature quand la dose "
                  "augmente, la cinétique devient d'ordre zéro et des prises "
                  "répétées donnent des concentrations disproportionnellement "
                  "plus élevées et plus durables. La ligne substrat ci-dessous "
                  "donne le mécanisme, pas le débit.",
        },
        "sources": [
            {
                "corpus": "wikipedia_pharm",
                "page": "mdma",
                "quote": "Complex, nonlinear pharmacokinetics arise via "
                         "autoinhibition of CYP2D6 and CYP2D8, resulting in "
                         "zeroth order kinetics at higher doses. It is thought "
                         "that this can result in sustained and higher "
                         "concentrations of MDMA if the user takes consecutive "
                         "doses of the drug.",
                "provenance": "verified",
                "llm": "opus",
            },
        ],
    },
]


def _addon_record(addon: dict[str, Any]) -> dict[str, Any]:
    """Validate one authored addon and return its emitted record.

    Fails loudly (like every other record builder here) on an unknown slot /
    display / tone, on an anchor kind that disagrees with the slot's own kind, or
    on a source citing an unknown corpus. Whether the anchor *id* exists is
    checked in ``generate_data.build_records``, which is where the id pools are.
    """
    aid = addon.get("id")
    what = f"Addon {aid!r}"
    slot = addon.get("slot")
    if slot not in ADDON_SLOTS:
        raise KeyError(f"{what} has unknown slot {slot!r} "
                       f"(valid: {sorted(ADDON_SLOTS)})")
    owner_kind = addon.get("owner_kind")
    if owner_kind != ADDON_SLOTS[slot]:
        raise KeyError(f"{what} anchors a {owner_kind!r} node in slot {slot!r}, "
                       f"which is a {ADDON_SLOTS[slot]!r} panel slot")
    display = addon.get("display")
    if display not in ADDON_DISPLAYS:
        raise KeyError(f"{what} has unknown display {display!r} "
                       f"(valid: {sorted(ADDON_DISPLAYS)})")
    tone = addon.get("tone")
    if tone not in ADDON_TONES:
        raise KeyError(f"{what} has unknown tone {tone!r} "
                       f"(valid: {sorted(ADDON_TONES)})")
    if not addon.get("owner"):
        raise KeyError(f"{what} has no owner id")
    # The title is optional (a bare note needs no heading); the text is the claim,
    # so it is not.
    if not addon.get("text"):
        raise KeyError(f"{what} has no text (the claim it states)")
    record: dict[str, Any] = {
        "id": aid,
        "owner_kind": owner_kind,
        "owner": addon["owner"],
        "slot": slot,
        "display": display,
        "tone": tone,
        "text": addon["text"],
        "sources": _quote_sources(addon.get("sources"), what),
    }
    if addon.get("title"):
        record["title"] = addon["title"]
    return record


def build_addons() -> list[dict[str, Any]]:
    """Every authored addon as an emitted record, ids checked unique."""
    records = [_addon_record(a) for a in ADDONS]
    seen: set[str] = set()
    for rec in records:
        if rec["id"] in seen:
            raise KeyError(f"Duplicate addon id {rec['id']!r}")
        seen.add(rec["id"])
    return records
