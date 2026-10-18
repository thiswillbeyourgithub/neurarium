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

Fourteen families of checks, numbered 0 to 13 as the report headers print them
(each ``check_*`` function's docstring holds the detail of its family):

0. **Quote table** (``check_quotes``). Every ``quote_id`` resolves, none is orphaned.

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
   ``wikipedia`` (the viewer shows a NOSOURCE pill), is a **warning**. A source
   *url* left as ``"TODO"`` is handled **provenance-aware**: the viewer surfaces a
   source's tiered grade (the pill), never its url, so a missing link on an ``llm``
   citation is the expected "no free link yet" state (reported as an ``[ok]``
   count, not a warning); only a source that *claims* a higher grade
   (``sourced`` / ``verified``) yet still has a ``TODO`` url is **warned** (an
   inconsistency: it asserts more than its link backs).

4. **Provenance grades**. Every emitted source (a ``sources[].provenance``,
   including the per-binding drug sources) and every wikipedia reference (a
   ``wikipedia_provenance`` beside a ``wikipedia``) must carry a known grade
   (``llm`` / ``sourced`` / ``verified``), the value the viewer renders as a
   grey/yellow/green pill. An unknown or missing grade is an **error** (the pill
   would fall back to "no source" and mislead). An UNKNOWN stamp (``unknown`` on a
   binding, data_generators/unknown.py) is an **error** on a binding that states a
   direction, or when its search skipped a corpus ``UNKNOWN_REQUIRED_SOURCES`` lists.

5. **Source quotes**. Each per-binding drug source is
   ``{corpus, page, quote, provenance}``; a ``"verified"`` grade is the one that
   claims the quote was confirmed present in the source. This re-confirms it: the
   ``corpus`` must resolve to ``meta.source_corpora``, a verified source must
   carry a page + quote, and the **normalized** quote must be an exact substring
   of the **normalized** cited page text (``<pages_dir>/<page>.md``). The page
   material is author-side and may be absent on a clone (see ``data_sources/books/stahl/`` in
   CLAUDE.local.md); the quote-in-page check is then **skipped with a warning**
   while the structural checks still run. A quote that is genuinely not on its
   page (an invented or mistyped extraction) is an **error**, so this is the gate
   that keeps the LLM extraction honest.

6. **Structure connectivity**. Warns (never errors) about a structure the
   connectome leaves stranded or one-sided: **isolated** (no projection touches
   it), **inward-only** (receives but never projects out), or **outward-only**
   (projects out but never receives, e.g. the modeled ascending source nuclei).
   An eyeball list for the author, not a gate.

7. **Measured-affinity (Ki) coverage**. Warns (never errors) per drug that carries
   bindings but no measured PDSP Ki on any of them, and re-confirms the shipped
   ``meta.provenance_stats.ki_coverage`` figure against a recompute. The honest
   complement to "% sourced": where a measured affinity was never looked up.

8. **Drug flow vs. binding consistency**. Warns (never errors) where a drug's
   by-mechanism flow overlay and its own receptor bindings tell opposite stories:
   the modeled flow raises a system's tone while the drug's postsynaptic receptors
   on that system net-block (or the reverse), and where it boosts a system's flow
   *into* a region whose receptors it strongly blocks. Ports the viewer's flow
   model so it reasons about the same numbers; an eyeball list (most flags are the
   intended presynaptic-tone vs. postsynaptic-block split), not a gate.

9. **Changelog** (``check_changelog``). ``version.js`` has its release notes.
10. **Innervation coverage** (``check_innervation``). Warns per transmitter system.
11. **Baked meshes** (``check_baked_meshes``). The SDF bake matches its shapes.
12. **Enzyme variability** (``check_enzyme_variability``). Re-derived from the
    pinned PharmFreq tables.
13. **Freshness** (``check_freshness``). An editable online corpus page cited but
    downloaded too long ago fails, and so does an UNKNOWN search that old.

Built with the help of Claude Code.
"""

import csv
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data"
# Repo root, used to resolve a source corpus's author-side ``pages_dir`` (e.g.
# ``data_sources/books/stahl/pages``) for the quote-in-page check (see check_sources).
REPO_ROOT = DATA_DIR.parent.parent

# A path like "...sources[3].url" (a citation) is a source url: its TODO is the
# known backlog, reported on its own. Anything else is a stray TODO.
_SOURCE_URL_RE = re.compile(r"\.sources\[\d+\]\.url$")
# Trailing hemisphere suffix on a structure id ("frontal_R" -> "frontal").
_HEMISPHERE_RE = re.compile(r"_(R|L)$")
# Valid source provenance grades (mirrors generate_data.py PROVENANCE_LEVELS), the
# value the viewer renders as the grey/yellow/green source pill.
_PROVENANCE_LEVELS = {"llm", "sourced", "verified"}

# The knowledge-node kinds folded into the headline coverage are NODE_KINDS, imported
# from data_generators/node_kinds.py (the one roster) further down.
# ``drug_binding_action`` is graded from the bindings' own quote sources, so its quotes
# are already walked as part of drug_bindings / drug_metabolite_bindings: the kind adds a
# tally column, never a new quote to gate.
# The per-drug physicochemistry citations (kinds drug_lipophilicity / drug_polar_surface /
# drug_bbb, data_generators/physchem.py).
PHYSCHEM_SOURCES = ("xlogp_sources", "tpsa_sources", "bbb_sources")



def _flip_hemisphere(structure_id):
    """Flip a structure id to the other hemisphere; midline ids unchanged."""
    if structure_id.endswith("_R"):
        return structure_id[:-2] + "_L"
    if structure_id.endswith("_L"):
        return structure_id[:-2] + "_R"
    return structure_id


def _expand_mirrored(projections):
    """Reflect ``mirror: true`` projections into the full bilateral connectome.

    A symmetric pathway is emitted once carrying ``mirror: true`` (the file stores
    only the right-hemisphere record; see generate_data.py ``_projection_records``).
    The reachability + connectivity checks reason over the logical connectome, so
    expand each flagged record into its hemisphere-flipped twin here, exactly as
    ``js/data.js`` does at load, before any check runs."""
    out = []
    for proj in projections:
        record = {k: v for k, v in proj.items() if k != "mirror"}
        out.append(record)
        if proj.get("mirror"):
            out.append({**record,
                        "from": _flip_hemisphere(record.get("from")),
                        "to": _flip_hemisphere(record.get("to"))})
    return out


class Report:
    """Collects errors/warnings while printing each section as it runs.

    A third level, ``review``, is for the per-item lines of an eyeball list whose
    flags are mostly intended (family 8's presynaptic-tone vs. postsynaptic-block
    split, family 7's drugs without a Ki): counted and summarized, but listed only
    under ``--verbose``, so the default run's warnings stay few enough to be read."""

    def __init__(self, verbose=False):
        self.errors = 0
        self.warnings = 0
        self.reviews = 0
        self.verbose = verbose

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

    def review(self, msg):
        self.reviews += 1
        if self.verbose:
            print(f"  [review] {msg}")


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
    # A soft hyphen (U+00AD) is a typesetting break hint, never text: a table cell
    # wrapped at one ("Brexpi­\nprazole") is one word, so it joins like a
    # hyphenated break instead of splitting the word in two.
    text = re.sub("­\\s*", "", text)
    # Inline markup the Markdown split keeps (`<u>` underline in a table cell,
    # `<sup>` around a reference number) is formatting: dropping only the tag keeps
    # its content, so `<u>CYP1A2</u>` reads as the word, not "u cyp1a2 u".
    # A tag INSIDE a word ("9-hydroxyrisperi<u>done)</u>", where the PDF underline
    # starts mid-word) is dropped outright, so the word stays one word.
    text = re.sub(r"(?<=\w)</?(?:u|b|i|em|strong)>(?=\w)", "", text)
    text = re.sub(r"</?(?:u|b|i|em|strong|sup|sub)>", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)          # drops combining marks too
    return " ".join(text.split())


def display_name(name):
    """A display name. The emitted data is English-only, so it is normally a
    plain string; the legacy ``{en, fr}`` object is still handled defensively
    (use the English text). French lives in data/translations.fr.json."""
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


def emitted_page_dirs() -> dict[str, str]:
    """``corpus -> author-side page directory`` (repo-relative), read from the emitted
    ``meta.source_corpora``: the trees the quote gate checks. The one reader of that
    registry for the author-side scripts (recheck / demote / heading resolution), so a
    corpus added to the generator reaches them all at once."""
    corpora = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8")).get(
        "source_corpora", {})
    return {name: entry["pages_dir"] for name, entry in corpora.items()
            if entry.get("pages_dir")}


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
# Quote table (externalized source quotes)
# --------------------------------------------------------------------------- #

def load_quotes(report):
    """Load ``quotes.jsonl`` into a ``quote_id -> quote node`` map.

    Source quotes are emitted once into this side table; each node references
    one by ``quote_id`` (see quote_table.py). A duplicate id is a hard error.
    """
    by_id = {}
    for q in load_jsonl(report, "quotes"):
        qid = q.get("id")
        if not isinstance(qid, str):
            report.error(f"quotes.jsonl: entry without a string id: {q!r}")
            continue
        if qid in by_id:
            report.error(f"quotes.jsonl: duplicate quote id {qid!r}")
        by_id[qid] = q
    return by_id


def rehydrate_quotes(node, by_id, referenced, dangling):
    """Merge each ``{quote_id, ...}`` reference's excerpt back in place.

    Mirrors the viewer's rehydration (js/data.js): copies every field of the quote
    node except its ``id`` onto the reference (so a field the generator adds to the
    quote node needs no edit here) and drops the ``quote_id`` key, so every later
    check sees the original inline source shape.
    Records each referenced id (for the orphan check) and any id with no entry.
    """
    if isinstance(node, dict):
        qid = node.get("quote_id")
        if isinstance(qid, str):
            referenced.add(qid)
            quote = by_id.get(qid)
            if quote is None:
                dangling.append(qid)
            else:
                node.update((k, v) for k, v in quote.items() if k != "id")
            node.pop("quote_id", None)
        for value in node.values():
            rehydrate_quotes(value, by_id, referenced, dangling)
    elif isinstance(node, list):
        for value in node:
            rehydrate_quotes(value, by_id, referenced, dangling)


def check_quotes(report, quotes_by_id, referenced, dangling):
    """Referential integrity of the externalized quote table.

    Every node's ``quote_id`` must resolve to a quote node, and every quote node
    must be referenced by at least one node (no orphans left behind by the
    generator). ``referenced``/``dangling`` are collected during rehydration.
    """
    report.header("0. Quote table")
    if dangling:
        for qid in sorted(set(dangling)):
            report.error(f"quote reference {qid!r} has no entry in quotes.jsonl")
    else:
        report.ok(f"all {len(referenced)} distinct quote references resolve "
                  f"to a quote node")
    orphans = sorted(set(quotes_by_id) - referenced)
    if orphans:
        report.error(f"{len(orphans)} quote(s) in quotes.jsonl are unreferenced "
                     f"(orphans, e.g. {orphans[:3]})")
    else:
        report.ok(f"no orphan quotes ({len(quotes_by_id)} quotes all referenced)")


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

    # An id becomes a file name and a URL segment (render_api, the viewer's ?params).
    malformed = sorted({str(v) for v in ids if not node_id.is_node_id(v)})
    for value in malformed:
        report.error(f"{label}: id {value!r} is not {node_id.NODE_ID_RE.pattern}")

    if not exact and not near and not name_dups and not malformed:
        report.ok(f"{label}: {len(items)} entries, no duplicate ids or names")


def check_projection_dups(report, projections):
    pairs = Counter((p.get("from"), p.get("to")) for p in projections)
    dups = {pair: count for pair, count in pairs.items() if count > 1}
    for (src, dst), count in sorted(dups.items(), key=lambda kv: str(kv[0])):
        report.error(f"projections: {src} -> {dst} defined {count} times")
    if not dups:
        report.ok(f"projections: {len(projections)} pathways, no duplicate from->to")


def check_binding_dups(report, drugs):
    """A drug may list one target twice (a dual mechanism: amphetamine both blocks DAT
    reuptake and releases through it), but never the same (target, action) twice: that
    is a dual pair one bulk edit collapsed onto a single action, losing the other."""
    n = 0
    for drug in drugs:
        pairs = Counter((b.get("target"), b.get("action")) for b in drug.get("bindings", []))
        for (target, action), count in sorted(pairs.items(), key=str):
            if count > 1:
                n += 1
                report.error(f"drug {drug.get('id')}: binding {target}/{action} listed "
                             f"{count} times (a collapsed dual-mechanism pair?)")
    if not n:
        report.ok("drug bindings: no (target, action) pair listed twice")


def check_duplicates(report, meta, structures, projections, circuits,
                     projection_groups, receptors, drugs, metabolites=()):
    report.header("1. Duplicates (exact + normalized)")
    check_id_collection(report, "structures", structures)
    check_id_collection(report, "receptors", receptors)
    check_id_collection(report, "drugs", drugs)
    check_id_collection(report, "metabolites", metabolites)
    check_id_collection(report, "circuits", circuits)
    check_id_collection(report, "projection groups", projection_groups)
    # drug_targets is a dict in meta; reshape to id-bearing records to reuse the
    # same machinery (the key is the id, the value carries the {en,fr} name).
    targets = [dict(value, id=key) for key, value in meta.get("drug_targets", {}).items()]
    check_id_collection(report, "targets", targets)
    check_projection_dups(report, projections)
    check_binding_dups(report, drugs)


# --------------------------------------------------------------------------- #
# 2. Reachability (referential integrity)
# --------------------------------------------------------------------------- #

def check_reachability(report, meta, structures, projections, circuits,
                       projection_groups, receptors, drugs, addons, metabolites=()):
    report.header("2. Reachability (dangling references)")
    structure_ids = {s.get("id") for s in structures}
    base_ids = {_HEMISPHERE_RE.sub("", sid) for sid in structure_ids}
    receptor_ids = {r.get("id") for r in receptors}
    targets = meta.get("drug_targets", {})
    before = report.errors

    def require(value, pool, context):
        if value not in pool:
            report.error(context)

    def check_density(ctx, owner, own_regions):
        """A density profile ranks the owner's OWN regions and nothing else: a stray base
        would draw an expression site the owner never claims. Shared by receptors and
        non-receptor targets (identical shape)."""
        density = owner.get("density")
        if not density:
            return
        for base in density.get("profile", {}):
            if base not in own_regions:
                report.error(f"{ctx}: density profile ranks {base!r}, which is not one "
                             f"of its regions (would imply an unclaimed expression site)")
        if not -1.0 <= density.get("reliability", 0) <= 1.0:
            report.error(f"{ctx}: density reliability {density.get('reliability')!r} "
                         f"is not a correlation in [-1, 1]")

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

    # Projection groups: each names a colour-mode + a kind/sign key the viewer
    # groups arrows by; an unknown key would make the group's member-pathway list
    # (derived in the viewer) empty, so its detail panel would be unreachable.
    for group in projection_groups:
        gid, mode, key = group.get("id"), group.get("mode"), group.get("key")
        if mode == "kind":
            require(key, meta.get("projection_colors", {}),
                    f"projection group {gid}: kind {key!r} is not in projection_colors")
        elif mode == "sign":
            require(key, meta.get("sign_colors", {}),
                    f"projection group {gid}: sign {key!r} is not in sign_colors")
        else:
            report.error(f"projection group {gid}: unknown mode {mode!r} "
                         f"(expected 'kind' or 'sign')")

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
        # A per-region expression source must grade one of the receptor's own
        # locations (the "ALL" sentinel is the ubiquitous receptor's one claim).
        own = set(receptor.get("locations", []))
        for base in (receptor.get("location_sources") or {}):
            if base != "ALL" and base not in own:
                report.error(f"receptor {rid}: location_sources key {base!r} is not "
                             f"one of its locations (grades a region it doesn't claim)")
            if base == "ALL" and not receptor.get("ubiquitous"):
                report.error(f"receptor {rid}: location_sources 'ALL' but the "
                             f"receptor is not ubiquitous")
        check_density(f"receptor {rid}", receptor, own)
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
        # A per-region expression source must grade one of the target's own regions
        # (mirror of the receptor location_sources key check above).
        own_regions = set(target.get("regions", []))
        for base in (target.get("location_sources") or {}):
            if base not in own_regions:
                report.error(f"target {key}: location_sources key {base!r} is not "
                             f"one of its regions (grades a region it doesn't claim)")
        check_density(f"target {key}", target, own_regions)
        linked = target.get("receptor")
        if linked is not None and linked not in receptor_ids:
            report.error(f"target {key}: linked receptor {linked!r} is not a receptor id")

    # Action <-> target-type compatibility. A pharmacological action only makes sense
    # on certain target kinds; a mismatch means the direction (boost/block/tone) was
    # almost certainly mis-assigned. This is the guard that catches a VMAT2 (vesicular)
    # inhibitor mislabeled `reuptake_inhibitor` (which would read as a boost, not the
    # depletion it is). `modulator` is deliberately unconstrained (context-dependent).
    # A peptide receptor takes every action a receptor does: the type exists to say
    # which legend heading it belongs under, not to restrict its pharmacology.
    receptorish = {"receptor", "receptor_group", "peptide_receptor"}
    action_target_types = {
        "reuptake_inhibitor": {"transporter"},
        "releaser": {"transporter"},
        "vesicular_inhibitor": {"transporter", "vesicle_protein"},
        "vesicular_releaser": {"transporter"},
        "enzyme_inhibitor": {"enzyme"},
        "agonist": receptorish,
        "partial_agonist": receptorish,
        "antagonist": receptorish | {"ion_channel"},
        "inverse_agonist": receptorish,
        "pam": receptorish,
        "nam": receptorish,
        # A cotransporter (NKCC1) moves ions rather than a transmitter, so it is
        # blocked, never "reuptake-inhibited"; its own type keeps `blocker` legal
        # here without loosening it on a reuptake pump, where it would silently
        # mean no tone at all.
        "blocker": {"ion_channel", "vesicle_protein", "cotransporter"},
    }
    compat_errors = 0
    drug_ids = {d.get("id") for d in drugs}

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
            # An affinity_only binding (PDSP Ki with no known direction) carries no
            # action/effect; every other binding must name a known action.
            if binding.get("affinity_only"):
                if not binding.get("ki"):
                    report.error(f"drug {did}: affinity_only binding {target!r} has "
                                 f"no ki (it would show nothing)")
            else:
                require(binding.get("action"), meta.get("drug_actions", {}),
                        f"drug {did}: binding action {binding.get('action')!r} is not "
                        f"in drug_actions")
                if "effect" in binding:
                    require(binding["effect"], meta.get("drug_effect_colors", {}),
                            f"drug {did}: binding effect {binding['effect']!r} is not "
                            f"in drug_effect_colors")
                # The action must be pharmacologically compatible with the target's
                # kind, else the derived direction (boost/block/tone) is mis-assigned.
                tgt = targets.get(target) or {}
                ttype = tgt.get("type")
                action = binding.get("action")
                allowed = action_target_types.get(action)
                if allowed is not None and ttype is not None and ttype not in allowed:
                    compat_errors += 1
                    report.error(f"drug {did}: action {action!r} is not valid on a "
                                 f"{ttype!r} target ({target!r}); its boost/block/tone "
                                 f"direction is almost certainly mis-assigned")
                elif tgt.get("vesicular") and action in ("reuptake_inhibitor", "releaser"):
                    compat_errors += 1
                    report.error(f"drug {did}: vesicular target {target!r} uses the "
                                 f"plasma-membrane action {action!r}; say which vesicular "
                                 f"direction it is -> vesicular_inhibitor (blocks loading, "
                                 f"depletes, tone down) or vesicular_releaser (a substrate "
                                 f"dumping the stores, tone up)")
            # The Ki annotation's source corpus must resolve (its verbatim-presence
            # in the CSV is confirmed in check_sources).
            ki = binding.get("ki")
            if ki:
                corpus = (ki.get("source") or {}).get("corpus")
                if corpus not in (meta.get("source_corpora", {}) or {}):
                    report.error(f"drug {did}: binding {target!r} ki source corpus "
                                 f"{corpus!r} is not in source_corpora")
    # Active metabolites: one record per molecule (metabolites.jsonl), referenced by
    # id from each parent's metabolites[]. Every ref must resolve, every record must be
    # referenced (an orphan is a molecule no panel reaches), a linked drug_id must be a
    # real drug, and a metabolite binding target must be a known target (so it can be
    # attributed in the receptor 'Interacting drugs' list).
    metab_ids = {m.get("id") for m in metabolites}
    referenced_metabs = set()
    for drug in drugs:
        for ref in drug.get("metabolites", []) or []:
            referenced_metabs.add(ref.get("id"))
            if ref.get("id") not in metab_ids:
                report.error(f"drug {drug.get('id')}: metabolite ref {ref.get('id')!r} "
                             f"is not a metabolites.jsonl id")
    for m in metabolites:
        mid = m.get("id")
        if mid not in referenced_metabs:
            report.error(f"metabolite {mid!r} is listed by no drug")
        link = m.get("drug_id")
        if link and link not in drug_ids:
            report.error(f"metabolite {mid!r} links drug_id {link!r} which is not a "
                         f"modeled drug")
        for binding in m.get("bindings", []) or []:
            if binding.get("target") not in targets:
                report.error(f"metabolite {mid!r} binding target "
                             f"{binding.get('target')!r} is not a known target")

    # Addon nodes carry their own insertion point, so "does it resolve?" is two
    # questions: does the anchored node exist, and is the slot one the viewer offers.
    # A wrong answer to either is a node that ships and is never drawn, which no other
    # check can see (it is well-formed, graded, and counted in the tally).
    addon_before = report.errors
    slots = meta.get("addon_slots") or {}
    displays = set(meta.get("addon_displays") or ())
    tones = set(meta.get("addon_tones") or {})
    addon_pools = {"drug": {d.get("id") for d in drugs},
                   "receptor": receptor_ids,
                   "target": set(targets),
                   "structure": base_ids,
                   # A section addon annotates a whole browse view rather than a
                   # node, so the "does the anchor exist" question is asked against
                   # the emitted section vocabulary itself.
                   "section": set(meta.get("addon_sections") or {})}
    for addon in addons:
        aid = addon.get("id")
        slot, kind = addon.get("slot"), addon.get("owner_kind")
        if slot not in slots:
            report.error(f"addon {aid!r}: slot {slot!r} is not in meta.addon_slots "
                         f"({sorted(slots)}); nothing would ever draw it")
        elif slots[slot] != kind:
            report.error(f"addon {aid!r}: anchors a {kind!r} node in slot {slot!r}, "
                         f"which is a {slots[slot]!r} panel slot")
        if addon.get("display") not in displays:
            report.error(f"addon {aid!r}: display {addon.get('display')!r} is not in "
                         f"meta.addon_displays ({sorted(displays)})")
        if addon.get("tone") not in tones:
            report.error(f"addon {aid!r}: tone {addon.get('tone')!r} is not in "
                         f"meta.addon_tones ({sorted(tones)})")
        pool = addon_pools.get(kind)
        if pool is None:
            report.error(f"addon {aid!r}: unknown owner_kind {kind!r}")
        elif addon.get("owner") not in pool:
            report.error(f"addon {aid!r}: anchors {kind} {addon.get('owner')!r}, "
                         f"which is not a known {kind} id")
        bases = meta.get("addon_bases") or ("claim",)
        basis = addon.get("basis", "claim")
        if basis not in bases:
            report.error(f"addon {aid!r}: basis {basis!r} is not in meta.addon_bases "
                         f"({list(bases)})")
        elif basis == "dataset" and addon.get("sources"):
            # A statement about the dataset itself cannot be sourced (and is kept out
            # of the tally on that ground), so a citation means it was misfiled.
            report.error(f"addon {aid!r}: a dataset statement carries sources")
        if not addon.get("text"):
            report.error(f"addon {aid!r}: no text (an addon IS its claim)")
    if addons and report.errors == addon_before:
        report.ok(f"all {len(addons)} addon nodes anchor a real node in a slot the "
                  f"viewer offers")

    if report.errors == before:
        report.ok("every cross-reference (drug -> target/action/category, projection "
                  "-> structure/kind, circuit/receptor/target -> structure) resolves; "
                  "every receptor/target region is in the atlas (its panel 'Found in' "
                  "row is clickable)")

    if compat_errors == 0:
        report.ok("every binding action is compatible with its target's kind "
                  "(no mis-assigned boost/block/tone direction)")


# --------------------------------------------------------------------------- #
# 3. TODOs
# --------------------------------------------------------------------------- #

def check_todos(report, meta, structures, projections, circuits,
                projection_groups, receptors, drugs):
    report.header("3. TODOs")

    def record_id(label, record):
        if label == "projection":
            return f"{record.get('from')}->{record.get('to')}"
        return record.get("id")

    scan = []
    for label, items in (("structure", structures), ("projection", projections),
                         ("circuit", circuits), ("projection group", projection_groups),
                         ("receptor", receptors),
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

    # --- corpus links ---
    # Per-claim sources are quote-level ``{corpus, page, quote}`` and carry no url of
    # their own: the viewer links a cited page from ``meta.source_corpora``, trying the
    # corpus's ``page_urls[page]``, then its ``page_url`` template, then its ``url``
    # landing page (a book's DOI or ISBN). So every corpus needs a real ``url``, and any
    # link it does carry must be one.
    def is_link(u):
        return str(u).startswith(("http://", "https://"))

    no_link = []
    for cid, corpus in (meta.get("source_corpora", {}) or {}).items():
        if not isinstance(corpus, dict):
            continue
        url = corpus.get("url")
        if url is None:
            no_link.append(cid)
        elif not is_link(url):
            report.error(f"source_corpora.{cid}.url is not a real link: {url!r}")
        bad = [p for p, u in (corpus.get("page_urls") or {}).items() if not is_link(u)]
        if bad:
            report.error(f"source_corpora.{cid}.page_urls: not a real link for "
                         f"{len(bad)} page(s), e.g. {bad[0]!r}")
    if no_link:
        report.warn(f"{len(no_link)} source corpus/corpora carry no url, so their "
                    f"citations are not clickable: {', '.join(sorted(no_link))}")
    else:
        report.ok("every source corpus carries a real url")


# --------------------------------------------------------------------------- #
# 4. Provenance grades
# --------------------------------------------------------------------------- #

def print_coverage(stats):
    """Print the per-kind, per-tier sourcing tally over the dataset's **nodes** (the
    same numbers the About panel + README headline read from
    ``meta.provenance_stats``), so the pre-push output shows at a glance exactly how
    many nodes sit at each provenance grade.

    A *node* is any sourceable datum (see the Nodes section of CLAUDE.md). Each node
    is reduced to its single strongest grade first, so the columns partition the node
    count (they sum to ``total``); the grades map to the viewer's pills: verified =
    green check, sourced = yellow ``~``, missing = grey ``?`` (an unbacked ``llm``
    assertion) / orange NOSOURCE (no source at all). ``references`` (wikipedia
    pointers) are a kind of their own, tallied but not folded into the headline (a
    reference points *at* a node, it is not itself one), so they are printed below the
    node total."""
    by = stats.get("by_kind", {})
    a = stats.get("nodes", {})
    node_kinds = NODE_KINDS

    def backed_pct(c):
        total = c.get("total", 0)
        return round(100 * backed(c) / total) if total else 0

    def row(label, c, pct=None, suffix=""):
        pct = backed_pct(c) if pct is None else pct
        m = c.get("missing", 0)
        s = c.get("sourced", 0)
        u = c.get("uncertain", 0)
        sv = backed(c)  # sourced-or-verified-or-uncertain = the backed count
        print(f"    {label:<19}{m:>6}{s:>6}{u:>6}{sv:>6}"
              f"{c.get('total', 0):>8}{pct:>7}%{suffix}")

    # Grade columns: M = missing (no source document: a bare llm assertion, or nothing
    # at all), S = sourced (document-backed but not quote-checked), U = uncertain
    # (quote-checked, but the quote does not attribute the claim), S+V = the backed
    # count (S and U are both subsets of it). S is ~always 0 on the node kinds because
    # the sourcing pipeline goes straight from llm to quote-verified; it shows up only
    # on Wikipedia refs.
    print("\n  node coverage by kind (each node reduced to its strongest grade;")
    print("  M=missing  S=sourced  U=uncertain  S+V=backed):")
    print(f"    {'kind':<19}{'M':>6}{'S':>6}{'U':>6}{'S+V':>6}{'total':>8}{'backed':>8}")
    for kind in node_kinds:
        row(kind, by.get(kind, {}))
    print(f"    {'-' * 53}")
    row("all nodes", a, pct=a.get("pct_backed", 0))
    if a.get("unknown"):
        print(f"    + {a['unknown']} UNKNOWN (searched, no source states it; "
              f"outside the total)")
    if by.get("references"):
        row("references", by["references"], suffix="   (pointers, not in headline)")


def check_provenance(report, meta, structures, projections, circuits,
                     projection_groups, receptors, drugs, addons, metabolites=()):
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

    # Citation sources (projections + drugs + circuits + projection groups) each
    # carry a per-source grade.
    for label, items in (("projection", projections), ("drug", drugs),
                         ("circuit", circuits),
                         ("projection group", projection_groups)):
        for record in items:
            for i, src in enumerate(record.get("sources", []) or []):
                grade(src.get("provenance"),
                      f"{label} {rec_id(label, record)} sources[{i}]")

    # Projection-group classification (the grouping/description grade) + its
    # wikipedia reference each carry a grade, like a receptor / target.
    for group in projection_groups:
        if "classification_provenance" in group:
            grade(group.get("classification_provenance"),
                  f"projection group {group.get('id')} classification_provenance")
        if group.get("wikipedia"):
            grade(group.get("wikipedia_provenance"),
                  f"projection group {group.get('id')} wikipedia")
    # A circuit's optional wikipedia reference likewise carries a grade.
    for circuit in circuits:
        if circuit.get("wikipedia"):
            grade(circuit.get("wikipedia_provenance"),
                  f"circuit {circuit.get('id')} wikipedia")

    # Per-binding drug sources (the quote-level provenance) each carry a grade too,
    # as does a drug's nbn_sources (the NbN is quote-sourced the same way).
    for drug in drugs:
        for ctx, src, _short, _facet, _owner in iter_drug_sources(drug):
            grade(src.get("provenance"), ctx)
        # A drug's class classification carries its own grade (default llm).
        if drug.get("category_provenance"):
            grade(drug.get("category_provenance"),
                  f"drug {drug.get('id')} category_provenance")
        # A drug's description carries its own grade (llm synthesis vs sourced WP lead).
        if drug.get("description"):
            grade(drug.get("description_provenance"),
                  f"drug {drug.get('id')} description_provenance")

    # A metabolite's own facts, once per molecule (metabolites.jsonl).
    for m in metabolites:
        mid = f"metabolite {m.get('id')}"
        for i, src in enumerate(m.get("half_life_sources", []) or []):
            grade(src.get("provenance"), f"{mid} half_life_sources[{i}]")
        for binding in m.get("bindings", []) or []:
            for i, src in enumerate(binding.get("sources", []) or []):
                grade(src.get("provenance"),
                      f"{mid} binding {binding.get('target')} sources[{i}]")

    # Each receptor / structure classification claim and each non-receptor target
    # classification carries a source grade (the panel's "Source" pill), counted in
    # the coverage tally like a binding / projection.
    for receptor in receptors:
        # Each classification attribute (family / receptor_class / sign / synaptic)
        # is its own graded sub-claim, so a wrong/unsourced GPCR or sign shows
        # honestly instead of borrowing a neighbour attribute's quote grade.
        for attr, entry in (receptor.get("classification") or {}).items():
            grade(entry.get("grade"),
                  f"receptor {receptor.get('id')} classification[{attr}]")
            for i, src in enumerate(entry.get("sources") or []):
                grade(src.get("provenance"),
                      f"receptor {receptor.get('id')} classification[{attr}] sources[{i}]")
        # Per-region expression sources (the "Found in" grading): each carries a grade.
        for base, srcs in (receptor.get("location_sources") or {}).items():
            for i, src in enumerate(srcs or []):
                grade(src.get("provenance"),
                      f"receptor {receptor.get('id')} location_sources[{base}][{i}]")
    for structure in structures:
        if "classification_provenance" in structure:
            grade(structure.get("classification_provenance"),
                  f"structure {structure.get('id')} classification_provenance")
    for key, target in meta.get("drug_targets", {}).items():
        if target.get("type") != "receptor" and "classification_provenance" in target:
            grade(target.get("classification_provenance"),
                  f"target {key} classification_provenance")
        # Tone-polarity sub-claim (kind target_polarity): its own grade + optional
        # quote source, distinct from the type/system classification above.
        if "polarity_provenance" in target:
            grade(target.get("polarity_provenance"),
                  f"target {key} polarity_provenance")
            for i, src in enumerate(target.get("polarity_sources") or []):
                grade(src.get("provenance"),
                      f"target {key} polarity_sources[{i}]")
        # Per-region expression sources (the target's "Found in" grading), mirror of
        # the receptor location_sources above; each carries a grade.
        for base, srcs in (target.get("location_sources") or {}).items():
            for i, src in enumerate(srcs or []):
                grade(src.get("provenance"),
                      f"target {key} location_sources[{base}][{i}]")

    # Addon nodes are graded through their quote-level sources like a binding.
    for addon in addons:
        for i, src in enumerate(addon.get("sources", []) or []):
            grade(src.get("provenance"), f"addon {addon.get('id')} sources[{i}]")

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

    # UNKNOWN stamps (data_generators/unknown.py): only on a claim still unsourced, and
    # only after a search that covered every corpus its kind requires.
    n_unknown = 0
    for where, kind, claim, stamp in _unknown_stamps(drugs, metabolites, receptors, meta):
        n_unknown += 1
        if kind == "drug_binding_action" and (
                claim.get("action") or not claim.get("affinity_only")):
            report.error(f"{where}: UNKNOWN stamped on a binding that states a direction "
                         f"(a real source wins)")
        if kind == "receptor_effect" and claim.get("effects"):
            report.error(f"{where}: UNKNOWN stamped on an owner that carries a sourced "
                         f"effect (a real source wins)")
        missing = unknown.missing_required(kind, stamp.get("corpora") or [])
        if missing:
            report.error(f"{where}: UNKNOWN search skipped required source(s) "
                         f"{', '.join(missing)}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(stamp.get("searched"))):
            report.error(f"{where}: UNKNOWN stamp has no YYYY-MM-DD search date")

    if report.errors == before:
        summary = ", ".join(f"{counts[lvl]} {lvl}"
                            for lvl in sorted(_PROVENANCE_LEVELS) if counts[lvl])
        if n_unknown:
            summary += f"; {n_unknown} UNKNOWN stamp(s), each fully searched"
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
            parts = (c.get("verified", 0) + c.get("uncertain", 0)
                     + c.get("sourced", 0) + c.get("missing", 0))
            if parts != c.get("total", 0):
                report.error(f"provenance_stats by_kind[{kind}] buckets "
                             f"({parts}) do not sum to total ({c.get('total')})")
        a = stats.get("nodes", {})
        node_kinds = NODE_KINDS
        by = stats.get("by_kind", {})
        for key in ("total", "verified", "uncertain", "sourced", "missing", "unknown"):
            want = sum(by.get(k, {}).get(key, 0) for k in node_kinds)
            if a.get(key) != want:
                report.error(f"provenance_stats nodes[{key}]={a.get(key)} "
                             f"!= sum over node kinds ({want})")
        n_backed = backed(a)
        if a.get("backed") != n_backed:
            report.error(f"provenance_stats nodes.backed={a.get('backed')} "
                         f"!= verified+uncertain+sourced ({n_backed})")
        want_pct = round(100 * n_backed / a["total"]) if a.get("total") else 0
        if a.get("pct_backed") != want_pct:
            report.error(f"provenance_stats nodes.pct_backed="
                         f"{a.get('pct_backed')} != {want_pct}")
        if report.errors == before_stats:
            report.ok(f"provenance_stats is self-consistent "
                      f"({a.get('pct_backed')}% of {a.get('total')} nodes "
                      f"sourced or verified)")
        print_coverage(stats)


# --------------------------------------------------------------------------- #
# 5. Source quotes (verbatim in the cited corpus page)
# --------------------------------------------------------------------------- #

# A normalized quote shorter than this risks an incidental substring match (a few
# common words appearing on the page by chance), so a too-short quote is warned
# about even when it "matches".
_MIN_QUOTE_CHARS = 16

# A page's Markdown heading line ("## Interactions") opens another section: a quote
# running across one glues two sections' sentences into one claim, and still matches
# verbatim once whitespace is normalized, so it is refused on its own.
_HEADING_IN_QUOTE = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]")


def spans_heading(quote):
    """Whether ``quote`` runs across a Markdown heading line of its page."""
    return bool(_HEADING_IN_QUOTE.search(quote or ""))

# A quote can be verbatim on the cited page and still not support the claim. The
# recurring way that happened here: Stahl's "How Drug Causes Side Effects" block
# lists the mechanisms of the drug's CLASS as subject-less rules ("Blocking
# muscarinic cholinergic receptors can cause dry mouth ..."), printed identically
# across the monographs (that one on 17 pages, the alpha-1 one on 28), so it never
# states that THIS drug blocks anything. 151 antipsychotic bindings were once
# sourced from three such lines, including muscarinic + H1 + alpha-1 blockade for
# sulpiride, a benzamide with none of them. A sentence that attributes the action
# ("By blocking X, IT can cause Y", "Paroxetine's weak antimuscarinic properties
# can cause ...") is fine and deliberately not matched: the subject is the point.
_NO_SUBJECT_QUOTE = re.compile(
    r"^(Blocking\b|Antihistaminic actions\b)[^.]*\b(can|may) cause\b", re.I)

# The other half of "is this quote about the drug we are talking about?": a Stahl
# quote must come from a page inside that drug's OWN monograph. The book is one
# monograph per drug over a contiguous page span, so a page outside the span is a
# quote read off a neighbour's entry, which no amount of verbatim matching would
# catch (the sentence really is on the page, just not that drug's page).
def _fold_name(name):
    """A drug name reduced to its letters+digits, so ``Amphetamine (d,l)`` and the
    index's ``Amphetamine (D,L)`` compare equal."""
    return alnum_key(name)


def stahl_monograph_ranges():
    """``folded drug name -> (first page, last page)`` from Stahl's generated INDEX.md.

    ``None`` when the author-side book tree is absent (a plain clone), so the
    caller skips the check exactly like the verbatim-quote gate does."""
    ranges = stahl_index.ranges(_fold_name, missing_ok=True)
    return ranges or None


def stahl_monograph_check(drug, ranges):
    """``(pages, span, stray)`` for one drug against the monograph index.

    ``pages`` is every Stahl page it quotes, ``span`` its own monograph (``None``
    when the index has no row under its name or any of its brands, so the caller
    reports it as unrangeable rather than as a violation), and ``stray`` the
    quoted pages that fall outside that span."""
    pages = sorted(quote_pages(drug, "stahl", set()))
    names = [drug.get("name") or ""]
    names += re.split(r"\s*\+\s*", names[0])          # a combo names both halves
    names += [b for b in (drug.get("brands") or []) if isinstance(b, str)]
    span = next((ranges[k] for k in map(_fold_name, names) if k in ranges), None)
    if span is None:
        return pages, None, []
    return pages, span, [p for p in pages if not span[0] <= p <= span[1]]


def quote_pages(node, corpus, out):
    """Collect every page a ``corpus`` quote in this subtree cites (sources are
    rehydrated in place, so a plain recursive walk sees them all)."""
    if isinstance(node, dict):
        if node.get("corpus") == corpus and node.get("page") is not None:
            out.add(node["page"])
        for value in node.values():
            quote_pages(value, corpus, out)
    elif isinstance(node, list):
        for value in node:
            quote_pages(value, corpus, out)
    return out


def check_sources(report, meta, drugs, projections, structures, receptors, addons,
                  metabolites=(), circuits=(), groups=(), contradictions=()):
    """The core of the sourcing system: confirm every quote-level source (a
    binding's ``sources``, a drug's ``nbn_sources``, an enzyme's ``variability``
    sources, and a projection's quote-level ``sources``) is actually present in the
    page it cites.

    A source is ``{corpus, page, quote, provenance}`` (the one shape used everywhere:
    drug bindings, NbN, projection/circuit/group quotes, region anatomy). A source
    with no ``corpus`` field is defensively skipped (there are none today; fabricated
    bibliographic ``{citation, url}`` citations were removed). This:

    * checks ``corpus`` resolves to ``meta.source_corpora`` (else the citation is
      unrenderable) and that a ``"verified"`` grade carries a page + quote;
    * for any source that carries a quote + page, locates the corpus's page file
      (``<pages_dir>/<page>.md``) and asserts the **normalized** quote is a
      substring of the **normalized** page text (see :func:`normalize_for_match`).

    The page material is author-side and may be absent on a plain checkout (it is
    large + uncommitted, see ``data_sources/books/stahl/`` in CLAUDE.local.md); when a corpus has no
    ``pages_dir`` on disk the quote-in-page check is **skipped with a warning**
    while the structural checks above still run. So this hard-fails an invented or
    mistyped quote on the author's machine (and the pre-push gate) without
    breaking on a clone that lacks the sources.

    One corpus stands that lookup **down** rather than skipping it. A corpus shipping
    its own raw tables declares ``tsv_dir`` and no ``pages_dir`` (PharmFreq, #13):
    there is no prose page to look in, and a page written out of the same numbers as
    the quote would prove nothing. Its quotes are gated by re-derivation from the
    sha256-pinned files instead, in :func:`check_enzyme_variability` (family 12),
    which is why that is the one quote gate that runs on a plain clone."""
    report.header("5. Source quotes (verbatim in cited page)")
    corpora = meta.get("source_corpora", {})
    # The closed vocabulary the "uncertain" bullets draw their reason kinds from,
    # read from the data rather than restated here so the two cannot drift.
    reason_kinds = set(meta.get("uncertainty_reasons", {}))
    before = report.errors

    # pipeline key -> its chain of custody (see provenance.QUOTE_PIPELINES). The rule
    # below is read OFF the chains rather than restated as a list of key names: a
    # pipeline in which a model chose the sentence but no model ever judged it is the
    # violation, whatever it ends up being called.
    pipelines = meta.get("quote_pipelines", {})
    unjudged_pipelines = {k for k, steps in pipelines.items()
                          if "extract_llm" in steps and "judge_llm" not in steps}
    unjudged = []

    page_cache = {}            # (corpus, page) -> normalized page text or None
    skipped_corpora = set()
    n_checked = 0
    # Every source carrying a derived book heading, checked in one pass below
    # (collected here so the whole dataset is walked once, not twice).
    headings = []

    def page_text(corpus, page):
        key = (corpus, page)
        if key not in page_cache:
            entry = corpora.get(corpus) or {}
            pages_dir = entry.get("pages_dir")
            text = None
            md = page_file(REPO_ROOT / pages_dir, page) if pages_dir else None
            if md and md.exists():
                text = normalize_for_match(md.read_text(encoding="utf-8"))
            page_cache[key] = text
        return page_cache[key]

    def check_one(ctx, src, short_ok=False):
        nonlocal n_checked
        if "corpus" not in src:
            return  # a bibliographic citation, not a quote-level source
        corpus = src.get("corpus")
        if corpus not in corpora:
            report.error(f"{ctx}: corpus {corpus!r} is not in "
                         f"meta.source_corpora (citation unrenderable)")
            return
        if src.get("heading"):
            headings.append((ctx, corpus, src.get("page"), src["heading"]))
        quote, page = src.get("quote"), src.get("page")
        if src.get("provenance") == "verified" and not (quote and page is not None):
            report.error(f"{ctx}: 'verified' source missing a page or quote "
                         f"(verified is the quote-checked grade)")
            return
        if quote:
            # NO LLM-PICKED QUOTE SHIPS UNJUDGED. A sentence a model chose out of prose
            # is the one that can be chosen wrongly (right page, wrong claim), so it
            # does not count as backed until a second model, which never saw the first
            # one's reasoning, agreed it supports the claim. A quote code copied out of
            # a table has no such failure mode and needs no judge. See CLAUDE.md "The
            # sourcing model" and tools/sourcing/recheck_quotes.py.
            if src.get("pipeline") not in pipelines:
                report.error(f"{ctx}: pipeline {src.get('pipeline')!r} is not in "
                             f"meta.quote_pipelines (chain of custody unrenderable)")
            elif src["pipeline"] in unjudged_pipelines:
                unjudged.append(ctx)
        if not quote or page is None:
            return  # weaker grade with no quote to check
        if spans_heading(quote):
            report.error(f"{ctx}: quote runs across a page heading (two sections "
                         f"glued into one claim): {quote!r}")
        entry = corpora.get(corpus) or {}
        # A corpus shipping its raw tables (`tsv_dir`) has no prose page to look in:
        # its quote is COMPOSED out of those tables, so family 13 re-derives it from
        # them instead. Everything structural above still applies.
        if entry.get("tsv_dir"):
            return
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
        # A brand quote IS a short proper noun (the name, verbatim) and a Ki quote one
        # table row: short by design (callers pass short_ok). Any flattened table row
        # ("α 2A | 15 | Antagonist") is too, whichever node cites it: its cells are a
        # whole row of the page, never an incidental substring of prose.
        if (not short_ok and " | " not in quote
                and len(needle.replace(" ", "")) < _MIN_QUOTE_CHARS):
            report.warn(f"{ctx}: quote is very short ({quote!r}); it matched "
                        f"but may be an incidental substring")

    def check_claims(ctx, node, claimed):
        """Gate a node's per-claim split (``claims``, see quotes/attestation.py).

        A sub-claim's sources are a SUBSET of the owner's own, picked by a word test, so
        the verbatim gate would already cover the text; what is checked here is the
        SELECTION: every quote a sub-claim cites must really name what it is cited for,
        and a sub-claim citing nothing must carry the base grade rather than a borrowed
        check. Re-derived from the very vocabulary the generator graded it with, so a
        hand-edited or stale ``claims`` block fails instead of shipping.

        ``claimed`` maps each claim name to the value the node states for it (the
        transmitter, the sign, the strength tier), which is what the word test is run
        for.
        """
        for claim, entry in (node.get("claims") or {}).items():
            srcs = entry.get("sources") or []
            for i, src in enumerate(srcs):
                where = f"{ctx} claims[{claim}] sources[{i}]"
                check_one(where, src)
                pattern = claim_pattern(claim, claimed.get(claim) or "")
                if pattern is None:
                    report.error(f"{where}: {claim} {claimed.get(claim)!r} has no word "
                                 f"test, so nothing could have attested it")
                elif not pattern.search(src.get("quote") or ""):
                    report.error(f"{where}: the quote does not name the {claim} it is "
                                 f"cited for ({claimed.get(claim)!r})")
            # A sub-claim another corpus denies, or a set-level sentence covers,
            # carries the same bullets as a whole node, gated the same way.
            check_uncertainty(f"{ctx} claims[{claim}]", entry)
            if not srcs and entry.get("grade") != CLAIM_BASE_GRADE:
                report.error(f"{ctx} claims[{claim}]: grade {entry.get('grade')!r} with "
                             f"no source (an unattested sub-claim is "
                             f"{CLAIM_BASE_GRADE!r})")

    gated = set()              # id() of every node whose bullets were gated below

    def check_uncertainty(what, node):
        """Gate the "uncertain" badge's bullets on any node that carries them.

        Each bullet is itself a claim shown to the reader with its own pill, so each is
        gated like any other node: its quote must be verbatim on the cited page, its
        reason kind must be one the vocabulary defines, and a bullet with no source must
        SAY it is an absence of evidence rather than leave a silent blank. Shared by the
        drug bindings and the projections, which carry the same bullet shape.
        """
        gated.add(id(node))
        for j, u in enumerate(node.get("uncertainty", []) or []):
            uctx = f"{what} uncertainty[{j}] ({u.get('kind')})"
            if u.get("kind") not in reason_kinds:
                report.error(f"{uctx}: reason kind is not one of "
                             f"meta.uncertainty_reasons ({sorted(reason_kinds)})")
            srcs = u.get("sources") or []
            if not srcs and not u.get("absence"):
                report.error(
                    f"{uctx}: has no source and does not declare absence=true. "
                    f"A bullet either cites a document or says outright that the "
                    f"corpus is silent; a blank one reads as the latter while "
                    f"meaning the source was forgotten")
            if srcs and u.get("absence"):
                report.error(f"{uctx}: declares absence=true yet cites a source")
            for k, src in enumerate(srcs):
                # A measured-affinity source is a CSV row id, not prose, so it is
                # gated by the Ki family (8) instead, exactly like a binding's own
                # ki.source.
                if (corpora.get(src.get("corpus"), {}).get("csv")
                        and not src.get("quote")):
                    continue
                check_one(f"{uctx} sources[{k}]", src)

    def check_location_uncertainty(what, owner):
        """A "Found in" region's bullets, keyed like its location_sources."""
        for base, bullets in (owner.get("location_uncertainty") or {}).items():
            if base not in (owner.get("location_sources") or {}):
                report.error(f"{what} location_uncertainty[{base}]: no location_sources "
                             f"for that region, so the doubt has no claim to doubt")
            check_uncertainty(f"{what} location[{base}]", {"uncertainty": bullets})

    for drug in drugs:
        did = drug.get("id")
        for ctx, src, short_ok, facet, owner in iter_drug_sources(drug):
            check_one(ctx, src, short_ok=short_ok)
            # A binding that DECLARES the problem (the orange "uncertain" badge, whose
            # own bullets say the sentence attributes nothing) is not silently passing
            # a subject-less quote off as a green check, so the gate stands down.
            if (facet == "binding" and not owner.get("uncertainty")
                    and _NO_SUBJECT_QUOTE.match(src.get("quote") or "")):
                report.error(
                    f"{ctx}: quote is a subject-less mechanism -> side-effect rule "
                    f"({src.get('quote')!r}). Stahl's 'How Drug Causes Side Effects' "
                    f"block prints the same lines on every monograph in the class, so "
                    f"such a sentence never says THIS drug has the action: it cannot "
                    f"source a binding (an attributed one, 'By blocking X, IT can "
                    f"cause Y', can)")
        for binding in drug.get("bindings", []):
            # A quote-carrying Ki source (corpus #9 wikipedia_pharm cites the verbatim
            # affinity-table row) is gated here like any other quote. A PDSP Ki cites a
            # CSV row (ki_id, no quote) and is verified by the CSV gate below instead, so
            # only feed a Ki source that actually carries a quote.
            ki_src = (binding.get("ki") or {}).get("source")
            if ki_src and ki_src.get("quote"):
                # A Ki quote is one table row (target | value | species): short by
                # design, and its number + target make a chance match implausible.
                check_one(f"drug {did} binding {binding.get('target')} ki.source", ki_src,
                          short_ok=True)
            check_uncertainty(f"drug {did} binding {binding.get('target')}", binding)
        for e in drug.get("enzymes", []) or []:
            # The denial quote of a contradicted row is gated exactly like the claim it
            # doubts: both sides of a corpus disagreement earn their grade the same way.
            check_uncertainty(f"drug {did} enzyme {e.get('enzyme')} ({e.get('role')})", e)
            # HOW MUCH of the clearing the row claims: its own node, so its own gate.
            check_claims(f"drug {did} enzyme {e.get('enzyme')}", e,
                         {"strength": e.get("strength")})
        # A denial of a metabolite link (CONTRADICTIONS), gated like the link.
        for m in drug.get("metabolites", []) or []:
            check_uncertainty(f"drug {did} metabolite {m.get('id')}", m)

    for m in metabolites:
        mid = f"metabolite {m.get('id')}"
        for i, src in enumerate(m.get("half_life_sources", []) or []):
            check_one(f"{mid} half_life_sources[{i}]", src)
        for binding in m.get("bindings", []) or []:
            for i, src in enumerate(binding.get("sources", []) or []):
                check_one(f"{mid} binding {binding.get('target')} sources[{i}]", src)
            # A metabolite binding's quote-carrying Ki (wikipedia_pharm table row) is
            # gated exactly like a drug binding's (a PDSP CSV Ki is checked below).
            ki_src = (binding.get("ki") or {}).get("source")
            if ki_src and ki_src.get("quote"):
                check_one(f"{mid} binding {binding.get('target')} ki.source", ki_src,
                          short_ok=True)  # a table row, as for a drug's Ki above
            check_uncertainty(f"{mid} binding {binding.get('target')}", binding)

    for addon in addons:
        for i, src in enumerate(addon.get("sources", []) or []):
            check_one(f"addon {addon.get('id')} sources[{i}]", src)

    for proj in projections:
        pid = f"{proj.get('from')}->{proj.get('to')}"
        for i, src in enumerate(proj.get("sources", []) or []):
            check_one(f"projection {pid} sources[{i}]", src)
        # The per-claim split (transmitter / sign): gated by the shared helper above.
        check_claims(f"projection {pid}", proj, {
            "transmitter": proj.get("neurotransmitter"),
            "sign": (meta.get("kind_signs") or {}).get(proj.get("kind")),
        })
        # A pathway the book only states as a blanket sweep wears the same orange badge
        # a binding does, and its bullets are gated the same way.
        check_uncertainty(f"projection {pid}", proj)

    effect_modes = meta.get("receptor_effect_modes") or {}
    effect_labels = meta.get("receptor_effect_labels") or {}

    def check_effects(ctx, owner, is_receptor):
        """receptor_effect nodes (BETA): closed vocabularies, one quote at least, each
        quote gated like any other. ``inhibition`` is a non-receptor target's mode."""
        for e in owner.get("effects") or []:
            where = f"{ctx} effects[{e.get('mode')}:{e.get('effect')}]"
            if e.get("mode") not in effect_modes or e.get("effect") not in effect_labels:
                report.error(f"{where}: mode/effect not in meta.receptor_effect_*")
            if is_receptor and e.get("mode") == "inhibition":
                report.error(f"{where}: 'inhibition' on a receptor")
            if not e.get("sources"):
                report.error(f"{where}: an effect node with no source")
            for i, src in enumerate(e.get("sources") or []):
                check_one(f"{where} sources[{i}]", src)

    structure_bases = {s.get("id", "").removesuffix("_R").removesuffix("_L")
                       for s in structures}

    def check_release_modulation(r):
        """receptor_release_modulation nodes (BETA): the same closed-vocabulary rules
        the applier and the emitter enforce (``release_modulation.vocab_error``), one
        quote at least, each quote gated like any other."""
        for n in r.get("release_modulation") or []:
            site = n.get("site") or {}
            f = {"kind": n.get("kind"), "structure": site.get("structure"),
                 "cell": site.get("cell"), "modulates": n.get("modulates"),
                 "effect": n.get("effect_of_activation")}
            where = f"receptor {r.get('id')} release_modulation[{RELMOD.node_key(**f)}]"
            neuro = r.get("neurotransmitter")
            why = RELMOD.vocab_error(f, neuro.get("en") if isinstance(neuro, dict) else neuro,
                                     structure_bases)
            if why:
                report.error(f"{where}: {why}")
            if not n.get("sources"):
                report.error(f"{where}: a release-modulation node with no source")
            for i, src in enumerate(n.get("sources") or []):
                check_one(f"{where} sources[{i}]", src)

    def check_demographics(ctx, owner):
        """receptor_demographic nodes (BETA): the closed vocabulary the applier and the
        emitter enforce (``demographics.vocab_error``), a magnitude verbatim in one of
        its own quotes, one quote at least, each quote gated like any other."""
        for n in owner.get("demographics") or []:
            f = {k: n.get(k) for k in ("factor", "direction", "structure")}
            where = f"{ctx} demographics[{DEMOG.node_key(**f)}]"
            why = DEMOG.vocab_error(f, structure_bases)
            if why:
                report.error(f"{where}: {why}")
            if not n.get("sources"):
                report.error(f"{where}: a demographic node with no source")
            mag = n.get("magnitude")
            if mag and not any(normalize_for_match(mag) in normalize_for_match(s.get("quote") or "")
                               for s in n.get("sources") or []):
                report.error(f"{where}: magnitude {mag!r} is in none of its quotes")
            for i, src in enumerate(n.get("sources") or []):
                check_one(f"{where} sources[{i}]", src)

    for s in structures:
        for i, src in enumerate(s.get("sources", []) or []):
            check_one(f"structure {s.get('id')} sources[{i}]", src)

    for r in receptors:
        for attr, entry in (r.get("classification") or {}).items():
            for i, src in enumerate(entry.get("sources") or []):
                check_one(f"receptor {r.get('id')} classification[{attr}] sources[{i}]", src)
            check_uncertainty(f"receptor {r.get('id')} classification[{attr}]", entry)
        # Per-region expression sources are quote-checked like any other (the gate
        # that keeps a future "5-HT2A is dense in the PFC" citation honest).
        for base, srcs in (r.get("location_sources") or {}).items():
            for i, src in enumerate(srcs or []):
                # One tissue line of the receptor's own gene page ("CNS: pons.").
                check_one(f"receptor {r.get('id')} location_sources[{base}][{i}]", src,
                          short_ok=True)
        check_location_uncertainty(f"receptor {r.get('id')}", r)
        # The density profile's quote carries the z per region and the cross-donor
        # agreement, so gating it verbatim is what keeps those numbers honest.
        for i, src in enumerate((r.get("density") or {}).get("sources") or []):
            check_one(f"receptor {r.get('id')} density sources[{i}]", src)
        check_effects(f"receptor {r.get('id')}", r, is_receptor=True)
        check_release_modulation(r)
        check_demographics(f"receptor {r.get('id')}", r)
        for n in r.get("variants") or []:
            for i, src in enumerate(n.get("sources") or []):
                check_one(f"receptor {r.get('id')} variants[{n.get('annotation')}] "
                          f"sources[{i}]", src)

    for tid, tinfo in (meta.get("drug_targets", {}) or {}).items():
        if isinstance(tinfo, dict):
            for i, src in enumerate(tinfo.get("sources", []) or []):
                check_one(f"target {tid} sources[{i}]", src)
            # A non-receptor target's per-region expression sources, quote-checked
            # like the receptor ones (same honesty gate for a future citation).
            for base, srcs in (tinfo.get("location_sources") or {}).items():
                for i, src in enumerate(srcs or []):
                    check_one(f"target {tid} location_sources[{base}][{i}]", src,
                              short_ok=True)  # one line of its gene page, as above
            check_location_uncertainty(f"target {tid}", tinfo)
            for i, src in enumerate((tinfo.get("density") or {}).get("sources") or []):
                check_one(f"target {tid} density sources[{i}]", src)
            check_effects(f"target {tid}", tinfo, is_receptor=False)
            check_demographics(f"target {tid}", tinfo)
            for n in tinfo.get("variants") or []:
                for i, src in enumerate(n.get("sources") or []):
                    check_one(f"target {tid} variants[{n.get('annotation')}] "
                              f"sources[{i}]", src)

    # Metabolizer-status profiles hang off `meta.enzymes`, not off any node file, so
    # they are reached from here rather than by the walks above. The page lookup stands
    # down for them (see the `tsv_dir` branch), but the structural half applies: a
    # `verified` grade still owes a page and a quote, and the pipeline still has to be
    # one `meta.quote_pipelines` describes.
    for eid, enzyme in sorted((meta.get("enzymes") or {}).items()):
        for i, src in enumerate(((enzyme.get("variability") or {})
                                 .get("sources") or [])):
            check_one(f"enzyme {eid} variability sources[{i}]", src)

    if skipped_corpora:
        report.warn(f"source pages absent for {sorted(skipped_corpora)} "
                    f"(author-only material); skipped the quote-in-page check there")
    if report.errors == before:
        report.ok(f"every checkable source quote ({n_checked}) is present verbatim "
                  f"in its cited page" if n_checked
                  else "no source quotes to verify yet")

    # A source's `heading` (the breadcrumb of book headings the passage sits under)
    # is DERIVED, keyed by quote id, from the author-side page trees by
    # tools/fetch/fetch_quote_headers.py. Nothing in the emitted data proves it is
    # still current, so check what is checkable without the books: the shape. A
    # blank level would render as an empty crumb, which reads like a heading the
    # book actually prints rather than one the resolver failed to find.
    before_shape = report.errors
    for ctx, corpus, page, trail in headings:
        if not isinstance(trail, list) or not trail:
            report.error(f"{ctx}: heading must be a non-empty list of headings, "
                         f"outermost first (got {trail!r}); omit it rather than "
                         f"storing an empty breadcrumb")
            continue
        for part in trail:
            if not isinstance(part, str) or not part.strip():
                report.error(f"{ctx}: heading trail has a blank level ({trail!r}); "
                             f"drop the level rather than storing a blank crumb")
    if report.errors == before_shape and headings:
        report.ok(f"all {len(headings)} derived heading trails are non-empty lists "
                  f"of non-blank headings")

    # Every Stahl quote on a drug must come off that drug's own monograph pages.
    ranges = stahl_monograph_ranges()
    if ranges is None:
        report.warn("Stahl INDEX.md absent (author-only material); skipped the "
                    "check that each drug's quotes come from its own monograph")
    else:
        before_range = report.errors
        checked = unindexed = 0
        for drug in drugs:
            pages, span, stray = stahl_monograph_check(drug, ranges)
            if not pages:
                continue
            if span is None:
                unindexed += 1
                report.warn(f"drug {drug.get('id')} ({drug.get('name')}) cites Stahl "
                            f"pages {pages} but has no INDEX.md monograph; "
                            f"its quotes cannot be range-checked")
                continue
            checked += 1
            if stray:
                report.error(f"drug {drug.get('id')}: Stahl quote(s) from page(s) "
                             f"{stray}, outside its own monograph (pages "
                             f"{span[0]}-{span[1]}). A quote read off a neighbouring "
                             f"drug's entry is verbatim on the page and still says "
                             f"nothing about this drug")
        if report.errors == before_range:
            report.ok(f"all Stahl quotes on {checked} drugs come from that drug's own "
                      f"monograph" + (f" ({unindexed} unindexed)" if unindexed else ""))

        # A Stahl heading trail LEADS with the monograph title, which is checkable
        # offline against the same INDEX.md ranges: the drug it names must be the
        # monograph the cited page actually falls in. That is what catches a
        # hand-edited or stale generated_cache entry, which would otherwise print a
        # confident and wrong breadcrumb over a real quote.
        before_head = report.errors
        stahl_headings = 0
        for ctx, corpus, page, trail in headings:
            if corpus != "stahl" or page is None or not isinstance(trail, list):
                continue
            stahl_headings += 1
            span = ranges.get(_fold_name(trail[0])) if trail else None
            if span is None:
                report.error(f"{ctx}: heading trail leads with {trail[:1]!r}, which "
                             f"is no INDEX.md monograph. A Stahl trail must open "
                             f"with the drug whose monograph the page falls in")
            elif not (span[0] <= page <= span[1]):
                report.error(f"{ctx}: heading says the quote is in {trail[0]!r}'s "
                             f"monograph (pages {span[0]}-{span[1]}) but it cites "
                             f"p.{page}. Re-run tools/fetch/fetch_quote_headers.py")
        if report.errors == before_head:
            report.ok(f"all {stahl_headings} Stahl heading trails open with the "
                      f"monograph their page falls in" if stahl_headings
                      else "no derived Stahl headings yet "
                           "(run tools/fetch/fetch_quote_headers.py)")

    # A binding's `ki` cites one CSV row by ki_id (the analogue of a quote's page):
    # confirm that row really exists in the corpus CSV with the cited value. Like the
    # quote gate this is author-side (the CSV is large + uncommitted, see
    # data_sources/books/pdsp_ki/), skipped with a warning on a clone that lacks it.
    ki_before = report.errors
    ki_index_cache = {}          # corpus -> {ki_id: ki_val_str} or None if csv absent

    def ki_index(corpus):
        if corpus not in ki_index_cache:
            entry = corpora.get(corpus) or {}
            path = entry.get("csv")
            idx = None
            if path and (REPO_ROOT / path).exists():
                idx = {}
                with open(REPO_ROOT / path, newline="", encoding="utf-8",
                          errors="replace") as f:
                    for row in csv.DictReader(f):
                        try:
                            idx[int(row["Number"])] = (row.get("ki Val") or "").strip()
                        except (TypeError, ValueError, KeyError):
                            pass
            ki_index_cache[corpus] = idx
        return ki_index_cache[corpus]

    n_ki = 0
    ki_skipped = set()

    def check_ki_source(ctx, src):
        """Gate one source citing a PDSP-CSV row by ki_id: a binding's Ki, or an
        uncertainty bullet's measurement (a curated denial included)."""
        nonlocal n_ki
        corpus, ki_id = src.get("corpus"), src.get("ki_id")
        # Only a CSV corpus (PDSP) cites a row by ki_id; a quote-gated Ki corpus
        # (wikipedia_pharm) was already verified by the source-quote gate above.
        if not (corpora.get(corpus) or {}).get("csv"):
            return
        if src.get("provenance") == "verified" and ki_id is None:
            report.error(f"{ctx}: 'verified' source needs a ki_id")
            return
        if ki_id is None:
            return
        idx = ki_index(corpus)
        if idx is None:
            ki_skipped.add(corpus)
            return
        if ki_id not in idx:
            report.error(f"{ctx}: ki_id {ki_id} not found in {corpus} CSV")
            return
        # The stored value must be the row's own value (we took it from there).
        try:
            if abs(float(idx[ki_id]) - float(src.get("value_nm"))) > 0.01:
                report.error(f"{ctx}: value_nm {src.get('value_nm')} != CSV row "
                             f"{ki_id} value {idx[ki_id]!r}")
                return
        except (TypeError, ValueError):
            pass
        n_ki += 1

    def check_bullet_ki(ctx, node):
        """The CSV-row sources of a node's uncertainty bullets, which the bullet gate
        (``check_uncertainty``) hands over to this family."""
        for j, u in enumerate(node.get("uncertainty") or []):
            for k, src in enumerate(u.get("sources") or []):
                if src.get("ki_id") is not None:
                    check_ki_source(f"{ctx} uncertainty[{j}] sources[{k}]", src)

    def check_ki(ctx, binding):
        """Gate one binding's PDSP-CSV Ki (a metabolite binding's Ki is checked the same
        way as a drug's) and its bullets' CSV rows."""
        check_ki_source(f"{ctx} ki", (binding.get("ki") or {}).get("source") or {})
        check_bullet_ki(ctx, binding)

    for drug in drugs:
        did = drug.get("id")
        for binding in drug.get("bindings", []):
            check_ki(f"drug {did} binding {binding.get('target')}", binding)
    for m in metabolites:
        for binding in m.get("bindings", []) or []:
            check_ki(f"metabolite {m.get('id')} binding {binding.get('target')}", binding)
    if ki_skipped:
        report.warn(f"Ki CSV absent for {sorted(ki_skipped)} (author-only material); "
                    f"skipped the ki-row-in-CSV check there")
    if report.errors == ki_before:
        report.ok(f"every checkable Ki annotation ({n_ki}) cites a real CSV row"
                  if n_ki else "no Ki annotations to verify yet")

    # The curated "contradicted" table, keyed by citation site (any node kind): every
    # site must still name exactly one emitted node, that node must wear the badge, and
    # its denial quotes are gated here when no per-kind walk above reached the node.
    nodes, ambiguous = CS.node_index(
        drugs=drugs, metabolites=metabolites, receptors=receptors,
        targets=meta.get("drug_targets") or {}, projections=projections,
        circuits=circuits, groups=groups, structures=structures)
    for site in contradictions:
        node = None if site in ambiguous else nodes.get(site)
        if node is None:
            report.error(f"CONTRADICTIONS[{site!r}]: names "
                         f"{'two emitted nodes' if site in ambiguous else 'no emitted node'}"
                         f" (gone, renamed, or a flat facet): the contradiction marks "
                         f"nothing")
            continue
        if not any(u.get("kind") == "contradicted" for u in node.get("uncertainty") or []):
            report.error(f"CONTRADICTIONS[{site!r}]: the node carries no contradicted "
                         f"bullet (stale data/: rerun tools/generate_data.py)")
        if id(node) not in gated:
            check_uncertainty(site, node)
            check_bullet_ki(site, node)

    if unjudged:
        report.error(f"{len(unjudged)} LLM-picked quote citation(s) were never judged "
                     f"by a second model (pipeline {sorted(unjudged_pipelines)}); run "
                     f"tools/sourcing/recheck_quotes.py, e.g. {unjudged[:2]}")
    else:
        report.ok("every LLM-picked quote was judged by a second model")


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


def check_ki_coverage(report, meta, drugs):
    """Report **measured-affinity (PDSP Ki) coverage** as an eyeball list.

    A binding backed only by a Stahl quote (no Ki) is legitimately sourced, so this
    is NOT a provenance gate: it is the honest complement to the "% sourced" figure,
    surfacing where a *measured* affinity was never looked up (the "we didn't even
    bother to look" case the grade tally cannot see). Each drug carrying at least one
    binding but **zero** Ki across all of them is warned (combo drugs "A + B" are
    Ki-exempt by design and excluded, matching the generator). Recomputed here from
    the emitted drugs, then cross-checked against ``meta.provenance_stats.ki_coverage``
    so the shipped number can never silently drift."""
    report.header("7. Measured-affinity (Ki) coverage")
    ki_drugs = [d for d in drugs if d.get("bindings") and not is_combination(d)]
    bindings = [b for d in ki_drugs for b in d["bindings"]]
    with_ki = [b for b in bindings if b.get("ki")]
    no_ki = sorted(d["id"] for d in ki_drugs
                   if not any(b.get("ki") for b in d["bindings"]))
    pct = round(100 * len(with_ki) / len(bindings)) if bindings else 0

    stat = (meta.get("provenance_stats") or {}).get("ki_coverage") or {}
    for key, want in (("bindings_total", len(bindings)),
                      ("bindings_with_ki", len(with_ki)),
                      ("pct_bindings_with_ki", pct),
                      ("drugs_total", len(ki_drugs)),
                      ("drugs_without_ki", len(no_ki))):
        if stat.get(key) != want:
            report.error(f"provenance_stats.ki_coverage[{key}]={stat.get(key)} "
                         f"!= recomputed ({want})")
    if stat.get("drugs_without_ki_ids") != no_ki:
        report.error("provenance_stats.ki_coverage.drugs_without_ki_ids "
                     "disagrees with recomputed list")

    for did in no_ki:
        report.review(f"drug {did!r}: no measured Ki on any binding "
                    "(sourced by quote only, or unsourced)")
    report.ok(f"{pct}% of {len(bindings)} bindings carry a measured Ki; "
              f"{len(no_ki)}/{len(ki_drugs)} drugs have none")


def _base_id(structure_id):
    """Drop a trailing ``_R`` / ``_L`` so a mirrored endpoint compares against a
    base region name (a receptor ``location`` / target ``region`` is a base)."""
    return _HEMISPHERE_RE.sub("", structure_id) if structure_id else structure_id


def _affinity_weight(ki):
    """Ki (nM) -> a 0.35..1 engagement weight, a faithful port of js/data.js
    ``affinityWeightOf`` (a pKi ramp, 1 uM..0.1 nM -> 0.35..1). A binding with no
    measured Ki gets the same neutral mid weight the viewer uses, so the check
    reasons about the exact numbers the flow overlay animates."""
    median = ki.get("median") if isinstance(ki, dict) else None
    if not (isinstance(median, (int, float)) and median > 0):
        return 0.55
    pki = 9 - math.log10(median)
    t = max(0.0, min(1.0, (pki - 6) / 4))
    return 0.35 + 0.65 * t


def _tone_bucket_of(target, rec_meta):
    """Which ``meta.tone_rules`` bucket a binding falls in, or None for no tone.

    The one part of the flow model that is not in the rule table, because it is a
    join rather than a rule: the target's ``type`` (plus its ``vesicular`` flag)
    picks the first four buckets, and the autoreceptor bucket needs the RECEPTOR
    record behind the binding, since a receptor only feeds back on release when it
    is presynaptic AND inhibitory. Mirrors ``toneBucketOf`` in js/data.js.
    """
    ttype = target.get("type", "")
    if ttype == "transporter":
        return "vesicular_transporter" if target.get("vesicular") else "transporter"
    if ttype in ("enzyme", "vesicle_protein"):
        return ttype
    if ttype in ("receptor", "receptor_group"):
        # sign/synaptic from the specific receptor record (a modeled 5-HT1x / D2/D3),
        # else the group's own flag (the alpha2 family, in meta.drug_targets).
        rm = rec_meta.get(target.get("receptor")) if target.get("receptor") else target
        presyn = bool(rm) and rm.get("synaptic") in ("presynaptic", "both")
        if presyn and rm.get("sign") == "inhibitory":
            return "autoreceptor"
    return None


def _tone_of(target, action, rec_meta, tone_rules):
    """Signed tone contribution of one binding + the *label* of the mechanism that
    set it: ``(+1|-1|0, driver|None)``. +1 raises the transmitter's tone, -1 lowers
    it, 0 = not a tone-setter (a postsynaptic receptor -> dots only, never flow). The
    label lets the check say *why* a system's flow points the way it does (a reuptake
    block vs. an autoreceptor block).

    ``tone_rules`` is ``meta.tone_rules``, the SAME table js/data.js animates: the
    rule used to be transcribed by hand in each language, which is how the VMAT2
    direction bug survived in one copy. Now only the bucket join above is per-language
    and the directions themselves have one author (TONE_RULES in
    tools/data_generators/drugs.py)."""
    bucket = _tone_bucket_of(target, rec_meta)
    rule = (tone_rules.get(bucket) or {}).get(action) if bucket else None
    if not rule:
        return (0, None)
    tone, mechanism = rule[0], rule[1]
    return (tone, mechanism.replace("_", " "))


def _target_regions(target, rec_meta):
    """Base regions where a drug target is expressed: a receptor-linked target
    reuses its receptor's ``locations``, a bare DRUG_TARGETS entry its ``regions``."""
    rid = target.get("receptor")
    if rid and rid in rec_meta:
        return set(rec_meta[rid].get("locations", []))
    return set(target.get("regions", []))


def check_flow_consistency(report, meta, drugs, projections, receptors):
    """Cross-check each drug's by-mechanism flow overlay against its own receptor
    bindings, as an **informational** eyeball list (warnings, never errors, like the
    connectivity family): where the modeled flow direction and the drug's receptor
    actions tell opposite stories, so a human can confirm the picture is intended.

    Two views (the user asked for both), each collapsed to one line per drug+system:

    * **system-level** (8a): the flow overlay drives a transmitter's tone one way
      while the drug's *postsynaptic* receptor bindings on that same system net the
      other way (e.g. an SSRI raising serotonergic tone via SERT while antagonising
      5-HT2 postsynaptically). The driver tag says which mechanism set the flow.
    * **region-level** (8b): the drug boosts a system's ascending flow *into* a
      region while strongly blocking that system's receptors expressed *there*, so
      the streamed beads overstate the downstream effect (the user's own example).

    Most flags are the **intended** presynaptic-tone-vs-postsynaptic-block split, the
    documented autoreceptor caveat (a D2-antagonist antipsychotic reads dopamine-up
    because it blocks the D2 autoreceptor, while its postsynaptic blockade shows in
    the block-coloured dots). This is a review aid, not a gate: it cannot tell an
    intended dual action from a mis-entered ``action``, only surface the mismatch.
    The flow model (``_affinity_weight`` / ``_tone_of``) is the same one js/data.js
    animates, ported here so the check reasons about the very numbers the user sees."""
    report.header("8. Drug flow vs. binding consistency")
    drug_targets = meta.get("drug_targets", {})
    drug_actions = meta.get("drug_actions", {})
    system_flow_kinds = meta.get("system_flow_kinds", {})
    tone_rules = meta.get("tone_rules", {})
    rec_meta = {r.get("id"): r for r in receptors}
    effect_sign = {"boost": 1, "block": -1, "modulate": 0}

    # Base target-regions per projection kind: where increased flow of a kind would
    # arrive, so its postsynaptic receptors are the ones the region-level check cares
    # about. (Projections are already mirror-expanded by the caller.)
    arrives_in = defaultdict(set)
    for proj in projections:
        kind, dst = proj.get("kind"), _base_id(proj.get("to"))
        if kind and dst:
            arrives_in[kind].add(dst)

    STRONG = 0.6   # per-binding engagement weight that counts as a "strong" block
    NET = 0.4      # net postsynaptic magnitude that counts as a real opposite lean

    a_flags, b_flags = [], []
    for drug in drugs:
        if is_combination(drug):
            continue  # a combo "A + B" has no unified flow (handled in the viewer)
        tone = defaultdict(float)          # system -> summed toneSign * affinity
        tone_drivers = defaultdict(list)   # system -> [(sign, driver_label)]
        postsyn = defaultdict(float)       # system -> summed effectSign * affinity
        postsyn_targets = defaultdict(set)  # system -> {receptor ids with an effect}
        strong_blocks = []                 # (system, target_id, base-region set)
        for b in drug.get("bindings", []):
            if b.get("affinity_only"):
                continue  # measured affinity, no direction -> never animates
            target = drug_targets.get(b.get("target"), {})
            system = target.get("system")
            if not system:
                continue
            action = b.get("action")
            aff = _affinity_weight(b.get("ki"))
            sign, driver = _tone_of(target, action, rec_meta, tone_rules)
            if sign:
                tone[system] += sign * aff
                tone_drivers[system].append((sign, driver))
                continue
            effect = drug_actions.get(action, {}).get("effect")
            es = effect_sign.get(effect, 0)
            if es:
                postsyn[system] += es * aff
                postsyn_targets[system].add(b["target"])
            if (effect == "block" and aff >= STRONG
                    and target.get("type") in ("receptor", "receptor_group")):
                strong_blocks.append(
                    (system, b["target"], _target_regions(target, rec_meta)))

        # 8a: flow direction opposes the net postsynaptic lean on the same system.
        for system, tsum in tone.items():
            if system not in system_flow_kinds or abs(tsum) < 1e-9:
                continue
            flow_dir = 1 if tsum > 0 else -1
            pnet = postsyn.get(system, 0.0)
            if (flow_dir > 0 and pnet <= -NET) or (flow_dir < 0 and pnet >= NET):
                drivers = sorted({drv for sgn, drv in tone_drivers[system]
                                  if sgn == flow_dir and drv})
                a_flags.append((
                    drug["id"], system, "up" if flow_dir > 0 else "down",
                    "; ".join(drivers) or "?",
                    "block" if pnet < 0 else "boost",
                    sorted(postsyn_targets[system])))

        # 8b: boosts a system's flow into regions whose receptors it strongly blocks.
        up_systems = {s for s, v in tone.items()
                      if s in system_flow_kinds and v > 0}
        by_system = defaultdict(lambda: (set(), set()))  # system -> (recs, regions)
        for system, tid, regions in strong_blocks:
            if system not in up_systems:
                continue
            hit = regions & arrives_in.get(system_flow_kinds[system], set())
            if hit:
                recs, regs = by_system[system]
                recs.add(tid)
                regs |= hit
        for system, (recs, regs) in by_system.items():
            b_flags.append((drug["id"], system, sorted(recs), sorted(regs)))

    for did, system, direction, drivers, lean, blocked in sorted(a_flags):
        report.review(
            f"drug {did!r}: {system} flow modeled {direction} ({drivers}) but its "
            f"postsynaptic {system} bindings net-{lean} ({', '.join(blocked)})")
    for did, system, recs, regs in sorted(b_flags):
        report.review(
            f"drug {did!r}: boosts {system} flow into {', '.join(regs)} yet blocks "
            f"{system} receptor(s) expressed there ({', '.join(recs)})")
    report.ok(
        f"{len(a_flags)} flow/postsynaptic + {len(b_flags)} flow-into-blocked-region "
        f"mismatches flagged (mostly the intended presynaptic-tone vs. postsynaptic-"
        f"block split; review, not a gate)")


_APP_VERSION_RE = re.compile(r"""__APP_VERSION__\s*=\s*["']([^"']+)["']""")

# The changelog category vocabulary, imported rather than restated: the authoring
# module owns it (adding one there must not need an edit here). That module is
# stdlib-only and imports nothing else, so this stays a cheap standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent / "data_generators"))
from changelog import CATEGORIES as CHANGELOG_CATEGORIES  # noqa: E402

# The PharmFreq export reader, imported rather than restated: family 12
# rebuilds the emitted quotes with the very code that wrote them, which is
# the whole point of the derivation gate (see data_generators/pharmfreq.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_generators import clinpgx, cpic, freshness, node_id, pharmfreq, unknown  # noqa: E402
from data_generators.node_kinds import NODE_KINDS, backed  # noqa: E402
from text_fold import alnum_key  # noqa: E402
from drugs_io import is_combination  # noqa: E402
from page_file import page_file  # noqa: E402 (refuses a path-like page)
import stahl_index  # noqa: E402 (the one INDEX.md reader)
from data_generators import release_modulation as RELMOD  # noqa: E402
from data_generators import demographics as DEMOG  # noqa: E402
# The drug + its formulations, the holders of brands / Tmax / T½ (one walker, so the
# grade and quote walks cannot skip a formulation's claims).
from data_generators.provenance import product_holders  # noqa: E402
# The curated contradictions, keyed by citation site and resolved through the one site
# grammar (tools/sourcing/citation_site.py), exactly as the generator applies them.
from data_generators.quotes.contradictions import CONTRADICTIONS  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent / "sourcing"))
import citation_site as CS  # noqa: E402

