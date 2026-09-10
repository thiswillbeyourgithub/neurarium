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
   Each claim reads ``<citation site> | <claim text>`` (see ``citation_site.py``),
   so a judge rejecting one claim of a quote cited from several places can name
   that one instead of condemning the sentence everywhere it is used.

   Scope it with ``--kinds a,b,c`` (the node kinds to judge, printed per pass),
   ``--unstamped`` (skip what ``quote_llm.json`` already stamps), ``--stamped-by <m>``
   (re-read exactly what model ``m`` vouched for, so a second model corroborates it),
   ``--flagged`` and ``--disputed`` (always re-judge what a previous pass could not
   confirm, or what two models disagree about). A scoped pass is the normal case now
   that the corpus is large: ``apply`` **merges** its verdicts into the three caches
   rather than replacing them, so the kinds it did not look at keep theirs.

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import citation_site as CS  # noqa: E402

# Weakest model first, so a pass can tell a corroboration from a demotion: a second,
# weaker read that confirms a quote adds confidence without lowering the stamp, while a
# weaker read that DOUBTS one is a disagreement to escalate, not a verdict to apply.
LLM_RANK = {m: i for i, m in enumerate(SOURCING_LLMS)}

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


def _labels():
    """``(category id -> label, target id -> display name)``, read from the emitted data.

    The judge is asked whether a sentence supports a claim, so the claim has to be
    written in the words the dataset actually publishes, not in its internal ids. The
    difference is not cosmetic: our ``stimulant`` bucket is labelled "Stimulant /
    wake-promoting", so Stahl's "Wake-promoting agent" supports it and the id does not,
    and a judge shown the id fails a claim the data never made.
    """
    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    cats = meta.get("drug_category_labels") or {}
    targets = {tid: (entry.get("name") or tid)
               for tid, entry in (meta.get("drug_targets") or {}).items()}
    for rec in _jsonl("receptors.jsonl"):
        targets.setdefault(rec["id"], rec.get("name") or rec["id"])
    return cats, targets


def _hours(hl):
    """A half-life record (``{hours, hours_max?}``) as a phrase the judge can weigh."""
    if not hl:
        return "an unstated duration"
    return (f"{hl['hours']}-{hl['hours_max']} hours" if hl.get("hours_max")
            else f"{hl['hours']} hours")


