#!/usr/bin/env python
"""Where in the book does a quote sit? (Stahl corpus #1 heading resolution.)

A quote source stores a passage and a page number. That is enough to *check* the
quote, but not enough to *read* it: "Blocking muscarinic cholinergic receptors can
cause dry mouth" reads very differently under **How the Drug Works** (a mechanism
the book attributes to the drug) than under **How Drug Causes Side Effects** (a
rule the book prints without a subject). The reader gets that context in the source
tooltip, and an LLM judge gets it in its prompt, only if we store it.

This resolves, for every stored Stahl quote, the **drug** whose monograph the page
belongs to and the **section > subsection** heading the passage sits under, and
writes them to the committed ``tools/generated_cache/quote_headers.json``, which
``data_generators/quote_table.py`` merges onto the quote nodes by id (exactly like
``quote_llm.json``: a derived annotation applied uniformly, never authored per site).

How it works, and why not just "the nearest heading above":

* Each page file is a two-level tree: an ALL-CAPS ``## **SIDE EFFECTS**`` section,
  then Title Case ``## **How Drug Causes Side Effects**`` subsections. So the
  subsection is positional: the last one at or above the quote's offset in the
  page, walking back through earlier pages of the same monograph when the page
  opens mid-section.
* The **section** is NOT positional. The PDF extraction drops ~30 of the 158
  section headings, and the nearest surviving one then leaks in from the previous
  section (or, at a monograph boundary, from the previous *drug*). But Stahl's
  subsection vocabulary is closed and stable: ``Class`` is under THERAPEUTICS in
  all 158 monographs, ``Pharmacokinetics`` under DOSING AND USE. So we derive
  ``subsection -> section`` by majority vote over the whole book and use that,
  falling back to the positional answer only for a subsection too rare to vote on.

Run it from the repo root, author-side (it needs the uncommitted page tree, see
CLAUDE.local.md), after ``generate_data.py`` has emitted the quote table:

    python tools/fetch/fetch_quote_headers.py            # rewrite the cache
    python tools/fetch/fetch_quote_headers.py --dry-run  # report, write nothing

Then re-run ``generate_data.py`` to bake the headings into the emitted quotes.
Deterministic and offline (it only reads files), so a re-run with unchanged pages
rewrites an identical cache. Written with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "tools"))

import check_data  # noqa: E402  (reuse the quote gate's normalizer + INDEX parser)

CORPUS = "stahl"
PAGES = os.path.join(REPO, "data_sources", "books", "stahl", "pages")
QUOTES = os.path.join(REPO, "public", "data", "quotes.jsonl")
CACHE = os.path.join(REPO, "tools", "generated_cache", "quote_headers.json")

_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$")
_HYPHEN_BREAK = re.compile(r"-\s*\n\s*")

# Stahl's closed set of monograph sections, in the order the book prints them.
# Matched **case-sensitively** inside a heading, which is what separates the
# section "SIDE EFFECTS" from the subsection "How Drug Causes Side Effects": the
# book prints a section in caps and a subsection in title case, so a case-blind
# substring test (the first thing tried) mislabels four subsections per monograph.
SECTIONS = (
    "THE ART OF PSYCHOPHARMACOLOGY",
    "THE ART OF SWITCHING",
    "SAFETY AND TOLERABILITY",
    "SPECIAL POPULATIONS",
    "DEPOT FORMULATIONS",
    "SUGGESTED READING",
    "DOSING AND USE",
    "SIDE EFFECTS",
    "THERAPEUTICS",
)

# A subsection name seen fewer times than this across the 158 monographs is not
# voted on (it is either monograph-specific or an OCR artifact); its section falls
# back to the positional answer.
MIN_VOTES = 3


def _clean(text: str) -> str:
    """A heading line stripped of markdown/OCR decoration, whitespace collapsed.

    A ``~~struck~~`` span is dropped **whole**: the extraction wraps the fragments
    it read off the page furniture that way (``## ~~Co~~ **THERAPEUTICS**``), and
    keeping the letters would leave "Co" glued to the heading name."""
    text = re.sub(r"~~.*?~~", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[*_#~\[\]|]", " ", text)).strip()


def _subsection(text: str) -> str:
    """A subsection heading trimmed of the content the extraction merged into it
    (``Brands • Ingrezza`` -> ``Brands``)."""
    return re.split(r"\s*•\s*", text)[0].strip(" :-")


def classify(text: str, drug_names: set[str]) -> tuple[str, str | None, str | None]:
    """Classify one cleaned heading -> ``(kind, name, trailing subsection)``.

    ``kind`` is ``section`` (name = the canonical section), ``drug`` (a monograph
    title, which ends the previous monograph's headings), ``sub`` (a subsection) or
    ``noise`` (a stray page number or extraction fragment).
    """
    for section in SECTIONS:
        at = text.find(section)
        if at >= 0:
            # "DOSING AND USE Usual Dosage Range" merges a section + its first
            # subsection onto one line; "LEE DOSING AND USE" is OCR spill before it.
            tail = _subsection(_clean(text[at + len(section):]))
            return "section", section, (tail or None)
    if check_data.normalize_for_match(text) in drug_names:
        return "drug", text, None
    letters = re.sub(r"[^A-Za-z]", "", text)
    if not letters or letters.isupper():
        return "noise", None, None
    return "sub", _subsection(text), None


class StahlPages:
    """The page tree, indexed once: headings + normalized text per page.

    Callers outside this script (a worklist builder wanting to hand an LLM judge the
    section a candidate quote sits in) should use :meth:`locate`.
    """

    def __init__(self) -> None:
        ranges = check_data.stahl_monograph_ranges()
        self.ok = bool(ranges) and os.path.isdir(PAGES)
        self.drug_names: set[str] = set()
        self.page_drug: dict[int, str] = {}
        self.page_span: dict[int, tuple[int, int]] = {}
        self._pages: dict[int, tuple[list, str]] = {}
        self._section_of: dict[str, str] | None = None
        if not self.ok:
            return
        for title, lo, hi in check_data.stahl_index_rows():
            self.drug_names.add(check_data.normalize_for_match(title))
            for page in range(lo, hi + 1):
                self.page_drug[page] = title
                self.page_span[page] = (lo, hi)

    def page(self, page: int) -> tuple[list, str]:
        """``([(offset, kind, name, tail)], normalized page text)``.

        The offsets index the same normalized string the quote gate matches
        against, so "which heading is above this quote" is a plain comparison.
        The one normalization rule that spans lines (joining a hyphenated line
        break) is applied to the whole page first, which keeps the reconstruction
        byte-identical to ``normalize_for_match`` over the whole file.
        """
        if page not in self._pages:
            path = os.path.join(PAGES, f"{page}.md")
            if not os.path.exists(path):
                self._pages[page] = ([], "")
                return self._pages[page]
            with open(path, encoding="utf-8") as fh:
                raw = _HYPHEN_BREAK.sub("", fh.read())
            marks, parts, offset = [], [], 0
            for line in raw.splitlines():
                head = _HEADING.match(line)
                body = check_data.normalize_for_match(
                    head.group(1) if head else line)
                if head:
                    marks.append((offset,) + classify(_clean(head.group(1)),
                                                      self.drug_names))
                if body:
                    parts.append(body)
                    offset += len(body) + 1
            self._pages[page] = (marks, " ".join(parts))
        return self._pages[page]

    @property
    def section_of(self) -> dict[str, str]:
        """``subsection -> section``, by majority vote over every monograph."""
        if self._section_of is None:
            votes: dict[str, collections.Counter] = collections.defaultdict(
                collections.Counter)
            for lo, hi in set(self.page_span.values()):
                section = None
                for page in range(lo, hi + 1):
                    for _off, kind, name, tail in self.page(page)[0]:
                        if kind == "section":
                            section = name
                            if tail:
                                votes[tail][section] += 1
                        elif kind == "sub" and section:
                            votes[name][section] += 1
            self._section_of = {
                sub: counter.most_common(1)[0][0]
                for sub, counter in votes.items()
                if sum(counter.values()) >= MIN_VOTES
            }
        return self._section_of

    def locate(self, page: int, quote: str) -> dict[str, str] | None:
        """``{drug, section, subsection}`` for a quote on ``page``, or ``None``.

        Only the keys it can actually resolve are present: a heading it cannot
        pin down is **omitted**, never guessed, so a reader never sees a
        confidently wrong breadcrumb.
        """
        if not self.ok:
            return None
        marks, text = self.page(page)
        at = text.find(check_data.normalize_for_match(quote))
        if at < 0:
            return None
        sub = positional = None
        for offset, kind, name, tail in marks:
            if offset > at:
                break
            if kind == "drug":
                sub = positional = None
            elif kind == "section":
                positional, sub = name, tail
            elif kind == "sub":
                sub = name
        lo, _hi = self.page_span.get(page, (page, page))
        back = page - 1
        while sub is None and back >= lo:      # a page opening mid-section, but
            for _off, kind, name, tail in self.page(back)[0]:   # never out of the
                if kind == "drug":                              # monograph
                    sub, positional = None, None
                elif kind == "section":
                    positional, sub = name, tail or sub
                elif kind == "sub":
                    sub = name
            back -= 1
        out = {}
        if self.page_drug.get(page):
            out["drug"] = self.page_drug[page]
        section = self.section_of.get(sub) if sub else None
        if section is None and sub is None:
            section = positional      # no subsection to vote with; take the page's
        if section:
            out["section"] = section
        if sub:
            out["subsection"] = sub
        return out or None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written, change nothing")
    args = ap.parse_args()

    pages = StahlPages()
    if not pages.ok:
        print(f"Stahl page tree or INDEX.md absent under {PAGES} (author-side "
              f"material, see CLAUDE.local.md); nothing to do.")
        return 1
    if not os.path.exists(QUOTES):
        print(f"{QUOTES} missing; run tools/generate_data.py first.")
        return 1

    resolved, partial, unresolved = {}, 0, []
    total = 0
    with open(QUOTES, encoding="utf-8") as fh:
        for line in fh:
            q = json.loads(line)
            if q.get("corpus") != CORPUS or q.get("page") is None:
                continue
            total += 1
            found = pages.locate(q["page"], q.get("quote") or "")
            if not found:
                unresolved.append((q["page"], (q.get("quote") or "")[:60]))
                continue
            resolved[q["id"]] = found
            if len(found) < 3:
                partial += 1

    print(f"{CORPUS}: {len(resolved)}/{total} quotes located "
          f"({len(resolved) - partial} with a full drug + section + subsection, "
          f"{partial} partial, {len(unresolved)} unresolved)")
    print(f"subsection -> section map: {len(pages.section_of)} entries")
    for page, quote in unresolved[:10]:
        print(f"  unresolved  p.{page}  {quote!r}")

    payload = {
        "_readme": ("Derived by tools/fetch/fetch_quote_headers.py from the "
                    "author-side Stahl page tree; applied onto the quote nodes by "
                    "data_generators/quote_table.py. Do not hand-edit."),
        "sections": dict(sorted(pages.section_of.items())),
        "quotes": {qid: resolved[qid] for qid in sorted(resolved)},
    }
    if args.dry_run:
        print("--dry-run: cache not written")
        return 0
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")
    print(f"wrote {CACHE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
