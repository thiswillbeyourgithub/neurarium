"""How a drug leaves the body: route, share excreted unchanged, renal process, urine pH.

Node kind ``drug_excretion`` (BETA): ONE node per (drug, aspect, value), read off the
same stored pharmacokinetics prose the T½ / Tmax passes read (Wikipedia #9, Stahl #1,
DailyMed #14, BDPM #16). Four aspects, each a closed vocabulary:

* ``route``: ``renal`` (urine) or ``fecal`` (faeces / bile), e.g. lithium ``renal``;
* ``unchanged``: ``urine``, the parent drug excreted unchanged in urine, its share in
  ``amount`` when the source gives one (amisulpride "50 %");
* ``renal_process``: ``filtration`` / ``tubular_secretion`` / ``tubular_reabsorption``,
  the nephron step the source names (lithium is filtered then ~80 % reabsorbed);
* ``urine_ph``: ``dependent`` (excretion varies with urine pH), ``acidic_faster`` or
  ``alkaline_faster`` (which way it goes: amphetamine leaves faster in acidic urine).

``amount`` is an optional verbatim span of the node's quote holding a figure
("80%", "less than 1%"), never a parsed number: sources mix doses, routes and time
windows ("50 % of an I.V. dose within 24 h"), and the span keeps the qualifier with it.

Every value carries a pattern its quote must contain (``attests``, like
``workup.TESTS``), so the applier (``tools/sourcing/apply_excretion.py``) refuses a pick
whose sentence does not itself say it, and the fetcher
(``tools/fetch/fetch_excretion.py``) offers lines on the same patterns. Labels are
authored bilingually inline and emitted into meta ``excretion_aspects`` (aspect ->
``{en, fr, values: {value: {en, fr}}}``). Data lives in the committed
``tools/generated_cache/excretion.json`` (applier-written, never hand-edited).

Built with the help of Claude Code.
"""
from __future__ import annotations

from typing import Any, Callable

from . import caches
from .caches import attests, labels

CACHE = caches.CACHE_DIR / "excretion.json"

# Aspect -> {en, fr, values}; value -> {en, fr, attests}. Order is display order.
# Patterns are case-insensitive and bilingual (EN corpora + the French RCP 5.2).
ASPECTS: dict[str, dict[str, Any]] = {
    "route": {"en": "route", "fr": "voie", "values": {
        "renal": {"en": "urine (kidneys)", "fr": "urines (reins)",
                  "attests": r"urin|kidney|renal|\breins?\b|r[ée]nal"},
        "fecal": {"en": "faeces (bile)", "fr": "selles (bile)",
                  "attests": r"f(?:a|ae)?ec(?:es|al)|stool|\bbil(?:e|iary)\b|"
                             r"selles|f[ée]c[ae]|biliaire"},
    }},
    "unchanged": {"en": "excreted unchanged", "fr": "excrété inchangé", "values": {
        "urine": {"en": "in urine", "fr": "dans les urines",
                  "attests": r"unchanged|unmetaboli[sz]ed|unaltered|\bintact\b|"
                             r"parent (?:drug|compound)|inchang|non m[ée]tabolis"},
    }},
    "renal_process": {"en": "kidney handling", "fr": "prise en charge rénale", "values": {
        "filtration": {"en": "glomerular filtration", "fr": "filtration glomérulaire",
                       "attests": r"filtrat|glom[ée]rul"},
        "tubular_secretion": {"en": "tubular secretion", "fr": "sécrétion tubulaire",
                              "attests": r"secret|s[ée]cr[ée]t"},
        "tubular_reabsorption": {"en": "tubular reabsorption",
                                 "fr": "réabsorption tubulaire",
                                 "attests": r"reabsor|r[ée]absor"},
    }},
    "urine_ph": {"en": "urine pH", "fr": "pH urinaire", "values": {
        "dependent": {"en": "excretion depends on it", "fr": "l'excrétion en dépend",
                      "attests": r"\bpH\b"},
        "acidic_faster": {"en": "faster in acidic urine", "fr": "plus rapide en urine acide",
                          "attests": r"acid"},
        "alkaline_faster": {"en": "faster in alkaline urine",
                            "fr": "plus rapide en urine alcaline",
                            "attests": r"alkalin|alcalin|\bbasic\b|basique"},
    }},
}


def values(aspect: str) -> dict[str, dict[str, str]]:
    """The value vocabulary of ``aspect`` (``{}`` for an unknown aspect)."""
    return (ASPECTS.get(aspect) or {}).get("values") or {}


def says(aspect: str, value: str, *texts: str | None) -> bool:
    """Whether any of ``texts`` names ``value`` of ``aspect`` (its ``attests`` pattern)."""
    return attests(values(aspect), value, *texts)


def named(text: str) -> list[str]:
    """Every ``aspect:value`` ``text`` names, in vocabulary order."""
    return [f"{a}:{v}" for a in ASPECTS for v in values(a) if says(a, v, text)]


def meta_labels() -> dict[str, dict[str, Any]]:
    """The ``excretion_aspects`` meta map (patterns stay author-side)."""
    return {a: {"en": e["en"], "fr": e["fr"], "values": labels(e["values"])}
            for a, e in ASPECTS.items()}


def fold(text: str) -> str:
    """Case, whitespace and apostrophe folding, for the verbatim-span checks."""
    return " ".join(text.replace("’", "'").casefold().split())


def is_span(span: str | None, quote: str | None) -> bool:
    """Whether ``span`` is a non-trivial verbatim span of ``quote`` (folded)."""
    s = fold(span or "")
    return len(s) >= 2 and s in fold(quote or "")


_DATA = caches.load(CACHE.name, required=False)


def drug_excretion(drug_id: str, quote_sources: Callable, data: dict | None = None
                   ) -> dict[str, Any]:
    """The emitted ``excretion`` field of one drug: ``[{aspect, value, amount?,
    sources}]`` in vocabulary order, or ``{}``. ``quote_sources`` is
    ``provenance._quote_sources`` (passed in, as for workup.py). Validates against the
    vocabularies so a hand edit of the cache fails the build instead of shipping an
    unlabelled row, and ``amount`` against its quotes so it stays a verbatim span."""
    rows = ((data if data is not None else _DATA).get("drugs") or {}).get(drug_id) or []
    out, seen = [], set()
    for r in rows:
        aspect, value = r.get("aspect"), r.get("value")
        what = f"Drug {drug_id!r} excretion {aspect!r}:{value!r}"
        if value not in values(aspect):
            raise KeyError(f"{what}: not in excretion.ASPECTS")
        if (aspect, value) in seen:
            raise ValueError(f"{what}: duplicate (aspect, value) node")
        seen.add((aspect, value))
        if not r.get("sources"):
            raise ValueError(f"{what}: no source")
        row = {"aspect": aspect, "value": value}
        if r.get("amount") is not None:
            if not any(is_span(r["amount"], s.get("quote")) for s in r["sources"]):
                raise ValueError(f"{what}: amount {r['amount']!r} is not a span of its quotes")
            row["amount"] = r["amount"]
        row["sources"] = quote_sources(r["sources"], what)
        out.append(row)
    order = {k: i for i, k in enumerate(f"{a}:{v}" for a in ASPECTS for v in values(a))}
    out.sort(key=lambda r: order[f"{r['aspect']}:{r['value']}"])
    return {"excretion": out} if out else {}
