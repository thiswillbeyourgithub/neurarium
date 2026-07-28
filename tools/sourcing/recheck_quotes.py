#!/usr/bin/env python3
"""Recheck the emitted verified quotes with a stronger LLM and stamp the sourcing model.

Every ``verified`` quote in ``public/data/quotes.jsonl`` was extracted+judged by some
LLM (historically often Haiku). This harness re-verifies each quote with a chosen model
(Sonnet by default) and records *which* model confirmed it, so a reader can weigh a quote
by the capability of the model that vouched for it (see CLAUDE.md "The sourcing model").

The output is a central ``tools/generated_cache/quote_llm.json`` map ``{quote_id: llm}``
applied uniformly at generation time by ``data_generators.quote_table`` (an override wins
over any source-level ``llm``), so ONE recheck pass stamps every kind of quote without
editing each authoring site. Quotes the recheck could not fully confirm are written to
``quote_recheck_flagged.json`` for human review (they are NOT stamped).

Token cost is minimized by batching: quotes are grouped by source page so each page's
OCR'd text is loaded ONCE per batch and shared by all its quotes.

Three steps (the middle one is the only LLM spend):

1. ``python tools/sourcing/recheck_quotes.py build --out <dir>``
   Reconstructs, for every non-Allen quote, the claim(s) it backs (Allen AHBA quotes are
   deterministic PACall confirmations, not LLM-sourced, so they are excluded) and writes
   ``<dir>/batch_<i>.json`` (each: ``{pages: {ref: text}, items: [{qid, page_ref, quote,
   claims, heading?}]}``) + ``manifest.json``.

2. Judge each batch with the chosen model. This project ran it as a Workflow: one agent
   per batch reads its file and returns, per item, ``{qid, present, supports, note?}``
   against the embedded page text (present allowing OCR noise; supports = the quote
   substantiates the claim). Aggregate every agent's ``verdicts`` into one JSON object
   ``{"verdicts": {qid: {present, supports, note?}}}``.

   **Tell the judge what ``heading`` means**, because it decides the harder half of the
   verdict: it is where in the book the passage sits (a breadcrumb of headings,
   outermost first), and Stahl's sections are not interchangeable. A sentence under
   *How the Drug Works*
   is the book attributing a mechanism to that drug; the same sentence under *How Drug
   Causes Side Effects* is a rule printed with the mechanism, not the drug, as its
   subject, so it does not by itself say this drug has the action (that distinction is
   what the "uncertain" badges rest on, see CLAUDE.md Source provenance). ``supports``
   should be false when the claim needs an attribution the section cannot give.

3. ``python tools/sourcing/recheck_quotes.py apply --batches <dir> --verdicts <file> [--llm sonnet]``
   Writes ``quote_llm.json`` (present AND supports -> stamped) + ``quote_recheck_flagged.json``.

Then regenerate (``python tools/generate_data.py``) and check. Made with the help of Claude Code.
"""
import argparse
import collections
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "public", "data")
CACHE = os.path.join(ROOT, "tools", "generated_cache")

# corpus -> author-side page directory (the same trees check_data.py's quote gate reads).
# Allen AHBA is intentionally absent: its quotes are deterministic, not LLM-sourced.
def _page_dirs():
    """``corpus -> author-side page directory``, read from the emitted
    ``meta.source_corpora``.

    Not a hardcoded map: the corpus registry already carries every ``pages_dir``
    (generate_data.py's SOURCE_CORPORA), and a copy here silently went stale as
    corpora #9-#12 were added, crashing this script with a KeyError on the first
    quote from a corpus it had never heard of. A corpus with no ``pages_dir`` (a Ki
    CSV) has no page text to embed and is skipped like the excluded ones."""
    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as fh:
        corpora = json.load(fh).get("source_corpora", {})
    return {name: entry["pages_dir"] for name, entry in corpora.items()
            if entry.get("pages_dir")}


PAGE_DIR = _page_dirs()
EXCLUDE_CORPUS = {"allen_ahba"}
MAX_Q, MAX_P = 22, 7  # per-batch caps (quotes, distinct pages)


