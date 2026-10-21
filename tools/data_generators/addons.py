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

The four vocabularies below are closed and emitted into ``meta`` (``addon_slots``
/ ``addon_sections`` / ``addon_displays`` / ``addon_tones``), so the viewer reads the
hook registry from the data instead of hardcoding it and ``check_data.py`` can reject
an unknown slot.

**A slot only exists if the viewer actually calls it.** Every key of
:data:`ADDON_SLOTS` has a matching ``appendAddons(...)`` call site in
the viewer (``js/panel/views/*.js``, ``js/legend/anatomy.js``); adding a slot here without one would silently swallow the node.
"""

from __future__ import annotations

from typing import Any

from .provenance import _quote_sources

# Insertion points the viewer offers, slot -> the node kind whose panel it is in.
# The name is "<owner kind>.<where>", so a reader can see the anchor kind without
# looking it up. Each is one appendAddons() call in js/panel/views/*.js (or js/legend/anatomy.js); see the module
# docstring before adding one.
ADDON_SLOTS: dict[str, str] = {
    # Top of a drug panel, under the title/class and the combo warning: a caveat
    # about the drug as a whole (e.g. "does not cross the blood-brain barrier").
    "drug.top": "drug",
    # Inside the drug panel's Metabolism section, under its heading + caption and
    # above the first enzyme row: a caveat about how the drug is cleared, which
    # the per-isoform rows below cannot express (they state a role, not a curve).
    "drug.metabolism": "drug",
    # Inside the drug panel's pharmacokinetic timing block, under the Tmax / half-life
    # chips: a caveat about what those two numbers measure (e.g. a serum half-life
    # that the brain does not follow). Drawn whenever the drug has either duration,
    # unlike drug.metabolism, which needs enzyme rows to exist at all.
    "drug.timing": "drug",
    # Top of a receptor / non-receptor-target / structure panel, same role as
    # drug.top for the other three panel kinds.
    "receptor.top": "receptor",
    "target.top": "target",
    "structure.top": "structure",
    # Top of the Projections browse section, above its first heading: a caveat about
    # how the pathways as a whole are modeled. Its anchor is a SECTION, not a node
    # (see ADDON_SECTIONS): the claim is true of every arrow at once, so pinning it
    # to one pathway would misfile it and repeating it on each would be ~90 copies
    # of one sentence.
    "section.projections": "section",
    # Under the enzyme rows of EVERY drug panel's Metabolism section: a caveat about
    # what such a list is (a union of the routes some corpus happens to name, never
    # all of them). A SECTION anchor for the same reason as above: the claim is true
    # of all ~240 drugs at once, and `drug.metabolism` would need one copy each.
    "section.metabolism": "section",
}

# The sections an addon may anchor, section key -> its display label: a browse
# section, or a panel section every node of a kind repeats. This is the one owner
# kind that is not a node: the claim it carries is about a whole view (how its data
# is modeled), so there is no single datum to hang it on and no panel to open from
# it. Closed like every other vocabulary here, so a typo'd section is a generation
# error rather than a node that ships and never draws. A section addon's ``owner``
# is one of these keys.
ADDON_SECTIONS: dict[str, dict[str, str]] = {
    "projections": {"en": "Projections", "fr": "Voies de projection"},
    "metabolism": {"en": "Metabolism", "fr": "Métabolisme"},
}

# How an addon draws (dispatched by ADDON_RENDERERS in js/panel/addons.js): `admonition` is
# an always-open boxed callout; `collapsible` is the same box folded to its title
# line until clicked, for a background caveat that should not push the data it
# qualifies down the panel.
ADDON_DISPLAYS: tuple[str, ...] = ("admonition", "collapsible")

# Tone -> its glyph. The tone is the *claim's* register (a caution reads louder
# than a note), so it is data; the colour ramp each tone paints with is UI chrome
# and lives with the rest of the panel CSS in public/css/panel-drug.css.
ADDON_TONES: dict[str, str] = {
    "info": "ℹ",
    "caution": "⚠",
}

# What an addon's text is a claim ABOUT, which decides how it is graded.
# ``claim`` (the default) is knowledge about the brain or a drug, sourced and tallied
# like any other node. ``dataset`` is a statement about this dataset itself (how it
# models something, what it leaves out): no corpus could ever be cited for it, so it
# carries no sources by construction, draws a neutral "about this dataset" pill
# instead of the red NOSOURCE one, and stays out of the coverage tally (it is not
# knowledge, so counting it as missing would understate coverage and counting it as
# backed would overstate it). Emitted as ``meta.addon_bases``.
ADDON_BASES: tuple[str, ...] = ("claim", "dataset")

# ---------------------------------------------------------------------------
# The authored addons. Each is one sourceable claim, so it is graded like any
# other node: a `verified` source needs a page + a verbatim quote that
# check_data.py finds on that page.
# ---------------------------------------------------------------------------

ADDONS: list[dict[str, Any]] = [
    {
        # The half-life chip above is lithium's SERUM elimination half-life (Stahl);
        # the organ it acts on lets go of it more slowly. One small 7Li MRS study (two
        # healthy volunteers at steady state), so the text says how thin it is.
        "id": "lithium_brain_half_life",
        "owner_kind": "drug",
        "owner": "lithium",
        "slot": "drug.timing",
        "display": "admonition",
        "tone": "caution",
        "title": {
            "en": "The brain lets go of lithium more slowly",
            "fr": "Le cerveau élimine le lithium plus lentement",
        },
        "text": {
            "en": "Measured directly in the brain (7Li magnetic resonance "
                  "spectroscopy, a small study of two volunteers at steady state), "
                  "lithium's median half-life was 28 h there against 16 h in serum: "
                  "the brain clears it more slowly than the blood does.",
            "fr": "Mesurée directement dans le cerveau (spectroscopie par résonance "
                  "magnétique du 7Li, une petite étude de deux volontaires à "
                  "l'équilibre), la demi-vie médiane "
                  "du lithium y était de 28 h contre 16 h dans le sérum : le cerveau "
                  "l'élimine plus lentement que le sang.",
        },
        "sources": [
            {
                "corpus": "europepmc",
                "page": "7827213",
                "quote": "The median half-life for lithium was 28 hr in the brain, and "
                         "16 hr in serum.",
                "provenance": "verified",
            },
        ],
    },
    {
        # Same shape as lithium's: the chip above is haloperidol's PLASMA half-life
        # (Stahl, 12-38 h). Post-mortem tissue from 11 treated patients, so the text says
        # it is one small study and an estimate.
        "id": "haloperidol_brain_half_life",
        "owner_kind": "drug",
        "owner": "haloperidol",
        "slot": "drug.timing",
        "display": "admonition",
        "tone": "caution",
        "title": {
            "en": "The brain lets go of haloperidol far more slowly",
            "fr": "Le cerveau élimine l'halopéridol bien plus lentement",
        },
        "text": {
            "en": "Measured in post-mortem brain tissue of 11 treated patients (one "
                  "small study, a population estimate), haloperidol sat at 10 to 30 "
                  "times its optimal serum level and left the brain with a half-life of "
                  "6.8 days, against hours in the blood: its effects can outlast the "
                  "last dose by weeks.",
            "fr": "Mesuré dans le tissu cérébral post mortem de 11 patients traités (une "
                  "seule petite étude, une estimation de population), l'halopéridol y "
                  "était 10 à 30 fois plus concentré que le taux sérique optimal et en "
                  "sortait avec une demi-vie de 6,8 jours, contre quelques heures dans "
                  "le sang : ses effets peuvent durer des semaines après la dernière "
                  "prise.",
        },
        "sources": [
            {
                "corpus": "europepmc",
                "page": "10360127",
                "quote": "The elimination half-life from brain tissue was calculated to "
                         "be 6.8 days.",
                "provenance": "verified",
            },
            {
                "corpus": "europepmc",
                "page": "10360127",
                "quote": "Haloperidol concentrations in the human brain tissue were "
                         "10-30 times higher than optimal serum concentrations used in "
                         "the treatment of schizophrenia.",
                "provenance": "verified",
            },
            {
                "corpus": "europepmc",
                "page": "10360127",
                "quote": "Patients exposed to haloperidol cannot be considered to be free "
                         "of residual effects of the drug for a number of weeks after "
                         "withdrawal.",
                "provenance": "verified",
            },
        ],
    },
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
    {
        # The bilaterality caveat. Almost every pathway here is authored once and
        # mirrored across the midline (``mirror: true``), and no corpus states the
        # left-hand copy: an anatomy book describes a tract once. That makes the
        # second arrow a modelling assumption, and it is one claim about the whole
        # collection rather than ~90 separate ones, so it is stated once here
        # instead of flagging every mirrored projection. Deliberately **sourceless**
        # (a red NOSOURCE pill): the claim it makes is precisely that nothing backs
        # the mirroring, so citing something for it would contradict its own text.
        "id": "projection_bilaterality",
        "basis": "dataset",
        "owner_kind": "section",
        "owner": "projections",
        "slot": "section.projections",
        "display": "admonition",
        "tone": "info",
        "title": {
            "en": "Left/right symmetry is assumed",
            "fr": "La symétrie gauche/droite est supposée",
        },
        "text": {
            "en": "Nearly every pathway below is drawn twice, once in each "
                  "hemisphere, because we assume the left and right brain are wired "
                  "the same way. The sources describe a tract once, without saying "
                  "which side, so the dataset stores one arrow and the viewer mirrors "
                  "it onto the other hemisphere. No quote backs that mirrored copy, "
                  "and a real pathway can be stronger on one side (lateralization). "
                  "A mirrored pair counts as one node here, not two.",
            "fr": "Presque toutes les voies ci-dessous sont dessinées deux fois, une "
                  "dans chaque hémisphère, car nous supposons que les cerveaux gauche "
                  "et droit sont câblés de la même façon. Les sources décrivent un "
                  "faisceau une seule fois, sans préciser le côté : le jeu de données "
                  "stocke donc une flèche et l'affichage la reflète dans l'autre "
                  "hémisphère. Aucune citation n'appuie cette copie miroir, et une "
                  "voie réelle peut être plus marquée d'un côté (latéralisation). "
                  "Une paire miroir compte ici pour un seul nœud, pas deux.",
        },
    },
    {
        # The coverage caveat on every Enzymes list. An enzyme row is a sourced claim
        # ("Stahl says CYP2D6 clears this"), but the LIST is only the union of the
        # routes the corpora here happen to name, and nothing in the model ever
        # asserts it is complete: Stahl names the clinically actionable isoform, a
        # Wikipedia drugbox names whatever its editors wrote down, CPIC names the
        # gene it doses on. A missing isoform is therefore a silent hole, and it
        # propagates: the drug -> drug rows are derived from exactly this list, so an
        # unnamed shared route is an interaction the panel simply never draws (the
        # shape of the clomipramine/CYP2C19 gap, 3.93.1). Said once for the section
        # rather than per drug, like the bilaterality caveat above, and deliberately
        # **sourceless** (a red NOSOURCE pill) for the same reason: the claim is
        # about this dataset's coverage, so no corpus could be cited for it.
        "id": "enzyme_list_not_exhaustive",
        "basis": "dataset",
        "owner_kind": "section",
        "owner": "metabolism",
        "slot": "section.metabolism",
        "display": "collapsible",
        "tone": "info",
        "title": {
            "en": "Not the full set of routes",
            "fr": "Liste de voies non exhaustive",
        },
        "text": {
            "en": "Each row above is sourced on its own, but the list is not: it "
                  "holds the routes a source here happens to name, and no corpus "
                  "claims to name them all. An isoform missing from it means no "
                  "source stated that route, never that the drug avoids it. The "
                  "interactions below are derived from this same list, so an "
                  "unnamed shared route is simply an interaction nothing draws.",
            "fr": "Chaque ligne ci-dessus est sourcée individuellement, mais pas la "
                  "liste : elle contient les voies qu'une source citée ici nomme, et "
                  "aucun corpus ne prétend les nommer toutes. Une isoforme absente "
                  "signifie qu'aucune source n'a énoncé cette voie, jamais que la "
                  "substance l'évite. Les interactions ci-dessous sont dérivées de "
                  "cette même liste : une voie commune non nommée est donc une "
                  "interaction que rien n'affiche.",
        },
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
    basis = addon.get("basis", "claim")
    if basis not in ADDON_BASES:
        raise KeyError(f"{what} has unknown basis {basis!r} "
                       f"(valid: {list(ADDON_BASES)})")
    # A dataset statement is unsourceable by construction (see ADDON_BASES), so a
    # citation on one means it was misfiled as such.
    if basis == "dataset" and addon.get("sources"):
        raise KeyError(f"{what} is a dataset statement but cites sources")
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
        "basis": basis,
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
