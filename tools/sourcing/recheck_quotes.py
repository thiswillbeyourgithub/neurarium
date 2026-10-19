#!/usr/bin/env python3
"""Recheck the emitted verified quotes with a stronger LLM and stamp the sourcing model.

Every ``verified`` quote in ``public/data/quotes.jsonl`` was extracted+judged by some
LLM (historically often Haiku). This harness re-verifies each quote with a chosen model
(Sonnet by default) and records *which* model confirmed it, so a reader can weigh a quote
by the capability of the model that vouched for it (see CLAUDE.md "The sourcing model").

The output is a central ``tools/generated_cache/quote_llm.json`` map
``{quote_id: {citation site: llm}}``, applied at generation time by
``data_generators.quote_table.finalize_citations``, so ONE recheck pass stamps every kind of
quote without editing each authoring site. A stamp is keyed to the sites the judge was shown
(the ``site | claim`` lines of its batch): a site added later reusing the same sentence is
NOT covered, reads unjudged, and fails ``check_data.py`` until a pass judges it. Quotes the recheck could not fully confirm are written to
``quote_recheck_flagged.json`` for human review (they are NOT stamped).

Token cost is minimized by batching: quotes are grouped by source page so each page's
OCR'd text is loaded ONCE per batch and shared by all its quotes.

Three steps (the middle one is the only LLM spend):

1. ``python tools/sourcing/recheck_quotes.py build --out <dir>``
   Reconstructs, for every non-Allen quote, the claim(s) it backs (Allen AHBA quotes are
   deterministic PACall confirmations, not LLM-sourced, so they are excluded) and writes
   ``<dir>/batch_<i>.json`` (each: ``{pages: {ref: text}, items: [{qid, page_ref, quote,
   claims, heading?}]}``) + ``manifest.json``.
   Each claim reads ``<citation site> | <claim text>`` (see ``citation_site.py``),
   so a judge rejecting one claim of a quote cited from several places can name
   that one instead of condemning the sentence everywhere it is used.

   Scope it with ``--kinds a,b,c`` (the node kinds to judge, printed per pass),
   ``--unstamped`` (skip the sites ``quote_llm.json`` already stamps; every selector decides per citation site), ``--stamped-by <m>``
   (re-read exactly what model ``m`` vouched for, so a second model corroborates it),
   ``--flagged`` and ``--disputed`` (always re-judge what a previous pass could not
   confirm, or what two models disagree about). A scoped pass is the normal case now
   that the corpus is large: ``apply`` **merges** its verdicts into the three caches
   rather than replacing them, so the kinds it did not look at keep theirs.

2. Judge each batch with the chosen model. This project ran it as a Workflow: one agent
   per batch reads its file and returns, per item, ``{qid, present, supports, note?}``
   against the embedded page text (present allowing OCR noise; supports = the quote
   substantiates the claim). Aggregate every agent's ``verdicts`` into one JSON object
   ``{"verdicts": {qid: {present, supports, note?, rejected_sites?}}}``. A verdict may
   name ``rejected_sites`` (the ``site`` prefixes of the claims the quote does NOT back):
   the other sites shown are then stamped, and only those are flagged.

   **Tell the judge what ``heading`` means**, because it decides the harder half of the
   verdict: it is where in the book the passage sits (a breadcrumb of headings,
   outermost first), and Stahl's sections are not interchangeable. A sentence under
   *How the Drug Works*
   is the book attributing a mechanism to that drug; the same sentence under *How Drug
   Causes Side Effects* is a rule printed with the mechanism, not the drug, as its
   subject, so it does not by itself say this drug has the action (that distinction is
   what the "uncertain" badges rest on, see docs/PROVENANCE.md). ``supports``
   should be false when the claim needs an attribution the section cannot give.

3. ``python tools/sourcing/recheck_quotes.py apply --batches <dir> --verdicts <file> [--llm sonnet]``
   Writes ``quote_llm.json`` (present AND supports -> stamped) +
   ``quote_recheck_flagged.json`` + ``quote_recheck_disputed.json``.

   A stamp names the STRONGEST model that has confirmed a quote, so a weaker second
   pass can only corroborate: it never lowers one. The mirror of that rule is that a
   weaker model doubting a quote is a *disagreement*, not a verdict, so it lands in
   ``quote_recheck_disputed.json`` with the stamp untouched. Re-running the stamping
   model over it (``build --disputed`` then ``apply --llm <that model>``) is the only
   thing that settles it: confirmed clears the dispute, doubted un-stamps and flags.

Then regenerate (``python tools/generate_data.py``) and check. Made with the help of Claude Code.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "public", "data")
CACHE = os.path.join(ROOT, "tools", "generated_cache")

sys.path.insert(0, os.path.join(ROOT, "tools"))
from data_generators.provenance import SOURCING_LLMS  # noqa: E402
from lib.page_file import read_page  # noqa: E402 (the raw page reader, refuses a path-like page)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.quote_match import emitted_page_dirs  # noqa: E402
from lib.io_atomic import atomic_write_json  # noqa: E402
# The claim walk lives in its own module (the generator runs it too); re-exported here
# because this is where the judge's side of it is read and tested.
from claim_walk import (  # noqa: E402,F401
    UNCERTAINTY_REASONS, UNPLACED, UNRECONSTRUCTED_CLAIM, _doubts, _hours,
    _jsonl,
    reconstruct_claims, site_of)

# Weakest model first, so a pass can tell a corroboration from a demotion: a second,
# weaker read that confirms a quote adds confidence without lowering the stamp, while a
# weaker read that DOUBTS one is a disagreement to escalate, not a verdict to apply.
LLM_RANK = {m: i for i, m in enumerate(SOURCING_LLMS)}

# corpus -> author-side page directory (the same trees check_data.py's quote gate reads),
# read off the emitted registry rather than a hardcoded map, which once went stale.
# Allen AHBA is intentionally absent from the judging (claim_walk.EXCLUDE_CORPUS).
PAGE_DIR = emitted_page_dirs()
MAX_Q, MAX_P = 22, 7  # per-batch caps (quotes, distinct pages)



def _load(path, default):
    """Read a cache file, or ``default`` on the first pass that writes it."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default




