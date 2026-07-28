"""Why a `verified` binding claim still deserves doubt (the ``uncertainty`` bullets).

A `verified` grade only ever meant "this sentence really is on that page". It never meant
"this sentence is *about this drug*", and the quote-quality audit
(``docs/SOURCING_GAPS.md``) found one shape where the difference matters: Stahl's **How
Drug Causes Side Effects** block prints mechanism-to-side-effect rules whose grammatical
subject is the *mechanism*, not the drug, so nothing in the sentence says this drug has
the action:

    "Blockade of alpha adrenergic 1 receptors may explain dizziness, sedation, and
     hypotension"

Those claims were kept, on evidence rather than convenience (the lines are printed
selectively, only on monographs that genuinely carry the property, and half the bindings
carry an independent measured Ki). But a flat green check overstates them, so they carry
an **uncertain** badge instead: same source, same quote, plus the reasons to doubt it,
each reason itself a badged, quote-gated claim.

**No prose is stored.** A bullet is a ``kind`` from :data:`UNCERTAINTY_REASONS` plus
optional slot ``args``; the viewer builds the sentence from an i18n key, so both languages
live in ``public/js/i18n.js`` with every other display string and the 89 flagged bindings
do not carry 89 copies of the same three sentences.

**Every bullet is itself sourced, or says so.** A bullet either resolves a real
quote-gated source (``source: "own_quote"`` reuses the binding's own quote,
``source: "ki"`` its measured affinity) or declares ``absence: True``, which renders the
red NOSOURCE pill and reads as "the corpus does not say this". Forgetting a source is an
error, not a silent blank (:func:`_uncertainty_bullet` raises, and ``check_data.py``
family 5 re-checks it on the emitted data).

Only the *judgement* kinds are authored below. The Ki bullet is appended automatically
from the binding's own ``ki``, so it can never drift from the affinity actually shipped.
"""
from __future__ import annotations

from typing import Any

# The closed vocabulary of reason kinds. Each entry declares where its source comes from:
#
# - ``own_quote``: the binding's own quote source (the sentence being doubted). The bullet
#   is a reading OF that quote, so it cites it and inherits its grade.
# - ``ki``:        the binding's measured-affinity source (PDSP / GtoPdb / Wikipedia).
# - ``None``:      an absence-of-evidence bullet; it MUST set ``absence`` so the viewer
#   renders NOSOURCE and the gate knows the blank is deliberate.
#
# ``args`` lists the slots the i18n sentence takes, so a typo in an authored/derived arg
# is caught here rather than surfacing as a literal "{ki}" in the panel. Adding a kind
# means adding its ``uncertain.<kind>`` string to BOTH i18n catalogues.
UNCERTAINTY_REASONS: dict[str, dict[str, Any]] = {
    # "The source sentence explains a side effect; its subject is the mechanism, not
    # the drug." The finding itself, cited on the very sentence it is about.
    "side_effect_rule": {"source": "own_quote", "absence": False, "args": ()},
    # "The same sentence is printed on N other monographs." Not damning on its own
    # (Stahl writes true class-wide lines constantly), but it is what the reader needs
    # in order to weigh the one above.
    "class_wide": {"source": "own_quote", "absence": False, "args": ("n",)},
    # "A measured binding affinity backs it independently of the sentence."
    "measured_ki": {"source": "ki", "absence": False, "args": ("ki", "n")},
    # ... and its absence twin.
    "no_measured_ki": {"source": None, "absence": True, "args": ()},
    # "The corpus never lists this action among the drug's mechanisms of action."
    "not_a_mechanism": {"source": None, "absence": True, "args": ()},
}


def _claim(drug: str, page: int, targets: tuple[str, ...],
           reasons: tuple[str, ...] = ("side_effect_rule", "not_a_mechanism"),
           ) -> dict[str, Any]:
    return {"drug": drug, "page": page, "targets": targets, "reasons": reasons}


