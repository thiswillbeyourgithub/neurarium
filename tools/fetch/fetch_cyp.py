#!/usr/bin/env python
"""Read Stahl's per-drug ``Pharmacokinetics`` block for the ``drug_enzymes`` pass.

Corpus #1 prints, in every monograph, a terse and remarkably regular block whose CYP
lines already state the role the drug plays::

    Substrate for CYP2D6 and CYP1A2
    Metabolized primarily by CYP1A2
    Inhibits CYP2C19

This module is the half of the CYP pipeline that knows how that book is shaped: which
pages a drug's monograph spans, how to pull its ``Pharmacokinetics`` bullets out of the
dump, which enzyme names the dataset recognises, and how to re-confirm a bullet
verbatim on a page inside the drug's own range.

It states no claim of its own. ``fetch_cyp_worklist.py`` uses these to offer candidate
bullets, a model reads them, and ``tools/sourcing/apply_cyp_sources.py`` gates the
answer. Regular as the block is, its lines still coordinate ("Inhibits CYP2C19 (and
perhaps CYP2C9)"), still hedge, and still describe the metabolite rather than the drug
("[+]-alpha-HTBZ is further metabolized in part by CYP2D6"), so the reading is a
judgement and belongs to the judge.

Only the ``Pharmacokinetics`` block is read here. The ``Drug Interactions`` block names
isoforms constantly, but most of its sentences are about *other* drugs acting on this
one ("Use of agomelatine with potent CYP1A2 inhibitors ... is contraindicated"), so
attributing the role to the subject drug is wrong roughly as often as it is right.

A library, not a script: import it, do not run it.
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))

import check_data  # noqa: E402  (reuse the quote gate's normalizer, one definition)

STAHL = os.path.join(REPO, "data_sources", "books", "stahl")
DUMP = os.path.join(STAHL, "stahl_dump.jsonl")
PAGES = os.path.join(STAHL, "pages")
INDEX = os.path.join(STAHL, "INDEX.md")

CYP_RE = re.compile(r"CYP\s?([1-4][A-Z]\d{1,2})((?:\s*/\s*\d?[A-Z]?\d{1,2})*)", re.I)
INDEX_ROW = re.compile(r"\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\[(\d+)-(\d+)\]")

# The non-cytochrome clearance routes the ENZYMES vocabulary carries, as the phrases a
# source spells them with. Lives here, beside CYP_RE, because both this Stahl pass and
# the Wikipedia one read the same sentences for the same claim: a drug cleared by one
# of these has no CYP row at all, so reading only CYP made it look unmetabolized.
# Only CES1 by name ("carboxylesterase" alone does not say which one, and CES2 is a
# different enzyme). MAO is deliberately out: it is a modeled drug target too, so a
# sentence naming it is usually about the drug acting ON it, not being cleared BY it.
NON_CYP_ENZYMES = [
    (re.compile(r"\balcohol\s+dehydrogenase\b", re.I), "adh"),
    (re.compile(r"\bCES-?1\b|\bcarboxylesterase\s*1\b|\bhCE-?1\b", re.I), "ces1"),
    (re.compile(r"\bFMO-?3\b", re.I), "fmo3"),
    (re.compile(r"\bUGT-?1A4\b", re.I), "ugt1a4"),
    (re.compile(r"\bUGT-?1A9\b", re.I), "ugt1a9"),
    (re.compile(r"\bUGT-?2B7\b", re.I), "ugt2b7"),
    (re.compile(r"\bUGT-?2B15\b", re.I), "ugt2b15"),
    # An isoform pattern cannot be swallowed by this generic one: \b does not fall
    # between "UGT" and "2B7".
    (re.compile(r"\bUGTs?\b|\bglucuronidation\b", re.I), "ugt"),
]
# What a role verb must govern to count: a cytochrome, or one of the routes above.
ENZYME_RE = re.compile("|".join([CYP_RE.pattern]
                                + [p.pattern for p, _ in NON_CYP_ENZYMES]), re.I)


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
    for pat, enzyme in NON_CYP_ENZYMES:
        if pat.search(text):
            found.append(enzyme)
    return list(dict.fromkeys(found))


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