# The pathway per-claim word tests, imported for the same reason: family 5 re-runs the
# very test that graded a transmitter/sign sub-claim, so a hand-edited or stale ``claims``
# block (a source that does not name what it is cited for) fails instead of shipping.
from data_generators.quotes.attestation import (  # noqa: E402
    BASE_GRADE as CLAIM_BASE_GRADE,
    pattern_for as claim_pattern,
)


def _holder_ctxs(ctx, drug):
    """``(context label, holder)`` for the drug and each of its formulations."""
    return [(ctx if h is drug else f"{ctx} formulation {h.get('release')}", h)
            for h in product_holders(drug)]


def _listed(ctx, sources, short_ok, facet, owner):
    for i, src in enumerate(sources or []):
        yield f"{ctx}[{i}]", src, short_ok, facet, owner


def iter_drug_sources(drug):
    """THE walk over every quote-level citation a drug record carries, shared by the
    grade family (4) and the quote family (5) so a facet added here is both graded and
    quote-gated. Yields ``(ctx, source, short_ok, facet, owner)``: ``short_ok`` when the
    quote is short by design (a class label, one table cell, a brand name, a
    ``Label: value`` line), ``facet`` names the collection and ``owner`` is the record
    holding the list (a binding, an enzyme row, a withdrawal, ...)."""
    did = f"drug {drug.get('id')}"
    for b in drug.get("bindings", []) or []:
        yield from _listed(f"{did} binding {b.get('target')} sources", b.get("sources"),
                           False, "binding", b)
    yield from _listed(f"{did} nbn_sources", drug.get("nbn_sources"), False, "nbn", drug)
    # A class quote is the class label itself ("Stimulant"): short by design.
    yield from _listed(f"{did} category_sources", drug.get("category_sources"), True,
                       "category", drug)
    # The molecule and each formulation: a release read off a brand's own suffix cites
    # that brand ("Seroquel XR"), a duration is one labelled cell ("Half-life 10 hours").
    for hctx, h in _holder_ctxs(did, drug):
        for f in ("half_life_sources", "tmax_sources", "release_sources"):
            yield from _listed(f"{hctx} {f}", h.get(f), True, f, h)
        for br in h.get("brands", []) or []:
            yield from _listed(f"{hctx} brand {br.get('name')} sources", br.get("sources"),
                               True, "brand", br)
    for f in ("first_approval_sources", "prodrug_sources", "constituents_sources",
              "therapeutic_range_sources", "alert_level_sources"):
        yield from _listed(f"{did} {f}", drug.get(f), False, f, drug)
    # A PubChem quote is one short `Label: value` line by design ("XLogP3: 3.2").
    for f in PHYSCHEM_SOURCES:
        yield from _listed(f"{did} {f}", drug.get(f), True, f, drug)
    for wi, w in enumerate(drug.get("withdrawals", []) or []):
        yield from _listed(f"{did} withdrawals[{wi}] sources", w.get("sources"), False,
                           "withdrawal", w)
    # A workup quote can be one RCP bullet under its heading ("Ionogramme sanguin,
    # numeration et formule sanguine."), so it may be short by design.
    for wi, w in enumerate(drug.get("workup", []) or []):
        yield from _listed(f"{did} workup[{wi}] sources", w.get("sources"), True,
                           "workup", w)
    # Holder names are short register strings ("holder: UCB PHARMA"), by design.
    for h in drug.get("holders", []) or []:
        yield from _listed(f"{did} holders[{h.get('market')}] sources", h.get("sources"),
                           True, "holder", h)
    for f in ("originator_sources", "originator_now_sources", "originator_country_sources"):
        yield from _listed(f"{did} {f}", drug.get(f), False, f, drug)
    # One cell of the drug's own metabolism table ("Inhibits CYP2D6").
    for e in drug.get("enzymes", []) or []:
        yield from _listed(f"{did} enzyme {e.get('enzyme')} sources", e.get("sources"),
                           True, "enzyme", e)
    # The per-parent half of a metabolite: "X is a metabolite of <did>" + the enzymes
    # making it from <did>. Its molecule facts are walked once, off metabolites.jsonl.
    for m in drug.get("metabolites", []) or []:
        mid = f"{did} metabolite {m.get('id')}"
        yield from _listed(f"{mid} sources", m.get("sources"), False, "metabolite", m)
        for fb in m.get("formed_by", []) or []:
            yield from _listed(f"{mid} formed_by {fb.get('enzyme')} sources",
                               fb.get("sources"), False, "formed_by", fb)