def _jsonl(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _qids(sources):
    return [s["quote_id"] for s in sources
            if isinstance(s, dict) and "quote_id" in s]


def reconstruct_claims(quotes):
    """quote_id -> [human-readable claim strings], scanning the emitted graph."""
    claims = collections.defaultdict(list)

    def add(qid, claim):
        if qid in quotes and quotes[qid]["corpus"] not in EXCLUDE_CORPUS:
            claims[qid].append(claim)

    for d in _jsonl("drugs.jsonl"):
        nm = d["name"]
        for b in d.get("bindings", []):
            tag = " (tentative)" if b.get("tentative") else ""
            for q in _qids(b.get("sources", [])):
                add(q, f"Drug {nm} acts on target '{b['target']}' as {b['action']}{tag}.")
        for q in _qids(d.get("category_sources", [])):
            add(q, f"Drug {nm} is classified as {', '.join(d.get('categories', []))}.")
        for q in _qids(d.get("nbn_sources", [])):
            add(q, f"Drug {nm} Neuroscience-based Nomenclature = '{d.get('nbn')}'.")

    for r in _jsonl("receptors.jsonl"):
        nm = r["name"]
        for attr, info in (r.get("classification") or {}).items():
            for q in _qids(info.get("sources", [])):
                add(q, f"Receptor {nm}: {attr} = '{r.get(attr)}'.")
        for region, srcs in (r.get("location_sources") or {}).items():
            for q in _qids(srcs):
                add(q, f"Receptor {nm} is expressed in brain region '{region}'.")

    for p in _jsonl("projections.jsonl"):
        for q in _qids(p.get("sources", [])):
            add(q, f"Projection '{p['from']}'->'{p['to']}' ({p.get('kind')}, "
                   f"{p.get('neurotransmitter')}): {p.get('label', '')}. {p.get('description', '')}")

    for c in _jsonl("circuits.jsonl"):
        for q in _qids(c.get("sources", [])):
            add(q, f"Functional circuit '{c['name']}': {c.get('description', '')}")

    for g in _jsonl("projection_groups.jsonl"):
        for q in _qids(g.get("sources", [])):
            add(q, f"Projection group '{g['name']}' ({g['mode']}={g['key']}): {g.get('description', '')}")

    for s in _jsonl("structures.jsonl"):
        for q in _qids(s.get("sources", [])):
            add(q, f"Brain structure '{s['name']}' ({s.get('base_name')}) anatomy/existence.")

    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    for tid, t in meta.get("drug_targets", {}).items():
        nm = t.get("name") or tid
        for region, srcs in (t.get("location_sources") or {}).items():
            for q in _qids(srcs):
                add(q, f"Molecular target {nm} is expressed in brain region '{region}'.")
        for k, v in t.items():
            if k == "location_sources":
                continue
            if isinstance(v, dict) and "sources" in v:
                for q in _qids(v["sources"]):
                    add(q, f"Molecular target {nm}: {k}.")
            elif isinstance(v, list):
                for q in _qids(v):
                    add(q, f"Molecular target {nm}: {k}.")

    # Fold any remaining (referenced but unreconstructed) non-Allen quote with a generic claim.
    for qid, q in quotes.items():
        if q["corpus"] not in EXCLUDE_CORPUS and qid not in claims:
            add(qid, "This quote substantiates a receptor/target mechanism classification. "
                     "Confirm it appears verbatim on the page and is a coherent, correct fact.")
    return claims


def cmd_build(args):
    quotes = {q["id"]: q for q in _jsonl("quotes.jsonl")}
    claims = reconstruct_claims(quotes)
    groups = collections.defaultdict(list)
    for qid in claims:
        q = quotes[qid]
        groups[(q["corpus"], str(q["page"]))].append(qid)

    page_cache = {}

    def page_text(corpus, page):
        key = (corpus, page)
        if key not in page_cache:
            page_dir = PAGE_DIR.get(corpus)
            fn = os.path.join(ROOT, page_dir, f"{page}.md") if page_dir else None
            page_cache[key] = (open(fn, encoding="utf-8", errors="replace").read()
                               if fn and os.path.exists(fn) else None)
        return page_cache[key]

    batches, cur = [], {"items": [], "pages": {}}
    for (corpus, page), qidlist in sorted(groups.items()):
        pref = f"{corpus}:{page}"
        if len(cur["items"]) + len(qidlist) > MAX_Q or len(cur["pages"]) >= MAX_P:
            if cur["items"]:
                batches.append(cur)
            cur = {"items": [], "pages": {}}
        cur["pages"][pref] = page_text(corpus, page)
        for qid in qidlist:
            item = {"qid": qid, "page_ref": pref,
                    "quote": quotes[qid]["quote"], "claims": claims[qid]}
            # Where in the book the passage sits (a heading breadcrumb, derived
            # by tools/fetch/fetch_quote_headers.py). It is the single most useful
            # piece of context for the "supports" half of the verdict: the same
            # sentence under "How the Drug Works" is the book attributing a mechanism
            # to this drug, while under "How Drug Causes Side Effects" it is a rule
            # printed without a subject. Absent for a quote whose heading is unknown.
            if quotes[qid].get("heading"):
                item["heading"] = quotes[qid]["heading"]
            cur["items"].append(item)
    if cur["items"]:
        batches.append(cur)

    os.makedirs(args.out, exist_ok=True)
    for f in glob.glob(os.path.join(args.out, "batch_*.json")):
        os.remove(f)
    for i, b in enumerate(batches):
        b["batch_id"] = i
        json.dump(b, open(os.path.join(args.out, f"batch_{i}.json"), "w"), ensure_ascii=False)
    json.dump({"n_batches": len(batches), "n_quotes": len(claims)},
              open(os.path.join(args.out, "manifest.json"), "w"))
    print(f"built {len(batches)} batches over {len(claims)} quotes -> {args.out}")


def cmd_apply(args):
    quotes = {q["id"]: q for q in _jsonl("quotes.jsonl")}
    claims = {}
    for bf in glob.glob(os.path.join(args.batches, "batch_*.json")):
        for it in json.load(open(bf))["items"]:
            claims[it["qid"]] = it["claims"]

    raw = json.load(open(args.verdicts))
    verdicts = raw.get("verdicts", raw)
    if isinstance(verdicts, list):
        verdicts = {v["qid"]: v for v in verdicts}

    stamped = {q: args.llm for q, v in verdicts.items()
               if v.get("present") and v.get("supports") and q in quotes}
    flagged = []
    for q, v in verdicts.items():
        if q not in quotes or (v.get("present") and v.get("supports")):
            continue
        flagged.append({"qid": q, "corpus": quotes[q]["corpus"], "page": quotes[q]["page"],
                        "heading": quotes[q].get("heading"),
                        "present": v.get("present"), "supports": v.get("supports"),
                        "quote": quotes[q]["quote"], "claims": claims.get(q, []),
                        "note": v.get("note", "")})
    flagged.sort(key=lambda x: (bool(x["present"]), bool(x["supports"])))

    os.makedirs(CACHE, exist_ok=True)
    json.dump(stamped, open(os.path.join(CACHE, "quote_llm.json"), "w"),
              indent=0, sort_keys=True)
    json.dump(flagged, open(os.path.join(CACHE, "quote_recheck_flagged.json"), "w"),
              indent=1, ensure_ascii=False)
    print(f"stamped {len(stamped)} quotes '{args.llm}'; flagged {len(flagged)} for review")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write per-page batch files for the LLM judge")
    b.add_argument("--out", required=True, help="output directory for batch_*.json")
    b.set_defaults(func=cmd_build)
    a = sub.add_parser("apply", help="apply aggregated verdicts -> quote_llm.json + flagged")
    a.add_argument("--batches", required=True, help="the build --out directory")
    a.add_argument("--verdicts", required=True, help="aggregated {verdicts:{qid:{present,supports,note}}}")
    a.add_argument("--llm", default="sonnet", choices=["haiku", "sonnet", "opus"],
                   help="model that judged (stamped on confirmed quotes; default sonnet)")
    a.set_defaults(func=cmd_apply)
    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
