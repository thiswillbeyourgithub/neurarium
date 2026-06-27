#!/usr/bin/env python
"""Integrity checks over the emitted dataset (``public/data/``).

This validates the committed data files that the static site actually serves
(``meta.json`` + ``structures`` / ``projections`` / ``circuits`` / ``receptors``
/ ``drugs`` ``.jsonl``), independently of ``generate_data.py``. The generator
already raises on most of these at build time; running the same checks over the
*emitted* artifacts is a cheap regression guard that also catches generator/data
drift and the duplicate/TODO classes the generator does not look for.

Run it directly (stdlib only, no deps, like ``generate_data.py``):

    python tools/check_data.py

Exit status is ``0`` when there are no errors (warnings are allowed) and ``1``
when any error is found, so it is usable as a gate (see the pre-push hook in
``tools/git-hooks/``).

Six families of checks:

1. **Duplicates** (per collection). An exact duplicate id/key, or two ids that
   collide once **normalized** (lowercased, every non-alphanumeric character
   stripped: ``mao_a`` and ``mao-a`` -> ``maoa``), is an **error**. Two entries
   whose **display names** collide once normalized is a **warning** (a likely
   accidental re-entry to eyeball, but occasionally legitimate). Projections have
   no id, so they are checked for duplicate ``from -> to`` endpoints instead.

2. **Reachability** (referential integrity). Every cross-reference must resolve
   or the detail is **unreachable** in the viewer. The canonical case: a drug
   binding whose ``target`` is not a key of ``meta.drug_targets`` can never be
   focused from its panel. This also covers every receptor ``location`` / target
   ``region``: it must name a structure **base** present in the atlas, otherwise
   its "Found in" row in the panel would point at nothing and so be **unclickable**.
   All dangling references are **errors**.

3. **TODOs**. A literal ``"TODO"`` placeholder anywhere **outside** a source url
   (e.g. a binding ``note`` left as TODO), plus any focusable target with no
   ``wikipedia`` (the viewer shows a TODO pill), is a **warning**. Source urls
   left as ``"TODO"`` are counted and warned about **separately** (they are a
   known, tracked backlog rather than a stray placeholder).

4. **Provenance grades**. Every emitted source (a ``sources[].provenance``,
   including the per-binding drug sources) and every wikipedia reference (a
   ``wikipedia_provenance`` beside a ``wikipedia``) must carry a known grade
   (``llm`` / ``sourced`` / ``verified``), the value the viewer renders as a
   grey/yellow/green pill. An unknown or missing grade is an **error** (the pill
   would fall back to "no source" and mislead).

5. **Source quotes**. Each per-binding drug source is
   ``{corpus, page, quote, provenance}``; a ``"verified"`` grade is the one that
   claims the quote was confirmed present in the source. This re-confirms it: the
   ``corpus`` must resolve to ``meta.source_corpora``, a verified source must
   carry a page + quote, and the **normalized** quote must be an exact substring
   of the **normalized** cited page text (``<pages_dir>/<page>.md``). The page
   material is author-side and may be absent on a clone (see ``stahl/`` in
   CLAUDE.local.md); the quote-in-page check is then **skipped with a warning**
   while the structural checks still run. A quote that is genuinely not on its
   page (an invented or mistyped extraction) is an **error**, so this is the gate
   that keeps the LLM extraction honest.

6. **Structure connectivity**. Warns (never errors) about a structure the
   connectome leaves stranded or one-sided: **isolated** (no projection touches
   it), **inward-only** (receives but never projects out), or **outward-only**
   (projects out but never receives, e.g. the modeled ascending source nuclei).
   An eyeball list for the author, not a gate.

Built with the help of Claude Code.
"""

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data"
# Repo root, used to resolve a source corpus's author-side ``pages_dir`` (e.g.
# ``stahl/pages``) for the quote-in-page check (see check_sources).
REPO_ROOT = DATA_DIR.parent.parent

