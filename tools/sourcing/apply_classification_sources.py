#!/usr/bin/env python
"""Apply GtoPdb classification facts into ``tools/generated_cache/classification_sources.json``.

Reads the proposals ``tools/fetch/fetch_gtopdb_class.py`` cached (corpus #12
``gtopdb_class``) and writes the verified sources ``generate_data.py`` merges onto a
receptor's per-attribute classification nodes (``family`` / ``receptor_class`` / ``sign``)
and onto a non-receptor target's classification node (``type``).

**Confirm-only, like every other sourcing pass**: a source is written only when
GtoPdb's fact *agrees with the value the dataset already states*. A disagreement is
reported for a human and changes nothing, because rewriting our data to match a source
would make the grade meaningless. Every quote is re-confirmed on its cached page with
``lib.quote_match.normalize_for_match`` before it is written, so a stale cache cannot
smuggle an unsourced quote through. Idempotent (dedup by quote); safe to re-run.

**The three mappings, and why each is honest.**

- ``receptor_class`` and a target's ``type`` come from GtoPdb's own ``type`` field, and
  ``family`` from its own family label. These are direct reads, not inferences: ``gpcr``
  *is* metabotropic, ``lgic`` *is* ionotropic, "Dopamine receptors" *is* dopaminergic.
- ``sign`` is mapped from the **transduction** table (GPCRs only), because GtoPdb
  states the transducer/effector and never a sign. The mapping is deliberately narrow
  (see :data:`SIGN_BY_TRANSDUCER`): a single unambiguous primary transducer family, or
  several primary rows that all agree. Anything mixed, secondary, empty or unknown
  writes nothing and the node honestly stays ``llm``. The quote carried into the pill
  is the transduction line itself, so a reader sees exactly what backs the sign.

GtoPdb has **no pre/post-synaptic field**, so ``synaptic`` is untouched here.

**``--prose`` mode** reads the residue GtoPdb cannot reach (``synaptic``, an ion channel's
``sign``, sigma-1's "chaperone", five target types) from prose instead:
``tools/fetch/fetch_classification_worklist.py`` lists indexed candidate sentences from the
owner's Wikipedia article (corpus #9) and Stahl Essential (corpus #3), an LLM answers by index
into ``classification_judged.json``, and :func:`apply_prose` gates and writes. Same
confirm-only rule: a pick lands only on an attribute the worklist listed as ``llm`` whose
value still equals the one the worklist recorded, and a ``synaptic`` pick must name exactly
the site(s) the value claims (``both`` needs a presynaptic AND a postsynaptic quote). It
writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py`` must judge it afterwards.

Run from the repo root, then regenerate + check::

    python tools/sourcing/apply_classification_sources.py --dry-run
    python tools/sourcing/apply_classification_sources.py
    python tools/sourcing/apply_classification_sources.py --prose --dry-run
    python tools/generate_data.py && python tools/check_data.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent   # tools/ (script lives in tools/sourcing/)
REPO = TOOLS.parent
CACHE = TOOLS / "generated_cache" / "gtopdb_class.json"
PAGES = REPO / "data_sources" / "gtopdb" / "pages_class"
OUT = TOOLS / "generated_cache" / "classification_sources.json"
WORKLIST = TOOLS / "generated_cache" / "classification_worklist.json"
JUDGED = TOOLS / "generated_cache" / "classification_judged.json"
# The stored page trees a --prose pick may cite, keyed by corpus (page file = <page>.md).
PROSE_PAGES = {
    "wikipedia_pharm": REPO / "data_sources" / "wikipedia" / "pages",
    "stahl_essential": REPO / "data_sources" / "books" / "stahl_essential_pharmacology" / "pages",
}
SITES = {"presynaptic": {"presynaptic"}, "postsynaptic": {"postsynaptic"},
         "both": {"presynaptic", "postsynaptic"}}

sys.path.insert(0, str(TOOLS))
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)
from prose_gate import add_source  # noqa: E402
from lib.io_atomic import atomic_write_json  # noqa: E402

# GtoPdb target type -> our receptor `receptor_class` vocabulary. Absent = no claim:
# `other_protein` (sigma-1) does not assert our "chaperone", so sigma-1 stays llm.
CLASS_BY_TYPE: dict[str, str] = {
    "gpcr": "metabotropic",
    "lgic": "ionotropic",
    "vgic": "ionotropic",
    "other_ic": "ionotropic",
}

# GtoPdb target type -> our non-receptor target `type` vocabulary (TARGET_TYPE_LABELS).
TARGET_TYPE_BY_TYPE: dict[str, str] = {
    "enzyme": "enzyme",
    "vgic": "ion_channel",
    "lgic": "ion_channel",
    "other_ic": "ion_channel",
    "transporter": "transporter",
    # A GtoPdb `gpcr` whose family name we model as a whole (melanocortin) is our
    # `receptor_group`: the quote names the receptor family, which is the claim.
    "gpcr": "receptor_group",
}

# GtoPdb family name -> our receptor `family` (neurotransmitter system) vocabulary.
# A direct read like the type field, not an inference: GtoPdb's own family label names the
# transmitter. Every name the cache holds is mapped, so an unmapped one (a family we start
# modelling later) is reported rather than silently dropped.
FAMILY_BY_GTOPDB_FAMILY: dict[str, str] = {
    "5-HT3 receptors": "serotonergic",
    "5-Hydroxytryptamine receptors": "serotonergic",
    "Acetylcholine receptors (muscarinic)": "cholinergic",
    "Adenosine receptors": "purinergic",
    "Adrenoceptors": "adrenergic",
    "Cannabinoid receptors": "cannabinoid",
    "Dopamine receptors": "dopaminergic",
    "GABAA receptors": "gabaergic",
    "GABAB receptors": "gabaergic",
    "Glycine receptors": "glycinergic",
    "Histamine receptors": "histaminergic",
    "Ionotropic glutamate receptors": "glutamatergic",
    "Melatonin receptors": "melatonergic",
    "Metabotropic glutamate receptors": "glutamatergic",
    "Nicotinic acetylcholine receptors (nACh)": "cholinergic",
    "Opioid receptors": "opioidergic",
    "Sigma receptors": "sigma",
}

# Transducer family -> the sign it implies. Narrow on purpose: only the three canonical
# couplings, each with an unambiguous direction on the postsynaptic cell. G12/G13 and
# "G protein (identity unknown)" are absent, so a receptor listing one writes nothing.
SIGN_BY_TRANSDUCER: dict[str, str] = {
    "Gi/Go family": "inhibitory",
    "Gs family": "excitatory",
    "Gq/G11 family": "excitatory",
}

# A transducer cell can list several mechanisms. This one names no G protein and so
# implies no sign; it is ignored rather than vetoing the row (D2 reads "Gi/Go family,
# G protein independent mechanism", where the Gi/Go coupling is the whole sign claim).
SIGN_NEUTRAL_MECHANISMS = {"G protein independent mechanism"}


CORPUS = "gtopdb_class"


def strip_corpus(rec_out: dict, tgt_out: dict, corpus: str = CORPUS) -> int:
    """Drop every ``corpus`` citation (pruning emptied buckets) so a re-run rewrites them.

    The GtoPdb pass owns its corpus's citations: after a ``--refresh`` a line GtoPdb
    reworded must REPLACE the old quote (no longer on the page), not sit beside it.
    Prose citations (other corpora) are left alone. Returns how many were dropped."""
    dropped = 0
    for owner in list(rec_out):
        for attr in list(rec_out[owner]):
            keep = [s for s in rec_out[owner][attr] if s.get("corpus") != corpus]
            dropped += len(rec_out[owner][attr]) - len(keep)
            if keep:
                rec_out[owner][attr] = keep
            else:
                del rec_out[owner][attr]
        if not rec_out[owner]:
            del rec_out[owner]
    for owner in list(tgt_out):
        keep = [s for s in tgt_out[owner] if s.get("corpus") != corpus]
        dropped += len(tgt_out[owner]) - len(keep)
        if keep:
            tgt_out[owner] = keep
        else:
            del tgt_out[owner]
    return dropped


def write_out(rec_out: dict, tgt_out: dict) -> None:
    """The one writer of classification_sources.json, shared by both modes."""
    payload = {k: v for k, v in (("receptors", rec_out), ("targets", tgt_out)) if v}
    atomic_write_json(OUT, payload, indent=1, sort_keys=True)
    print(f"wrote {OUT.relative_to(REPO)}")


def current_values() -> tuple[dict[str, dict], dict[str, dict]]:
    """What the dataset states today: (receptor_id -> record, target_id -> record).
    The confirm-only comparison is against these, never against an authored table."""
    recs = [json.loads(line) for line in (REPO / "public/data/receptors.jsonl")
            .read_text("utf-8").splitlines() if line.strip()]
    meta = json.loads((REPO / "public/data/meta.json").read_text("utf-8"))
    return ({r["id"]: r for r in recs},
            {k: v for k, v in meta["drug_targets"].items() if isinstance(v, dict)})


def sign_from_transduction(entries: list[dict]) -> tuple[str | None, dict | None, str]:
    """Map a target's transduction table to a sign, conservatively.

    Returns ``(sign, entry_backing_it, why)``. Only **primary** rows count; every
    mapped family must agree, and an unmapped one vetoes the whole target (a receptor
    coupling to something we do not map is exactly the case where inferring a sign
    would be guessing).
    """
    primary = [e for e in entries if not e.get("secondary")]
    if not primary:
        return None, None, "no primary transduction row"
    signs, backing = set(), None
    for e in primary:
        families = [f.strip() for f in (e.get("transducers") or "").split(",")
                    if f.strip() and f.strip() not in SIGN_NEUTRAL_MECHANISMS]
        if not families:
            return None, None, f"no G protein named in {e.get('transducers')!r}"
        for fam in families:
            mapped = SIGN_BY_TRANSDUCER.get(fam)
            if mapped is None:
                return None, None, f"unmapped transducer {fam!r}"
            signs.add(mapped)
        if backing is None:
            backing = e
    if len(signs) > 1:
        return None, None, f"primary rows disagree ({sorted(signs)})"
    return signs.pop(), backing, ""


def apply_prose(worklist: dict, judged: dict, receptors: dict, targets: dict,
                rec_out: dict, tgt_out: dict, pages: dict = PROSE_PAGES) -> tuple[int, list]:
    """Gate the LLM's by-index picks and merge them into ``rec_out`` / ``tgt_out``.

    ``judged`` is ``{"receptors": {rid: {"sign"|"receptor_class": [idx],
    "synaptic": {site: [idx]}}}, "targets": {tid: [idx]}}``; indices point into
    ``worklist["owners"][id]["candidates"]``. Returns ``(applied, misses)``; a miss
    writes nothing for that attribute.
    """
    owners = worklist.get("owners", {})
    gate = PageGate(pages)
    applied, misses = 0, []

    def sources(oid: str, picks, what: str) -> list[dict] | None:
        return gate.sources(owners[oid].get("candidates", []), picks, f"{oid}/{what}", misses)

    for rid, attrs in sorted((judged.get("receptors") or {}).items()):
        own, rec = owners.get(rid), receptors.get(rid)
        if own is None or rec is None:
            misses.append(f"{rid}: not in the worklist / not a current receptor")
            continue
        for attr, picks in sorted(attrs.items()):
            if attr not in own.get("need", []):
                misses.append(f"{rid}/{attr}: not listed as llm in the worklist")
                continue
            value = rec.get(attr)
            if value != own["values"].get(attr):
                misses.append(f"{rid}/{attr}: value changed since the worklist "
                              f"({own['values'].get(attr)!r} -> {value!r})")
                continue
            if attr == "synaptic":
                picks = {k: v for k, v in (picks or {}).items() if v}
                if set(picks) != SITES.get(value, {None}):
                    misses.append(f"{rid}/synaptic: picks cover {sorted(picks)}, "
                                  f"value {value!r} needs {sorted(SITES.get(value, []))}")
                    continue
                flat = [i for site in sorted(picks) for i in picks[site]]
            else:
                flat = picks
            srcs = sources(rid, flat, attr)
            if srcs:
                bucket = rec_out.setdefault(rid, {}).setdefault(attr, [])
                applied += sum(add_source(bucket, s) for s in srcs)

    for tid, picks in sorted((judged.get("targets") or {}).items()):
        own = owners.get(tid)
        if own is None or tid not in targets:
            misses.append(f"{tid}: not in the worklist / not a current target")
            continue
        if targets[tid].get("type") != own["values"].get("type"):
            misses.append(f"{tid}/type: value changed since the worklist")
            continue
        srcs = sources(tid, picks, "type")
        if srcs:
            bucket = tgt_out.setdefault(tid, [])
            applied += sum(add_source(bucket, s) for s in srcs)
    return applied, misses


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written, change nothing")
    ap.add_argument("--prose", action="store_true",
                    help="apply classification_judged.json (Wikipedia / Stahl Essential "
                         "prose picks) instead of the GtoPdb cache")
    args = ap.parse_args()

    if args.prose:
        receptors, targets = current_values()
        existing = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
        rec_out, tgt_out = existing.get("receptors", {}), existing.get("targets", {})
        applied, misses = apply_prose(worklist_io.read(WORKLIST),
                                      worklist_io.read(JUDGED),
                                      receptors, targets, rec_out, tgt_out)
        for m in misses:
            print(f"  [miss] {m}", file=sys.stderr)
        print(f"applied {applied} prose classification source(s), {len(misses)} miss(es)")
        if args.dry_run:
            print("(dry run: not written)")
            return 0
        write_out(rec_out, tgt_out)
        return 0

    if not CACHE.exists():
        raise SystemExit(f"error: {CACHE} missing; run tools/fetch/fetch_gtopdb_class.py first")
    proposals = json.loads(CACHE.read_text("utf-8"))
    receptors, targets = current_values()

    existing = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
    rec_out: dict[str, dict[str, list]] = existing.get("receptors", {})
    tgt_out: dict[str, list] = existing.get("targets", {})
    replaced = strip_corpus(rec_out, tgt_out)

    class_gate = PageGate({CORPUS: PAGES})
    applied, conflicts, skipped = 0, [], []

    def gated(owner: str, attr: str, tid: int, quote: str) -> dict | None:
        """The source dict, or None when the quote is not verbatim on its page."""
        # Lenient on a missing or empty page (a clone), unlike PageGate.refuted().
        if class_gate.text(CORPUS, tid) and not class_gate.on_page(CORPUS, tid, quote):
            skipped.append(f"{owner}/{attr}: quote not on page {tid}")
            return None
        return {"corpus": CORPUS, "page": tid, "quote": quote,
                "provenance": "verified"}

    for owner, prop in sorted(proposals.items()):
        tid = prop["target_id"]
        if prop["kind"] == "receptor":
            rec = receptors.get(owner)
            if rec is None:
                skipped.append(f"{owner}: not a current receptor")
                continue
            # family, from GtoPdb's own family label (same line as the type).
            fam = FAMILY_BY_GTOPDB_FAMILY.get(prop.get("family", ""))
            if fam is None:
                skipped.append(f"{owner}/family: family {prop.get('family')!r} maps to nothing")
            elif fam != rec["family"]:
                conflicts.append(f"{owner}/family: we say {rec['family']!r}, "
                                 f"GtoPdb family {prop['family']!r} implies {fam!r}")
            else:
                src = gated(owner, "family", tid, prop["type_quote"])
                if src and add_source(rec_out.setdefault(owner, {}).setdefault("family", []), src):
                    applied += 1
            # receptor_class, from GtoPdb's own type field.
            mapped = CLASS_BY_TYPE.get(prop["type"])
            if mapped is None:
                skipped.append(f"{owner}/receptor_class: type {prop['type']!r} maps to nothing")
            elif mapped != rec["receptor_class"]:
                conflicts.append(f"{owner}/receptor_class: we say {rec['receptor_class']!r}, "
                                 f"GtoPdb type {prop['type']!r} implies {mapped!r}")
            else:
                src = gated(owner, "receptor_class", tid, prop["type_quote"])
                if src and add_source(rec_out.setdefault(owner, {}).setdefault("receptor_class", []), src):
                    applied += 1
            # sign, mapped from the transduction table (GPCRs only).
            sign, backing, why = sign_from_transduction(prop["transduction"])
            if sign is None:
                skipped.append(f"{owner}/sign: {why}")
            elif sign != rec["sign"]:
                conflicts.append(f"{owner}/sign: we say {rec['sign']!r}, "
                                 f"{backing['transducers']} implies {sign!r}")
            else:
                src = gated(owner, "sign", tid, backing["quote"])
                if src and add_source(rec_out.setdefault(owner, {}).setdefault("sign", []), src):
                    applied += 1
        else:
            tgt = targets.get(owner)
            if tgt is None:
                skipped.append(f"{owner}: not a current target")
                continue
            mapped = TARGET_TYPE_BY_TYPE.get(prop["type"])
            if mapped is None:
                skipped.append(f"{owner}/type: type {prop['type']!r} maps to nothing")
            elif mapped != tgt.get("type"):
                conflicts.append(f"{owner}/type: we say {tgt.get('type')!r}, "
                                 f"GtoPdb type {prop['type']!r} implies {mapped!r}")
            else:
                src = gated(owner, "type", tid, prop["type_quote"])
                if src and add_source(tgt_out.setdefault(owner, []), src):
                    applied += 1

    for c in conflicts:
        print(f"  [conflict] {c}", file=sys.stderr)
    for s in skipped:
        print(f"  [skip] {s}", file=sys.stderr)

    n_attrs = sum(len(a) for o in rec_out.values() for a in o.values())
    print(f"\napplied {applied} classification source(s); "
          f"{n_attrs} receptor attribute sources over {len(rec_out)} receptors, "
          f"{sum(len(v) for v in tgt_out.values())} target sources over {len(tgt_out)} targets")
    print(f"{len(conflicts)} conflict(s) reported (not resolved), {len(skipped)} skipped")

    print(f"({replaced} previous {CORPUS} citation(s) rewritten from the current pages)")
    if args.dry_run:
        print("(dry run: not written)")
        return 0
    write_out(rec_out, tgt_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
