"""The one serialization of every committed ``tools/generated_cache/*.json`` file.

A cache is often written by more than one script: its owning fetcher or applier, and
``sourcing/demote_quotes.py``, which rewrites every quote-bearing cache in place. When each
spelled its own ``json.dumps`` arguments the formats drifted apart (a re-run of the other
writer then rewrote every line, or dropped the trailing newline), so the format now lives
here, once per file name, and every writer goes through :func:`write`.

``tools/tests/test_cache_io.py`` holds the contract: every committed cache equals
``dumps(name, json.loads(its text))`` byte for byte, so a writer that drifts, or a new cache
nobody registered, fails the suite.

Example::

    >>> dumps("quote_recheck_flagged.json", [{"qid": "q1"}])
    '[\\n {\\n  "qid": "q1"\\n }\\n]'
    >>> dumps("location_sources.json", {"b": 1, "a": 2})
    '{\\n "a": 2,\\n "b": 1\\n}'

Stdlib only, so ``generate_data.py`` stays runnable offline.

Built with the help of Claude Code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lib.io_atomic import atomic_write_text

CACHE_DIR = Path(__file__).resolve().parent.parent / "generated_cache"


@dataclass(frozen=True)
class Format:
    """How one cache file is laid out.

    ``sort`` is ``"none"`` (insertion order), ``"all"`` (``sort_keys=True``) or ``"fields"``
    (top-level keys in insertion order, every value's keys sorted: a ledger whose entries
    keep the order they were added in, for a small diff, while each entry stays canonical).
    """
    indent: int | None = 1
    sort: str = "none"
    ensure_ascii: bool = False
    newline: bool = True

    def dumps(self, obj: Any) -> str:
        if self.sort == "fields":
            obj = {k: json.loads(json.dumps(v, sort_keys=True)) for k, v in obj.items()}
        elif self.sort not in ("none", "all"):
            raise ValueError(f"unknown sort mode {self.sort!r}")
        text = json.dumps(obj, indent=self.indent, sort_keys=self.sort == "all",
                          ensure_ascii=self.ensure_ascii)
        return text + ("\n" if self.newline else "")


def _one_line_per_key(obj: dict) -> str:
    """``{"k": v, ...}`` sorted by key, one compact ``"k": v`` pair per line (the Europe PMC
    species ledger: one PMID per line keeps its diff one line per paper)."""
    return "{\n" + ",\n".join(f"{json.dumps(k)}: {json.dumps(v)}"
                              for k, v in sorted(obj.items())) + "\n}\n"


DEFAULT = Format()
SORTED = Format(sort="all")
SORTED_NO_NL = Format(sort="all", newline=False)
SORTED_ASCII = Format(sort="all", ensure_ascii=True)
INDENT2 = Format(indent=2)

# File name -> its format. Every committed cache must be listed (the test enforces it).
FORMATS: dict[str, Format | Callable[[Any], str]] = {
    "agnp_tdm.json": DEFAULT,
    "bdpm_labels.json": SORTED,
    "bdpm_rcp_labels.json": SORTED,
    "binding_directions_judged.json": DEFAULT,
    "binding_directions_search_judged.json": DEFAULT,
    "binding_directions_search_worklist.json": DEFAULT,
    "binding_directions_tables.json": DEFAULT,
    "binding_directions_worklist.json": INDENT2,
    "binding_gaps_judged.json": DEFAULT,
    "binding_gaps_worklist.json": DEFAULT,
    "brand_judged.json": INDENT2,
    "brand_worklist.json": Format(indent=2, sort="all", newline=False),
    "category_judged.json": DEFAULT,
    "category_worklist.json": DEFAULT,
    "circuit_images_sources.json": INDENT2,
    "classification_judged.json": DEFAULT,
    "classification_sources.json": SORTED,
    "classification_worklist.json": DEFAULT,
    "clinpgx_variants.json": SORTED_ASCII,
    "cpic_guidance.json": SORTED_NO_NL,
    "cyp_judged.json": DEFAULT,
    "cyp_strength_judged.json": DEFAULT,
    "cyp_worklist.json": SORTED,
    "dailymed_labels.json": SORTED,
    "demographics_judged.json": DEFAULT,
    "demographics_worklist.json": DEFAULT,
    "drug_enzymes.json": SORTED,
    "drug_enzymes_wikipedia.json": SORTED,
    "drug_history_judged.json": DEFAULT,
    "drug_history_worklist.json": DEFAULT,
    "drugsfda_approvals.json": SORTED,
    "enzyme_variability.json": SORTED_NO_NL,
    "europepmc_binding_search.json": Format(sort="fields", ensure_ascii=True),
    "europepmc_effect_search.json": Format(sort="fields", ensure_ascii=True),
    "europepmc_species.json": _one_line_per_key,
    "expression_density.json": SORTED_NO_NL,
    "fetch_dates.json": SORTED_ASCII,
    "formulation_judged.json": DEFAULT,
    "formulation_worklist.json": DEFAULT,
    "gtopdb_class.json": Format(indent=2, sort="all", ensure_ascii=True),
    "gtopdb_ki.json": SORTED,
    "half_life_judged.json": DEFAULT,
    "half_life_worklist.json": DEFAULT,
    "ki_prose_judged.json": DEFAULT,
    "ki_prose_worklist.json": DEFAULT,
    "location_sources.json": SORTED_NO_NL,
    "metabolite_bindings_judged.json": INDENT2,
    "metabolite_bindings_worklist.json": INDENT2,
    "molecules_sources.json": INDENT2,
    "originator_judged.json": DEFAULT,
    "originator_worklist.json": DEFAULT,
    "page_links.json": SORTED_ASCII,
    "physchem.json": SORTED,
    "pk_judged.json": DEFAULT,
    "pk_worklist.json": Format(indent=2, newline=False),
    "prodrug_judged.json": DEFAULT,
    "prodrug_worklist.json": DEFAULT,
    "projection_judged.json": DEFAULT,
    "projection_sources.json": DEFAULT,
    "projection_worklist.json": DEFAULT,
    "quote_headers.json": INDENT2,
    "quote_llm.json": Format(indent=0, sort="all", newline=False),
    "quote_recheck_disputed.json": Format(newline=False),
    "quote_recheck_flagged.json": Format(newline=False),
    "receptor_demographics.json": SORTED,
    "receptor_effects.json": SORTED,
    "receptor_effects_judged.json": DEFAULT,
    "receptor_effects_worklist.json": DEFAULT,
    "release_modulation.json": SORTED,
    "release_modulation_judged.json": DEFAULT,
    "release_modulation_worklist.json": DEFAULT,
    "structure_images_sources.json": INDENT2,
    "tmax_judged.json": DEFAULT,
    "tmax_worklist.json": DEFAULT,
    "unknown_searches.json": Format(sort="fields"),
    "workup.json": SORTED,
    "workup_judged.json": DEFAULT,
    "workup_worklist.json": DEFAULT,
}


def dumps(name: str | Path, obj: Any) -> str:
    """``obj`` serialized the way the cache named ``name`` (a file name or any path ending in
    one) is committed. An unregistered name raises ``KeyError``: register it in
    :data:`FORMATS` first, so the format is chosen once and tested."""
    key = Path(name).name
    try:
        fmt = FORMATS[key]
    except KeyError:
        raise KeyError(f"{key}: no format registered in lib/cache_io.FORMATS") from None
    return fmt.dumps(obj) if isinstance(fmt, Format) else fmt(obj)


def write(path: str | Path, obj: Any, name: str | None = None) -> None:
    """Write ``obj`` to ``path`` atomically in its cache's format.

    ``name`` picks the format when ``path`` is not the cache's own file name (a fetcher's
    ``--out`` pointed at a scratch file still writes the cache's layout); it defaults to
    ``path``'s file name."""
    atomic_write_text(path, dumps(name or path, obj))
