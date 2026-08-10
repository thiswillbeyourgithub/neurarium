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
   would fall back to "no source" and mislead).

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

Built with the help of Claude Code.
"""

import csv
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

# A path like "...sources[3].url" (a citation) or "...source_corpora.<id>.url" (a
# corpus reference) is a source url: its TODO is the known backlog, reported on
# its own. Anything else is a stray TODO.
_SOURCE_URL_RE = re.compile(r"(\.sources\[\d+\]\.url|\.source_corpora\.[^.]+\.url)$")
# Trailing hemisphere suffix on a structure id ("frontal_R" -> "frontal").
_HEMISPHERE_RE = re.compile(r"_(R|L)$")
# Valid source provenance grades (mirrors generate_data.py PROVENANCE_LEVELS), the
# value the viewer renders as the grey/yellow/green source pill.
_PROVENANCE_LEVELS = {"llm", "sourced", "verified"}

# The knowledge-node kinds folded into the headline coverage, in the generator's order
# (mirrors provenance.py's by_kind minus "references", which points *at* a node rather
# than being one). Adding a node kind means adding it here too, in one place: both the
# coverage table and the self-consistency check read this.
NODE_KINDS = ("drug_bindings", "drug_nbn", "drug_brands", "drug_categories",
              "drug_half_life", "drug_enzymes", "drug_metabolites",
              "drug_metabolite_enzyme", "drug_metabolite_bindings",
              "projections", "circuits", "projection_groups", "receptors",
              "receptor_class", "receptor_sign", "receptor_synaptic",
              "receptor_locations", "receptor_density", "targets", "target_polarity",
              "target_locations", "target_density", "structures")


def _backed(counts):
    """Nodes resting on a real document: verified + uncertain + sourced.

    ``uncertain`` counts here on purpose (see quotes/uncertainty.py): the claim does
    have a quote-checked source, the badge only says the sentence does not attribute
    it. Only ``missing`` (a bare llm assertion or nothing at all) is unbacked.
    """
    return (counts.get("verified", 0) + counts.get("uncertain", 0)
            + counts.get("sourced", 0))


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

    Mirrors the viewer's rehydration (js/data.js): copies the quote node's
    ``corpus``/``page``/``quote``/``species`` onto the reference and drops the
    ``quote_id`` key, so every later check sees the original inline source shape.
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
                for k in ("corpus", "page", "quote", "species", "llm", "heading"):
                    if k in quote:
                        node[k] = quote[k]
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

    if not exact and not near and not name_dups:
        report.ok(f"{label}: {len(items)} entries, no duplicate ids or names")


def check_projection_dups(report, projections):
    pairs = Counter((p.get("from"), p.get("to")) for p in projections)
    dups = {pair: count for pair, count in pairs.items() if count > 1}
    for (src, dst), count in sorted(dups.items(), key=lambda kv: str(kv[0])):
        report.error(f"projections: {src} -> {dst} defined {count} times")
    if not dups:
        report.ok(f"projections: {len(projections)} pathways, no duplicate from->to")


def check_duplicates(report, meta, structures, projections, circuits,
                     projection_groups, receptors, drugs):
    report.header("1. Duplicates (exact + normalized)")
    check_id_collection(report, "structures", structures)
    check_id_collection(report, "receptors", receptors)
    check_id_collection(report, "drugs", drugs)
    check_id_collection(report, "circuits", circuits)
    check_id_collection(report, "projection groups", projection_groups)
    # drug_targets is a dict in meta; reshape to id-bearing records to reuse the
    # same machinery (the key is the id, the value carries the {en,fr} name).
    targets = [dict(value, id=key) for key, value in meta.get("drug_targets", {}).items()]
    check_id_collection(report, "targets", targets)
    check_projection_dups(report, projections)


# --------------------------------------------------------------------------- #
# 2. Reachability (referential integrity)
# --------------------------------------------------------------------------- #

def check_reachability(report, meta, structures, projections, circuits,
                       projection_groups, receptors, drugs):
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
    action_target_types = {
        "reuptake_inhibitor": {"transporter"},
        "releaser": {"transporter"},
        "vesicular_inhibitor": {"transporter", "vesicle_protein"},
        "vesicular_releaser": {"transporter"},
        "enzyme_inhibitor": {"enzyme"},
        "agonist": {"receptor", "receptor_group"},
        "partial_agonist": {"receptor", "receptor_group"},
        "antagonist": {"receptor", "receptor_group", "ion_channel"},
        "inverse_agonist": {"receptor", "receptor_group"},
        "pam": {"receptor", "receptor_group"},
        "nam": {"receptor", "receptor_group"},
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
        # Active metabolites: a linked drug_id must be a real drug, and any inline
        # metabolite binding target must be a known target (so it can be attributed
        # in the receptor 'Interacting drugs' list once bindings are sourced).
        for m in drug.get("metabolites", []) or []:
            link = m.get("drug_id")
            if link and link not in drug_ids:
                report.error(f"drug {did}: metabolite {m.get('name')!r} links "
                             f"drug_id {link!r} which is not a modeled drug")
            for binding in m.get("bindings", []) or []:
                if binding.get("target") not in targets:
                    report.error(f"drug {did}: metabolite {m.get('name')!r} binding "
                                 f"target {binding.get('target')!r} is not a known target")

    # Shared-metabolite consistency guard. One metabolite can be produced by several
    # modeled drugs (e.g. desipramine by imipramine AND lofepramine, mCPP by nefazodone
    # AND trazodone), so it appears once under each parent. Its bindings are intrinsic to
    # the molecule, not to which parent made it, so every occurrence MUST carry the same
    # bindings; the applier guarantees this (it keys by metabolite name and writes an
    # identical list to each parent), but a hand-edit to drugs_data.jsonl could diverge
    # the two inline copies. That would make the viewer show contradictory rows and the
    # tally count them inconsistently, so we fail loudly here. (Fold on the name only,
    # matching the tally + viewer identity key.)
    metab_occurrences = {}
    for drug in drugs:
        for m in drug.get("metabolites", []) or []:
            key = re.sub(r"[^a-z0-9]", "", (m.get("name") or "").lower())
            metab_occurrences.setdefault(key, []).append(
                (drug.get("id"), m.get("name"),
                 json.dumps(m.get("bindings", []) or [], sort_keys=True)))
    for key, occ in metab_occurrences.items():
        distinct = {b for _, _, b in occ}
        if len(occ) > 1 and len(distinct) > 1:
            parents = ", ".join(sorted(did for did, _, _ in occ))
            report.error(f"metabolite {occ[0][1]!r} is shared by drugs [{parents}] but "
                         f"carries DIFFERENT bindings under them; a metabolite's bindings "
                         f"are a property of the molecule and must be identical across "
                         f"parents (re-run apply_metabolite_bindings.py, which writes them "
                         f"consistently, or reconcile the hand-edit)")

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

    # --- corpus-url TODOs (expected, not flagged) ---
    # Per-claim sources are quote-level ``{corpus, page, quote}`` and carry no url of
    # their own (the viewer resolves the link from ``meta.source_corpora``). A book
    # corpus may legitimately have no free url (Stahl's ``url`` is "TODO"); the
    # provenance pill, not a link, is what conveys the grade, so this is expected and
    # merely reported, never warned.
    expected_no_link = 0
    for cid, corpus in (meta.get("source_corpora", {}) or {}).items():
        if isinstance(corpus, dict) and corpus.get("url") == "TODO":
            expected_no_link += 1
    if expected_no_link:
        report.ok(f"{expected_no_link} source corpus/corpora have no free url yet "
                  f"(expected: the provenance pill conveys the grade, not the url)")
    else:
        report.ok("every source corpus has a real url")


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
        return round(100 * _backed(c) / total) if total else 0

    def row(label, c, pct=None, suffix=""):
        pct = backed_pct(c) if pct is None else pct
        m = c.get("missing", 0)
        s = c.get("sourced", 0)
        u = c.get("uncertain", 0)
        sv = _backed(c)  # sourced-or-verified-or-uncertain = the backed count
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
    if by.get("references"):
        row("references", by["references"], suffix="   (pointers, not in headline)")


def check_provenance(report, meta, structures, projections, circuits,
                     projection_groups, receptors, drugs):
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
        for binding in drug.get("bindings", []):
            for i, src in enumerate(binding.get("sources", []) or []):
                grade(src.get("provenance"),
                      f"drug {drug.get('id')} binding {binding.get('target')} "
                      f"sources[{i}]")
        for i, src in enumerate(drug.get("nbn_sources", []) or []):
            grade(src.get("provenance"), f"drug {drug.get('id')} nbn_sources[{i}]")
        # The drug's class classification carries its own grade (default llm), plus
        # any quote-level category_sources that upgrade it.
        if drug.get("category_provenance"):
            grade(drug.get("category_provenance"),
                  f"drug {drug.get('id')} category_provenance")
        for i, src in enumerate(drug.get("category_sources", []) or []):
            grade(src.get("provenance"), f"drug {drug.get('id')} category_sources[{i}]")
        # Half-life (T½) node + each active-metabolite node (and a metabolite's own
        # T½ / inline bindings) carry their own quote-level grades, same shape.
        for i, src in enumerate(drug.get("half_life_sources", []) or []):
            grade(src.get("provenance"), f"drug {drug.get('id')} half_life_sources[{i}]")
        for mi, m in enumerate(drug.get("metabolites", []) or []):
            mid = f"drug {drug.get('id')} metabolite {m.get('name')}"
            for i, src in enumerate(m.get("sources", []) or []):
                grade(src.get("provenance"), f"{mid} sources[{i}]")
            for i, src in enumerate(m.get("half_life_sources", []) or []):
                grade(src.get("provenance"), f"{mid} half_life_sources[{i}]")
            for binding in m.get("bindings", []) or []:
                for i, src in enumerate(binding.get("sources", []) or []):
                    grade(src.get("provenance"),
                          f"{mid} binding {binding.get('target')} sources[{i}]")
        # A drug's description carries its own grade (llm synthesis vs sourced WP lead).
        if drug.get("description"):
            grade(drug.get("description_provenance"),
                  f"drug {drug.get('id')} description_provenance")

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
            parts = (c.get("verified", 0) + c.get("uncertain", 0)
                     + c.get("sourced", 0) + c.get("missing", 0))
            if parts != c.get("total", 0):
                report.error(f"provenance_stats by_kind[{kind}] buckets "
                             f"({parts}) do not sum to total ({c.get('total')})")
        a = stats.get("nodes", {})
        node_kinds = NODE_KINDS
        by = stats.get("by_kind", {})
        for key in ("total", "verified", "uncertain", "sourced", "missing"):
            want = sum(by.get(k, {}).get(key, 0) for k in node_kinds)
            if a.get(key) != want:
                report.error(f"provenance_stats nodes[{key}]={a.get(key)} "
                             f"!= sum over node kinds ({want})")
        backed = _backed(a)
        if a.get("backed") != backed:
            report.error(f"provenance_stats nodes.backed={a.get('backed')} "
                         f"!= verified+uncertain+sourced ({backed})")
        want_pct = round(100 * backed / a["total"]) if a.get("total") else 0
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
_STAHL_INDEX = REPO_ROOT / "data_sources" / "books" / "stahl" / "INDEX.md"
_STAHL_INDEX_ROW = re.compile(r"\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\[(\d+)-(\d+)\]")


def _fold_name(name):
    """A drug name reduced to its letters+digits, so ``Amphetamine (d,l)`` and the
    index's ``Amphetamine (D,L)`` compare equal."""
    return "".join(c for c in name.lower() if c.isalnum())


