#!/usr/bin/env python
"""Build the receptor / target classification worklist from prose already on disk.

A receptor's classification is four graded sub-claims (family / receptor_class / sign /
synaptic) and a non-receptor target's is one (type + system). GtoPdb (corpus #12,
``apply_classification_sources.py``) closed most of them from structured fields, but it has
no pre/post-synaptic field at all, no transduction row for an ion channel, and no type that
asserts "chaperone". Those residues are stated, when anywhere, in prose: the receptor's own
English Wikipedia article (corpus #9 ``wikipedia_pharm``, stored by
``fetch_wikipedia_pharmacology.py --title <Article>``) and Stahl's Essential
Psychopharmacology (corpus #3 ``stahl_essential``).

This is the fetch / candidate-extraction half of the usual four-step pipeline and states
**no verdict of its own**. Per owner whose attribute still grades ``llm`` it lists, indexed:

* every sentence of the owner's stored Wikipedia article that hits one of the still-``llm``
  attributes' keyword sets (:data:`KEYWORDS`);
* every Stahl Essential sentence that names the owner (``target_aliases.mentions``) and hits
  the same keywords.

plus the value the dataset states for each attribute. The LLM pass reads
``tools/generated_cache/classification_worklist.json`` and answers by candidate index into
``classification_judged.json`` (confirm-only: it never changes a value, only points at the
sentence asserting it); ``apply_classification_sources.py --prose`` gates and writes.

Usage (from the repo root)::

    python tools/fetch/fetch_classification_worklist.py
    python tools/fetch/fetch_classification_worklist.py --only nmda,sigma1

Stdlib only, offline; author-side (needs the gitignored ``data_sources/`` trees).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # repo root
sys.path.insert(0, str(ROOT / "tools"))
from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib.corpora import wikipedia as wikistore  # noqa: E402 (slug_of, SENTENCE_SPLIT, REFERENCE_RE)
from lib import target_aliases  # noqa: E402
from lib import worklist_io  # noqa: E402

OUT_PATH = ROOT / "tools" / "generated_cache" / "classification_worklist.json"
WIKI_PAGES = ROOT / "data_sources" / "wikipedia" / "pages"
STAHL_ESS_PAGES = ROOT / "data_sources" / "books" / "stahl_essential_pharmacology" / "pages"

MIN_LINE, MAX_LINE = 30, 600
# An owner whose article URL is a redirect: the store names the file after the resolved
# title. Listed rather than guessed, like ``lib.corpora.wikipedia.PAGE_ALIASES``.
PAGE_ALIASES: dict[str, str] = {
    "cannabinoid_receptor_type_1": "cannabinoid_receptor_1",
    "4_aminobutyrate_aminotransferase": "4_aminobutyrate_transaminase",
    # The CGRP receptor is CALCRL + RAMP1; the article title redirects to the gene.
    "calcitonin_gene_related_peptide_receptor": "calcrl",
}
RECEPTOR_ATTRS = ("receptor_class", "sign", "synaptic")
# Spellings Stahl Essential uses that ``target_aliases`` does not carry (its display names
# are "Neuronal α4β2 nAChR", "GABA-B", ...). Local to this pass on purpose: widening the
# shared table would silently change every other pass's candidate set.
PROSE_ALIASES: dict[str, list[str]] = {
    "nachr_a4b2": ["α4β2", "alpha4beta2"],
    "gaba_b": ["GABAB", "GABA B"],
    "gaba_a_rho": ["GABAC", "GABA-rho", "GABAA-rho"],
}

# The words a sentence must carry to be offered for an attribute. Recall over precision:
# the judge discards a weak hit, but a sentence never offered can never be picked.
KEYWORDS: dict[str, re.Pattern[str]] = {
    "synaptic": re.compile(
        r"presynap|postsynap|pre- or postsynap|autoreceptor|heteroreceptor|"
        r"nerve terminal|axon terminal|somatodendritic|dendritic spine", re.I),
    "sign": re.compile(
        r"excitat|inhibit|depolari|hyperpolari|chloride|cation|sodium|calcium|"
        r"potassium|\bG[iso]\b|Gi/o|Gαi|Gαs|Gαq|adenylyl|adenylate|cAMP", re.I),
    "receptor_class": re.compile(
        r"chaperone|ion channel|G protein|GPCR|ligand-gated|metabotropic|ionotropic", re.I),
    "type": re.compile(
        r"\benzyme|catalyz|catalys|cotransporter|symporter|transporter|\breceptor\b|"
        r"decarboxylase|transaminase|aminotransferase|methyltransferase", re.I),
}


def sentences(text: str) -> list[str]:
    """Prose sentences of a stored page: tables, headings, the stamp and references dropped.

    Hyphenated line breaks are joined first, exactly as ``lib.quote_match.normalize_for_match``
    does, so a candidate taken from a hard-wrapped book page still re-finds verbatim.
    """
    text = re.sub(r"-\s*\n\s*", "", text)
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(ln.strip() for ln in para.splitlines()
                        if ln.strip() and " | " not in ln and not ln.lstrip().startswith(
                            ("#", "<!--", "source:")))
        if not para or wikistore.REFERENCE_RE.search(para):
            continue
        para = para.lstrip("- ").strip()
        for part in wikistore.SENTENCE_SPLIT.split(para):
            part = part.strip()
            if MIN_LINE <= len(part) <= MAX_LINE:
                out.append(part)
    return out


def _hits(line: str, attrs: list[str]) -> list[str]:
    return [a for a in attrs if KEYWORDS[a].search(line)]


def owners() -> dict[str, dict]:
    """``{id: {kind, name, wikipedia, values, need}}`` for every owner still graded llm."""
    out: dict[str, dict] = {}
    for line in (ROOT / "public/data/receptors.jsonl").read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        cls = r.get("classification") or {}
        need = [a for a in RECEPTOR_ATTRS if (cls.get(a) or {}).get("grade") == "llm"]
        if need:
            out[r["id"]] = {"kind": "receptor", "name": r["name"],
                            "wikipedia": r.get("wikipedia", ""),
                            "values": {a: r[a] for a in RECEPTOR_ATTRS}, "need": need}
    meta = json.loads((ROOT / "public/data/meta.json").read_text("utf-8"))
    for tid, t in meta["drug_targets"].items():
        if isinstance(t, dict) and t.get("classification_provenance") == "llm":
            out[tid] = {"kind": "target", "name": t["name"],
                        "wikipedia": t.get("wikipedia", ""),
                        "values": {"type": t.get("type"), "system": t.get("system")},
                        "need": ["type"]}
    return out


def stahl_sentences() -> list[tuple[int, str]]:
    """Every Stahl Essential sentence, with its page number (empty on a clone)."""
    out: list[tuple[int, str]] = []
    if not STAHL_ESS_PAGES.exists():
        return out
    for p in sorted(STAHL_ESS_PAGES.glob("*.md"), key=lambda q: int(q.stem)):
        out.extend((int(p.stem), s) for s in sentences(p.read_text("utf-8", errors="replace")))
    return out


def candidates(oid: str, owner: dict, stahl: list[tuple[int, str]],
               aliases: dict[str, list[str]]) -> list[dict]:
    out: list[dict] = []
    slug = wikistore.slug_of(owner["wikipedia"]) if owner["wikipedia"] else ""
    slug = PAGE_ALIASES.get(slug, slug)
    path = page_path(WIKI_PAGES, slug)
    if slug and path.exists():
        for line in sentences(path.read_text("utf-8", errors="replace")):
            hit = _hits(line, owner["need"])
            if hit:
                out.append({"corpus": "wikipedia_pharm", "page": slug, "line": line,
                            "attrs": hit})
    names = (aliases.get(oid) or []) + PROSE_ALIASES.get(oid, [])
    rx = target_aliases.alias_regex(names) if names else None
    for page, line in stahl:
        if rx and rx.search(target_aliases.fold(line)):
            hit = _hits(line, owner["need"])
            if hit:
                out.append({"corpus": "stahl_essential", "page": page, "line": line,
                            "attrs": hit})
    seen: set[tuple] = set()
    return [c for c in out if not ((c["corpus"], c["line"]) in seen
                                   or seen.add((c["corpus"], c["line"])))]


def build(only: set[str] | None = None) -> dict:
    stahl = stahl_sentences()
    aliases = target_aliases.aliases_by_target()
    work = {}
    for oid, owner in owners().items():
        if only and oid not in only:
            continue
        work[oid] = {**owner, "candidates": candidates(oid, owner, stahl, aliases)}
    return {"owners": work}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated receptor/target ids to scope the scan to")
    ap.add_argument("--out", type=Path, default=OUT_PATH, help="worklist output path")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None
    wl = build(only)
    worklist_io.write(args.out, wl)
    n = sum(len(v["candidates"]) for v in wl["owners"].values())
    print(f"[ok] wrote {args.out}: {len(wl['owners'])} owners, {n} candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