def check_innervation(report, meta, structures, projections, receptors):
    """Family 10: per-transmitter-system **innervation coverage** (warns, never errors).

    The dots and the arrows are independent node kinds with wildly different coverage:
    a region lights for a drug because it *expresses* one of the drug's targets
    (``receptor_locations``, sourced in bulk from GtoPdb + Allen), while an arrow needs
    its own hand-found textbook quote. So a region can carry six adrenergic receptors
    with no noradrenergic pathway drawn anywhere near it, and the viewer honestly says
    "acts here" while showing no supply. That reads as a contradiction to a visitor,
    and it is invisible to every other family: nothing is dangling, nothing is
    ungraded, the data is simply thin in one layer.

    So: for each system in ``meta.system_flow_kinds``, compare the regions expressing
    its receptors + non-receptor targets against the regions its projections touch, and
    list the difference. NOT a gate. A gap is usually a missing *pathway* from a source
    nucleus that already exists (raphe -> striatum), occasionally a missing *structure*
    (the nucleus basalis was one: cortical M1-M5 with no cholinergic source at all).
    Glutamate + GABA are deliberately absent from the map (they are not diffuse
    ascending systems), so they never appear here.

    Also runs the mirror question, which catches the opposite hole: a pathway landing
    where no receptor of its own transmitter is recorded means the *expression* layer
    is missing something. A system's own source nuclei are excluded (a nucleus need not
    express the receptors it projects onto)."""
    report.header("10. Innervation coverage (transmitter systems)")
    flow = (meta.get("system_flow_kinds") or {})
    if not flow:
        report.warn("meta.system_flow_kinds is empty; skipping innervation coverage")
        return
    names = {_base_id(s["id"]): s.get("base_name") or _base_id(s["id"])
             for s in structures}

    # Where each system is expressed: its receptors' locations + its non-receptor
    # targets' regions. A ubiquitous receptor is everywhere by definition, so it can
    # never be part of a gap and would only drown the signal.
    expressed = defaultdict(set)
    owners = defaultdict(lambda: defaultdict(set))
    everywhere = set()   # systems carrying a ubiquitous receptor: expressed in ALL
    for rec in receptors:
        kind = flow.get(rec.get("family"))
        if kind and rec.get("ubiquitous"):
            everywhere.add(kind)
        if not kind or rec.get("ubiquitous"):
            continue
        for base in rec.get("locations") or []:
            expressed[kind].add(base)
            owners[kind][base].add(rec.get("id"))
    for tid, tgt in (meta.get("drug_targets") or {}).items():
        kind = flow.get(tgt.get("system"))
        if not kind or tgt.get("receptor"):   # receptor-backed: counted above
            continue
        for base in tgt.get("regions") or []:
            expressed[kind].add(base)
            owners[kind][base].add(tid)

    # Where each system's pathways go. ``projections`` is already mirror-expanded, so
    # both hemispheres are present; either endpoint counts as innervated.
    reached, sources = defaultdict(set), defaultdict(set)
    for p in projections:
        kind = p.get("kind")
        reached[kind].add(_base_id(p.get("from")))
        reached[kind].add(_base_id(p.get("to")))
        sources[kind].add(_base_id(p.get("from")))

    for kind in sorted(set(flow.values())):
        exp, got = expressed[kind], reached[kind]
        gap = sorted(exp - got, key=lambda b: (-len(owners[kind][b]), b))
        if gap:
            report.warn(
                f"{kind}: {len(gap)}/{len(exp)} region(s) express it but no {kind} "
                f"pathway reaches them: "
                + ", ".join(f"{names.get(b, b)} ({len(owners[kind][b])})" for b in gap))
        else:
            report.ok(f"{kind}: every one of the {len(exp)} region(s) expressing it "
                      "is reached by a pathway")
        # The reverse question asks about EXPRESSION, so it must count the ubiquitous
        # receptors the forward gap deliberately drops: a system with one is expressed
        # everywhere, and can never be landed on blind.
        blind = [] if kind in everywhere else sorted((got - exp) - sources[kind])
        if blind:
            report.warn(f"{kind}: a {kind} pathway lands in {', '.join(blind)} but no "
                        f"{kind} receptor/target is recorded there (expression gap)")

    # A system with receptors but no projection kind at all has no source nucleus in
    # the model. Often correct (opioid / cannabinoid / sigma are local neuromodulators
    # with no single source), but it is also how a genuinely missing source shows up.
    unmapped = defaultdict(set)
    for rec in receptors:
        fam = rec.get("family")
        if fam and fam not in flow and not rec.get("ubiquitous"):
            unmapped[fam] |= set(rec.get("locations") or [])
    if unmapped:
        report.warn(
            "system(s) with receptors but no projection kind at all (no modeled "
            "source nucleus; expected for a local neuromodulator, a real hole for a "
            "diffuse one): "
            + ", ".join(f"{fam} ({len(regs)} region(s))"
                        for fam, regs in sorted(unmapped.items(),
                                                key=lambda kv: -len(kv[1]))))