def _load(path, default):
    """Read a cache file, or ``default`` on the first pass that writes it."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default



def _target_facet(key: str) -> str:
    """A drug target's own `sources` list is its *classification* source.

    The applier walks `classification_sources.json`, where the same quote sits under the
    target itself (a non-receptor target states one `type`, so it has no per-attribute
    level), and a site has to read the same from both ends or it addresses nothing.
    """
    return "classification" if key == "sources" else key


# Printed over a quote the claim walk could not reach (a source on a node kind the
# reconstruction does not model, e.g. an uncertainty bullet's own citation). It is a
# prompt, not a claim, so it is deliberately excluded from the co-citation tally below.
UNRECONSTRUCTED_CLAIM = ("This quote is cited as the source of a dataset claim whose "
                         "text could not be reconstructed here. Confirm it appears "
                         "verbatim on the page and states a coherent, correct fact.")


def reconstruct_claims(quotes):
    """``(claims, kinds)``: per quote id, the claim(s) it backs and its node kind."""
    claims = collections.defaultdict(list)
    kinds = {}
    cat_labels, target_names = _labels()
    # The node kind the loop below is filling, read by ``add``. A holder rather than an
    # argument on every call site, because the kinds come in runs (one loop, one kind);
    # it is what lets ``build --kinds`` narrow a rerun to the kinds a pass needs. Coarse
    # on purpose: ``receptor_classification`` covers the four per-attribute tally kinds.
    kind = {"now": None}

    def add(qid, claim, site=None):
        """Record one claim, prefixed by the citation site it is made at.

        The site is what lets a verdict name a claim rather than a sentence: a quote
        cited from three places gets three claims here, and a judge that rejects one
        answers with that one site, so the other two keep their source (see
        ``citation_site.py``, and ``demote_quotes.py --sites``). It rides in the claim
        string rather than in a field of its own so every reader of a batch, the judge
        included, sees it beside the claim it addresses instead of in a parallel list
        that has to be zipped back together.
        """
        if qid in quotes and quotes[qid]["corpus"] not in EXCLUDE_CORPUS:
            kinds.setdefault(qid, kind["now"])
            # `site | text`, not `[site] text`: a site carries brackets of its own
            # (`bindings[5ht2a]`), so a bracketed prefix cannot be split back off it.
            claims[qid].append(f"{site} | {claim}" if site else claim)

    for d in _jsonl("drugs.jsonl"):
        nm = d["name"]
        kind["now"] = "drug_bindings"
        for b in d.get("bindings", []):
            tag = " (tentative)" if b.get("tentative") else ""
            tname = target_names.get(b["target"], b["target"])
            for q in _qids(b.get("sources", [])):
                add(q, f"Drug {nm} acts on target '{tname}' as {b['action']}{tag}.",
                    CS.site("drug", d["id"], f"bindings[{CS.binding_key(b)}]"))
        kind["now"] = "drug_categories"
        for q in _qids(d.get("category_sources", [])):
            cats = [cat_labels.get(c, c) for c in d.get("categories", [])]
            add(q, f"Drug {nm} is classified as {', '.join(cats)}.",
                CS.site("drug", d["id"], "categories"))
        kind["now"] = "drug_nbn"
        for q in _qids(d.get("nbn_sources", [])):
            add(q, f"Drug {nm} Neuroscience-based Nomenclature = '{d.get('nbn')}'.",
                CS.site("drug", d["id"], "nbn"))
        kind["now"] = "drug_brands"
        for br in d.get("brands", []):
            for q in _qids(br.get("sources", [])):
                add(q, f"Drug {nm} is sold under the brand name '{br['name']}'.",
                    CS.site("drug", d["id"], f"brands[{br['name']}]"))
        kind["now"] = "drug_half_life"
        for q in _qids(d.get("half_life_sources", [])):
            add(q, f"Drug {nm} has an elimination half-life of "
                   f"{_hours(d.get('half_life'))}.",
                CS.site("drug", d["id"], "half_life"))
        kind["now"] = "drug_enzymes"
        for e in d.get("enzymes", []):
            tier = f", {e['strength']}" if e.get("strength") else ""
            for q in _qids(e.get("sources", [])):
                add(q, f"Drug {nm} is a {e['role']} of the enzyme "
                       f"{e['enzyme'].upper()}{tier}.",
                    CS.site("drug", d["id"], f"enzymes[{CS.enzyme_key(e)}]"))
        for m in d.get("metabolites", []):
            mn = m.get("name")
            kind["now"] = "drug_metabolites"
            for q in _qids(m.get("sources", [])):
                add(q, f"Drug {nm} has an active metabolite, {mn}.",
                    CS.site("drug", d["id"], f"metabolites[{mn}]"))
            for q in _qids(m.get("half_life_sources", [])):
                add(q, f"{mn}, an active metabolite of {nm}, has an elimination "
                       f"half-life of {_hours(m.get('half_life'))}.",
                    CS.site("drug", d["id"], f"metabolites[{mn}]/half_life"))
            kind["now"] = "drug_metabolite_bindings"
            for mb in m.get("bindings", []):
                mt = target_names.get(mb["target"], mb["target"])
                for q in _qids(mb.get("sources", [])):
                    add(q, f"{mn}, an active metabolite of {nm}, acts on target "
                           f"'{mt}' as {mb['action']}.",
                        CS.site("drug", d["id"],
                                f"metabolites[{mn}]/bindings[{CS.binding_key(mb)}]"))
            kind["now"] = "drug_metabolite_enzyme"
            for fb in m.get("formed_by", []):
                step = f" by {fb['reaction']}" if fb.get("reaction") else ""
                for q in _qids(fb.get("sources", [])):
                    add(q, f"The metabolite {mn} is formed from {nm} by the enzyme "
                           f"{fb['enzyme'].upper()}{step}.",
                        CS.site("drug", d["id"],
                                f"metabolites[{mn}]/formed_by[{fb['enzyme']}]"))

    for r in _jsonl("receptors.jsonl"):
        nm = r["name"]
        kind["now"] = "receptor_classification"
        for attr, info in (r.get("classification") or {}).items():
            for q in _qids(info.get("sources", [])):
                add(q, f"Receptor {nm}: {attr} = '{r.get(attr)}'.",
                    CS.site("receptor", r["id"], "classification", attr))
        kind["now"] = "receptor_locations"
        for region, srcs in (r.get("location_sources") or {}).items():
            for q in _qids(srcs):
                add(q, f"Receptor {nm} is expressed in brain region '{region}'.",
                    CS.site("receptor", r["id"], "locations", region))

    kind["now"] = "projections"
    for p in _jsonl("projections.jsonl"):
        for q in _qids(p.get("sources", [])):
            add(q, f"Projection '{p['from']}'->'{p['to']}' ({p.get('kind')}, "
                   f"{p.get('neurotransmitter')}): {p.get('label', '')}. {p.get('description', '')}",
                CS.site("projection", f"{p['from']}->{p['to']}"))

    kind["now"] = "circuits"
    for c in _jsonl("circuits.jsonl"):
        for q in _qids(c.get("sources", [])):
            add(q, f"Functional circuit '{c['name']}': {c.get('description', '')}",
                CS.site("circuit", c["id"]))

    kind["now"] = "projection_groups"
    for g in _jsonl("projection_groups.jsonl"):
        for q in _qids(g.get("sources", [])):
            add(q, f"Projection group '{g['name']}' ({g['mode']}={g['key']}): {g.get('description', '')}",
                CS.site("group", f"{g['mode']}:{g['key']}"))

    kind["now"] = "structures"
    for s in _jsonl("structures.jsonl"):
        for q in _qids(s.get("sources", [])):
            add(q, f"Brain structure '{s['name']}' ({s.get('base_name')}) anatomy/existence.",
                CS.site("structure", s["id"]))

    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    for tid, t in meta.get("drug_targets", {}).items():
        nm = t.get("name") or tid
        kind["now"] = "target_locations"
        for region, srcs in (t.get("location_sources") or {}).items():
            for q in _qids(srcs):
                add(q, f"Molecular target {nm} is expressed in brain region '{region}'.",
                    CS.site("target", tid, "locations", region))
        kind["now"] = "target_other"
        for k, v in t.items():
            if k == "location_sources":
                continue
            if isinstance(v, dict) and "sources" in v:
                for q in _qids(v["sources"]):
                    add(q, f"Molecular target {nm}: {k}.",
                        CS.site("target", tid, _target_facet(k)))
            elif isinstance(v, list):
                for q in _qids(v):
                    add(q, f"Molecular target {nm}: {k}.",
                        CS.site("target", tid, _target_facet(k)))
    kind["now"] = "addons"
    for a in _jsonl("addons.jsonl"):
        for q in _qids(a.get("sources", [])):
            add(q, f"Annotation on {a['owner_kind']} '{a['owner']}': {a.get('text', '')}",
                CS.site("addon", f"{a['owner_kind']}:{a['owner']}"))


    # Fold any remaining (referenced but unreconstructed) non-Allen quote with a generic claim.
    kind["now"] = "other"
    for qid, q in quotes.items():
        if q["corpus"] not in EXCLUDE_CORPUS and qid not in claims:
            add(qid, UNRECONSTRUCTED_CLAIM)
    # A node backed by SEVERAL quotes is not asking each of them for the whole claim.
    # That is the dataset's own model (a compound value earns its green check only when
    # every part is attested: 5-HT1B's synaptic="both" is one presynaptic quote plus one
    # postsynaptic one, a two-category class is one sentence per category), and a judge
    # shown one quote beside the whole claim rejects the pair that is exactly right. So
    # the claim says out loud how many citations share it, and what to weigh THIS one on.
    shared = collections.Counter()
    for qid, texts in claims.items():
        for text in set(texts):
            # The unreconstructed-claim placeholder is not a claim, it is the same
            # sentence printed over every quote the walk could not reach. Counting it
            # would tell hundreds of unrelated quotes they are co-cited with each other.
            if text != UNRECONSTRUCTED_CLAIM:
                shared[text] += 1
    for texts in claims.values():
        for i, text in enumerate(texts):
            if shared[text] > 1:
                texts[i] = (f"{text} [cited here alongside {shared[text] - 1} other "
                            f"quote(s): judge whether THIS one carries its share of the "
                            f"claim, not whether it carries the whole claim alone]")
    return claims, kinds


def _unjudged_quotes():
    """Quote ids a model picked out of prose and no second model has ever judged.

    Read off the emitted citations rather than guessed: each carries the ``pipeline``
    key its chain of custody resolved to (see provenance.quote_pipeline), and a chain in
    which a model chose the sentence but none judged it is exactly what the rule in
    CLAUDE.md forbids shipping. A quote code copied out of a table has no such failure
    mode and is not selected here.
    """
    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    unjudged = {k for k, steps in (meta.get("quote_pipelines") or {}).items()
                if "extract_llm" in steps and "judge_llm" not in steps}
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


def _quote_llms():
    """``{quote id: model}`` as it stands today: the central override wins over the
    source-level stamp, exactly as ``quote_table`` applies it at emit time."""
    stamps = {q["id"]: q["llm"] for q in _jsonl("quotes.jsonl") if q.get("llm")}
    stamps.update(_load(os.path.join(CACHE, "quote_llm.json"), {}))
    return stamps


def _select(claims, kinds, args):
    """Narrow a build to the quotes this pass actually judges.

    A full rebuild embeds every cited page, so a pass that only needs the kinds nobody
    has ever rechecked (brands, half-lives, metabolites) would otherwise pay for the
    whole corpus. ``--flagged`` is a union, not a filter: the quotes a previous pass
    could not confirm come back whatever else is selected.
    """
    wanted = {k for k in args.kinds.split(",") if k} if args.kinds else None
    keep = {q: c for q, c in claims.items()
            if wanted is None or kinds.get(q) in wanted}
    if wanted is not None:
        unknown = wanted - set(kinds.values())
        if unknown:
            sys.exit(f"unknown --kinds: {', '.join(sorted(unknown))}")
    if args.stamped_by:
        # A quote only one model has ever read is not independently confirmed: a second,
        # different model reading it is what makes the verdict a corroboration.
        stamps = _quote_llms()
        keep = {q: c for q, c in keep.items()
                if stamps.get(q) == args.stamped_by}
    if args.unjudged:
        picked = _unjudged_quotes()
        keep = {q: c for q, c in keep.items() if q in picked}
    if args.unstamped:
        stamped = _load(os.path.join(CACHE, "quote_llm.json"), {})
        keep = {q: c for q, c in keep.items() if q not in stamped}
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
    counts = collections.Counter(kinds.get(q) for q in keep)
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
    claims, kinds = reconstruct_claims(quotes)
    claims = _select(claims, kinds, args)
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
        # The stamp as it stands: the central override, else the source-level one.
        prior = stamped.get(q) or quotes[q].get("llm")
        if v.get("present") and v.get("supports"):
            # Two models confirming a quote beats one, and the stamp names the capability
            # a reader should weigh the quote against, so it keeps the strongest reader it
            # has had. A weaker second pass corroborates; it never demotes.
            if rank >= LLM_RANK.get(prior, -1):
                stamped[q] = args.llm
            disputed.pop(q, None)
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
        stamped.pop(q, None)
        disputed.pop(q, None)
        flagged.append({"qid": q, "corpus": quotes[q]["corpus"], "page": quotes[q]["page"],
                        "heading": quotes[q].get("heading"),
                        "present": v.get("present"), "supports": v.get("supports"),
                        "quote": quotes[q]["quote"], "claims": claims.get(q, []),
                        "note": v.get("note", "")})
    # A row about a quote the dataset no longer cites is dead weight: the sentence was
    # dropped, or repaired into a different one (the id is a content hash, so a repair
    # makes a NEW quote). Left in, it is re-proposed by every pass for ever and reads as
    # an open item that nothing can close.
    flagged = [f for f in flagged if f.get("qid") in quotes]
    disputed = {q: d for q, d in disputed.items() if q in quotes}
    # ``.get``: the carried-over rows come from an older file that may predate a key.
    flagged.sort(key=lambda x: (bool(x.get("present")), bool(x.get("supports"))))

    os.makedirs(CACHE, exist_ok=True)
    json.dump(stamped, open(os.path.join(CACHE, "quote_llm.json"), "w"),
              indent=0, sort_keys=True)
    json.dump(flagged, open(os.path.join(CACHE, "quote_recheck_flagged.json"), "w"),
              indent=1, ensure_ascii=False)
    json.dump(sorted(disputed.values(), key=lambda d: d["qid"]),
              open(os.path.join(CACHE, "quote_recheck_disputed.json"), "w"),
              indent=1, ensure_ascii=False)
    print(f"stamped {len(stamped)} quotes (this pass: '{args.llm}'); "
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
                   help="skip the quotes quote_llm.json already stamps")
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
