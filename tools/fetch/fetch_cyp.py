#!/usr/bin/env python
"""Extract each drug's cytochrome-P450 roles from Stahl's Pharmacokinetics block.

Corpus #1 (Stahl's Prescriber's Guide) prints, in every monograph, a terse and
remarkably regular ``Pharmacokinetics`` block whose CYP lines already state the
*role* the drug plays:

    Substrate for CYP2D6 and CYP1A2
    Metabolized primarily by CYP1A2
    Inhibits CYP2C19
    Weak inhibitor of CYP2D6

That regularity is why this pass needs **no LLM at all**: the sentence shape is as
fixed as the "Neuroscience-based Nomenclature:" line that ``apply_nbn_sources.py``
greps, so a pattern match plus the ordinary verbatim quote gate is a *stronger*
guarantee than a judge would be. Everything here is deterministic and offline.

Deliberately narrow, because precision matters more than yield:

* only the ``Pharmacokinetics`` block is read. The ``Drug Interactions`` block also
  names isoforms constantly, but most of those sentences are about *other* drugs
  acting on this one ("Use of agomelatine with potent CYP1A2 inhibitors ... is
  contraindicated"), so attributing the role to the subject drug there would be
  wrong roughly as often as right. That block is a separate, judged pass if it is
  ever wanted.
* a bullet is used only when the verb has the drug itself as subject
  (``Substrate for``/``Metabolized by``/``Inhibits``/``Induces``). A bullet naming
  someone else's inhibitors (plural "inhibitors", "inhibitors of") is skipped.
* every accepted bullet is re-confirmed **verbatim** on a page inside the drug's own
  page range (INDEX.md), using check_data's own normalizer, and the page it was
  found on becomes the quote's ``page``. A bullet that does not gate is dropped, not
  guessed: Stahl's page breaks split a few lines mid-sentence and a spliced-in DOI
  footer wrecks a few more.

Output: ``tools/generated_cache/drug_enzymes.json``, committed and read at build time
by ``generate_data.py`` (like ``expression_density.json``), so the emitted data stays
reproducible without the author-side book tree.

Usage (from the repo root):
    python tools/fetch/fetch_cyp.py            # rewrite the cache
    python tools/fetch/fetch_cyp.py --dry-run  # report only
    python tools/fetch/fetch_cyp.py --verbose  # also list every dropped bullet
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))

import check_data  # noqa: E402  (reuse the quote gate's normalizer, one definition)
import drugs_io  # noqa: E402

STAHL = os.path.join(REPO, "data_sources", "books", "stahl")
DUMP = os.path.join(STAHL, "stahl_dump.jsonl")
PAGES = os.path.join(STAHL, "pages")
INDEX = os.path.join(STAHL, "INDEX.md")
OUT = os.path.join(REPO, "tools", "generated_cache", "drug_enzymes.json")

CYP_RE = re.compile(r"CYP\s?([1-4][A-Z]\d{1,2})((?:\s*/\s*\d?[A-Z]?\d{1,2})*)", re.I)
INDEX_ROW = re.compile(r"\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\[(\d+)-(\d+)\]")

# Subject-is-the-drug patterns, checked in order (substrate first). Each requires the
# verb to govern an isoform a few words later, not merely to appear in the bullet:
# amitriptyline's "Metabolized to an active metabolite, nortriptyline, which is
# predominantly a norepinephrine reuptake inhibitor, by demethylation via CYP1A2" is a
# substrate claim, and its "inhibitor" describes the metabolite, not a CYP.
ROLE_PATTERNS = [
    ("substrate", re.compile(r"\bsubstrate\b(?:\s+\S+){0,3}?\s*CYP|"
                             r"\bmetaboliz\w*\b.*?\b(?:by|via)\b(?:\s+\S+){0,3}?\s*CYP", re.I)),
    ("inhibitor", re.compile(r"\binhibit(?:s|or)\b(?:\s+\S+){0,3}?\s*CYP", re.I)),
    ("inducer", re.compile(r"\binduc(?:es|er)\b(?:\s+\S+){0,3}?\s*CYP", re.I)),
]
# A bullet that talks about OTHER drugs' effect on this one, never about its own role.
VICTIM_RE = re.compile(r"inhibitors\b|\binducers\b|may be increased|"
                       r"may increase|plasma levels of|clearance of|coadminist|co-administ",
                       re.I)
# "Nortriptyline is the active metabolite of amitriptyline, formed by demethylation
# via CYP1A2" states which enzyme *made* this drug, not one it is a substrate of. A
# different claim (the `formed_by` node the metabolism survey describes), so drop it
# here rather than mislabel it.
ORIGIN_RE = re.compile(r"\bis (?:the|an?) (?:active )?metabolite of\b", re.I)

STRENGTH_RE = [
    ("major", re.compile(r"\bprimarily|mainly|major\b", re.I)),
    ("minor", re.compile(r"\bminor\b|\bpartly\b|\bin part\b|to a lesser extent", re.I)),
    ("strong", re.compile(r"\bpotent(?:ly)?|strong(?:ly)?\b", re.I)),
    ("weak", re.compile(r"\bweak(?:ly)?|mild(?:ly)?\b", re.I)),
    ("moderate", re.compile(r"\bmoderate(?:ly)?\b", re.I)),
]
# Which strength vocabulary each role may use (a substrate is major/minor, an
# inhibitor or inducer strong/moderate/weak); keeps a stray "primarily" off an
# inhibitor row.
ROLE_STRENGTHS = {
    "substrate": {"major", "minor"},
    "inhibitor": {"strong", "moderate", "weak"},
    "inducer": {"strong", "moderate", "weak"},
}


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def load_index() -> dict[str, tuple[int, int]]:
    """Stahl drug name (lowercased) -> its (first, last) page-file number."""
    out = {}
    with open(INDEX, encoding="utf-8") as f:
        for line in f:
            m = INDEX_ROW.match(line)
            if m:
                out[m.group(1).strip().lower()] = (int(m.group(2)), int(m.group(3)))
    return out


def load_pk_blocks() -> dict[str, str]:
    """Stahl drug name (lowercased) -> its concatenated Pharmacokinetics answers."""
    out: dict[str, str] = collections.defaultdict(str)
    with open(DUMP, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if (rec.get("Question") or "").strip() == "Pharmacokinetics?":
                out[rec["Drug"].strip().lower()] += " " + (rec.get("Answer") or "")
    return out


def isoforms(text: str) -> list[str]:
    """Every isoform named in a bullet, as ids ('cyp2c19').

    Handles Stahl's two shorthands for a pair: 'CYP2C9/2C19' spells the second one
    out, while 'CYP3A4/5' gives only the trailing digit and means CYP3A5, so a
    shorthand half inherits whatever the first isoform does not supply.
    """
    found = []
    for m in CYP_RE.finditer(text):
        head = m.group(1).upper()                       # e.g. "2C9"
        found.append("cyp" + head.lower())
        for part in re.findall(r"[^/\s]+", m.group(2) or ""):
            part = part.upper()
            if not re.match(r"^\d[A-Z]", part):         # "5" -> family of the head
                part = head[:2] + part
            found.append("cyp" + part.lower())
    return list(dict.fromkeys(found))


def classify(bullet: str) -> tuple[str | None, str | None]:
    """(role, strength) for a bullet whose subject is the drug, else (None, None)."""
    if VICTIM_RE.search(bullet) or ORIGIN_RE.search(bullet):
        return None, None
    first_isoform = CYP_RE.search(bullet)
    head = bullet[: first_isoform.start()] if first_isoform else bullet
    for role, pat in ROLE_PATTERNS:
        if pat.search(bullet):
            # A qualifier only counts when the bullet carries exactly one of them AND it
            # precedes the FIRST isoform, so it plainly governs the whole list.
            # "Metabolized primarily by CYP2D6 and CYP3A4" is major for both; but
            # carbamazepine's "an inducer of CYP2C9 and weakly of CYP1A2 and CYP2C19"
            # qualifies only part of its list, and sildenafil's "primarily by CYP3A4
            # (major route) and CYP2C9 (minor route)" splits per isoform, so both get
            # none rather than a strength copied onto the wrong isoform.
            present = {s for s, spat in STRENGTH_RE
                       if s in ROLE_STRENGTHS[role] and spat.search(bullet)}
            if len(present) == 1:
                strength = present.pop()
                spat = dict(STRENGTH_RE)[strength]
                if spat.search(head):
                    return role, strength
            return role, None
    return None, None


def page_holding(quote: str, lo: int, hi: int) -> int | None:
    """The page-file number inside [lo, hi] whose text contains `quote` verbatim."""
    needle = check_data.normalize_for_match(quote)
    for page in range(lo, hi + 1):
        path = os.path.join(PAGES, f"{page}.md")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            if needle in check_data.normalize_for_match(f.read()):
                return page
    return None


def gate(bullet: str, lo: int, hi: int) -> tuple[int, str] | None:
    """Confirm a bullet on the drug's pages, shortening it once if the full one fails.

    Two artifacts of the page split defeat an otherwise-fine bullet: the dump
    sometimes carries a running header into it ("Inhibits CYP3A4 FLUOXETINE
    (continued)"), and a word hyphenated across a line break rejoins differently on
    the page than in the dump ("long- lasting" vs "long-\\nlasting"). Both live
    *after* the isoform, so retry with the bullet cut just past its last isoform: a
    shorter quote is still a verbatim quote, and it still carries the whole claim.
    """
    page = page_holding(bullet, lo, hi)
    if page is not None:
        return page, bullet
    last = None
    for last in CYP_RE.finditer(bullet):
        pass
    if last is None:
        return None
    short = bullet[: last.end()].strip()
    if short == bullet:
        return None
    page = page_holding(short, lo, hi)
    return (page, short) if page is not None else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--verbose", action="store_true", help="list dropped bullets too")
    args = ap.parse_args()

    for path in (DUMP, INDEX, PAGES):
        if not os.path.exists(path):
            print(f"missing author-side Stahl tree ({path}); see CLAUDE.local.md")
            return 1

    index = load_index()
    blocks = load_pk_blocks()
    by_name = {d["name"].strip().lower(): d["id"] for d in drugs_io.load_drugs()}

    out: dict[str, list[dict]] = {}
    stats = collections.Counter()
    dropped = []
    for name, answer in sorted(blocks.items()):
        drug_id = by_name.get(name)
        if drug_id is None:
            stats["drug not modeled"] += 1
            continue
        span = index.get(name)
        if span is None:
            stats["drug not in INDEX.md"] += 1
            continue
        rows: dict[tuple[str, str], dict] = {}
        for raw in re.split(r"<br\s*/?>|•", answer):
            bullet = strip_html(raw)
            if not bullet or not CYP_RE.search(bullet):
                continue
            role, strength = classify(bullet)
            if role is None:
                stats["bullet: role not attributable"] += 1
                dropped.append((name, "role", bullet))
                continue
            gated = gate(bullet, *span)
            if gated is None:
                stats["bullet: quote not verbatim on the page range"] += 1
                dropped.append((name, "gate", bullet))
                continue
            page, quote = gated
            for enzyme in isoforms(bullet):
                key = (enzyme, role)
                if key in rows:                # same claim twice: keep the first quote
                    continue
                row = {"enzyme": enzyme, "role": role}
                if strength:
                    row["strength"] = strength
                row["sources"] = [{"corpus": "stahl", "page": page,
                                   "quote": quote, "provenance": "verified"}]
                rows[key] = row
                stats[f"node: {role}"] += 1
        if rows:
            out[drug_id] = [rows[k] for k in sorted(rows)]

    print(f"{len(out)} drugs, {sum(len(v) for v in out.values())} enzyme nodes")
    for key, n in sorted(stats.items()):
        print(f"  {key:<44} {n}")
    iso = collections.Counter(r["enzyme"] for v in out.values() for r in v)
    print("  isoforms:", ", ".join(f"{k}={n}" for k, n in iso.most_common()))
    if args.verbose:
        print("\ndropped bullets:")
        for name, why, bullet in dropped:
            print(f"  [{why}] {name}: {bullet[:110]}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"\nwrote {os.path.relpath(OUT, REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
