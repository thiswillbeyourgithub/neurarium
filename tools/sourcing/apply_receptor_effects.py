#!/usr/bin/env python
"""Gate the ``receptor_effect`` picks and write ``tools/generated_cache/receptor_effects.json``.

Third step of the four-step pipeline (see ``tools/fetch/fetch_receptor_effects.py`` for the
first): an LLM read ``receptor_effects_worklist.json`` and answered by candidate index into
``receptor_effects_judged.json``::

    {"owners": {"h1": [{"effect": "sedation", "mode": "antagonism", "picks": [3],
                        "evidence": {"3": "in_vivo"}}]}}

``evidence`` is the picker's reading of each picked sentence (closed
``EFFECT_EVIDENCE``): ``isolated_tissue`` when it reports only an isolated human tissue
preparation (a vessel ring, a mucosa strip), else ``in_vivo``. It rides each cached
source, and a node whose every source is ``isolated_tissue`` wears the derived
``isolated_tissue`` uncertainty bullet (``data_generators.receptor_effects``).

This applier is the **sole writer** of the cache and rebuilds it from the judged file on
every run (so dropping a pick there, e.g. after a judge reject, drops its node here).
A node lands only when every gate passes, all or nothing per node:

1. the owner is in the worklist AND is still a current receptor / target;
2. ``effect`` / ``mode`` are in the closed vocabularies
   (``data_generators.receptor_effects``), and ``inhibition`` sits on a non-receptor
   target only (a receptor is agonised or antagonised, not inhibited);
3. every picked candidate was offered for that effect (its keyword hit), so a pick
   cannot attach a sentence to an effect it never mentions;
4. every pick carries an ``evidence`` reading from ``EFFECT_EVIDENCE``;
5. every picked sentence is still verbatim on its stored page (``pipeline.gate.PageGate``).

It writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py`` (``--kinds
receptor_effect``) must judge the new citations afterwards, or ``check_data.py`` family 5
fails them as extracted-but-unjudged.

``--unknown-log --model <m>`` then writes, for every receptor the Europe PMC effect
search covered (``fetch_europepmc.py --effect-search``) that still carries no effect
node, its owner-level UNKNOWN entry (``receptor:<id>/effects``) into
``tools/generated_cache/unknown_searches.json``: run it only after the picker has read
every offered candidate and picked none.

Usage (from the repo root)::

    python tools/sourcing/apply_receptor_effects.py --dry-run
    python tools/sourcing/apply_receptor_effects.py
    python tools/sourcing/apply_receptor_effects.py --unknown-log --model opus

Built with the help of Claude Code.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_generators.receptor_effects import (  # noqa: E402
    CACHE, EFFECT_EVIDENCE, RECEPTOR_EFFECT_MODES, RECEPTOR_EFFECTS)
from lib.page_file import page_path  # noqa: E402 (refuses a path-like id)
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from prose_gate import apply_picks, not_offered, run_applier  # noqa: E402
from apply_classification_sources import PROSE_PAGES as _PROSE  # noqa: E402
from data_generators.provenance import corpus_page_path  # noqa: E402
from lib import cache_io  # noqa: E402

# The two prose corpora plus GtoPdb's function pages (corpus #23) and the Europe PMC
# abstracts the owner-level effect search read (corpus #17).
PROSE_PAGES = {**_PROSE, "gtopdb_function": corpus_page_path("gtopdb_function", 0).parent,
               "europepmc": corpus_page_path("europepmc", 0).parent}

WORKLIST = TOOLS / "generated_cache" / "receptor_effects_worklist.json"
JUDGED = TOOLS / "generated_cache" / "receptor_effects_judged.json"


def current_kinds() -> dict[str, str]:
    """``{owner id: "receptor" | "target"}`` for what the dataset models today."""
    out = {}
    for line in (REPO / "public/data/receptors.jsonl").read_text("utf-8").splitlines():
        if line.strip():
            out[json.loads(line)["id"]] = "receptor"
    meta = json.loads((REPO / "public/data/meta.json").read_text("utf-8"))
    for tid, t in meta["drug_targets"].items():
        if isinstance(t, dict):
            out.setdefault(tid, "target")
    return out


def apply(worklist: dict, judged: dict, kinds: dict[str, str],
          pages: dict = PROSE_PAGES) -> tuple[dict, list[str]]:
    """``(cache, misses)``: the rebuilt ``{owner: {"mode:effect": [source]}}`` cache."""
    def check(oid, node, cands):
        mode, effect = node.get("mode"), node.get("effect")
        key = f"{mode}:{effect}"
        if mode not in RECEPTOR_EFFECT_MODES or effect not in RECEPTOR_EFFECTS:
            return key, "mode or effect outside the closed vocabulary"
        if mode == "inhibition" and kinds[oid] == "receptor":
            return key, "'inhibition' is a non-receptor target's mode"
        off = not_offered(cands, node.get("picks"), "effects", effect)
        if off:
            return key, f"candidate(s) {off} were not offered for {effect!r}"
        evidence = node.get("evidence") or {}
        unread = [p.get("index") for p in node.get("picks") or []
                  if evidence.get(str(p.get("index"))) not in EFFECT_EVIDENCE]
        if unread:
            return key, f"pick(s) {unread} carry no evidence reading in {EFFECT_EVIDENCE}"
        return key, None
    def stamp(node, pick, src):  # each landed source carries its pick's evidence reading
        src["evidence"] = node["evidence"][str(pick["index"])]
    return apply_picks(worklist, judged, kinds, check, pages, stamp)


def unknown_log(worklist: dict, cache: dict, kinds: dict[str, str], ledger: dict,
                by: dict, prior: dict | None = None) -> dict:
    """The receptor-effect UNKNOWN entries (``data_generators/unknown.py``): one per
    owner the Europe PMC effect search covered that still carries no effect node, its
    four legs read off the worklist (what each corpus offered the picker, none of it
    picked) and the search ledger. Other kinds' entries in ``prior`` are kept; an owner
    that has since gained an effect loses its entry."""
    sys.path.insert(0, str(TOOLS / "fetch"))
    import fetch_gtopdb_function as gfunc                   # noqa: E402 (RAW, offerable)
    import fetch_receptor_effects as fre                    # noqa: E402 (owner_names)
    from lib import target_aliases                                   # noqa: E402
    from data_generators.unknown import effects_site       # noqa: E402
    aliases = target_aliases.aliases_by_target()
    log = dict(prior or {})
    for oid, kind in sorted(kinds.items()):
        site = effects_site(kind, oid)
        hit = ledger.get(site)
        if not hit or cache.get(oid):
            if log.get(site, {}).get("kind") == "receptor_effect":
                log.pop(site)
            continue
        owner = (worklist.get("owners") or {}).get(oid) or {}
        cands = owner.get("candidates") or []
        offered = {c: sum(1 for x in cands if x["corpus"] == c)
                   for c in ("wikipedia_pharm", "gtopdb_function", "stahl_essential",
                             "europepmc")}
        none = "offered to the picker, none states an effect of acting on it in humans"
        raw = page_path(gfunc.RAW, oid, ".json")
        lines = (json.loads(raw.read_text("utf-8")).get("lines") or []) if raw.exists() else []
        slug = (owner.get("wikipedia") or "").rstrip("/").rsplit("/", 1)[-1] or "none"
        log[site] = {
            "kind": "receptor_effect", "searched": hit["searched"],
            "by": {"harness": by["harness"], "model": by["model"]},
            "candidates_offered": len(cands),
            "sources": [
                {"corpus": "wikipedia_pharm", "hits": offered["wikipedia_pharm"],
                 "lookup": f"article {slug}: every sentence with a closed-vocabulary "
                           "effect keyword", "note": none},
                {"corpus": "gtopdb_function", "hits": offered["gtopdb_function"],
                 "lookup": f"function / pathophysiology / altered-expression rows of "
                           f"{oid}: human or species-less lines with an effect keyword",
                 "note": f"{len(lines)} line(s), "
                         f"{sum(1 for x in lines if gfunc.offerable(x))} human or "
                         f"species-less; {none}"},
                {"corpus": "stahl_essential", "hits": offered["stahl_essential"],
                 "lookup": "every page: sentences naming "
                           f"{', '.join(fre.owner_names(oid, aliases)) or oid} with an "
                           "effect keyword", "note": none},
                {"corpus": "europepmc", "hits": hit["hits"], "query": hit["query"],
                 "read": hit["read"], "offered": offered["europepmc"], "note": none}]}
    return log


def _main_unknown_log() -> int:
    import argparse
    sys.path.insert(0, str(TOOLS / "fetch"))
    import fetch_europepmc as epmc                          # noqa: E402
    from data_generators import unknown                     # noqa: E402
    ap = argparse.ArgumentParser(description="write the receptor-effect UNKNOWN entries")
    ap.add_argument("--unknown-log", action="store_true")
    ap.add_argument("--model", required=True, choices=("sonnet", "opus"),
                    help="the model that read the offered candidates and picked none")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    log = unknown_log(worklist_io.read(WORKLIST),
                      json.loads(CACHE.read_text("utf-8")), current_kinds(),
                      json.loads(epmc.EFFECT_SEARCH_LEDGER.read_text("utf-8")),
                      {"harness": "Claude Code", "model": args.model}, unknown.load_log())
    n = sum(1 for e in log.values() if e.get("kind") == "receptor_effect")
    print(f"  UNKNOWN log: {n} receptor_effect owner(s)")
    if not args.dry_run:   # entries keep their order (a small diff), fields sorted
        cache_io.write(unknown.UNKNOWN_LOG_PATH, log)
    return 0


def main() -> int:
    if "--unknown-log" in sys.argv:
        return _main_unknown_log()
    return run_applier(__doc__, WORKLIST, JUDGED, CACHE,
                       lambda w, j: apply(w, j, current_kinds()), "receptor_effect")


if __name__ == "__main__":
    raise SystemExit(main())
