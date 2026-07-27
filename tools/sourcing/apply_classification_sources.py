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
``check_data.normalize_for_match`` before it is written, so a stale cache cannot
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

Run from the repo root, then regenerate + check::

    python tools/sourcing/apply_classification_sources.py --dry-run
    python tools/sourcing/apply_classification_sources.py
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

sys.path.insert(0, str(TOOLS))
from check_data import normalize_for_match  # noqa: E402  (reuse the gate's normalizer)

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


def page_text(target_id: int, cache: dict[int, str]) -> str:
    """Normalized text of a target's cached classification page (the quote gate)."""
    if target_id not in cache:
        p = PAGES / f"{target_id}.md"
        cache[target_id] = normalize_for_match(p.read_text("utf-8")) if p.exists() else ""
    return cache[target_id]


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written, change nothing")
    args = ap.parse_args()

    if not CACHE.exists():
        raise SystemExit(f"error: {CACHE} missing; run tools/fetch/fetch_gtopdb_class.py first")
    proposals = json.loads(CACHE.read_text("utf-8"))
    receptors, targets = current_values()

    existing = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
    rec_out: dict[str, dict[str, list]] = existing.get("receptors", {})
    tgt_out: dict[str, list] = existing.get("targets", {})

    ptext: dict[int, str] = {}
    applied, conflicts, skipped = 0, [], []

    def add(bucket: list, src: dict) -> bool:
        if any(s.get("quote") == src["quote"] for s in bucket):
            return False
        bucket.append(src)
        return True

    def gated(owner: str, attr: str, tid: int, quote: str) -> dict | None:
        """The source dict, or None when the quote is not verbatim on its page."""
        text = page_text(tid, ptext)
        if text and normalize_for_match(quote) not in text:
            skipped.append(f"{owner}/{attr}: quote not on page {tid}")
            return None
        return {"corpus": "gtopdb_class", "page": tid, "quote": quote,
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
                if src and add(rec_out.setdefault(owner, {}).setdefault("family", []), src):
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
                if src and add(rec_out.setdefault(owner, {}).setdefault("receptor_class", []), src):
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
                if src and add(rec_out.setdefault(owner, {}).setdefault("sign", []), src):
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
                if src and add(tgt_out.setdefault(owner, []), src):
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

    payload = {}
    if rec_out:
        payload["receptors"] = rec_out
    if tgt_out:
        payload["targets"] = tgt_out
    if args.dry_run:
        print("(dry run: not written)")
        return 0
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