def check_changelog(report):
    """Family 9: the release notes the viewer pops up after an update.

    Cheap structural checks (well-formed, ordered, no duplicates), plus the one that
    actually matters: the running version must have notes. Bumping version.js without
    writing them ships an update that announces nothing, and nobody notices until a
    visitor sees an empty popup."""
    report.header("9. Changelog (release notes per version)")
    before = report.errors
    path = DATA_DIR / "changelog.json"
    version_js = REPO_ROOT / "public" / "version.js"
    if not path.exists():
        report.error("public/data/changelog.json is missing (run generate_data.py)")
        return
    try:
        releases = json.loads(path.read_text(encoding="utf-8")).get("versions") or []
    except json.JSONDecodeError as exc:
        report.error(f"changelog.json is not valid JSON: {exc}")
        return

    keys, dates, seen = [], [], set()
    for release in releases:
        version = release.get("version")
        try:
            key = tuple(int(p) for p in re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version).groups())
        except (AttributeError, TypeError):
            report.error(f"changelog: {version!r} is not a major.minor.patch version")
            continue
        if version in seen:
            report.error(f"changelog: version {version} appears twice")
        seen.add(version)
        keys.append(key)
        released = str(release.get("date") or "")
        try:
            date.fromisoformat(released)
            dates.append(released)
        except ValueError:
            report.error(f"changelog {version}: {released!r} is not a YYYY-MM-DD date")
        if not release.get("entries"):
            report.error(f"changelog {version}: no entries (an empty release note)")
        for entry in release.get("entries") or []:
            if entry.get("category") not in CHANGELOG_CATEGORIES:
                report.error(f"changelog {version}: unknown category "
                             f"{entry.get('category')!r}")
            if not str(entry.get("text") or "").strip():
                report.error(f"changelog {version}: an entry has no text")
            for sha in entry.get("commits") or []:
                if not re.fullmatch(r"[0-9a-f]{7,40}", str(sha)):
                    report.error(f"changelog {version}: {sha!r} is not a commit sha")
    if keys != sorted(keys, reverse=True):
        report.error("changelog: versions are not newest-first (the viewer relies on "
                     "the order to show the releases since a visitor's last one)")
    if dates != sorted(dates, reverse=True):
        report.error("changelog: the release dates run backwards somewhere, so a "
                     "release would sit above an older version but carry an earlier date")

    match = _APP_VERSION_RE.search(version_js.read_text(encoding="utf-8")) \
        if version_js.exists() else None
    if not match:
        # An error, not a warning: version.js is committed and required, so an
        # unreadable one is a real defect (it once shipped EMPTY for two releases,
        # unnoticed because this only warned). With no version the panel header and
        # loading overlay lose their version tag and the What's new popup can never
        # decide a release is new, so a visitor is never told anything shipped.
        report.error("public/version.js: could not read __APP_VERSION__. The version "
                     "is what a visitor's browser compares against to see what is new, "
                     "so a build without one announces nothing")
    elif match.group(1) not in seen:
        report.error(f"version.js is {match.group(1)} but docs/changelog/{match.group(1)}/"
                     f"changelog.md does not exist. Every released version needs notes, "
                     f"else the What's new popup announces an update it cannot describe")
    if report.errors == before:
        report.ok(f"{len(releases)} version(s) of release notes, newest first, "
                  f"current version covered")


