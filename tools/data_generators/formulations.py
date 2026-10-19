"""Drug formulations: one molecule, several products (release type sub-nodes).

A drug is ONE molecule: its bindings, enzymes, metabolites and TDM ranges are a property
of the molecule and stay on it. What depends on the *product* is how fast the molecule
reaches the blood and which name it is sold under: Seroquel XR peaks around 6 h where the
quetiapine tablet peaks at 1.5 h, and Risperdal Consta is a fortnightly depot injection,
not a tablet. So a drug carries an optional ``formulations[]``, one per release type a
source names, each holding the brands, time-to-peak and half-life that were measured or
sold for THAT product (see ``docs/DRUGS.md`` "Formulations"):

    {release, release_sources, brands?, tmax?, tmax_sources?, half_life?, half_life_sources?}

``release`` is an id from the closed :data:`RELEASES` vocabulary, and the release type
is itself a sourced claim (node kind ``drug_formulations``, ONE node per formulation,
graded by ``release_sources``). A brand / Tmax / T½ whose source names no formulation
stays at molecule level: nothing here is ever guessed.

Every release id carries the patterns a quote must contain to attest it (``abbr`` is
matched case-sensitively, so the French article "La" never reads as Ritalin LA's "LA";
``words`` / ``fr`` case-insensitively), so the applier
(``tools/sourcing/apply_formulations.py``) can refuse a release a quote does not state:
code picks the release only off structured fields (a brand's own suffix, a DailyMed
label title, a BDPM product denomination), and an LLM pick off prose must still name a
release its sentence attests.

Labels are authored bilingually inline (like ``history.py``) and emitted into meta as
``drug_releases``.

Built with the help of Claude Code.
"""

from __future__ import annotations

import re
from typing import Any

from .provenance import _drug_brands, _hours_value, _quote_sources

# Release id -> {en, fr, abbr, words, fr_words}, in display order. "Modified release"
# is deliberately no pattern: it covers delayed AND extended release, so reading it as
# either would be a guess.
RELEASES: dict[str, dict[str, Any]] = {
    "ir": {
        "en": "Immediate release", "fr": "Libération immédiate",
        "abbr": (r"\bIR\b",),
        "words": (r"immediate[- ]release", r"\bconventional\b"),
        "fr_words": (r"lib[ée]ration imm[ée]diate",),
    },
    "xr": {
        "en": "Extended release", "fr": "Libération prolongée",
        "abbr": (r"\b(?:XR|XL|SR|CR|ER|LA|CD|LP)\b",),
        "words": (r"(?:extended|sustained|controlled|prolonged|slow)[- ]release",),
        "fr_words": (r"lib[ée]ration prolong",),
    },
    "dr": {
        "en": "Delayed release (gastro-resistant)", "fr": "Gastro-résistant",
        "abbr": (r"\bDR\b",),
        "words": (r"delayed[- ]release", r"enteric[- ]coated", r"gastro-?resistant"),
        "fr_words": (r"gastro-?r[ée]sistant",),
    },
    "odt": {
        "en": "Orally disintegrating", "fr": "Orodispersible",
        "abbr": (r"\bODT\b",),
        "words": (r"orally disintegrating", r"oral disintegrating"),
        "fr_words": (r"orodispersible", r"lyophilisat oral"),
    },
    "sublingual": {
        "en": "Sublingual / buccal", "fr": "Sublinguale / buccale",
        "abbr": (), "words": (r"sublingual", r"\bbuccal\b", r"transmucosal"),
        "fr_words": (r"sublingual", r"\bbuccale?s?\b", r"gingival"),
    },
    "nasal": {
        "en": "Nasal", "fr": "Nasale",
        "abbr": (), "words": (r"\b(?:intra)?nasal\b",), "fr_words": (r"\bnasale?s?\b",),
    },
    "transdermal": {
        "en": "Transdermal patch", "fr": "Dispositif transdermique",
        "abbr": (), "words": (r"transdermal", r"\bpatch(?:es)?\b"),
        "fr_words": (r"transdermique",),
    },
    "injection": {
        "en": "Injection", "fr": "Injectable",
        "abbr": (r"\bIV\b", r"\bIM\b"),
        "words": (r"\binjection\b", r"\binjectable\b", r"intravenous", r"intramuscular",
                  r"subcutaneous", r"\binfusion\b"),
        "fr_words": (r"injectable", r"\bperfusion\b", r"intraveineu"),
    },
    "depot": {
        "en": "Long-acting injection (depot)", "fr": "Injectable à action prolongée (dépôt)",
        "abbr": (r"\bLAI\b",),
        # A depot ester (palmitate, decanoate, enanthate) is a depot by definition.
        "words": (r"\bdepot\b", r"long[- ]acting injectable",
                  r"extended[- ]release injectable",
                  r"injection(?:, (?:suspension|powder, for suspension))?, extended release",
                  r"\bpalmitate\b", r"\bdecanoate\b", r"\benanthate\b"),
        "fr_words": (r"\bd[ée]p[oô]t\b",
                     r"injectable[^,]*lib[ée]ration prolong[ée]e",
                     r"lib[ée]ration prolong[ée]e[^,]*injectable"),
    },
}