# The flagged claims, one record per (drug, Stahl page, target set): 33 editorial
# decisions carrying 89 bindings. Counted at the claim level on purpose, since one
# sentence sources every subtype it mentions (m1-m5, alpha1a/b/d).
#
# `targets` must match bindings the drug actually has (``_uncertainty`` raises otherwise,
# mirroring the METABOLITE_ENZYME_QUOTES rule), so a later data edit cannot silently drop
# a flag. `page` picks which of the binding's sources the ``own_quote`` bullets cite.
#
# Every one is the same shape: a mechanism-noun-phrase sentence in the side-effect block,
# and an action Stahl's own "How the Drug Works" list never states. The `class_wide` and
# `measured_ki` bullets are derived, not authored.
_TCA_MUSCARINIC = ("m1", "m2", "m3", "m4", "m5")
_ALPHA1 = ("alpha1a", "alpha1b", "alpha1d")

UNCERTAIN_BINDING_CLAIMS: tuple[dict[str, Any], ...] = (
    _claim("amitriptyline", 40, _ALPHA1),
    _claim("amoxapine", 48, _ALPHA1),
    _claim("clomipramine", 180, _TCA_MUSCARINIC),
    _claim("clomipramine", 180, ("h1",)),
    _claim("clomipramine", 180, _ALPHA1),
    # The user-facing example: Stahl names M3 only to explain a pancreatic side effect,
    # and never lists a muscarinic action among clozapine's mechanisms. The measured Ki
    # is what keeps the binding rather than dropping it.
    _claim("clozapine", 207, ("m3",)),
    _claim("cyamemazine", 216, _TCA_MUSCARINIC),
    _claim("cyamemazine", 216, ("h1",)),
    _claim("desipramine", 226, ("h1",)),
    _claim("desipramine", 226, _ALPHA1),
    _claim("dothiepin", 278, _ALPHA1),
    _claim("doxepin", 284, _ALPHA1),
    _claim("imipramine", 396, _TCA_MUSCARINIC),
    _claim("imipramine", 396, ("h1",)),
    _claim("imipramine", 396, _ALPHA1),
    _claim("lofepramine", 450, _TCA_MUSCARINIC),
    _claim("lofepramine", 450, ("h1",)),
    _claim("lofepramine", 450, _ALPHA1),
    _claim("maprotiline", 496, _TCA_MUSCARINIC),
    _claim("maprotiline", 496, ("h1",)),
    _claim("maprotiline", 496, _ALPHA1),
    _claim("nefazodone", 578, _ALPHA1),
    _claim("nortriptyline", 584, _TCA_MUSCARINIC),
    _claim("nortriptyline", 584, ("h1",)),
    _claim("nortriptyline", 584, _ALPHA1),
    _claim("phenterminetopiramate", 660, ("carbonic_anhydrase",)),
    _claim("protriptyline", 700, ("h1",)),
    _claim("protriptyline", 700, _ALPHA1),
    _claim("trazodone", 840, ("h1",)),
    _claim("trazodone", 840, _ALPHA1),
    _claim("trimipramine", 864, _TCA_MUSCARINIC),
    _claim("trimipramine", 864, ("h1",)),
    _claim("trimipramine", 864, _ALPHA1),
)


def _uncertainty_bullet(kind: str, *, what: str, binding: dict[str, Any],
                        page: Any, args: dict[str, Any] | None = None
                        ) -> dict[str, Any]:
    """One ``uncertainty`` bullet: a reason kind, its slot args, and its own source.

    Where the source comes from is declared by the kind, not by the author (see
    :data:`UNCERTAINTY_REASONS`), so a bullet cannot cite the wrong thing:

    * ``own_quote`` reuses the binding's own source for ``page`` (the very sentence the
      bullet is a reading of), so the bullet inherits its grade and its quote gate;
    * ``ki`` reuses the binding's measured-affinity source;
    * an ``absence`` kind carries no source on purpose and renders NOSOURCE.

    Raises when a non-absence kind resolves to nothing: a bullet with a silent blank
    would read exactly like an absence bullet while meaning "we forgot".
    """
    spec = UNCERTAINTY_REASONS.get(kind)
    if spec is None:
        raise KeyError(f"{what} uncertainty bullet {kind!r} is not an "
                       f"UNCERTAINTY_REASONS kind (one of "
                       f"{sorted(UNCERTAINTY_REASONS)})")
    args = args or {}
    missing = [a for a in spec["args"] if a not in args]
    if missing:
        raise ValueError(f"{what} uncertainty bullet {kind!r} is missing "
                         f"arg(s) {missing} (the i18n sentence has those slots)")
    out: dict[str, Any] = {"kind": kind}
    if args:
        out["args"] = args
    if spec["absence"]:
        out["absence"] = True
        return out
    if spec["source"] == "own_quote":
        src = next((s for s in binding.get("sources", []) if s.get("page") == page), None)
    elif spec["source"] == "ki":
        src = (binding.get("ki") or {}).get("source")
    else:
        src = None
    if not src:
        raise ValueError(
            f"{what} uncertainty bullet {kind!r} resolves to no source "
            f"(it cites {spec['source']!r}, which this binding does not carry). "
            f"Every bullet must be sourced or declare absence=True.")
    out["sources"] = [dict(src)]
    return out