def check_baked_meshes(report, structures):
    """Family 11: the baked SDF geometry is current for the shapes it was baked from.

    The bake (tools/bake_meshes.mjs) replaces ~3.8s of in-browser meshing with a
    download, which means the geometry a visitor sees is no longer derived from the
    shape file at run time. So an edited shape with a stale bake would silently ship
    last week's brain, and look like nothing at all went wrong. The manifest records
    each shape file's SHA-256, and this re-hashes the file: that catches a stale bake
    without needing Node here (re-meshing to compare would mean a Python marching
    cubes, which is exactly the duplication the bake tool exists to avoid).

    Absence is fine, not an error: the viewer falls back to meshing in the browser
    (js/baked-meshes.js), so an unbaked clone is slow, not broken."""
    report.header("11. Baked meshes (pre-built SDF geometry)")
    mesh_dir = DATA_DIR / "meshes"
    manifest_path = mesh_dir / "index.json"
    if not manifest_path.exists():
        report.warn("public/data/meshes/index.json absent: the viewer will mesh the "
                    "brain in the browser (slower, but correct). Run: node tools/bake_meshes.mjs")
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"meshes/index.json is not valid JSON: {exc}")
        return

    baked = manifest.get("meshes") or {}
    # Every DISTINCT sdf shape file, the same set the bake tool collects.
    wanted = {}
    for row in structures:
        shape_file = row.get("shape_file")
        if not shape_file or shape_file in wanted:
            continue
        path = DATA_DIR.parent / shape_file
        if not path.exists():
            continue
        try:
            raw = path.read_bytes()
            if json.loads(raw.decode("utf-8")).get("type") != "sdf":
                continue
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        wanted[shape_file] = hashlib.sha256(raw).hexdigest()

    stale = []
    for shape_file, digest in sorted(wanted.items()):
        entry = baked.get(shape_file)
        if entry is None:
            stale.append(f"{shape_file}: no baked mesh")
            continue
        if entry.get("spec_sha256") != digest:
            stale.append(f"{shape_file}: shape edited since the bake")
        blob = mesh_dir / str(entry.get("file") or "")
        if not blob.exists():
            stale.append(f"{shape_file}: {entry.get('file')} is missing")
        elif blob.stat().st_size != entry.get("bytes"):
            stale.append(f"{shape_file}: {entry.get('file')} size disagrees with the manifest")
    for orphan in sorted(set(baked) - set(wanted)):
        stale.append(f"{orphan}: baked, but no structure uses it any more")

    if stale:
        for line in stale:
            report.error(f"baked mesh out of date: {line}")
        report.error("run `node tools/bake_meshes.mjs` and commit public/data/meshes/")
        return
    total = sum(int(e.get("bytes") or 0) for e in baked.values())
    report.ok(f"{len(baked)} baked mesh(es) current with their shape files "
              f"({total / 1024 / 1024:.2f} MB, served compressed)")