# Which release wins when one string names several (see :func:`classify`): the more
# specific delivery beats the generic one, so "Adzenys XR-ODT" (an extended-release
# orally disintegrating tablet) reads as xr, its kinetics, and a depot (an
# extended-release injectable) never reads as xr or as a plain injection.
PRECEDENCE = ("depot", "transdermal", "nasal", "sublingual", "injection", "xr", "dr",
              "odt", "ir")

_PATTERNS: dict[str, re.Pattern] = {}
for _rid in PRECEDENCE:
    _r = RELEASES[_rid]
    _parts = [f"(?-i:{a})" for a in _r["abbr"]] + list(_r["words"]) + list(_r["fr_words"])
    _PATTERNS[_rid] = re.compile("|".join(_parts), re.IGNORECASE)

# Conventional oral dosage forms. A product register names a modified release in the
# form itself (FDA SPL "TABLET, EXTENDED RELEASE"; EDQM standard terms "comprimé à
# libération prolongée"), so an oral product whose form is one of these and names no
# other release IS immediate release: a structured-field read, not an inference from
# a missing word in prose. Used only on a DailyMed title / BDPM denomination.
IR_FORMS_EN = re.compile(
    r"\b(?:TABLET|CAPSULE|SYRUP|ELIXIR|(?:ORAL )?SOLUTION, ORAL|ORAL SOLUTION|"
    r"ORAL SUSPENSION|SUSPENSION, ORAL)\b", re.IGNORECASE)
IR_FORMS_FR = re.compile(
    r"\b(?:comprim[ée]s?|g[ée]lules?|capsules?|solution buvable|suspension buvable|"
    r"sirop|gouttes buvables|granul[ée]s)\b", re.IGNORECASE)

# The FDA established name of an extended-release product leads with the word
# ("EXTENDED PHENYTOIN SODIUM CAPSULE"); uppercase only, as a title writes it.
_EXTENDED_NAME = re.compile(r"\s*EXTENDED\b")
# A label covering several products (a kit, a title naming two products) says nothing
# about which one a sentence of it describes.
_KIT = re.compile(r"\bKIT\b", re.IGNORECASE)


def releases_in(text: str) -> list[str]:
    """Every release id ``text`` attests, in :data:`PRECEDENCE` order."""
    return [rid for rid, pat in _PATTERNS.items() if pat.search(text or "")]


def attests(release: str, text: str) -> bool:
    """Whether ``text`` names ``release`` (the applier's gate on an LLM pick)."""
    return bool(_PATTERNS[release].search(text or ""))


def classify(text: str) -> str | None:
    """The one release a structured string names, by precedence, or None.

    >>> classify("Seroquel XR"), classify("Adzenys XR-ODT"), classify("Seroquel")
    ('xr', 'xr', None)
    >>> classify("Saphris (sublingual)"), classify("La résorption est rapide")
    ('sublingual', None)
    """
    found = releases_in(text)
    return found[0] if found else None


def classify_label_title(title: str, routes=()) -> str | None:
    """The release of a DailyMed SPL title ("QUETIAPINE TABLET, EXTENDED RELEASE [..]").

    The labeler in brackets is dropped (a company name is not a dosage form). A kit
    covers several products, so it is never classified. ``routes`` are the SPL's own
    route-of-administration codes (``fetch_dailymed.spl_routes``): the title names a
    dosage form, not a route, so a generic "ASENAPINE TABLET" is a sublingual tablet,
    and a tablet is read as immediate release only when nothing says it is not
    swallowed. An "EXTENDED <name>" title is the FDA established name of an
    extended-release product ("Extended Phenytoin Sodium Capsules").

    >>> classify_label_title("ALPRAZOLAM TABLET [ACTAVIS PHARMA, INC.]")
    'ir'
    >>> classify_label_title("PALIPERIDONE TABLET, EXTENDED RELEASE [AJANTA PHARMA USA INC.]")
    'xr'
    >>> classify_label_title("VALPROATE SODIUM INJECTION, SOLUTION [SAGENT]")
    'injection'
    >>> classify_label_title("CANNABIDIOL SOLUTION [X]") is None
    True
    >>> classify_label_title("ASENAPINE TABLET [ALEMBIC]", {"SUBLINGUAL"})
    'sublingual'
    >>> classify_label_title("EXTENDED PHENYTOIN SODIUM (PHENYTOIN SODIUM) CAPSULE [X]")
    'xr'
    """
    body = re.sub(r"\[[^\]]*\]", " ", title or "")
    if _KIT.search(body):
        return None
    named = classify(body)
    if named:
        return named
    if _EXTENDED_NAME.match(body):
        return "xr"
    routes = {r.upper() for r in routes}
    if routes - {"ORAL"}:
        # One non-oral route names the release; a label mixing routes is not one product.
        return classify(next(iter(routes))) if len(routes) == 1 else None
    return "ir" if IR_FORMS_EN.search(body) else None