def apply_binding_uncertainty(drugs: list[dict[str, Any]]) -> None:
    """Attach the ``uncertainty`` bullets to the flagged bindings, in place.

    Run as a post-pass over the emitted drugs rather than inside ``_binding_record``,
    because one bullet (``class_wide``) is a count *across* drugs: the same Stahl
    sentence printed on a dozen monographs is exactly the context a reader needs in
    order to weigh it, and no single binding can see that.

    Raises when a claim names a drug or a (drug, target) binding that does not exist,
    mirroring the ``METABOLITE_ENZYME_QUOTES`` rule: a later data edit must not be able
    to silently drop a flag and quietly restore a green check.
    """
    by_id = {d["id"]: d for d in drugs}
    # How many drugs each flagged sentence is printed on. Keyed by the quote text,
    # since that is what "the same sentence" means to a reader.
    spread: dict[str, set[str]] = {}
    for claim in UNCERTAIN_BINDING_CLAIMS:
        drug = by_id.get(claim["drug"])
        if drug is None:
            raise KeyError(f"UNCERTAIN_BINDING_CLAIMS names unknown drug "
                           f"{claim['drug']!r}")
        for b in drug.get("bindings", []):
            if b["target"] not in claim["targets"]:
                continue
            for s in b.get("sources", []):
                if s.get("page") == claim["page"] and s.get("quote"):
                    spread.setdefault(s["quote"], set()).add(drug["id"])

    for claim in UNCERTAIN_BINDING_CLAIMS:
        drug = by_id[claim["drug"]]
        found = {b["target"] for b in drug.get("bindings", [])}
        missing = [t for t in claim["targets"] if t not in found]
        if missing:
            raise KeyError(
                f"UNCERTAIN_BINDING_CLAIMS for drug {claim['drug']!r} p.{claim['page']} "
                f"names target(s) {missing} the drug has no binding for")
        for b in drug["bindings"]:
            if b["target"] not in claim["targets"]:
                continue
            what = f"Drug {drug['id']!r} binding {b['target']!r}"
            bullets = [_uncertainty_bullet(kind, what=what, binding=b,
                                           page=claim["page"])
                       for kind in claim["reasons"]]
            quote = next((s.get("quote") for s in b.get("sources", [])
                          if s.get("page") == claim["page"]), None)
            n_others = len(spread.get(quote or "", set())) - 1
            if n_others > 0:
                bullets.append(_uncertainty_bullet(
                    "class_wide", what=what, binding=b, page=claim["page"],
                    args={"n": n_others}))
            # The affinity bullet is derived, never authored, so it cannot drift from
            # the Ki actually shipped: it says what the measurement is, or that there
            # is none (which is itself a reason to doubt).
            ki = b.get("ki")
            if ki:
                bullets.append(_uncertainty_bullet(
                    "measured_ki", what=what, binding=b, page=claim["page"],
                    args={"ki": ki["median"],
                          "n": int(ki.get("n_human", 0)) + int(ki.get("n_nonhuman", 0))}))
            else:
                bullets.append(_uncertainty_bullet(
                    "no_measured_ki", what=what, binding=b, page=claim["page"]))
            # Evidence first, absences last: the list reads as "here is what the source
            # does say ... but here is what it never says", which is the shape of the
            # doubt. Stable within each half (authored order, then the derived bullets).
            bullets.sort(key=lambda bl: bool(bl.get("absence")))
            b["uncertainty"] = bullets