def check_enzyme_variability(report, meta, drugs):
    """Family 12: the metabolizer-status profiles, re-derived from their pinned tables.

    Every other corpus proves a quote by finding it verbatim in prose somebody else
    wrote. PharmFreq (corpus #13) publishes a table instead, and the sentence a reader
    sees is one this repo composes out of it, so there is no page to look in: writing
    that sentence to a page file and then finding it there would prove only that the
    same code ran twice.

    So the proof runs the other way. The export is committed under `tools/data/`
    (small, freely redistributable, unlike the books), the cache that built the profiles
    pins each file's sha256, and this rebuilds every emitted profile and quote straight
    off those files. A hand-edited frequency, a stale cache, a refreshed download nobody
    re-ran the fetcher over: each one lands here as an error, on any clone, with no
    author-side material needed.
    """
    report.header("12. Enzyme variability (profiles re-derived from the pinned export)")
    corpora = meta.get("source_corpora") or {}
    tsv_corpora = {c: e for c, e in corpora.items() if e.get("tsv_dir")}
    if not tsv_corpora:
        report.ok("no committed-table corpus to re-derive")
        return
    for corpus, entry in sorted(tsv_corpora.items()):
        export = REPO_ROOT / entry["tsv_dir"]
        if not export.is_dir():
            report.error(f"{corpus}: {entry['tsv_dir']} is missing, yet the corpus is "
                         f"committed with the repo (its quotes cannot be re-derived)")
            return
        pins = entry.get("export_sha256") or {}
        if not pins:
            report.error(f"{corpus}: declares {entry['tsv_dir']} but pins no file "
                         f"sha256, so nothing anchors its quotes")
            return
        # Every file that looks like part of this export, by the extension the pins
        # themselves use (PharmFreq ships TSVs, CPIC one JSON), so a new sibling data
        # file nothing anchors is caught while the dir's README is left alone.
        suffixes = {Path(name).suffix for name in pins}
        on_disk = {p.name for p in export.iterdir()
                   if p.is_file() and p.suffix in suffixes}
        fetcher = f"tools/fetch/fetch_{corpus}.py"
        for name in sorted(set(pins) | on_disk):
            if name not in on_disk:
                report.error(f"{corpus}: pins {name}, which is not in "
                             f"{entry['tsv_dir']}")
            elif name not in pins:
                report.error(f"{corpus}: {entry['tsv_dir']}/{name} is not pinned "
                             f"(re-run {fetcher})")
            elif pharmfreq.sha256(str(export / name)) != pins[name]:
                report.error(f"{corpus}: {entry['tsv_dir']}/{name} no longer hashes to "
                             f"its pin, so the emitted numbers are not the ones in it "
                             f"(re-run {fetcher})")
        if report.errors:
            return

    export = REPO_ROOT / tsv_corpora["pharmfreq"]["tsv_dir"]
    try:
        raw = pharmfreq.read_export(str(export))
    except pharmfreq.ExportError as exc:
        report.error(f"pharmfreq: {exc}")
        return

    n = 0
    for eid, enzyme in sorted((meta.get("enzymes") or {}).items()):
        var = enzyme.get("variability")
        if not var:
            continue
        gene = var.get("gene")
        ctx = f"enzyme {eid} variability"
        if gene not in raw:
            report.error(f"{ctx}: cites gene {gene!r}, which the export does not cover")
            continue
        if pharmfreq.GENE_ENZYMES.get(gene) != eid:
            report.error(f"{ctx}: gene {gene!r} is mapped to "
                         f"{pharmfreq.GENE_ENZYMES.get(gene)!r}, not to {eid!r}")
            continue
        want_profile = pharmfreq.ordered_profile(raw[gene])
        if var.get("profile") != want_profile:
            report.error(f"{ctx}: the emitted profile is not what {gene} reads in the "
                         f"export (re-run tools/fetch/fetch_pharmfreq.py)")
            continue
        # Key order is deliberately NOT checked: the viewer walks
        # `meta.metabolizer_groups` and looks each group up, so the profile is a
        # mapping and the cache is free to serialize it sorted.
        want_quote = pharmfreq.quote_for(gene, want_profile)
        srcs = var.get("sources") or []
        if not srcs:
            report.error(f"{ctx}: carries a profile but no source")
            continue
        for i, src in enumerate(srcs):
            if src.get("page") != gene:
                report.error(f"{ctx} sources[{i}]: page {src.get('page')!r} is not the "
                             f"gene symbol {gene!r} the profile is keyed by")
            if src.get("quote") != want_quote:
                report.error(f"{ctx} sources[{i}]: the quote is not the one the export "
                             f"yields for {gene} (re-run tools/fetch/fetch_pharmfreq.py)")
            else:
                n += 1

    covered = {eid for eid, e in (meta.get("enzymes") or {}).items()
               if e.get("variability")}
    uncovered = sorted(set(pharmfreq.GENE_ENZYMES.values()) - covered)
    if uncovered:
        report.warn(f"mapped to a PharmFreq gene but carrying no profile: "
                    f"{', '.join(uncovered)}")
    report.ok(f"{n} metabolizer-status quote(s) re-derived from the pinned export, "
              f"exact match")
    check_cpic_guidance(report, meta, drugs)