def classify_denomination(denomination: str, route: str) -> str | None:
    """The release of a BDPM product, from its denomination + route column.

    >>> classify_denomination("SEROQUEL LP 50 mg, comprimé à libération prolongée", "orale")
    'xr'
    >>> classify_denomination("OXYNORM 5 mg, gélule", "orale")
    'ir'
    >>> classify_denomination("AOTAL 333 mg, comprimé enrobé gastro-résistant", "orale")
    'dr'
    >>> classify_denomination("GENCEBOK 10 mg/mL, solution pour perfusion",
    ...                        "intraveineuse;orale")
    'injection'
    """
    named = classify(denomination)
    if named:
        return named
    routes = [r.strip().lower() for r in (route or "").split(";") if r.strip()]
    if routes == ["orale"] and IR_FORMS_FR.search(denomination or ""):
        return "ir"
    return None


def labels() -> dict[str, dict[str, str]]:
    """The ``{id: {en, fr}}`` label map emitted into meta, in display order."""
    return {k: {"en": v["en"], "fr": v["fr"]} for k, v in RELEASES.items()}


def placed(drug: dict[str, Any], field: str) -> list[Any]:
    """Every ``field`` value ``apply_formulations.py`` already moved onto a formulation.

    ``field`` is ``"tmax"`` / ``"half_life"`` (one value per formulation holding one) or
    ``"brands"`` (flattened). Every molecule-level applier of a relocatable claim asks
    this before writing, so a re-run leaves a placed claim where it sits instead of
    re-adding it to the molecule (``tools/tests/test_applier_fixpoint.py`` guards it):
    ``placed({"formulations": [{"release": "xr", "tmax": {"hours": 6}}]}, "tmax")``
    is ``[{"hours": 6}]``.
    """
    out: list[Any] = []
    for f in drug.get("formulations") or []:
        v = f.get(field)
        if v:
            out.extend(v if isinstance(v, list) else [v])
    return out


def drug_formulations(drug: dict[str, Any]) -> dict[str, Any]:
    """The emitted ``formulations`` of one drug (validated), or ``{}``.

    Each release appears at most once per drug, carries at least one release source
    and at least one claim (a brand, a Tmax or a T½: a release with nothing under it
    says nothing about this dataset's numbers). A quote cited both at molecule level and
    under a formulation for the same field means a brand / Tmax / T½ applier re-ran
    after ``apply_formulations.py``: the build fails rather than publishing the claim
    twice. Emitted in :data:`RELEASES` order.
    """
    did = drug["id"]
    rows = drug.get("formulations") or []
    if not rows:
        return {}
    molecule_quotes = {
        field: {s.get("quote") for s in drug.get(f"{field}_sources") or []}
        for field in ("tmax", "half_life")}
    molecule_brands = {(b.get("name") or "").lower() for b in drug.get("brands") or []}
    seen: set[str] = set()
    out = []
    for f in rows:
        rel = f.get("release")
        what = f"Drug {did!r} formulation {rel!r}"
        if rel not in RELEASES:
            raise KeyError(f"{what}: release not in RELEASES ({list(RELEASES)})")
        if rel in seen:
            raise ValueError(f"{what}: release listed twice")
        seen.add(rel)
        srcs = _quote_sources(f.get("release_sources"), f"{what} release")
        if not srcs:
            raise ValueError(f"{what}: no release_sources (the release is a claim)")
        rec: dict[str, Any] = {"release": rel, "release_sources": srcs}
        brands = _drug_brands(did, f.get("brands"))
        for b in brands:
            if b["name"].lower() in molecule_brands:
                raise ValueError(f"{what}: brand {b['name']!r} is also at molecule level; "
                                 f"re-run tools/sourcing/apply_formulations.py")
        if brands:
            rec["brands"] = brands
        for field in ("tmax", "half_life"):
            if not f.get(field):
                continue
            rec[field] = _hours_value(f[field], what=what, field=field)
            fs = _quote_sources(f.get(f"{field}_sources"), f"{what} {field}")
            if any(s.get("quote") in molecule_quotes[field] for s in fs):
                raise ValueError(f"{what}: {field} quote is also cited at molecule level; "
                                 f"re-run tools/sourcing/apply_formulations.py")
            if fs:
                rec[f"{field}_sources"] = fs
        if not (brands or rec.get("tmax") or rec.get("half_life")):
            raise ValueError(f"{what}: carries no brand, tmax or half_life")
        out.append(rec)
    order = list(RELEASES)
    return {"formulations": sorted(out, key=lambda r: order.index(r["release"]))}
