"""Shared I/O for the authored drug dataset (``tools/data/drugs_data.jsonl``) and its
active-metabolite store (``tools/data/metabolites_data.jsonl``).

The dataset is stored as JSONL (one compact JSON object per line) rather than a
single pretty-printed JSON array: line-oriented diffs stay small and every
consumer reads/writes it the same way. Centralized here so no consumer hand-rolls it.

**One metabolite, one record.** A metabolite is a molecule, so what is true of the
molecule (its name, its link to a modeled drug, its own half-life, its own receptor
bindings) lives ONCE in ``metabolites_data.jsonl``, keyed by ``id``; a drug's
``metabolites[]`` only references it, ``{id, sources}``, the sources being the per-parent
claim "<metabolite> is an active metabolite of <drug>". So nordazepam, made by four
benzodiazepines, is one record and four references, e.g.::

    metabolites_data.jsonl  {"id": "desmethyldiazepam", "name": "Desmethyldiazepam (nordazepam)",
                             "half_life": {...}, "half_life_sources": [...], "bindings": [...]}
    drugs_data.jsonl        {"id": "diazepam", ..., "metabolites": [{"id": "desmethyldiazepam",
                             "sources": [<the diazepam article sentence>]}, ...]}
"""

import json
import re
from pathlib import Path

from lib.io_atomic import atomic_write_text
from lib.text_fold import ascii_key

DRUGS_PATH = Path(__file__).resolve().parents[1] / "data" / "drugs_data.jsonl"
METABOLITES_PATH = Path(__file__).resolve().parents[1] / "data" / "metabolites_data.jsonl"


# A combination product's name joins its parts with + or an en / em dash ("Naltrexone +
# Bupropion", "Phentermine–Topiramate"), never a plain hyphen (real names carry those).
_COMBO_SPLIT = re.compile(r"\s*[+–—]\s*")


def combo_parts(name: str | None) -> list[str] | None:
    """A combination's constituent names, split off its name, else None."""
    if not name or not _COMBO_SPLIT.search(name):
        return None
    return [p.strip() for p in _COMBO_SPLIT.split(name) if p.strip()]


def is_combination(drug: dict) -> bool:
    """THE combination test: a +/–/— in the name, or a slash-titled Wikipedia article
    ("Dextromethorphan/bupropion"). A salt with declared ``constituents``
    (dimenhydrinate) is one product, not a combination."""
    title = (drug.get("wikipedia") or "").rsplit("/wiki/", 1)[-1]
    return bool(combo_parts(drug.get("name"))) or "/" in title


def load_drugs(path=None) -> list[dict]:
    """Read the JSONL dataset, one ``json.loads`` per non-empty line, in order."""
    p = Path(path) if path is not None else DRUGS_PATH
    records = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _in_prior_order(rec, order: list[str] | None):
    """``rec`` with the keys the record held on disk (``order``) back in place, new ones last.

    An applier that owns a field pops it and re-adds it, which moves the key to the end;
    without this a re-run that changes nothing still rewrites every touched line.
    """
    if not order or not isinstance(rec, dict):
        return rec
    rank = {k: i for i, k in enumerate(order)}
    return dict(sorted(rec.items(), key=lambda kv: rank.get(kv[0], len(rank))))


def save_drugs(records, path=None) -> None:
    """Write the records as JSONL (compact), one per line, so a re-run is byte-stable.

    A record the file already holds (by ``id``) keeps its on-disk key order, see
    :func:`_in_prior_order`; any other record keeps the order it was built in.
    """
    p = Path(path) if path is not None else DRUGS_PATH
    prior = ({r.get("id"): list(r) for r in load_drugs(p) if isinstance(r, dict)}
             if p.exists() else {})
    lines = [json.dumps(_in_prior_order(rec, prior.get(rec.get("id"))
                                        if isinstance(rec, dict) else None),
                        ensure_ascii=False) for rec in records]
    atomic_write_text(p, "\n".join(lines) + "\n")


def load_metabolites(path=None) -> list[dict]:
    """Read the metabolite store (one record per molecule), ``[]`` when absent."""
    p = Path(path) if path is not None else METABOLITES_PATH
    return load_drugs(p) if p.exists() else []