def stahl_index_rows():
    """``[(display drug name, first page, last page)]`` from Stahl's generated
    INDEX.md, in book order; empty when the author-side tree is absent.

    The one parser for that table: :func:`stahl_monograph_ranges` folds it for the
    monograph-range gate, and ``tools/fetch/fetch_quote_headers.py`` reads the
    display title (what a reader sees above a quote) off the same rows."""
    if not _STAHL_INDEX.exists():
        return []
    rows = []
    for line in _STAHL_INDEX.read_text(encoding="utf-8").splitlines():
        m = _STAHL_INDEX_ROW.match(line)
        if m:
            rows.append((m.group(1), int(m.group(2)), int(m.group(3))))
    return rows


def stahl_monograph_ranges():
    """``folded drug name -> (first page, last page)`` from Stahl's generated INDEX.md.

    ``None`` when the author-side book tree is absent (a plain clone), so the
    caller skips the check exactly like the verbatim-quote gate does."""
    ranges = {_fold_name(title): (lo, hi) for title, lo, hi in stahl_index_rows()}
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


def check_sources(report, meta, drugs, projections, structures, receptors):
    """The core of the sourcing system: confirm every quote-level source (a
    binding's ``sources``, a drug's ``nbn_sources``, and a projection's quote-level
    ``sources``) is actually present in the page it cites.

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
    breaking on a clone that lacks the sources."""
    report.header("5. Source quotes (verbatim in cited page)")
    corpora = meta.get("source_corpora", {})
    # The closed vocabulary the "uncertain" bullets draw their reason kinds from,
    # read from the data rather than restated here so the two cannot drift.
    reason_kinds = set(meta.get("uncertainty_reasons", {}))
    before = report.errors

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
            if pages_dir:
                md = REPO_ROOT / pages_dir / f"{page}.md"
                if md.exists():
                    text = normalize_for_match(md.read_text(encoding="utf-8"))
            page_cache[key] = text
        return page_cache[key]

    def check_one(ctx, src):
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

    def check_uncertainty(what, node):
        """Gate the "uncertain" badge's bullets on any node that carries them.

        Each bullet is itself a claim shown to the reader with its own pill, so each is
        gated like any other node: its quote must be verbatim on the cited page, its
        reason kind must be one the vocabulary defines, and a bullet with no source must
        SAY it is an absence of evidence rather than leave a silent blank. Shared by the
        drug bindings and the projections, which carry the same bullet shape.
        """
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

    for drug in drugs:
        did = drug.get("id")
        for binding in drug.get("bindings", []):
            # A binding that DECLARES the problem (the orange "uncertain" badge, whose
            # own bullets say the sentence attributes nothing) is not silently passing
            # a subject-less quote off as a green check, so the gate below stands down.
            declared = bool(binding.get("uncertainty"))
            for i, src in enumerate(binding.get("sources", []) or []):
                ctx = f"drug {did} binding {binding.get('target')} sources[{i}]"
                check_one(ctx, src)
                if not declared and _NO_SUBJECT_QUOTE.match(src.get("quote") or ""):
                    report.error(
                        f"{ctx}: quote is a subject-less mechanism -> side-effect rule "
                        f"({src.get('quote')!r}). Stahl's 'How Drug Causes Side Effects' "
                        f"block prints the same lines on every monograph in the class, so "
                        f"such a sentence never says THIS drug has the action: it cannot "
                        f"source a binding (an attributed one, 'By blocking X, IT can "
                        f"cause Y', can)")
            # A quote-carrying Ki source (corpus #9 wikipedia_pharm cites the verbatim
            # affinity-table row) is gated here like any other quote. A PDSP Ki cites a
            # CSV row (ki_id, no quote) and is verified by the CSV gate below instead, so
            # only feed a Ki source that actually carries a quote.
            ki_src = (binding.get("ki") or {}).get("source")
            if ki_src and ki_src.get("quote"):
                check_one(f"drug {did} binding {binding.get('target')} ki.source", ki_src)
            check_uncertainty(f"drug {did} binding {binding.get('target')}", binding)
        for i, src in enumerate(drug.get("nbn_sources", []) or []):
            check_one(f"drug {did} nbn_sources[{i}]", src)
        for i, src in enumerate(drug.get("category_sources", []) or []):
            check_one(f"drug {did} category_sources[{i}]", src)
        # Half-life quote + each metabolite's identity/T½/binding quotes are gated the
        # same way (verbatim substring on the cited corpus page).
        for i, src in enumerate(drug.get("half_life_sources", []) or []):
            check_one(f"drug {did} half_life_sources[{i}]", src)
        # Metabolism rows (fetch_cyp.py already gates these on the way in, but that
        # is the author-side pass; this is the backstop that also catches a later
        # hand-edit of the emitted data).
        for e in drug.get("enzymes", []) or []:
            for i, src in enumerate(e.get("sources", []) or []):
                check_one(f"drug {did} enzyme {e.get('enzyme')} sources[{i}]", src)
        for m in drug.get("metabolites", []) or []:
            mid = f"drug {did} metabolite {m.get('name')}"
            for i, src in enumerate(m.get("sources", []) or []):
                check_one(f"{mid} sources[{i}]", src)
            for i, src in enumerate(m.get("half_life_sources", []) or []):
                check_one(f"{mid} half_life_sources[{i}]", src)
            for f in m.get("formed_by", []) or []:
                for i, src in enumerate(f.get("sources", []) or []):
                    check_one(f"{mid} formed_by {f.get('enzyme')} sources[{i}]", src)
            for binding in m.get("bindings", []) or []:
                for i, src in enumerate(binding.get("sources", []) or []):
                    check_one(f"{mid} binding {binding.get('target')} sources[{i}]", src)
                # A metabolite binding's quote-carrying Ki (wikipedia_pharm table row) is
                # gated exactly like a drug binding's (a PDSP CSV Ki is checked below).
                ki_src = (binding.get("ki") or {}).get("source")
                if ki_src and ki_src.get("quote"):
                    check_one(f"{mid} binding {binding.get('target')} ki.source", ki_src)

    for proj in projections:
        pid = f"{proj.get('from')}->{proj.get('to')}"
        for i, src in enumerate(proj.get("sources", []) or []):
            check_one(f"projection {pid} sources[{i}]", src)
        # A pathway the book only states as a blanket sweep wears the same orange badge
        # a binding does, and its bullets are gated the same way.
        check_uncertainty(f"projection {pid}", proj)

    for s in structures:
        for i, src in enumerate(s.get("sources", []) or []):
            check_one(f"structure {s.get('id')} sources[{i}]", src)

    for r in receptors:
        for attr, entry in (r.get("classification") or {}).items():
            for i, src in enumerate(entry.get("sources") or []):
                check_one(f"receptor {r.get('id')} classification[{attr}] sources[{i}]", src)
        # Per-region expression sources are quote-checked like any other (the gate
        # that keeps a future "5-HT2A is dense in the PFC" citation honest).
        for base, srcs in (r.get("location_sources") or {}).items():
            for i, src in enumerate(srcs or []):
                check_one(f"receptor {r.get('id')} location_sources[{base}][{i}]", src)
        # The density profile's quote carries the z per region and the cross-donor
        # agreement, so gating it verbatim is what keeps those numbers honest.
        for i, src in enumerate((r.get("density") or {}).get("sources") or []):
            check_one(f"receptor {r.get('id')} density sources[{i}]", src)

    for tid, tinfo in (meta.get("drug_targets", {}) or {}).items():
        if isinstance(tinfo, dict):
            for i, src in enumerate(tinfo.get("sources", []) or []):
                check_one(f"target {tid} sources[{i}]", src)
            # A non-receptor target's per-region expression sources, quote-checked
            # like the receptor ones (same honesty gate for a future citation).
            for base, srcs in (tinfo.get("location_sources") or {}).items():
                for i, src in enumerate(srcs or []):
                    check_one(f"target {tid} location_sources[{base}][{i}]", src)
            for i, src in enumerate((tinfo.get("density") or {}).get("sources") or []):
                check_one(f"target {tid} density sources[{i}]", src)

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

    def check_ki(ctx, binding):
        """Gate one binding's PDSP-CSV Ki (a metabolite binding's Ki is checked the same
        way as a drug's). Returns 1 if a CSV row was confirmed, else 0."""
        nonlocal n_ki
        ki = binding.get("ki")
        if not ki:
            return
        src = ki.get("source") or {}
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

    for drug in drugs:
        did = drug.get("id")
        for binding in drug.get("bindings", []):
            check_ki(f"drug {did} binding {binding.get('target')} ki", binding)
        for m in drug.get("metabolites", []) or []:
            for binding in m.get("bindings", []) or []:
                check_ki(f"drug {did} metabolite {m.get('name')} binding "
                         f"{binding.get('target')} ki", binding)
    if ki_skipped:
        report.warn(f"Ki CSV absent for {sorted(ki_skipped)} (author-only material); "
                    f"skipped the ki-row-in-CSV check there")
    if report.errors == ki_before:
        report.ok(f"every checkable Ki annotation ({n_ki}) cites a real CSV row"
                  if n_ki else "no Ki annotations to verify yet")


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
    is_combo = lambda d: bool(re.search(r"[+–—]", d.get("name", "")))
    ki_drugs = [d for d in drugs if d.get("bindings") and not is_combo(d)]
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
        report.warn(f"drug {did!r}: no measured Ki on any binding "
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
    is_combo = lambda d: bool(re.search(r"[+–—]", d.get("name", "")))

    a_flags, b_flags = [], []
    for drug in drugs:
        if is_combo(drug):
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
        report.warn(
            f"drug {did!r}: {system} flow modeled {direction} ({drivers}) but its "
            f"postsynaptic {system} bindings net-{lean} ({', '.join(blocked)})")
    for did, system, recs, regs in sorted(b_flags):
        report.warn(
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


def main():
    report = Report()
    print(f"neurarium data integrity check\nreading {DATA_DIR}")

    meta = load_meta(report)
    structures = load_jsonl(report, "structures")
    projections = _expand_mirrored(load_jsonl(report, "projections"))
    circuits = load_jsonl(report, "circuits")
    projection_groups = load_jsonl(report, "projection_groups")
    receptors = load_jsonl(report, "receptors")
    drugs = load_jsonl(report, "drugs")

    # Rehydrate the externalized source quotes in place (collecting referenced +
    # dangling ids), so every check below sees the original inline source shape;
    # then report the quote table's referential integrity.
    quotes_by_id = load_quotes(report)
    referenced, dangling = set(), []
    rehydrate_quotes([meta, structures, projections, circuits, projection_groups,
                      receptors, drugs], quotes_by_id, referenced, dangling)
    check_quotes(report, quotes_by_id, referenced, dangling)

    args = (report, meta, structures, projections, circuits, projection_groups,
            receptors, drugs)
    check_duplicates(*args)
    check_reachability(*args)
    check_todos(*args)
    check_provenance(*args)
    check_sources(report, meta, drugs, projections, structures, receptors)
    check_connectivity(report, structures, projections)
    check_ki_coverage(report, meta, drugs)
    check_flow_consistency(report, meta, drugs, projections, receptors)
    check_changelog(report)
    check_innervation(report, meta, structures, projections, receptors)

    print(f"\nSummary: {report.errors} error(s), {report.warnings} warning(s)")
    if report.errors:
        print("FAILED: fix the errors above (warnings are informational).")
        return 1
    print("PASSED (warnings are informational).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