# A path like "...sources[3].url" (a citation) or "...source_corpora.<id>.url" (a
# corpus reference) is a source url: its TODO is the known backlog, reported on
# its own. Anything else is a stray TODO.
_SOURCE_URL_RE = re.compile(r"(\.sources\[\d+\]\.url|\.source_corpora\.[^.]+\.url)$")
# Trailing hemisphere suffix on a structure id ("frontal_R" -> "frontal").
_HEMISPHERE_RE = re.compile(r"_(R|L)$")
# Valid source provenance grades (mirrors generate_data.py PROVENANCE_LEVELS), the
# value the viewer renders as the grey/yellow/green source pill.
_PROVENANCE_LEVELS = {"llm", "sourced", "verified"}


class Report:
    """Collects errors/warnings while printing each section as it runs."""

    def __init__(self):
        self.errors = 0
        self.warnings = 0

    def header(self, title):
        print(f"\n{title}\n{'-' * len(title)}")

    def ok(self, msg):
        print(f"  [ok]    {msg}")

    def error(self, msg):
        self.errors += 1
        print(f"  [ERROR] {msg}")

    def warn(self, msg):
        self.warnings += 1
        print(f"  [warn]  {msg}")


def normalize(value):
    """Lowercase and keep only alphanumeric characters (Unicode-aware, so a
    Greek receptor name like ``α1A`` collapses to ``α1a`` rather than vanishing).
    Two strings that normalize equal are "the same entry" for the dup check."""
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def normalize_for_match(text):
    """Canonicalize prose for the quote-in-page substring check (see check_sources).

    The PDF->Markdown extraction of the source pages introduces artifacts the raw
    quote will not match verbatim: hard-wrapped lines (a word hyphenated across a
    line break), markdown emphasis/bullets, curly quotes, en/em dashes, accents.
    This folds all of that away deterministically: join hyphenated line breaks,
    NFKD-decompose (so an accent becomes a strippable combining mark), lowercase,
    then collapse every run of non-alphanumerics to a single space. The result is
    still compared with an **exact** substring test, only on a canonical form: no
    fuzzy / similarity matching, which would manufacture false confidence. A miss
    is therefore a real miss to investigate, not a threshold to tune."""
    text = re.sub(r"-\s*\n\s*", "", text)            # join hyphenated line breaks
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)          # drops combining marks too
    return " ".join(text.split())


def display_name(name):
    """A display name is either a plain string (receptors, drugs) or an
    ``{en, fr}`` object (structures, circuits, targets); use the English text."""
    if isinstance(name, dict):
        return name.get("en")
    return name