def _unjudged_pipelines():
    """The ``pipeline`` keys whose chain has a model choosing the sentence and none judging it.

    Read off the emitted registry rather than guessed (see provenance.quote_pipeline): such
    a chain is exactly what the rule in CLAUDE.md forbids shipping. A quote code copied out
    of a table has no such failure mode and is never selected by ``--unjudged``.
    """
    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    return {k for k, steps in (meta.get("quote_pipelines") or {}).items()
            if "extract_llm" in steps and "judge_llm" not in steps}


def _unjudged_quotes(unjudged):
    """Quote ids with at least one emitted citation whose ``pipeline`` is in ``unjudged``.

    Quote-level on purpose: it answers only for a claim the walk could not place (site
    :data:`UNPLACED`); a placed claim is decided per site (see :func:`_select`).
    """
    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    found = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("pipeline") in unjudged and node.get("quote_id"):
                found.add(node["quote_id"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(meta)
    for name in sorted(os.listdir(DATA)):
        if name.endswith(".jsonl") and name != "quotes.jsonl":
            for row in _jsonl(name):
                walk(row)
    return found


def _strongest(models):
    """The strongest of ``models`` by :data:`LLM_RANK`, or ``None``."""
    known = [m for m in models if m in LLM_RANK]
    return max(known, key=LLM_RANK.get) if known else None


def _site_llm(quotes, stamped):
    """``site_llm(qid, site)``: the strongest model that judged ``qid`` AT ``site``.

    The central per-site stamp; a quote with no central stamp at all falls back to its
    quote node's source-level ``llm`` (stamped by the pass that wrote that source).
    """
    def site_llm(qid, site):
        if qid in stamped:
            return stamped[qid].get(site)
        return quotes.get(qid, {}).get("llm")
    return site_llm


def _select(claims, site_kinds, args, quotes=None, unjudged_sites=frozenset()):
    """Narrow a build to the (quote, citation site) pairs this pass actually judges.

    A full rebuild embeds every cited page, so a pass that only needs the kinds nobody
    has ever rechecked (brands, half-lives, metabolites) would otherwise pay for the
    whole corpus. Every narrowing selector is ONE predicate on ``(qid, site)`` and
    filters claim lines, never whole quotes: a stamp is keyed per site, so a quote judged
    for one claim and newly cited at another (norzimelidine's binding reusing the
    sentence judged for zimelidine's metabolite) must come back for exactly the new site,
    whatever kind the quote was first seen under. ``site_kinds`` is ``{(qid, site):
    kind}`` (see ``reconstruct_claims``), ``unjudged_sites`` the placed pairs whose
    emitted citation reads unjudged. ``--flagged`` is a union, not a filter: the quotes
    a previous pass could not confirm come back whatever else is selected.
    """
    stamped = _load(os.path.join(CACHE, "quote_llm.json"), {})
    preds = []
    if args.kinds:
        wanted = {k for k in args.kinds.split(",") if k}
        unknown = wanted - set(site_kinds.values())
        if unknown:
            sys.exit(f"unknown --kinds: {', '.join(sorted(unknown))}")
        preds.append(lambda q, s: site_kinds.get((q, s)) in wanted)
    if args.stamped_by:
        # A quote only one model ever read is not independently confirmed: a second,
        # different model reading it is what makes the verdict corroboration.
        site_llm = _site_llm(quotes or {}, stamped)
        preds.append(lambda q, s: site_llm(q, s) == args.stamped_by)
    if args.unjudged:
        unplaced = _unjudged_quotes(_unjudged_pipelines())
        preds.append(lambda q, s: (q, s) in unjudged_sites
                     or (s == UNPLACED and q in unplaced))
    if args.unstamped:
        # A site added since the last pass is exactly what a stamp must not silently cover.
        preds.append(lambda q, s: s not in stamped.get(q, {}))
    keep = {}
    for q, lines in claims.items():
        kept = [t for t in lines if all(p(q, site_of(t)) for p in preds)]
        if kept:
            keep[q] = kept

    # The RESTRICTIVE forms: judge that list and nothing else. A re-extraction or a
    # dispute-settling pass has one question about a handful of quotes ("is there a
    # better sentence on this page", "the stamping model is asked again"), so every
    # other quote is noise in the batch and, at 3000-odd of them, unaffordable noise.
    for flag, fname in (("only_flagged", "quote_recheck_flagged.json"),
                        ("only_disputed", "quote_recheck_disputed.json")):
        if not getattr(args, flag):
            continue
        qids = {row.get("qid") for row in _load(os.path.join(CACHE, fname), [])}
        keep = {q: c for q, c in claims.items() if q in qids}
    for flag, fname in (("flagged", "quote_recheck_flagged.json"),
                        ("disputed", "quote_recheck_disputed.json")):
        if not getattr(args, flag):
            continue
        for row in _load(os.path.join(CACHE, fname), []):
            if row.get("qid") in claims:
                keep[row["qid"]] = claims[row["qid"]]
    counts = collections.Counter(site_kinds.get((q, site_of(t)))
                                 for q, lines in keep.items() for t in lines)
    print("selected " + ", ".join(f"{k}={n}" for k, n in sorted(counts.items(),
                                                               key=lambda kv: str(kv[0]))))
    return keep



def _locate(text, quote):
    """``(start, end)`` of ``quote`` in ``text``, or ``(-1, -1)``.

    Exact first, then a whitespace-tolerant match: the stored pages carry the line breaks
    of a PDF split or a flattened article, and a quote is one sentence out of them.
    """
    i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    m = re.search(r"\s+".join(map(re.escape, quote.split())), text, re.I)
    return (m.start(), m.end()) if m else (-1, -1)


def _excerpt(text, quotes, cap):
    """The page as the judge needs to see it: whole when small, else the neighbourhoods.

    A book page is a page, and fits. A stored Wikipedia article is the WHOLE article (up
    to 700 KB), and pasting one into a judge's context buys nothing: the verbatim half of
    the verdict is settled offline by ``check_data.py``'s gate, and the half that is not
    (does this sentence support the claim?) is decided by the paragraphs around the
    sentence, not by the other forty sections.
    """
    if text is None or len(text) <= cap:
        return text
    window = max(cap // (2 * max(len(quotes), 1)), 600)
    spans = []
    for q in quotes:
        a, b = _locate(text, q)
        if a >= 0:
            spans.append([max(0, a - window), min(len(text), b + window)])
    if not spans:
        return text[:cap] + "\n[... page truncated ...]"
    spans.sort()
    merged = [spans[0]]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return "\n[... elided ...]\n".join(text[a:b] for a, b in merged)


def cmd_build(args):
    quotes = {q["id"]: q for q in _jsonl("quotes.jsonl")}
    unjudged, unjudged_sites, site_kinds = _unjudged_pipelines(), set(), {}

    def on_cite(site, ref):
        if ref.get("pipeline") in unjudged:
            unjudged_sites.add((ref["quote_id"], site))
    claims, _ = reconstruct_claims(quotes, on_cite=on_cite, site_kinds=site_kinds)
    claims = _select(claims, site_kinds, args, quotes, unjudged_sites)
    if not claims:
        sys.exit("nothing to build: every selected quote is filtered out")
    groups = collections.defaultdict(list)
    for qid in claims:
        q = quotes[qid]
        groups[(q["corpus"], str(q["page"]))].append(qid)

    page_cache = {}

    def page_text(corpus, page):
        key = (corpus, page)
        if key not in page_cache:
            page_dir = PAGE_DIR.get(corpus)
            page_cache[key] = read_page(os.path.join(ROOT, page_dir) if page_dir else None,
                                        page)
        return page_cache[key]

    batches, cur = [], {"items": [], "pages": {}}
    for (corpus, page), qidlist in sorted(groups.items()):
        pref = f"{corpus}:{page}"
        if len(cur["items"]) + len(qidlist) > MAX_Q or len(cur["pages"]) >= MAX_P:
            if cur["items"]:
                batches.append(cur)
            cur = {"items": [], "pages": {}}
        cur["pages"][pref] = _excerpt(page_text(corpus, page),
                                     [quotes[q]["quote"] for q in qidlist],
                                     args.max_page_chars)
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

    stamped = _load(os.path.join(CACHE, "quote_llm.json"), {})
    disputed = {d["qid"]: d for d in
                _load(os.path.join(CACHE, "quote_recheck_disputed.json"), [])}
    # Merge, never overwrite: a scoped pass (``build --kinds``) re-judges part of the
    # corpus, so the stamps, disputes and flags it did not look at must survive it, while
    # the ones it did look at take this pass's verdict.
    judged = {q for q in verdicts if q in quotes}
    flagged = [f for f in _load(os.path.join(CACHE, "quote_recheck_flagged.json"), [])
               if f.get("qid") not in judged]
    rank = LLM_RANK.get(args.llm, -1)
    for q in sorted(judged):
        v = verdicts[q]
        # The stamp keyed to each site this judge was shown (the claim lines it read):
        # a verdict covers those claims and no other (see claim_walk.py).
        sites = {site_of(t) for t in claims.get(q, [])} or {UNPLACED}
        held = stamped.get(q, {})
        # The stamp as it stands: the strongest per-site one, else the source-level one.
        prior = _strongest(held.values()) or quotes[q].get("llm")
        # A split verdict names the sites it rejects (``rejected_sites``): the others
        # it was shown are confirmed, and only those are flagged for demotion.
        rejected = set(v.get("rejected_sites") or []) & sites
        split = bool(v.get("present") and rejected and rejected != sites)
        if v.get("present") and (v.get("supports") or split):
            # Two models confirming a quote beats one, and the stamp names the capability
            # a reader should weigh the quote against, so it keeps the strongest reader it
            # has had. A weaker second pass corroborates; it never demotes.
            held = dict(held)
            for site in sites - rejected:
                held[site] = _strongest([held.get(site), args.llm])
            stamped[q] = held
            disputed.pop(q, None)
            if not split:
                continue
        if rank < LLM_RANK.get(prior, -1):
            # A weaker model contradicting a stronger one is a disagreement, not a
            # verdict. The stamp stands until the stronger model is asked again
            # (``build --disputed`` then ``apply --llm <that model>``), which is the only
            # thing that can settle it either way.
            disputed[q] = {"qid": q, "stamped": prior, "doubted_by": args.llm,
                           "corpus": quotes[q]["corpus"], "page": quotes[q]["page"],
                           "present": v.get("present"), "supports": v.get("supports"),
                           "quote": quotes[q]["quote"], "claims": claims.get(q, []),
                           "note": v.get("note", "")}
            continue
        row = {"qid": q, "corpus": quotes[q]["corpus"], "page": quotes[q]["page"],
               "heading": quotes[q].get("heading"),
               "present": v.get("present"), "supports": v.get("supports"),
               "quote": quotes[q]["quote"], "claims": claims.get(q, []),
               "note": v.get("note", "")}
        if split:
            # Only the rejected sites lose their stamp; ``demote_quotes.py --flagged``
            # removes the source at exactly these sites.
            stamped[q] = {k: m for k, m in stamped[q].items() if k not in rejected}
            row["sites"] = sorted(rejected)
        else:
            stamped.pop(q, None)
            disputed.pop(q, None)
        flagged.append(row)
    # A row about a quote the dataset no longer cites is dead weight: the sentence was
    # dropped, or repaired into a different one (the id is a content hash, so a repair
    # makes a NEW quote). Left in, it is re-proposed by every pass for ever and reads as
    # an open item that nothing can close.
    flagged = [f for f in flagged if f.get("qid") in quotes]
    disputed = {q: d for q, d in disputed.items() if q in quotes}
    # ``.get``: the carried-over rows come from an older file that may predate a key.
    flagged.sort(key=lambda x: (bool(x.get("present")), bool(x.get("supports"))))

    atomic_write_json(os.path.join(CACHE, "quote_llm.json"), stamped,
                      trailing_newline=False, indent=0, sort_keys=True)
    atomic_write_json(os.path.join(CACHE, "quote_recheck_flagged.json"), flagged,
                      trailing_newline=False, indent=1)
    atomic_write_json(os.path.join(CACHE, "quote_recheck_disputed.json"),
                      sorted(disputed.values(), key=lambda d: d["qid"]),
                      trailing_newline=False, indent=1)
    print(f"stamped {sum(map(len, stamped.values()))} sites over {len(stamped)} quotes "
          f"(this pass: '{args.llm}'); "
          f"flagged {len(flagged)}, disputed {len(disputed)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write per-page batch files for the LLM judge")
    b.add_argument("--out", required=True, help="output directory for batch_*.json")
    b.add_argument("--max-page-chars", type=int, default=24000,
                   help="embed only the quotes' neighbourhoods on a page longer than this")
    b.add_argument("--kinds", default="",
                   help="comma-separated node kinds to judge (default: every kind)")
    b.add_argument("--stamped-by", default="", choices=("", "haiku", "sonnet", "opus"),
                   help="judge only the quotes this model stamped (a second, corroborating read)")
    b.add_argument("--unjudged", action="store_true",
                   help="judge only the quotes a model PICKED and none has judged "
                        "(the state check_data.py fails on)")
    b.add_argument("--unstamped", action="store_true",
                   help="skip the citation sites quote_llm.json already stamps")
    b.add_argument("--only-flagged", action="store_true",
                   help="judge ONLY the flagged quotes (a re-extraction pass: pair it "
                        "with a large --max-page-chars so the whole page is offered)")
    b.add_argument("--only-disputed", action="store_true",
                   help="judge ONLY the disputed quotes (run this with --llm set to the "
                        "model that stamped them, to settle the disagreement)")
    b.add_argument("--flagged", action="store_true",
                   help="also judge every quote in quote_recheck_flagged.json")
    b.add_argument("--disputed", action="store_true",
                   help="also judge every quote in quote_recheck_disputed.json (run this "
                        "with --llm set to the model that stamped them, to settle it)")
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