def save_metabolites(records, path=None) -> None:
    """Write the metabolite store, sorted by id (stable diffs whatever the writer did)."""
    save_drugs(sorted(records, key=lambda m: m["id"]),
               path if path is not None else METABOLITES_PATH)


_fold = ascii_key


def names_of(metabolite: str) -> list[str]:
    """The folded names a source may use for a metabolite: ``"Desmethyldiazepam
    (nordazepam)"`` -> ``["desmethyldiazepam", "nordazepam"]``, a bare
    ``"(+)-alpha-Dihydrotetrabenazine"`` -> ``["alphadihydrotetrabenazine"]``."""
    parts = [metabolite.split("(")[0]] + re.findall(r"\(([^)]*)\)", metabolite)
    folded = [f for f in (_fold(p) for p in parts) if f]
    whole = _fold(metabolite)
    return folded if folded and not metabolite.startswith("(") else [whole]


def metabolite_id(name: str) -> str:
    """The id a NEW metabolite record gets: its name before any parenthesised synonym,
    slugged (``"Desmethyldiazepam (nordazepam)"`` -> ``"desmethyldiazepam"``,
    ``"Carbamazepine-10,11-epoxide"`` -> ``"carbamazepine_10_11_epoxide"``)."""
    slug = lambda s: re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return slug(name.split("(")[0]) or slug(name)


def find_metabolite(metabolites: list[dict], name: str) -> dict | None:
    """The store record ``name`` designates (any of its :func:`names_of` matching), or None."""
    want = set(names_of(name))
    return next((m for m in metabolites if want & set(names_of(m["name"]))), None)


def attach_metabolite(drug: dict, metabolites: list[dict], name: str) -> tuple[dict, dict]:
    """``(ref, record)`` for metabolite ``name`` of ``drug``, creating what is missing.

    The store record is found by name (:func:`find_metabolite`) or appended; the drug's
    ``metabolites[]`` gets a ``{id}`` reference to it unless it already holds one. The
    caller then writes per-parent facts on ``ref`` (``sources``) and molecule facts on
    ``record`` (half-life, bindings), never the other way round."""
    rec = find_metabolite(metabolites, name)
    if rec is None:
        mid = metabolite_id(name)
        if any(m["id"] == mid for m in metabolites):
            raise ValueError(f"metabolite id {mid!r} (from {name!r}) already names "
                             f"another molecule; rename one")
        rec = {"id": mid, "name": name}
        metabolites.append(rec)
    refs = drug.setdefault("metabolites", [])
    ref = next((r for r in refs if r["id"] == rec["id"]), None)
    if ref is None:
        ref = {"id": rec["id"]}
        refs.append(ref)
    return ref, rec


def parents_of(drugs: list[dict]) -> dict[str, list[str]]:
    """Metabolite id -> the ids of the drugs listing it, in dataset order."""
    out: dict[str, list[str]] = {}
    for d in drugs:
        for r in d.get("metabolites", []):
            out.setdefault(r["id"], []).append(d["id"])
    return out


def non_modeled_metabolites(drugs: list[dict], metabolites: list[dict],
                            key=str.lower) -> list[dict]:
    """Every referenced metabolite that is not itself a modeled drug.

    Shared by every metabolite pass (Wikipedia ``fetch_metabolite_bindings.py``, GtoPdb
    ``fetch_gtopdb_ki.py``). Mirrors ``js/data.js``: a metabolite links to a modeled drug
    by explicit ``drug_id`` or by its name matching a drug name, and those reuse that
    drug's bindings (nothing to source here). The rest are returned as
    ``{id, name, parents, key}`` (``key`` = the caller's stable lowercase id rule, e.g.
    the Wikipedia slug, for --only / worklist). One record per molecule, so a metabolite
    two drugs make (mCPP: nefazodone AND trazodone) is sourced once, both parents listed.
    """
    drug_ids = {d["id"] for d in drugs}
    by_norm = {_fold(d.get("name", "")): d["id"] for d in drugs}
    parents = parents_of(drugs)
    out = []
    for m in metabolites:
        if m["id"] not in parents:
            continue
        linked = m.get("drug_id") or by_norm.get(_fold(m["name"]))
        if linked and linked in drug_ids:
            continue
        out.append({"id": m["id"], "name": m["name"], "parents": parents[m["id"]],
                    "key": key(m["name"])})
    return out