def load_jsonl(report, name):
    path = DATA_DIR / f"{name}.jsonl"
    records = []
    if not path.exists():
        report.error(f"missing data file: {path}")
        return records
    for lineno, line in enumerate(path.open(encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            report.error(f"{name}.jsonl:{lineno}: invalid JSON ({exc})")
    return records


def load_meta(report):
    path = DATA_DIR / "meta.json"
    if not path.exists():
        report.error(f"missing data file: {path}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"meta.json: invalid JSON ({exc})")
        return {}


def walk_strings(obj, path):
    """Yield ``(json_path, string_value)`` for every string anywhere in ``obj``,
    so the TODO scan can both find placeholders and tell *where* they sit."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk_strings(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walk_strings(value, f"{path}[{index}]")
    elif isinstance(obj, str):
        yield path, obj


# --------------------------------------------------------------------------- #
# 1. Duplicates
# --------------------------------------------------------------------------- #

def check_id_collection(report, label, items, id_key="id", name_key="name"):
    """Exact + normalized duplicate ids (errors) and normalized duplicate display
    names (warnings) within one id-bearing collection."""
    ids = [item.get(id_key) for item in items]

    exact = {value: count for value, count in Counter(ids).items() if count > 1}
    for value, count in sorted(exact.items(), key=lambda kv: str(kv[0])):
        report.error(f"{label}: id {value!r} appears {count} times")

    by_norm_id = defaultdict(set)
    for value in ids:
        by_norm_id[normalize(value)].add(value)
    near = [raws for raws in by_norm_id.values() if len(raws) > 1]
    for raws in sorted(near, key=lambda s: sorted(map(str, s))):
        report.error(f"{label}: ids collide once normalized: {sorted(raws)}")

    by_norm_name = defaultdict(set)
    for item in items:
        name = display_name(item.get(name_key))
        if name:
            by_norm_name[normalize(name)].add(item.get(id_key))
    name_dups = {(nk, frozenset(idset)) for nk, idset in by_norm_name.items() if len(idset) > 1}
    for nk, idset in sorted(name_dups, key=lambda kv: kv[0]):
        report.warn(f"{label}: ids {sorted(idset)} share normalized name {nk!r}")

    if not exact and not near and not name_dups:
        report.ok(f"{label}: {len(items)} entries, no duplicate ids or names")


def check_projection_dups(report, projections):
    pairs = Counter((p.get("from"), p.get("to")) for p in projections)
    dups = {pair: count for pair, count in pairs.items() if count > 1}
    for (src, dst), count in sorted(dups.items(), key=lambda kv: str(kv[0])):
        report.error(f"projections: {src} -> {dst} defined {count} times")
    if not dups:
        report.ok(f"projections: {len(projections)} pathways, no duplicate from->to")


def check_duplicates(report, meta, structures, projections, circuits, receptors, drugs):
    report.header("1. Duplicates (exact + normalized)")
    check_id_collection(report, "structures", structures)
    check_id_collection(report, "receptors", receptors)
    check_id_collection(report, "drugs", drugs)
    check_id_collection(report, "circuits", circuits)
    # drug_targets is a dict in meta; reshape to id-bearing records to reuse the
    # same machinery (the key is the id, the value carries the {en,fr} name).
    targets = [dict(value, id=key) for key, value in meta.get("drug_targets", {}).items()]
    check_id_collection(report, "targets", targets)
    check_projection_dups(report, projections)


# --------------------------------------------------------------------------- #
# 2. Reachability (referential integrity)
# --------------------------------------------------------------------------- #

def check_reachability(report, meta, structures, projections, circuits, receptors, drugs):
    report.header("2. Reachability (dangling references)")
    structure_ids = {s.get("id") for s in structures}
    base_ids = {_HEMISPHERE_RE.sub("", sid) for sid in structure_ids}
    receptor_ids = {r.get("id") for r in receptors}
    targets = meta.get("drug_targets", {})
    before = report.errors

    def require(value, pool, context):
        if value not in pool:
            report.error(context)

    for structure in structures:
        require(structure.get("group"), meta.get("group_labels", {}),
                f"structure {structure.get('id')}: group {structure.get('group')!r} "
                f"is not in group_labels")

    for proj in projections:
        ctx = f"projection {proj.get('from')}->{proj.get('to')}"
        for endpoint in (proj.get("from"), proj.get("to")):
            if endpoint not in structure_ids:
                report.error(f"{ctx}: endpoint {endpoint!r} is not a structure id")
        require(proj.get("kind"), meta.get("projection_colors", {}),
                f"{ctx}: kind {proj.get('kind')!r} is not in projection_colors")

    for circuit in circuits:
        for sid in circuit.get("structures", []):
            if sid not in structure_ids:
                report.error(f"circuit {circuit.get('id')}: structure {sid!r} "
                             f"is not a structure id")

    for receptor in receptors:
        rid = receptor.get("id")
        for field, pool in (("family", "receptor_family_labels"),
                            ("receptor_class", "receptor_class_labels"),
                            ("synaptic", "synaptic_labels"),
                            ("sign", "sign_colors")):
            require(receptor.get(field), meta.get(pool, {}),
                    f"receptor {rid}: {field} {receptor.get(field)!r} is not in {pool}")
        for loc in receptor.get("locations", []):
            if loc not in base_ids:
                report.error(f"receptor {rid}: location {loc!r} is not a structure "
                             f"base (not in the atlas, so its panel 'Found in' row "
                             f"would not be clickable)")
        # The merged Receptors & targets browse list expects every receptor to
        # also be a drug_targets key (a binding can target it directly).
        if rid not in targets:
            report.error(f"receptor {rid}: missing from drug_targets (unbrowsable)")

    for key, target in targets.items():
        require(target.get("type"), meta.get("target_type_labels", {}),
                f"target {key}: type {target.get('type')!r} is not in target_type_labels")
        for region in target.get("regions", []):
            if region not in base_ids:
                report.error(f"target {key}: region {region!r} is not a structure "
                             f"base (not in the atlas, so its panel 'Found in' row "
                             f"would not be clickable)")
        linked = target.get("receptor")
        if linked is not None and linked not in receptor_ids:
            report.error(f"target {key}: linked receptor {linked!r} is not a receptor id")

    for drug in drugs:
        did = drug.get("id")
        for category in drug.get("categories", []):
            require(category, meta.get("drug_category_labels", {}),
                    f"drug {did}: category {category!r} is not in drug_category_labels")
        for binding in drug.get("bindings", []):
            target = binding.get("target")
            if target not in targets:
                report.error(f"drug {did}: binding target {target!r} is not a known "
                             f"target (the binding can never be focused)")
            require(binding.get("action"), meta.get("drug_actions", {}),
                    f"drug {did}: binding action {binding.get('action')!r} is not in "
                    f"drug_actions")
            if "effect" in binding:
                require(binding["effect"], meta.get("drug_effect_colors", {}),
                        f"drug {did}: binding effect {binding['effect']!r} is not in "
                        f"drug_effect_colors")

    if report.errors == before:
        report.ok("every cross-reference (drug -> target/action/category, projection "
                  "-> structure/kind, circuit/receptor/target -> structure) resolves; "
                  "every receptor/target region is in the atlas (its panel 'Found in' "
                  "row is clickable)")


# --------------------------------------------------------------------------- #
# 3. TODOs
# --------------------------------------------------------------------------- #

def check_todos(report, meta, structures, projections, circuits, receptors, drugs):
    report.header("3. TODOs")

    def record_id(label, record):
        if label == "projection":
            return f"{record.get('from')}->{record.get('to')}"
        return record.get("id")

    scan = []
    for label, items in (("structure", structures), ("projection", projections),
                         ("circuit", circuits), ("receptor", receptors),
                         ("drug", drugs)):
        for record in items:
            scan.append((f"{label}:{record_id(label, record)}", record))
    scan.append(("meta", meta))

    source_todos = []
    other_todos = []
    for base, record in scan:
        for path, value in walk_strings(record, base):
            if "TODO" not in value:
                continue
            (source_todos if _SOURCE_URL_RE.search(path) else other_todos).append(path)

    # A focusable target with no wikipedia surfaces as a TODO pill in showTarget;
    # surface it here as a non-source TODO too (a non-receptor target is focusable
    # once it has regions to light).
    missing_wiki = [
        key for key, target in meta.get("drug_targets", {}).items()
        if target.get("receptor") is None and not target.get("wikipedia")
        and target.get("regions")
    ]

    # --- non-source TODOs (warned, listed individually) ---
    if not other_todos and not missing_wiki:
        report.ok("no stray TODOs outside of source urls")
    else:
        for path in other_todos:
            report.warn(f"stray TODO placeholder at {path}")
        for key in missing_wiki:
            report.warn(f"target {key}: no wikipedia url (shows a TODO pill)")

    # --- source-url TODOs (warned, summarized; this is the known backlog) ---
    if source_todos:
        by_kind = Counter(path.split(":", 1)[0].split(".", 1)[0] for path in source_todos)
        breakdown = ", ".join(f"{count} on {kind}s" for kind, count in sorted(by_kind.items()))
        report.warn(f"{len(source_todos)} source url(s) still set to \"TODO\" ({breakdown}); "
                    f"pending real reference links")
    else:
        report.ok("every source url is a real link (no TODO urls)")


# --------------------------------------------------------------------------- #
# 4. Provenance grades
# --------------------------------------------------------------------------- #

def check_provenance(report, meta, structures, projections, circuits, receptors, drugs):
    report.header("4. Source provenance grades")
    before = report.errors
    counts = Counter()

    def grade(value, ctx):
        if value not in _PROVENANCE_LEVELS:
            report.error(f"{ctx}: provenance {value!r} is not one of "
                         f"{sorted(_PROVENANCE_LEVELS)}")
        else:
            counts[value] += 1

    def rec_id(label, record):
        if label == "projection":
            return f"{record.get('from')}->{record.get('to')}"
        return record.get("id")

    # Citation sources (projections + drugs) each carry a per-source grade.
    for label, items in (("projection", projections), ("drug", drugs)):
        for record in items:
            for i, src in enumerate(record.get("sources", []) or []):
                grade(src.get("provenance"),
                      f"{label} {rec_id(label, record)} sources[{i}]")

    # Per-binding drug sources (the quote-level provenance) each carry a grade too,
    # as does a drug's nbn_sources (the NbN is quote-sourced the same way).
    for drug in drugs:
        for binding in drug.get("bindings", []):
            for i, src in enumerate(binding.get("sources", []) or []):
                grade(src.get("provenance"),
                      f"drug {drug.get('id')} binding {binding.get('target')} "
                      f"sources[{i}]")
        for i, src in enumerate(drug.get("nbn_sources", []) or []):
            grade(src.get("provenance"), f"drug {drug.get('id')} nbn_sources[{i}]")
        # A drug's description carries its own grade (llm synthesis vs sourced WP lead).
        if drug.get("description"):
            grade(drug.get("description_provenance"),
                  f"drug {drug.get('id')} description_provenance")

    # Each receptor's classification claims (sign / class / synaptic / locations)
    # carry a source grade (the panel's "Source" pill), counted in the coverage tally
    # like a binding / projection.
    for receptor in receptors:
        if "classification_provenance" in receptor:
            grade(receptor.get("classification_provenance"),
                  f"receptor {receptor.get('id')} classification_provenance")

    # Wikipedia references (structures / receptors / drugs, + the meta targets)
    # carry a sibling `wikipedia_provenance` whenever the link is present.
    for label, items in (("structure", structures), ("receptor", receptors),
                         ("drug", drugs)):
        for record in items:
            if record.get("wikipedia"):
                grade(record.get("wikipedia_provenance"),
                      f"{label} {record.get('id')} wikipedia")
    for key, target in meta.get("drug_targets", {}).items():
        if target.get("wikipedia"):
            grade(target.get("wikipedia_provenance"), f"target {key} wikipedia")

    if report.errors == before:
        summary = ", ".join(f"{counts[lvl]} {lvl}"
                            for lvl in sorted(_PROVENANCE_LEVELS) if counts[lvl])
        report.ok(f"every source/reference carries a valid provenance grade "
                  f"({summary})")

    # Internal consistency of the emitted provenance_stats tally (the figure the
    # About panel + README headline read). Re-deriving the counts would duplicate
    # the generator; this just confirms the emitted buckets are self-consistent, so
    # a malformed emit or a hand-edited stat can never ship a wrong "% sourced".
    stats = meta.get("provenance_stats")
    if not stats:
        report.warn("meta.provenance_stats is missing (the % sourced figure)")
    else:
        before_stats = report.errors
        for kind, c in stats.get("by_kind", {}).items():
            parts = c.get("verified", 0) + c.get("sourced", 0) + c.get("unverified", 0)
            if parts != c.get("total", 0):
                report.error(f"provenance_stats by_kind[{kind}] buckets "
                             f"({parts}) do not sum to total ({c.get('total')})")
        a = stats.get("assertions", {})
        kinds = ("drug_bindings", "drug_nbn", "drug_descriptions", "projections",
                 "receptors")
        by = stats.get("by_kind", {})
        for key in ("total", "verified", "sourced", "unverified"):
            want = sum(by.get(k, {}).get(key, 0) for k in kinds)
            if a.get(key) != want:
                report.error(f"provenance_stats assertions[{key}]={a.get(key)} "
                             f"!= sum over claim kinds ({want})")
        backed = a.get("verified", 0) + a.get("sourced", 0)
        if a.get("backed") != backed:
            report.error(f"provenance_stats assertions.backed={a.get('backed')} "
                         f"!= verified+sourced ({backed})")
        want_pct = round(100 * backed / a["total"]) if a.get("total") else 0
        if a.get("pct_backed") != want_pct:
            report.error(f"provenance_stats assertions.pct_backed="
                         f"{a.get('pct_backed')} != {want_pct}")
        if report.errors == before_stats:
            report.ok(f"provenance_stats is self-consistent "
                      f"({a.get('pct_backed')}% of {a.get('total')} assertions "
                      f"sourced or verified)")


# --------------------------------------------------------------------------- #
# 5. Source quotes (verbatim in the cited corpus page)
# --------------------------------------------------------------------------- #

# A normalized quote shorter than this risks an incidental substring match (a few
# common words appearing on the page by chance), so a too-short quote is warned
# about even when it "matches".
_MIN_QUOTE_CHARS = 16


def check_sources(report, meta, drugs):
    """The core of the sourcing system: confirm every quote-level source (a
    binding's ``sources`` and a drug's ``nbn_sources``) is actually present in the
    page it cites.

    Each source is ``{corpus, page, quote, provenance}``. This:

    * checks ``corpus`` resolves to ``meta.source_corpora`` (else the citation is
      unrenderable) and that a ``"verified"`` grade carries a page + quote;
    * for any source that carries a quote + page, locates the corpus's page file
      (``<pages_dir>/<page>.md``) and asserts the **normalized** quote is a
      substring of the **normalized** page text (see :func:`normalize_for_match`).

    The page material is author-side and may be absent on a plain checkout (it is
    large + uncommitted, see ``stahl/`` in CLAUDE.local.md); when a corpus has no
    ``pages_dir`` on disk the quote-in-page check is **skipped with a warning**
    while the structural checks above still run. So this hard-fails an invented or
    mistyped quote on the author's machine (and the pre-push gate) without
    breaking on a clone that lacks the sources."""
    report.header("5. Source quotes (verbatim in cited page)")
    corpora = meta.get("source_corpora", {})
    before = report.errors

    page_cache = {}            # (corpus, page) -> normalized page text or None
    skipped_corpora = set()
    n_checked = 0

    def page_text(corpus, page):
        key = (corpus, page)
        if key not in page_cache:
            entry = corpora.get(corpus) or {}
            pages_dir = entry.get("pages_dir")
            text = None
            if pages_dir:
                md = REPO_ROOT / pages_dir / f"{page}.md"
                if md.exists():
                    text = normalize_for_match(md.read_text(encoding="utf-8"))
            page_cache[key] = text
        return page_cache[key]

    def check_one(ctx, src):
        nonlocal n_checked
        corpus = src.get("corpus")
        if corpus not in corpora:
            report.error(f"{ctx}: corpus {corpus!r} is not in "
                         f"meta.source_corpora (citation unrenderable)")
            return
        quote, page = src.get("quote"), src.get("page")
        if src.get("provenance") == "verified" and not (quote and page is not None):
            report.error(f"{ctx}: 'verified' source missing a page or quote "
                         f"(verified is the quote-checked grade)")
            return
        if not quote or page is None:
            return  # weaker grade with no quote to check
        entry = corpora.get(corpus) or {}
        if not entry.get("pages_dir"):
            skipped_corpora.add(corpus)
            return
        text = page_text(corpus, page)
        if text is None:
            skipped_corpora.add(corpus)
            return
        needle = normalize_for_match(quote)
        if needle not in text:
            report.error(f"{ctx}: quote NOT found verbatim on {corpus} "
                         f"p.{page}: {quote!r}")
            return
        n_checked += 1
        if len(needle.replace(" ", "")) < _MIN_QUOTE_CHARS:
            report.warn(f"{ctx}: quote is very short ({quote!r}); it matched "
                        f"but may be an incidental substring")

    for drug in drugs:
        did = drug.get("id")
        for binding in drug.get("bindings", []):
            for i, src in enumerate(binding.get("sources", []) or []):
                check_one(f"drug {did} binding {binding.get('target')} sources[{i}]", src)
        for i, src in enumerate(drug.get("nbn_sources", []) or []):
            check_one(f"drug {did} nbn_sources[{i}]", src)

    if skipped_corpora:
        report.warn(f"source pages absent for {sorted(skipped_corpora)} "
                    f"(author-only material); skipped the quote-in-page check there")
    if report.errors == before:
        report.ok(f"every checkable source quote ({n_checked}) is present verbatim "
                  f"in its cited page" if n_checked
                  else "no source quotes to verify yet")


# --------------------------------------------------------------------------- #
# 6. Structure connectivity
# --------------------------------------------------------------------------- #

def check_connectivity(report, structures, projections):
    """Warn about structures the connectome leaves stranded or one-sided.

    A projection is directed ``from -> to`` (a ``bidirectional`` one counts both
    ways for both endpoints). This flags, as **warnings** (not errors; each can be
    legitimate, so it is an eyeball list, not a gate):

    * **isolated**: no projection touches the structure at all (it is only
      reachable via receptors / drug targets, with no modeled pathway yet);
    * **inward-only**: it receives projections but sends none (a pure sink);
    * **outward-only**: it sends projections but receives none (a pure source,
      e.g. the neuromodulatory source nuclei raphe / locus coeruleus / VTA, which
      are modeled as ascending sources, so these are expected here).

    The aim is the author's intuition that a structure wired in one direction only
    is worth a look, without hard-failing the genuinely one-directional cases."""
    report.header("6. Structure connectivity")
    structure_ids = {s.get("id") for s in structures}
    inward, outward = set(), set()
    for proj in projections:
        src, dst = proj.get("from"), proj.get("to")
        if src in structure_ids:
            outward.add(src)
        if dst in structure_ids:
            inward.add(dst)
        if proj.get("bidirectional"):
            if src in structure_ids:
                inward.add(src)
            if dst in structure_ids:
                outward.add(dst)

    isolated, in_only, out_only = [], [], []
    for structure in structures:
        sid = structure.get("id")
        has_in, has_out = sid in inward, sid in outward
        if not has_in and not has_out:
            isolated.append(sid)
        elif has_in and not has_out:
            in_only.append(sid)
        elif has_out and not has_in:
            out_only.append(sid)

    for sid in sorted(isolated):
        report.warn(f"structure {sid}: no projections touch it "
                    f"(isolated in the connectome)")
    for sid in sorted(in_only):
        report.warn(f"structure {sid}: only inward projections "
                    f"(receives, never projects out)")
    for sid in sorted(out_only):
        report.warn(f"structure {sid}: only outward projections "
                    f"(projects out, never receives)")

    flagged = len(isolated) + len(in_only) + len(out_only)
    if not flagged:
        report.ok(f"all {len(structures)} structures have both inward and outward "
                  f"projections")
    else:
        report.ok(f"{len(structures) - flagged} of {len(structures)} structures are "
                  f"two-way connected ({len(isolated)} isolated, {len(in_only)} "
                  f"inward-only, {len(out_only)} outward-only flagged above)")


def main():
    report = Report()
    print(f"neurarium data integrity check\nreading {DATA_DIR}")

    meta = load_meta(report)
    structures = load_jsonl(report, "structures")
    projections = load_jsonl(report, "projections")
    circuits = load_jsonl(report, "circuits")
    receptors = load_jsonl(report, "receptors")
    drugs = load_jsonl(report, "drugs")

    args = (report, meta, structures, projections, circuits, receptors, drugs)
    check_duplicates(*args)
    check_reachability(*args)
    check_todos(*args)
    check_provenance(*args)
    check_sources(report, meta, drugs)
    check_connectivity(report, structures, projections)

    print(f"\nSummary: {report.errors} error(s), {report.warnings} warning(s)")
    if report.errors:
        print("FAILED: fix the errors above (warnings are informational).")
        return 1
    print("PASSED (warnings are informational).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