def check_cpic_guidance(report, meta, drugs):
    """Family 12, second half: CPIC's guidance, re-derived from its pinned export.

    Same mechanism as the profiles above and for a different reason. The quote here IS
    somebody else's sentence, so it could be gated against a page; the point of
    re-deriving instead is that this is the one corpus whose text is **clinical advice**
    ("use 50% of the typical dose"), so every emitted word has to come out of the pinned
    file by code, with no step in between where a sentence could be trimmed, joined or
    paraphrased into saying something CPIC did not.

    Checks the whole shape, not just the quotes: the gene-drug pairs present, each row's
    phenotype / implication / recommendation / classification / assumption, and both of
    its citations. A pair that drifts, or one the emitted data invents, is an error.
    """
    corpora = meta.get("source_corpora") or {}
    if "cpic" not in corpora:
        report.ok("no CPIC corpus to re-derive")
        return
    try:
        want = cpic.guidance_for(cpic.read_export(cpic.export_path(str(REPO_ROOT))))
    except cpic.ExportError as exc:
        report.error(f"cpic: {exc}")
        return

    got = {d["id"]: d["pgx"] for d in drugs if d.get("pgx")}
    for drug in sorted(set(want) | set(got)):
        if drug not in got:
            report.error(f"cpic: the export carries guidance for {drug}, which the "
                         f"emitted drug does not (re-run tools/generate_data.py)")
            continue
        if drug not in want:
            report.error(f"drug {drug} carries CPIC guidance the export does not "
                         f"(re-run tools/fetch/fetch_cpic.py)")
            continue
    n = 0
    for drug in sorted(set(want) & set(got)):
        blocks, emitted = want[drug], got[drug]
        if len(blocks) != len(emitted):
            report.error(f"drug {drug} pgx: {len(emitted)} gene block(s) emitted, "
                         f"{len(blocks)} in the export")
            continue
        for block, out in zip(blocks, emitted):
            ctx = f"drug {drug} pgx {block['gene']}"
            for key in ("gene", "enzyme", "level"):
                if out.get(key) != block[key]:
                    report.error(f"{ctx}: {key} is {out.get(key)!r}, not "
                                 f"{block[key]!r} as the export reads")
            if (out.get("guideline") or {}).get("id") != block["guideline"]["id"]:
                report.error(f"{ctx}: cites a guideline the export does not")
            if len(out.get("rows") or []) != len(block["rows"]):
                report.error(f"{ctx}: {len(out.get('rows') or [])} row(s) emitted, "
                             f"{len(block['rows'])} in the export")
                continue
            for row, wrow in zip(out["rows"], block["rows"]):
                rctx = f"{ctx} {wrow['phenotype']}"
                for key in ("phenotype", "implication", "recommendation",
                            "classification"):
                    if row.get(key) != wrow[key]:
                        report.error(f"{rctx}: {key} is not what the export reads "
                                     f"(re-run tools/fetch/fetch_cpic.py)")
                if (row.get("assumes") or {}) != (wrow.get("assumes") or {}):
                    report.error(f"{rctx}: the co-dosed-gene assumption differs from "
                                 f"the export's")
                # Two citations per node: CPIC's implication, then its recommendation.
                # Both quotes must be the export's own strings, verbatim.
                srcs = row.get("sources") or []
                quotes = [s.get("quote") for s in srcs]
                if quotes != [wrow["implication"], wrow["recommendation"]]:
                    report.error(f"{rctx}: its {len(srcs)} citation(s) do not quote the "
                                 f"export's implication then its recommendation")
                    continue
                for i, src in enumerate(srcs):
                    if src.get("page") != block["guideline"]["id"]:
                        report.error(f"{rctx} sources[{i}]: page {src.get('page')!r} is "
                                     f"not the guideline id "
                                     f"{block['guideline']['id']!r}")
                    else:
                        n += 1
    n += check_cpic_enzyme_claims(report, want, drugs)
    check_cpic_enzyme_coverage(report, want, drugs)
    report.ok(f"{n} CPIC guidance quote(s) re-derived from the pinned export, "
              f"exact match")


def check_clinpgx_variants(report, meta, receptors):
    """Family 12, last part: ClinPGx's variant annotations, re-derived from their export.

    Every ``receptor_variant`` node is rebuilt from the pinned export by the generator's
    own reader (``clinpgx.variant_nodes``) and must match the emitted one field for
    field, its quotes included: ClinPGx's sentences are copied by code, so no step may
    trim or reword one. An export row no owner carries (an owner id the emitted data
    does not have) and an emitted node the export does not hold are both errors.
    """
    corpora = meta.get("source_corpora") or {}
    if "clinpgx" not in corpora:
        report.ok("no ClinPGx corpus to re-derive")
        return
    try:
        want = clinpgx.variant_nodes(
            clinpgx.read_export(clinpgx.export_path(str(REPO_ROOT))))
    except clinpgx.ExportError as exc:
        report.error(f"clinpgx: {exc}")
        return
    got = {("receptor", r["id"]): r.get("variants") or [] for r in receptors}
    got.update((("target", tid), t.get("variants") or [])
               for tid, t in (meta.get("drug_targets") or {}).items()
               if isinstance(t, dict) and t.get("type") != "receptor")
    keys = ("annotation", "variant", "genes", "level", "categories", "drugs",
            "drug_names", "phenotypes", "pmids", "genotypes", "population", "url")
    n = 0
    for owner in sorted(set(want) | {k for k, v in got.items() if v}):
        ctx = f"{owner[0]} {owner[1]} variants"
        if owner not in got:
            report.error(f"{ctx}: the export holds {len(want[owner])} annotation(s) for "
                         f"an owner the emitted data does not have (fix genes.GENE_OWNERS)")
            continue
        wants, emitted = want.get(owner, []), got[owner]
        if [w["annotation"] for w in wants] != [e.get("annotation") for e in emitted]:
            report.error(f"{ctx}: emitted annotations are not the export's (re-run "
                         f"tools/generate_data.py)")
            continue
        for w, e in zip(wants, emitted):
            for key in keys:
                if e.get(key) != w.get(key):
                    report.error(f"{ctx} {w['annotation']}: {key} is {e.get(key)!r}, not "
                                 f"{w.get(key)!r} as the export reads")
            quotes = [s.get("quote") for s in e.get("sources") or []]
            if quotes != [s["quote"] for s in w["sources"]]:
                report.error(f"{ctx} {w['annotation']}: its citations do not quote the "
                             f"export's genotype sentences verbatim")
                continue
            for i, src in enumerate(e["sources"]):
                if src.get("corpus") != "clinpgx" or src.get("page") != w["annotation"]:
                    report.error(f"{ctx} {w['annotation']} sources[{i}]: not cited to "
                                 f"clinpgx page {w['annotation']!r}")
                else:
                    n += 1
    report.ok(f"{n} ClinPGx variant quote(s) re-derived from the pinned export, "
              f"exact match")


def check_cpic_enzyme_coverage(report, want, drugs):
    """A gene CPIC doses a drug on, that the drug's enzyme list does not carry.

    Not an error, and deliberately not one: it means no corpus here states the route,
    which is a hole in the sources and not a mistake in the data. Flagging it is still
    worth a line, because the panel then shows a reader advice about their CYP2C19
    speed over an Enzymes section that never mentions CYP2C19, and because the enzyme
    list feeds the derived drug-drug edges, so a missing route quietly removes
    interactions nobody sees go missing.

    Clomipramine was exactly that case (fixed in 3.93.1: 11 interaction edges appeared
    with the row). This exists so the next one is reported rather than noticed by eye,
    since either side can produce it: a CPIC refresh adding a pair, or a CYP fetcher
    re-run dropping a row.
    """
    by_id = {d["id"]: d for d in drugs}
    for drug in sorted(want):
        doc = by_id.get(drug)
        if doc is None:
            continue
        have = {e["enzyme"] for e in doc.get("enzymes") or []}
        for block in want[drug]:
            if block["enzyme"] in have:
                continue
            report.warn(f"drug {drug}: CPIC doses it on {block['gene']}, which its "
                        f"enzyme list does not carry, so the guidance sits over a "
                        f"section that never names the gene (no corpus here states "
                        f"the route; see docs/SOURCING_GAPS.md)")


def check_cpic_enzyme_claims(report, want, drugs) -> int:
    """The enzyme routes CPIC's own wording states (see ``cpic.enzyme_claims_for``).

    An enzyme row sourced to CPIC is the one place this corpus is read for something
    other than guidance, so it gets the same treatment: re-derived from the export and
    compared. The gate runs both ways. A row the re-derivation does not produce is an
    error (it would mean we asserted a metabolic route CPIC never phrased), and a claim
    the re-derivation produces that no drug carries is checked only for its quote,
    because another corpus legitimately owns that (enzyme, role) pair already.
    """
    claims = {(drug, r["enzyme"]): r["sources"][0]["quote"]
              for drug, rows in cpic.enzyme_claims_for(want).items() for r in rows}
    n = 0
    for drug in drugs:
        for row in drug.get("enzymes") or []:
            src = (row.get("sources") or [{}])[0]
            if src.get("corpus") != "cpic":
                continue  # another corpus owns this row
            quote = src.get("quote")
            ctx = f"drug {drug['id']} enzymes[{row['enzyme']}]"
            if claims.get((drug["id"], row["enzyme"])) != quote:
                report.error(f"{ctx}: cites a CPIC sentence the export does not state "
                             f"for this pair (re-run tools/fetch/fetch_cpic.py)")
            elif row.get("role") != "substrate":
                report.error(f"{ctx}: CPIC's wording states a route, so the role can "
                             f"only be 'substrate', not {row.get('role')!r}")
            else:
                n += 1
    return n


def _editable_sources(node, editable, out):
    """Collect every source dict of an ``editable`` corpus in this (rehydrated) subtree."""
    if isinstance(node, dict):
        if node.get("corpus") in editable:
            out.append(node)
        for value in node.values():
            _editable_sources(value, editable, out)
    elif isinstance(node, list):
        for value in node:
            _editable_sources(value, editable, out)
    return out


def _unknown_stamps(drugs, metabolites=(), receptors=(), meta=None):
    """Every emitted UNKNOWN stamp, as ``(where, kind, claim, stamp)``: a drug or
    metabolite binding direction (kind ``drug_binding_action``, claim = the binding),
    or a receptor's / non-receptor target's effects (kind ``receptor_effect``, claim =
    the owner record). See data_generators/unknown.py."""
    owners = [(f"drug {d.get('id')}", d) for d in drugs] + [
        (f"metabolite {m.get('id')}", m) for m in metabolites]
    for label, owner in owners:
        for b in owner.get("bindings", []) or []:
            if b.get("unknown"):
                yield (f"{label} binding {b.get('target')}", "drug_binding_action", b,
                       b["unknown"])
    effect_owners = [(f"receptor {r.get('id')}", r) for r in receptors] + [
        (f"target {tid}", t) for tid, t in ((meta or {}).get("drug_targets") or {}).items()
        if isinstance(t, dict) and t.get("type") != "receptor"]
    for label, owner in effect_owners:
        if owner.get("effects_unknown"):
            yield f"{label} effects", "receptor_effect", owner, owner["effects_unknown"]


def check_freshness(report, meta, collections, today=None, metabolites=(), receptors=()):
    """Family 13: every cited page of an editable online corpus was downloaded recently.

    A book page does not change under a citation; a Wikipedia article or a live database
    does, so a quote checked against an old download may no longer be on today's page.
    Each source of a corpus flagged `editable` in `meta.source_corpora` carries the date
    its page was downloaded (`fetched`, stamped by generate_data.py from the committed
    ledger, see data_generators/freshness.py). An error when a source has no date (the
    ledger does not know its page: run tools/fetch/stamp_fetch_dates.py) or when the date
    is more than FRESHNESS_MAX_MONTHS old (refetch the corpus). Author-side, a page
    whose own header date disagrees with the emitted one means a refetch was not
    restamped. Runs on a clone (no page material needed for the first two), and alone
    via `--only freshness` from the pre-push hook.
    """
    months = freshness.FRESHNESS_MAX_MONTHS
    report.header("13. Freshness (editable corpora downloaded within "
                  f"{months} months)")
    today = today or date.today()
    corpora = meta.get("source_corpora") or {}
    editable = {c for c, rec in corpora.items() if rec.get("editable")}
    if not editable:
        report.error("meta.source_corpora flags no corpus as editable")
        return
    undated, stale, drift = defaultdict(set), defaultdict(dict), defaultdict(set)
    n = 0
    for src in _editable_sources(collections, editable, []):
        n += 1
        corpus, page, fetched = src["corpus"], src.get("page"), src.get("fetched")
        where = "(bulk)" if page is None else str(page)
        if not isinstance(fetched, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fetched):
            undated[corpus].add(where)
            continue
        if freshness.is_stale(fetched, today, months):
            stale[corpus][where] = fetched
        path = freshness.page_path(corpus, page)
        on_disk = freshness.header_date(path) if path else None
        if on_disk and on_disk != fetched:
            drift[corpus].add(f"{where} (page {on_disk}, emitted {fetched})")

    def _some(items):
        items = sorted(items)
        return ", ".join(items[:8]) + (f" (+{len(items) - 8} more)" if len(items) > 8 else "")

    for corpus, pages in sorted(undated.items()):
        report.error(f"{corpus}: {len(pages)} cited page(s) carry no download date "
                     f"(run tools/fetch/stamp_fetch_dates.py, then generate_data.py): "
                     f"{_some(pages)}")
    for corpus, pages in sorted(stale.items()):
        report.error(f"{corpus}: {len(pages)} cited page(s) downloaded more than {months} "
                     f"months ago (oldest {min(pages.values())}); refetch the corpus "
                     f"(see tools/README.md): {_some(pages)}")
    for corpus, pages in sorted(drift.items()):
        report.error(f"{corpus}: {len(pages)} page(s) refetched but not restamped (run "
                     f"tools/fetch/stamp_fetch_dates.py): {_some(pages)}")
    # An UNKNOWN is a search result, and the literature moves: the same age limit.
    drugs = next((c for c in collections if isinstance(c, list) and c
                  and isinstance(c[0], dict) and "bindings" in c[0]), [])
    old_searches = {}
    for where, _k, _c, stamp in _unknown_stamps(drugs, metabolites, receptors, meta):
        searched = str(stamp.get("searched"))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", searched) and freshness.is_stale(
                searched, today, months):
            old_searches[where] = searched
    if old_searches:
        report.error(f"{len(old_searches)} UNKNOWN search(es) older than {months} months "
                     f"(oldest {min(old_searches.values())}); rerun the search (see "
                     f"tools/README.md): {_some(old_searches)}")
    if not (undated or stale or drift or old_searches):
        report.ok(f"{n} source(s) across {len(editable)} editable corpora, all downloaded "
                  f"within {months} months")


def main():
    argv = sys.argv[1:]
    verbose = "--verbose" in argv
    argv = [a for a in argv if a != "--verbose"]
    only = argv == ["--only", "freshness"]
    if argv and not only:
        print("usage: check_data.py [--verbose] [--only freshness]", file=sys.stderr)
        return 2
    report = Report(verbose=verbose)
    print(f"neurarium data integrity check\nreading {DATA_DIR}")

    meta = load_meta(report)
    structures = load_jsonl(report, "structures")
    projections = _expand_mirrored(load_jsonl(report, "projections"))
    circuits = load_jsonl(report, "circuits")
    projection_groups = load_jsonl(report, "projection_groups")
    receptors = load_jsonl(report, "receptors")
    drugs = load_jsonl(report, "drugs")
    metabolites = load_jsonl(report, "metabolites")
    addons = load_jsonl(report, "addons")

    # Rehydrate the externalized source quotes in place (collecting referenced +
    # dangling ids), so every check below sees the original inline source shape;
    # then report the quote table's referential integrity.
    quotes_by_id = load_quotes(report)
    referenced, dangling = set(), []
    rehydrate_quotes([meta, structures, projections, circuits, projection_groups,
                      receptors, drugs, metabolites, addons], quotes_by_id, referenced,
                     dangling)
    check_quotes(report, quotes_by_id, referenced, dangling)
    collections = [meta, structures, projections, circuits, projection_groups,
                   receptors, drugs, metabolites, addons]
    if only:
        check_freshness(report, meta, collections, metabolites=metabolites,
                        receptors=receptors)
        return _summary(report)

    args = (report, meta, structures, projections, circuits, projection_groups,
            receptors, drugs)
    check_duplicates(*args, metabolites)
    check_reachability(*args, addons, metabolites)
    check_todos(*args)
    check_provenance(*args, addons, metabolites)
    check_sources(report, meta, drugs, projections, structures, receptors, addons,
                  metabolites, circuits, projection_groups, CONTRADICTIONS)
    check_connectivity(report, structures, projections)
    check_ki_coverage(report, meta, drugs)
    check_flow_consistency(report, meta, drugs, projections, receptors)
    check_changelog(report)
    check_innervation(report, meta, structures, projections, receptors)
    check_baked_meshes(report, structures)
    check_enzyme_variability(report, meta, drugs)
    check_clinpgx_variants(report, meta, receptors)
    check_freshness(report, meta, collections, metabolites=metabolites,
                        receptors=receptors)
    return _summary(report)


def _summary(report):
    print(f"\nSummary: {report.errors} error(s), {report.warnings} warning(s)")
    if report.reviews and not report.verbose:
        print(f"         {report.reviews} review item(s) not listed "
              f"(intended-by-design eyeball lists; --verbose prints them)")
    if report.errors:
        print("FAILED: fix the errors above (warnings are informational).")
        return 1
    print("PASSED (warnings are informational).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
